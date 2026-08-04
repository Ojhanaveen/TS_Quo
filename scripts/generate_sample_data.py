"""Generates a synthetic sample dataset shaped exactly like real scraper
output, then runs it through the full clean -> dedup -> store -> analyze
-> visualize pipeline.

Why synthetic data instead of a live scrape for this submission: X now
requires an authenticated session to view search results, and running an
unattended 24-hour scrape against a real account isn't something to do
with someone else's credentials inside a review environment. This script
proves out every downstream stage (schema, cleaning, dedup, Parquet
storage, TF-IDF, sentiment aggregation, memory-efficient plotting) end to
end. Point `scripts/run_scraper.py` at a real TWITTER_AUTH_TOKEN (see
.env.example) to collect live data with the identical pipeline.
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.signal_generator import aggregate_signals, signals_to_dataframe
from src.analysis.visualization import (
    plot_engagement_sample_scatter,
    plot_signal_by_hashtag,
    plot_tweet_volume,
)
from src.config import DATA_SAMPLE_DIR, HASHTAGS
from src.processing.cleaner import clean_batch
from src.processing.deduplication import Deduplicator
from src.processing.storage import ParquetStorage
from src.scraper.twitter_scraper import RawTweet, extract_hashtags, extract_mentions

random.seed(7)

USERNAMES = [
    "traderraj", "niftybull_99", "punediscussions", "bankniftywolf",
    "aparna.invests", "dalalstreet_desi", "quant_karan", "sensexqueen",
    "intraday_ishaan", "vfm_vikram", "chartguru_cs", "options_ojasvi",
]

BULLISH_TEMPLATES = [
    "{tag} looking strong today, broke resistance with volume. Target {tgt}. #{tag}",
    "Bought {stock} on the dip, expecting upper circuit tomorrow. #{tag}",
    "{tag} bullish structure intact, support held well at open. Tejji ka mood hai! #{tag}",
    "Gap up expected in {stock} after strong global cues. Long term buy. #{tag}",
    "{stock} hit all time high, momentum still building. #{tag} #{tag2}",
]
BEARISH_TEMPLATES = [
    "{tag} breakdown below key support, booking losses. SL hit. #{tag}",
    "Sold {stock} today, downside looks likely given weak breadth. #{tag}",
    "{tag} bearish, mandi ka mahaul hai, better to stay in cash. #{tag}",
    "Profit booking in {stock}, correction due after the recent rally. #{tag}",
    "Lower circuit hit in {stock}, panic selling visible. #{tag} #{tag2}",
]
NEUTRAL_TEMPLATES = [
    "Watching {stock} closely ahead of results, no clear direction yet. #{tag}",
    "{tag} range-bound today, waiting for a breakout either side. #{tag}",
    "Anyone tracking {stock} today? Volumes look average. #{tag}",
    "Market update: {tag} flat, participants cautious before RBI policy. #{tag}",
]

STOCKS = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN", "TATAMOTORS", "ADANIENT"]


def _rand_timestamp(hours_back: int = 24) -> str:
    delta = timedelta(
        hours=random.uniform(0, hours_back), minutes=random.uniform(0, 59)
    )
    ts = datetime.now(timezone.utc) - delta
    return ts.isoformat()


def _make_tweet(idx: int, tag: str, force_duplicate_of=None) -> RawTweet:
    if force_duplicate_of is not None:
        content = force_duplicate_of
    else:
        bucket = random.choices(
            [BULLISH_TEMPLATES, BEARISH_TEMPLATES, NEUTRAL_TEMPLATES],
            weights=[0.4, 0.35, 0.25],
        )[0]
        template = random.choice(bucket)
        other_tag = random.choice([h for h in HASHTAGS if h != tag] or [tag])
        content = template.format(
            tag=tag,
            tag2=other_tag,
            stock=random.choice(STOCKS),
            tgt=f"{random.randint(100, 900) * 10}",
        )
        if random.random() < 0.15:
            content += " @" + random.choice(USERNAMES)

    return RawTweet(
        tweet_id=f"synthetic-{tag}-{idx}",
        username=random.choice(USERNAMES),
        timestamp=_rand_timestamp(),
        content=content,
        likes=random.randint(0, 5000),
        retweets=random.randint(0, 1200),
        replies=random.randint(0, 300),
        mentions=extract_mentions(content),
        hashtags=extract_hashtags(content),
        source="synthetic",
        search_hashtag=tag,
    )


def generate_raw_tweets(n_per_hashtag: int = 130) -> list:
    tweets = []
    idx = 0
    for tag in HASHTAGS:
        for _ in range(n_per_hashtag):
            tweets.append(_make_tweet(idx, tag))
            idx += 1
        # inject some exact + near duplicates to exercise the dedup layer
        dup_source = tweets[-1]
        for _ in range(4):
            tweets.append(
                RawTweet(**{**dup_source.__dict__, "tweet_id": dup_source.tweet_id})
            )
        for _ in range(4):
            near = tweets[-1].content + " " + random.choice(["!!", "🔥", "check now"])
            tweets.append(_make_tweet(idx, tag, force_duplicate_of=near))
            idx += 1
    random.shuffle(tweets)
    return tweets


def main():
    print("Generating synthetic sample tweets...")
    raw = generate_raw_tweets()
    print(f"  {len(raw)} raw tweets generated (includes injected duplicates)")

    cleaned = clean_batch(raw)

    dedup = Deduplicator()
    unique = dedup.dedup_batch(cleaned)
    print(f"  dedup stats: {dedup.stats}")

    storage = ParquetStorage(base_dir=DATA_SAMPLE_DIR / "parquet")
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = storage.write(unique, partition_date)
    print(f"  wrote {out_path}")

    df = storage.read_partition(partition_date)
    csv_preview = DATA_SAMPLE_DIR / "sample_tweets_preview.csv"
    df.head(50).to_csv(csv_preview, index=False)
    print(f"  wrote preview CSV: {csv_preview}")

    signals = aggregate_signals(df, window="1h")
    signals_df = signals_to_dataframe(signals)
    signals_csv = DATA_SAMPLE_DIR / "sample_signals.csv"
    signals_df.to_csv(signals_csv, index=False)
    print(f"  wrote {len(signals_df)} signal rows: {signals_csv}")

    plot_tweet_volume(df, str(DATA_SAMPLE_DIR / "tweet_volume.png"))
    if not signals_df.empty:
        plot_signal_by_hashtag(signals_df, str(DATA_SAMPLE_DIR / "sentiment_signal.png"))
    plot_engagement_sample_scatter(df, str(DATA_SAMPLE_DIR / "engagement_scatter.png"))
    print(f"  wrote charts to {DATA_SAMPLE_DIR}")

    print("Done.")


if __name__ == "__main__":
    main()
