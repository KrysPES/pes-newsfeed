"""CFTC Commitments of Traders release schedule.

The page publishes a full year of release dates as a month row with one cell
per release day, under a heading of the form '2026 Release Schedule'. The
release time, 3:30 p.m. eastern, is stated in the prose above the table. An
asterisk on a day marks a release the page flags as holiday affected.

Row identity here is the release date rather than the ISO week that the other
weekly series use. A holiday can put two COT releases inside one ISO week, for
example the Monday catch up on 16 November 2026 and the ordinary Friday
release on the 20th, and a week based identity would silently drop one of
them. The cost is that a moved release reads as a cancellation plus a new row
rather than as a reschedule. The CFTC publishes a full year at a time and
flags its own holiday shifts in advance, so that is the cheaper trade.
"""

import datetime as dt
import re

from .. import html as html_helpers
from ..dates import MONTH_NAMES, month_number, to_utc_time
from ..rows import make_row

URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm"

SOURCE = {
    "id": "cftc_cot",
    "name": "CFTC Commitments of Traders schedule",
    "url": URL,
    "region": "US",
    "category": "other",
}

HEADING = re.compile(r"(\d{4})\s+Release Schedule", re.I)
RELEASE_TIME = re.compile(r"released at\s*(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.)\s*Eastern", re.I)

RELEVANCE = (
    "Managed money positioning in gas and crude futures is the cleanest read "
    "on how much of a price move is speculative rather than physical."
)
CADENCE = "weekly, 15:30 eastern on Fridays, covering the previous Tuesday"


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def _release_time(page):
    match = RELEASE_TIME.search(html_helpers.text_of(page))
    if not match:
        return ""
    hour = int(match.group(1)) % 12
    if match.group(3).lower().startswith("p"):
        hour += 12
    return "%02d:%s" % (hour, match.group(2))


def parse(page, ctx):
    eastern = _release_time(page)
    out = []
    headings = list(HEADING.finditer(page))
    for index, heading in enumerate(headings):
        year = int(heading.group(1))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        block = page[heading.end():end]
        table = re.search(r"<table\b.*?</table>", block, re.S | re.I)
        if not table:
            continue
        for cells in html_helpers.rows_of(table.group(0)):
            if not cells:
                continue
            month = month_number(cells[0])
            if not month:
                continue
            for cell in cells[1:]:
                digits = re.match(r"\s*(\d{1,2})\s*(\*?)", cell)
                if not digits:
                    continue
                try:
                    date = dt.date(year, month, int(digits.group(1)))
                except ValueError:
                    continue
                notes = (
                    "Marked on the schedule as affected by a federal holiday."
                    if digits.group(2)
                    else ""
                )
                out.append(
                    make_row(
                        date=date,
                        region="US",
                        category="other",
                        title="CFTC Commitments of Traders, %d %s %d"
                        % (date.day, MONTH_NAMES[date.month - 1], date.year),
                        detail=(
                            "The Commodity Futures Trading Commission publishes "
                            "the Commitments of Traders reports covering "
                            "positions as of the previous Tuesday."
                        ),
                        energy_relevance=RELEVANCE,
                        fuel_scope="both",
                        source_url=URL,
                        cadence=CADENCE,
                        time=to_utc_time(date, eastern, "US/Eastern"),
                        notes=notes,
                    )
                )
    return out
