# Future Enhancements

Notes on what this project could grow into, and the trade-offs involved.
None of this is built -- it's a record of directions considered while
working on the assignment, kept honest about cost, not just upside.

## 1. Move from batch to a streaming pipeline (Redis + TimescaleDB + WebSockets)

**What it is now:** a batch job. Run the scraper, it writes a Parquet
file, then a separate step reads that file and computes signals. Nothing
updates until you run it again.

**What it could be:** the scraper keeps polling instead of running once,
pushing new tweets onto a Redis stream as they're found. A worker
consumes that stream, computes the signal update incrementally, and
writes into TimescaleDB instead of a Parquet file (better fit for
"give me the last hour of this signal" queries than reading a whole
partition back into pandas). A small WebSocket endpoint lets a dashboard
subscribe to signal updates as they happen instead of polling a file.

**Trade-offs:**
- Real added complexity: now there's a queue, a long-running worker
  process, and a database server to operate, instead of "run a script,
  read a file."
- Parquet's columnar compression and partition pruning are genuinely
  better than TimescaleDB for *bulk* analytical reads (e.g. "give me
  every tweet from the last 30 days for a research notebook"). This
  isn't a strict upgrade -- it's a different tool for a different access
  pattern (live small reads vs. bulk analytical reads), so a real version
  of this would probably keep both: TimescaleDB for the live signal,
  periodic Parquet exports for research/backtesting.
- Only worth doing if something is actually consuming the signal live.
  For a one-off analysis run, this is pure overhead.

## 2. Backtest the signal against real price data

**What it is now:** the pipeline produces a composite sentiment signal
per hashtag per hour. Nothing checks whether that signal means anything.

**What it could be:** pull historical Nifty/BankNifty price data (NSE
public data, or `yfinance` as a free source) and, for each signal window,
check whether the sign of the signal matched the direction of the next
interval's price move. Basic version: a hit rate. Slightly better
version: an information coefficient (correlation between signal strength
and forward return) so a weak-but-consistent signal isn't dismissed just
because its hit rate is close to 50%.

**Trade-offs:**
- This is the difference between "text got turned into a number" and
  "the number is worth anything," so it's probably the highest-value
  addition of the three -- but it's also the easiest to get quietly
  wrong. Naive backtests leak information (using a close price that
  wouldn't have been known yet, picking a lookback window post-hoc
  because it happens to work) and produce a number that looks good and
  means nothing. Doing this properly needs a clear point-in-time
  discipline, which is more design work than the pipeline code itself.
- A hashtag-level daily/hourly signal is a coarse, noisy input to
  backtest against 1-minute price bars in the first place -- worth being
  upfront that a believable result here would take real iteration, not
  a first pass.
- Needs a second free data source (price history) with its own
  reliability/rate-limit questions, same category of problem as the
  tweet scraping itself.

## 3. Co-mention graph for spotting coordinated activity

**What it is now:** each tweet is scored independently. Nothing looks at
the relationship *between* tweets or accounts.

**What it could be:** build a graph (a plain `networkx` graph, no new
database) connecting accounts/hashtags/stocks that get mentioned together
within a short time window, then run community detection to surface
tight clusters -- a handful of accounts posting near-identical bullish
content about the same obscure ticker in a burst looks different in this
graph than organic, spread-out discussion does. This is a real pattern
in Indian retail markets (SEBI has taken action on coordinated
social-media-driven pump schemes), so it's not a hypothetical use case.

**Trade-offs:**
- Cheapest of the three to prototype -- no new infrastructure, reuses
  data already being collected.
- But also the easiest to produce false positives with: organic viral
  content (a stock actually does move, and people organically talk about
  it at the same time) looks structurally similar to coordinated posting
  without more signal (account age, posting history, network centrality
  over time) than a single scrape captures. As a standalone score this
  would need real validation against known cases before trusting it;
  as an exploratory/visualization tool (surfacing clusters for a human
  to look at, not auto-flagging) it's useful immediately.

## Why none of these are in the current submission

The assignment's scope is the collection -> clean -> dedup -> store ->
signal -> visualize pipeline, done well and honestly, on real data within
the time given. All three of the above are legitimate next steps *if*
this were becoming a real, ongoing system rather than a scoped
assignment -- but each adds either new infrastructure (#1), a
correctness-sensitive research problem that deserves more than a rushed
first pass (#2), or a technique that needs validation before it's
trustworthy (#3). Listing them here is meant to show the direction this
could go, not to quietly smuggle half-built versions of them into the
submission.
