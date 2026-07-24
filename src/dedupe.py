"""
Deduplication and clustering.

The same Sleipner trip will arrive from twelve outlets inside ninety minutes.
Without this the feed becomes unreadable within a day.

Three passes, cheapest first:
  1. exact URL match after canonicalisation
  2. exact title match after normalisation
  3. token-overlap clustering for near-duplicates

No embeddings, no model calls, no cost. Token overlap on news headlines is
crude but works well because headlines about the same event share their
proper nouns, and proper nouns are exactly what we weight.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer",
    "source", "cmpid", "ito", "at_medium", "at_campaign", "__twitter_impression",
    "sh", "share", "amp", "spm", "s_cid", "ncid", "smid",
}

# words that carry no identifying information in a headline
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "will", "would", "could",
    "has", "have", "had", "says", "said", "after", "before", "over", "into",
    "amid", "up", "down", "new", "more", "than", "about", "out", "off",
    "unavailability", "unavailable",
}


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same article from two links collapses to one."""
    if not url:
        return ""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return url.strip().lower()

    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/")

    return urlunparse((parts.scheme.lower(), netloc, path, "", urlencode(query), ""))


def normalise_title(title: str) -> str:
    """Lowercase, strip punctuation and the publisher suffix outlets append."""
    if not title:
        return ""
    t = title.lower()
    # publishers love appending " - Reuters" or " | Bloomberg"
    t = re.split(r"\s+[-|\u2013\u2014]\s+[a-z0-9 .&']{2,25}$", t)[0]
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_tokens(title: str) -> set[str]:
    """
    Bare numbers are excluded: two different reactors both described as
    "(1000 MW)" share the token "1000", which says nothing about whether they
    are the same story. Numbers only identify anything alongside the entity
    they belong to, and the entity is already a token.
    """
    return {w for w in normalise_title(title).split()
            if w not in STOPWORDS and len(w) > 2 and not w.isdigit()}


# Words that are ubiquitous in THIS domain and therefore carry no identifying
# power, however rare they happen to look in a small batch. Without this list a
# storage data point merged with a storage regulation story purely because both
# said "gas" and "storage".
DOMAIN_STOPWORDS = {
    "gas", "power", "energy", "electricity", "market", "markets", "price",
    "prices", "pricing", "oil", "lng", "supply", "demand", "storage", "grid",
    "plant", "outage", "outages", "capacity", "output", "production", "flows",
    "flow", "terminal", "pipeline", "nuclear", "reactor", "carbon", "coal",
    "wind", "solar", "european", "europe", "britain", "british",
    # boilerplate that every REMIT-style disclosure headline contains
    "unavailability", "unavailable", "remit", "umm",
}


# Common headline verbs and quantifiers. These are rare enough in a small batch
# to look distinctive to a frequency test, but they identify nothing. "cuts" is
# the one that caused real damage: it retired a Kollsnes gas outage because an
# unrelated interconnector story also said "cuts".
HEADLINE_NOISE = {
    "cuts", "cut", "rises", "rise", "falls", "fall", "hits", "hit", "sees",
    "adds", "sets", "ends", "opens", "closes", "starts", "halts", "drops",
    "jumps", "slips", "gains", "loses", "plans", "warns", "says", "urges",
    "backs", "faces", "seeks", "wins", "takes", "makes", "keeps", "holds",
    "moves", "turns", "brings", "calls", "needs", "wants", "gives", "shows",
    "finds", "looks", "comes", "goes", "boosts", "lifts", "eases", "climbs",
    "extended", "reduced", "confirmed", "announced", "reported", "expected",
    "unplanned", "planned", "scheduled", "delayed", "million", "billion",
    "percent", "cent", "days", "day", "weeks", "week", "months", "month",
    "years", "year", "first", "second", "third", "next", "last", "major",
    "minor", "higher", "lower", "record", "amid", "after", "before",
    # days, months and generic publication words get capitalised in headlines
    # and would otherwise link two unrelated stories that both say "Wednesday"
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december",
    "news", "report", "reports", "update", "updates", "exclusive", "analysis",
}


