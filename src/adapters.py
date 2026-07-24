"""
Source adapters. One function per source type, all returning the same shape.

Every adapter returns a list of raw dicts:
    { title, url, snippet, published_at (datetime|None), type }

The ingest layer adds source metadata and scoring. Adapters stay dumb on
purpose so adding a new source type is a single function, not a refactor.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None


USER_AGENT = "PES-NewsFeed/1.0 (+https://www.pesomnia.com)"
TIMEOUT = 20


def _get(url: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    return requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)


def _clean(text: str | None, limit: int = 300) -> str:
    """Strip HTML and clamp length. We store a snippet, never full article text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# ==========================================================================
# RSS / Atom
# ==========================================================================

def fetch_rss(source: dict) -> list[dict]:
    if feedparser is None:
        raise RuntimeError("feedparser not installed")

    resp = _get(source["url"])
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    items = []
    for entry in parsed.entries[:80]:
        published = None
        for key in ("published_parsed", "updated_parsed"):
            if getattr(entry, key, None):
                published = datetime(*getattr(entry, key)[:6], tzinfo=timezone.utc)
                break

        items.append({
            "title": _clean(getattr(entry, "title", ""), 400),
            "url": getattr(entry, "link", "") or "",
            "snippet": _clean(getattr(entry, "summary", "") or getattr(entry, "description", "")),
            "published_at": published,
            "type": source.get("default_type", "news"),
        })
    return items


# ==========================================================================
# ENTSO-E Transparency Platform
# ==========================================================================

_ENTSOE_NS = {"": "urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0"}


def _slug(text: str, limit: int = 48) -> str:
    """Stable, URL-safe identifier fragment."""
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-")[:limit].lower()


def fetch_entsoe(source: dict) -> list[dict]:
    token = os.environ.get(source.get("api_key_env", "ENTSOE_TOKEN"), "")
    if not token:
        raise RuntimeError("ENTSOE_TOKEN not set")

    params_cfg = source.get("params", {})
    lookback = int(params_cfg.get("lookback_hours", 24))
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=lookback)).strftime("%Y%m%d%H00")
    end = (now + timedelta(hours=72)).strftime("%Y%m%d%H00")

    items: list[dict] = []

    for domain in params_cfg.get("domains", []):
        for doc_type in params_cfg.get("document_types", ["A80"]):
            try:
                resp = _get(source["url"], params={
                    "securityToken": token,
                    "documentType": doc_type,
                    "biddingZone_Domain": domain,
                    "periodStart": start,
                    "periodEnd": end,
                })
                if resp.status_code != 200:
                    continue
                items.extend(_parse_entsoe_outages(resp.content, domain, doc_type))
            except requests.RequestException:
                continue

    return items


def _parse_entsoe_outages(payload: bytes, domain: str, doc_type: str) -> list[dict]:
    """
    ENTSO-E returns IEC 62325 XML. Two hard-won details:

    1. Tag names are DOTTED: the asset name arrives as something like
       <production_RegisteredResource.name>, whose XML local name is the whole
       dotted string. An earlier version matched on local name == "name" and
       would have captured nothing from a real response. Matching is now on the
       last dot-separated segment.

    2. Every item must carry a UNIQUE url. All outages share one landing page,
       and downstream deduplication keys on canonical URL, so identical URLs
       collapsed every ENTSO-E outage into a single item. A stable ?event=
       query identifies each event; the query survives URL canonicalisation
       (only known tracking parameters are stripped) and gives the widget a
       stable key for read-state.

    published_at comes from the document's createdDateTime. The earlier now()
    stamp re-freshened every item on every 5-minute run, so ENTSO-E outages
    never decayed and permanently topped the Recent sort.
    """
    out: list[dict] = []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return out

    def local(el) -> str:
        return el.tag.split("}")[-1]

    created = None
    for el in root.iter():
        if local(el) == "createdDateTime" and el.text:
            created = _parse_iso(el.text.strip())
            break

    wanted = {"name", "nominal_P", "quantity", "businessType",
              "start", "end", "text", "psrType"}

    for ts in root.iter():
        if local(ts) != "TimeSeries":
            continue

        fields: dict[str, str] = {}
        for child in ts.iter():
            key = local(child).split(".")[-1]
            if key in wanted and child.text and child.text.strip() and key not in fields:
                fields[key] = child.text.strip()

        asset = fields.get("name", "unnamed asset")
        capacity = fields.get("nominal_P") or fields.get("quantity") or ""
        reason = fields.get("text", "")
        event_start = fields.get("start", "")

        title = f"Unavailability: {asset}"
        if capacity:
            title += f" ({capacity} MW)"

        event_id = f"{_slug(domain)}.{_slug(doc_type)}.{_slug(asset)}.{_slug(event_start, 16)}"
        out.append({
            "title": title,
            "url": ("https://transparency.entsoe.eu/outage-domain/r2/"
                    f"unavailabilityOfGenerationUnits/show?event={event_id}"),
            "snippet": _clean(f"{domain} {doc_type} {reason} "
                              f"from {event_start} to {fields.get('end', '')}"),
            "published_at": created or _parse_iso(event_start),
            "type": "outage",
        })

    return out


# ==========================================================================
# Elexon Insights REMIT (GB)
# ==========================================================================

