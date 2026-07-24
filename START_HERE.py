#!/usr/bin/env python3
"""
START HERE.

One command, start to finish:

    python START_HERE.py

Runs an offline self-test first, so you can see the whole thing working before
any keys or network are involved. Then, if you want, it sets up the live feed.

Nothing here can break anything. It reads public feeds and writes files inside
this folder only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def rule(title: str = "") -> None:
    print()
    print("=" * 68)
    if title:
        print(f"  {title}")
        print("=" * 68)


def run(args: list[str], label: str) -> bool:
    print(f"\n> {label}\n")
    result = subprocess.run([PY, *args], cwd=ROOT)
    return result.returncode == 0


def keys_present(env_path: Path) -> bool:
    """True once at least one key in the .env file has a value after the = sign."""
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        if value.strip().strip('"').strip("'"):
            return True
    return False


def ask(question: str) -> bool:
    try:
        return input(f"\n{question} [y/n]: ").strip().lower().startswith("y")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def main() -> int:
    rule("PES news feed setup")
    print("""
  This runs in two parts.

    Part 1  an offline test, no keys and no internet needed.
            Proves the machinery works and shows you the widget.

    Part 2  the live feed, using your API keys.

  You can stop after Part 1 and come back later.
""")

    # ---- python version ----------------------------------------------
    major, minor = sys.version_info[:2]
    print(f"  Python {major}.{minor} detected", end="")
    if (major, minor) < (3, 10):
        print("  -- too old, please install Python 3.10 or newer from python.org")
        return 1
    print("  -- fine")

    # ---- dependencies -------------------------------------------------
    rule("Checking the two libraries it needs")

    def have_deps() -> bool:
        try:
            import feedparser, requests   # noqa: F401
            return True
        except ImportError:
            return False

    if have_deps():
        print("  already installed, nothing to do")
    else:
        # try the normal way, then the fallbacks. Managed Python installs
        # (some Linux distros, some locked-down corporate builds) refuse a
        # plain install, so do not give up on the first refusal.
        attempts = [
            (["-m", "pip", "install", "-q", "-r", "requirements.txt"], "standard install"),
            (["-m", "pip", "install", "-q", "--user", "-r", "requirements.txt"], "user install"),
            (["-m", "pip", "install", "-q", "--break-system-packages",
              "-r", "requirements.txt"], "managed-environment install"),
        ]
        for args, label in attempts:
            run(args, label)
            if have_deps():
                break

        if not have_deps():
            print("""
  Could not install them automatically. Run one of these by hand, then
  start this script again:

     python -m pip install feedparser requests
     python -m pip install --user feedparser requests
""")
            return 1
        print("  done")

    # ---- part 1: offline self-test ------------------------------------
    rule("PART 1  offline test")
    print("\n  Running the built-in checks first.")
    if not run(["tests/test_pipeline.py"], "self-test"):
        print("\n  Something is wrong with the install. Send me the output above.")
        return 1

    print("\n  Now building a demo feed from the sample data.")
    if not run(["src/ingest.py", "--demo"], "build sample feed"):
        return 1
    if not run(["build_demo.py"], "build the widget"):
        return 1

    demo = ROOT / "web" / "PES_News_Drawer_DEMO.html"
    rule("Part 1 done")
    print(f"""
  Open this file by double-clicking it:

     {demo}

  That is the widget, working, with sample headlines. Click the NEWS tab on
  the right to collapse it. Click a headline to expand it.

  The headlines in it are made up. They exist to test the ranking.
""")

    if not ask("Set up the live feed now?"):
        print("\n  Fine. Run this script again whenever you are ready.\n")
        return 0

    # ---- part 2: live -------------------------------------------------
    rule("PART 2  live feed")

    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# Paste your keys after the = sign. No quotes, no spaces.\n"
            "# This file is never uploaded to GitHub.\n\n"
            "AGSI_KEY=\nENTSOE_TOKEN=\n", encoding="utf-8")

    # Wait for the user rather than making them restart the script. An earlier
    # version created the file and exited, which meant running the whole thing
    # twice for no reason.
    while not keys_present(env_path):
        print(f"""
  Your API keys go in this file:

     {env_path}

  1. Open it in Notepad. If Windows will not open it, right-click the file,
     Open with, Choose another app, Notepad.
  2. Paste your keys after the = signs, so it reads like:

        AGSI_KEY=your_agsi_key
        ENTSOE_TOKEN=your_entsoe_token

     No quotes, no spaces around the = sign.
  3. Save and close it.
""")
        try:
            input("  Press Enter once you have saved the file (or Ctrl+C to stop): ")
        except (EOFError, KeyboardInterrupt):
            print("\n  Stopped. Your keys are safe in that file for next time.\n")
            return 0

        if not keys_present(env_path):
            print("\n  Still cannot see a key in there. Check it saved, and that the")
            print("  file is named exactly .env with nothing after it.")

    print("\n  Keys found.")

    rule("Your feed URLs")
    print("""
  Now paste the URLs you have. Nord Pool is asked for first.
  Press Enter to skip anything you have not got yet; you can run this
  again later to add more.
""")
    if not run(["src/configure.py"], "configure sources"):
        return 1

    rule("Testing every source")
    run(["src/ingest.py", "--check"], "source health check")
    print("""
  Some FAIL lines are expected. Several feed URLs could not be tested when
  this was built, so a few will need correcting or switching off. That is
  normal and does not mean anything is broken.
""")

    if not ask("Build the live feed now?"):
        return 0

    rule("Building the live feed")
    if not run(["src/ingest.py"], "fetch and score"):
        return 1
    if not run(["build_demo.py"], "rebuild the widget"):
        return 1

    rule("Done")
    print(f"""
  Open this again to see the live feed:

     {demo}

  Read the top twenty headlines. The question that matters is whether the
  ranking is right: anything important buried, anything trivial at the top.

  Send those notes back and the weights can be tuned.
""")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled. Nothing was changed.\n")
        code = 1
    if sys.stdin.isatty():
        input("\nPress Enter to close.")
    raise SystemExit(code)
