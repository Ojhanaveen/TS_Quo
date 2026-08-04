"""Runs analysis + visualization over whatever is currently in
data/processed/ (i.e. after one or more run_scraper.py runs)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.signal_generator import aggregate_signals, signals_to_dataframe
from src.analysis.visualization import (
    plot_engagement_sample_scatter,
    plot_signal_by_hashtag,
    plot_tweet_volume,
)
from src.config import DATA_PROCESSED_DIR
from src.processing.storage import ParquetStorage
from src.utils.logger import get_logger

logger = get_logger("run_pipeline")


def main():
    storage = ParquetStorage()
    df = storage.read_all()
    if df.empty:
        logger.error("No processed data found in %s -- run run_scraper.py first", DATA_PROCESSED_DIR)
        return

    logger.info("Loaded %d tweets across all partitions", len(df))

    signals = aggregate_signals(df, window="1h")
    signals_df = signals_to_dataframe(signals)
    signals_df.to_csv(DATA_PROCESSED_DIR / "signals.csv", index=False)
    logger.info("Wrote %d signal rows", len(signals_df))

    plot_tweet_volume(df, str(DATA_PROCESSED_DIR / "tweet_volume.png"))
    if not signals_df.empty:
        plot_signal_by_hashtag(signals_df, str(DATA_PROCESSED_DIR / "sentiment_signal.png"))
    plot_engagement_sample_scatter(df, str(DATA_PROCESSED_DIR / "engagement_scatter.png"))
    logger.info("Wrote charts to %s", DATA_PROCESSED_DIR)


if __name__ == "__main__":
    main()
