#!/usr/bin/env python3
"""
Merge this update into an existing annotations store.

    python merge_update.py current_store.json          # writes merged_store.json
    python merge_update.py current_store.json --dry-run

`current_store.json` is an export of whatever the terminal holds now: either the
full seed document, or a bare JSON array of annotation objects.

THE RULE THIS ENFORCES: an admin deletion always wins. If Alex, Krys or Alex
Dovey removed an annotation, re-running an update must not resurrect it. Without
this, the first update silently undoes every prune the three of them have made.

Merge semantics, keyed on `id` (evt-YYYY-MM-DD):

  - date not in the store        -> added
  - in the store, deleted_at set -> LEFT DELETED, update discarded
  - in the store, not deleted    -> refreshed from the update, but any local
                                    edit to `label` is kept (see --force-labels)

No network, no cost. Run it, read the summary, then load merged_store.json.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
UPDATE = HERE / "data" / "events_seed.json"


def load_annotations(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        return doc, None
    return doc.get("annotations", []), doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store", help="export of the current annotations store")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--force-labels", action="store_true",
                    help="overwrite locally edited labels with the update's wording")
    ap.add_argument("-o", "--out", default="merged_store.json")
    args = ap.parse_args()

    store_path = Path(args.store)
    if not store_path.exists():
        sys.exit(f"{store_path} not found.")
    if not UPDATE.exists():
        sys.exit("data/events_seed.json not found; run this from the package folder.")

    current, _ = load_annotations(store_path)
    update_doc = json.loads(UPDATE.read_text(encoding="utf-8"))
    incoming = update_doc["annotations"]

    by_id = {a.get("id"): a for a in current}
    added = refreshed = kept_deleted = kept_label = 0

    for inc in incoming:
        cur = by_id.get(inc["id"])
        if cur is None:
            by_id[inc["id"]] = dict(inc)
            added += 1
            continue

        if cur.get("deleted_at"):
            kept_deleted += 1                      # an admin removed it: it stays removed
            continue

        merged = dict(inc)
        if not args.force_labels and cur.get("label") and cur["label"] != inc["label"]:
            merged["label"] = cur["label"]         # a human edited this wording; keep it
            kept_label += 1
        for f in ("deleted_by", "deleted_at"):
            merged[f] = cur.get(f)
        by_id[inc["id"]] = merged
        refreshed += 1

    merged_list = sorted(by_id.values(), key=lambda a: a.get("date", ""))
    local_only = len(current) - (refreshed + kept_deleted)

    print(f"store in    {len(current)}")
    print(f"update in   {len(incoming)}")
    print("-" * 34)
    print(f"added       {added}")
    print(f"refreshed   {refreshed}")
    print(f"kept deleted{kept_deleted:>7}   (admin removals preserved)")
    print(f"kept label  {kept_label:>7}   (local edits preserved)")
    if local_only > 0:
        print(f"store-only  {local_only:>7}   (not in this update, left untouched)")
    print("-" * 34)
    print(f"store out   {len(merged_list)}")

    dates = [a.get("date") for a in merged_list]
    if len(dates) != len(set(dates)):
        sys.exit("ERROR: duplicate dates after merge. Do not load this; tell Alex.")

    if args.dry_run:
        print("\ndry run, nothing written")
        return

    out = dict(update_doc)
    out["annotations"] = merged_list
    out["counts"] = dict(update_doc.get("counts", {}), published=len(merged_list))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
