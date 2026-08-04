"""Validators, as section 9 requires.

Every check returns a list of failure strings. A validator that has never
failed has not been tested, so tests/test_mutations.py breaks each of these
deliberately and confirms it fires.
"""

from . import config
from .dates import parse_iso


def check_schema(header):
    if list(header) != config.FORWARD_COLUMNS:
        return [
            "schema: header is not the %d columns in order"
            % len(config.FORWARD_COLUMNS)
        ]
    return []


def check_rows(rows, run_date, horizon_end, historic_keys=None):
    failures = []
    failures.extend(_check_dates(rows, horizon_end))
    failures.extend(_check_enums(rows))
    failures.extend(_check_titles(rows))
    failures.extend(_check_dashes(rows))
    failures.extend(_check_blank_columns(rows))
    failures.extend(_check_duplicates(rows))
    failures.extend(_check_date_source(rows))
    failures.extend(_check_source_url(rows))
    if historic_keys:
        failures.extend(_check_historic_collision(rows, historic_keys))
    return failures


def _label(row):
    return "%s %s" % (row.get("date", "?"), row.get("title", "?")[:40])


def _check_dates(rows, horizon_end):
    failures = []
    for row in rows:
        value = row.get("date", "")
        try:
            date = parse_iso(value)
        except (ValueError, AttributeError):
            failures.append("date %r is not an ISO 8601 date (%s)" % (value, _label(row)))
            continue
        if date > horizon_end:
            failures.append(
                "date %s is beyond the horizon %s (%s)"
                % (value, horizon_end.isoformat(), _label(row))
            )
        time = row.get("time", "")
        if time:
            parts = time.split(":")
            valid = (
                len(parts) == 2
                and all(part.isdigit() for part in parts)
                and len(parts[0]) == 2
                and len(parts[1]) == 2
                and int(parts[0]) < 24
                and int(parts[1]) < 60
            )
            if not valid:
                failures.append("time %r is not HH:MM (%s)" % (time, _label(row)))
    return failures


def _check_enums(rows):
    failures = []
    for row in rows:
        if row.get("category") not in config.CATEGORIES:
            failures.append(
                "category %r not in enum (%s)" % (row.get("category"), _label(row))
            )
        if row.get("fuel_scope") not in config.FUEL_SCOPES:
            failures.append(
                "fuel_scope %r not in enum (%s)" % (row.get("fuel_scope"), _label(row))
            )
        if row.get("status") not in config.STATUSES:
            failures.append(
                "status %r not in enum (%s)" % (row.get("status"), _label(row))
            )
        if row.get("recurring") not in ("yes", "no"):
            failures.append(
                "recurring %r is not yes or no (%s)" % (row.get("recurring"), _label(row))
            )
    return failures


def _check_titles(rows):
    failures = []
    for row in rows:
        title = row.get("title", "")
        if not title.strip():
            failures.append("title is blank (%s)" % _label(row))
        elif len(title) > config.TITLE_MAX:
            failures.append(
                "title is %d characters, over %d (%s)"
                % (len(title), config.TITLE_MAX, _label(row))
            )
    return failures


def _check_dashes(rows):
    failures = []
    for row in rows:
        for column, value in row.items():
            if not isinstance(value, str):
                continue
            for dash in config.BANNED_DASHES:
                if dash in value:
                    failures.append(
                        "%s contains a dash character U+%04X (%s)"
                        % (column, ord(dash), _label(row))
                    )
    return failures


def _check_blank_columns(rows):
    failures = []
    for row in rows:
        for column in ("consensus", "actual"):
            if (row.get(column) or "").strip():
                failures.append(
                    "%s is not blank (%r) (%s)" % (column, row.get(column), _label(row))
                )
    return failures


def _check_duplicates(rows):
    failures = []
    seen_pair = set()
    seen_title = set()
    for row in rows:
        pair = (row.get("date", ""), row.get("title", "").strip().lower())
        if pair in seen_pair:
            failures.append("duplicate date plus title: %s" % _label(row))
        seen_pair.add(pair)
        title = row.get("title", "").strip().lower()
        if title in seen_title:
            failures.append(
                "duplicate title, which breaks row identity: %s" % _label(row)
            )
        seen_title.add(title)
    return failures


def _check_date_source(rows):
    failures = []
    for row in rows:
        if row.get("date_source") not in config.DATE_SOURCES:
            failures.append(
                "date_source %r not set to published or generated (%s)"
                % (row.get("date_source"), _label(row))
            )
        if not (row.get("last_verified") or "").strip():
            failures.append("last_verified is blank (%s)" % _label(row))
        else:
            try:
                parse_iso(row["last_verified"])
            except ValueError:
                failures.append(
                    "last_verified %r is not an ISO date (%s)"
                    % (row["last_verified"], _label(row))
                )
    return failures


def _check_source_url(rows):
    failures = []
    for row in rows:
        url = row.get("source_url", "")
        if not url.startswith("https://"):
            failures.append("source_url %r is not an https URL (%s)" % (url, _label(row)))
    return failures


def _check_historic_collision(rows, historic_keys):
    failures = []
    for row in rows:
        key = (row.get("date", ""), row.get("title", "").strip().lower())
        if key in historic_keys:
            failures.append("collides with a historic calendar row: %s" % _label(row))
    return failures
