"""
One-shot store merge for the researched annotations update (run by hand).

Wraps Bannon's merge_update.py so the whole cycle runs where the job key
already lives (GitHub Actions), instead of anyone handling the secret
locally:

    Omnia API  --what=export-->  merge_update.py  --merged store-->  Omnia API
                                       |                             (mode merge)
                data/events_seed.json -+
                                       +--merged store--> Index API (mode merge,
                                                          only when INDEX_BASE set)

Admin deletions always win: merge_update.py keys on id and leaves anything
with deleted_at alone, and the API's merge mode never resurrects a deletion
on the receiving side either. Running this twice is harmless.

Env:
    ANNOTATIONS_JOB_KEY   shared secret, same value on every base
    OMNIA_BASE            optional, defaults to production Omnia
    INDEX_BASE            optional, e.g. https://app.index-terminal.com;
                          when set the merged store is pushed there too
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("OMNIA_BASE", "https://www.pesomnia.com")
INDEX_BASE = os.environ.get("INDEX_BASE", "").strip().rstrip("/")
KEY = os.environ["ANNOTATIONS_JOB_KEY"]
PATH = "/api/terminal/annotations/job"


def api_get(base: str):
    req = urllib.request.Request(base + PATH + "?what=export",
                                 headers={"x-annotations-key": KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"export from {base} failed: {body.get('error')}")
    return body["annotations"]


def api_merge(base: str, annotations: list):
    req = urllib.request.Request(
        base + PATH,
        data=json.dumps({"annotations": annotations, "mode": "merge"}).encode("utf-8"),
        headers={"x-annotations-key": KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"merge into {base} failed: {body.get('error')}")
    return body


def main() -> int:
    current = api_get(BASE)
    print(f"exported {len(current)} annotations from {BASE}")

    with tempfile.TemporaryDirectory() as td:
        store = os.path.join(td, "current_store.json")
        merged = os.path.join(td, "merged_store.json")
        with open(store, "w", encoding="utf-8") as f:
            json.dump(current, f)
        subprocess.run(
            [sys.executable, os.path.join(HERE, "merge_update.py"), store, "-o", merged],
            check=True,
        )
        with open(merged, encoding="utf-8") as f:
            doc = json.load(f)
    out = doc["annotations"] if isinstance(doc, dict) else doc
    print(f"merged store holds {len(out)} annotations")

    res = api_merge(BASE, out)
    print(f"{BASE}: {res}")
    if INDEX_BASE:
        res = api_merge(INDEX_BASE, out)
        print(f"{INDEX_BASE}: {res}")
    else:
        print("INDEX_BASE not set; Index store untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
