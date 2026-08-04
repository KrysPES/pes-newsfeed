"""Shared test helpers. The whole suite runs offline against saved fixtures."""

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scanner.dates import add_months  # noqa: E402

# The date the fixtures were captured on. Fixing it keeps the suite
# deterministic as the calendar moves on.
RUN_DATE = dt.date(2026, 7, 31)


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


def context(run_date=RUN_DATE, months=18):
    return {"run_date": run_date, "horizon_end": add_months(run_date, months)}
