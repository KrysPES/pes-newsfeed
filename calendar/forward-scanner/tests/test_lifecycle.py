"""One test per row of the section 7 lifecycle table."""

import datetime as dt
import unittest

from support import context  # noqa: F401

from scanner.lifecycle import reconcile, source_id_of
from scanner.rows import make_row

RUN_DATE = dt.date(2026, 8, 10)
TODAY = "2026-08-10"

REGISTRY = {
    "sources": [
        {
            "id": "boe_mpc",
            "verdict": "resolved",
            "url": "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
            "url_prefixes": [
                "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"
            ],
        },
        {
            "id": "ons_calendar",
            "verdict": "resolved",
            "url": "https://www.ons.gov.uk/releasecalendar",
            "url_prefixes": ["https://www.ons.gov.uk/releases/"],
        },
    ]
}

BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"


def boe_row(date, title, **kwargs):
    row = make_row(
        date=date,
        region="UK",
        category="rates",
        title=title,
        detail="A decision.",
        energy_relevance="It moves the curve.",
        fuel_scope="both",
        source_url=BOE_URL,
        cadence="eight a year",
        **kwargs
    )
    return row


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.title = "Bank of England MPC decision, September 2026"

    def run_reconcile(self, previous, candidates, unreachable=(), historic=()):
        return reconcile(
            previous,
            candidates,
            RUN_DATE,
            set(unreachable),
            REGISTRY,
            set(historic),
        )

    def test_same_date_updates_last_verified_only(self):
        previous = [
            boe_row(
                dt.date(2026, 9, 17),
                self.title,
                status="scheduled",
                last_verified="2026-08-03",
                notes="Original note.",
            )
        ]
        candidates = [boe_row(dt.date(2026, 9, 17), self.title)]
        rows, actions = self.run_reconcile(previous, candidates)
        self.assertEqual(actions["unchanged"], 1)
        self.assertEqual(rows[0]["last_verified"], TODAY)
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertEqual(rows[0]["notes"], "Original note.")

    def test_a_new_date_is_a_reschedule_and_records_the_old_one(self):
        previous = [
            boe_row(
                dt.date(2026, 9, 17),
                self.title,
                status="scheduled",
                last_verified="2026-08-03",
            )
        ]
        candidates = [boe_row(dt.date(2026, 9, 24), self.title)]
        rows, actions = self.run_reconcile(previous, candidates)
        self.assertEqual(actions["rescheduled"], 1)
        self.assertEqual(rows[0]["date"], "2026-09-24")
        self.assertEqual(rows[0]["status"], "rescheduled")
        self.assertIn("previously dated 2026-09-17", rows[0]["notes"])
        self.assertEqual(rows[0]["last_verified"], TODAY)

    def test_dropping_off_the_schedule_cancels_and_keeps_the_row(self):
        previous = [
            boe_row(
                dt.date(2026, 9, 17),
                self.title,
                status="scheduled",
                last_verified="2026-08-03",
            )
        ]
        rows, actions = self.run_reconcile(previous, [])
        self.assertEqual(actions["cancelled"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "cancelled")
        self.assertIn("seen missing on %s" % TODAY, rows[0]["notes"])

    def test_a_passed_date_becomes_occurred_with_actual_left_blank(self):
        previous = [
            boe_row(
                dt.date(2026, 8, 6),
                "Bank of England MPC decision, August 2026",
                status="scheduled",
                last_verified="2026-08-03",
            )
        ]
        candidates = [
            boe_row(dt.date(2026, 8, 6), "Bank of England MPC decision, August 2026")
        ]
        rows, actions = self.run_reconcile(previous, candidates)
        self.assertEqual(actions["occurred"], 1)
        self.assertEqual(rows[0]["status"], "occurred")
        self.assertEqual(rows[0]["actual"], "")

    def test_an_unreachable_source_leaves_the_row_and_the_stale_date(self):
        previous = [
            boe_row(
                dt.date(2026, 9, 17),
                self.title,
                status="scheduled",
                last_verified="2026-07-20",
            )
        ]
        rows, actions = self.run_reconcile(previous, [], unreachable=["boe_mpc"])
        self.assertEqual(actions["stale"], 1)
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertEqual(rows[0]["last_verified"], "2026-07-20")

    def test_a_new_event_becomes_a_scheduled_row(self):
        candidates = [boe_row(dt.date(2026, 11, 5), "Bank of England MPC decision, November 2026")]
        rows, actions = self.run_reconcile([], candidates)
        self.assertEqual(actions["new"], 1)
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertEqual(rows[0]["last_verified"], TODAY)

    def test_a_collision_with_the_historic_file_is_not_emitted(self):
        candidates = [boe_row(dt.date(2026, 11, 5), "Bank of England MPC decision, November 2026")]
        historic = {("2026-11-05", "bank of england mpc decision, november 2026")}
        rows, actions = self.run_reconcile([], candidates, historic=historic)
        self.assertEqual(actions["collided"], 1)
        self.assertEqual(rows, [])

    def test_a_cancelled_row_that_comes_back_is_reinstated(self):
        previous = [
            boe_row(
                dt.date(2026, 9, 17),
                self.title,
                status="cancelled",
                last_verified="2026-08-03",
                notes="Dropped off the published schedule, seen missing on 2026-08-03.",
            )
        ]
        candidates = [boe_row(dt.date(2026, 9, 17), self.title)]
        rows, actions = self.run_reconcile(previous, candidates)
        self.assertEqual(actions["reinstated"], 1)
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertIn("Back on the published schedule", rows[0]["notes"])

    def test_a_cancelled_row_in_the_past_is_not_marked_occurred(self):
        previous = [
            boe_row(
                dt.date(2026, 8, 6),
                "Bank of England MPC decision, August 2026",
                status="cancelled",
                last_verified="2026-08-03",
            )
        ]
        rows, _ = self.run_reconcile(previous, [])
        self.assertEqual(rows[0]["status"], "cancelled")

    def test_output_is_sorted_by_date_then_title(self):
        candidates = [
            boe_row(dt.date(2026, 11, 5), "Bank of England MPC decision, November 2026"),
            boe_row(dt.date(2026, 9, 17), self.title),
        ]
        rows, _ = self.run_reconcile([], candidates)
        self.assertEqual([row["date"] for row in rows], ["2026-09-17", "2026-11-05"])

    def test_source_id_is_resolved_by_the_longest_matching_prefix(self):
        row = {"source_url": "https://www.ons.gov.uk/releases/consumerpriceinflationjuly2026"}
        self.assertEqual(source_id_of(row, REGISTRY), "ons_calendar")
        self.assertEqual(source_id_of({"source_url": "https://example.com"}, REGISTRY), "")


if __name__ == "__main__":
    unittest.main()
