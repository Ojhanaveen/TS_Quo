# Technical Approach

## Collection strategy and constraints

The assignment forbids paid/official APIs. X's public search has been
behind a login wall since 2023, so "no paid API" in practice means one of:
(a) automate a real login form, (b) inject a session cookie from an
account the operator already controls, or (c) use a login-free mirror.

This repo does (b) as the primary path and (c) (Nitter) as a fallback:

- `XSearchScraper` navigates to `x.com`, sets the `auth_token` cookie from
  `TWITTER_AUTH_TOKEN`, and scrapes the "Latest" search tab. No password is
  ever typed by the automation -- the cookie is lifted from the operator's
  own already-authenticated browser session (see `.env.example`).
- `NitterScraper` hits open-source Nitter mirror instances, which serve
  Twitter content without a login wall. Used automatically when no auth
  token is configured, and as a natural fallback target if X starts
  blocking the session mid-run.

Both scrapers share a `RawTweet` output shape so everything downstream
(cleaning, dedup, storage, analysis) is source-agnostic.

## Anti-bot / rate limiting

`RateLimiter` (`src/scraper/rate_limiter.py`) combines two mechanisms:

1. **Sliding window** (`collections.deque` of request timestamps, O(1)
   amortized push/evict): caps requests per 15-minute window, forcing a
   wait once the cap is hit rather than firing requests as fast as
   possible.
2. **Exponential backoff on failure**: a detected block, CAPTCHA, or empty
   response doubles a backoff timer (base 30s, capped at 15min, with
   jitter) so repeated failures back off instead of hammering the
   endpoint.

The Selenium driver is also configured with a realistic user agent, the
`navigator.webdriver` flag suppressed via a CDP injected script, and
randomized human-like delays between scroll actions.

## Deduplication: complexity and correctness

Two layers, chosen for the accuracy/cost trade-off at target scale
(thousands to tens of thousands of tweets per run):

1. **Exact dedup on tweet ID** -- a Python `set`, O(1) average lookup and
   insert, O(n) total. Catches the same tweet appearing in more than one
   hashtag search (a tweet tagged both `#nifty50` and `#banknifty`).

2. **Near-duplicate dedup via SimHash** -- catches retweet-with-comment,
   copy-paste "tip" spam, and bot networks posting near-identical text
   with small variations.

   - **Shingling choice**: an early version tokenized on whole words,
     which fails on tweet-length text -- a single added or edited word can
     be a large fraction of a ~20-word tweet's tokens, so the fingerprint
     swings far more than the intended "near" duplicate should. Switching
     to overlapping 4-character shingles (the standard construction for
     near-dup detection on short documents) spreads each edit's influence
     over only the shingles that touch it, so a punctuation change or one
     added word moves the fingerprint by a handful of bits instead of
     dozens.
   - **Sub-linear candidate lookup**: comparing every new tweet's
     fingerprint against all previously seen fingerprints is O(n) *per
     tweet* (O(n^2) total), which doesn't scale. We use multi-band LSH
     instead: the 64-bit fingerprint is split into 8 non-overlapping
     8-bit bands, each indexed in its own dict (`band_value -> [(fp, id)]`).
     A new tweet is only compared against tweets sharing at least one band
     value -- Hamming-close fingerprints are overwhelmingly likely to
     match in at least one band, so recall stays high while the average
     candidate set per tweet stays small and roughly constant, independent
     of how many tweets have been seen so far.

## Handling Indian-language / code-mixed content

Indian market Twitter is heavily code-mixed (Hindi-English, occasional
other Indic scripts, emoji, `$CASHTAGS`). `cleaner.py`:

- NFC-normalizes text so visually-identical Devanagari sequences typed via
  different input methods compare and hash equal (important for both
  dedup and TF-IDF).
- Strips URLs and control characters without touching non-Latin script
  (no "keep only ASCII" shortcut, which would silently delete Hindi
  content).
