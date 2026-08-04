# Qode Market Intelligence

A data collection and analysis system for real-time Indian stock-market
sentiment on Twitter/X, built for the Qode Advisors technical assignment.

Pipeline: **scrape (Selenium, no paid APIs) -> clean/normalize -> deduplicate
-> store (Parquet) -> convert text to trading signals -> visualize**.

## Why this repo ships with synthetic sample data

X/Twitter now requires an authenticated session to view search results, and
this assignment explicitly forbids paid/official APIs. The scraper
(`src/scraper/twitter_scraper.py`) is fully implemented against real
`x.com` search and a Nitter-mirror fallback, but a real run needs a session
cookie from an account the operator owns (see "Live scraping" below) and
is meant to run unattended for up to 24 hours. Rather than run that inside
a review/CI environment, `scripts/generate_sample_data.py` generates a
schema-accurate **synthetic** dataset and pushes it through the exact same
clean -> dedup -> store -> analyze -> visualize pipeline that live-scraped
data goes through. Every stage downstream of collection is proven out on
real code paths; only the network I/O against x.com is swapped for
synthetic input. `data/sample_output/` contains the result of that run.

## Project structure

```
src/
  config.py                 # env-driven settings
  scraper/
    twitter_scraper.py      # Selenium scraper: X search + Nitter fallback
    rate_limiter.py         # sliding-window limiter + exponential backoff
    selectors.py            # CSS/XPath selectors, isolated for easy fixes
  processing/
    cleaner.py               # unicode normalization, URL stripping, cashtags
    deduplication.py         # exact (hash set) + near-dup (SimHash + LSH)
    storage.py                # partitioned Parquet read/write
  analysis/
    signal_generator.py       # TF-IDF + lexicon sentiment -> composite signal w/ CI
    visualization.py          # memory-efficient plotting (aggregation + reservoir sampling)
  utils/logger.py
scripts/
  run_scraper.py             # CLI: real scrape -> clean -> dedup -> store
  run_pipeline.py            # CLI: analyze + plot whatever's in data/processed/
  generate_sample_data.py    # synthetic data -> full pipeline (see above)
tests/                        # pytest unit tests
data/
  sample_output/              # output of generate_sample_data.py (committed)
  raw/, processed/             # gitignored; populated by real runs
docs/TECHNICAL_APPROACH.md    # design rationale, complexity, scalability plan
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TWITTER_AUTH_TOKEN for a real run (optional)
```

Requires Chrome/Chromium installed locally (Selenium drives it via
`webdriver-manager`, no manual driver download needed).

## Running

**Generate the sample dataset and analysis (no browser/network needed):**
```bash
python scripts/generate_sample_data.py
```
Writes to `data/sample_output/`: `sample_tweets_preview.csv`,
`sample_signals.csv`, three PNG charts, and the partitioned Parquet dataset.

**Run the test suite:**
```bash
pytest
```

**Live scraping** (requires your own X account's session cookie or a
working Nitter mirror -- see `.env.example`):
```bash
python scripts/run_scraper.py --hashtags nifty50,sensex,intraday,banknifty --count 2000
python scripts/run_pipeline.py   # analyze + plot data/processed/
```

## Approach summary

- **Collection**: Selenium against `x.com/search` (session-cookie auth, no
  password automation) with a Nitter-mirror fallback for when X blocks the
  session. A sliding-window rate limiter paces requests; failures trigger
  exponential backoff. Infinite scroll is bounded by both a target count
  and a stall detector so a dead selector can't hang the browser.
- **Cleaning**: NFC unicode normalization (Indic-script safe), URL/control
  character stripping, structured extraction of mentions/hashtags/cashtags.
- **Deduplication**: O(1) hash-set dedup on tweet ID, plus SimHash with
  multi-band LSH for near-duplicates (retweet-with-comment, copy-paste
  spam) -- see `docs/TECHNICAL_APPROACH.md` for why word-level SimHash
  fails on tweet-length text and how banding avoids an O(n^2) scan.
- **Storage**: Parquet, partitioned by date, snappy-compressed, written via
  PyArrow with an explicit schema.
- **Signals**: TF-IDF vectorization plus a sentiment lexicon tuned for
  Indian retail-trader slang (Hindi-English code-mixed terms like "tejji",
  "mandi"), aggregated into an engagement-weighted composite signal per
  hashtag/hour with a 95% confidence interval sized by effective sample
  count.
- **Visualization**: time-bucketed aggregation (not per-tweet plotting) and
  reservoir sampling keep chart memory usage flat regardless of dataset
  size.

Full design rationale and the 10x-scale plan are in
[docs/TECHNICAL_APPROACH.md](docs/TECHNICAL_APPROACH.md).

## Known limitations

- Live scraping wasn't run end-to-end against production X in this
  submission (see rationale above); the scraper code is complete and
  unit-testable logic (parsing, cleaning, dedup) is exercised by both
  the test suite and the synthetic-data pipeline.
- Nitter mirror availability is unpredictable (public instances churn);
  `NITTER_INSTANCES` in `.env` should be refreshed before a live run.
- The sentiment lexicon is a hand-built term list, not a trained model --
  documented as a deliberate scope choice in `docs/TECHNICAL_APPROACH.md`.
