"""Shared parsing for the two EIA weekly release schedule pages.

Both pages state the standard release day and time in prose and then publish a
table of holiday exceptions. That gives two kinds of row:

  published  an exception the page states outright
  generated  an ordinary week, produced from the cadence sentence on the page

Decision 2 allows generation only as a fallback and requires it to be visible.
Every generated row carries date_source=generated and says so in notes. The
alternative was to publish only the dozen holiday exceptions a year and leave
the weekly series that the desk actually watches out of the calendar.
"""

import datetime as dt
import re

from .. import html as html_helpers
from ..dates import iso_week_label, month_number, to_utc_time
from ..rows import make_row

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

STANDARD = re.compile(
    r"standard release time and day of the week will be at\s*"
    r"(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.)\s*eastern time on\s*([A-Za-z]+day)s",
    re.I,
)

US_DATE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})")
CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.)", re.I)


def standard_schedule(page):
    """(weekday index, 'HH:MM' eastern) from the cadence sentence, or None."""
    match = STANDARD.search(html_helpers.text_of(page))
    if not match:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).lower().startswith("p"):
        hour += 12
    weekday = WEEKDAYS.get(match.group(4).lower())
    if weekday is None:
        return None
    return weekday, "%02d:%s" % (hour, match.group(2))


def parse_us_date(text):
    match = US_DATE.search(text or "")
    if not match:
        return None
    month = month_number(match.group(1))
    if not month:
        return None
    try:
        return dt.date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None


def parse_clock(text):
    match = CLOCK.search(text or "")
    if not match:
        return ""
    hour = int(match.group(1)) % 12
    if match.group(3).lower().startswith("p"):
        hour += 12
    return "%02d:%s" % (hour, match.group(2))


def exceptions(page):
    """Holiday exception rows as dicts of date, time and holiday.

    Both pages put the alternate release date in the column headed 'Alternate
    release date'. The petroleum page carries an extra leading column for the
    data week, which is kept as context rather than used as the date.
    """
    out = []
    for table in html_helpers.tables(page):
        rows = html_helpers.rows_of(table)
        if not rows:
            continue
        header = [cell.lower() for cell in rows[0]]
        try:
            date_column = next(
                index
                for index, cell in enumerate(header)
                if "alternate release date" in cell
            )
        except StopIteration:
            continue
        time_column = next(
            (index for index, cell in enumerate(header) if "release time" in cell),
            None,
        )
        holiday_column = next(
            (index for index, cell in enumerate(header) if "holiday" in cell), None
        )
        week_column = next(
            (index for index, cell in enumerate(header) if "week ending" in cell), None
        )
        for cells in rows[1:]:
            if len(cells) <= date_column:
                continue
            date = parse_us_date(cells[date_column])
            if not date:
                continue
            out.append(
                {
                    "date": date,
                    "time": parse_clock(cells[time_column])
                    if time_column is not None and len(cells) > time_column
                    else "",
                    "holiday": cells[holiday_column].strip()
                    if holiday_column is not None and len(cells) > holiday_column
                    else "",
                    "week": cells[week_column].strip()
                    if week_column is not None and len(cells) > week_column
                    else "",
                }
            )
    return out


def build(page, ctx, spec):
    """Rows for one EIA weekly series."""
    schedule = standard_schedule(page)
    found = exceptions(page)
    rows = []
    seen_weeks = set()

    for entry in found:
        date = entry["date"]
        if date < ctx["run_date"] or date > ctx["horizon_end"]:
            continue
        seen_weeks.add(date.isocalendar()[:2])
        notes = ["Holiday exception published on the release schedule page."]
        if entry["holiday"]:
            notes.append("Holiday: %s." % entry["holiday"])
        if entry["week"]:
            notes.append("Covers data for the week ending %s." % entry["week"])
        rows.append(
            make_row(
                date=date,
                region="US",
                category="inventory",
                title="%s, %s" % (spec["label"], iso_week_label(date)),
                detail=spec["detail"],
                energy_relevance=spec["relevance"],
                fuel_scope=spec["fuel_scope"],
                source_url=spec["url"],
                cadence=spec["cadence"],
                time=to_utc_time(date, entry["time"], "US/Eastern"),
                notes=" ".join(notes),
                date_source="published",
            )
        )

    if schedule:
        weekday, eastern = schedule
        cursor = ctx["run_date"]
        cursor += dt.timedelta(days=(weekday - cursor.weekday()) % 7)
        while cursor <= ctx["horizon_end"]:
            if cursor.isocalendar()[:2] not in seen_weeks:
                rows.append(
                    make_row(
                        date=cursor,
                        region="US",
                        category="inventory",
                        title="%s, %s" % (spec["label"], iso_week_label(cursor)),
                        detail=spec["detail"],
                        energy_relevance=spec["relevance"],
                        fuel_scope=spec["fuel_scope"],
                        source_url=spec["url"],
                        cadence=spec["cadence"],
                        time=to_utc_time(cursor, eastern, "US/Eastern"),
                        notes=(
                            "Date generated from the standard weekly cadence "
                            "stated on the release schedule page. The EIA "
                            "publishes only its holiday exceptions as dates."
                        ),
                        date_source="generated",
                    )
                )
            cursor += dt.timedelta(days=7)

    return rows
