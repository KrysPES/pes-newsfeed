"""Data steps: discontinuities in a price series that are not market moves.

Why this is in the annotations package. The detector reads the same workbook
columns the terminal charts, and a column that jumps 37% overnight and stays
there looks exactly like a violent single day shock. It is not one. Five such
clusters sit in the live Market Pricing workbook:

    2023-01-05  the WHOLE gas curve, +8.6% to +17.4%, both tabs
    2023-02-07  electricity Win-26 and its six monthlies, about +37%
    2023-04-05  electricity Win-28 and eleven monthlies, +12% to +20%
    2023-09-26  electricity Win-27 and Win-28 and twelve monthlies, +25% to +34%
    2025-03-04  electricity Sum-30 and five 2030 monthlies, about -15%

Feeding those to the detector manufactures episodes that no news can explain,
which is a plausible source of some of the dates already quarantined as
suspect. Excluding them costs nothing: a real event on the same day still
reaches the detector through every other contract.

Size alone cannot tell a splice from a real move. March 2026 moved 17% to 24%
in a day and held. What separates them is the OTHER FUEL: a splice appears in
one fuel while the other sits still, a real move appears in both. Across the
eight step dates checked in the live workbook the five suspect ones had the
other fuel inside 5% on the same day and the three genuine ones had it moving
10% to 12% the same way. No overlap.

Stdlib only, same as the rest of the package.

    from stepguard import step_dates, scan_pairs
    bad = step_dates(gas["Win-26"], power["Win-26"])
"""
from __future__ import annotations

STEP_PCT = 15.0          # single day move that gets looked at
PERSIST_TOL = 5.0        # the new level must hold, not snap back
PERSIST_DAYS = 5         # over this many following closes
CORROBORATE_PCT = 5.0    # other fuel moving less than this is no corroboration


def _day_move(series: dict[str, float], dates: list[str], date: str) -> float | None:
    try:
        i = dates.index(date)
    except ValueError:
        return None
    if i == 0:
        return None
    prev = series[dates[i - 1]]
    if not prev:
        return None
    return (series[date] / prev - 1.0) * 100.0


def steps(series: dict[str, float], references: list[dict[str, float]] | None = None) -> list[dict]:
    """Steps in `series` that no reference corroborates.

    `references` should be the SAME delivery period in the other fuel. An
    unchecked step is not reported: with no reference carrying data that day
    we do not know, and a false positive here would put a warning about the
    exchange's own data in front of a client.
    """
    dates = sorted(series)
    refs = [(r, sorted(r)) for r in (references or []) if r]
    out: list[dict] = []

    for i in range(1, len(dates)):
        date = dates[i]
        prev = series[dates[i - 1]]
        if not prev:
            continue
        here = series[date]
        pct = (here / prev - 1.0) * 100.0
        if abs(pct) < STEP_PCT:
            continue

        # Not the return leg of a one day spike. A spike up and straight back
        # down reads as two steps: the second lands on a level that then holds,
        # because it is the level the series was on all along. Checking that the
        # previous day did not make the opposite move at similar size kills that
        # without demanding a quiet run in, which would miss a splice landing in
        # a volatile week.
        prev_move = _day_move(series, dates, dates[i - 1]) if i > 1 else None
        if prev_move is not None and (prev_move > 0) != (pct > 0) and abs(prev_move) >= abs(pct) * 0.6:
            continue

        after = [series[d] for d in dates[i + 1 : i + 1 + PERSIST_DAYS]]
        if not after:
            continue
        mean = sum(after) / len(after)
        if abs((mean / here - 1.0) * 100.0) > PERSIST_TOL:
            continue  # a spike that snaps back is a market, not a splice

        checked = 0
        corroborated = False
        for ref, rdates in refs:
            move = _day_move(ref, rdates, date)
            if move is None:
                continue
            checked += 1
            if abs(move) >= CORROBORATE_PCT and (move > 0) == (pct > 0):
                corroborated = True
                break
        if corroborated or not checked:
            continue

        out.append({"date": date, "pct": round(pct, 1), "before": prev, "after": here})
    return out


def step_dates(series: dict[str, float], reference: dict[str, float] | None = None) -> set[str]:
    """Just the dates, for filtering."""
    return {s["date"] for s in steps(series, [reference] if reference else [])}


def scan_pairs(gas: dict[str, dict[str, float]], power: dict[str, dict[str, float]]) -> dict[str, list[dict]]:
    """Every contract in both books, each checked against its opposite number.

    Returns {"gas Win-26": [step, ...]} for whatever is found. This is the
    standing check: run it after each data refresh and a new splice surfaces
    the same week rather than three years later.
    """
    found: dict[str, list[dict]] = {}
    for fuel, book, other in (("gas", gas, power), ("electricity", power, gas)):
        for period, series in (book or {}).items():
            hits = steps(series, [(other or {}).get(period)])
            if hits:
                found["%s %s" % (fuel, period)] = hits
    return found


def excluded_dates(gas: dict[str, dict[str, float]], power: dict[str, dict[str, float]]) -> set[str]:
    """Trigger days the detector should not raise an episode on.

    Deliberately a set of DATES rather than of contract and date pairs. A
    splice hits a block of contracts at once, and the detector's episode is
    keyed on the trigger day across the whole book, so a per contract
    exclusion would still let the same bad day through on its neighbour.
    """
    out: set[str] = set()
    for hits in scan_pairs(gas, power).values():
        for h in hits:
            out.add(h["date"])
    return out
