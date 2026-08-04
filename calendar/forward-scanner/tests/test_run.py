"""End to end tests of the screening and the run wiring, offline."""

import datetime as dt
import unittest

from support import context, fixture

from scanner import registry as registry_module
from scanner import run as run_module
from scanner.fetch import StubFetcher
from scanner.parsers import boe, ecb, ons
from scanner.rows import make_row

BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"


def a_row(date, title, url=BOE_URL):
    return make_row(
        date=date,
        region="UK",
        category="rates",
        title=title,
        detail="A decision.",
        energy_relevance="It moves the curve.",
        fuel_scope="both",
        source_url=url,
        cadence="eight a year",
    )


class TestScreen(unittest.TestCase):
    def setUp(self):
        self.ctx = context(dt.date(2026, 8, 10))

    def screen(self, rows, historic=()):
        return run_module.screen(rows, self.ctx, set(historic))

    def test_a_past_date_is_dropped(self):
        kept, dropped = self.screen([a_row("2026-08-09", "Old thing")])
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "dated before the run date")

    def test_a_row_beyond_the_horizon_is_dropped(self):
        kept, dropped = self.screen([a_row("2028-03-01", "Far thing")])
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "beyond the 18 month horizon")

    def test_the_run_date_itself_is_kept(self):
        kept, _ = self.screen([a_row("2026-08-10", "Today thing")])
        self.assertEqual(len(kept), 1)

    def test_an_over_long_title_is_dropped_rather_than_written(self):
        kept, dropped = self.screen([a_row("2026-09-01", "T" * 61)])
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "title over 60 characters")

    def test_a_historic_collision_is_dropped(self):
        historic = {("2026-09-01", "known thing")}
        kept, dropped = self.screen([a_row("2026-09-01", "Known thing")], historic)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "collides with a historic calendar row")

    def test_a_duplicate_title_within_a_run_is_dropped_once(self):
        rows = [a_row("2026-09-01", "Same thing"), a_row("2026-09-08", "Same thing")]
        kept, dropped = self.screen(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped[0]["reason"], "duplicate title within this run")


class TestGather(unittest.TestCase):
    def setUp(self):
        self.ctx = context()
        self.registry = {
            "sources": [
                {"id": "boe_mpc", "verdict": "resolved", "url": boe.URL, "url_prefixes": [boe.URL]},
                {"id": "ecb_gc", "verdict": "resolved", "url": ecb.URL, "url_prefixes": [ecb.URL]},
            ]
        }

    def test_a_blocked_source_does_not_stop_the_run(self):
        stub = StubFetcher({boe.URL: 403, ecb.URL: fixture("ecb_gc.html")})
        rows, statuses = run_module.gather(stub, self.ctx, self.registry, None)
        self.assertEqual(statuses["boe_mpc"], 403)
        self.assertEqual(statuses["ecb_gc"], 200)
        self.assertTrue(rows)
        self.assertTrue(all(row["_source_id"] == "ecb_gc" for row in rows))

    def test_a_parser_fault_is_recorded_and_the_run_continues(self):
        class Exploding(object):
            SOURCE = {"id": "boe_mpc"}

            @staticmethod
            def collect(fetcher, ctx):
                raise ValueError("bang")

        original = run_module.BY_ID["boe_mpc"]
        run_module.BY_ID["boe_mpc"] = Exploding
        try:
            stub = StubFetcher({ecb.URL: fixture("ecb_gc.html")})
            rows, statuses = run_module.gather(stub, self.ctx, self.registry, None)
        finally:
            run_module.BY_ID["boe_mpc"] = original
        self.assertIn("parser error", statuses["boe_mpc"])
        self.assertTrue(rows)


