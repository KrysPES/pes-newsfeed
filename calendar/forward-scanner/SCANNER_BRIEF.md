# PES market calendar: forward scanner build brief

Phase two of part five of the PES trading terminal. The historic calendar is
done and immutable. This brief builds the thing that keeps the calendar
populated going forward.

## 1. What you are building

**Build a scanner, not a research run.** The last run was a one-off crawl by
an agent. This is a recurring job that will run every week for years. So the
deliverable is **deterministic Python code** plus a source registry, not a
transcript of findings.

Reason: scraping the same thirty pages every week is mechanical. Putting a
model in that loop each time reintroduces variance into dates, which is the
one field that must never wobble. The model builds the scanner and reviews it
periodically. The scanner does the weekly work.

Standard library plus `requests` only. No framework. It must run unattended
from a scheduler with no interactive input.

## 2. Scope, scheduled events only

The scanner captures events whose date is published in advance. It does **not**
attempt to anticipate unscheduled events. Outages, sanctions, conflict and
supply shocks are the historic file's business, not the scanner's. Predicting
them would be forecasting dressed as a calendar.

### In scope for v1

**Energy data releases.** EIA weekly natural gas storage and weekly petroleum
status, EIA Short Term Energy Outlook, GIE AGSI storage plus the EU filling
target dates, IEA Oil Market Report and Gas Market Report, OPEC monthly report
and OPEC+ ministerials and JMMC, Baker Hughes rig count, CFTC positioning.

**Policy and regulatory dates.** Ofgem price cap announcements, Capacity Market
T-1 and T-4 auctions, CfD allocation round milestones, UK and EU ETS auction
calendars, EU Energy Council meetings, the six monthly EU sectoral sanctions
renewals, Budget and Spring Statement, annual network charging decisions.

**Macro and rates.** BoE, ECB and Fed decisions plus minutes and the Monetary
Policy Report, ONS CPI, labour market and monthly GDP, Eurostat flash HICP and
GDP, BLS CPI and payrolls, PMIs for the UK, euro area, US and China, German Ifo
and ZEW.

**Political.** Scheduled elections and referendums, plus fixed date summits,
COP, G7, G20, European Council.

**Market mechanics.** ICE contract expiries and prompt rolls, gas year start on
1 October, the seasonal roll, clock changes.

**Weather, fixed release dates only.** ECMWF and Copernicus monthly and
seasonal outlooks, the Met Office three month outlook, the NOAA hurricane
season outlook and season start. Forecast content is out of scope, only the
scheduled release dates.

### Held back to phase two

**Physical supply schedules.** Norwegian field and pipeline maintenance, French
nuclear availability and planned outages, interconnector outages, LNG terminal
maintenance, National Gas planned works.

This is the highest value group on the list and it is deliberately not in v1.
The sourcing is hard, some of it sits behind REMIT platforms that may need
registration, and a half working version would contaminate the file. Do not
attempt it. Note in the output that it is absent by design.

## 3. Output schema

`forward_calendar.csv`. The historic 15 columns in the same order, plus three:

| column | rule |
|---|---|
| date | ISO 8601 |
| time | HH:MM UTC, blank unless taken from the source |
| region | UK, EU, US, Global or a named other |
| category | rates, inflation, employment, growth, election, policy, regulation, geopolitics, sanctions, supply, inventory, other |
| title | plain, max 60 characters, no rhetorical tail |
| detail | 1 to 2 sentences on what is scheduled to happen |
| energy_relevance | 1 sentence on the channel to gas or power prices |
| fuel_scope | gas, electricity or both |
| previous | prior value, blank if not applicable |
| consensus | **always blank** |
| actual | **always blank on forward rows**, see decision 6 |
| recurring | yes or no |
| cadence | the schedule for the era this row sits in |
| source_url | the published schedule page the date came from |
| notes | qualifiers, blank if none |
| **status** | `scheduled`, `rescheduled`, `cancelled` or `occurred` |
| **last_verified** | ISO date the source was last successfully fetched |
| **date_source** | `published` or `generated`, see decision 2 |

Horizon: 18 months forward from the run date. Do not emit rows beyond that even
where a body publishes further out.

House style on every text field: British English, no em dashes or en dashes, no
Oxford commas, plain flat titles.

## 4. Settled decisions, do not revisit

1. **Scheduled only.** As section 2.
2. **Scrape the published schedule, do not generate dates.** Bodies publish
   forward calendars. Generating a date from a cadence rule goes silently wrong
   the moment a body reschedules. Generation is a fallback only, and any
   generated row must carry `date_source=generated` so it is visible. A
   generated row is never emitted where the body publishes a schedule that
   simply failed to fetch this week, in that case carry the previous value and
   leave `last_verified` stale.
3. **No API keys.** Alex has declined registration, so EIA API v2, BLS API v2
   and any other keyed route are out. Consequences are in section 8, state them
   in the output rather than working around them quietly.
4. **Forward rows live in their own file.** `forward_calendar.csv` is separate
   from the historic `calendar.csv`, which is immutable. The terminal merges
   them at display time. Never write to the historic file.
5. **Refresh rhythm.** Full refresh weekly. Daily check limited to events dated
   in the next 14 days, where a late change matters most and the fetch cost is
   small.
