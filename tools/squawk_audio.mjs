// Squawk natural voice step (29 Oct 2026). Runs right after each ingest tick:
// every fresh squawk-worthy item (alert normal and up - the level Squawk reads
// by default) gets a spoken script built by the SAME rules the terminal's
// browser voice uses (tools/squawk_script.js, vendored byte-identical from the
// terminal repo), which is POSTed to the terminal's clip factory
// (/api/squawk-audio). That route makes the ElevenLabs clip once, stores it,
// and answers with its URL; this step writes audio_url + spoken into the item
// in news.json, so terminals play the natural voice with zero client changes.
//
// All paid keys stay on the terminal deployment - this PUBLIC repo holds only
// the machine credential (INDEX_APP_CRON_SECRET, the terminal's CRON_SECRET).
// With the secret unset the step is a silent no-op and Squawk behaves exactly
// as before (browser voice / caption pop-up).
//
// data/squawk_audio.json is the memory: item url -> {url, spoken, at}. It is
// what makes generation idempotent across ticks and what re-attaches clips
// after ingest regenerates news.json. Entries (and the server's stored clips)
// age out after 14 days - Squawk never reads old news.
import fs from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Script = require("./squawk_script.js");

const NEWS = "data/news.json";
const MAP = "data/squawk_audio.json";
const ENDPOINT = process.env.INDEX_APP_SQUAWK_URL || "https://app.index-terminal.com/api/squawk-audio";
const KEY = (process.env.INDEX_APP_CRON_SECRET || "").trim();
const LEVELS = new Set(["normal", "high", "critical"]);
const KEEP_DAYS = 14;
const PER_TICK = 8;    // a tick is 5 minutes; a flood waits for the next one
const PER_DAY = 120;   // hard stop so a feed malfunction cannot drain the quota

function log(m) { console.log("[squawk-audio] " + m); }

if (!KEY) { log("INDEX_APP_CRON_SECRET not set - skipping (feature off)"); process.exit(0); }

const news = JSON.parse(fs.readFileSync(NEWS, "utf8"));
let map = {};
try { map = JSON.parse(fs.readFileSync(MAP, "utf8")); } catch { /* first run */ }

// Age out old entries; the clip factory prunes its stored files to match.
const cutoff = Date.now() - KEEP_DAYS * 86400_000;
for (const k of Object.keys(map)) if (!map[k].at || Date.parse(map[k].at) < cutoff) delete map[k];

const dayStart = new Date(); dayStart.setUTCHours(0, 0, 0, 0);
let madeToday = Object.values(map).filter((m) => Date.parse(m.at) >= dayStart.getTime()).length;

const items = Array.isArray(news.items) ? news.items : [];
const candidates = items.filter((it) =>
  it && it.url && !map[it.url] && LEVELS.has(it.alert) && !it.withdrawn && !it.superseded
);

async function makeClip(item) {
  // Headline-only scripts (detail:false): crisp bulletins, and the reason the
  // Creator-tier credit budget holds. The admin pronunciation lexicon lives in
  // the terminal's back end, out of this public repo's reach; the built-in
  // list in squawk_script.js does the heavy lifting (units, contracts, moves).
  const spoken = Script.build(item, { detail: false, lexicon: [] });
  if (!spoken || spoken.length < 8) return null;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 25_000);
  try {
    const r = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + KEY },
      body: JSON.stringify({ id: item.url, text: spoken.slice(0, 600) }),
      signal: ctl.signal,
    });
    const j = await r.json().catch(() => null);
    if (!r.ok || !j || !j.ok || !j.url) throw new Error((j && j.error) || "HTTP " + r.status);
    return { url: j.url, spoken, at: new Date().toISOString() };
  } finally {
    clearTimeout(timer);
  }
}

let made = 0, failed = 0;
for (const item of candidates.slice(0, PER_TICK)) {
  if (madeToday >= PER_DAY) { log("daily cap reached (" + PER_DAY + ") - the rest wait for tomorrow"); break; }
  try {
    const entry = await makeClip(item);
    if (!entry) continue;
    map[item.url] = entry;
    made++; madeToday++;
  } catch (e) {
    // Next tick retries naturally: the item is still not in the map.
    failed++;
    log("clip failed for " + item.url.slice(0, 80) + " : " + (e && e.message));
  }
  await new Promise((r) => setTimeout(r, 300));
}

// Attach clips (old and new) to the regenerated feed. spoken rides along so
// the caption shows exactly the words the clip says.
let attached = 0;
for (const it of items) {
  const m = it && it.url ? map[it.url] : null;
  if (!m) continue;
  it.audio_url = m.url;
  it.spoken = m.spoken;
  attached++;
}

fs.writeFileSync(MAP, JSON.stringify(map, null, 2) + "\n");
fs.writeFileSync(NEWS, JSON.stringify(news, null, 2) + "\n");
log("made " + made + " clip(s), " + failed + " failed, " + attached + " item(s) carrying audio, " + madeToday + " today");
