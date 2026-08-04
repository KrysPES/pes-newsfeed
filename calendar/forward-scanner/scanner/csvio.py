"""Reading and writing the calendar files."""

import csv
import os

from . import config


def read_rows(path, columns=None):
    """Read a CSV into a list of dicts. Missing file gives an empty list."""
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
    if columns:
        for row in rows:
            for column in columns:
                row.setdefault(column, "")
    return rows


def write_rows(path, rows, columns=None):
    columns = columns or config.FORWARD_COLUMNS
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def header_of(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            return row
    return []


def historic_keys(path=None):
    """(date, title) pairs already in the immutable historic calendar."""
    path = path or config.HISTORIC_CSV
    keys = set()
    for row in read_rows(path):
        keys.add((row.get("date", "").strip(), row.get("title", "").strip().lower()))
    return keys
