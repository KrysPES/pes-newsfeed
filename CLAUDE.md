# CLAUDE.md

Instructions for Claude. Read this before doing anything else in this repo.

## What this is

A live energy and commodities news feed for the PES trading terminal, to be
deployed on pesomnia.com as a collapsible drawer.

**It is finished and working.** Alex built and tuned it, and has run it against
live feeds. You are picking up a working system to deploy and integrate, not a
brief to implement.

Your user is **Krys**, the developer who builds the production versions of
Alex's tools. He is also building the production trading terminal that this
drawer plugs into.

## First action, before anything else

```bash
pip install -r requirements.txt
python tests/test_pipeline.py
```

34 tests should pass. If they do, the system is intact and you should not be
modifying `src/scoring.py`, `src/dedupe.py` or `src/supersede.py`.

Then open `web/PES_News_Drawer_DEMO.html` in a browser. That is the finished
widget with sample data.

## Your two jobs

1. **Deploy the ingestion job** so `data/news.json` refreshes automatically.
2. **Integrate the drawer** into the production trading terminal.

Both need things only a human can do. See the walkthrough section below and
run it interactively with Krys rather than assuming he has already done it.

## Do not

- **Do not rewrite the scoring engine.** It is deterministic by design because
  the budget for this project is zero: no API keys with per-token costs, no
  model calls at runtime. Every weight in `config/themes.json` was tuned
  against real output. Suggesting an LLM-based relevance score is not helpful.
- **Do not re-derive urgency in the front end.** Use the `alert` field. The
  banding includes planned-event and rate-limit logic that will silently drift
  if reimplemented in JavaScript.
- **Do not deploy the feed via Netlify build hooks or scheduled functions.**
  Netlify's free plan is credit-metered across bandwidth, builds and compute,
  and production deploys consume credits. A 5 minute schedule exhausts the free
  tier inside a day and takes pesomnia.com offline with it. The feed is served
  as a static file from GitHub. This is deliberate.
- **Do not remove the localStorage read-state.** If you have guidance that
  localStorage fails in artifacts: that applies to Claude.ai artifacts, and
  this widget is not one. It is a page on a hosted website where localStorage
  is the correct tool. It is what stops a refresh re-flashing alerts.
- **Do not strip the `?event=` query from adapter URLs**, however redundant it
  looks against a landing page that ignores it. It is the per-event identity:
  deduplication keys on canonical URL and read-state keys on `url`, so
  removing it collapses every outage from that platform into one item.
- **Do not commit `.env`.** It holds API keys. It is gitignored; keep it that way.
- **Do not enable the `gdelt` or `google_news` sources.** Both are flagged
  `requires_review` in `config/sources.json`: GDELT's free tier may be
  non-commercial, and Google News terms restrict redisplaying content on
  another site. Those are Alex's decisions and the system does not need either.
- **Do not make the drawer a flex sibling of the terminal's main panels.** It
  is `position: fixed` and overlays deliberately. The terminal has a hard
  requirement to fit a maximised Chrome window with no scrollbars, verified
  from 1366x645 up to 2560x1289. If the drawer takes width from the layout,
  the charts reflow and that guarantee breaks.

## How it works, briefly

```
sources ──▶ ingest.py (cron, 5 min) ──▶ data/news.json ──▶ widget polls it
```

- `src/ingest.py` fetches, scores, deduplicates and writes one JSON file
- That file **is** the API. No server, no database, no endpoint
- `web/widget.html` is the reference drawer. It is complete and working
- `.github/workflows/ingest.yml` runs the job every 5 minutes

Read `docs/DATA_SPEC.md` for the JSON contract before touching the front end.
Read `docs/BUILD_BRIEF.md` for the integration detail.

Three behaviours are non-obvious and deliberate:

- **Planned versus unplanned** is the most important distinction in the feed.
  Routine maintenance is already priced in; an unplanned outage is the news.
  Anything flagged planned can never raise a critical alert.
- **Supersession** retires earlier versions of a developing story. Monday's
  outage, Tuesday's extension and Wednesday's fix collapse to one visible row.
  Superseded items are flagged `hidden`, not deleted. Filter on `hidden`.
- **A resolution is never merged into the outage it resolves.** They stay as
  separate items with a supersession link. Merging them would hide the fact
  that something is fixed.

## Human setup walkthrough

Work through this with Krys interactively. Ask one thing at a time, confirm
each is done before moving on, and do not assume anything is already in place.

### Part A: credentials

The feed uses two free API keys plus one feed URL.

1. Ask Krys whether he has received the API keys from Alex. They are
   `AGSI_KEY` (GIE gas storage) and `ENTSOE_TOKEN` (ENTSO-E outages).
2. **Do not ask him to paste them into the chat.** Tell him to put them
   straight into the `.env` file, or directly into GitHub Actions Secrets.
3. Flag this to Krys: Alex registered both keys personally. For a production
   service, PES may prefer keys registered to a service account so they do not
   break when someone changes role. Worth raising with Alex before go-live.
4. He also needs the **Nord Pool UMM feed URL** from Alex. It cannot be
   derived; it is generated by applying filters in the UI at
   umm.nordpoolgroup.com and copying the RSS link.

### Part B: the repository

1. Tell Krys to create a **public** GitHub repository.
   Explain why, because it looks wrong at first glance: GitHub Actions minutes
   are unlimited on public repos and capped at 2,000 per month on private
   ones, which a 5 minute schedule burns through in about three days. The repo
   contains only public feed URLs and scoring config. No credentials.
2. Push this project to it.
3. Walk him through adding the two secrets:
   Settings, then Secrets and variables, then Actions, then New repository
   secret. Names must be exactly `AGSI_KEY` and `ENTSOE_TOKEN`.
4. Confirm `.env` is not in the pushed files. Check `git status` shows it as
   ignored.

### Part C: verify the job runs

1. Ask him to open the Actions tab and trigger `news feed ingest` manually
   using **Run workflow**.
2. It should finish green in under two minutes.
3. Wait for the 5 minute schedule and confirm commits appear against
   `data/news.json`.
4. If sources fail, that is expected. Run `python src/ingest.py --check` and
   fix or disable the broken ones in `config/sources.json`. A handful of the
   publisher RSS URLs were never verifiable at build time.

### Part D: connect the terminal

1. The feed URL is:
   `https://raw.githubusercontent.com/<owner>/<repo>/main/data/news.json`
2. Verified: raw.githubusercontent.com serves `access-control-allow-origin: *`
   and `cache-control: max-age=300`, so the terminal reads it cross-origin
   with no proxy, and the cache lines up with the 5 minute cron.
3. In the widget, set the single constant at the top of the script:
   ```js
   const FEED_URL = "https://raw.githubusercontent.com/<owner>/<repo>/main/data/news.json";
   ```
4. Integrate the drawer into the terminal. Swap the four colour variables
   declared at the top of its stylesheet for the terminal's own.

### Part E: hand back to Alex

One open question Alex has not settled: **should a critical alert auto-open the
drawer, or only flash it?** Currently it only flashes, on the view that a
terminal that opens panels by itself while someone is working is infuriating.
Ask Krys to confirm with Alex before go-live.

## Ongoing

`config/themes.json` is Alex's file. It defines what counts as relevant, using
structural vocabulary rather than named events so it does not need editing when
the news changes. If Krys wants to change ranking behaviour, that is a
conversation with Alex, not a code change.

Run `python tests/test_pipeline.py` after any change to config or scoring.
Every test in there exists because that behaviour was wrong at some point
during the build.
