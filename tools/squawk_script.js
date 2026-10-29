/* script.js: turns a news item into the words Index says out loud.

   Headlines are written to be read, not heard. "Kollsnes -18 mcm/d, NBP Win-26
   +3.2p" read straight by a speech engine comes out as letter soup, so every
   item goes through the same rules before it reaches any voice:

     1. the pronunciation list (admins edit it in the back end): written form
        to spoken form, whole words only, e.g. NBP -> "N B P", p/th -> "pence a
        therm", Win-26 -> "winter 26"
     2. tidy-ups: machine codes (EIC codes, ISO timestamps) dropped or turned
        into "23 July", signed moves read as "up" and "down", shouting
        capitals (PALUEL) read as a word, brackets read as a pause
     3. the squawk shape: "Breaking." in front of a critical item, "Update." in
        front of a story that replaces an earlier one, then the headline, then
        (if the user wants it) the first sentence of the summary

   Deterministic on purpose: no model calls, no per-use cost, the same item
   always produces the same words. The same script feeds whichever voice is
   plugged in, browser speech today or a paid natural voice later, so the
   pronunciation list carries straight over.

   Works in the browser (window.IndexSquawkScript) and in Node (tests). */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.IndexSquawkScript = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  // The starting pronunciation list. Admins add to it (Pronunciation tab);
  // their rows are applied first, so an admin row always wins.
  const DEFAULT_LEXICON = [
    ["NBP", "N B P"], ["TTF", "T T F"], ["LNG", "L N G"], ["UMM", "U M M"],
    ["REMIT", "remit"], ["EDF", "E D F"], ["NESO", "Neso"], ["ENTSO-E", "Entso E"],
    ["IFA", "I F A"], ["IFA2", "I F A 2"], ["EIA", "E I A"], ["GIE", "G I E"], ["AGSI+", "A G S I"],
    ["GB", "G B"], ["EU", "E U"], ["HH", "half-hourly"], ["DA", "day-ahead"], ["WD", "within-day"],
    ["CfD", "C F D"], ["PPA", "P P A"], ["BM", "balancing mechanism"], ["SAP", "S A P"], ["SSP", "S S P"],
    ["mcm/d", "million cubic metres a day"], ["mcm/day", "million cubic metres a day"],
    ["mcm", "million cubic metres"], ["bcm", "billion cubic metres"],
    ["p/th", "pence a therm"], ["p/therm", "pence a therm"],
    ["£/MWh", "pounds a megawatt hour"], ["€/MWh", "euros a megawatt hour"], ["EUR/MWh", "euros a megawatt hour"],
    ["$/MMBtu", "dollars per million B T U"], ["MMBtu", "million B T U"],
    ["GW", "gigawatts"], ["MW", "megawatts"], ["TWh", "terawatt hours"], ["GWh", "gigawatt hours"], ["MWh", "megawatt hours"],
    ["Ofgem", "Ofgem"], ["Dunkelflaute", "dunkel-flowter"],
  ];

  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const SHORT = { Jan: "January", Feb: "February", Mar: "March", Apr: "April", May: "May", Jun: "June", Jul: "July", Aug: "August",
    Sep: "September", Sept: "September", Oct: "October", Nov: "November", Dec: "December",
    Win: "winter", Sum: "summer", Cal: "cal", Q1: "Q1", Q2: "Q2", Q3: "Q3", Q4: "Q4" };

  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Whole-word match that also works for terms made of symbols (p/th, £/MWh).
  function termRegex(term, flags) {
    const head = /^\w/.test(term) ? "(?<![\\w])" : "";
    const tail = /\w$/.test(term) ? "(?![\\w])" : "";
    return new RegExp(head + reEsc(term) + tail, flags);
  }

  // flags "gi" for the admins' rows (so SIZEWELL finds Sizewell), "g" for the
  // built-in list, where case matters (MW is megawatts, mW would not be).
  function compile(lexicon, flags) {
    // Longest first, so "mcm/day" is taken before "mcm".
    return lexicon.filter((r) => r && r[0] && r[1] != null)
      .slice().sort((a, b) => b[0].length - a[0].length)
      .map(([w, s]) => [termRegex(String(w).trim(), flags), String(s)]);
  }

  const CUR = { "£": "pounds", "€": "euros", "$": "dollars" };
  const PER = { MWh: "megawatt hour", therm: "therm", th: "therm", MMBtu: "million B T U", t: "tonne", tonne: "tonne" };

  function isoDate(y, m, d) {
    const mi = +m - 1;
    return MONTHS[mi] ? +d + " " + MONTHS[mi] : "";
  }

  // lexicon: the admin rows; the default list is always applied after them.
  function speakable(text, lexicon) {
    let t = " " + String(text || "") + " ";
    // Machine noise first.
    t = t.replace(/https?:\/\/\S+/g, " ");
    t = t.replace(/\b10[XYZ][A-Z0-9-]{10,}\b/g, " ");                    // EIC codes
    t = t.replace(/\b(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?/g, (_, y, m, d) => isoDate(y, m, d));
    t = t.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (_, y, m, d) => isoDate(y, m, d));
    // Contracts: Win-26, Sum 27, Oct-26, Q1-27, Cal-27.
    t = t.replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|Win|Sum|Cal|Q[1-4])[- ]?(\d{2})\b/g,
      (_, a, y) => SHORT[a] + " " + y);
    // Temperatures: -5C, 12°C.
    t = t.replace(/(^|[\s(,])[-\u2212\u2013](\d+(?:\.\d+)?)\s?°?C(?![A-Za-z])/g, "$1minus $2 degrees");
    t = t.replace(/(\d)\s?°?C(?![A-Za-z])/g, "$1 degrees");
    // Prices per unit: £95.40/MWh, $1.60/MMBtu, €80/t, 95/MWh.
    t = t.replace(/([£€$])\s?(\d[\d,.]*)\s?\/\s?(MWh|therm|th|MMBtu|tonne|t)(?![A-Za-z])/g, (_, c, n, u) => n + " " + CUR[c] + " a " + PER[u]);
    t = t.replace(/(\d)\s?\/\s?(MWh|therm|MMBtu|tonne)(?![A-Za-z])/g, (_, n, u) => n + " per " + PER[u]);
    // Units written straight after the number: 18mcm/d, 1,200MW, 84.5p/th.
    t = t.replace(/(\d)(mcm\/d(?:ay)?|mcm|bcm|[MGT]Wh|[MG]W|p\/th(?:erm)?)(?![A-Za-z])/g, "$1 $2");
    // The pronunciation list: the admins' rows first, then the built-in one.
    compile(lexicon || [], "gi").forEach(([re, s]) => { t = t.replace(re, s); });
    compile(DEFAULT_LEXICON, "g").forEach(([re, s]) => { t = t.replace(re, s); });
    t = t.replace(/(\d)\s?\/\s?(?=[A-Za-z])/g, "$1 per ");                // $1.60/million B T U
    t = t.replace(/\bper (megawatt|gigawatt|terawatt) hours\b/g, "per $1 hour");
    // Signed moves: +3.2p, -6.8%, +0.41.
    t = t.replace(/(^|[\s(,])\+(\d[\d.,]*)\s?p\b(?!\.\w)/g, "$1up $2 pence");
    t = t.replace(/(^|[\s(,])[-−–](\d[\d.,]*)\s?p\b(?!\.\w)/g, "$1down $2 pence");
    t = t.replace(/(^|[\s(,])\+(\d[\d.,]*)\s?%/g, "$1up $2 percent");
    t = t.replace(/(^|[\s(,])[-−–](\d[\d.,]*)\s?%/g, "$1down $2 percent");
    t = t.replace(/(^|[\s(,])\+(\d[\d.,]*)/g, "$1up $2");
    t = t.replace(/(^|[\s(,])[-−–](\d[\d.,]*)/g, "$1down $2");
    t = t.replace(/(\d)\s?%/g, "$1 percent");
    t = t.replace(/(\d)\s?p\b(?!\.\w)/g, "$1 pence");                   // not 4 p.m.
    // "Down -3%" would say "down down".
    t = t.replace(/\b(up|down|rose|fell|rises|falls|gained|lost|dropped|climbed)\s+(up|down)\s+(?=\d)/gi, "$1 ");
    // Shouting capitals (PALUEL, HEYSHAM) read as a word, not spelt out.
    // Short ones (UK, LNG) are left to the list and the engine.
    t = t.replace(/\b[A-Z]{5,}\b/g, (w) => w.charAt(0) + w.slice(1).toLowerCase());
    // Punctuation into pauses.
    t = t.replace(/\s*[(\[]\s*/g, ", ").replace(/\s*[)\]]\s*/g, ", ");
    t = t.replace(/\s*:\s+/g, ". ").replace(/\s+[-–—]\s+/g, ", ");
    t = t.replace(/\s*;\s*/g, ". ");
    t = t.replace(/\s*,\s*(,\s*)+/g, ", ").replace(/,\s*\./g, ".").replace(/\s+([,.!?])/g, "$1");
    t = t.replace(/\s{2,}/g, " ").trim();
    return t.replace(/^[,.\s]+/, "").replace(/[,\s]+$/, "");
  }

  function sentence(s) {
    s = String(s || "").trim();
    if (!s) return "";
    return /[.!?]$/.test(s) ? s : s + ".";
  }

  function firstSentence(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    const m = s.match(/^(.{20,220}?[.!?])(\s|$)/);
    if (m) return m[1];
    return s.length > 220 ? s.slice(0, 220).replace(/\s+\S*$/, "") + "." : s;
  }

  /* build(item, opts) -> the words to say.
     item: { title, snippet, alert, update_count, supersedes, origin, script }
       an admin item may carry its own hand-written `script`; it is used as is
       (still through the pronunciation list).
     opts: { detail: bool, lexicon: [[written, said], ...] } */
  function build(item, opts) {
    opts = opts || {};
    const lex = opts.lexicon || [];
    if (item.script && String(item.script).trim()) return speakable(sentence(item.script), lex);
    const parts = [];
    if (item.alert === "critical") parts.push("Breaking.");
    else if (item.update_count || item.supersedes) parts.push("Update.");
    parts.push(sentence(speakable(item.title, lex)));
    if (opts.detail && item.snippet) {
      const d = speakable(firstSentence(item.snippet), lex);
      if (d) parts.push(sentence(d));
    }
    return parts.join(" ");
  }

  // Splits a script into chunks a browser voice can say without cutting out
  // (Chrome drops long utterances after about 15 seconds).
  function chunks(text, max) {
    max = max || 180;
    const out = [];
    String(text || "").split(/(?<=[.!?])\s+/).forEach((s) => {
      while (s.length > max) {
        let cut = s.lastIndexOf(", ", max);
        if (cut < 40) cut = s.lastIndexOf(" ", max);
        if (cut < 1) cut = max;
        out.push(s.slice(0, cut + 1).trim());
        s = s.slice(cut + 1).trim();
      }
      if (s) out.push(s);
    });
    return out;
  }

  return { build, speakable, chunks, firstSentence, DEFAULT_LEXICON };
});
