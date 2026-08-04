# PES forward scanner: build and first run report

Written straight. What is unresolved, absent or thin comes first.

Run date 2026-07-31. Horizon 2028-01-31. `output/forward_calendar.csv` holds
**244 rows** from **10 resolved sources**. Validators: **0 failures**.

## 1. What is absent, and why

**25 of the 35 sources in the registry are unresolved.** Every one is recorded in
`registry.json` with the route tried, the observed status and the date checked.
None was worked around.

| absent | reason | expected by section 8 |
|---|---|---|
| IEA Oil Market Report and Gas Market Report | `iea.org` returns 403 | yes |
| Eurostat flash HICP and GDP | portlet yields no dated links to a plain fetcher | yes |
| Physical supply schedules | held back to phase two by section 2 | yes |
| OPEC monthly report, ministerials, JMMC | `opec.org` 403s on every schedule path | no |
| Ofgem price cap and network charging | `ofgem.gov.uk` is now a JavaScript shell | **no, this is a regression** |
| Capacity Market T-1 and T-4 auctions | every NESO path returns a soft 404 | no |
| CfD allocation round milestones | gov.uk carries publication dates, not milestones | no |
| UK ETS and EU ETS auction calendars | dates live inside PDFs, not in the HTML | no |
| EU Energy Council and European Council | `consilium.europa.eu` returns 403 | no |
| EU sectoral sanctions renewals | no forward renewal calendar is published | no |
| Budget and Spring Statement | the date arrives as a statement, not a schedule | no |
| GIE AGSI storage and EU filling targets | JavaScript shell, no forward target dates | yes for AGSI |
| Baker Hughes rig count | `rigcount.bakerhughes.com` times out | no |
| PMIs, Ifo, ZEW | blocklisted publisher, shells and timeouts | no |
| Scheduled elections and referendums | no forward timetable in dated form | no |
| COP, G7, G20 | `unfccc.int` returns a few hundred bytes, `g20.org` has no dated entry | no |
| ICE contract expiries and prompt rolls | expiry calendar is not in the markup | no |
| Gas year start and the seasonal roll | convention, no published schedule page | no |
| ECMWF, Copernicus, Met Office, NOAA outlooks | past issues published, no forward release calendar | no |

### Two recoveries against section 8

**Euro area rates are in.** The historic run recorded the ECB as unresolved
because the decisions index and the per year press release index render via
JavaScript. The **Governing Council meeting calendar** is a different page and
is plain HTML. It gives 11 forward ECB decision dates out to March 2028.

**US macro is in, conditionally.** Section 8 predicted US CPI and payrolls
would be absent. The brief asked for BLS API v1 to be tested. It was:
**v1 is open without a key but serves series observations, not release dates**,
so it does not recover the calendar. What does work is the iCalendar file the
BLS publishes at `bls.gov/schedule/news_release/bls.ics`. It is served as
`text/calendar` at 200 from the same host whose HTML schedule pages return 403
and 404, and it carries every release with a US Eastern timestamp.

**Read this as fragile, not fixed.** That URL returned 403 on one of four test
fetches. The block is applied inconsistently. On a run where it fails the BLS
rows are left untouched with a stale `last_verified`, which is the section 7
behaviour, not an error. If the block hardens, US macro goes back to absent
and nothing else in the file is affected.

### One regression against the historic run

**`ofgem.gov.uk` no longer walks cleanly.** Section 5 lists it as known good,
drawn from `reference/coverage.md`. It is not any more. The price cap page and
the publications index both return 200 with about 190 kB of markup that strips
to roughly 7 kB of navigation and a "This site is currently in BETA" banner.
There is no body content and no dated entry. Both the price cap announcements
and the annual network charging decisions are unresolved as a result.

## 2. The electricity finding, as section 8 asks

**`fuel_scope=electricity` is 0 of 244 rows.** Section 8 says that if it is at
or near zero after a run, that is a finding. It is, and here it is.

The four routes named as the fix are all unresolved: Capacity Market auctions,
CfD allocation rounds, UK and EU ETS auction calendars, and network charging
decisions. Three of them fail for the same underlying reason, which is that
the bodies publish their forward dates in a PDF or behind a JavaScript
front end rather than as dated HTML.

88 rows are `fuel_scope=both` and do carry a power channel, so the file is not
silent on electricity. But nothing in it is electricity specific, and the
historic file's gap is not yet closed. **This is the single highest value
thing to fix next**, and it is a sourcing problem rather than a code problem:
each of the four needs a route that a plain fetcher can read, most likely a
PDF reader for the two auction calendars.

## 2b. Added after this run: end to end coverage

This report describes the first live run. Since then `tests/test_endtoend.py`
was added: eight tests driving the whole pipeline twice against the saved
fixtures, asserting the second pass is a no-op. `qa/mutate_endtoend.py` at the
bundle root proves those tests fail when `lifecycle.py` is deliberately broken.

## 3. Mutation test result

