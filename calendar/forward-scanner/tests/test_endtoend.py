"""End to end pipeline tests, offline, against the saved fixtures.

The gap these close: every other suite tests a stage. Nothing ran the whole
pipeline twice and checked the second run is a no-op. A scanner that quietly
appends instead of reconciling would double the file every week and no unit
test would notice.

    python -m unittest discover -s tests -p "test_*.py"
"""
import datetime as dt
import json
import unittest

from support import context, fixture

from scanner import lifecycle, registry as registry_module, run as run_module, validate
from scanner.fetch import StubFetcher

RUN_DATE = dt.date(2026, 8, 10)


def pages_for(registry):
    """Serve each resolved source its saved fixture, by URL.

    Fixture filenames match the registry ids, so the map is derived rather
    than hand written and cannot drift out of step with the registry.
    """
    pages = {}
    for source in registry_module.resolved(registry):
        url = source.get("url")
        if not url:
            continue
        for ext in (".html", ".ics"):
            try:
                pages[url] = fixture(source["id"] + ext)
                break
            except Exception:
                continue
    return pages


def add_paged_fixtures(pages, fetcher):
    """Map any follow-on page the parsers asked for and we have a fixture for.

    The ONS calendar paginates; the parser walks to page two. Without this the
    stub 404s that request and the ONS series comes out short.
    """
    added = 0
    for attempt in fetcher.attempts:
        url = attempt["url"]
        if url in pages:
            continue
        for name in ("ons_calendar_page2.html",):
            if "ons.gov.uk" in url and "page=2" in url.replace("&", "&"):
                pages[url] = fixture(name)
                added += 1
                break
    return added


class Pipeline(unittest.TestCase):
    """gather -> screen -> reconcile, driven by StubFetcher."""

    def setUp(self):
        self.ctx = context(RUN_DATE)
        self.registry = registry_module.load()
        self.pages = pages_for(self.registry)
        if not self.pages:
            self.skipTest("no fixture URLs matched the registry")

    def cycle(self, previous, run_date=RUN_DATE, historic=frozenset()):
        """One full pass. Returns the written rows and the action tally."""
        ctx = context(run_date)
        fetcher = StubFetcher(self.pages)
        candidates, statuses = run_module.gather(fetcher, ctx, self.registry, None)
        if add_paged_fixtures(self.pages, fetcher):
            fetcher = StubFetcher(self.pages)
            candidates, statuses = run_module.gather(fetcher, ctx, self.registry, None)
        candidates, _dropped = run_module.screen(candidates, ctx, set(historic))

        previous_by_source = {}
        for row in previous:
            source = lifecycle.source_id_of(row, self.registry)
            previous_by_source[source] = previous_by_source.get(source, 0) + 1

        unreachable = run_module.unreachable_sources(
            self.registry, statuses, candidates, previous_by_source, None
        )
        for row in candidates:
            row.pop("_source_id", None)
        return lifecycle.reconcile(
            previous, candidates, run_date, unreachable, self.registry, set(historic)
        )

    # ---- the check that was missing -------------------------------------

    def test_second_identical_run_is_a_no_op(self):
        first, _ = self.cycle([])
        self.assertTrue(first, "the first pass produced no rows at all")
        second, actions = self.cycle(first)

        self.assertEqual(len(second), len(first),
                         "row count moved on an unchanged rerun: appending, not reconciling")
        self.assertEqual([r["date"] for r in second], [r["date"] for r in first])
        self.assertEqual([r["title"] for r in second], [r["title"] for r in first])
        self.assertEqual(actions.get("added", 0), 0, "an unchanged rerun added rows")
        self.assertEqual(actions.get("rescheduled", 0), 0)
        self.assertEqual(actions.get("cancelled", 0), 0)

    def test_a_third_run_is_also_stable(self):
        rows = []
        counts = []
        for _ in range(3):
            rows, _ = self.cycle(rows)
            counts.append(len(rows))
        self.assertEqual(counts[1], counts[2], "row count still drifting by the third run")

    def test_rerun_only_moves_last_verified(self):
        first, _ = self.cycle([])
        later = RUN_DATE + dt.timedelta(days=7)
        second, _ = self.cycle(first, run_date=later)
        by_key = {(r["date"], r["title"]): r for r in first}
        moved = 0
        for row in second:
            before = by_key.get((row["date"], row["title"]))
            if before is None:
                continue
            for field in ("region", "category", "detail", "fuel_scope",
                          "source_url", "cadence", "date_source"):
                self.assertEqual(row[field], before[field],
                                 "%s changed on a rerun for %r" % (field, row["title"]))
            if row["status"] != "scheduled":
                continue          # an occurred or cancelled row is not re-verified
            self.assertEqual(
                row["last_verified"], later.isoformat(),
                "%r kept a stale last_verified though its source was reachable"
                % row["title"])
            moved += 1
        self.assertTrue(moved, "no rows matched between the two runs at all")

    def test_pipeline_output_passes_the_validators(self):
        rows, _ = self.cycle([])
        failures = validate.check_rows(rows, RUN_DATE, self.ctx["horizon_end"], set())
        self.assertEqual(failures, [], "pipeline output fails its own validators")

    def test_no_duplicate_titles_out_of_the_pipeline(self):
        rows, _ = self.cycle([])
        titles = [r["title"] for r in rows]
        self.assertEqual(len(titles), len(set(titles)))

    def test_rows_are_inside_the_horizon(self):
        rows, _ = self.cycle([])
        for row in rows:
            self.assertGreaterEqual(row["date"], RUN_DATE.isoformat(), row["title"])
            self.assertLessEqual(row["date"], self.ctx["horizon_end"].isoformat(), row["title"])

    def test_a_historic_collision_never_reaches_the_output(self):
        rows, _ = self.cycle([])
        # historic keys are (date, lowercased title), see csvio.historic_keys
        victim = (rows[0]["date"], rows[0]["title"].lower())
        again, _ = self.cycle([], historic={victim})
        emitted = {(r["date"], r["title"].lower()) for r in again}
        self.assertNotIn(victim, emitted)
        self.assertEqual(len(again), len(rows) - 1)

    def test_a_dead_source_does_not_wipe_its_rows(self):
        first, _ = self.cycle([])
        self.assertTrue(first)
        # every source now 404s, exactly as a site going dark would look
        fetcher = StubFetcher({})
        ctx = context(RUN_DATE)
        candidates, statuses = run_module.gather(fetcher, ctx, self.registry, None)
        candidates, _ = run_module.screen(candidates, ctx, set())
        previous_by_source = {}
        for row in first:
            source = lifecycle.source_id_of(row, self.registry)
            previous_by_source[source] = previous_by_source.get(source, 0) + 1
        unreachable = run_module.unreachable_sources(
            self.registry, statuses, candidates, previous_by_source, None
        )
        rows, actions = lifecycle.reconcile(
            first, candidates, RUN_DATE, unreachable, self.registry, set()
        )
        self.assertEqual(len(rows), len(first),
                         "rows were lost when every source went dark")
        self.assertEqual(actions.get("cancelled", 0), 0,
                         "an unreachable source cancelled its rows instead of holding them")


if __name__ == "__main__":
    unittest.main(verbosity=2)
