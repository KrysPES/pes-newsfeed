"""
Episode detection.

Finds the market moves worth annotating. Deterministic, no network, no model.

The definition, which must not drift from the historic seed data or the chart
ends up with two incompatible sets of markers on it:

    rolling weekly move = % change vs 5 TRADING days earlier, computed daily
    breach              = |rolling weekly move| > 10%
    episode             = a run of consecutive trading days in breach
    trigger day         = the largest single-day move, in the breach direction,
                          inside the 5 trading days that produced the move

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
BREACH_PCT = 10.0       # |rolling weekly move| above this is a breach
DRIFT_PCT = 5.0         # no single day above this = a grind, not an event


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
