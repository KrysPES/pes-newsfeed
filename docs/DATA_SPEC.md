# DATA_SPEC: news.json

The contract between the ingestion job and the terminal widget. This file is
the entire API. If you change the shape of it, change this document.

Served as a static asset. The widget fetches it once a minute with
`cache: "no-store"`.

---

## Top level

```jsonc
{
  "generated_at": "2026-07-23T12:04:11.882Z",   // ISO 8601 UTC, when the job ran
  "item_count": 18,
  "alert_counts": { "critical": 4, "high": 3, "normal": 10 },  // visible items only
  "superseded_count": 2,                         // retired by a later update
  "sources": {
    "healthy": 9,
    "total": 11,
    "degraded": true,                            // true when healthy < total
    "detail": [
      { "id": "ofgem", "ok": true,  "count": 12, "error": null, "ms": 380 },
      { "id": "gie_agsi", "ok": false, "count": 0, "error": "RuntimeError: AGSI_KEY not set", "ms": 2 }
    ]
  },
  "items": [ /* see below, sorted by score descending */ ]
}
```

`generated_at` drives the freshness dot in the widget header, using the same
rule as the terminal's LAST SYNC stamp: green within the hour, red beyond it.

`sources.degraded` is the signal that the feed is running on partial input.
Surface it. A quiet feed because three sources died looks exactly like a quiet
news day, and that is the failure mode that will catch someone out.

---

## Item

```jsonc
{
  "title": "Unplanned outage at Kollsnes processing plant cuts 18 mcm/day",
  "url": "https://...",                    // the source article, opened on click
  "snippet": "Gassco said an unplanned outage has reduced capacity by...",
  "published_at": "2026-07-23T09:12:00+00:00",
  "source": "nordpool_umm",                // stable id, matches sources.json
  "source_name": "Nord Pool REMIT UMM",    // display name
  "tier": 1,                               // 1 operational, 2 trade press, 3 broad
  "authority": 30,                         // raw source trust, pre-scoring
  "type": "outage",                        // outage | storage | regulation | news

  "score": 87,                             // 0-100
  "alert": "critical",                     // critical | high | normal | low
  "nature": "unplanned",                   // unplanned | planned | ""
  "tags": ["supply_disruption", "infrastructure"],

  "duplicate_count": 2,                    // other outlets that ran this story
  "also_reported_by": ["LNG Prime", "Energy Voice"],
  "first_seen_at": "2026-07-23T09:12:00+00:00",  // earliest sighting across the cluster

  "alert_capped": false,                   // true if demoted by the rate limiter

  // --- developing story fields ---
  "update_count": 2,                       // earlier versions this item retired
  "thread_started_at": "2026-07-22T16:40:00+00:00",
  "superseded": false,                     // true once a later update replaces it
  "hidden": false,                         // superseded items: do not render by default
  "superseded_by": null,                   // {url, title, published_at} when superseded

  "why": {                                 // score breakdown, shown on row click
    "authority": 20.4,
    "themes": 44.4,
    "geography": 16,
    "geo_band": "primary",
    "event_nature": 20,
    "urgency": 16,
    "magnitude": 12,
    "speculative": 0,
    "raw": 128.8,
    "recency_multiplier": 1.0
  },

  "matched": {                             // which terms fired, for debugging
    "supply_disruption": ["outage", "unplanned outage"],
    "geography": ["kollsnes", "easington"],
    "unplanned": ["unplanned"]
  }
}
```

### Field notes

**`alert`** is the only field the UI needs for urgency. Do not re-derive
urgency from `score` in the front end; the banding rules include the planned
and rate-limit logic and will drift if reimplemented.

**`alert` values and what the UI should do:**

| Value      | Meaning                                    | UI treatment                        |
|------------|--------------------------------------------|-------------------------------------|
| `critical` | Drop what you are doing                    | Red left border, drawer flashes red |
| `high`     | Worth reading now                          | Amber left border                   |
| `normal`   | Background, read when convenient           | Neutral border                      |
| `low`      | Retained but below the display threshold   | Hidden by default                   |

**`nature`** is the planned versus unplanned read. Show it. On a trading desk
the difference between "Kollsnes down, planned" and "Kollsnes down, unplanned"
is the whole story, and a headline does not always make it obvious.

**`duplicate_count`** drives the "+2 sources" badge. It is a corroboration
signal, not clutter: three outlets running the same story inside an hour means
something is moving.

**`why` and `matched`** exist so anyone can interrogate a ranking. Keep them
reachable in the UI. The moment the desk stops trusting the ordering, the
widget is dead, and "why is this at the top" needs an answer in one click.

**`published_at`** may be `null` if a source gives no timestamp. Handle it.
The scorer applies a mild discount rather than dropping the item.

---

## Guarantees

- `items` is always sorted by `score` descending.
- Every item has `title`, `url`, `score`, `alert` and `tags`.
- Items scoring below 30 are dropped at ingestion and never appear.
- Superseded items are demoted and flagged `hidden`, never deleted. The UI must
  filter on `hidden`, not assume the list is display-ready.
- Retention is 14 days or 1,200 items, whichever bites first.
- The file is written atomically by the job. A partial read is not possible.
- If every source fails, the job still writes a valid file with an empty
  `items` array and `degraded: true`. It never writes malformed JSON.

## Not guaranteed

- Item ordering is not stable between runs. Scores shift as items age, so a
  row can move down the list without any new content arriving. Key the UI on
  `url`, not on array index.
- Feed strings (title, snippet, source names) are NOT guaranteed HTML-safe.
  The reference widget escapes everything before insertion and refuses
  non-http(s) hrefs; any reimplementation must do the same.
- `url` IS unique per event and stable across runs. Operational adapters
  (ENTSO-E, Elexon, AGSI) append a stable `?event=` query because their
  platforms use one landing page for everything, and deduplication keys on
  canonical URL. The widget's read-state persistence also keys on `url`, so
  keep it stable if you touch an adapter.


---

## Developing stories

Two separate mechanisms, often confused:

**Deduplication** collapses simultaneous reports of one event, within a 12 hour
window. Twelve outlets running the same Kollsnes outage become one row with a
"+11 sources" badge.

**Supersession** retires earlier versions of a story that has moved on, within
a 5 day window. Monday's outage, Tuesday's extension and Wednesday's fix become
one visible row: the fix, badged "updated", with `update_count: 2` and
`thread_started_at` pointing at Monday.

The UI should:

- **Filter out `hidden` items by default.** They are history.
- **Offer a way to see them.** The reference widget has a "show N superseded"
  toggle in the footer. Someone asking "when did this start" needs the trail.
- **Show the `updated` badge** when `update_count` is set. A story that is
  still developing reads differently from one that broke and stopped.

One rule matters more than the rest: **a resolution is never merged into the
outage it resolves.** "Kollsnes back to full capacity" and "Kollsnes outage"
stay separate items with a supersession link between them. Merging them would
hide the fact that it is fixed, which is the worst thing this feed could do.
