# CLAUDE.md: PES market calendar

Instructions for Claude, working with Krys, to integrate this into the PES
trading terminal on pesomnia.com.

## What this is

Part five of the terminal. A market calendar sharing the existing right hand
drawer with the news feed, on a split vertical tab.

Three components, all finished:

| Path | What it is |
|---|---|
| `data/calendar.csv` | 59 historic events, 2018 to July 2026. **Fixed. Never regenerate.** |
| `data/forward_calendar.csv` | 244 upcoming events. Scanner output, refreshed weekly |
| `data/events.json` | The two merged, chronological. What the pane reads |
| `forward-scanner/` | The scanner that keeps the forward file current |
| `src/` | The pane: CSS, JS, flag sprite, drawer markup |
| `web/PES_Calendar_Drawer_DEMO.html` | Built from `src/`. Opens offline |
| `build_data.py` | Merges the two CSVs into `events.json` |
| `build_demo.py` | Assembles the demo from `src/` |
| `docs/` | Data spec, integration notes, provenance |

**Open `web/PES_Calendar_Drawer_DEMO.html` first.** It is the whole pane
working, offline, on the real data.

## Build rules

- **No dependencies.** Standard library and `requests` for the scanner, plain
  JS for the pane. No framework, no build step beyond the two scripts.
- **The demo is a build artefact.** Never edit `web/` by hand. Change `src/`,
  run `python build_data.py && python build_demo.py`. Running the build twice
  must produce a byte identical file; there is a test for this.
- **Run the tests after any change:**
  ```bash
  python -m unittest discover -s tests -p "test_*.py"          # 30 package tests
  cd forward-scanner && python -m unittest discover -s tests    # 79 scanner tests
  ```

## Integration into the terminal

Four things, mirroring what the news drawer needed.

**0. Everything is namespaced.** Classes are `.pes-cal-*`, ids are `pesCal*`,
CSS variables are `--cal-*`, and the JS exposes exactly one global,
`window.PESCalendarPane`. This matches the popups module, which uses
`.pes-tech-*` and `--tech-*`. It matters because the pane's selectors used to
be bare (`.row`, `.title`, `.time`, `.list`) which would have collided with the
terminal shell. There are tests that fail if a bare one comes back.

**1. Split the tab, not the drawer.** The rail becomes two stacked blocks,
News on top and Calendar below, and whichever is clicked fills the existing
392px pane. Do **not** show both panes at once; that halves the news list.
`src/drawer.html` shows the structure.

**2. Colour variables need nothing done to them.** `src/calendar.css`
namespaces everything to `--cal-*`, scoped to `.drawer`, each one inheriting
the terminal's own token with a fallback: `--cal-panel: var(--bg-panel,
#161d27)`. Drop the file in and it picks up the terminal automatically. This
matches how `popups/src/popup.css` handles `--tech-*`.

`src/demo-only.css` carries the terminal stand-in tokens and the backdrop, and
is used **only** by the demo build. Do not ship it. There is a test that
`calendar.css` declares no terminal level variable, because an earlier version
did and it silently recoloured the popups.

**3. Respect the layout rules.** The terminal must fit a maximised Chrome
window with no scrollbars, verified 1366x645 up to 2560x1289. The drawer is
`position: fixed` and overlays rather than displacing the grid, specifically
so it cannot break that. **Do not make it a flex sibling of the main panels.**

**4. Point the pane at live data.** The demo has `events.json` baked in as
`var EV = [...]`. In production, fetch it. Same static file pattern as the
news feed, same CORS story. `docs/DATA_SPEC.md` has the contract.

## Behaviour to preserve

These were decided deliberately with Alex. Please keep them.

- **Both panes collapsed on load**, neither preselected.
- **No active marker on the rail.** The rail is only visible while collapsed,
  so an open pane indicator there shows nothing true.
- **One chronological list**, historic and forward together, opening on today.
- **A row is time, region flag and title.** Nothing else. A click expands to
  detail, why it matters, notes and the source link.
- **No filtering, sorting, priority or impact ranking.** Deliberate.
- **It ignores the time machine.** Also deliberate.
- **Region is an inline SVG flag**, with a text chip for Global and Middle
  East which have no flag. Emoji flags do not render on Windows; do not
  switch to them.
- **Past rows sit at 50% opacity** and the Today divider is amber.
- **The Today jump offsets by the sticky day header height.** Removing that
  offset parks the Today label underneath the pinned header.

## Running the scanner

`forward-scanner/` is a self contained subproject. Weekly full refresh plus a
daily check on the next 14 days. It writes a new `forward_calendar.csv`, then
`build_data.py` merges it and `build_demo.py` rebuilds.

It never touches `data/calendar.csv`. The historic file is immutable.

`forward-scanner/SCANNER_BRIEF.md` is the spec it was built to.
`docs/SCANNER_RUN_REPORT.md` is what the first run actually produced,
including everything that did not resolve.

## What is unfinished

Do not present this as complete. `KRYS_READ_ME_FIRST.md` lists it, and the
short version is: zero electricity specific rows, 10 of 35 sources resolved,
62% of forward rows generated from a cadence rather than a published date,
and `ofgem.gov.uk` has regressed to a JavaScript shell.
