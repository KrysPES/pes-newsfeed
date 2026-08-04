"""The validators pass on a clean row set."""

import datetime as dt
import unittest

from support import context  # noqa: F401

from scanner import config, validate
from scanner.rows import make_row

RUN_DATE = dt.date(2026, 8, 10)
HORIZON = dt.date(2028, 2, 10)


def clean_row(date="2026-09-17", title="Bank of England MPC decision, September 2026"):
    row = make_row(
        date=date,
        region="UK",
        category="rates",
        title=title,
        detail="The committee announces its decision.",
        energy_relevance="Bank Rate sets the discount rate behind forward curves.",
        fuel_scope="both",
        source_url="https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
        cadence="eight scheduled meetings a year",
        time="11:00",
        last_verified="2026-08-10",
    )
    return row


class TestValidators(unittest.TestCase):
    def test_clean_rows_pass(self):
        rows = [clean_row(), clean_row("2026-11-05", "Bank of England MPC decision, November 2026")]
        self.assertEqual(validate.check_rows(rows, RUN_DATE, HORIZON), [])

    def test_schema_check_accepts_the_forward_columns(self):
        self.assertEqual(validate.check_schema(config.FORWARD_COLUMNS), [])

    def test_column_order_matches_the_historic_file_then_the_three_new_ones(self):
        self.assertEqual(config.FORWARD_COLUMNS[:15], config.HISTORIC_COLUMNS)
        self.assertEqual(
            config.FORWARD_COLUMNS[15:], ["status", "last_verified", "date_source"]
        )

    def test_historic_collision_is_reported(self):
        rows = [clean_row()]
        historic = {("2026-09-17", "bank of england mpc decision, september 2026")}
        failures = validate.check_rows(rows, RUN_DATE, HORIZON, historic)
        self.assertTrue(any("collides with a historic" in f for f in failures))


if __name__ == "__main__":
    unittest.main()
