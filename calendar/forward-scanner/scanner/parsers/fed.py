"""Federal Reserve FOMC meeting calendar.

The page groups meetings under an anchor of the form '2026 FOMC Meetings'.
Each meeting is a month label and a day range, for example 'January' and
'27-28', or 'Apr/May' and '28-29' where the meeting straddles two months. The
decision lands on the last day of the range. An asterisk marks a meeting that
carries a Summary of Economic Projections.
"""

import datetime as dt
import re

from ..dates import month_number, month_year
from ..rows import make_row

URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

SOURCE = {
    "id": "fed_fomc",
    "name": "Federal Reserve FOMC calendar",
    "url": URL,
    "region": "US",
    "category": "rates",
}

YEAR_HEADING = re.compile(r">\s*(\d{4})\s+FOMC Meetings\s*<", re.I)
MEETING = re.compile(
    r'fomc-meeting__month[^>]*>\s*(?:<strong>)?(.*?)(?:</strong>)?\s*</div>'
    r'.*?fomc-meeting__date[^>]*>\s*(.*?)\s*</div>',
    re.S | re.I,
)

CADENCE = "eight scheduled meetings a year, statement on the second day"
RELEVANCE = (
    "US policy rates move the dollar and the market's read on global demand, "
    "which feeds through dollar priced crude and LNG into European gas."
)


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    out = []
    headings = list(YEAR_HEADING.finditer(page))
    for index, heading in enumerate(headings):
        year = int(heading.group(1))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        block = page[heading.end():end]
        for month_label, day_label in MEETING.findall(block):
            date = _meeting_date(year, month_label, day_label)
            if not date:
                continue
            projections = "*" in day_label
            notes = (
                "Meeting associated with a Summary of Economic Projections."
                if projections
                else ""
            )
            out.append(
                make_row(
                    date=date,
                    region="US",
                    category="rates",
                    title="FOMC monetary policy decision, %s" % month_year(date),
                    detail=(
                        "The Federal Open Market Committee closes a scheduled "
                        "two day meeting and publishes its policy statement."
                    ),
                    energy_relevance=RELEVANCE,
                    fuel_scope="both",
                    source_url=URL,
                    cadence=CADENCE,
                    notes=notes,
                )
            )
    return out


def _meeting_date(year, month_label, day_label):
    """Last day of the meeting. Handles 'Apr/May' plus '28-29'."""
    months = [part for part in re.split(r"[/\s]+", month_label.strip()) if part]
    numbers = [month_number(part) for part in months]
    numbers = [number for number in numbers if number]
    if not numbers:
        return None
    days = [int(value) for value in re.findall(r"\d{1,2}", day_label)]
    if not days:
        return None
    last_day = days[-1]
    month = numbers[-1]
    # A meeting labelled 'Jan/Feb' that ends in the second month rolls into the
    # next calendar year only when the pair is Dec/Jan, which the Fed does not
    # schedule. No year adjustment is needed.
    try:
        return dt.date(year, month, last_day)
    except ValueError:
        return None
