#!/usr/bin/env python3
"""
Interactive setup. Avoids hand-editing config/sources.json.

    python src/configure.py

Walks through the sources that need a URL, then switches on everything that is
ready to run. Validates as it goes, so a stray comma cannot break the file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ingest import ensure_env_file, load_env_file   # noqa: E402

SOURCES = ROOT / "config" / "sources.json"

# sources that need no credential at all
NO_KEY_NEEDED = {"elexon_remit"}


def main() -> int:
    if ensure_env_file():
        return 0
    load_env_file()

    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = cfg["sources"]

    print()
    print("PES news feed setup")
    print("=" * 66)
    print("Press Enter to skip anything you have not got yet.")
    print()

    # ---- 1. URLs that have to be pasted in ------------------------------
    for src in sources:
        if src.get("tier") != 1 or src.get("url"):
            continue

        print(f"  {src['name']}")
        note = src.get("note", "")
        if note:
            first = note.split(". ")[0]
            print(f"    {first[:88]}")
        try:
            answer = input("    Paste URL (or Enter to skip): ").strip()
        except EOFError:
            answer = ""
            print()
        if answer:
            src["url"] = answer
            src["active"] = True
            src["confidence"] = "user-supplied"
            print("    set and switched on")
        else:
            print("    skipped")
        print()

    # ---- 2. switch on anything now ready --------------------------------
    turned_on, waiting = [], []

    for src in sources:
        if src.get("active") or not src.get("url"):
            continue

        # never auto-enable a source carrying a licence or terms question.
        # GDELT's free tier may be non-commercial and Google News terms
        # restrict redisplaying content. Those are Alex's calls, not a
        # setup script's.
        if src.get("requires_review"):
            waiting.append(f"{src['name']} (left off: see note in sources.json)")
            continue

        key_var = src.get("api_key_env")
        if key_var and not os.environ.get(key_var):
            waiting.append(f"{src['name']} (needs {key_var} in .env)")
            continue
        if src["id"] not in NO_KEY_NEEDED and src.get("type") == "html_watch":
            continue

        src["active"] = True
        turned_on.append(src["name"])

    # ---- 3. write back safely -------------------------------------------
    text = json.dumps(cfg, indent=2, ensure_ascii=False)
    json.loads(text)                       # prove it parses before saving
    SOURCES.write_text(text, encoding="utf-8")

    print("-" * 66)
    active = [s["name"] for s in sources if s.get("active")]
    print(f"Active sources: {len(active)}")
    for name in active:
        print(f"  on   {name}")
    for name in waiting:
        print(f"  wait {name}")

    missing = [s["name"] for s in sources if s.get("tier") == 1 and not s.get("url")]
    if missing:
        print()
        print("Still without a URL (optional, add later by running this again):")
        for name in missing:
            print(f"  --   {name}")

    print()
    print("Next:  python src/ingest.py --check")
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ncancelled, nothing changed")
        raise SystemExit(1)
