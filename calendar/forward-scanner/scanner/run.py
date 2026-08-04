"""Entry point. Runs unattended and never asks a question.

  python -m scanner.run --mode weekly
  python -m scanner.run --mode daily

weekly   full refresh across every resolved source, plus a re-probe of the
         unresolved ones so the registry verdicts stay current
daily    limited to sources that carry an event inside the next 14 days, where
         a late change matters most and the fetch cost is small
"""

import argparse
import datetime as dt
import json
import sys

from . import config, csvio, lifecycle, registry as registry_module, validate
from .dates import add_months, iso, parse_iso
from .fetch import Fetcher
from .parsers import BY_ID
from .rows import uid


def build_context(run_date):
    return {
        "run_date": run_date,
        "horizon_end": add_months(run_date, config.HORIZON_MONTHS),
    }


def gather(fetcher, ctx, registry, source_ids):
    """Run each resolved parser. Returns (candidates, statuses)."""
    candidates = []
    statuses = {}
    for entry in registry_module.resolved(registry):
        if source_ids is not None and entry["id"] not in source_ids:
            continue
        module = BY_ID.get(entry["id"])
        if module is None:
            statuses[entry["id"]] = "no parser"
            continue
        try:
            rows, status = module.collect(fetcher, ctx)
        except Exception as error:  # a parser fault must not stop the run
            statuses[entry["id"]] = "parser error: %s" % type(error).__name__
            continue
        statuses[entry["id"]] = status
        for row in rows:
            row["_source_id"] = entry["id"]
        candidates.extend(rows)
    return candidates, statuses


def probe_unresolved(fetcher, registry):
    """Re-check the sources with no route, so the verdicts do not go stale."""
    observed = {}
    for entry in registry_module.unresolved(registry):
        url = entry.get("url")
        if not url:
            continue
        status, _ = fetcher.get(url, entry["id"])
        observed[entry["id"]] = status
    return observed


def screen(candidates, ctx, historic_keys):
    """Drop candidates that cannot legally be written. Returns (kept, dropped)."""
    kept = []
    dropped = []
    seen = set()
    for row in candidates:
        reason = None
        try:
            date = parse_iso(row["date"])
        except (KeyError, ValueError):
            reason = "unparseable date"
            date = None
        if reason is None and date < ctx["run_date"]:
            reason = "dated before the run date"
        elif reason is None and date > ctx["horizon_end"]:
            reason = "beyond the 18 month horizon"
        elif reason is None and len(row.get("title", "")) > config.TITLE_MAX:
            reason = "title over %d characters" % config.TITLE_MAX
        elif reason is None and (row["date"], row["title"].strip().lower()) in historic_keys:
            reason = "collides with a historic calendar row"
        elif reason is None and uid(row.get("title", "")) in seen:
            reason = "duplicate title within this run"
        if reason:
            dropped.append({"title": row.get("title", ""), "date": row.get("date", ""), "reason": reason})
            continue
        seen.add(uid(row["title"]))
        kept.append(row)
    return kept, dropped


def unreachable_sources(registry, statuses, candidates, previous_by_source, source_ids):
    """Sources whose rows must be left alone this run.

    A source is unreachable if it did not answer, if the daily run did not look
    at it, or if it answered 200 and parsed to nothing while it previously had
    rows. That last case is a layout change rather than a mass cancellation,
    and cancelling a whole series on the strength of it would quietly gut the
    calendar. statuses is annotated in place so the reason reaches the summary.
    """
    unreachable = set()
    for entry in registry_module.resolved(registry):
        source_id = entry["id"]
        if source_ids is not None and source_id not in source_ids:
            unreachable.add(source_id)
            continue
        if statuses.get(source_id) != 200:
            unreachable.add(source_id)
            continue
        produced = sum(1 for row in candidates if row.get("_source_id") == source_id)
        if produced == 0 and previous_by_source.get(source_id, 0) > 0:
            unreachable.add(source_id)
            statuses[source_id] = "200 but parsed to no rows"
    return unreachable


def main(argv=None):
    parser = argparse.ArgumentParser(description="PES forward calendar scanner")
    parser.add_argument("--mode", choices=("weekly", "daily"), default="weekly")
    parser.add_argument("--run-date", default=None, help="ISO date, defaults to today UTC")
    args = parser.parse_args(argv)

    run_date = (
        parse_iso(args.run_date)
        if args.run_date
        else dt.datetime.now(dt.timezone.utc).date()
    )
    ctx = build_context(run_date)
    registry = registry_module.load()
    fetcher = Fetcher()

    previous = csvio.read_rows(config.FORWARD_CSV, config.FORWARD_COLUMNS)
    historic_keys = csvio.historic_keys()

    source_ids = None
    if args.mode == "daily":
        source_ids = _sources_in_window(previous, registry, run_date)

    candidates, statuses = gather(fetcher, ctx, registry, source_ids)
    candidates, dropped = screen(candidates, ctx, historic_keys)

    previous_by_source = {}
    for row in previous:
        source = lifecycle.source_id_of(row, registry)
        previous_by_source.setdefault(source, 0)
        previous_by_source[source] += 1

    unreachable = unreachable_sources(
        registry, statuses, candidates, previous_by_source, source_ids
    )

    for row in candidates:
        row.pop("_source_id", None)

    rows, actions = lifecycle.reconcile(
        previous, candidates, run_date, unreachable, registry, historic_keys
    )

    csvio.write_rows(config.FORWARD_CSV, rows)

    if args.mode == "weekly":
        probed = probe_unresolved(fetcher, registry)
    else:
        probed = {}
    _update_registry(registry, statuses, probed, run_date)
    registry_module.save(registry)

    failures = validate.check_schema(csvio.header_of(config.FORWARD_CSV))
    failures += validate.check_rows(rows, run_date, ctx["horizon_end"], historic_keys)

    summary = {
        "mode": args.mode,
        "run_date": iso(run_date),
        "horizon_end": iso(ctx["horizon_end"]),
        "rows": len(rows),
        "actions": actions,
        "source_status": {key: str(value) for key, value in sorted(statuses.items())},
        "unreachable": sorted(unreachable),
        "dropped_candidates": dropped,
        "validator_failures": failures,
        "electricity_rows": sum(1 for row in rows if row.get("fuel_scope") == "electricity"),
        "generated_rows": sum(1 for row in rows if row.get("date_source") == "generated"),
    }
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


def _sources_in_window(previous, registry, run_date):
    """Sources with an event inside the next 14 days."""
    end = run_date + dt.timedelta(days=config.DAILY_WINDOW_DAYS)
    wanted = set()
    for row in previous:
        try:
            date = parse_iso(row.get("date", ""))
        except ValueError:
            continue
        if run_date <= date <= end:
            source = lifecycle.source_id_of(row, registry)
            if source:
                wanted.add(source)
    return wanted


def _update_registry(registry, statuses, probed, run_date):
    today = iso(run_date)
    for entry in registry["sources"]:
        observed = statuses.get(entry["id"], probed.get(entry["id"]))
        if observed is None:
            continue
        entry["last_checked"] = today
        entry["last_status"] = observed if isinstance(observed, int) else str(observed)


if __name__ == "__main__":
    sys.exit(main())
