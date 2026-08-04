"""Mutation tests, as section 9 requires.

A validator that has never failed has not been tested, so each one is broken
on purpose here and the run asserts that it fires.

Two kinds of mutation are used.

  data mutations    a clean row set is damaged and the validators are run over
                    it, which is how the historic run tested its checks
  source mutations  scanner/lifecycle.py is recompiled with one transition
                    changed and the lifecycle expectations are run against the
                    mutant, which must then fail

Running this module directly prints the table that goes into RUN_REPORT.md.
"""

import copy
import datetime as dt
import unittest

from support import context  # noqa: F401

from scanner import config, lifecycle, validate
from scanner.rows import make_row

RUN_DATE = dt.date(2026, 8, 10)
HORIZON = dt.date(2028, 2, 10)
BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"


def clean_rows():
    return [
        make_row(
            date="2026-09-17",
            region="UK",
            category="rates",
            title="Bank of England MPC decision, September 2026",
            detail="The committee announces its Bank Rate decision.",
            energy_relevance="Bank Rate sets the discount rate behind forward curves.",
            fuel_scope="both",
            source_url=BOE_URL,
            cadence="eight scheduled meetings a year",
            last_verified="2026-08-10",
        ),
        make_row(
            date="2026-11-05",
            region="UK",
            category="rates",
            title="Bank of England MPC decision, November 2026",
            detail="The committee announces its Bank Rate decision.",
            energy_relevance="Bank Rate sets the discount rate behind forward curves.",
            fuel_scope="both",
            source_url=BOE_URL,
            cadence="eight scheduled meetings a year",
            last_verified="2026-08-10",
        ),
    ]


def _set(index, column, value):
    def apply(rows):
        rows[index][column] = value

    return apply


def _duplicate(index):
    def apply(rows):
        rows.append(copy.deepcopy(rows[index]))

    return apply


# (name, mutation, expected fragment of the message it must raise)
DATA_MUTATIONS = [
    (
        "date bound: push a row past the 18 month horizon",
        _set(0, "date", "2028-06-01"),
        "beyond the horizon",
    ),
    (
        "title length: set a title to 61 characters",
        _set(0, "title", "B" * 61),
        "is 61 characters, over 60",
    ),
    (
        "dash rule: insert U+2014 into detail",
        _set(0, "detail", "The committee announces — its decision."),
        "dash character U+2014",
    ),
    (
        "dash rule: insert U+2013 into notes",
        _set(0, "notes", "range 2026–2027"),
        "dash character U+2013",
    ),
    (
        "consensus rule: set consensus to 2.5",
        _set(0, "consensus", "2.5"),
        "consensus is not blank",
    ),
    (
        "actual rule: set actual on a forward row",
        _set(0, "actual", "3.75"),
        "actual is not blank",
    ),
    (
        "category enum: set category to weather",
        _set(0, "category", "weather"),
        "not in enum",
    ),
    (
        "fuel_scope enum: set fuel_scope to coal",
        _set(0, "fuel_scope", "coal"),
        "fuel_scope 'coal' not in enum",
    ),
    (
        "status enum: set status to pending",
        _set(0, "status", "pending"),
        "status 'pending' not in enum",
    ),
    (
        "ISO date rule: set a date to 17/09/2026",
        _set(0, "date", "17/09/2026"),
        "is not an ISO 8601 date",
    ),
    (
        "time rule: set a time to 9am",
        _set(0, "time", "9am"),
        "is not HH:MM",
    ),
    (
        "duplicate rule: append a copy of row one",
        _duplicate(0),
        "duplicate date plus title",
    ),
    (
        "date_source rule: blank date_source",
        _set(0, "date_source", ""),
        "not set to published or generated",
    ),
    (
        "last_verified rule: blank last_verified",
        _set(0, "last_verified", ""),
        "last_verified is blank",
    ),
    (
        "source_url rule: point a row at an http URL",
        _set(0, "source_url", "http://www.bankofengland.co.uk/"),
        "is not an https URL",
    ),
    (
        "recurring rule: set recurring to maybe",
        _set(0, "recurring", "maybe"),
        "is not yes or no",
    ),
]


def _load_mutant(old, new):
    """Recompile scanner/lifecycle.py with one substitution applied."""
    with open(lifecycle.__file__, encoding="utf-8") as handle:
        source = handle.read()
    if old not in source:
        raise AssertionError("mutation target not found in lifecycle.py: %r" % old)
    source = source.replace(old, new, 1)
    namespace = {
        "__name__": "scanner.lifecycle_mutant",
        "__file__": lifecycle.__file__,
        "__package__": "scanner",
    }
    exec(compile(source, "lifecycle_mutant", "exec"), namespace)
    return namespace


REGISTRY = {
    "sources": [
        {"id": "boe_mpc", "verdict": "resolved", "url": BOE_URL, "url_prefixes": [BOE_URL]}
    ]
}


