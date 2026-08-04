# DATA_SPEC: the calendar data contract

Read this before wiring the pane to live data.

## Three files

| File | Rows | Regenerated |
|---|---|---|
| `data/calendar.csv` | 59 | **Never.** Fixed historic research |
| `data/forward_calendar.csv` | 244 | Weekly, by the scanner |
| `data/events.json` | 303 | By `build_data.py` from the two above |

## calendar.csv, 15 columns

`date, time, region, category, title, detail, energy_relevance, fuel_scope,
previous, consensus, actual, recurring, cadence, source_url, notes`

## forward_calendar.csv, the same 15 plus 3

`status, last_verified, date_source`

- `status` is `scheduled`, `rescheduled`, `cancelled` or `occurred`
- `last_verified` is the ISO date the source was last fetched successfully.
  A stale value is information, not an error
- `date_source` is `published` or `generated`. Generated means the date came
  from a cadence rule on the fetched page rather than a published date

## Invariants, all enforced by `tests/test_package.py`

- `date` is ISO 8601. `time` is HH:MM in UTC or blank
- `category` is one of rates, inflation, employment, growth, election, policy,
  regulation, geopolitics, sanctions, supply, inventory, other
- `fuel_scope` is gas, electricity or both
- `title` is 60 characters or fewer
- `consensus` is blank on every row, in both files
- `actual` is blank on every forward row
- every row has an https `source_url`
- no em dashes or en dashes anywhere
- historic rows are all dated before 2026-07-31
- historic and forward never collide on date plus title

## events.json, what the pane reads

An array sorted by date, then time, then title. Keys are short to keep the
baked in payload small.

| key | column |
|---|---|
| `d` | date |
| `t` | time |
| `rg` | region |
| `c` | category |
| `ti` | title |
| `de` | detail |
| `er` | energy_relevance |
| `f` | fuel_scope |
| `u` | source_url |
| `cd` | cadence |
| `n` | notes |
| `st` | status, `occurred` for all historic rows |
| `src` | `historic` or `forward` |

`previous`, `actual`, `recurring`, `last_verified` and `date_source` are not
carried into the feed. They are audit fields, not display fields. Add them if
the pane ever needs them.

## Region values

Ten appear in the data: US, UK, EU, Russia, Australia, Global, Germany, Qatar,
Middle East, Saudi Arabia.

Eight have a flag in `src/flags.svg`. **Global and Middle East do not**, and
fall back to the text chip. If the scanner ever emits a new region, it will
fall back the same way rather than break. Adding a flag means adding a
`<symbol>` and one line to the `FLAG` map in `src/calendar.js`.

## fuel_scope in practice

156 gas, 88 both, **zero electricity** across the forward file, and 34 gas,
25 both, zero electricity across the historic file. The field is carried but
nothing currently displays it, since the colour coding was removed. See
`docs/SCANNER_RUN_REPORT.md` section 2 for why electricity is empty.
