"""Section 7 reconciliation.

Each run compares the rows a source published this week against the rows the
previous forward_calendar.csv holds, rather than rebuilding from nothing.

Row identity is the normalised title, see rows.uid. Every parser puts an
invariant reference period in the title so a date change is seen as a
reschedule rather than as a cancellation plus a new row.
"""

from .dates import iso, parse_iso
from .rows import uid


def source_id_of(row, registry):
    """Which registry source a stored row came from, by URL prefix."""
    url = row.get("source_url", "")
    best = ""
    best_length = -1
    for entry in registry.get("sources", []):
        for prefix in entry.get("url_prefixes", []) or [entry.get("url", "")]:
            if prefix and url.startswith(prefix) and len(prefix) > best_length:
                best = entry["id"]
                best_length = len(prefix)
    return best


def reconcile(previous, candidates, run_date, unreachable, registry, historic_keys):
    """Return (rows, actions).

    previous     rows read from the last forward_calendar.csv
    candidates   rows built this run from sources that answered
    unreachable  set of source ids that did not answer, or answered with
                 nothing where they previously had rows
    """
    today = iso(run_date)
    actions = {
        "unchanged": 0,
        "rescheduled": 0,
        "cancelled": 0,
        "occurred": 0,
        "new": 0,
        "stale": 0,
        "collided": 0,
        "reinstated": 0,
    }

    by_uid = {}
    for candidate in candidates:
        by_uid[uid(candidate["title"])] = candidate

    out = []
    seen = set()

    for row in previous:
        key = uid(row.get("title", ""))
        seen.add(key)
        source = source_id_of(row, registry)
        updated = dict(row)

        if source in unreachable:
            # Leave the row untouched, leave last_verified stale.
            actions["stale"] += 1
            out.append(_maybe_occurred(updated, run_date, actions))
            continue

        match = by_uid.get(key)
        if match is None:
            if updated.get("status") != "cancelled":
                updated["status"] = "cancelled"
                updated["notes"] = _append(
                    updated.get("notes", ""),
                    "Dropped off the published schedule, seen missing on %s." % today,
                )
                actions["cancelled"] += 1
            updated["last_verified"] = today
            out.append(updated)
            continue

        if updated.get("status") == "cancelled":
            updated["status"] = "scheduled"
            updated["notes"] = _append(
                updated.get("notes", ""),
                "Back on the published schedule on %s." % today,
            )
            actions["reinstated"] += 1

        if match["date"] != updated.get("date"):
            old = updated.get("date")
            updated["date"] = match["date"]
            updated["time"] = match["time"]
            updated["status"] = "rescheduled"
            updated["notes"] = _append(
                updated.get("notes", ""),
                "Rescheduled on %s, previously dated %s." % (today, old),
            )
            actions["rescheduled"] += 1
        else:
            actions["unchanged"] += 1
            # A published date that was previously generated, or a time that
            # the source has since published, is worth taking.
            updated["date_source"] = match["date_source"]
            if match["time"] and not updated.get("time"):
                updated["time"] = match["time"]

        updated["last_verified"] = today
        out.append(_maybe_occurred(updated, run_date, actions))

    for candidate in candidates:
        key = uid(candidate["title"])
        if key in seen:
            continue
        historic_key = (candidate["date"], candidate["title"].strip().lower())
        if historic_key in historic_keys:
            actions["collided"] += 1
            continue
        fresh = dict(candidate)
        fresh["status"] = "scheduled"
        fresh["last_verified"] = today
        actions["new"] += 1
        out.append(_maybe_occurred(fresh, run_date, actions))

    out.sort(key=lambda row: (row.get("date", ""), row.get("title", "")))
    return out, actions


def _maybe_occurred(row, run_date, actions):
    """An event whose date has passed is marked occurred. actual stays blank.

    A cancelled event never happened, so it is left cancelled.
    """
    if row.get("status") in ("cancelled", "occurred"):
        return row
    try:
        date = parse_iso(row.get("date", ""))
    except ValueError:
        return row
    if date < run_date:
        row["status"] = "occurred"
        row["actual"] = ""
        actions["occurred"] += 1
    return row


def _append(existing, addition):
    existing = (existing or "").strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return existing + " " + addition
