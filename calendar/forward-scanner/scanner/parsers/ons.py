"""ONS release calendar.

The upcoming filter on the release calendar carries structured attributes for
every forthcoming release: the date as YYYYMMDD, the release time, the title
and the release page link. The link is harvested, never constructed, and is
used as the source_url so a rescheduled release keeps a stable source.

The release time is published here, which is what the historic run could not
find on the bulletin pages. Times are UK civil time and are converted to UTC.
"""

import datetime as dt
import re

from ..dates import to_utc_time
from ..rows import make_row

BASE = "https://www.ons.gov.uk"
CALENDAR = BASE + "/releasecalendar?release-type=type-upcoming&page=%d"
# The calendar serves ten items a page and does not honour a size parameter,
# so the cap is generous rather than tight.
MAX_PAGES = 20

SOURCE = {
    "id": "ons_calendar",
    "name": "ONS release calendar",
    "url": BASE + "/releasecalendar?release-type=type-upcoming",
    "region": "UK",
    "category": "inflation",
}

ITEM = re.compile(
    r'<li class="ons-list__item.*?data-gtm-release-title\s*=\s*"(?P<title>[^"]*)"'
    r'.*?data-gtm-release-url="(?P<url>[^"]*)"'
    r'.*?data-gtm-release-date="(?P<date>\d{8})"'
    r'.*?data-gtm-release-time="(?P<time>[^"]*)"'
    r'(?P<tail>.*?)</li>',
    re.S,
)

# Section 2 names ONS CPI, labour market and monthly GDP. Each entry gives the
# match against the released title, the category, and the wording used in the
# row. Nothing outside this map is emitted.
SERIES = [
    {
        "match": "consumer price inflation",
        "category": "inflation",
        "label": "ONS consumer price inflation",
        "detail": (
            "The Office for National Statistics publishes the consumer price "
            "inflation bulletin covering CPIH, CPI and RPI."
        ),
        "relevance": (
            "The electricity, gas and other fuels component is the published "
            "read on how wholesale energy costs reach UK households, and it "
            "shapes the Bank Rate path."
        ),
        "cadence": "monthly, roughly the third week of the following month",
    },
    {
        "match": "uk labour market",
        "category": "employment",
        "label": "ONS labour market statistics",
        "detail": (
            "The Office for National Statistics publishes the labour market "
            "overview covering employment, unemployment and earnings growth."
        ),
        "relevance": (
            "Earnings growth is the main domestic input to the Bank Rate path "
            "and so to the discount rate behind UK forward power and gas."
        ),
        "cadence": "monthly, usually the Tuesday before the CPI release",
        "note": (
            "The ONS renamed this release from the labour market overview to "
            "UK Labour Market. The match follows the current name."
        ),
    },
    {
        "match": "gdp monthly estimate",
        "category": "growth",
        "label": "ONS monthly GDP estimate",
        "detail": (
            "The Office for National Statistics publishes its monthly estimate "
            "of gross domestic product, with output by industry."
        ),
        "relevance": (
            "Industrial output within the release is the closest published "
            "proxy for UK non domestic gas and power demand."
        ),
        "cadence": "monthly, about six weeks after the reference month",
    },
    {
        "match": "gdp first quarterly estimate",
        "category": "growth",
        "label": "ONS first quarterly GDP estimate",
        "detail": (
            "The Office for National Statistics publishes its first quarterly "
            "estimate of gross domestic product."
        ),
        "relevance": (
            "The quarterly path of output frames the demand side of UK gas and "
            "power balances for the year ahead."
        ),
        "cadence": "quarterly, about six weeks after the quarter end",
    },
]


def collect(fetcher, ctx):
    rows = []
    last_status = None
    for page_number in range(1, MAX_PAGES + 1):
        url = CALENDAR % page_number
        status, page = fetcher.get(url, SOURCE["id"])
        last_status = status
        if status != 200 or not page:
            break
        found = parse(page, ctx, url)
        rows.extend(found)
        if 'data-gtm-release-date' not in page:
            break
        if _beyond_horizon(page, ctx):
            break
    return rows, last_status


def _beyond_horizon(page, ctx):
    """Stop paging once every release on a page sits past the horizon."""
    dates = re.findall(r'data-gtm-release-date="(\d{8})"', page)
    if not dates:
        return True
    parsed = [dt.datetime.strptime(value, "%Y%m%d").date() for value in dates]
    return min(parsed) > ctx["horizon_end"]


def parse(page, ctx, page_url=None):
    out = []
    for match in ITEM.finditer(page):
        title = match.group("title").strip()
        series = _series_for(title)
        if not series:
            continue
        try:
            date = dt.datetime.strptime(match.group("date"), "%Y%m%d").date()
        except ValueError:
            continue
        reference = _reference(title)
        if not reference:
            continue
        tail = match.group("tail")
        provisional = "Provisional" in tail
        release_url = match.group("url").strip()
        if release_url.startswith("/"):
            release_url = BASE + release_url
        elif not release_url.startswith("http"):
            continue
        time_utc = to_utc_time(date, match.group("time").strip(), "UK")
        notes = []
        if provisional:
            notes.append("Release date shown as provisional by the ONS.")
        notes.append("Release time published as UK civil time and converted to UTC.")
        if not time_utc:
            notes = notes[:-1]
        if series.get("note"):
            notes.append(series["note"])
        out.append(
            make_row(
                date=date,
                region="UK",
                category=series["category"],
                title="%s, %s" % (series["label"], reference),
                detail=series["detail"] + " This release covers %s." % reference,
                energy_relevance=series["relevance"],
                fuel_scope="both",
                source_url=release_url,
                cadence=series["cadence"],
                time=time_utc,
                notes=" ".join(notes),
            )
        )
    return out


# The ONS lists a companion time series release alongside several bulletins.
# It lands at the same moment and carries no separate event, so it is dropped.
EXCLUDE = ("time series", "timeseries")


def _series_for(title):
    lowered = title.lower()
    if any(term in lowered for term in EXCLUDE):
        return None
    for series in SERIES:
        if series["match"] in lowered:
            return series
    return None


def _reference(title):
    """The reference period after the final colon, for example 'July 2026'.

    The reference period is what makes a row identity survive a reschedule, so
    a release without one is skipped rather than guessed at.
    """
    if ":" not in title:
        return ""
    reference = title.rsplit(":", 1)[1].strip()
    if not reference or len(reference) > 28:
        return ""
    return reference