- Extracts hashtags, `@mentions`, and `$CASHTAGS` into structured fields
  rather than stripping them from the body, so they remain available as
  features.
- The sentiment lexicon (`signal_generator.py`) includes common
  Hindi-English code-mixed trading slang ("tejji"/bullish, "mandi"/bearish)
  alongside English terms, rather than assuming English-only input.

## Text-to-signal conversion

- **TF-IDF** (`build_tfidf_matrix`): unigrams + bigrams, English stop
  words removed, `min_df=2` to drop hapax noise -- the standard
  sparse-feature baseline for downstream ML (e.g. feeding a classifier),
  included per the assignment's "TF-IDF, word embeddings, or custom
  feature engineering" requirement.
- **Lexicon sentiment** (`lexicon_sentiment`): a hand-built bullish/bearish
  term list scored as `(bull_hits - bear_hits) / total_hits`, in `[-1, 1]`,
  `0` when no lexicon term is present. Chosen over a pretrained sentiment
  model because generic English sentiment models don't recognize
  market-specific and code-mixed terms ("upper circuit," "tejji") that
  carry the actual directional signal here. A production version would
  train a supervised classifier on labeled market tweets; this is
  explicitly a scoped-down baseline, documented rather than disguised.
- **Signal aggregation** (`aggregate_signals`): tweets are grouped by
  `(hashtag, hour)`. Sentiment is weighted by `log1p(engagement)` so
  high-engagement tweets influence the composite more without letting one
  viral tweet dominate linearly. The weighted mean's confidence interval
  uses the *effective sample size* under weighting
  (`(sum(w))^2 / sum(w^2)`), not the raw tweet count -- so a window
  dominated by one heavily-weighted tweet correctly gets a wide interval
  even if it technically contains many tweets.

## Memory-efficient visualization

`visualization.py` avoids ever materializing "one point per tweet" in a
plot:

- Volume and signal charts aggregate first (`pandas.resample` /
  `groupby`), so the plotted array size is O(number of time buckets), not
  O(number of tweets) -- flat memory regardless of input size.
- The one plot that needs individual points (likes vs. retweets scatter)
  uses **reservoir sampling**: a fixed-size reservoir is maintained while
  streaming rows once (`O(k)` memory, `O(n)` time, single pass, unbiased
  sample), so it stays bounded even against a dataset far too large to
  plot directly.

## Concurrency

`RawTweet` generation, cleaning, and dedup are structured as independent
per-item functions specifically so they can be parallelized: cleaning
(`clean_batch`) is pure and side-effect-free per tweet, making it a direct
fit for `concurrent.futures.ProcessPoolExecutor` if CPU-bound cleaning of
large batches becomes the bottleneck. Scraping itself is I/O-bound and
already the slow path; the natural parallelism there is one Selenium
driver instance per hashtag (bounded by target machine's CPU/RAM, since
each is a full browser process) rather than one driver per tweet.

## Scaling to 10x data

- **Storage**: already partitioned by date in Parquet; a 10x run adds
  `search_hashtag` as a second partition key so per-hashtag analysis reads
  don't scan irrelevant partitions.
- **Dedup**: the LSH band structure's memory is O(unique tweets), which at
  10x scale (tens of thousands to ~100K+ tweets/day) still fits in
  process memory; beyond that, band buckets would move to Redis (shared,
  TTL-evictable) so multiple scraper processes can dedup against a common
  index instead of each holding an in-memory copy.
- **Processing**: `clean_batch`/`dedup_batch` currently operate on Python
  lists in memory; at 10x this would move to chunked processing (read a
  Parquet row-group at a time via `pyarrow.dataset`) so peak memory stays
  bounded instead of scaling with total dataset size.
- **Collection**: multiple hashtags already scrape independently; at 10x
  volume this parallelizes across worker processes (one Selenium instance
  each) coordinated through a shared rate limiter (Redis-backed token
  bucket) so the *aggregate* request rate across workers still respects
  X/Nitter's tolerance, not just each worker's individual rate.