class TestUnreachable(unittest.TestCase):
    registry = {
        "sources": [
            {"id": "boe_mpc", "verdict": "resolved"},
            {"id": "ecb_gc", "verdict": "resolved"},
            {"id": "iea_reports", "verdict": "unresolved"},
        ]
    }

    def test_a_source_that_answered_with_rows_is_reachable(self):
        statuses = {"boe_mpc": 200, "ecb_gc": 200}
        candidates = [{"_source_id": "boe_mpc"}, {"_source_id": "ecb_gc"}]
        result = run_module.unreachable_sources(
            self.registry, statuses, candidates, {}, None
        )
        self.assertEqual(result, set())

    def test_a_non_200_is_unreachable(self):
        statuses = {"boe_mpc": 403, "ecb_gc": 200}
        candidates = [{"_source_id": "ecb_gc"}]
        result = run_module.unreachable_sources(
            self.registry, statuses, candidates, {}, None
        )
        self.assertEqual(result, {"boe_mpc"})

    def test_a_200_that_parses_to_nothing_does_not_cancel_the_series(self):
        statuses = {"boe_mpc": 200, "ecb_gc": 200}
        candidates = [{"_source_id": "ecb_gc"}]
        previous = {"boe_mpc": 16}
        result = run_module.unreachable_sources(
            self.registry, statuses, candidates, previous, None
        )
        self.assertEqual(result, {"boe_mpc"})
        self.assertEqual(statuses["boe_mpc"], "200 but parsed to no rows")

    def test_a_new_source_with_no_previous_rows_is_allowed_to_be_empty(self):
        statuses = {"boe_mpc": 200, "ecb_gc": 200}
        candidates = [{"_source_id": "ecb_gc"}]
        result = run_module.unreachable_sources(
            self.registry, statuses, candidates, {}, None
        )
        self.assertEqual(result, set())

    def test_a_daily_run_does_not_judge_sources_it_skipped(self):
        statuses = {"ecb_gc": 200}
        candidates = [{"_source_id": "ecb_gc"}]
        result = run_module.unreachable_sources(
            self.registry, statuses, candidates, {"boe_mpc": 16}, {"ecb_gc"}
        )
        self.assertEqual(result, {"boe_mpc"})


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = registry_module.load()

    def test_every_resolved_source_has_a_parser(self):
        from scanner.parsers import BY_ID

        for entry in registry_module.resolved(self.registry):
            self.assertIn(entry["id"], BY_ID, entry["id"])

    def test_every_parser_is_registered(self):
        from scanner.parsers import SOURCES

        ids = {entry["id"] for entry in self.registry["sources"]}
        for module in SOURCES:
            self.assertIn(module.SOURCE["id"], ids)

    def test_every_source_records_a_verdict_and_a_check_date(self):
        for entry in self.registry["sources"]:
            self.assertIn(entry["verdict"], ("resolved", "unresolved"), entry["id"])
            self.assertTrue(entry.get("last_checked"), entry["id"])

    def test_unresolved_sources_are_never_gathered(self):
        rows, statuses = run_module.gather(
            StubFetcher({}), context(), self.registry, None
        )
        for entry in registry_module.unresolved(self.registry):
            self.assertNotIn(entry["id"], statuses, entry["id"])

    def test_registry_urls_are_https_or_absent(self):
        for entry in self.registry["sources"]:
            url = entry.get("url")
            if url:
                self.assertTrue(url.startswith("https://"), entry["id"])


class TestOnsPaging(unittest.TestCase):
    def test_paging_stops_once_a_page_is_past_the_horizon(self):
        ctx = context(dt.date(2026, 7, 31), months=0)
        stub = StubFetcher({ons.CALENDAR % 1: fixture("ons_calendar.html")})
        rows, status = ons.collect(stub, ctx)
        self.assertEqual(status, 200)
        self.assertEqual(len(stub.attempts), 1)

    def test_paging_stops_on_a_missing_page(self):
        ctx = context()
        stub = StubFetcher({ons.CALENDAR % 1: fixture("ons_calendar.html")})
        rows, status = ons.collect(stub, ctx)
        self.assertEqual(status, 404)
        self.assertEqual(len(stub.attempts), 2)


if __name__ == "__main__":
    unittest.main()