def _entity_candidates(title: str) -> set[str]:
    """
    Tokens that look like proper nouns: capitalised somewhere other than the
    first word, or an all-caps acronym.

    Frequency alone cannot tell "Kollsnes" from "cuts" in a small batch. How
    the word is WRITTEN can. Titles that are more than 60 per cent capitalised
    are Title Case and carry no signal, so they are skipped.
    """
    words = [w.strip(".,:;!?()[]'\"") for w in title.split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return set()

    capped = sum(1 for w in words[1:] if w[:1].isupper())
    if capped > 0.6 * max(1, len(words) - 1):
        return set()                      # Title Case Headline, no signal

    out = set()
    for w in words[1:]:
        clean = "".join(ch for ch in w if ch.isalnum()).lower()
        if len(clean) > 2 and (w[:1].isupper() or w.isupper()):
            out.add(clean)
    return out


def build_anchors(items: list[dict]) -> set[str]:
    """
    Identify 'anchor' tokens: distinctive entities a story is about. Plant
    names, field names, terminals, companies.

    The test is SHAPE, not rarity. An earlier version gated on document
    frequency and it broke on the case that matters most: "Kollsnes" appeared
    in four items of a developing outage story, exceeded the rarity ceiling and
    stopped being an anchor. The bigger the running story, the more certainly
    frequency disqualified its own subject.

    The frequency test is gone entirely. It was kept briefly as a safety valve
    against a proper noun appearing everywhere, but that case needs no guard:
    if "Kollsnes" turns up in most of the batch, Kollsnes IS the story and is
    exactly what should anchor it.

    Why not plain inverse document frequency? It was tried first and it made
    things worse. Normalising by total token weight means the rare words that
    are NOT shared ('processing', 'gassco', 'confirms' in one headline;
    'norway', 'prices', 'rise' in the other) inflate the denominator and push
    the similarity down. Two headlines about the same outage scored 0.39.

    What actually identifies a shared story is a shared rare token, in absolute
    terms. If two headlines both say 'Kollsnes', they are about Kollsnes.
    """
    entities: set[str] = set()
    for item in items:
        entities |= _entity_candidates(item.get("title", ""))

    return {
        tok for tok in entities
        if len(tok) > 3
        and tok not in DOMAIN_STOPWORDS
        and tok not in HEADLINE_NOISE
    }


def similarity(a: set[str], b: set[str]) -> float:
    """Overlap normalised by the shorter headline, so a long subheading
    cannot dilute a genuine match."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# Language that marks a story as the RESOLUTION of an earlier one.
RESOLUTION_TERMS = {
    "restored", "resumed", "resumes", "normalised", "normalized", "resolved",
    "reopened", "restarted", "online", "completed", "lifted", "ended", "over",
    "returns", "returned", "back", "recovery", "recovered", "fixed", "repaired",
}


def _is_resolution(tokens: set[str]) -> bool:
    return bool(tokens & RESOLUTION_TERMS)


def same_story(a: set[str], b: set[str], anchors: set[str],
               threshold: float, anchor_floor: float = 0.40) -> bool:
    """
    Merge on either of two conditions:

      1. High plain overlap. Catches reworded versions of the same headline.
      2. A shared anchor token PLUS at least two shared tokens overall.

    The 'at least two shared tokens' guard on rule 2 is what stops
    'Kollsnes outage extended' merging with 'Kollsnes back online'. Those share
    exactly one token, the anchor, and are opposite stories.
    """
    shared = a & b
    if not shared:
        return False

    # "Kollsnes back to full capacity" is not a duplicate of "Kollsnes outage".
    # It is the next chapter. Merging them hides the fact that it is fixed,
    # which is the single worst thing this feed could do. Supersession handles
    # the relationship between them instead.
    if _is_resolution(a) != _is_resolution(b):
        return False

    if similarity(a, b) >= threshold:
        return True

    if len(shared) >= 2 and (shared & anchors) and similarity(a, b) >= anchor_floor:
        return True

    return False


def cluster(items: list[dict], threshold: float = 0.60) -> list[dict]:
    """
    Collapse duplicates. The surviving item is the one with the highest score,
    which naturally promotes the primary source over the aggregators.

    Returns the deduped list. Each survivor gains:
        duplicate_count : how many others collapsed into it
        also_reported_by: list of the other source names
    """
    seen_urls: dict[str, dict] = {}
    seen_titles: dict[str, dict] = {}
    clusters: list[dict] = []
    cluster_tokens: list[set[str]] = []

    anchors = build_anchors(items)

    # highest scoring first so the best version of a story becomes the anchor
    ordered = sorted(items, key=lambda i: i.get("score", 0), reverse=True)

    for item in ordered:
        cu = canonical_url(item.get("url", ""))
        nt = normalise_title(item.get("title", ""))
        tokens = title_tokens(item.get("title", ""))

        anchor = None

        # pass 1: same URL
        if cu and cu in seen_urls:
            anchor = seen_urls[cu]

        # pass 2: same title
        elif nt and nt in seen_titles:
            anchor = seen_titles[nt]

        # pass 3: near-duplicate headline
        else:
            for existing, existing_tokens in zip(clusters, cluster_tokens):
                if not _within_window(item, existing):
                    continue
                if same_story(tokens, existing_tokens, anchors, threshold):
                    anchor = existing
                    break

        if anchor is not None:
            anchor["duplicate_count"] = anchor.get("duplicate_count", 0) + 1
            others = anchor.setdefault("also_reported_by", [])
            src = item.get("source_name") or item.get("source")
            if src and src not in others and src != anchor.get("source_name"):
                others.append(src)
            # keep the earliest sighting: that is when the market first knew
            if item.get("published_at") and anchor.get("published_at"):
                if item["published_at"] < anchor["published_at"]:
                    anchor["first_seen_at"] = item["published_at"]
            continue

        item.setdefault("duplicate_count", 0)
        item.setdefault("also_reported_by", [])
        clusters.append(item)
        cluster_tokens.append(tokens)
        if cu:
            seen_urls[cu] = item
        if nt:
            seen_titles[nt] = item

    return clusters


def _within_window(a: dict, b: dict, hours: int = 12) -> bool:
    """
    Two stories can only be duplicates if they appeared close together. Stops a
    plant name merging an outage this week with the same plant's outage in six
    months' time, which matters once the feed holds a fortnight of history.

    Tightened from 36 hours to 12: deduplication is for simultaneous reports of
    one event. Anything developing over a longer span is a thread, and that is
    supersession's job, not this one's.
    """
    from datetime import datetime, timedelta

    def parse(item):
        val = item.get("published_at")
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except ValueError:
            return None

    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return True
    return abs((pa - pb).total_seconds()) <= hours * 3600
