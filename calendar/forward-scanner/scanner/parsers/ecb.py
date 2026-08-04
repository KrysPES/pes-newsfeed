"""ECB Governing Council meeting calendar.

The historic run recorded the ECB as unresolved because the decisions index
and the per year press release index render via JavaScript. The Governing
Council schedule page is a different page and is plain HTML: a definition list
of DD/MM/YYYY against a description. The monetary policy decision is announced
on the second day of a two day meeting, the entry that says it is followed by
a press conference.
"""

import datetime as dt
import re

from .. import html as html_helpers
from ..dates import month_year
from ..rows import make_row

URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

SOURCE = {
    "id": "ecb_gc",
    "name": "ECB Governing Council calendar",
    "url": URL,
    "region": "EU",
    "category": "rates",
}

ENTRY = re.compile(r"<dt>\s*(\d{2})/(\d{2})/(\d{4})\s*</dt>\s*<dd>(.*?)</dd>", re.S | re.I)

CADENCE = "eight monetary policy meetings a year, decision on the second day"
RELEVANCE = (
    "Euro area policy rates set the discount rate behind TTF and continental "
    "power curves and move the euro against dollar priced LNG."
)


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    out = []
    for day, month, year, body in ENTRY.findall(page):
        text = html_helpers.text_of(body).lower()
        if "monetary policy meeting" not in text:
            continue
        if "press conference" not in text:
            continue
        try:
            date = dt.date(int(year), int(month), int(day))
        except ValueError:
            continue
        out.append(
            make_row(
                date=date,
                region="EU",
                category="rates",
                title="ECB monetary policy decision, %s" % month_year(date),
                detail=(
                    "The Governing Council closes its monetary policy meeting "
                    "and announces its rate decision, followed by a press conference."
                ),
                energy_relevance=RELEVANCE,
                fuel_scope="both",
                source_url=URL,
                cadence=CADENCE,
                notes="",
            )
        )
    return out
