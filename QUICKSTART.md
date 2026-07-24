# Quickstart

## Windows

Double-click **START_HERE.bat**

## Mac

Open Terminal, then:

    cd <drag the folder here>
    python3 START_HERE.py

---

That is it. The script does everything else and tells you what it needs.

It runs in two parts. Part 1 is an offline test that proves the machinery
works and shows you the widget, with no keys and no internet. Part 2 sets up
the live feed using your API keys.

You can stop after Part 1 and come back later. Running it again is always safe.

## Where your keys and URLs go

You do not have to find anything. The script asks you for both, in order:

1. **API keys** (AGSI, ENTSO-E) go in a file called `.env`. The script creates
   it, prints the full path, and waits while you paste your keys in and save.
2. **Feed URLs** (Nord Pool and any others) are typed straight into the script
   when it prompts you.

Press Enter to skip anything you have not got yet. Missing sources are simply
left out; nothing breaks. Run the script again later to add them.

Everything else in this folder is reference material:

| File                       | What it is                                |
|----------------------------|-------------------------------------------|
| `docs/GETTING_STARTED.md`  | The same steps, explained slowly           |
| `docs/BUILD_BRIEF.md`      | For Krys, when you hand it over            |
| `docs/DATA_SPEC.md`        | The JSON contract for the widget           |
| `README.md`                | How the whole thing works                  |
| `config/themes.json`       | What counts as relevant. The file you tune |

## Sorting

The drawer opens sorted by **Priority**, highest score first. The **Recent**
button re-sorts by time, newest first. It is a display choice only: scores and
alert levels do not change.
