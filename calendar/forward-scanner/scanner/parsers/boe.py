"""Bank of England Monetary Policy Committee dates.

The page carries one table per year under an h2 of the form
'2026 confirmed dates' or '2027 provisional dates'. The first cell of each row
is a weekday and a day and month with no year, so the year comes from the
heading. The second cell says which publications land with the decision.
"""

import datetime as dt
import re

from .. import html as html_helpers
from ..dates import month_number, month_year
from ..rows import make_row

URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"

SOURCE = {
    "id": "boe_mpc",
    "name": "Bank of England MPC dates",
    "url": URL,
    "region": "UK",
    "category": "rates",
}

HEADING = re.compile(r"<h2[^>]*>\s*(\d{4})\s+(confirmed|provisional)\s+dates\s*</h2>", re.I)
DAY_MONTH = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"(\d{1,2})\s+([A-Za-z]+)",
    re.I,
)

CADENCE = "eight scheduled meetings a year, announcement at noon UK time"
RELEVANCE_DECISION = (
    "Bank Rate sets the discount rate behind UK forward power and gas curves "
    "and moves sterling, which reprices imported LNG and interconnector flows."
)
RELEVANCE_MPR = (
    "The report carries the Bank's demand and inflation path, which shapes "
    "expectations for UK industrial gas and power consumption."
)


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    out = []
    headings = list(HEADING.finditer(page))
    for index, heading in enumerate(headings):
        year = int(heading.group(1))
        confirmed = heading.group(2).lower() == "confirmed"
        end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        block = page[heading.end():end]
        table = re.search(r"<table\b.*?</table>", block, re.S | re.I)
        if not table:
            continue
        for cells in html_helpers.rows_of(table.group(0)):
            if len(cells) < 2:
                continue
            match = DAY_MONTH.search(cells[0])
            if not match:
                continue
            month = month_number(match.group(2))
            if not month:
                continue
            date = dt.date(year, month, int(match.group(1)))
            note = "" if confirmed else "Provisional date as published by the Bank."
            out.append(
                make_row(
                    date=date,
                    region="UK",
                    category="rates",
                    title="Bank of England MPC decision, %s" % month_year(date),
                    detail=(
                        "The Monetary Policy Committee announces its Bank Rate "
                        "decision and publishes the meeting minutes on the same day."
                    ),
                    energy_relevance=RELEVANCE_DECISION,
                    fuel_scope="both",
                    source_url=URL,
                    cadence=CADENCE,
                    notes=note,
                )
            )
            if "monetary policy report" in cells[1].lower():
                out.append(
                    make_row(
                        date=date,
                        region="UK",
                        category="rates",
                        title="Bank of England Monetary Policy Report, %s" % month_year(date),
                        detail=(
                            "The Bank publishes its quarterly Monetary Policy Report "
                            "alongside the Bank Rate decision."
                        ),
                        energy_relevance=RELEVANCE_MPR,
                        fuel_scope="both",
                        source_url=URL,
                        cadence="quarterly, published alongside four of the eight rate decisions",
                        notes=note,
                    )
                )
    return out
