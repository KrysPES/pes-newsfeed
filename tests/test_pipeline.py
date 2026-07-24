"""
Regression tests for the scoring and dedupe engine.

Every test here exists because the behaviour it checks was WRONG at some point
during the build. They are not decoration. Run them after any config change:

    python tests/test_pipeline.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dedupe import cluster, build_anchors, title_tokens, same_story   # noqa: E402
from scoring import Scorer                                            # noqa: E402
from supersede import apply_supersession                              # noqa: E402

THEMES = json.loads((ROOT / "config" / "themes.json").read_text())
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    (PASSED if condition else FAILED).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"  <- {detail}" if detail and not condition else ""))


def item(title, snippet="", authority=15, tier=2, itype="news", age_h=1):
    return {
        "title": title,
        "snippet": snippet,
        "authority": authority,
        "tier": tier,
        "type": itype,
        "url": f"https://test.invalid/{abs(hash(title))}",
        "published_at": (NOW - timedelta(hours=age_h)).isoformat(),
        "source_name": "Test",
    }


def main():
    scorer = Scorer(THEMES)
    s = lambda i: scorer.score(i, now=NOW)   # noqa: E731

    print("\nExclusions")
    check("energy drink is dropped",
          s(item("New energy drink launches in UK supermarkets")).excluded)
    check("stock spam is dropped",
          s(item("Top 10 energy stocks to buy now")).excluded)
    check("football is dropped",
          s(item("Premier League transfer window closes")).excluded)
    check("an item matching no theme is dropped",
          s(item("Local council announces new library opening hours")).excluded)

    print("\nPlanned versus unplanned")
    unplanned = s(item("Unplanned outage at Kollsnes cuts 18 mcm/day",
                       "Force majeure declared, uncertain duration",
                       authority=30, tier=1, itype="outage"))
    planned = s(item("Planned maintenance at Kollsnes to cut 18 mcm/day",
                     "Scheduled maintenance proceeding as planned",
                     authority=30, tier=1, itype="outage"))
    check("unplanned is tagged unplanned", unplanned.nature == "unplanned")
    check("planned is tagged planned", planned.nature == "planned")
    check("unplanned outscores the identical planned event",
          unplanned.score > planned.score,
          f"{unplanned.score} vs {planned.score}")
    check("planned can never be critical", planned.alert != "critical")

    print("\nRanking sanity")
    hormuz = s(item("Tanker attacked in the Strait of Hormuz, insurers raise premiums",
                    "Escalation fears lifted crude by 4% and freight rates jumped."))
    bacton = s(item("Bacton terminal planned maintenance extended by four days",
                    "Scheduled maintenance at the Bacton entry point extended, "
                    "reducing UK entry capacity by 12 mcm/day.",
                    authority=26, tier=1, itype="outage"))
    check("a Hormuz attack outranks routine UK maintenance",
          hormuz.score > bacton.score,
          f"hormuz {hormuz.score} vs bacton {bacton.score}")
    check("a chokepoint earns geographic credit",
          hormuz.breakdown.get("geo_band") == "chokepoint",
          str(hormuz.breakdown.get("geo_band")))

    print("\nSpeculation handling")
    factual = s(item("Ofgem consultation on network charges expected to enter into force",
                     "A code modification is expected to enter into force in April 2027.",
                     authority=22))
    opinion = s(item("Analyst says gas could rally if winter proves colder",
                     "Prices may rise and could test new highs, much depends on weather.",
                     authority=12))
    check("a factual regulatory timeline is not penalised as speculation",
          factual.breakdown.get("speculative", 0) == 0,
          str(factual.breakdown.get("speculative")))
    check("pure opinion is penalised",
          opinion.breakdown.get("speculative", 0) < 0)

    print("\nScore distribution")
    scores = [s(item(t, sn, a, ti, ty)).score for t, sn, a, ti, ty in [
        ("Unplanned outage at Kollsnes cuts 18 mcm/day", "Force majeure", 30, 1, "outage"),
        ("GB REMIT: Heysham 2 unavailable 610 MW", "Unplanned fault", 28, 1, "outage"),
        ("OPEC+ agrees production quota rollover", "Brent a dollar higher", 15, 2, "news"),
        ("World Nuclear News: lifetime extension approved", "1800 MW to 2045", 19, 2, "news"),
    ]]
    check("scores do not all saturate at 100",
          max(scores) < 100 and len(set(scores)) == len(scores), str(scores))
    check("scores stay inside 0-100", all(0 <= x <= 100 for x in scores))

    print("\nDeduplication")
    kollsnes = [
        item("Unplanned outage at Kollsnes processing plant cuts 18 mcm/day, Gassco confirms"),
        item("Norway's Kollsnes plant hit by unplanned outage, gas prices rise"),
        item("Kollsnes outage: Norwegian supply down 18 mcm/day"),
    ]
    for i, it in enumerate(kollsnes):
        it["score"] = 80 - i
    merged = cluster(list(kollsnes))
    check("three reports of one outage collapse to one",
          len(merged) == 1, f"got {len(merged)}")
    check("the merged item records the other sources",
          merged[0].get("duplicate_count") == 2)

    distinct = [
        item("EU gas storage: unusual withdrawal, now 62.4% full", itype="storage"),
        item("European Commission proposes revision of gas storage filling targets"),
    ]
    for i, it in enumerate(distinct):
        it["score"] = 60 - i
    check("a storage data point does not merge with a storage regulation story",
          len(cluster(list(distinct))) == 2)

    opposite = [item("Kollsnes outage extended"), item("Kollsnes back online")]
    for i, it in enumerate(opposite):
        it["score"] = 60 - i
    check("opposite stories about one asset do not merge",
          len(cluster(list(opposite))) == 2)

    anchors = build_anchors([item("Kollsnes gas plant storage outage")] * 3)
    check("domain-ubiquitous words never become anchors",
          "storage" not in anchors and "gas" not in anchors and "plant" not in anchors,
          str(sorted(anchors)))

    print("\nTier-1 URL uniqueness")
    # Discovered in review: ENTSO-E, Elexon and AGSI items all carried their
    # platform's single landing URL, and dedupe pass 1 keys on canonical URL,
    # so every outage from those sources collapsed into ONE item. The fixtures
    # had unique URLs, which is why 34 green tests never noticed.
    same_page = []
    for n, name in enumerate(["PALUEL 2", "HEYSHAM 1", "TIHANGE 3"]):
        it = item(f"Unavailability: {name} (1000 MW)", "unplanned fault",
                  28, 1, "outage")
        it["url"] = f"https://transparency.entsoe.eu/show?event=ev-{n}"
        it["score"] = 80 - n
        same_page.append(it)
    check("distinct events from one platform never collapse",
          len(cluster(list(same_page))) == 3)

    truly_same = []
    for _ in range(2):
        it = item("Unavailability: PALUEL 2 (1330 MW)", "", 28, 1, "outage")
        it["url"] = "https://transparency.entsoe.eu/show?event=fr.a80.paluel-2.2026-07-23"
        it["score"] = 80
        truly_same.append(it)
    check("the same event fetched twice still merges",
          len(cluster(list(truly_same))) == 1)

    print("\nENTSO-E parser against realistic XML")
    from adapters import _parse_entsoe_outages
    # Real IEC 62325 uses DOTTED tag names. An earlier parser matched local
    # name == "name" and would have captured nothing from a live response.
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Unavailability_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0">
  <createdDateTime>2026-07-23T06:15:00Z</createdDateTime>
  <TimeSeries>
    <businessType>A54</businessType>
    <production_RegisteredResource.name>PALUEL 2</production_RegisteredResource.name>
    <production_RegisteredResource.pSRType.powerSystemResources.nominal_P>1330</production_RegisteredResource.pSRType.powerSystemResources.nominal_P>
    <start>2026-07-23T05:00Z</start>
    <end>2026-09-14T22:00Z</end>
    <Reason><text>stress corrosion inspection</text></Reason>
  </TimeSeries>
  <TimeSeries>
    <businessType>A54</businessType>
    <production_RegisteredResource.name>FLAMANVILLE 1</production_RegisteredResource.name>
    <production_RegisteredResource.pSRType.powerSystemResources.nominal_P>1330</production_RegisteredResource.pSRType.powerSystemResources.nominal_P>
    <start>2026-07-22T05:00Z</start>
    <end>2026-08-01T22:00Z</end>
  </TimeSeries>
</Unavailability_MarketDocument>"""
    parsed = _parse_entsoe_outages(xml, "10YFR-RTE------C", "A80")
    check("parser extracts every TimeSeries", len(parsed) == 2, str(len(parsed)))
    check("dotted asset names are captured",
          any("PALUEL 2" in i["title"] for i in parsed),
          str([i["title"] for i in parsed]))
    check("capacity travels into the title",
          any("1330 MW" in i["title"] for i in parsed))
    check("each event gets a unique url",
          len({i["url"] for i in parsed}) == 2)
    check("published_at comes from createdDateTime, not now()",
          all(i["published_at"] and i["published_at"].isoformat().startswith("2026-07-23T06:15")
              for i in parsed),
          str([str(i["published_at"]) for i in parsed]))

    print("\nAlert banding")
    order = {"critical": 3, "high": 2, "normal": 1, "low": 0}
    samples = sorted(
        [s(item(f"Unplanned outage number {n} cuts {n * 100} MW", "Force majeure declared",
                authority=30, tier=1, itype="outage")) for n in range(1, 6)],
        key=lambda r: r.score, reverse=True)
    monotonic = all(order[a.alert] >= order[b.alert] for a, b in zip(samples, samples[1:]))
    check("alert level never rises as score falls", monotonic,
          str([(r.score, r.alert) for r in samples]))

    print("\nRecency decay")
    raw_item = ("Unplanned outage at Kollsnes cuts 18 mcm/day", "Force majeure declared",
                30, 1, "outage")
    by_age = {h: s(item(*raw_item, age_h=h)).score for h in (0, 6, 12, 24, 48, 120)}
    check("a story decays materially within a day",
          by_age[24] < by_age[0] * 0.55, str(by_age))
    check("nothing parks above the display floor after two days",
          by_age[48] < 42, f"48h scored {by_age[48]}")
    check("decay is monotonic",
          all(by_age[a] >= by_age[b] for a, b in zip(sorted(by_age), sorted(by_age)[1:])),
          str(by_age))
    check("old items are retained, not deleted",
          by_age[120] > 0, str(by_age[120]))

    print("\nAnchor detection")
    batch = [item("Unplanned outage at Kollsnes processing plant cuts 18 mcm/day"),
             item("Interconnector cable fault cuts capacity between GB and Belgium"),
             item("Kollsnes outage to last into Wednesday, Gassco says"),
             item("Kollsnes returns to full capacity")]
    anchors = build_anchors(batch)
    check("a common headline verb is never an anchor",
          "cuts" not in anchors, str(sorted(anchors)))
    check("a recurring entity stays an anchor",
          "kollsnes" in anchors, str(sorted(anchors)))
    check("a day of the week is never an anchor", "wednesday" not in anchors)

    print("\nSupersession")
    thread = [
        item("Kollsnes outage to last into Wednesday, Gassco says", age_h=20),
        item("Unplanned outage at Kollsnes processing plant cuts 18 mcm/day", age_h=3),
        item("Kollsnes returns to full capacity after unplanned outage", age_h=1),
    ]
    for it in thread:
        it["tags"] = ["supply_disruption"]
        it["score"] = 70
        it["alert"] = "high"
    apply_supersession(thread)

    visible = [i for i in thread if not i.get("hidden")]
    check("a developing story collapses to its latest version",
          len(visible) == 1, f"{len(visible)} visible")
    check("the survivor is the resolution",
          "returns to full capacity" in visible[0]["title"], visible[0]["title"])
    check("the survivor records how many versions it retired",
          visible[0].get("update_count") == 2, str(visible[0].get("update_count")))
    check("retired versions are demoted, not deleted",
          all(i["score"] < 70 and i["alert"] == "low"
              for i in thread if i.get("hidden")))
    check("retired versions still point at what replaced them",
          all(i.get("superseded_by") for i in thread if i.get("hidden")))

    unrelated = [
        item("Freeport LNG train 2 halted by compressor failure", age_h=72),
        item("Freeport announces expansion of liquefaction capacity", age_h=2),
    ]
    unrelated[0]["tags"] = ["supply_disruption"]
    unrelated[1]["tags"] = ["infrastructure"]
    for it in unrelated:
        it["score"] = 60
    apply_supersession(unrelated)
    check("a different kind of story about the same asset does not supersede",
          not any(i.get("hidden") for i in unrelated))

    print("\nResolutions versus deduplication")
    pair = [item("Unplanned outage at Kollsnes processing plant cuts 18 mcm/day"),
            item("Kollsnes returns to full capacity after unplanned outage")]
    for i, it in enumerate(pair):
        it["score"] = 70 - i
    check("a resolution never merges into the outage it resolves",
          len(cluster(list(pair))) == 2,
          "merging these would hide the fact that it is fixed")

    print("\n" + "-" * 62)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
    print()
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
