# PES market calendar: coverage and failures

Run completed unattended. This file leads with what is thin, missing or
unverified, as section 10 requires.

## Mutation test result, reported first

The final gate requires the validators to have been mutation tested. They were.
Eight deliberate breakages were injected into a copy of the concatenated file
and every one was caught. The three the brief names explicitly are the first
three.

| mutation injected | check fired | message raised |
|---|---|---|
| date bound: set a row date to 2026-07-31 | yes | `date 2026-07-31 outside 2018-01-01..2026-07-30` |
| title length: set a title to 61 characters | yes | `title is 61 characters, over 60` |
| dash rule: inserted U+2014 into `detail` | yes | `detail contains a dash character U+2014` |
| consensus rule: set `consensus` to 2.5 | yes | `consensus is not blank ('2.5')` |
| aggregator rule: set `source_url` to tradingeconomics.com | yes | `source_url host tradingeconomics.com is an aggregator` |
| duplicate rule: appended a copy of row 1 | yes | `duplicate date plus title` |
| category enum: set `category` to `weather` | yes | `category 'weather' not in enum` |
| schema: dropped a column from the header | yes | `schema: header is not the 15 columns in order` |

Validators run over the real concatenated file: **0 failures**.

## The headline problem: the annotation seeds did not survive the fetch gate

This is the single most important thing in this run.

Section 3 decision 5 says to reuse the 41 published annotations for the
geopolitics and supply rows. Section 4 says a row is written only if its
`source_url` was fetched, returned 200 and carries the date, "No exceptions".
Those two collided, and the hard rule won.

Of the 41 seeds, **14 were written and 27 were rejected**. The breakdown of why:

- **Link rot on one domain.** All 12 `hellenicshippingnews.com` URLs in the
  seed file now return 404. Two were later recovered from the Internet Archive,
  the other eight seeds relying on that domain were not.
- **Bot blocking.** `bloomberg.com`, `spglobal.com`, `argusmedia.com` and
  `euronews.com` return 403 or 406 to any plain fetcher.
- **Aggregator hosts.** Three seeds cite `nasdaq.com` and one cites
  `finance.yahoo.com`, which fail the section 7 aggregator check regardless of
  whether they resolve.
- **Date not on the page.** Several seeds point at a page carrying only the
  month, or at an article datelined the day after the seed's trigger day. The
  `2021-08-24` Nord Stream 2 court seed is the clearest case: every source
  found dates the Duesseldorf ruling to 25 August, not the seed's 24 August.
  Under the "two sources disagree on a date, omit the row" rule that one is out
  on its merits, not on a technicality.

For the failing seeds a replacement source was researched, keeping the seed
wording untouched and swapping only `source_url`. That recovered 5. A second
pass then queried the Internet Archive, which section 4 permits as an archive
index, asking for the snapshot closest to each seed date and putting the
returned URL through the same gate. That recovered 3 more. The remainder are in
`rejects.csv` with the observed HTTP status per source.

The archive pass was checked against the CDX index as well as the availability
API, and the pages it could not find were genuinely never archived rather than
missed. Bloomberg and Argus pages are excluded from the archive by robots, so
those seeds are unrecoverable by this route.

**What this means for the file.** The crisis years the seeds were supposed to
carry are the years that lost most. 2022 lost 6 of 14 seeds, 2023 lost 10 of
12. Only 2 of the 12 2023 seeds survived, and none of the 2023 losses could be
recovered from the archive.

**This is fixable on the seed side, not here.** The events are real and were
published. What has decayed is the URLs. Re-sourcing `events_seed.json` against
live pages would restore most of these rows mechanically.

## Rows by category

| category | rows |
|---|---|
| supply | 21 |
| rates | 8 |
| sanctions | 8 |
| geopolitics | 6 |
| policy | 5 |
| regulation | 4 |
| inflation | 2 |
| inventory | 2 |
| election | 1 |
| employment | 1 |
| growth | 1 |
| **total** | **59** |

No rows in `other`.

## Rows by year

| year | rows | rejected | comment |
|---|---|---|---|
| 2018 | 4 | 0 | no seed coverage by design, researched from scratch |
| 2019 | 1 | 1 | thinnest year in the file, see below |
| 2020 | 5 | 0 | no seed coverage by design, researched from scratch |
| 2021 | 5 | 2 | |
| 2022 | 15 | 7 | |
| 2023 | 5 | 10 | worst affected by seed link rot |
| 2024 | 3 | 1 | genuinely quiet |
| 2025 | 5 | 4 | |
| 2026 | 16 | 3 | best covered year, trap F window worked |

