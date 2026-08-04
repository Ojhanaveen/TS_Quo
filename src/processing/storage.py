"""Parquet-backed storage, partitioned by date and search hashtag.

Parquet gives us columnar compression (tweet text compresses well,
engagement ints even better) and predicate pushdown for downstream
analysis (e.g. "read only 2026-08-04/nifty50" without touching other
partitions) -- important once volume grows past what fits comfortably
in memory (see the 10x scalability note in docs/TECHNICAL_APPROACH.md).
"""
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import DATA_PROCESSED_DIR
from src.utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA = pa.schema(
    [
        ("tweet_id", pa.string()),
        ("username", pa.string()),
        ("timestamp", pa.string()),
        ("content_raw", pa.string()),
        ("content_clean", pa.string()),
        ("mentions", pa.list_(pa.string())),
        ("hashtags", pa.list_(pa.string())),
        ("cashtags", pa.list_(pa.string())),
        ("likes", pa.int32()),
        ("retweets", pa.int32()),
        ("replies", pa.int32()),
        ("engagement_score", pa.int32()),
        ("source", pa.string()),
        ("search_hashtag", pa.string()),
        ("scraped_at", pa.string()),
    ]
)


class ParquetStorage:
    def __init__(self, base_dir: Path = DATA_PROCESSED_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, cleaned_tweets: list, partition_date: str) -> Path:
        if not cleaned_tweets:
            logger.info("No tweets to write for partition %s", partition_date)
            return None

        df = pd.DataFrame([asdict(t) for t in cleaned_tweets])
        table = pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)

        partition_dir = self.base_dir / f"date={partition_date}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        out_path = partition_dir / "tweets.parquet"

        if out_path.exists():
            existing = pq.read_table(out_path)
            table = pa.concat_tables([existing, table])
            # dedup on write in case of overlapping runs for the same day
            df_combined = table.to_pandas().drop_duplicates(subset="tweet_id")
            table = pa.Table.from_pandas(df_combined, schema=SCHEMA, preserve_index=False)

        pq.write_table(table, out_path, compression="snappy")
        logger.info("Wrote %d rows to %s", table.num_rows, out_path)
        return out_path

    def read_partition(self, partition_date: str) -> pd.DataFrame:
        path = self.base_dir / f"date={partition_date}" / "tweets.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pq.read_table(path).to_pandas()

    def read_all(self) -> pd.DataFrame:
        parts = list(self.base_dir.glob("date=*/tweets.parquet"))
        if not parts:
            return pd.DataFrame()
        tables = [pq.read_table(p) for p in parts]
        return pa.concat_tables(tables).to_pandas()
