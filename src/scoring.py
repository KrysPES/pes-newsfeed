"""
Relevance scoring for the PES news feed.

Deterministic, explainable, zero cost. Every score carries a breakdown so you
can always answer "why did this rank where it did", which matters more on a
trading desk than a marginally cleverer black-box number.

Score anatomy
-------------
    authority     source credibility            0 - 22
  + themes        weighted theme hits, tapered  0 - ~55
  + geography     proximity to the book         0 - 16   (additive, see note)
  + urgency       happening-now language        0 - 16
  + magnitude     a number with a unit          0 - 12
  + unplanned     the event was not expected    0 - 20
  - planned       routine, already in the curve 0 - -12
  - speculative   opinion / PR, only when
                  nothing concrete is present   0 - -12
  = raw
  x recency       age decay                     0.4 - 1.0
  -> soft saturation curve -> 0 - 100

Two decisions worth explaining, because both came out of the first test run:

1. Geography is ADDITIVE, not a multiplier. As a multiplier it let a routine
   four-day maintenance extension at Bacton outrank a tanker attack in the
   Strait of Hormuz, purely because "Bacton" is a UK word. Chokepoints now sit
   in their own band at the same weight as the UK itself.

2. The speculative penalty only applies when the item has no concrete signal.
   Otherwise it fired on "expected to enter into force", which is a factual
   regulatory timeline rather than speculation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


# --------------------------------------------------------------------------
# matching helpers
# --------------------------------------------------------------------------

def _boundary_pattern(term: str) -> re.Pattern:
    """
    Word-boundary match so 'lng' does not fire inside 'belonging' and 'ets'
    does not fire inside 'markets'. Multi-word terms match as phrases with
    flexible internal whitespace.
    """
    escaped = r"\s+".join(re.escape(part) for part in term.split())
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


class TermIndex:
    """Pre-compiled term set. Built once at startup, reused for every item."""

    def __init__(self, terms: list[str]):
        self.patterns = [(t, _boundary_pattern(t)) for t in terms]

    def hits(self, text: str) -> list[str]:
        return [term for term, pattern in self.patterns if pattern.search(text)]

    def any(self, text: str) -> bool:
        return any(pattern.search(text) for _, pattern in self.patterns)


# --------------------------------------------------------------------------

@dataclass
class ScoreResult:
    score: int
    tags: list[str] = field(default_factory=list)
    alert: str = "normal"
    nature: str = ""                 # unplanned | planned | ""
    breakdown: dict = field(default_factory=dict)
    matched: dict = field(default_factory=dict)
    excluded: bool = False
    exclusion_reason: str = ""


# --------------------------------------------------------------------------

class Scorer:

    # theme contribution tapers so a keyword-stuffed article cannot climb the
    # rankings just by mentioning ten different things once each
    THEME_TAPER = [1.0, 0.60, 0.35, 0.20, 0.10]

    # controls how fast the raw score saturates toward 100
    # raw 60 -> 62, raw 100 -> 80, raw 150 -> 91, raw 200 -> 96
    SATURATION = 62.0

    ALERT_CRITICAL = 80
    ALERT_HIGH = 66
    ALERT_NORMAL = 42

    AUTHORITY_CAP = 22.0

    def __init__(self, themes_config: dict):
        cfg = themes_config

        self.themes = {}
        for name, spec in cfg["themes"].items():
            if not spec.get("active", True):
                continue
            self.themes[name] = {
                "weight": spec["weight"],
                "label": spec.get("label", name),
                "colour": spec.get("colour", "grey"),
                "terms": TermIndex(spec.get("terms", [])),
                "phrases": TermIndex(spec.get("phrases", [])),
                "requires_any": TermIndex(spec["requires_any"]) if spec.get("requires_any") else None,
            }

        geo = cfg["geography"]
        self.geo = []
        for band in ("chokepoint", "primary", "secondary", "tertiary"):
            if band in geo and isinstance(geo[band], dict):
                self.geo.append((band, float(geo[band]["boost"]), TermIndex(geo[band]["terms"])))
        self.geo.sort(key=lambda x: x[1], reverse=True)

        urg = cfg["urgency"]
        self.urgency_boost = float(urg["high"]["boost"])
        self.urgency_terms = TermIndex(urg["high"]["terms"])
        self.spec_penalty = float(urg["speculative"]["penalty"])
        self.spec_terms = TermIndex(urg["speculative"]["terms"])

        nature = cfg.get("event_nature", {})
        self.unplanned_boost = float(nature.get("unplanned", {}).get("boost", 0))
        self.unplanned_terms = TermIndex(nature.get("unplanned", {}).get("terms", []))
        self.planned_penalty = float(nature.get("planned", {}).get("penalty", 0))
        self.planned_terms = TermIndex(nature.get("planned", {}).get("terms", []))

        mag = cfg["magnitude"]
        self.magnitude_boost = float(mag["boost"])
        self.magnitude_patterns = [re.compile(p, re.IGNORECASE) for p in mag["patterns"]]

        self.exclusions = TermIndex(cfg["exclusions"]["terms"])

        rec = cfg.get("recency", {})
        self.full_weight_h = float(rec.get("full_weight_hours", 2.0))
        self.half_life_h = float(rec.get("half_life_hours", 9.0))
        self.recency_floor = float(rec.get("floor", 0.10))
        self.unknown_ts_factor = float(rec.get("unknown_timestamp_factor", 0.55))

    # ------------------------------------------------------------------

    def score(self, item: dict, now: datetime | None = None) -> ScoreResult:
        now = now or datetime.now(timezone.utc)
        text = f"{item.get('title', '')} {item.get('snippet', '')}"

        # 1. hard exclusions -------------------------------------------------
        excluded = self.exclusions.hits(text)
        if excluded:
            return ScoreResult(score=0, excluded=True, alert="low",
                               exclusion_reason=excluded[0])

        breakdown: dict = {}
        matched: dict = {}

        # 2. source authority, compressed into its band ----------------------
        authority = min(self.AUTHORITY_CAP, float(item.get("authority", 10)) * 0.73)
        breakdown["authority"] = round(authority, 1)

        # 3. themes ----------------------------------------------------------
        theme_scores: list[tuple[str, float, list[str]]] = []
        for name, theme in self.themes.items():
            if theme["requires_any"] and not theme["requires_any"].any(text):
                continue

            term_hits = theme["terms"].hits(text)
            phrase_hits = theme["phrases"].hits(text)
            if not term_hits and not phrase_hits:
                continue

            strength = min(1.0, (len(term_hits) * 0.28) + (len(phrase_hits) * 0.52))
            theme_scores.append((name, theme["weight"] * strength, term_hits + phrase_hits))

        theme_scores.sort(key=lambda x: x[1], reverse=True)

        # an item matching no theme is noise, whatever the source
        if not theme_scores:
            return ScoreResult(score=0, alert="low", excluded=True,
                               exclusion_reason="no theme match")

        theme_total = 0.0
        tags: list[str] = []
        for i, (name, raw_theme, hits) in enumerate(theme_scores):
            taper = self.THEME_TAPER[i] if i < len(self.THEME_TAPER) else 0.05
            theme_total += raw_theme * taper
            tags.append(name)
            matched[name] = hits[:6]

        breakdown["themes"] = round(theme_total, 1)

        # 4. geography, additive, highest band wins --------------------------
        geo_score = 0.0
        for band, boost, index in self.geo:
            hits = index.hits(text)
            if hits:
                geo_score = boost
                matched["geography"] = hits[:4]
                breakdown["geo_band"] = band
                break
        breakdown["geography"] = round(geo_score, 1)

        # 5. planned vs unplanned --------------------------------------------
        planned_hits = self.planned_terms.hits(text)
        unplanned_hits = self.unplanned_terms.hits(text)

        nature = ""
        nature_score = 0.0
        if planned_hits:
            nature = "planned"
            nature_score = self.planned_penalty
            matched["planned"] = planned_hits[:3]
        elif unplanned_hits:
            nature = "unplanned"
            nature_score = self.unplanned_boost
            matched["unplanned"] = unplanned_hits[:4]
        breakdown["event_nature"] = round(nature_score, 1)

        # 6. urgency ----------------------------------------------------------
        urgency_hits = self.urgency_terms.hits(text)
        urgency = self.urgency_boost if urgency_hits else 0.0
        breakdown["urgency"] = round(urgency, 1)
        if urgency_hits:
            matched["urgency"] = urgency_hits[:4]

        # 7. magnitude --------------------------------------------------------
        magnitude = 0.0
        for pattern in self.magnitude_patterns:
            if pattern.search(text):
                magnitude = self.magnitude_boost
                break
        breakdown["magnitude"] = round(magnitude, 1)
        item["has_magnitude"] = bool(magnitude)

        # 8. speculation, only when nothing concrete is present ---------------
        concrete = bool(magnitude or unplanned_hits or item.get("type") in ("outage", "storage"))
        spec_hits = self.spec_terms.hits(text)
        speculative = 0.0
        if spec_hits and not concrete:
            speculative = self.spec_penalty
            matched["speculative"] = spec_hits[:4]
        breakdown["speculative"] = round(speculative, 1)

        raw = (authority + theme_total + geo_score + nature_score
               + urgency + magnitude + speculative)
        raw = max(0.0, raw)
        breakdown["raw"] = round(raw, 1)

        # 9. recency ----------------------------------------------------------
        recency = self._recency_factor(item.get("published_at"), now)
        breakdown["recency_multiplier"] = round(recency, 2)

        # 10. soft saturation -------------------------------------------------
        saturated = 100.0 * (1.0 - math.exp(-(raw * recency) / self.SATURATION))
        final = int(max(0, min(100, round(saturated))))

        alert = self._alert_level(final, item, nature, bool(urgency_hits))

        return ScoreResult(score=final, tags=tags, alert=alert, nature=nature,
                           breakdown=breakdown, matched=matched)

    # ------------------------------------------------------------------

    def _recency_factor(self, published_at, now: datetime) -> float:
        """
        Exponential half-life decay.

        The first version held a 0.40 floor, so a major story settled at score
        57 and stayed there indefinitely. On a live feed that is worse than
        useless: Tuesday's outage floats above Thursday's news and the reader
        cannot tell what is current. The floor is now low enough that anything
        beyond a day is effectively retired unless something re-reports it.
        """
        if not published_at:
            return self.unknown_ts_factor

        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except ValueError:
                return self.unknown_ts_factor

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        age_h = (now - published_at).total_seconds() / 3600.0

        if age_h <= self.full_weight_h:
            return 1.0

        decayed = 0.5 ** ((age_h - self.full_weight_h) / self.half_life_h)
        return max(self.recency_floor, decayed)

    def _alert_level(self, score: int, item: dict, nature: str, urgent: bool) -> str:
        """
        Critical is deliberately hard to reach. It is the level that flashes the
        drawer red, so it has to mean something. Anything explicitly described
        as planned can never be critical however high it scores, because routine
        maintenance is already in the curve.

        Alert level moves monotonically with score. An earlier version promoted
        tier-1 disclosures across the threshold, which produced a 79 flagged
        critical sitting above an 81 flagged high. Primary sources already earn
        their place through the authority component; buying them a second
        advantage here just made the ranking untrustworthy to read.
        """
        if nature == "planned":
            return self._band(score)

        hard_signal = bool(item.get("has_magnitude")) or item.get("tier") == 1

        if (score >= self.ALERT_CRITICAL
                and (nature == "unplanned" or urgent)
                and hard_signal):
            return "critical"

        return self._band(score)

    def _band(self, score: int) -> str:
        if score >= self.ALERT_HIGH:
            return "high"
        if score >= self.ALERT_NORMAL:
            return "normal"
        return "low"