## What is thin, stated plainly

- **2019 is one row.** The only 2019 seed failed and no replacement carrying 5
  April 2019 was found. The single row is the September 2019 Abqaiq attack. The
  12 December 2019 UK general election is missing because the only route to a
  dated source page was to construct the URL from an observed pattern, which
  section 4 forbids.
- **2023 is five rows** against ten rejected seeds. Two are surviving seeds and
  three are the Chevron Australia LNG strike sequence researched this run. It
  should be a much denser year.
- **2024 is three rows.** Little was found beyond the UK general election, the
  US LNG export pause and the EU storage milestone that had both a clear energy
  channel and a fetchable dated source.
- **Occurrence rows are sparse across the macro series.** Decision 1 allows
  occurrence rows only where a release actually moved the energy market. For
  most CPI, labour market and GDP prints that link could not be evidenced from
  a primary source, so no occurrence row was written. This is deliberate, but it
  means the macro categories are almost all cadence rows.
- **`previous` and `actual` are blank on most rows.** Decision 4 requires first
  print with the vintage stated. Where the first print could not be confirmed
  from the source document the field was left blank rather than filled from a
  revised figure. They are populated only for the Bank Rate rows, the Fed
  emergency cut, the Ofgem cap and two figure-bearing EU rows.
- **No `time` on most rows.** Only three rows carry a time: the two Fed rows and
  the EIA gas storage cadence row, all taken from the release document itself as
  decision 6 requires. See the trap B note below.

## Unverified and unresolved series

| series | outcome |
|---|---|
| ECB monetary policy decisions | **Trap A confirmed.** The decisions index and the per year press release index both return no dated monetary policy links to a plain fetcher. Dropped to a single cadence only row anchored on the 23 July 2026 meeting date, which the key interest rates page does carry. |
| US CPI and employment situation | **`bls.gov` returns 403 to both the crawler and WebFetch.** No BLS row could be sourced from BLS. The October 2025 CPI cancellation (trap E) is in the file, sourced from a news report of the BLS announcement rather than from BLS. The routine BLS release cadence is absent. |
| Eurostat euro area HICP | **Unresolved.** The euro indicators page is a search portlet and yields no per release dated links to a plain fetcher. No Eurostat row was written. |
| IEA Oil Market Report | **`iea.org` returns 403.** The 11 March 2026 collective action is in the file sourced from news reporting, not from the IEA. The monthly OMR series has no row. |
| EU sanctions timeline on consilium.europa.eu | **`consilium.europa.eu` returns 403** to the crawler and to WebFetch. Replaced with `finance.ec.europa.eu`, which carries dated pages per package and worked well. Seven sanctions rows come from that route. |
| GIE AGSI storage | **Not usable.** `agsi.gie.eu` returns a 1.4 kB JavaScript shell with no dated content. No row. |
| NESO winter outlook | **Not resolved.** The publications page renders but no dated per edition link was harvested within budget. No row. |
| UK and US sanctions listings | **Not located.** No row. |
| Ofgem price cap, pre-quarterly era | Only the quarterly era is represented, anchored on the 27 May 2026 announcement. The six monthly era could not be anchored on a fetched dated page within budget, so trap D is only half captured. |
| ONS CPI, labour market, GDP | Reachable and walked. Archives paginate cleanly and bulletin pages carry the release date. |
| BoE MPC | Reachable via the Bank Rate history page, which carries every change date in the window on one page. |
| Fed FOMC | Reachable. Both index pages walk, 29 statement links harvested for 2018 to 2020 and 53 for 2021 onwards. |
| OPEC | Index walks and yields 22 dated press release links, but all are 2026. No pre-2026 OPEC release was harvestable from the index, and constructing older IDs is forbidden. No OPEC ministerial row was written. |

## Traps, one by one

- **A, JavaScript indexes.** Confirmed on ECB, and the same pattern on Eurostat
  and AGSI. Detected by checking for dated links before concluding an archive
  was empty, as instructed.
- **B, release times drift.** **Not captured.** ONS bulletin pages carry the
  release date but not the release time, so the 09:30 to 07:00 move is not in
  the file. Rather than assume a single time across 2018 to 2026, which the
  brief explicitly calls wrong, `time` is blank on all ONS rows and the gap is
  recorded here.
- **C, contradictory calendar pages.** Honoured by leaving ECB `time` blank.
- **D, cadence drifts.** Half captured. See the Ofgem note above.
- **E, releases that did not happen.** Captured. The cancelled October 2025 US
  CPI is a row dated to the 21 November 2025 cancellation announcement, with the
  original 7 November scheduled date in `notes`.
