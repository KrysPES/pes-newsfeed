"""EIA Weekly Petroleum Status Report schedule."""

from . import eia_common

URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"

SOURCE = {
    "id": "eia_wpsr",
    "name": "EIA weekly petroleum status schedule",
    "url": URL,
    "region": "US",
    "category": "inventory",
}

SPEC = {
    "url": URL,
    "label": "EIA weekly petroleum status",
    "fuel_scope": "gas",
    "detail": (
        "The Energy Information Administration publishes US crude oil, "
        "gasoline and distillate stocks, runs and product supplied."
    ),
    "relevance": (
        "Crude and product stocks move the oil complex, which still prices a "
        "large share of term LNG and so feeds European gas."
    ),
    "cadence": "weekly, 10:30 eastern on Wednesdays, shifted for public holidays",
}


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    return eia_common.build(page, ctx, SPEC)
