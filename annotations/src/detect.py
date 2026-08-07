"""
Episode detection.

Finds the market moves worth annotating. Deterministic, no network, no model.

The definition, which must not drift from the historic seed data or the chart
ends up with two incompatible sets of markers on it:

    DEFINITION v2 (July 2026). Two detectors, results merged by trigger day:

    A. Weekly episode
       rolling weekly move = % change vs 5 TRADING days earlier, computed daily
       breach              = |rolling weekly move| > 8%          (v1 was 10%)
       episode             = a run of consecutive trading days in breach
       trigger day         = the largest single-day move, in the breach
                             direction, inside the 5 days that produced it

    B. Gradient shock (new in v2)
       A single day whose move is large relative to how that contract has been
       behaving: |1-day move| > 3.5x the contract's typical daily move over the
       trailing 60 trading days, with a 3% absolute floor. Volatility scaling is
       what makes it regime-aware: a 4% day fires in a calm market and stays
       silent in crisis conditions where 4% days are routine. The shock day is
       its own trigger day, because the shock day IS the event day.

    Every annotation from the v1 definition remains valid under v2: a 10%
    weekly breach is also an 8% one.

The trigger day is what gets labelled, not the breach date. This matters. The
breach date is where a cumulative five day move crossed the threshold, and on
only about a third of historic episodes did the news actually land that day.
Labelling the breach date puts the marker up to a week away from the event.

Contracts that have expired flatline in most price exports. Feeding a flat tail
in produces no false breaches (a flat series has zero change) but it does skew
observation counts, so `truncate_flat` trims it.

INPUT RULE, and the one most likely to be broken by accident: pass RAW season
contract series only (Win-26, Sum-27, each as its own series). Never pass a
stitched "front season" or "second season" chain. A continuous chain jumps
every April and October as it rolls onto the next season's price, and the
detector cannot tell that jump from a market event, so it will manufacture a
fake episode at every rollover. The same applies to continuous front-month
chains. The historic dataset was built entirely on raw contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date as Date
from typing import Iterable, Sequence


WINDOW = 5              # trading days in the rolling window
BREACH_PCT = 8.0        # |rolling weekly move| above this is a breach (v2)
DRIFT_PCT = 5.0         # no single day above this = a grind, not an event
SHOCK_Z = 3.5           # day move vs trailing typical day (v2)
SHOCK_FLOOR_PCT = 3.0   # absolute minimum day move for a shock (v2)
SHOCK_LOOKBACK = 60     # trading days of trailing volatility
SHOCK_MIN_OBS = 30      # minimum observations before a shock can fire


@dataclass
class Episode:
    breach_date: str
    window_start: str
    window_end: str
    trigger_day: str
    trigger_move_pct: float
    trigger_contract: str
    direction: str                  # "Up" | "Down"
    fuel_scope: str                 # "Gas only" | "Electricity only" | "Both"
    largest_weekly_pct: float
    largest_weekly_contract: str
    breaches: dict = field(default_factory=dict)
    length_trading_days: int = 1
    is_drift: bool = False

    def as_dict(self):
        return asdict(self)


def truncate_flat(series: dict[str, float]) -> dict[str, float]:
    """Drop the flat tail an expired contract leaves behind."""
    dates = sorted(series)
    last_change = None
    for prev, cur in zip(dates, dates[1:]):
        if series[cur] != series[prev]:
            last_change = cur
    if last_change is None:
        return dict(series)
    return {d: series[d] for d in dates if d <= last_change}


def _pct_change(series: dict[str, float], dates: Sequence[str], lag: int) -> dict[str, float]:
    out = {}
    for i in range(lag, len(dates)):
        prev, cur = series.get(dates[i - lag]), series.get(dates[i])
        if prev in (None, 0) or cur is None:
            continue
        out[dates[i]] = (cur / prev - 1.0) * 100.0
    return out


def detect(
    gas: dict[str, dict[str, float]],
    power: dict[str, dict[str, float]],
    breach_pct: float = BREACH_PCT,
    window: int = WINDOW,
) -> list[Episode]:
    """
    gas / power: {contract_name: {"YYYY-MM-DD": close_price}}

    Returns episodes oldest first. Feed it the full history to rebuild
    everything, or a trailing slice to detect only what is new. Detection is
    stateless, so the same input always gives the same output.
    """
    books = {"Gas": {k: truncate_flat(v) for k, v in gas.items()},
             "Electricity": {k: truncate_flat(v) for k, v in power.items()}}

    all_dates = sorted({d for book in books.values() for s in book.values() for d in s})
    if len(all_dates) <= window:
        return []
    idx = {d: i for i, d in enumerate(all_dates)}

    weekly, daily = {}, {}
    for fuel, book in books.items():
        for contract, series in book.items():
            dates = sorted(series)
            weekly[(fuel, contract)] = _pct_change(series, dates, window)
            daily[(fuel, contract)] = _pct_change(series, dates, 1)

    # which contracts breach on each date
    breached: dict[str, dict[tuple[str, str], float]] = {}
    for key, moves in weekly.items():
        for d, v in moves.items():
            if abs(v) > breach_pct:
                breached.setdefault(d, {})[key] = v

    episodes: list[Episode] = []
    open_ep: list[str] = []

    def close(run: list[str]):
        if not run:
            return
        d = run[0]
        br = breached[d]
        lead_key, lead_val = max(br.items(), key=lambda kv: abs(kv[1]))
        direction = "Up" if lead_val > 0 else "Down"

        i = idx[d]
        win = all_dates[max(0, i - window): i + 1]

        best = None
        for (fuel, contract), _ in br.items():
            for wd in win[1:]:
                v = daily.get((fuel, contract), {}).get(wd)
                if v is None:
                    continue
                if (direction == "Up" and v <= 0) or (direction == "Down" and v >= 0):
                    continue
                if best is None or abs(v) > abs(best[2]):
                    best = (wd, f"{fuel} {contract}", v)
        if best is None:                       # degenerate, fall back to the breach date
            best = (d, f"{lead_key[0]} {lead_key[1]}", 0.0)

        fuels = sorted({k[0] for k in br})
        scope = "Both" if len(fuels) == 2 else f"{fuels[0]} only"

        episodes.append(Episode(
            breach_date=d,
            window_start=win[0],
            window_end=d,
            trigger_day=best[0],
            trigger_move_pct=round(best[2], 2),
            trigger_contract=best[1],
            direction=direction,
            fuel_scope=scope,
            largest_weekly_pct=round(lead_val, 2),
            largest_weekly_contract=f"{lead_key[0]} {lead_key[1]}",
            breaches={f"{k[0]} {k[1]}": round(v, 2) for k, v in br.items()},
            length_trading_days=len(run),
            is_drift=abs(best[2]) < DRIFT_PCT,
        ))

    for d in all_dates:
        if d in breached:
            open_ep.append(d)
        else:
            close(open_ep)
            open_ep = []
    close(open_ep)

    return episodes


def detect_shocks(
    gas: dict[str, dict[str, float]],
    power: dict[str, dict[str, float]],
    z_threshold: float = SHOCK_Z,
    floor_pct: float = SHOCK_FLOOR_PCT,
) -> list[Episode]:
    """Gradient shocks: single days that are violent relative to that contract's
    own recent behaviour. Same input rule as detect(): raw contract series only,
    never continuous chains."""
    books = {"Gas": {k: truncate_flat(v) for k, v in gas.items()},
             "Electricity": {k: truncate_flat(v) for k, v in power.items()}}
    hits: dict[str, tuple] = {}          # date -> best (fuel, contract, move, z)

    for fuel, book in books.items():
        for contract, series in book.items():
            dates = sorted(series)
            moves = []                    # (date, pct move)
            for prev, cur in zip(dates, dates[1:]):
                if series[prev]:
                    moves.append((cur, (series[cur] / series[prev] - 1.0) * 100.0))
            for i, (d, m) in enumerate(moves):
                if i < SHOCK_MIN_OBS:
                    continue
                window = [abs(x) for _, x in moves[max(0, i - SHOCK_LOOKBACK):i]]
                typical = (sum(window) / len(window)) * 1.2533   # ~std for normal moves
                if typical <= 0:
                    continue
                if abs(m) > floor_pct and abs(m) / typical > z_threshold:
                    prior = hits.get(d)
                    if prior is None or abs(m) > abs(prior[2]):
                        hits[d] = (fuel, contract, m, abs(m) / typical)

    out = []
    for d in sorted(hits):
        fuel, contract, m, z = hits[d]
        # a 5-trading-day window ending on the shock day, for news search
        all_dates = sorted({x for book in books.values() for s2 in book.values() for x in s2})
        i = all_dates.index(d)
        win_start = all_dates[max(0, i - WINDOW)]
        out.append(Episode(
            breach_date=d, window_start=win_start, window_end=d,
            trigger_day=d, trigger_move_pct=round(m, 2),
            trigger_contract=f"{fuel} {contract}",
            direction="Up" if m > 0 else "Down",
            fuel_scope=f"{fuel} only",
            largest_weekly_pct=round(m, 2),
            largest_weekly_contract=f"{fuel} {contract}",
            breaches={f"{fuel} {contract}": round(m, 2)},
            length_trading_days=1, is_drift=False,
        ))
    return out


def detect_all(
    gas: dict[str, dict[str, float]],
    power: dict[str, dict[str, float]],
) -> list[Episode]:
    """The v2 detector: weekly episodes plus gradient shocks, merged so one
    trigger day yields one episode (the weekly record wins, it carries more
    context). This is what the daily job should call."""
    best: dict[str, Episode] = {}
    for e in detect(gas, power):
        prior = best.get(e.trigger_day)
        # two weekly runs can share one trigger day; keep the larger move
        if prior is None or abs(e.largest_weekly_pct) > abs(prior.largest_weekly_pct):
            best[e.trigger_day] = e
    for e in detect_shocks(gas, power):
        best.setdefault(e.trigger_day, e)       # weekly record wins, more context
    return [best[d] for d in sorted(best)]


def new_episodes(episodes: Iterable[Episode], known_dates: set[str]) -> list[Episode]:
    """Episodes whose trigger day is not already annotated. Trigger day is the
    identity, because two episodes can share one, and on the chart that is a
    single event with a single marker."""
    seen = set(known_dates)
    out = []
    for e in episodes:
        if e.trigger_day in seen:
            continue
        seen.add(e.trigger_day)
        out.append(e)
    return out