- **F, the post cutoff window.** This got full research effort and is the best
  covered part of the file: 16 rows in 2026, including the Qatari LNG force
  majeure and its extension, the IEA record stock release, the two Hormuz
  ceasefire steps, four EU coordination and storage decisions, the Ofgem cap
  rise attributed to the conflict, and the 20th and 21st sanctions packages.
- **G, seeds do not cover the whole window.** Confirmed and worked around. 2018,
  2019, 2020 and April to July 2026 were researched from scratch.

## Decisions taken under the no questions rule

Recorded because each is a judgement a reader may want to overturn.

1. **Column count.** Section 7 says "exactly the 16 columns" but the section 2
   schema table names 15. Section 2 is the authoritative list, so the validator
   checks 15 columns in the section 2 order. No 16th column was invented.
2. **Seed category derivation.** Decision 5 gives `supply` for physical flow,
   outage and production, `sanctions` for sanctions measures, `geopolitics`
   otherwise. Weather and storage balance events fit none of the three
   literally, so they were put under `supply` as physical balance events.
   Calling a cold snap `geopolitics` would have been worse.
3. **Seed `region`.** Decision 5 does not map a region. Regions were assigned
   from where the event happened, for example `Norway` for Norwegian supply and
   `Middle East` for the Hormuz events.
4. **Oil events get `fuel_scope` gas.** Section 9 puts OPEC events under `gas`,
   which sets the precedent that oil linked events are scoped by their channel
   into the gas market rather than by the molecule. Applied consistently to the
   OPEC+ 2020 rows, the IEA stock release, Abqaiq and the oil sanctions
   packages.
5. **Aggregator definition.** Read as economic calendar aggregators and scraper
   mirrors, not as news publishers. The blocklist is in `work/pes.py`. Original
   reporting from a wire or trade publication is treated as a source; a calendar
   site is not.
6. **Seed date collisions.** One row sits on a seed date: the 11 March 2026 IEA
   release. That seed was itself rejected, so there is no competing row. It is
   declared in the validator as a deliberate merge.
7. **Archive snapshots as `source_url`.** Three rows cite a `web.archive.org`
   snapshot because the publisher's own URL is dead. The snapshot is a copy of
   that publisher's page, not a third party summary, and the original URL is
   recorded in `notes`. Flip these back if your terminal should only ever link
   to live publisher domains, but note the alternative is not having the rows.
8. **One row excluded on the aggregator rule, not on availability.** The
   24 January 2022 invasion fears seed has a reachable archive snapshot that
   passes the date check, but its publisher is `nasdaq.com`, which this run
   treats as an aggregator. It is listed in `rejects.csv` with that reasoning
   so you can reinstate it if you read Nasdaq as a wire syndication mirror
   rather than an aggregator.

## Run statistics

- 218 fetch attempts logged, 171 returned 200.
- Failure statuses: 22 x 404, 17 x 403, 2 x 406, 2 x 202, 2 x 429, 2 timeouts.
- Domains that blocked the crawler outright: `bls.gov`, `iea.org`,
  `consilium.europa.eu`, `bloomberg.com`, `spglobal.com`, `investing.com`,
  `ferc.gov`, `offshore-technology.com`.
- Domain with total link rot: `hellenicshippingnews.com`, 12 of 12 URLs dead.
- Budget caps were not hit. The run stopped researching because the remaining
  candidates were not yielding verifiable sources, not because of a cap.

## Files

- `output/calendar.csv`, 59 rows, the concatenated file.
- `output/rejects.csv`, 28 rows, everything dropped and why, with the observed
  HTTP status of each source that was tried.
- `output/provenance.csv`, one line per calendar row giving the source URL, the
  status observed when it was fetched, and whether it is a live page or an
  archive snapshot. Not required by the brief, added so the fetch gate stays
  auditable after ingestion.
- `output/tranches/*.csv`, one CSV per category, identical columns, as
  decision 2 requires.
- `work/fetch_log.jsonl`, every fetch attempt with status.
- `work/cache/`, the fetched pages, so the gate is auditable after the fact.

## Honest summary

59 rows is a short calendar. It is short because the fetch before write rule was
applied without exception, including to the annotation seeds, and roughly two
thirds of the seed URLs no longer resolve, are blocked, or do not carry the
date they claim. The parts researched from primary sources this run, the 2026
window especially, are dense and well evidenced. The parts inherited from the
seed file are not, and the fix for that sits in the seed file rather than here.