6. **No backfilling actuals.** When an event passes, flip `status` to
   `occurred` and stop. Do not fetch the outturn. Scraping outturns is what cost
   the last run 27 rows, and with decision 3 there is no clean API route to do
   it properly.

## 5. Source registry

Build the registry from domains empirically known to admit a crawler. The last
run established both lists, do not rediscover them.

**Known to walk cleanly:** `ons.gov.uk`, `bankofengland.co.uk`,
`federalreserve.gov`, `eia.gov`, `ir.eia.gov`, `ec.europa.eu` including
`finance.ec.europa.eu` and `energy.ec.europa.eu`, `ofgem.gov.uk`,
`europarl.europa.eu`, `electionresults.parliament.uk`,
`commonslibrary.parliament.uk`.

**Known to block outright, do not build on them:** `bls.gov`, `iea.org`,
`consilium.europa.eu`, `bloomberg.com`, `spglobal.com`, `investing.com`,
`ferc.gov`, `argusmedia.com`.

**Known to render via JavaScript with no dated links to a plain fetcher:** the
ECB decisions index, the Eurostat euro indicators portlet, `agsi.gie.eu`.

**Known dead:** `hellenicshippingnews.com`, total link rot.

For every other source in section 2, resolve the route at build time the same
way: find the published schedule page, confirm it carries dated entries,
confirm a plain fetcher can read them. Record the verdict per source in the
registry file with the date checked. A source that cannot be resolved is
recorded as unresolved and produces no rows. It is not worked around.

One thing worth trying, flagged as unverified: BLS API v1 is open without
registration and sits on a different host to the blocked `bls.gov` pages. If it
resolves it may recover US macro release dates without a key. Test it. If it
does not work, drop US macro and say so.

## 6. Hard rules

- A row is written only if its `source_url` was fetched, returned 200 and the
  page carries the date. No exceptions.
- URLs are harvested from links on a schedule page. **Never construct a URL
  from an observed pattern.**
- `consensus` is blank on every row. `actual` is blank on every row.
- Omit rather than guess. Leave a field blank rather than infer it.
- **Never stop to ask a question.** This runs unattended on a scheduler.
- Failures go to `scan_log.jsonl` with the observed status, and the run
  continues.

## 7. Lifecycle

Each weekly run reconciles against the previous `forward_calendar.csv` rather
than rebuilding from nothing:

| situation | action |
|---|---|
| event still on the published schedule, same date | update `last_verified`, leave the rest |
| event now shows a different date | update `date`, set `status=rescheduled`, record the old date in `notes` |
| event has dropped off the published schedule | set `status=cancelled`, keep the row, record when it vanished |
| event date has passed | set `status=occurred`, leave `actual` blank |
| source unreachable this run | leave the row untouched, leave `last_verified` stale, log it |
| new event appears on the schedule | new row, `status=scheduled` |
| candidate row collides with a historic `calendar.csv` row | do not emit, the historic file wins |

A stale `last_verified` is information, not an error. Surface it, do not paper
over it by refetching from somewhere else.

## 8. Constraints to state in the output

Do not hide these behind a clean summary.

- **US macro is likely absent.** The BLS schedule pages 403 and decision 3
  rules out the keyed API. Unless BLS v1 works, US CPI and payrolls dates will
  not be in the file.
- **Euro area HICP is likely absent.** The Eurostat portlet yields no dated
  links to a plain fetcher and the keyed route is out.
- **IEA is likely absent.** `iea.org` blocks outright.
- **Physical supply schedules are absent by design**, see section 2.
- **The historic file has zero electricity scoped rows.** The scanner should
  materially improve that through Capacity Market auctions, CfD rounds, ETS
  auctions and network charging dates. If `fuel_scope=electricity` is still at
  or near zero after a run, that is a finding, report it.

## 9. Tests

- Unit tests on the parsers, one per source, against a saved fixture of the
  page so the suite runs offline.
- Lifecycle tests covering every row in the section 7 table.
- Validators as the historic run used: schema and column order, ISO dates,
  category and fuel_scope enums, 60 character titles, no em or en dashes, blank
  `consensus` and `actual`, no duplicate date plus title, no collision with the
  historic file, `date_source` set on every row, horizon not exceeded.
- **Mutation test the validators and the lifecycle logic.** Deliberately break
  the date bound, the title length rule, the dash rule and at least two
  lifecycle transitions. Confirm each check fails. Report the result. A
  validator that has never failed has not been tested.

## 10. Deliverables

- `scanner/` the code
- `registry.yaml` or equivalent, every source with its route, its verdict and
  the date it was last checked
- `forward_calendar.csv` from a first live run
- `scan_log.jsonl` every fetch attempt with status
- `tests/` with the fixtures
- `RUN_REPORT.md` leading with what is unresolved, absent or stale, the
  mutation test result, and the electricity scope count. Written straight. Do
  not tidy the failures out of it.
- a one line scheduler command for the weekly and the daily run

## 11. Reference material in this folder

- `reference/calendar.csv` the finished historic file, 59 rows. Dedupe against
  it. Match its column order and house style exactly.
- `reference/coverage.md` the historic run report. Section 5 of this brief is
  drawn from it. Read it before building the registry.
