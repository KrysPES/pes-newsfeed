"""Date helpers.

Timezone conversion is done from first principles rather than from a timezone
database, because the scanner is standard library plus requests only and
tzdata is not guaranteed to be present on a Windows scheduler host.

Only two zones are needed: UK civil time and US Eastern. Both rules are stated
in law and neither has changed inside the horizon this scanner covers.
"""

import calendar
import datetime as dt

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def month_number(name):
    """Return the month number for a month name, or None."""
    return MONTHS.get(name.strip().lower().rstrip("."))


def nth_weekday(year, month, weekday, n):
    """The nth weekday of a month. weekday uses Monday=0. n is 1 based."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def last_weekday(year, month, weekday):
    """The last given weekday of a month. Monday=0."""
    last_day = calendar.monthrange(year, month)[1]
    last = dt.date(year, month, last_day)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def uk_offset_hours(date, hour=12):
    """UK civil time offset from UTC on a given date.

    British Summer Time runs from 01:00 UTC on the last Sunday in March to
    01:00 UTC on the last Sunday in October.
    """
    start = last_weekday(date.year, 3, 6)
    end = last_weekday(date.year, 10, 6)
    if date < start or date > end:
        return 0
    if date == start:
        return 1 if hour >= 1 else 0
    if date == end:
        return 0 if hour >= 2 else 1
    return 1


def us_eastern_offset_hours(date, hour=12):
    """US Eastern offset from UTC, as a negative number of hours.

    Daylight time runs from 02:00 local on the second Sunday in March to
    02:00 local on the first Sunday in November.
    """
    start = nth_weekday(date.year, 3, 6, 2)
    end = nth_weekday(date.year, 11, 6, 1)
    if date < start or date > end:
        return -5
    if date == start:
        return -4 if hour >= 2 else -5
    if date == end:
        return -5 if hour >= 2 else -4
    return -4


def to_utc_time(date, hhmm, zone):
    """Convert a local HH:MM on a date to an HH:MM string in UTC.

    Returns an empty string if the input is empty. Returns the time only, so a
    conversion that rolls over midnight is dropped rather than silently
    attached to the wrong date. None of the sources in the registry release
    close enough to midnight for that to bite, and a blank beats a wrong value.
    """
    if not hhmm:
        return ""
    hour, minute = [int(part) for part in hhmm.split(":")]
    if zone == "UTC":
        offset = 0
    elif zone == "UK":
        offset = uk_offset_hours(date, hour)
    elif zone == "US/Eastern":
        offset = us_eastern_offset_hours(date, hour)
    else:
        raise ValueError("unknown zone %r" % zone)
    local = dt.datetime(date.year, date.month, date.day, hour, minute)
    utc = local - dt.timedelta(hours=offset)
    if utc.date() != date:
        return ""
    return "%02d:%02d" % (utc.hour, utc.minute)


def add_months(date, months):
    """Add whole months to a date, clamping the day to the month length."""
    total = date.month - 1 + months
    year = date.year + total // 12
    month = total % 12 + 1
    day = min(date.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def iso(date):
    return date.strftime("%Y-%m-%d")


def parse_iso(text):
    return dt.datetime.strptime(text.strip(), "%Y-%m-%d").date()


def month_year(date):
    """'August 2026', for use in titles as a stable event reference."""
    return "%s %d" % (MONTH_NAMES[date.month - 1], date.year)


def iso_week_label(date):
    """'week 32 2026'. Used as a stable identity for weekly series.

    A weekly release that slips a day for a public holiday stays in the same
    ISO week, so the row keeps its identity and the lifecycle sees a
    reschedule rather than a cancellation plus a new row.
    """
    year, week, _ = date.isocalendar()
    return "week %d %d" % (week, year)


def weekdays_between(start, end, weekday):
    """Every date with the given weekday in [start, end]. Monday=0."""
    out = []
    cursor = start + dt.timedelta(days=(weekday - start.weekday()) % 7)
    while cursor <= end:
        out.append(cursor)
        cursor += dt.timedelta(days=7)
    return out
