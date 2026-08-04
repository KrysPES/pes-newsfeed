"""Paths, schema and house style constants."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
REFERENCE_DIR = os.path.join(ROOT, "reference")

FORWARD_CSV = os.path.join(OUTPUT_DIR, "forward_calendar.csv")
SCAN_LOG = os.path.join(OUTPUT_DIR, "scan_log.jsonl")
REGISTRY_PATH = os.path.join(ROOT, "registry.json")
HISTORIC_CSV = os.path.join(REFERENCE_DIR, "calendar.csv")

# The historic 15 columns in the same order, plus the three forward columns.
HISTORIC_COLUMNS = [
    "date",
    "time",
    "region",
    "category",
    "title",
    "detail",
    "energy_relevance",
    "fuel_scope",
    "previous",
    "consensus",
    "actual",
    "recurring",
    "cadence",
    "source_url",
    "notes",
]

FORWARD_COLUMNS = HISTORIC_COLUMNS + ["status", "last_verified", "date_source"]

CATEGORIES = {
    "rates",
    "inflation",
    "employment",
    "growth",
    "election",
    "policy",
    "regulation",
    "geopolitics",
    "sanctions",
    "supply",
    "inventory",
    "other",
}

FUEL_SCOPES = {"gas", "electricity", "both"}
STATUSES = {"scheduled", "rescheduled", "cancelled", "occurred"}
DATE_SOURCES = {"published", "generated"}

TITLE_MAX = 60

# Section 3 house style: no em dash, no en dash. The horizontal bar and the
# minus sign are close enough cousins to be worth catching too.
BANNED_DASHES = ["—", "–", "―", "−"]

HORIZON_MONTHS = 18

# Section 5 decision 5: the daily run only re-checks events inside this window.
DAILY_WINDOW_DAYS = 14

USER_AGENT = (
    "Mozilla/5.0 (compatible; PES-forward-scanner/1.0; "
    "+https://professionalenergy.co.uk)"
)
FETCH_TIMEOUT = 45