22 mutations injected, **22 caught, 0 missed**. 16 damage a clean row set and
run the validators over it. 1 damages the header. 5 recompile
`scanner/lifecycle.py` with a single transition changed and run the lifecycle
expectations against the mutant, which must then fail.

Reproduce with `python tests/test_mutations.py`.

| mutation injected | check fired | message raised |
|---|---|---|
| date bound: push a row past the 18 month horizon | yes | `date 2028-06-01 is beyond the horizon 2028-02-10` |
| title length: set a title to 61 characters | yes | `title is 61 characters, over 60` |
| dash rule: insert U+2014 into detail | yes | `detail contains a dash character U+2014` |
| dash rule: insert U+2013 into notes | yes | `notes contains a dash character U+2013` |
| consensus rule: set consensus to 2.5 | yes | `consensus is not blank ('2.5')` |
| actual rule: set actual on a forward row | yes | `actual is not blank ('3.75')` |
| category enum: set category to weather | yes | `category 'weather' not in enum` |
| fuel_scope enum: set fuel_scope to coal | yes | `fuel_scope 'coal' not in enum` |
| status enum: set status to pending | yes | `status 'pending' not in enum` |
| ISO date rule: set a date to 17/09/2026 | yes | `date '17/09/2026' is not an ISO 8601 date` |
| time rule: set a time to 9am | yes | `time '9am' is not HH:MM` |
| duplicate rule: append a copy of row one | yes | `duplicate date plus title` |
| date_source rule: blank date_source | yes | `date_source '' not set to published or generated` |
| last_verified rule: blank last_verified | yes | `last_verified is blank` |
| source_url rule: point a row at an http URL | yes | `source_url ... is not an https URL` |
| recurring rule: set recurring to maybe | yes | `recurring 'maybe' is not yes or no` |
| schema: drop date_source from the header | yes | `schema: header is not the 18 columns in order` |
| lifecycle: a date change no longer sets status=rescheduled | yes | `status was 'scheduled'` |
| lifecycle: an event dropping off the schedule is not cancelled | yes | `status was 'scheduled'` |
| lifecycle: a passed date is not flipped to occurred | yes | `status was 'scheduled'` |
| lifecycle: an unreachable source no longer leaves the row alone | yes | `last_verified was '2026-08-10'` |
| lifecycle: a historic collision is emitted instead of dropped | yes | `a colliding row was emitted` |

Full suite: **71 tests, all passing, all offline against saved fixtures.**

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## 4. Generated rows, stated plainly

**151 of 244 rows carry `date_source=generated`.** That is 62 per cent of the
file and it is the least comfortable number in this report, so it goes here
rather than in a footnote.

All 151 are the two EIA weeklies. Both schedule pages state the standard day
and time in prose, then publish **only the holiday exceptions** as dates. So
the choice was to write about a dozen exception dates a year and leave the two
most watched weekly energy prints out of the calendar, or to generate the
ordinary weeks from the cadence sentence on the same fetched page and flag
every one of them. Decision 2 allows generation as a visible fallback, so the
second was taken.

Every generated row says so in `notes` as well as in `date_source`, and the
exception weeks are published rows that override the generated ones. If the
EIA moves a release for a reason other than a listed holiday, the generated
row will be wrong until the exception appears on the page. That is the honest
cost of the choice.

The remaining 93 rows are `published`, including all 38 rates rows, all 24 ONS
and BLS statistical rows, all 22 COT dates and both EIA holiday tables.

## 5. What is thin

- **ONS gives 14 rows.** The upcoming filter runs about ten weeks
  ahead, not eighteen months, so CPI, labour market and GDP fill in week by
  week rather than arriving as a block. Expect this series to stay short and
  to refresh forward on every run.
- **BLS gives 10 rows.** The published iCalendar covers roughly a year, and
  only five CPI and five payroll releases sit inside it after the run date.
- **STEO gives one row.** The outlook page publishes only its next release
  date. There is no forward schedule to harvest.
- **CFTC gives 22 rows.** The page publishes one calendar year at a time and
  the run is in August, so only the rest of 2026 is available. It should jump
  to a full year when the 2027 schedule is posted.
- **The file is US weighted.** 200 rows US, 33 UK, 11 EU. That is entirely the
  two EIA weeklies. Strip them out and it is 44 US, 33 UK, 11 EU, which is a
  fairer picture of the coverage.
- **`previous` is blank on every row.** Every resolved source is a schedule
  page. None of them carries a prior value, so filling the column would mean
  fetching outturns, which decision 6 forbids.
- **`time` is blank on 42 rows.** 38 of them are the rates rows: neither the
  Bank, the ECB nor the Fed states an announcement time on its calendar page,
  and assuming one is worse than leaving it blank. The other four are the
  three clock changes and the STEO row, where no time is published either.
  The remaining 202 rows carry a real published time converted to UTC.

## 6. Design decisions taken under the no questions rule

Recorded because each is a judgement a reader may want to overturn.

