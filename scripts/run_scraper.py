"""CLI entry point for a real scrape run.

Usage:
    python scripts/run_scraper.py --hashtags nifty50,sensex --count 2000

Requires TWITTER_AUTH_TOKEN in .env for the X search path, otherwise
falls back to the Nitter mirrors in NITTER_INSTANCES. See README.md
"Live scraping" section before running this against a real account.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.processing.cleaner import clean_batch
from src.processing.deduplication import Deduplicator
from src.processing.storage import ParquetStorage
from src.scraper.twitter_scraper import collect_tweets
from src.utils.logger import get_logger

logger = get_logger("run_scraper")


def main():
    parser = argparse.ArgumentParser(description="Scrape Indian market-related tweets")
    parser.add_argument("--hashtags", type=str, default=",".join(config.HASHTAGS))
    parser.add_argument("--count", type=int, default=config.TARGET_TWEET_COUNT)
    parser.add_argument("--headless", action="store_true", default=config.HEADLESS)
    args = parser.parse_args()

    hashtags = [h.strip() for h in args.hashtags.split(",") if h.strip()]
    logger.info("Starting scrape: hashtags=%s target=%d", hashtags, args.count)

    raw_tweets = list(
        collect_tweets(hashtags=hashtags, target_count=args.count, headless=args.headless)
    )
    logger.info("Collected %d raw tweets", len(raw_tweets))

    cleaned = clean_batch(raw_tweets)
    dedup = Deduplicator()
    unique = dedup.dedup_batch(cleaned)
    logger.info("After dedup: %d unique tweets (%s)", len(unique), dedup.stats)

    storage = ParquetStorage()
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = storage.write(unique, partition_date)
    logger.info("Wrote output to %s", out_path)


if __name__ == "__main__":
    main()
