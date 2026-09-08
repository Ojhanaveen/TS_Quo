# Local Testing Log

This documents how the pipeline was actually verified after being built:
first against synthetic data, then against a real, live X/Twitter account.
Each bug below was hit during that process, on real runs, and fixed before
moving on -- kept here rather than smoothed over, since the debugging
process is itself evidence of how the system behaves under real conditions.

## 1. Setup and synthetic-data verification

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                              # unit tests, no network/browser needed
python scripts/generate_sample_data.py   # synthetic tweets -> full pipeline
```

This exercises every stage except real network I/O: cleaning, dedup,
Parquet storage, TF-IDF/sentiment signals, and chart rendering. Output
lands in `data/sample_output/` (committed to the repo).

## 2. Live scraping setup: obtaining and using a real session token

X's search results are behind a login wall, and the assignment forbids
paid/official APIs. The scraper authenticates by injecting a session
cookie from an account you already own -- no password is ever typed by
the automation.

**To get the token:**
1. Log into `x.com` normally, in your own browser.
2. Open DevTools (`Cmd+Option+I` on Mac).
3. Go to **Application** tab -> **Cookies** -> `https://x.com`.
4. Find the cookie named `auth_token` and copy its value.

**To use it:**
```bash
cp .env.example .env
```
Then edit `.env` directly (never `.env.example` -- see Bug 4 below) and set:
```
TWITTER_AUTH_TOKEN=<paste the value here>
```
`.env` is gitignored, so this value never gets committed or pushed. Then:
```bash
python scripts/run_scraper.py --hashtags nifty50 --count 50
```

## Bugs found during testing, and fixes

### Bug 1 -- Parquet append crashed with a schema mismatch

**Symptom:** `generate_sample_data.py` worked on a clean run, but running
it a second time (so `storage.write()` had to append to an existing
Parquet file) crashed:
```
pyarrow.lib.ArrowInvalid: Schema at index 1 was different:
... mentions: list<element: string> ...
vs
... mentions: list<item: string> ...
```

**Root cause:** `pa.concat_tables()` requires byte-identical schemas.
Arrow's `pa.list_(pa.string())` names its inner field `item`, but Parquet's
on-disk list encoding renames that field to `element` per the Parquet spec.
So a table just built in memory (`item`) never matched the same table read
back from disk after a round trip (`element`) -- guaranteed to fail on
every second run, not an intermittent issue.

**Fix:** stopped merging via `pa.concat_tables()` on raw pyarrow Tables.
Instead, both the existing and new data are converted to pandas, merged
with `pd.concat()` + `drop_duplicates(subset="tweet_id")`, and a single
canonical `pa.Table` is rebuilt from the combined DataFrame against our
own `SCHEMA` before writing. This sidesteps Arrow-level schema equality
entirely. (`src/processing/storage.py`)

### Bug 2 -- a phantom `date` column appeared on every read

**Symptom:** surfaced while diagnosing Bug 1 -- the "existing" schema in
the crash log had 16 fields, not 15; there was an extra
`date: dictionary<values=string, indices=int32, ordered=0>` column that
isn't in `SCHEMA` at all.

**Root cause:** Parquet partitions are stored as directories named
`date=2026-08-04` (Hive-style, intentional -- lets later analysis read one
date without scanning others). `pyarrow.parquet.read_table()` defaults to
`partitioning="hive"`, and it auto-detects that `key=value` folder-name
pattern and injects the key back in as a column on every read -- even when
reading one specific file, not a whole partitioned dataset.

