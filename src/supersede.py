"""
Supersession: retiring stories that a later update has overtaken.

Deduplication handles the same story arriving from twelve outlets inside an
hour. It does not handle the same story DEVELOPING over days:

    Mon 09:12  Unplanned outage at Kollsnes cuts 18 mcm/day
    Mon 16:40  Kollsnes outage to last into Wednesday, Gassco says
    Wed 08:05  Kollsnes back to full capacity

Without this module all three sit in the feed at once. The Monday item decays
but never disappears, and a reader scanning the drawer sees an outage that was
fixed yesterday sitting above genuinely live news.

Only the Wednesday item should be visible. The other two are history.

How a supersession is decided
-----------------------------
Two items are the same thread when:

  1. they share an anchor token (a rare, distinctive word: a plant name, a
     field, a terminal), and
  2. they share at least one theme tag, and
  3. they fall inside the supersession window.

Condition 2 is the important guard. Without it, "Freeport train 2 halted"
would be superseded by "Freeport announces expansion" three days later purely
because both say Freeport. Sharing an anchor means they are about the same
THING; sharing a theme means they are about the same KIND of event.

Note this is deliberately looser than the deduplication rule, which refuses to
merge "Kollsnes outage extended" with "Kollsnes back online" on the grounds
that they are opposite stories. For supersession that is exactly the merge we
want: a resolution should retire the outage that preceded it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dedupe import build_anchors, title_tokens


def _parse(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def apply_supersession(items: list[dict],
                       window_days: float = 5.0,
                       demote: float = 0.30,
                       hide: bool = True) -> list[dict]:
    """
    Mark older members of a developing story as superseded.

    Mutates and returns the list. Superseded items gain:

        superseded          True
        superseded_by       {url, title, published_at} of the newest version
        score               multiplied by `demote`
        alert               forced down to "low"

    The surviving newest item gains:

        update_count        how many earlier versions it retired
        thread_started_at   timestamp of the earliest version in the thread

    Nothing is deleted. The history stays in the file, it just stops competing
    for attention. That matters: someone asking "when did this start" needs the
    original, and `thread_started_at` tells them without a second lookup.
    """
    if not items:
        return items

    anchors = build_anchors(items)
    window = timedelta(days=window_days)

    # index by anchor token so this stays near-linear rather than comparing
    # every item against every other one
    buckets: dict[str, list[int]] = {}
    meta: list[tuple[set[str], set[str], datetime | None]] = []

    for idx, item in enumerate(items):
        tokens = title_tokens(item.get("title", ""))
        tags = set(item.get("tags", []))
        when = _parse(item.get("published_at"))
        meta.append((tokens, tags, when))

        for token in tokens & anchors:
            buckets.setdefault(token, []).append(idx)

    # newest index that supersedes each item
    superseder: dict[int, int] = {}

    for indices in buckets.values():
        if len(indices) < 2:
            continue

        for a in indices:
            tokens_a, tags_a, when_a = meta[a]
            if when_a is None:
                continue

            for b in indices:
                if a == b:
                    continue
                tokens_b, tags_b, when_b = meta[b]
                if when_b is None or when_b <= when_a:
                    continue                      # b must be strictly newer
                if when_b - when_a > window:
                    continue
                if not (tags_a & tags_b):
                    continue                      # same thing, different kind of event

                current = superseder.get(a)
                if current is None or (meta[current][2] or when_b) < when_b:
                    superseder[a] = b

    # collapse chains so everything points at the newest version, not the next
    # one along. Mon -> Tue -> Wed becomes Mon -> Wed and Tue -> Wed.
    for idx in list(superseder):
        seen = {idx}
        target = superseder[idx]
        while target in superseder and target not in seen:
            seen.add(target)
            target = superseder[target]
        superseder[idx] = target

    threads: dict[int, list[int]] = {}
    for old, new in superseder.items():
        threads.setdefault(new, []).append(old)

    for old, new in superseder.items():
        newest = items[new]
        item = items[old]
        item["superseded"] = True
        item["superseded_by"] = {
            "url": newest.get("url"),
            "title": newest.get("title"),
            "published_at": newest.get("published_at"),
        }
        item["score"] = int(round(item.get("score", 0) * demote))
        item["alert"] = "low"
        if hide:
            item["hidden"] = True

    for new, olds in threads.items():
        newest = items[new]
        newest["update_count"] = len(olds)
        starts = [meta[o][2] for o in olds if meta[o][2]]
        own = meta[new][2]
        if own:
            starts.append(own)
        if starts:
            newest["thread_started_at"] = min(starts).isoformat()

    return items
