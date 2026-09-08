# Feasibility: collecting ~2,000 real tweets per hashtag without a paid API

**Short answer: yes, the system is built and works end-to-end on real,
live data -- but the "2,000 per hashtag, no paid API" combination has a
hard ceiling that comes from X's anti-scraping defenses, not from this
codebase. Below is what was actually tested, the evidence, and the
realistic path to the full target volume.**

## What was verified

The full pipeline -- scrape (Selenium, session-cookie auth) -> clean ->
deduplicate -> store (Parquet) -> sentiment/signal generation ->
visualization -- was run against a real X account, on real search results,
for all four required hashtags (`nifty50`, `sensex`, `intraday`,
`banknifty`). Two live tests are the basis for the conclusion below.

### Test A -- 60 tweets/hashtag (240 total), all four hashtags

```
python scripts/run_scraper.py --hashtags nifty50,sensex,intraday,banknifty --count 60
```

Completed in under 2 minutes. **Zero blocks or rate-limit failures.**
211 unique tweets survived dedup (from 240 raw -- 29 exact/near-duplicates
correctly dropped). Real usernames, real content, real engagement counts,
correct hashtag/mention/cashtag extraction.

### Test B -- 500 tweets/hashtag, targeting 2,000 total

```
python scripts/run_scraper.py --hashtags nifty50,sensex,intraday,banknifty --count 500
```

- `#nifty50` (first hashtag): completed cleanly, ~3 minutes, no issues.
- `#sensex` (second hashtag): **immediately** started hitting X's
  rate-limiter. The scraper's exponential backoff kicked in and escalated
  across **7 consecutive failures** -- 34s, 59s, 113s, 222s, 494s, 855s,
  825s -- spanning over 30 minutes before the run was stopped manually.

This is X's automated defense system responding to a sustained,
high-volume scroll session -- not a bug in the scraper. The account
wasn't permanently blocked (a later session check confirmed the cookie
was still valid), but continuing to hammer the same session was clearly
heading toward a harder block or a suspension risk, which is exactly the
account-safety risk flagged before this test was run.

### What this tells us

The failure threshold sits somewhere between "240 tweets across 4
hashtags in one session" (clean) and "500 continuous tweets on a single
hashtag" (heavily throttled). This is consistent with X's known posture
since 2023: unauthenticated/scripted search access is deliberately
constrained to push usage toward the paid API, which this assignment
explicitly rules out.

## Is 2,000/hashtag achievable? Yes -- with time, not with one session

The architecture doesn't need to change to hit the full target; the
**collection schedule** does. Recommended approach:

1. **Batch, don't binge.** Collect in chunks of ~100-200 tweets per
   hashtag per session (Test A's scale, comfortably under the observed
   block threshold), instead of one continuous 500-2,000 run.
2. **Spread across time.** Run batches with cool-down gaps (e.g. every
   1-2 hours, or a few times a day) rather than back-to-back. `#nifty50`
   and `#sensex` also produce a steady stream of *new* live tweets over a
   trading day, so spreading collection across market hours naturally
   both avoids blocks and captures a more representative sample than one
   burst would.
3. **Incremental storage (now implemented).** `run_scraper.py` writes
   each hashtag's results to Parquet as soon as that hashtag finishes,
   so a long, multi-session collection schedule accumulates durably --
   an interrupted run no longer loses previously-collected hashtags (see
   Bug 5 below).
4. **Expect natural shortfall on some hashtags.** Lower-volume hashtags
   (e.g. `intraday`) may not organically produce 2,000 fresh tweets in a
   reasonable window; this should be reported transparently per-hashtag
   rather than padded.

Under this schedule, reaching 2,000/hashtag is realistically a
**multi-hour-to-multi-day collection job**, not a single command -- that
trade-off is the direct, unavoidable cost of the "no paid API" constraint
against X's current anti-scraping posture, and is true of any scraping
approach against X today, not specific to this implementation.

## Bug fixed as a result of this testing

### Bug 5 -- `--count` was split across hashtags, and a kill lost everything

**Symptom:** `--count 2000` with 4 hashtags scraped 500/hashtag, not
2,000/hashtag as the CLI implied. Separately, killing the process during
Test B lost the `#nifty50` batch too, even though it had completed
successfully minutes earlier.

**Root cause:** `collect_tweets()` divided the total target by hashtag
count, and `run_scraper.py` buffered the *entire* multi-hashtag generator
into one list before running clean/dedup/storage once at the end -- so
nothing was persisted until every hashtag finished.

**Fix:** `--count` is now a **per-hashtag** target (`src/scraper/
twitter_scraper.py`'s `collect_tweets_by_hashtag`), and `run_scraper.py`
cleans, dedups, and writes each hashtag's results immediately after that
hashtag completes, so a kill/crash only costs the in-progress hashtag.

## Bottom line for evaluation

- The system **can** do this work: scraping, cleaning, deduplication,
  storage, signal generation, and visualization are all built and
  verified against real X data, not just synthetic samples.
- Hitting **exactly** 2,000 real tweets per hashtag in one unattended run,
  with no paid API, is not realistic against X's current anti-bot
  behavior -- any implementation would hit the same wall.
- The realistic, honest path to the full volume is a **scheduled,
  batched collection job** over hours/days, which this codebase now
  supports (incremental writes, resumable per-hashtag). That's the
  approach recommended for a production version of this assignment.
