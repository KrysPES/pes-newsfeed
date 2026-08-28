"""Energy relevance filter for the Index news feed.

One function, no dependencies, no network:

    keep, reason = is_relevant(title, summary, url)

It exists because a story about a football match reached the terminal. It is
written to be droppable into whatever is actually running the live feed, which
may not be the Python pipeline in this repository. Call it from an ingest step,
from a widget's render loop, or from a scheduled clean-up over stored items.

Three layers, cheapest and most precise first:

1. SECTION      the URL path says this is sport, entertainment, travel and so
                on. Precise, costs nothing, and catches the whole section
                rather than one story at a time.
2. VOCABULARY   sport and showbiz terms in the text. Whack-a-mole on its own,
                useful as a second net.
3. ANCHOR       the item mentions nothing to do with energy or commodities at
                all. This is the backstop and the only layer that generalises:
                a story that never says anything about the market is noise
                whatever else it scores on.

Layer 3 is the one that matters. The first two are there because a precise
rule that fires early is worth having, not because they are sufficient.

The anchor vocabulary is read from config/themes.json when it is available, so
there is one place to maintain it. A built-in fallback keeps the module
standalone if it is copied somewhere else on its own.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# --------------------------------------------------------------------------
# layer 1: URL sections
# --------------------------------------------------------------------------

# Matched against the URL path, lowercased, as a whole path segment. Kept
# deliberately short: a segment that means "this is not news about the world"
# on any mainstream publisher.
BLOCKED_SECTIONS = {
    "sport", "sports", "football", "soccer", "cricket", "rugby", "tennis",
    "golf", "f1", "formula1", "olympics", "boxing", "nfl", "nba", "mlb",
    "entertainment", "celebrity", "celebrities", "showbiz", "gossip",
    "arts", "art", "culture", "film", "films", "movies", "movie", "tv",
    "television", "music", "books", "theatre", "gaming", "games",
    "lifestyle", "style", "fashion", "beauty", "food", "recipes", "recipe",
    "travel", "horoscope", "horoscopes", "astrology", "puzzles", "crossword",
    "obituaries", "royal", "royals", "weddings", "parenting", "wellness",
    "health-and-fitness", "opinion-cartoon", "cartoons", "photos-of-the-week",
}

# Weather is NOT blocked. It moves the curve.

_SEG = re.compile(r"[^a-z0-9]+")


def _segments(url: str) -> list[str]:
    if not url:
        return []
    path = url.lower()
    for marker in ("://",):
        if marker in path:
            path = path.split(marker, 1)[1]
    path = path.split("/", 1)[1] if "/" in path else ""
    path = path.split("?", 1)[0].split("#", 1)[0]
    return [s for s in path.split("/") if s]


def section_block(url: str) -> str | None:
    """Return the blocking segment, or None. Only the first three path
    segments are considered: a slug can contain anything, and blocking on a
    word that appears inside a headline slug would drop real stories such as
    .../news/2026/opec-cuts-hit-travel-fuel-demand."""
    for seg in _segments(url)[:3]:
        if seg in BLOCKED_SECTIONS:
            return seg
        # trailing index or date forms, e.g. /sport-news/ or /sports2026/
        stripped = _SEG.sub("", seg)
        if stripped in BLOCKED_SECTIONS:
            return seg
    return None


# --------------------------------------------------------------------------
# layer 2: vocabulary that means this is not a market story
# --------------------------------------------------------------------------

BLOCKED_TERMS = [
    # sport
    "champions league", "premier league", "europa league", "la liga",
    "serie a", "bundesliga", "ligue 1", "world cup", "fa cup", "carabao cup",
    "qualifying win", "friendly match", "kick-off", "kickoff", "half-time",
    "full-time", "penalty shoot", "transfer window", "transfer deadline",
    "grand slam", "wicket", "scrum", "touchdown", "slam dunk", "test match",
    "grand prix", "pole position", "manager sacked", "head coach",
    "goalkeeper", "midfielder", "striker scored", "own goal", "hat-trick",
    "hat trick", "relegation", "play-off round", "playoff round",
    # entertainment and lifestyle
    "box office", "red carpet", "film festival", "movie review",
    "album review", "chart-topping", "reality tv", "streaming series",
    "celebrity", "kardashian", "oscars", "grammys", "baftas", "eurovision",
    "royal wedding", "horoscope", "zodiac", "recipe",
    # promotional noise
    "discount code", "black friday", "coupon", "casino", "betting odds",
    "sponsored content", "press release distribution", "webinar registration",
]

# --------------------------------------------------------------------------
# layer 3: the anchor. If none of this appears, it is not a market story.
# --------------------------------------------------------------------------

# Strong anchors: a story containing one of these is about the market.
FALLBACK_ANCHORS = [
    "gas", "lng", "nbp", "ttf", "power", "electricity", "grid", "megawatt",
    "gigawatt", "terawatt", "mw", "gw", "tw", "mwh", "gwh", "twh", "kwh",
    "therm", "pipeline", "interconnector", "storage", "outage", "unavailable",
    "unavailability", "maintenance", "curtailment", "remit", "nuclear",
    "reactor", "coal", "lignite", "oil", "crude", "brent", "wti", "opec",
    "refinery", "refineries", "diesel", "gasoil", "petrol", "gasoline",
    "fuel", "carbon", "ets", "emissions", "solar", "hydro", "renewable",
    "renewables", "generation", "capacity market", "ofgem", "national grid",
    "elexon", "entso", "sanction", "sanctions", "embargo", "export ban",
    "import ban", "chokepoint", "strait of hormuz", "suez", "tanker",
    "terminal", "field", "platform", "compressor", "feedgas",
    "regasification", "utility", "energy price", "price cap", "supplier",
    "wind farm", "wind output", "offshore wind", "onshore wind",
    "power station", "power plant", "transmission", "distribution network",
]

# Weak anchors: energy-adjacent on their own, but they turn up in stories that
# have nothing to do with the market. "Flooding closes schools" is a weather
# story. "Recount demand" is a political one. One of these is not enough; two
# of them, or one strong anchor, is.
WEAK_ANCHORS = [
    "demand", "flood", "flooding", "storm", "cold snap", "heatwave",
    "temperature", "temperatures", "rainfall", "snow", "freeze", "frost",
    "wind", "weather", "forecast", "mild", "warm", "cold", "winter",
    "summer", "drought", "price", "prices", "market", "markets", "supply",
    "output", "consumption", "imports", "exports",
]

def _load_anchor_terms(themes_path):
    """Theme vocabulary plus the built-in list, so the config stays the single
    place to add market vocabulary without the module losing its floor if a
    theme file is trimmed. Geography is deliberately NOT an anchor: a country
    name in a football result is still a football result, which is how the
    Fenerbahce item would have scored on proximity alone."""
    terms = list(FALLBACK_ANCHORS)
    if themes_path is not None:
        try:
            cfg = json.loads(Path(themes_path).read_text(encoding="utf8"))
        except (OSError, ValueError):
            cfg = {}
        for theme in (cfg.get("themes") or {}).values():
            for key in ("terms", "phrases"):
                terms.extend(theme.get(key) or [])

    weak = {w.lower() for w in WEAK_ANCHORS}
    strong = []
    seen = set()
    for t in terms:
        t = str(t).strip().lower()
        if not t or t in seen or t in weak:
            continue
        seen.add(t)
        strong.append(t)
    return strong


def _compile(terms):
    out = []
    for t in terms:
        t = str(t).strip().lower()
        if not t:
            continue
        escaped = r"\s+".join(re.escape(p) for p in t.split())
        out.append(re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE))
    return out


class RelevanceFilter:
    def __init__(self, themes_path=None):
        self.anchors = _compile(_load_anchor_terms(themes_path))
        self.weak = _compile(WEAK_ANCHORS)
        self.blocked = _compile(BLOCKED_TERMS)
        self.anchor_count = len(self.anchors)
        self.weak_count = len(self.weak)

    def check(self, title: str, summary: str = "", url: str = ""):
        """Returns (keep, reason). reason is empty when the item is kept."""
        seg = section_block(url or "")
        if seg:
            return False, f"section: {seg}"

        text = f"{title or ''} {summary or ''}"
        for pat in self.blocked:
            m = pat.search(text)
            if m:
                return False, f"blocked term: {m.group(0).lower()}"

        for pat in self.anchors:
            if pat.search(text):
                return True, ""

        # Two weak anchors will do. One will not: "recount demand" and
        # "flooding closes schools" each carry exactly one.
        hits = set()
        for pat in self.weak:
            m = pat.search(text)
            if m:
                hits.add(m.group(0).lower())
                if len(hits) >= 2:
                    return True, ""

        return False, "no energy anchor"


_DEFAULT = None


def is_relevant(title: str, summary: str = "", url: str = "", themes_path=None):
    """Module level convenience wrapper. Builds the filter once."""
    global _DEFAULT
    if _DEFAULT is None or themes_path is not None:
        f = RelevanceFilter(themes_path)
        if themes_path is None:
            _DEFAULT = f
        return f.check(title, summary, url)
    return _DEFAULT.check(title, summary, url)