def fetch_elexon(source: dict) -> list[dict]:
    now = datetime.now(timezone.utc)
    resp = _get(source["url"], params={
        "from": (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": "json",
    })
    resp.raise_for_status()
    payload = resp.json()

    rows = payload.get("data", payload if isinstance(payload, list) else [])
    items = []
    for row in rows[:100]:
        asset = row.get("assetId") or row.get("affectedUnit") or "GB asset"
        unavailable = row.get("unavailableCapacity") or row.get("normalCapacity") or ""
        cause = row.get("cause") or row.get("eventType") or ""

        title = f"GB REMIT: {asset}"
        if unavailable:
            title += f" unavailable {unavailable} MW"

        # unique per message: shared URLs collapse in deduplication
        mrid = row.get("mrid") or row.get("mRID") or row.get("id") or ""
        event_id = _slug(mrid) if mrid else f"{_slug(asset)}.{_slug(row.get('eventStartTime', ''), 16)}"

        items.append({
            "title": title,
            "url": f"https://bmrs.elexon.co.uk/remit?event={event_id}",
            "snippet": _clean(f"{cause} {row.get('eventStatus', '')} "
                              f"{row.get('eventStartTime', '')} to {row.get('eventEndTime', '')}"),
            "published_at": _parse_iso(row.get("publishTime")),
            "type": "outage",
        })
    return items


# ==========================================================================
# GIE AGSI+ storage
# ==========================================================================

def fetch_agsi(source: dict) -> list[dict]:
    """
    Deliberately quiet. Mirroring a storage percentage every five minutes would
    flood the feed with non-events. This only emits an item when the daily move
    is unusual against the trailing fortnight, which is the only time storage
    is news.
    """
    key = os.environ.get(source.get("api_key_env", "AGSI_KEY"), "")
    if not key:
        raise RuntimeError("AGSI_KEY not set")

    items: list[dict] = []
    for country in source.get("params", {}).get("countries", ["EU"]):
        try:
            resp = _get(source["url"], params={"country": country, "size": 20},
                        headers={"x-key": key})
            if resp.status_code != 200:
                continue
            rows = resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            continue

        if len(rows) < 3:
            continue

        try:
            latest = rows[0]
            full = float(latest.get("full", 0))
            net = float(latest.get("netWithdrawal", 0) or 0)
            history = [abs(float(r.get("netWithdrawal", 0) or 0)) for r in rows[1:15]]
        except (TypeError, ValueError):
            continue

        if not history:
            continue

        avg = sum(history) / len(history)
        unusual = avg > 0 and abs(net) > (avg * 1.8)

        if not unusual:
            continue

        direction = "withdrawal" if net > 0 else "injection"
        items.append({
            "title": f"{country} gas storage: unusual {direction}, now {full:.1f}% full",
            "url": f"https://agsi.gie.eu/?event={_slug(country)}.{_slug(latest.get('gasDayStart', ''), 16)}",
            "snippet": _clean(
                f"Net {direction} of {abs(net):.2f} against a 14-day average of {avg:.2f}. "
                f"Storage at {full:.1f} per cent full on {latest.get('gasDayStart', '')}."
            ),
            "published_at": _parse_iso(latest.get("gasDayStart")),
            "type": "storage",
        })

    return items


# ==========================================================================
# GDELT
# ==========================================================================

def fetch_gdelt(source: dict, queries: list[str]) -> list[dict]:
    items: list[dict] = []
    for query in queries[:6]:
        try:
            resp = _get(source["url"], params={
                "query": query,
                "mode": "ArtList",
                "maxrecords": 40,
                "timespan": "2h",
                "format": "json",
                "sort": "datedesc",
            })
            if resp.status_code != 200:
                continue
            articles = resp.json().get("articles", [])
        except (requests.RequestException, ValueError):
            continue

        for art in articles:
            items.append({
                "title": _clean(art.get("title", ""), 400),
                "url": art.get("url", ""),
                "snippet": _clean(art.get("domain", "")),
                "published_at": _parse_gdelt_date(art.get("seendate")),
                "type": "news",
            })
    return items


def _parse_gdelt_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ==========================================================================
# Google News search (off by default, see sources.json note)
# ==========================================================================

def fetch_google_news(source: dict, queries: list[str]) -> list[dict]:
    if feedparser is None:
        raise RuntimeError("feedparser not installed")

    params = source.get("params", {})
    items: list[dict] = []

    for query in queries[:8]:
        q = f"{query} when:{params.get('when', '1d')}"
        url = (f"{source['url']}?q={quote_plus(q)}"
               f"&hl={params.get('hl', 'en-GB')}"
               f"&gl={params.get('gl', 'GB')}"
               f"&ceid={quote_plus(params.get('ceid', 'GB:en'))}")
        try:
            resp = _get(url)
            if resp.status_code != 200:
                continue
            parsed = feedparser.parse(resp.content)
        except requests.RequestException:
            continue

        for entry in parsed.entries[:30]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            items.append({
                "title": _clean(getattr(entry, "title", ""), 400),
                "url": getattr(entry, "link", ""),
                "snippet": _clean(getattr(entry, "source", {}).get("title", "")
                                  if isinstance(getattr(entry, "source", None), dict) else ""),
                "published_at": published,
                "type": "news",
            })
    return items


# ==========================================================================
# shared
# ==========================================================================

def _parse_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


ADAPTERS = {
    "rss": fetch_rss,
    "entsoe": fetch_entsoe,
    "elexon": fetch_elexon,
    "agsi": fetch_agsi,
    "gdelt": fetch_gdelt,
    "google_news": fetch_google_news,
    "html_watch": None,   # placeholder, see sources.json note on Gassco
}
