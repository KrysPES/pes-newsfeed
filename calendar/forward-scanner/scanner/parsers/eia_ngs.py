"""EIA Weekly Natural Gas Storage Report schedule."""

from . import eia_common

URL = "https://ir.eia.gov/ngs/schedule.html"

SOURCE = {
    "id": "eia_ngs",
    "name": "EIA weekly natural gas storage schedule",
    "url": URL,
    "region": "US",
    "category": "inventory",
}

SPEC = {
    "url": URL,
    "label": "EIA weekly natural gas storage",
    "fuel_scope": "gas",
    "detail": (
        "The Energy Information Administration publishes working gas in "
        "underground storage for the lower 48 states."
    ),
    "relevance": (
        "The weekly storage change is the reference print for Henry Hub and "
        "sets the tone for TTF and NBP through the LNG arbitrage."
    ),
    "cadence": "weekly, 10:30 eastern on Thursdays, shifted for public holidays",
}


def collect(fetcher, ctx):
    status, page = fetcher.get(URL, SOURCE["id"])
    if status != 200 or not page:
        return [], status
    return parse(page, ctx), status


def parse(page, ctx):
    return eia_common.build(page, ctx, SPEC)
