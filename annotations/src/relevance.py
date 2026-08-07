"""
Per-chart relevance.

An annotation is stored once, keyed on a date. This decides whether it should be
DRAWN on the chart the user is currently looking at.

The rule, set by Alex: show the annotation on any futures chart where there was
market movement that the annotation actually explains. A cold snap that moved
Jan-23 is not an event on the Win-30 chart, and putting a marker there invites
the reader to connect a label to a flat line.

Deterministic, no network, no stored per-contract data needed: the terminal
already has the displayed contract's price series, so relevance is computed at
render time from that.

    from relevance import is_relevant
    if is_relevant(annotation, displayed_series):
        draw_marker(annotation)

Thresholds are deliberately low. The question is not "did this contract have its
own event" but "did this contract move enough that a reader would want the
explanation". Set them too high and the curve-wide events vanish from exactly the
charts people watch most.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

MIN_DAY_PCT = 1.5        # move on the label date alone
MIN_WINDOW_PCT = 3.0     # move across the annotation's window
REQUIRE_SAME_DIRECTION = True


def _at_or_before(dates: list[str], target: str) -> str | None:
    """Last trading date on or before `target`, by binary search."""
    i = bisect_right(dates, target)
    return dates[i - 1] if i else None


def _pct(series: dict[str, float], dates: list[str], start: str, end: str) -> float | None:
    """% change between the last observation on or before `start` and on or
    before `end`. Tolerates the exact dates not being trading days."""
    a = _at_or_before(dates, start)
    b = _at_or_before(dates, end)
    if a is None or b is None or a == b:
        return None
    p0 = series[a]
    if not p0:
        return None
    return (series[b] / p0 - 1.0) * 100.0


def movement(annotation: dict, series: dict[str, float],
             dates: list[str] | None = None) -> dict:
    """What the displayed contract actually did around this annotation.

    `dates` is an optional pre-sorted list of the series' keys. Sorting inside
    every call cost ~58ms per chart render (160 annotations against a
    1700-point series), which is felt on a redraw; `filter_for_chart` sorts
    once and passes it down, bringing that to well under a millisecond.
    Deliberately a parameter rather than a cache: memoising on the series
    object would risk serving a stale index if the prices were refreshed in
    place.
    """
    if not series:
        return {"day_pct": None, "window_pct": None}
    if dates is None:
        dates = sorted(series)
    date = annotation["date"]

    i = bisect_left(dates, date)
    day = _pct(series, dates, dates[i - 1], date) if i else None

    win = annotation.get("window") or {}
    window = _pct(series, dates, win.get("start", date),
                  max(win.get("end", date), date))
    return {"day_pct": day, "window_pct": window}


def is_relevant(annotation: dict, series: dict[str, float],
                dates: list[str] | None = None) -> bool:
    """True if this annotation should be drawn on the chart for `series`.

    `series` is {"YYYY-MM-DD": close} for the contract currently displayed.
    Pass the raw contract series, never a continuous chain.

    For a whole chart, call `filter_for_chart` instead; it sorts once.
    """
    if not series:
        return False

    m = movement(annotation, series, dates)
    day, window = m["day_pct"], m["window_pct"]

    moved = ((day is not None and abs(day) >= MIN_DAY_PCT) or
             (window is not None and abs(window) >= MIN_WINDOW_PCT))
    if not moved:
        return False

    if REQUIRE_SAME_DIRECTION:
        want = annotation.get("direction")
        # judge on whichever leg cleared its threshold; the day move wins when both do
        got = day if (day is not None and abs(day) >= MIN_DAY_PCT) else window
        if got is not None and want in ("Up", "Down"):
            if (got > 0) != (want == "Up"):
                return False

    return True


def filter_for_chart(annotations: list[dict], series: dict[str, float]) -> list[dict]:
    """The annotations to draw on this chart, oldest first.

    Sorts the series once for the whole set. Use this on every chart render
    rather than calling `is_relevant` in a loop.
    """
    if not series:
        return []
    dates = sorted(series)
    return [a for a in annotations
            if not a.get("deleted_at") and is_relevant(a, series, dates)]
