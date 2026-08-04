"""Row construction and the row identity used by the lifecycle."""

import re

from . import config
from .dates import iso

WHITESPACE = re.compile(r"\s+")


def uid(title):
    """Stable identity for a row, derived from the title alone.

    The lifecycle in section 7 has to tell a rescheduled event from a new one,
    which means an identity that survives a date change. There is no spare
    column in the schema to hold a key, so every parser puts an invariant
    reference into the title itself: the meeting month for a policy decision,
    the ISO week for a weekly release, the reference period for a statistical
    bulletin. The uid is that title, normalised.
    """
    return WHITESPACE.sub(" ", title).strip().lower()


def make_row(
    date,
    region,
    category,
    title,
    detail,
    energy_relevance,
    fuel_scope,
    source_url,
    cadence,
    recurring="yes",
    time="",
    previous="",
    notes="",
    status="scheduled",
    last_verified="",
    date_source="published",
):
    """Build a schema shaped row. consensus and actual are never populated."""
    return {
        "date": iso(date) if hasattr(date, "year") else date,
        "time": time,
        "region": region,
        "category": category,
        "title": title,
        "detail": detail,
        "energy_relevance": energy_relevance,
        "fuel_scope": fuel_scope,
        "previous": previous,
        "consensus": "",
        "actual": "",
        "recurring": recurring,
        "cadence": cadence,
        "source_url": source_url,
        "notes": notes,
        "status": status,
        "last_verified": last_verified,
        "date_source": date_source,
    }


def blank_row():
    return {column: "" for column in config.FORWARD_COLUMNS}
