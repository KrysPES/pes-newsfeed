# Read me first

Krys,

This is the live news feed for the trading terminal. It sits as a collapsible
drawer on the right edge, and flashes red when something lands that is worth
opening it for.

It is built, tuned and working. What is left is deployment and integration
into the terminal you are building.

## How to start

Drop this whole folder into Claude and say:

> Read CLAUDE.md and walk me through deploying this.

`CLAUDE.md` contains full instructions written for Claude, including a
step-by-step walkthrough of the parts that need a human: creating the repo,
adding the API keys, verifying the scheduled job and wiring the terminal up.

## Before you start, you need from Alex

1. Two API keys, `AGSI_KEY` and `ENTSOE_TOKEN`
2. The Nord Pool UMM feed URL

None of them are in this package, deliberately.

## To see what it does right now

Open `web/PES_News_Drawer_DEMO.html` in a browser. That is the finished widget
running on sample data. Click the NEWS tab to collapse it, click a headline to
expand it, and try the Priority and Recent sort buttons.

The headlines in the demo are synthetic. They exist to exercise the ranking.

## The one thing worth knowing up front

The feed is served as a static JSON file from GitHub, not from Netlify.

That is deliberate rather than lazy. Netlify's free plan meters production
deploys against a shared credit pool, and a five minute refresh would exhaust
it in about a day and take pesomnia.com down with it. GitHub serves the file
with permissive CORS and a five minute cache, which matches the refresh
exactly. `CLAUDE.md` covers this.

## Open question for Alex

Should a critical alert auto-open the drawer, or only flash it? It currently
only flashes. Worth confirming with him before go-live.
