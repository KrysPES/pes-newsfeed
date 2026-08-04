# QA report: adversarial pass before handover

> **Superseded in part.** This was the calendar's solo pass. It was bundled with
> the popups module afterwards, and that pass found three further issues in this
> module: a `:root` block that overrode the terminal's variables, bare class
> names that would have restyled the terminal shell, and leaked JavaScript
> globals. See `../../docs/QA_REPORT.md` for the current picture.

Run 31 July 2026 against the built package. Findings ranked, each with a
reproduction. Verdict at the bottom.

## Findings

### 1. Medium, FIXED. Source link did not check the URL scheme

The expanded row rendered `source_url` straight into an `href`. `esc()`
escapes HTML but does not stop a `javascript:` URL becoming a clickable link.
Harmless while the data is baked in, but the pane is meant to fetch a JSON
file over the network in production, which makes the data untrusted input.

**Reproduction.** Inject a row with `"u":"javascript:alert(1)"` into `EV` and
expand it. Before the fix the row emitted a live link to that URL.

**Fix.** `safeUrl()` in `src/calendar.js` allows `https://` only, otherwise no
link is rendered. Re-run of the same reproduction now emits 0 links while the
row itself still renders. `rel` also upgraded to `noopener noreferrer`.

### 2. Low, ACCEPTED. The webfont is fetched from a CDN

`web/` links IBM Plex Sans from Google Fonts. That is the only external
request in the file. Offline it falls back through Segoe UI to the system
sans, and nothing else breaks.

Kept because the demo needs to look right on Alex's machine. **On integration
this link should be deleted**, since the terminal already loads the face.

### 3. Low, ACCEPTED. IBM Plex rendering is unverified

The build container has no Plex installed, so every render check in this pass
measured the fallback face, not Plex. Geometry, colour and layout assertions
are unaffected. The type itself needs one look on a machine that has it.

### 4. Informational. Zero electricity rows is a data gap, not a bug

`fuel_scope=electricity` never appears, so no pane path exercises it. The
colour coding that would have exposed this was removed on request, so it is
invisible in the UI. Cause and the four unresolved sources are in
`docs/SCANNER_RUN_REPORT.md` section 2.

## Checks run and passed

| Check | Result |
|---|---|
| Clean rebuild from deleted artefacts | identical md5 across two runs |
| `build_demo.py` twice, byte identical | pass, and enforced by a test |
| `build_data.py` refuses duplicate date plus title | exits 1 with the offending key |
| Package tests | 21 pass |
| Scanner tests | 71 pass |
| Scanner mutation tests | 22 injected, 22 caught |
| Hostile `javascript:` URL | no link emitted |
| Overflow at 1366x645 | none |
| Overflow at 1920x1080 | none |
| Overflow at 2560x1289 | none |
| First tab stop | the news rail block, labelled |
| Enter opens a pane | yes |
| Rows are real buttons with `aria-expanded` | yes |
| `prefers-reduced-motion` honoured | yes |
| Flags paint the right colours | UK, US and EU verified by pixel decode |
| Today jump from the bottom of the list | label fully visible, nothing overlapping |
| Collapsed on load, neither pane preselected | yes |
| No em dashes or en dashes in the built file | none |

## Verdict

**Ship.** One medium finding was found and fixed inside this pass, the two low
findings are documented rather than outstanding, and the informational one is
a known data gap already stated at the top of `KRYS_READ_ME_FIRST.md`.

Two things to do at integration time rather than now: delete the webfont link
so the pane inherits the terminal's type, and confirm the Plex rendering on a
machine that has the font.
