# PES market calendar

Part five of the PES trading terminal. A market calendar in the right hand
drawer, sharing a split tab with the news feed.

**Start with `KRYS_READ_ME_FIRST.md`.** Then hand the folder to Claude with
`CLAUDE.md`.

## Namespacing

Classes `.pes-cal-*`, ids `pesCal*`, variables `--cal-*`, one global
`window.PESCalendarPane`. Same discipline as the popups module.

## Behaviour change to something already shipped

Integrating this **changes the existing news drawer**. Its rail currently has
one `NEWS` label; it becomes two stacked blocks with the calendar below.
Nothing about the news pane's width, geometry or content changes, but the rail
markup and CSS do. Flagged here rather than buried in the integration doc.

## Quick start

```bash
# see it
open web/PES_Calendar_Drawer_DEMO.html

# rebuild after editing src/
python build_data.py && python build_demo.py

# tests
python -m unittest discover -s tests -p "test_*.py"
cd forward-scanner && python -m unittest discover -s tests -p "test_*.py"
```

## Layout

```
data/          calendar.csv (fixed) + forward_calendar.csv (weekly) + events.json
src/           the pane: calendar.css, calendar.js, flags.svg, drawer.html
               plus demo-only.css, which is demo scaffolding and does not ship
web/           built demo, opens offline. Never edit by hand
forward-scanner/  the weekly scanner, self contained, own test suite
tests/         21 data contract and build integrity tests
docs/          DATA_SPEC, INTEGRATION, QA_REPORT, and the two run reports
build_data.py  merges the CSVs into events.json
build_demo.py  assembles web/ from src/
```

## Counts

59 historic events, 244 forward, 303 in the merged feed. 10 of 35 scanner
sources resolved. 109 tests across the two suites, plus 22 mutation tests in
the scanner.
