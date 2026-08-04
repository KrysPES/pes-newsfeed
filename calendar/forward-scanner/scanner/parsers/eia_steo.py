"""EIA Short Term Energy Outlook.

The outlook page states its own next release date. Only one forward date is
published at a time, so this source contributes a single row per run and the
rest of the series appears month by month as the page moves on.
"""

import re

from .. import html as html_helpers
from ..dates import month_year
from ..rows import make_row
from .eia_common import parse_us_date

URL = "https://www.eia.gov/outlooks/steo/"

SOURCE = {
    "id": "eia_steo",
    "name": "EIA Short Term Energy Outlook",
    "url": URL,
    "region": "US",
    "category": "other",
}

NEXT = re.compile(r"Next Release Date:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.I)

RELEVANCE = (
    "The outlook carries the EIA view on US gas balances, LNG exports and "
    "Henry Hub, which anchors expectations for cargoes reaching Europe."
)


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    text = html_helpers.text_of(page)
    match = NEXT.search(text)
    if not match:
        return []
    date = parse_us_date(match.group(1))
    if not date:
        return []
    return [
        make_row(
            date=date,
            region="US",
            category="other",
            title="EIA Short Term Energy Outlook, %s" % month_year(date),
            detail=(
                "The Energy Information Administration publishes its monthly "
                "Short Term Energy Outlook covering the next two calendar years."
            ),
            energy_relevance=RELEVANCE,
            fuel_scope="both",
            source_url=URL,
            cadence="monthly, usually the second Tuesday of the month",
            notes=(
                "Only the next release date is published on the outlook page, "
                "so the series appears one month at a time."
            ),
        )
    ]
