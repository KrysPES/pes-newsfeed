"""UK clock changes.

Section 2 lists clock changes under market mechanics. The rule is in statute
and could be generated, but gov.uk publishes the dates in a table, so they are
taken as published rather than derived.

The other two market mechanics items in section 2, the gas year start and the
seasonal roll, have no published schedule page that a plain fetcher can read.
They are recorded as unresolved in the registry rather than generated from
convention.
"""

import datetime as dt
import re

from .. import html as html_helpers
from ..dates import MONTH_NAMES, month_number
from ..rows import make_row

URL = "https://www.gov.uk/when-do-the-clocks-change"

SOURCE = {
    "id": "uk_clocks",
    "name": "UK clock changes",
    "url": URL,
    "region": "UK",
    "category": "other",
}

DAY_MONTH = re.compile(r"(\d{1,2})\s+([A-Za-z]+)")

SPECS = [
    {
        "column": "clocks go forward",
        "label": "UK clocks go forward",
        "detail": (
            "British Summer Time begins and the clocks go forward one hour at "
            "01:00 UTC."
        ),
        "relevance": (
            "The gas day and the power settlement day change length, so the "
            "short day carries 23 settlement periods and shapes within day shape."
        ),
    },
    {
        "column": "clocks go back",
        "label": "UK clocks go back",
        "detail": (
            "British Summer Time ends and the clocks go back one hour at "
            "01:00 UTC."
        ),
        "relevance": (
            "The long day carries 25 settlement periods and the evening peak "
            "moves an hour earlier against demand, which lifts peak power."
        ),
    },
]


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    out = []
    for table in html_helpers.tables(page):
        rows = html_helpers.rows_of(table)
        if not rows:
            continue
        header = [cell.lower() for cell in rows[0]]
        if not header or "year" not in header[0]:
            continue
        for spec in SPECS:
            try:
                column = next(
                    index for index, cell in enumerate(header) if spec["column"] in cell
                )
            except StopIteration:
                continue
            for cells in rows[1:]:
                if len(cells) <= column or not cells[0].strip().isdigit():
                    continue
                year = int(cells[0].strip())
                match = DAY_MONTH.search(cells[column])
                if not match:
                    continue
                month = month_number(match.group(2))
                if not month:
                    continue
                try:
                    date = dt.date(year, month, int(match.group(1)))
                except ValueError:
                    continue
                out.append(
                    make_row(
                        date=date,
                        region="UK",
                        category="other",
                        title="%s, %s %d" % (spec["label"], MONTH_NAMES[month - 1], year),
                        detail=spec["detail"],
                        energy_relevance=spec["relevance"],
                        fuel_scope="both",
                        source_url=URL,
                        cadence="twice a year, the last Sunday in March and in October",
                        notes="",
                    )
                )
    return out
