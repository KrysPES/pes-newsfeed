"""
Attribution.

Given a detected episode and the news feed's recent items, propose which item
explains the move. Deterministic, no model calls, no cost.

Design note (policy v2, set by Alex July 2026): any episode with an associated
event gets labelled. "Associated" means a news item that passes the three gates
below: published inside the episode's search window, implying the same direction
as the move, and not routine planned maintenance. There is NO rank threshold on
top of the gates.

v1 additionally required the top candidate to clear a rank score of 70. In five
months of live running that bar published nothing at all across a dozen
detectable episodes, because it was calibrated against one synthetic maxed-out
item rather than the feed's real score distribution. Alex's decision: labels are
cheap to remove (per-annotation delete, whole layer toggles off) and missing
ones are invisible, so publish whatever passes the gates and let admins prune.

Do not add a threshold back without asking Alex. If mislabels become a problem,
the fix is tightening the gates or the lexicon, not resurrecting the bar that
silenced the system.

Candidate filtering is deliberately strict. Three hard gates, applied in order:

  1. the item must be published inside the episode's search window
  2. the direction the item implies must match the direction of the move
  3. the item must not be routine (planned maintenance already in the curve)

Anything surviving all three is ranked and the leader publishes. If nothing
survives the gates, the function returns None and no marker appears; the daily
job should log that outcome rather than let it pass silently.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "direction.json"


# --------------------------------------------------------------------------
# direction
# --------------------------------------------------------------------------

def _load_lexicon(path: Path = CONFIG):
    cfg = json.loads(path.read_text(encoding="utf-8"))
    clean = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}
    return clean(cfg["bullish"]), clean(cfg["bearish"]), cfg["settings"], cfg["cancellers"]


def _hits(text: str, lexicon: dict[str, int], cancellers=None) -> tuple[float, list[str], float, list[str]]:
    """Returns (score, terms, flipped_score, flipped_terms).

    A bullish term sitting next to a canceller ("force majeure lifted") has its
    weight moved to the other side rather than dropped, because a disruption
    that has been called off is genuinely bearish news."""
    total, matched = 0.0, []
    flipped, flipped_terms = 0.0, []
    low = (text or "").lower()

    cterms = (cancellers or {}).get("terms", [])
    cwin = (cancellers or {}).get("canceller_window", 45)

    for term, weight in lexicon.items():
        for m in re.finditer(r"\b" + re.escape(term) + r"\b", low):
            near = low[max(0, m.start() - cwin): m.end() + cwin]
            if cterms and any(re.search(r"\b" + re.escape(c) + r"\b", near) for c in cterms):
                flipped += weight
                flipped_terms.append(f"{term} (cancelled)")
            else:
                total += weight
                matched.append(term)
            break                       # count each term once
    return total, matched, flipped, flipped_terms


def implied_direction(title: str, snippet: str, lexicon=None) -> tuple[str | None, dict]:
    """Returns ("Up" | "Down" | None, evidence). None means directionless, which
    is a skip rather than a guess."""
    bull, bear, settings, cancellers = lexicon or _load_lexicon()
    tm = settings["title_multiplier"]

    b_t, b_terms, bf_t, bf_terms = _hits(title, bull, cancellers)
    r_t, r_terms, _, _ = _hits(title, bear)
    b_s, b_terms2, bf_s, bf_terms2 = _hits(snippet, bull, cancellers)
    r_s, r_terms2, _, _ = _hits(snippet, bear)

    bull_score = b_t * tm + b_s
    bear_score = r_t * tm + r_s + bf_t * tm + bf_s
    evidence = {
        "bullish_score": round(bull_score, 1), "bearish_score": round(bear_score, 1),
        "bullish_terms": sorted(set(b_terms + b_terms2)),
        "bearish_terms": sorted(set(r_terms + r_terms2 + bf_terms + bf_terms2)),
    }

    margin = settings["min_margin"]
    if bull_score - bear_score >= margin:
        return "Up", evidence
    if bear_score - bull_score >= margin:
        return "Down", evidence
    return None, evidence


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------

POWER_ONLY = {
    "nuclear", "reactor", "edf", "wind", "wind output", "solar", "interconnector",
    "ccgt", "capacity market", "carbon", "eua", "ets", "grid", "national grid eso",
    "settlement period", "balancing",
}
GAS_ONLY = {
    "lng", "pipeline", "storage", "nord stream", "yamal", "gassco", "troll",
    "kollsnes", "nyhamna", "easington", "bacton", "ttf", "nbp", "qatarenergy",
    "freeport", "regasification", "terminal", "bcm", "mcm",
    "gas field", "processing plant", "gas plant", "gas processing", "gas export",
    "gas flows", "gas supply",
}


NEUTRAL_FIT = 0.85


def scope_fit(text: str, fuel_scope: str) -> float:
    """1.0 fits, 0.85 neutral, 0.25 contradicts. Soft, not a gate: a big enough
    gas shock moves power too.

    Neutral sits high on purpose. An item that names no fuel-specific keyword is
    an absence of evidence, not evidence against, and scoring it near the
    contradiction end pushed genuinely strong items below the publish bar.
    Only an item pointing at the *other* fuel is actually penalised."""
    low = (text or "").lower()
    p = sum(1 for t in POWER_ONLY if t in low)
    g = sum(1 for t in GAS_ONLY if t in low)
    if fuel_scope.startswith("Electricity"):
        return 1.0 if p > g else (0.25 if g > p else NEUTRAL_FIT)
    if fuel_scope.startswith("Gas"):
        return 1.0 if g > p else (0.25 if p > g else NEUTRAL_FIT)
    return 1.0 if (g or p) else NEUTRAL_FIT


# --------------------------------------------------------------------------
# attribution
# --------------------------------------------------------------------------

def _parse(ts: str):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def attribute(episode: dict, news_items: list[dict], lexicon=None, top_n: int = 3) -> dict | None:
    """
    episode: an Episode.as_dict() from detect.py
    news_items: the `items` array from the news feed's news.json

    Returns a published annotation for the best gated candidate, or None when no
    news item passes the gates. Ranking chooses BETWEEN surviving candidates; it
    is not a bar any of them must clear.

    Drift episodes return None without being scored. They are slow grinds rather
    than shocks and historically have no findable cause.
    """
    if episode.get("is_drift"):
        return None

    lex = lexicon or _load_lexicon()

    win_start = datetime.fromisoformat(episode["window_start"]).replace(tzinfo=timezone.utc)
    win_end = (datetime.fromisoformat(episode["window_end"]).replace(tzinfo=timezone.utc)
               + timedelta(days=1))
    trigger = datetime.fromisoformat(episode["trigger_day"]).replace(tzinfo=timezone.utc)

    candidates = []
    for item in news_items:
        published = _parse(item.get("published_at"))
        if published is None or not (win_start <= published < win_end):
            continue                                        # gate 1: in window

        text = f"{item.get('title','')} {item.get('snippet','')}"
        direction, evidence = implied_direction(
            item.get("title", ""), item.get("snippet", ""), lex)
        if direction is None or direction != episode["direction"]:
            continue                                        # gate 2: direction

        if item.get("nature") == "planned":
            continue                                        # gate 3: not routine

        relevance = float(item.get("score", 0))
        fit = scope_fit(text, episode["fuel_scope"])

        days_off = abs((published.date() - trigger.date()).days)
        proximity = {0: 1.0, 1: 0.9, 2: 0.75}.get(days_off, 0.55)

        unplanned = 1.15 if item.get("nature") == "unplanned" else 1.0
        alert = {"critical": 1.15, "high": 1.05}.get(item.get("alert"), 1.0)

        rank = relevance * fit * proximity * unplanned * alert

        candidates.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "publisher": item.get("source_name", item.get("source", "")),
            "published_at": item.get("published_at"),
            "event_date": published.date().isoformat(),
            "feed_score": relevance,
            "alert": item.get("alert"),
            "nature": item.get("nature"),
            "implied_direction": direction,
            "rank_score": round(rank, 1),
            "why": {"scope_fit": fit, "proximity": proximity,
                    "days_from_trigger": days_off, **evidence},
        })

    candidates.sort(key=lambda c: c["rank_score"], reverse=True)
    top = candidates[:top_n]

    if not top:
        return None

    return {
        "id": f"evt-{episode['trigger_day']}",
        "date": episode["trigger_day"],
        "label": headline_to_label(top[0]["title"]),
        "headline": top[0]["title"],
        "what_happened": body_text(top[0]),
        "why_it_moved": "",
        "confidence": "Auto",
        "status": "published",
        "direction": episode["direction"],
        "fuel_scope": episode["fuel_scope"],
        "weekly_move": f"{episode['largest_weekly_pct']:+.1f}%",
        "weekly_contract": episode["largest_weekly_contract"],
        "trigger_move": f"{episode['trigger_move_pct']:+.1f}%",
        "window": {"start": episode["window_start"], "end": episode["window_end"]},
        "sources": [{"url": c["url"], "publisher": c["publisher"],
                     "event_date": c["event_date"]} for c in top[:2]],
        "candidates": top,
        "origin": "auto",
        "deleted_by": None,
        "deleted_at": None,
    }


LABEL_MAX = 60
_FLUFF = re.compile(
    r"\b(?:it is understood that|reportedly|according to reports|amid growing|"
    r"in a move that|sources say|it emerged that|has been revealed|"
    r"in what could be|is set to|looks set to|appears to)\b", re.I)


# A label must not end on a word that is waiting for the rest of its clause.
# "Europe's Energy Reserves Worked. The Next Test Will Be" is what the old
# trimmer produced from a real headline: it never broke a word, but it stopped
# on "Be" and the card read as truncated.
_DANGLING = {
    "a", "an", "and", "as", "at", "be", "been", "being", "but", "by", "can", "could",
    "do", "does", "for", "from", "had", "has", "have", "in", "into", "is", "it", "its",
    "may", "might", "more", "most", "not", "of", "on", "or", "over", "shall", "should",
    "than", "that", "the", "their", "then", "there", "these", "this", "to", "up", "was",
    "were", "will", "with", "would",
}


def _trim_dangling(text: str) -> str:
    """Drop trailing words that cannot end a label."""
    words = text.split()
    while words and words[-1].strip(",.;:").lower() in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(" ,-")


def headline_to_label(title: str) -> str:
    """Trim a news headline into a chart label.

    Headlines are written to be read in a feed, not to sit on an axis. Strip
    the hedging, cut at the first sentence end where there is one, drop a
    trailing clause if it is still too long, never end mid word and never end
    on a dangling word. Core information only.

    The sentence cut comes first because a two sentence headline carries its
    news in the first sentence and the second is almost always a tease. It is
    also the difference between a clean 31 character label and a 54 character
    one that stops on "Will Be".
    """
    t = _FLUFF.sub("", str(title or "")).strip()
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[\-\u2013\u2014\s]+|[\s\.]+$", "", t)

    # First sentence, when the split leaves something substantial. The lookahead
    # keeps decimals and abbreviations ("U.S.", "5.6 bcm") out of it.
    m = re.search(r"(?<=[a-z\)\"'])[.!?]\s+(?=[A-Z])", t)
    if m and m.start() >= 24:
        first = t[: m.start()].rstrip(" .")
        if len(first) >= 24:
            t = first

    if len(t) <= LABEL_MAX:
        return _trim_dangling(t)

    cut = t[:LABEL_MAX]
    for sep in (" - ", " \u2013 ", ", ", " as ", " after ", " on "):
        i = cut.rfind(sep)
        if i > 24:
            return _trim_dangling(cut[:i].rstrip(" ,-"))
    i = cut.rfind(" ")
    return _trim_dangling((cut[:i] if i > 24 else cut).rstrip(" ,-"))


def body_text(candidate: dict) -> str:
    """What goes under "What happened" on the annotation card.

    The news item's snippet where there is one. Where there is not, the FULL
    untrimmed headline, because a card with an empty body reads as broken and
    the commentary in the position report has nothing to work with either. An
    empty string is only returned when the item carries neither.
    """
    snippet = str(candidate.get("snippet") or "").strip()
    if snippet:
        return snippet
    return str(candidate.get("title") or "").strip()
