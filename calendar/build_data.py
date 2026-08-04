"""Merge the historic and forward CSVs into the single feed the pane consumes.

Run after every scanner refresh:  python build_data.py
Reads   data/calendar.csv          the fixed historic file, never regenerated
        data/forward_calendar.csv  the scanner output, refreshed weekly
Writes  data/events.json           one chronological array
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
def path(*p): return os.path.join(HERE, *p)

FIELDS = ("date time region category title detail energy_relevance fuel_scope "
          "source_url cadence notes status").split()

def read(fn, default_status):
    out = []
    with open(path("data", fn), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            out.append({
                "d":  (r.get("date") or "").strip(),
                "t":  (r.get("time") or "").strip(),
                "rg": (r.get("region") or "").strip(),
                "c":  (r.get("category") or "").strip(),
                "ti": (r.get("title") or "").strip(),
                "de": (r.get("detail") or "").strip(),
                "er": (r.get("energy_relevance") or "").strip(),
                "f":  (r.get("fuel_scope") or "").strip(),
                "u":  (r.get("source_url") or "").strip(),
                "cd": (r.get("cadence") or "").strip(),
                "n":  (r.get("notes") or "").strip(),
                "st": (r.get("status") or default_status).strip(),
                "src": default_status and "forward" or "historic",
            })
    return out

def main():
    hist = read("calendar.csv", "")
    for h in hist:
        h["st"], h["src"] = "occurred", "historic"
    fwd = read("forward_calendar.csv", "scheduled")
    for f in fwd:
        f["src"] = "forward"

    rows = hist + fwd
    rows.sort(key=lambda x: (x["d"], x["t"] or "99:99", x["ti"]))

    seen, dupes = set(), []
    for r in rows:
        k = (r["d"], r["ti"])
        if k in seen:
            dupes.append(k)
        seen.add(k)
    if dupes:
        sys.stderr.write("duplicate date plus title, refusing to build: %r\n" % dupes[:5])
        return 1

    with open(path("data", "events.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, separators=(",", ":"), ensure_ascii=False)
    print("historic %d  forward %d  total %d -> data/events.json"
          % (len(hist), len(fwd), len(rows)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
