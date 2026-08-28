"""Apply the relevance filter to a news store that already exists.

Forward-only filtering leaves whatever already got through sitting in the feed
until it ages out. This walks a stored file, drops anything the filter rejects,
and reports what went and why so the decision can be checked before it is
committed.

    python3 retrofit.py news.json                 # report only, writes nothing
    python3 retrofit.py news.json --write         # rewrite in place
    python3 retrofit.py news.json -o cleaned.json

Works on either shape: a bare list of items, or an object with an "items" key
like the pipeline's data/news.json. Each item needs title, and optionally
summary/description and url/link.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from energy_relevance import RelevanceFilter  # noqa: E402


def get(item, *names):
    for n in names:
        v = item.get(n)
        if v:
            return v
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("-o", "--out")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--themes", default=str(HERE / "themes.reference.json"))
    a = ap.parse_args()

    raw = json.loads(Path(a.store).read_text(encoding="utf8"))
    wrapper = isinstance(raw, dict)
    items = raw.get("items", []) if wrapper else raw

    themes = a.themes if Path(a.themes).exists() else None
    f = RelevanceFilter(themes)
    print(f"{len(items)} items, {f.anchor_count} anchor terms")

    kept, dropped = [], []
    for item in items:
        ok, why = f.check(get(item, "title", "headline"),
                          get(item, "summary", "description", "snippet"),
                          get(item, "url", "link"))
        (kept if ok else dropped).append((item, why))

    for item, why in dropped:
        print(f"  DROP  [{why}] {get(item, 'title', 'headline')[:70]}")
    print(f"\nkeeping {len(kept)}, dropping {len(dropped)}")

    if not a.write and not a.out:
        print("report only. Pass --write or -o to change anything.")
        return

    out_items = [i for i, _ in kept]
    if wrapper:
        raw["items"] = out_items
        if "item_count" in raw:
            raw["item_count"] = len(out_items)
        payload = raw
    else:
        payload = out_items

    dest = Path(a.out) if a.out else Path(a.store)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf8")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
