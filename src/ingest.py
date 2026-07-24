#!/usr/bin/env python3
"""
PES news feed ingestion.

    python src/ingest.py            run the pipeline, write data/news.json
    python src/ingest.py --check    test every source, print a health report
    python src/ingest.py --demo     build from fixtures, no network needed

Design notes for whoever picks this up:
  - Nothing here costs money. No paid APIs, no model calls.
  - A source failing is normal and must never break the run. Each one is
    isolated; failures are recorded in the output so the widget can show
    a degraded state rather than silently going stale.
  - The output file is the entire API. Serve it as a static asset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from adapters import ADAPTERS, fetch_gdelt, fetch_google_news   # noqa: E402
from dedupe import cluster                                       # noqa: E402
from scoring import Scorer                                       # noqa: E402
from supersede import apply_supersession                          # noqa: E402


ENV_TEMPLATE = """# Paste your keys after the = sign. No quotes, no spaces.
# This file is never uploaded to GitHub.

AGSI_KEY=
ENTSOE_TOKEN=
"""


def ensure_env_file() -> bool:
    """
    Create the .env file if it is missing, and say exactly where it is.

    Shipping a .env.example for the user to copy turned out to be unreliable:
    files beginning with a dot are hidden by macOS Finder and are silently
    skipped by several Windows extraction tools, so it can arrive invisible or
    not at all. Creating it here removes the dependency entirely.

    Returns True if it created one, meaning the caller should stop and let the
    user fill it in.
    """
    env_path = ROOT / ".env"
    if env_path.exists():
        return False

    env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    print()
    print("  No .env file found, so one has been created for you:")
    print()
    print(f"     {env_path}")
    print()
    print("  Open that file in Notepad, paste your AGSI key after AGSI_KEY=")
    print("  save it, then run this command again.")
    print()
    return True


def load_env_file() -> int:
    """
    Read keys from a plain .env text file next to this project.

    Environment variables are the usual way to do this, but the syntax differs
    between Windows PowerShell, Windows cmd and macOS, and getting it wrong
    fails in a confusing way. A text file works identically everywhere.

    Real environment variables still win if both are set, so this changes
    nothing for the GitHub Actions run, which uses Actions Secrets.
    """
    env_path = ROOT / ".env"
    if not env_path.exists():
        return 0

    loaded = 0
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value
            loaded += 1
    return loaded


CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
FIXTURE_DIR = ROOT / "fixtures"


# --------------------------------------------------------------------------

load_env_file()


def load_config() -> tuple[dict, dict]:
    themes = json.loads((CONFIG_DIR / "themes.json").read_text())
    sources = json.loads((CONFIG_DIR / "sources.json").read_text())
    return themes, sources


def theme_queries(themes: dict, limit: int = 8) -> list[str]:
    """
    Build search queries for the tier-3 sources straight out of the theme
    dictionary. This is what makes the system self-updating: add a theme,
    the broad search picks it up automatically. No query list to maintain.
    """
    queries = []
    for name, spec in themes["themes"].items():
        if not spec.get("active", True):
            continue
        phrases = spec.get("phrases", [])[:3]
        if phrases:
            queries.append(" OR ".join(f'"{p}"' for p in phrases))
    return queries[:limit]


# --------------------------------------------------------------------------

def run(demo: bool = False) -> dict:
    themes, sources_cfg = load_config()
    scorer = Scorer(themes)
    queries = theme_queries(themes)

    raw_items: list[dict] = []
    source_status: list[dict] = []

    if demo:
        fixtures = json.loads((FIXTURE_DIR / "sample_items.json").read_text())
        for item in fixtures:
            item["published_at"] = _parse(item.get("published_at"))
            raw_items.append(item)
        source_status.append({"id": "fixtures", "ok": True, "count": len(raw_items),
                              "error": None, "ms": 0})
    else:
        for source in sources_cfg["sources"]:
            if not source.get("active"):
                continue

            started = time.time()
            try:
                fetched = _dispatch(source, queries)
                for item in fetched:
                    item["source"] = source["id"]
                    item["source_name"] = source["name"]
                    item["authority"] = source.get("authority", 10)
                    item["tier"] = source.get("tier", 2)
                    raw_items.append(item)

                source_status.append({
                    "id": source["id"], "ok": True, "count": len(fetched),
                    "error": None, "ms": int((time.time() - started) * 1000),
                })
            except Exception as exc:                      # noqa: BLE001
                source_status.append({
                    "id": source["id"], "ok": False, "count": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                    "ms": int((time.time() - started) * 1000),
                })

    # ---- score -----------------------------------------------------------
    now = datetime.now(timezone.utc)
    scored: list[dict] = []

    for item in raw_items:
        if not item.get("title"):
            continue
        result = scorer.score(item, now=now)
        if result.excluded or result.score < 30:
            continue

        item["score"] = result.score
        item["tags"] = result.tags
        item["alert"] = result.alert
        item["nature"] = result.nature
        item["why"] = result.breakdown
        item["matched"] = result.matched
        item["published_at"] = _iso(item.get("published_at"))
        scored.append(item)

    # ---- dedupe ----------------------------------------------------------
    deduped = cluster(scored)
    deduped.sort(key=lambda i: (i.get("score", 0), i.get("published_at") or ""), reverse=True)

    # ---- supersession ----------------------------------------------------
    # must run BEFORE the alert cap, so a retired story cannot occupy one of
    # the four critical slots that a live story needs
    sup = sources_cfg.get("supersession") or themes.get("supersession", {})
    deduped = apply_supersession(
        deduped,
        window_days=sup.get("window_days", 5.0),
        demote=sup.get("demote", 0.30),
        hide=sup.get("hide_superseded", True),
    )
    deduped.sort(key=lambda i: (i.get("score", 0), i.get("published_at") or ""), reverse=True)

    # ---- alert rate limit ------------------------------------------------
    deduped = cap_alerts(deduped, now)

    # ---- retention -------------------------------------------------------
    retention = sources_cfg.get("retention", {})
    cutoff = (now - timedelta(days=retention.get("days", 14))).isoformat()
    kept = [i for i in deduped if not i.get("published_at") or i["published_at"] >= cutoff]
    kept = kept[:retention.get("max_items", 1200)]

    healthy = sum(1 for s in source_status if s["ok"])
    payload = {
        "generated_at": now.isoformat(),
        "item_count": len(kept),
        "alert_counts": {
            level: sum(1 for i in kept if i["alert"] == level and not i.get("hidden"))
            for level in ("critical", "high", "normal")
        },
        "superseded_count": sum(1 for i in kept if i.get("superseded")),
        "sources": {
            "healthy": healthy,
            "total": len(source_status),
            "degraded": healthy < len(source_status),
            "detail": source_status,
        },
        "items": kept,
    }
    return payload


def cap_alerts(items: list[dict], now: datetime,
               window_hours: int = 6, max_critical: int = 4) -> list[dict]:
    """
    An alert that fires constantly is an alert nobody looks at.

    Keep only the strongest N criticals in any rolling window and demote the
    rest to high. They stay in the feed and stay visible, they just stop
    flashing the drawer. If four genuine criticals land in six hours the desk
    has bigger problems than the fifth notification.
    """
    cutoff = now - timedelta(hours=window_hours)

    recent_criticals = []
    for item in items:
        if item.get("alert") != "critical":
            continue
        published = item.get("published_at")
        if not published:
            recent_criticals.append(item)
            continue
        try:
            when = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except ValueError:
            recent_criticals.append(item)
            continue
        if when >= cutoff:
            recent_criticals.append(item)

    recent_criticals.sort(key=lambda i: i.get("score", 0), reverse=True)

    for item in recent_criticals[max_critical:]:
        item["alert"] = "high"
        item["alert_capped"] = True

    return items


def _dispatch(source: dict, queries: list[str]) -> list[dict]:
    stype = source["type"]
    if stype == "gdelt":
        return fetch_gdelt(source, queries)
    if stype == "google_news":
        return fetch_google_news(source, queries)

    adapter = ADAPTERS.get(stype)
    if adapter is None:
        raise RuntimeError(f"no adapter for type '{stype}'")
    return adapter(source)


# --------------------------------------------------------------------------

def health_check() -> int:
    """Test every source, active or not, and report. Run this first."""
    themes, sources_cfg = load_config()
    queries = theme_queries(themes)

    width = 26
    print()
    print("PES news feed source check")
    print("=" * 78)
    print(f"{'source':<{width}} {'tier':<5} {'conf':<11} {'status':<9} items  detail")
    print("-" * 78)

    failures = 0
    for source in sources_cfg["sources"]:
        conf = source.get("confidence", "?")
        tier = source.get("tier", "?")
        name = source["id"][:width - 1]

        if not source.get("url"):
            print(f"{name:<{width}} {tier:<5} {conf:<11} {'NO URL':<9} {'-':>5}  needs setup")
            continue

        if not source.get("active"):
            print(f"{name:<{width}} {tier:<5} {conf:<11} {'OFF':<9} {'-':>5}  inactive")
            continue

        try:
            items = _dispatch(source, queries)
            status = "OK" if items else "EMPTY"
            if not items:
                failures += 1
            print(f"{name:<{width}} {tier:<5} {conf:<11} {status:<9} {len(items):>5}")
        except Exception as exc:                          # noqa: BLE001
            failures += 1
            detail = f"{type(exc).__name__}: {exc}"[:34]
            print(f"{name:<{width}} {tier:<5} {conf:<11} {'FAIL':<9} {'-':>5}  {detail}")

    print("-" * 78)
    print(f"{failures} source(s) need attention")
    print()
    return 0 if failures == 0 else 1


# --------------------------------------------------------------------------

def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="PES news feed ingestion")
    parser.add_argument("--check", action="store_true", help="test sources and exit")
    parser.add_argument("--demo", action="store_true", help="build from fixtures")
    parser.add_argument("--out", default=str(DATA_DIR / "news.json"))
    args = parser.parse_args()

    # --demo is the offline self-test: no network, no keys. Prompting for
    # credentials there stopped the demo building at all on a first run.
    if not args.demo:
        if ensure_env_file():
            return 0
        load_env_file()

    if args.check:
        print()
        for name, label in (("AGSI_KEY", "GIE AGSI+ storage"),
                            ("ENTSOE_TOKEN", "ENTSO-E outages")):
            state = "found" if os.environ.get(name) else "NOT SET"
            print(f"  {name:<14} {state:<8} ({label})")
        return health_check()

    payload = run(demo=args.demo)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    counts = payload["alert_counts"]
    print(f"wrote {payload['item_count']} items to {out_path} "
          f"({payload['superseded_count']} superseded and hidden)")
    print(f"  critical {counts['critical']}, high {counts['high']}, normal {counts['normal']}")
    print(f"  sources {payload['sources']['healthy']}/{payload['sources']['total']} healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