**Fix:** pass `partitioning=None` explicitly on every `pq.read_table()`
call in `storage.py` (`write`'s append path, `read_partition`, `read_all`).

### Bug 3 -- StaleElementReferenceException during live scraping

**Symptom:** the very first real scrape against X (after Bugs 1-2 were
fixed and a real `auth_token` was supplied) got through login and started
finding tweets, then crashed:
```
selenium.common.exceptions.StaleElementReferenceException:
stale element reference: stale element not found in the current frame
```

**Root cause:** X virtualizes its timeline -- as you scroll, React
detaches DOM nodes that scroll out of the loaded window and may replace
ones still referenced. A Selenium element handle grabbed a moment earlier
can go stale before it's fully read.

**Fix:** wrapped per-article parsing in a `try/except
StaleElementReferenceException` at both the loop level (skip that article,
continue to the next) and inside `_parse_article`'s engagement-count
lookup, instead of letting one detached node kill the whole run.
(`src/scraper/twitter_scraper.py`)

### Bug 4 -- engagement counts (likes/retweets/replies) always read 0

**Symptom:** after Bug 3 was fixed, a full run completed successfully and
wrote real tweet data -- but every single row had `likes=0, retweets=0,
replies=0`, across 48 real tweets. Statistically implausible for genuine
X content.

**Root cause:** the selector (`div[data-testid='like'] span`) was reading
text out of whichever `<span>` happened to match first inside the action
button -- often a decorative/icon element with no text, not the count.

**Fix:** switched to reading the button's `aria-label` attribute instead
(e.g. `"1.2K Likes. Like"`), which X renders consistently regardless of
the internal DOM structure around the icon. Added a dedicated parser
(`_parse_aria_label_count`) with the old text-based read kept only as a
fallback, plus unit tests covering `K`/`M` suffixes, comma-formatted
numbers, and the genuine-zero case (`"Like"` with no leading number).
(`src/scraper/twitter_scraper.py`, `src/scraper/selectors.py`)

**Verified fixed:** re-ran the same scrape; engagement values were no
longer flat -- real (small but nonzero) counts appeared, consistent with
scraping the "Latest" (chronological, `f=live`) search tab, where tweets
are fresh and haven't had time to accumulate much engagement yet.

### Near-miss -- a live session token was pasted into the wrong file

Not a code bug, but part of the same testing session and worth recording:
the real `auth_token` was initially pasted into `.env.example` (the
template file that's committed to the public repo) instead of `.env` (the
gitignored file it was meant for). Caught before any commit or push --
verified via `git log --all -p -- .env.example | grep <token-prefix>`
that it had never entered git history. Fixed by reverting
`.env.example` to a blank placeholder and moving the value to `.env`.
As an extra precaution (the value had already appeared in a chat
transcript), the X session was logged out and back in to rotate the
cookie before continuing to test.

## Final live verification

After all four fixes, a full run across all four required hashtags:

```bash
python scripts/run_scraper.py --hashtags nifty50,sensex,intraday,banknifty --count 200
python scripts/run_pipeline.py
```

completed cleanly: 200 raw tweets collected, dedup correctly dropped 16
exact + 21 near-duplicates, engagement counts were real and varied
(up to 9 likes / 5 retweets / 9 replies on individual tweets), and the
signal generator produced 16 hourly (hashtag, window) sentiment rows with
correctly-behaving confidence intervals (single-tweet windows show a wide
interval; multi-tweet windows narrow appropriately). All three charts
(volume, sentiment signal with CI bands, engagement scatter) rendered
without error.

This live run's output was not committed to the repo (`data/processed/`
is gitignored by design, since it holds a specific run's real,
timestamped data rather than a stable demo artifact) -- the committed
`data/sample_output/` synthetic dataset remains the reproducible artifact
anyone cloning the repo can regenerate without needing their own X
account. This log is the record that the same pipeline was also verified
against real, live data.

## Follow-up testing: scaling toward the full 2,000/hashtag target

A later session pushed volume further to test whether the full
2,000-tweets-per-hashtag target is reachable in one run, and found a real
CLI bug (`--count` was silently split across hashtags) plus X's
anti-scraping defenses escalating sharply at higher volume. Full evidence,
root cause, the fix, and the recommended batched-collection approach to
reach the full target are in
[docs/FEASIBILITY.md](FEASIBILITY.md) -- that document is the direct
answer to "can this system do the full assignment volume."
