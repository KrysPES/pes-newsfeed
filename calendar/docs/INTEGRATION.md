# INTEGRATION: wiring the pane into the terminal

**Naming.** Every class is prefixed `pes-cal-`, every id `pesCal`, every CSS
variable `--cal-`. The snippets below use the short names for readability; the
real ones carry the prefix.

Companion to `CLAUDE.md`. This is the detail that did not fit there.

## The split tab

The news drawer's rail is a single 34px strip with one `NEWS` label. It
becomes two stacked blocks:

```
+----+  <- 6px padding
|NEWS|
|    |
+----+  <- 6px gap, app background showing through
|CAL |
|    |
+----+
```

Each block is `flex:1`, has its own border and a 3px rounded left edge, and
the gap between them is the app background. That gap is what makes them read
as two options rather than one strip. It was specifically asked for.

There is **no active or selected styling on the rail.** The rail only shows
while the drawer is collapsed, at which point nothing is open, so a marker
there would be asserting something false.

## What opening a pane does

`openPane(which)` removes `collapsed`, swaps the heading text and shows the
matching body. In the demo the news body is a placeholder note, since the news
pane lives in your existing package. In production, swap that for the real
news list and keep both bodies mounted, toggling visibility.

## The Today jump

`jumpToday()` measures the sticky `.daybar` height and subtracts it from the
scroll target. **Do not simplify this to a plain `scrollIntoView`.** Day
headers are `position: sticky; top: 0`, so scrolling the Today line flush to
the top parks it directly underneath a pinned header and it disappears. This
was a reported bug and this is the fix.

## Sticky headers and measurement

Related trap for anyone testing this: both `getBoundingClientRect()` and
`offsetTop` report the *shifted* position for a sticky element, not its layout
position. Measuring day spacing while headers are pinned returns nonsense.
Set `position: static` on the bars, measure, then restore.

## Freshness stamp

The header carries a dot and a stamp, matching the news drawer's convention:
green within the hour, red beyond. In the demo it is a static string. Wire it
to the scanner's `last_verified`, or better, reuse the terminal's own helper
rather than keeping two.

## Row identity

The scanner uses the **normalised title** as the row key, which is why every
title carries an invariant reference: the meeting month for a policy decision,
the reference period for a bulletin, the ISO week for a weekly release. That
is what lets a reschedule be told from a new event. If you rewrite titles for
display, do it in the pane, not in the data.

## Poll interval

The demo does not poll. The forward file changes weekly, so a daily fetch is
generous. If the terminal already has a sync loop, fold it into that so there
is one heartbeat rather than three.

## Accessibility floor already met

Rows are real `<button>` elements with `aria-expanded`, the rail blocks are
buttons with labels, flags carry `role="img"` and an `aria-label`, and
`prefers-reduced-motion` disables the drawer transition. Please keep these.
