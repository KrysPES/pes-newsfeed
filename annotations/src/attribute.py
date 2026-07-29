"""
Attribution.

Given a detected episode and the news feed's recent items, propose which item
explains the move. Deterministic, no model calls, no cost.

Design note, and the important one: attribution publishes straight to the chart,
but only when a candidate clears AUTOPUBLISH_MIN_RANK. Below that bar it
publishes nothing at all rather than a weak guess.

That gate is doing the job a review queue would otherwise do. The project rule is
that a wrong label is worse than no label, and direction matching is about 95%
accurate on the cases where it commits. A bar that only lets strong candidates
through is what keeps the marginal calls off a chart nobody is going to
proofread. Lowering it to increase coverage trades away the thing the whole
dataset was built to protect.

Anything published can be removed by an admin. Removal is the correction
mechanism, so the gate has to be strict enough that corrections are rare.

Candidate filtering is deliberately strict. Three hard gates, applied in order:

  1. the item must be published inside the episode's search window
  2. the direction the item implies must match the direction of the move
  3. the item must not be routine (planned maintenance already in the curve)

Anything surviving all three is ranked, and the leader publishes only if it
clears AUTOPUBLISH_MIN_RANK. If nothing survives, or nothing clears the bar, the
function returns None and no marker appears. That is a normal outcome, not an
error: the chart carrying fewer events is the intended trade.
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


AUTOPUBLISH_MIN_RANK = 70.0     # rank_score a candidate must clear to reach the chart


def attribute(episode: dict, news_items: list[dict], lexicon=None, top_n: int = 3) -> dict | None:
    """
    episode: an Episode.as_dict() from detect.py
    news_items: the `items` array from the news feed's news.json

    Returns a published annotation, or None when nothing clears the bar. None
    means no marker: the chart stays clean rather than carrying a guess.

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

    if not top or top[0]["rank_score"] < AUTOPUBLISH_MIN_RANK:
        return None

    return {
        "id": f"evt-{episode['trigger_day']}",
        "date": episode["trigger_day"],
        "label": headline_to_label(top[0]["title"]),
        "headline": top[0]["title"],
        "what_happened": top[0].get("snippet", ""),
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


def headline_to_label(title: str) -> str:
    """Trim a news headline into a chart label.

    Headlines are written to be read in a feed, not to sit on an axis. Strip the
    hedging, drop a trailing clause if it is still too long, and never end
    mid-word. Core information only.
    """
    t = _FLUFF.sub("", str(title or "")).strip()
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[\-\u2013\u2014\s]+|[\s\.]+$", "", t)
    if len(t) <= LABEL_MAX:
        return t
    cut = t[:LABEL_MAX]
    for sep in (" - ", " \u2013 ", ", ", " as ", " after ", " on "):
        i = cut.rfind(sep)
        if i > 24:
            return cut[:i].rstrip(" ,-")
    i = cut.rfind(" ")
    return (cut[:i] if i > 24 else cut).rstrip(" ,-")