def _row(date, title, **kwargs):
    return make_row(
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


TITLE = "Bank of England MPC decision, September 2026"


def _check_reschedule(reconcile):
    previous = [_row("2026-09-17", TITLE, status="scheduled", last_verified="2026-08-03")]
    rows, _ = reconcile(previous, [_row("2026-09-24", TITLE)], RUN_DATE, set(), REGISTRY, set())
    assert rows[0]["status"] == "rescheduled", "status was %r" % rows[0]["status"]
    assert rows[0]["date"] == "2026-09-24"


def _check_cancellation(reconcile):
    previous = [_row("2026-09-17", TITLE, status="scheduled", last_verified="2026-08-03")]
    rows, _ = reconcile(previous, [], RUN_DATE, set(), REGISTRY, set())
    assert rows[0]["status"] == "cancelled", "status was %r" % rows[0]["status"]


def _check_occurred(reconcile):
    title = "Bank of England MPC decision, August 2026"
    previous = [_row("2026-08-06", title, status="scheduled", last_verified="2026-08-03")]
    rows, _ = reconcile(previous, [_row("2026-08-06", title)], RUN_DATE, set(), REGISTRY, set())
    assert rows[0]["status"] == "occurred", "status was %r" % rows[0]["status"]


def _check_stale(reconcile):
    previous = [_row("2026-09-17", TITLE, status="scheduled", last_verified="2026-07-20")]
    rows, _ = reconcile(previous, [], RUN_DATE, {"boe_mpc"}, REGISTRY, set())
    assert rows[0]["last_verified"] == "2026-07-20", "last_verified was %r" % rows[0]["last_verified"]
    assert rows[0]["status"] == "scheduled", "status was %r" % rows[0]["status"]


def _check_collision(reconcile):
    title = "Bank of England MPC decision, November 2026"
    historic = {("2026-11-05", title.lower())}
    rows, _ = reconcile([], [_row("2026-11-05", title)], RUN_DATE, set(), REGISTRY, historic)
    assert rows == [], "a colliding row was emitted"


# (name, substitution, the lifecycle expectation that must now fail)
SOURCE_MUTATIONS = [
    (
        "lifecycle: a date change no longer sets status=rescheduled",
        ('updated["status"] = "rescheduled"', 'updated["status"] = "scheduled"'),
        _check_reschedule,
    ),
    (
        "lifecycle: an event dropping off the schedule is not cancelled",
        ('updated["status"] = "cancelled"', 'updated["status"] = "scheduled"'),
        _check_cancellation,
    ),
    (
        "lifecycle: a passed date is not flipped to occurred",
        ('row["status"] = "occurred"', 'row["status"] = "scheduled"'),
        _check_occurred,
    ),
    (
        "lifecycle: an unreachable source no longer leaves the row alone",
        ("if source in unreachable:", "if False:"),
        _check_stale,
    ),
    (
        "lifecycle: a historic collision is emitted instead of dropped",
        ("if historic_key in historic_keys:", "if False:"),
        _check_collision,
    ),
]


class TestDataMutations(unittest.TestCase):
    def test_clean_rows_raise_nothing(self):
        self.assertEqual(validate.check_rows(clean_rows(), RUN_DATE, HORIZON), [])

    def test_every_data_mutation_is_caught(self):
        for name, mutate, fragment in DATA_MUTATIONS:
            with self.subTest(mutation=name):
                rows = clean_rows()
                mutate(rows)
                failures = validate.check_rows(rows, RUN_DATE, HORIZON)
                self.assertTrue(failures, "%s raised nothing" % name)
                self.assertTrue(
                    any(fragment in failure for failure in failures),
                    "%s raised %r, expected %r" % (name, failures, fragment),
                )

    def test_dropping_a_column_from_the_header_is_caught(self):
        header = list(config.FORWARD_COLUMNS)
        header.remove("date_source")
        failures = validate.check_schema(header)
        self.assertTrue(failures)
        self.assertIn("schema:", failures[0])

    def test_reordering_the_header_is_caught(self):
        header = list(config.FORWARD_COLUMNS)
        header[0], header[1] = header[1], header[0]
        self.assertTrue(validate.check_schema(header))


class TestSourceMutations(unittest.TestCase):
    def test_the_unmutated_lifecycle_passes_every_check(self):
        for name, _, check in SOURCE_MUTATIONS:
            with self.subTest(check=name):
                check(lifecycle.reconcile)

    def test_every_lifecycle_mutation_is_caught(self):
        for name, (old, new), check in SOURCE_MUTATIONS:
            with self.subTest(mutation=name):
                mutant = _load_mutant(old, new)
                with self.assertRaises(AssertionError, msg="%s went unnoticed" % name):
                    check(mutant["reconcile"])


def report():
    """Print the mutation table for RUN_REPORT.md."""
    lines = ["| mutation injected | check fired | message raised |", "|---|---|---|"]
    for name, mutate, fragment in DATA_MUTATIONS:
        rows = clean_rows()
        mutate(rows)
        failures = validate.check_rows(rows, RUN_DATE, HORIZON)
        hit = [failure for failure in failures if fragment in failure]
        lines.append(
            "| %s | %s | `%s` |"
            % (name, "yes" if hit else "NO", hit[0] if hit else "none")
        )

    header = list(config.FORWARD_COLUMNS)
    header.remove("date_source")
    schema_failures = validate.check_schema(header)
    lines.append(
        "| schema: drop date_source from the header | %s | `%s` |"
        % ("yes" if schema_failures else "NO", schema_failures[0] if schema_failures else "none")
    )

    for name, (old, new), check in SOURCE_MUTATIONS:
        mutant = _load_mutant(old, new)
        try:
            check(mutant["reconcile"])
        except AssertionError as error:
            lines.append("| %s | yes | `%s` |" % (name, error))
        else:
            lines.append("| %s | NO | none |" % name)
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
