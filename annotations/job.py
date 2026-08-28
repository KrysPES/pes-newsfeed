"""
Daily chart-annotation job (PES_Annotations pack, glue only).

Runs in this repo's GitHub Actions after the news ingest, so news.json is
fresh when attribution reads it. detect.py and attribute.py are Bannon's
reference implementations, copied verbatim — the logic lives there, this file
only moves data:

    Omnia API  --series-->  detect()  --new episodes-->  attribute()
    (raw season contracts)      |                            |
    Omnia API  --known dates----+          news.json --------+
                                                             |
    Omnia API  <--publishable annotations (or nothing) ------+

Env:
    ANNOTATIONS_JOB_KEY   shared secret for the Omnia annotations job API
    OMNIA_BASE            optional, defaults to production

v2 upgrade (Bannon, Aug 2026): the entry point is detect_all() — weekly
episodes PLUS gradient shocks — and the series now include monthly contracts
(the Omnia API's what=series carries both tabs). The old rank-70 publish bar
is GONE, deliberately: in five months live it published nothing at all. The
three gates in attribute.py (in window, direction match, not planned
maintenance) are the whole bar now; mislabels are handled by the admins'
per-annotation delete, not by reinstating a threshold.

Every run ends with a RUN SUMMARY line (episodes detected / candidates gated /
annotations published) because the v1 silence went unnoticed for five months —
nothing recorded the gap between detection and publication.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from detect import detect_all, new_episodes      # noqa: E402
from attribute import attribute                  # noqa: E402

BASE = os.environ.get("OMNIA_BASE", "https://www.pesomnia.com")
# Optional second store: the Index terminal runs the identical job route on
# its own Supabase (same shared key). When set, every run mirrors the full
# Omnia store there in merge mode - Index-side deletions are never
# resurrected by the route, so the mirror cannot undo an admin's prune.
INDEX_BASE = os.environ.get("INDEX_BASE", "").strip().rstrip("/")
KEY = os.environ["ANNOTATIONS_JOB_KEY"]
NEWS = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")


def api_get(path: str):
    req = urllib.request.Request(BASE + path, headers={"x-annotations-key": KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"GET {path} failed: {body.get('error')}")
    return body


def api_post(path: str, payload: dict, base: str = None):
    req = urllib.request.Request(
        (base or BASE) + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-annotations-key": KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"POST {path} failed: {body.get('error')}")
    return body


def main() -> int:
    series = api_get("/api/terminal/annotations/job?what=series")
    known = set(api_get("/api/terminal/annotations/job?what=known")["dates"])
    with open(NEWS, encoding="utf-8") as f:
        items = json.load(f).get("items", [])
    print(f"series: {len(series['gas'])} gas + {len(series['power'])} power contracts; "
          f"{len(known)} known dates; {len(items)} news items")

    episodes = detect_all(series["gas"], series["power"])
    fresh = new_episodes(episodes, known)
    print(f"{len(episodes)} episodes in the trailing window, {len(fresh)} new")

    published = []
    gated = 0
    for ep in fresh:
        ann = attribute(ep.as_dict(), items)
        if ann:
            gated += len(ann.get("candidates") or [])
            published.append(ann)
            print(f"  publish {ann['id']}: {ann['label']}")
        else:
            why = "drift" if ep.is_drift else "no news item passed the three gates"
            print(f"  {ep.trigger_day}: no annotation ({why})")

    if published:
        res = api_post("/api/terminal/annotations/job", {"annotations": published})
        print(f"stored: inserted {res.get('inserted')}, skipped {res.get('skipped')}")
    else:
        print("nothing to publish today")

    # Mirror the master store to the Index terminal, when configured. A dead
    # Index deploy must not fail the Omnia run, so this only warns.
    if INDEX_BASE:
        try:
            store = api_get("/api/terminal/annotations/job?what=export")["annotations"]
            res = api_post("/api/terminal/annotations/job",
                           {"annotations": store, "mode": "merge"}, base=INDEX_BASE)
            print(f"MIRROR {INDEX_BASE}: sent {len(store)}, {res}")
        except Exception as e:  # noqa: BLE001 - a mirror failure is a warning, not a job failure
            print(f"MIRROR {INDEX_BASE} FAILED: {e}")

    # The one line to scan the Actions history for. Detection without
    # publication for weeks on end is exactly the failure v1 hid.
    print(f"RUN SUMMARY: episodes_detected={len(episodes)} new={len(fresh)} "
          f"candidates_gated={gated} annotations_published={len(published)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
