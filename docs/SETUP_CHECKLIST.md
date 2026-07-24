# Setup checklist

Roughly 40 minutes end to end. Steps 1-3 are the only ones that need Alex.

## 1. Get the two free keys

- [ ] **ENTSO-E**: register at transparency.entsoe.eu, then email
      transparency@entsoe.eu asking for API access. They issue a security
      token. Free, usually a day or two.
- [ ] **GIE AGSI+**: request a key on agsi.gie.eu. Free, usually instant.

Register both to a PES service account rather than a personal address, so
neither dies when someone changes role.

## 2. Grab the REMIT UMM feed URLs

This is the highest value step in the whole setup and it cannot be automated,
because the URL is generated from whatever filter you build in the UI.

- [ ] Go to umm.nordpoolgroup.com
- [ ] Filter to: message type "unavailability", both gas and electricity,
      all areas
- [ ] Copy the RSS URL the page offers
- [ ] Paste it into `config/sources.json` under `nordpool_umm`, set `active: true`
- [ ] Repeat on the EEX Transparency platform for `eex_transparency_umm`

These two feeds are where French nuclear outages, Norwegian gas outages and
continental plant trips actually surface, ahead of any news wire.

## 3. Check Gassco before scraping it

- [ ] Look at whether the EEX or GIE UMM feed already carries Gassco's
      messages. Gassco publish to an Inside Information Platform, so they very
      probably do.
- [ ] If they do, leave `gassco_flow` off permanently. One less scraper to
      maintain and it will be faster anyway.

## 4. Run the health check

```bash
pip install -r requirements.txt
export ENTSOE_TOKEN=...
export AGSI_KEY=...
python src/ingest.py --check
```

- [ ] Note which sources come back FAIL or EMPTY
- [ ] Fix the URL, or set `active: false` and move on. A dead source costs
      nothing but noise in the report.

The publisher RSS URLs in `config/sources.json` are marked `likely` rather than
`verified`. They follow each publisher's standard pattern but could not be
tested from the build environment, which had no outbound access to them. Expect
two or three to need correcting. That is what this step is for.

## 5. First real run

```bash
python src/ingest.py
python build_demo.py
```

- [ ] Open `web/PES_News_Drawer_DEMO.html` and read the top 20 items
- [ ] Ask the only question that matters: **is the ranking right?**
- [ ] Anything mis-ranked, click the row and read the breakdown. It will show
      exactly which theme or term did it.

## 6. Tune

Nearly all tuning is `config/themes.json`. Common adjustments:

| Symptom                                | Fix                                              |
|----------------------------------------|--------------------------------------------------|
| Too much noise from one outlet         | Drop its `authority` in `sources.json`           |
| A theme is under-weighted              | Raise its `weight`                               |
| A specific rubbish story type recurs   | Add a phrase to `exclusions`                     |
| Criticals firing too often             | Raise `ALERT_CRITICAL` in `scoring.py`           |
| Too many criticals at once             | Lower `max_critical` in `cap_alerts`             |

- [ ] Run `python tests/test_pipeline.py` after any change. 20 checks, instant.

## 7. Deploy

- [ ] Create a **public** GitHub repo (unlimited Actions minutes; private caps
      at 2,000/month which a 5-minute cron burns in about three days)
- [ ] Add `ENTSOE_TOKEN` and `AGSI_KEY` as Actions Secrets
- [ ] Push. The workflow runs every five minutes on its own.
- [ ] Point the terminal at the raw `data/news.json` URL, or copy it into the
      pesomnia deploy

## 8. Hand to Krys

- [ ] Send `docs/BUILD_BRIEF.md`, `docs/DATA_SPEC.md` and the demo file
- [ ] Confirm the one open question: should a critical auto-open the drawer,
      or only flash it?
