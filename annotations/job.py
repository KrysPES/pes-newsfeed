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

A day with no output is the NORMAL outcome: the publish bar
(AUTOPUBLISH_MIN_RANK in attribute.py) is deliberately strict, because a
wrong label is worse than no label. Do not "fix" quiet days by lowering it.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from detect import detect, new_episodes          # noqa: E402
from attribute import attribute                  # noqa: E402

BASE = os.environ.get("OMNIA_BASE", "https://www.pesomnia.com")
KEY = os.environ["ANNOTATIONS_JOB_KEY"]
NEWS = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")


def api_get(path: str):
    req = urllib.request.Request(BASE + path, headers={"x-annotations-key": KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"GET {path} failed: {body.get('error')}")
    return body


def api_post(path: str, payload: dict):
    req = urllib.request.Request(
        BASE + path,
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

    episodes = detect(series["gas"], series["power"])
    fresh = new_episodes(episodes, known)
    print(f"{len(episodes)} episodes in the trailing window, {len(fresh)} new")

    published = []
    for ep in fresh:
        ann = attribute(ep.as_dict(), items)
        if ann:
            published.append(ann)
            print(f"  publish {ann['id']}: {ann['label']}")
        else:
            why = "drift" if ep.is_drift else "nothing cleared the publish bar"
            print(f"  {ep.trigger_day}: no annotation ({why})")

    if published:
        res = api_post("/api/terminal/annotations/job", {"annotations": published})
        print(f"stored: inserted {res.get('inserted')}, skipped {res.get('skipped')}")
    else:
        print("nothing to publish today (normal)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
