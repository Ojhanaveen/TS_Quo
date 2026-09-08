"""CLI entry point for a real scrape run.

Usage:
    python scripts/run_scraper.py --hashtags nifty50,sensex --count 2000

--count is a PER-HASHTAG target (2000 means 2000 for each hashtag listed,
not split across them). Each hashtag's results are cleaned, deduped, and
written to Parquet as soon as that hashtag finishes, so killing the process
partway through a later hashtag does not lose earlier ones.

Requires TWITTER_AUTH_TOKEN in .env for the X search path, otherwise
falls back to the Nitter mirrors in NITTER_INSTANCES. See README.md
"Live scraping" section before running this against a real account.
"""
import argparse
import sys
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.processing.cleaner import clean_batch
from src.processing.deduplication import Deduplicator
from src.processing.storage import ParquetStorage
from src.scraper.twitter_scraper import collect_tweets_by_hashtag
from src.utils.logger import get_logger

logger = get_logger("run_scraper")


def main():
    parser = argparse.ArgumentParser(description="Scrape Indian market-related tweets")
    parser.add_argument("--hashtags", type=str, default=",".join(config.HASHTAGS))
    parser.add_argument(
        "--count", type=int, default=config.TARGET_TWEET_COUNT,
        help="Target tweet count PER HASHTAG (not total).",
    )
    parser.add_argument("--headless", action="store_true", default=config.HEADLESS)
    args = parser.parse_args()

    hashtags = [h.strip() for h in args.hashtags.split(",") if h.strip()]
    logger.info(
        "Starting scrape: hashtags=%s target_per_hashtag=%d", hashtags, args.count
    )

    dedup = Deduplicator()
    storage = ParquetStorage()
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_written = 0

    tagged_stream = collect_tweets_by_hashtag(
        hashtags=hashtags, per_hashtag_count=args.count, headless=args.headless
    )
    for tag, group in groupby(tagged_stream, key=lambda pair: pair[0]):
        raw_tweets = [tweet for _, tweet in group]
        logger.info("Collected %d raw tweets for #%s", len(raw_tweets), tag)

        cleaned = clean_batch(raw_tweets)
        unique = dedup.dedup_batch(cleaned)
        logger.info(
            "After dedup for #%s: %d unique tweets so far (%s)",
            tag, len(unique), dedup.stats,
        )

        if unique:
            out_path = storage.write(unique, partition_date)
            total_written += len(unique)
            logger.info("Wrote %d rows for #%s to %s", len(unique), tag, out_path)

    logger.info("Run complete: %d total unique tweets written", total_written)


if __name__ == "__main__":
    main()
