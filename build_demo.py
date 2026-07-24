#!/usr/bin/env python3
"""Inject the current news.json into widget.html to produce a standalone demo.

Two hardening details, both prompted by real feed content rather than theory:

- The JSON goes in via a lambda, never as a re.sub replacement string. In a
  replacement string, backslash sequences are reinterpreted, and real
  headlines contain quotes that json-escape to backslash sequences.
- "</" is escaped to "<\\/" inside the JSON. A headline containing
  "</script>" would otherwise terminate the script tag mid-file.
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).parent
data = json.loads((ROOT / "data" / "news.json").read_text())
html = (ROOT / "web" / "widget.html").read_text()

payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
out = re.sub(
    r"/\*__DATA__\*/.*?/\*__ENDDATA__\*/",
    lambda m: "/*__DATA__*/ " + payload + " /*__ENDDATA__*/",
    html, flags=re.S,
)
target = ROOT / "web" / "PES_News_Drawer_DEMO.html"
target.write_text(out)
print(f"wrote {target} ({len(out)/1024:.0f} KB, {data['item_count']} items)")
