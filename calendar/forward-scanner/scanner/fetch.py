"""Fetching, with every attempt logged.

Hard rule, section 6: a row is written only if its source_url was fetched and
returned 200. Nothing else in the scanner is allowed to invent a page.
"""

import datetime as dt
import json
import os

import requests

from . import config


class Fetcher(object):
    """Fetches URLs, records every attempt, and never raises at the caller."""

    def __init__(self, log_path=None, timeout=None, session=None):
        self.log_path = log_path or config.SCAN_LOG
        self.timeout = timeout or config.FETCH_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/calendar,*/*",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        self.attempts = []

    def _log(self, record):
        self.attempts.append(record)
        directory = os.path.dirname(self.log_path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def get(self, url, source_id=""):
        """Return (status, text). status is an int, or a string on transport
        failure. text is None unless the status was 200."""
        started = dt.datetime.now(dt.timezone.utc)
        record = {
            "fetched_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_id": source_id,
            "url": url,
        }
        try:
            response = self.session.get(url, timeout=self.timeout)
        except Exception as error:  # transport level, never fatal
            record["status"] = "error"
            record["error"] = "%s: %s" % (type(error).__name__, str(error)[:200])
            self._log(record)
            return record["status"], None

        record["status"] = response.status_code
        record["bytes"] = len(response.content)
        record["content_type"] = response.headers.get("Content-Type", "")
        self._log(record)
        if response.status_code != 200:
            return response.status_code, None
        return 200, response.text


class StubFetcher(object):
    """Serves saved fixtures. Used by the offline test suite."""

    def __init__(self, pages):
        self.pages = dict(pages)
        self.attempts = []

    def get(self, url, source_id=""):
        self.attempts.append({"url": url, "source_id": source_id})
        if url not in self.pages:
            return 404, None
        value = self.pages[url]
        if isinstance(value, int):
            return value, None
        return 200, value