1. **`registry.json`, not `registry.yaml`.** The brief allows an equivalent. A
   YAML reader is not in the standard library and section 1 caps the
   dependencies at requests.

2. **Row identity is the normalised title.** Section 7 needs to tell a
   reschedule from a new event, which needs an identity that survives a date
   change, and the schema has no spare column to hold a key. So every parser
   puts an invariant reference into the title: the meeting month for a policy
   decision, the reference period for a bulletin, the ISO week for a weekly
   release. A validator enforces that no two rows share a title.

3. **CFTC rows are titled by release date, not by ISO week.** A holiday can put
   two COT releases in one ISO week, for example 16 and 20 November 2026, and a
   week based identity silently dropped one of them in the first run. The cost
   is that a moved COT release reads as a cancellation plus a new row rather
   than as a reschedule.

4. **A source that answers 200 and parses to nothing is treated as
   unreachable.** Section 7 says an event that drops off the schedule is
   cancelled. Applied literally, one layout change would cancel a whole
   series in a single run. So a source that previously had rows and now
   produces none is treated as unreachable: the rows survive untouched and the
   summary says `200 but parsed to no rows`.

5. **A cancelled row that reappears is reinstated.** Section 7 does not cover
   this case. Leaving a row marked cancelled when the body has put it back on
   the schedule would be wrong, so it goes back to `scheduled` with a dated
   note.

6. **A cancelled row whose date passes stays cancelled.** It never happened, so
   flipping it to `occurred` would assert something false.

7. **Occurred rows are kept in the file indefinitely.** Section 7 says flip the
   status and stop. Nothing says to delete them, so they accumulate. If the
   terminal would rather they aged out, that is a one line change in
   `lifecycle.py` and a decision for the display side.

8. **Timezone conversion is done from first principles.** UK and US Eastern
   rules are implemented in `scanner/dates.py` rather than read from a
   timezone database, because `tzdata` is not guaranteed on a Windows
   scheduler host and section 1 caps the dependencies.

9. **STEO and COT are categorised `other`.** Neither is an inventory print, a
   rate decision or a macro statistic. `other` is the honest bucket.

10. **Oil linked rows carry `fuel_scope=gas`.** This follows the historic run's
    decision 4, that oil events are scoped by their channel into the gas
    market rather than by the molecule. It is why the EIA petroleum status
    rows are `gas` and not something else.

11. **Clock changes are taken as published, not generated.** The rule is in
    statute and could be generated, but gov.uk publishes a dated table, so it
    goes through the normal fetch gate.

12. **Unresolved sources are re-probed weekly.** Section 5 says to record a
    verdict with the date checked. Re-probing keeps `last_checked` current and
    would surface Ofgem coming back. `last_status` is the raw observed status
    and does not imply usable content: several blocked sites answer 200 with
    an interstitial. Only `verdict` decides whether a source is used, and it
    is changed by hand.

## 7. First run statistics

- 51 fetch attempts logged, 47 returned 200.
- Failures: 2 x 403 (`iea.org`, `opec.org`), 1 x 404 (`neso.energy`), 1
  timeout (`rigcount.bakerhughes.com`).
- All 10 resolved sources answered 200.
- 133 candidate rows were built and then dropped: 123 dated before the run
  date, 10 beyond the 18 month horizon. None was dropped for a title length,
  a duplicate or a collision with the historic file.
- 0 collisions with `reference/calendar.csv`, which is 59 rows ending on
  2026-07-23. The check is implemented and tested rather than assumed.
- A second identical run produced 244 unchanged, 0 new, 0 cancelled and a byte
  identical file, so the reconciliation is idempotent.
- A daily run checked the 6 sources with an event inside 14 days, left the
  other 4 alone and left 41 rows untouched.

## 8. Files

- `scanner/` the code. `run.py` is the entry point, `parsers/` is one module
  per source, `lifecycle.py` is section 7, `validate.py` is section 9.
- `registry.json` every source with its route, its verdict and the date it was
  last checked.
- `output/forward_calendar.csv` 244 rows from the first live run.
- `output/scan_log.jsonl` every fetch attempt with the observed status.
- `tests/` 71 tests and 10 saved page fixtures, all offline.
- `RUN_REPORT.md` this file.

## 9. Scheduler

Weekly full refresh, Sundays at 06:00 UTC:

```bash
cd /c/Users/alexb/Downloads/pes-forward-scanner/pes-forward-scanner && python -m scanner.run --mode weekly >> output/run.log 2>&1
```

Daily 14 day check, 05:00 UTC:

```bash
cd /c/Users/alexb/Downloads/pes-forward-scanner/pes-forward-scanner && python -m scanner.run --mode daily >> output/run.log 2>&1
```

On Windows Task Scheduler the same two commands run as
`python.exe -m scanner.run --mode weekly` with the start-in directory set to
the project root. The process exits 0 when the validators pass and 1 when they
do not, so the scheduler can alert on a non zero exit. It never prompts and
never waits for input.
