# BUILD_BRIEF: news drawer for the PES trading terminal

For Krys. Companion to the existing terminal handover pack.

---

## What this is

A live energy and commodities news feed, to sit in the production terminal on
pesomnia.com as a collapsible drawer on the right edge. Collapsed by default,
showing a narrow vertical tab. The tab and the drawer edge flash red when
something has landed that is worth opening it for.

The hard part is already done and it is not the UI. It is the relevance
scoring, which decides what is worth showing at all. That runs server side and
hands you a sorted JSON file. **Your job is to render it and wire it into the
terminal shell.** Please do not reimplement the ranking in the front end.

## What already exists in this repo

| Path                              | What it is                                        |
|-----------------------------------|---------------------------------------------------|
| `src/ingest.py`                   | The pipeline. Run on a cron, writes `data/news.json` |
| `src/scoring.py`                  | Relevance engine. Deterministic, zero cost        |
| `src/dedupe.py`                   | Story clustering across outlets                   |
| `src/adapters.py`                 | One function per source type                      |
| `config/themes.json`              | What counts as relevant. Alex owns this file      |
| `config/sources.json`             | Where news comes from                             |
| `web/widget.html`                 | Reference drawer implementation, working          |
| `web/PES_News_Drawer_DEMO.html`   | Standalone demo, opens from disk, data baked in   |
| `docs/DATA_SPEC.md`               | The JSON contract. Read this first                |
| `tests/test_pipeline.py`          | 20 regression checks. Run after any config change |

Open the demo file first. It is the whole thing working, offline, with
synthetic fixtures. Everything you need to understand is visible in it.

---

## Integration into the terminal

The reference widget is deliberately self-contained so it can be lifted in
whole. Four things need doing to make it native:

**1. Swap the colour variables.** The drawer declares its own `--bg-panel`,
`--elec`, `--gas` and so on at the top of the stylesheet. Delete those and
inherit the terminal's. The values were matched by eye against the current
build, so it should be a straight substitution.

**2. Respect the layout rules.** The terminal is under a hard constraint: it
must fit a maximised Chrome window with no scrollbars, verified from 1366x645
up to 2560x1289. The drawer is `position: fixed` and overlays rather than
displacing the grid, specifically so it cannot break that. **Do not convert it
into a flex sibling of the main panels.** If it takes width from the layout,
the charts reflow and the no-scroll guarantee goes.

**3. Wire the freshness stamp to the existing convention.** The drawer already
uses the terminal's rule, green within the hour and red beyond, driven by
`generated_at`. It re-checks on a timer so it flips on its own when left open.
Reuse the terminal's own helper if there is one rather than keeping two.

**4. Decide the poll interval.** Currently 60 seconds against a static JSON
file. That is cheap and fine. If the terminal already has a sync loop, fold it
into that instead so there is one heartbeat rather than two.

## Behaviour to preserve

These are deliberate and were tuned against real output. Please keep them.

- **Alert level comes from the `alert` field only.** Do not re-derive it from
  `score`. The banding includes planned-event and rate-limit logic that will
  drift the moment it is reimplemented.
- **The red flash fires only on an unseen critical, and only while collapsed.**
  Opening the drawer marks criticals seen and stops the flash. It must not
  pulse while the user is looking at it.
- **`prefers-reduced-motion` kills the pulse** and leaves a static red edge.
  Already implemented, keep it.
- **The pause button stops the refresh, not the animation.** It exists so a row
  does not shift while someone is mid-read.
- **Row click reveals the score breakdown.** Keep it reachable. The desk will
  stop trusting the ordering the first time something inexplicable is at the
  top, and "why is this here" needs an answer in one click.
- **The tab badge means one thing: unread items.** It hides at zero. It never
  switches to a different count depending on state; an earlier version showed
  criticals-then-total and the number silently changed meaning.
- **Read-state persists in localStorage** (`pesNewsSeen_v1`), pruned to URLs
  still in the feed, so a page refresh does not re-flash criticals someone
  already dismissed. Storage unavailable degrades to in-memory, the old
  behaviour. This runs on a normal website, so localStorage is fine here.
- **Everything from the feed is escaped before rendering** and hrefs are
  restricted to http(s). Feed titles are third-party content; treat any
  string in the JSON as hostile until escaped.
- **Priority is the default sort.** The feed arrives sorted by score. The
  Recent toggle re-sorts by time in the front end only: it never changes
  scores or alert levels, so a critical stays critical wherever it lands in
  the list. Do not let a sort mode alter the alert banding.
- **Show `sources.degraded`.** A feed that has gone quiet because four sources
  died looks identical to a quiet news day. That is the failure that catches
  people out.

## Deliberately not built

Flagged so nobody assumes they were forgotten:

- **No sound or desktop notification.** Visual only, by design. Worth
  discussing whether a critical should do more than flash.
- **No search box.** Filter chips only. Easy to add if the desk wants it.
- **No mobile layout.** The terminal is a desktop product. The drawer will
  render on a narrow viewport but has not been designed for one.

## Open question for Alex, not for you

Whether the drawer should auto-open on a critical or only flash. Currently it
only flashes, on the view that a terminal that opens panels by itself while
someone is working is infuriating. Worth confirming.
