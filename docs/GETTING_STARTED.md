# Getting started

Written for someone who has not run a Python script before. If a step already
looks obvious, skip it.

You need to do this once. After it is deployed to GitHub it runs on its own and
you never touch the terminal again.

---

## 1. Put the folder somewhere sensible

Unzip the handover pack. Move the `pes-newsfeed` folder somewhere you can find
it, for example `C:\Users\<you>\Documents\pes-newsfeed`.

Avoid OneDrive-synced folders if you can. Sync can lock files mid-run and
produce errors that look like bugs in the script.

## 2. Check whether Python is installed

**Windows:** press Start, type `powershell`, press Enter. In the blue window:

    python --version

**Mac:** press Cmd+Space, type `terminal`, press Enter. Then:

    python3 --version

You want a reply like `Python 3.12.1`. Anything 3.10 or above is fine.

If instead you get an error, or Windows opens the Microsoft Store, install
Python from python.org/downloads. **On Windows, tick "Add Python to PATH" on
the first screen of the installer.** It is easy to miss and nothing works
without it. Close PowerShell, open it again, and re-run the version check.

## 3. Point the terminal at the folder

    cd "C:\Users\<you>\Documents\pes-newsfeed"

On Mac:

    cd ~/Documents/pes-newsfeed

Shortcut: type `cd ` (with the space), then drag the folder from Explorer or
Finder onto the terminal window. It fills in the path for you.

To confirm you are in the right place, run `dir` on Windows or `ls` on Mac.
You should see `README.md`, `config`, `src` and `web` listed.

## 4. Install the two libraries it needs

    pip install -r requirements.txt

On Mac, use `pip3` instead of `pip`.

This downloads two small packages, feedparser and requests. It prints a lot of
text. As long as the last line does not say `ERROR`, it worked.

## 5. Put your API key in

Run this:

    python src/ingest.py --check

The first time, it will tell you it has created a file for you and print its
full location, something like:

    No .env file found, so one has been created for you:

       C:\Users\you\Documents\pes-newsfeed\.env

Open that file in Notepad, paste your AGSI key after `AGSI_KEY=`, and save:

    AGSI_KEY=a1b2c3d4e5f6
    ENTSOE_TOKEN=

No quotes, no spaces around the `=`. Leave the ENTSOE line empty until that
token arrives.

If Notepad will not open it because Windows does not recognise the file type:
right-click the file, Open with, Choose another app, Notepad.

If you cannot see the file in Explorer at all, it is because names beginning
with a dot are hidden by some tools. It is there; the script just printed the
path. On a Mac, press Cmd+Shift+. in Finder to reveal hidden files.

Then run the same command again and it will confirm:

    AGSI_KEY       found    (GIE AGSI+ storage)
    ENTSOE_TOKEN   NOT SET  (ENTSO-E outages)

## 6. Add your Nord Pool feed

Run:

    python src/configure.py

It asks for each URL in turn. Paste your Nord Pool one when prompted, press
Enter to skip the rest, and it switches on everything that is ready.

You do not need to edit any files by hand. The script validates the config
before saving, so a stray comma cannot break anything.

Run it again any time you get another URL.

## 7. Test it

    python src/ingest.py --check

You should see your keys confirmed, then a table of every source and whether it
worked.

| Status   | Meaning                                                    |
|----------|------------------------------------------------------------|
| `OK`     | Working, and returned items                                |
| `EMPTY`  | Reachable but returned nothing. Often fine on a quiet feed |
| `FAIL`   | Broken. The error is printed alongside                     |
| `NO URL` | Needs a URL pasting in                                     |
| `OFF`    | Deliberately inactive                                      |

**Some FAILs are expected.** I could not test the publisher RSS URLs from my
end, so two or three will need correcting or switching off. That is what this
step is for, it is not a sign anything is wrong.

## 8. Run it for real

    python src/ingest.py
    python build_demo.py

Then open `web/PES_News_Drawer_DEMO.html` by double-clicking it.

That is your live feed, with real headlines. Read the top twenty and decide
whether the ranking is right.

---

## If something goes wrong

**`python is not recognised`** — Python is not installed, or the PATH box was
not ticked during install. Reinstall from python.org and tick it.

**`pip is not recognised`** — try `python -m pip install -r requirements.txt`.

**`No such file or directory`** — you are not in the project folder. Go back to
step 3.

**`ModuleNotFoundError: No module named 'feedparser'`** — step 4 did not
complete. Run it again and read the last few lines.

**`AGSI_KEY NOT SET`** — the `.env` file is misnamed, in the wrong folder, or
saved as `.env.txt`. It must sit in the same folder as `README.md`.

**`JSONDecodeError`** — a typo in `config/sources.json`, usually a missing or
extra comma. The message names the line number.

Whatever the error, paste the last ten lines to me and I will tell you what it
means.
