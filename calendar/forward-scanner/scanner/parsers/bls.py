"""US Bureau of Labor Statistics release schedule, via the published iCalendar.

Section 8 expected US macro to be absent because the BLS schedule pages return
403 and decision 3 rules out the keyed API. The brief asks for BLS API v1 to be
tested. It was: v1 is open without a key but serves series observations, not
release dates, so it does not recover the calendar.

What does work is the iCalendar file the BLS publishes alongside the schedule
pages. It is served as text/calendar from the same host that 403s the HTML,
and it carries every release with a US Eastern timestamp. The block is applied
inconsistently, so this source returns 403 on some runs. That is handled by the
lifecycle: the rows are left untouched and last_verified goes stale.
"""

import datetime as dt
import re

from ..dates import month_year, to_utc_time
from ..rows import make_row

URL = "https://www.bls.gov/schedule/news_release/bls.ics"

SOURCE = {
    "id": "bls_ics",
    "name": "BLS economic news release schedule",
    "url": URL,
    "region": "US",
    "category": "inflation",
}

EVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)
DTSTART = re.compile(r"DTSTART;TZID=US-Eastern:(\d{8})T(\d{2})(\d{2})(\d{2})")
SUMMARY = re.compile(r"SUMMARY:(.*)")

SERIES = {
    "consumer price index": {
        "category": "inflation",
        "label": "US consumer price index release",
        "detail": (
            "The Bureau of Labor Statistics publishes the consumer price index "
            "for the previous month."
        ),
        "relevance": (
            "US inflation drives Federal Reserve expectations and the dollar, "
            "which reprices dollar denominated crude and LNG cargoes."
        ),
        "cadence": "monthly, usually mid month for the previous month",
    },
    "employment situation": {
        "category": "employment",
        "label": "US employment situation release",
        "detail": (
            "The Bureau of Labor Statistics publishes non farm payrolls and the "
            "unemployment rate for the previous month."
        ),
        "relevance": (
            "Payrolls is the single largest scheduled mover of the dollar and "
            "of the rate path that discounts energy forward curves."
        ),
        "cadence": "monthly, usually the first Friday of the month",
    },
}


def collect(fetcher, ctx):
    status, payload = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not payload:
        return [], status
    return parse(payload, ctx), status


def parse(payload, ctx):
    out = []
    for block in EVENT.findall(payload):
        summary_match = SUMMARY.search(block)
        start_match = DTSTART.search(block)
        if not summary_match or not start_match:
            continue
        summary = summary_match.group(1).strip()
        series = SERIES.get(summary.lower())
        if not series:
            continue
        try:
            date = dt.datetime.strptime(start_match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        local = "%s:%s" % (start_match.group(2), start_match.group(3))
        time_utc = to_utc_time(date, local, "US/Eastern")
        # The calendar gives the release date, not the reference month, so the
        # release month is what makes the title unique and stable.
        out.append(
            make_row(
                date=date,
                region="US",
                category=series["category"],
                title="%s, %s" % (series["label"], month_year(date)),
                detail=series["detail"],
                energy_relevance=series["relevance"],
                fuel_scope="both",
                source_url=URL,
                cadence=series["cadence"],
                time=time_utc,
                notes=(
                    "Date and time taken from the BLS published iCalendar and "
                    "converted from US Eastern to UTC."
                ),
            )
        )
    return out
