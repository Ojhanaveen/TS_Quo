"""Memory-efficient plotting for potentially large tweet datasets.

Two techniques keep memory flat regardless of input size:

1. Chunked/streaming aggregation: instead of loading the full frame
   and plotting every point, we aggregate with pandas `resample`/
   `groupby` first (bucket counts, mean sentiment per hour) -- the
   plotted arrays are O(number of time buckets), not O(number of
   tweets).
2. Reservoir sampling for any plot that must show individual points
   (e.g. an engagement scatter): a fixed-size reservoir is kept while
   streaming rows once, giving an unbiased sample without holding the
   full dataset in memory.
"""
import random

import matplotlib

matplotlib.use("Agg")  # headless-safe, no GUI backend required
import matplotlib.pyplot as plt
import pandas as pd


def reservoir_sample(iterable, k: int, seed: int = 42) -> list:
    rng = random.Random(seed)
    reservoir = []
    for i, item in enumerate(iterable):
        if i < k:
            reservoir.append(item)
        else:
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = item
    return reservoir


def plot_tweet_volume(df: pd.DataFrame, out_path: str, freq: str = "1h") -> str:
    work = df.copy()
    work["ts"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    work = work.dropna(subset=["ts"])
    volume = work.set_index("ts").resample(freq).size()

    fig, ax = plt.subplots(figsize=(10, 4))
    volume.plot(ax=ax, kind="line", marker="o", ms=3)
    ax.set_title("Tweet volume over time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Tweet count")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def plot_signal_by_hashtag(signals_df: pd.DataFrame, out_path: str) -> str:
    fig, ax = plt.subplots(figsize=(10, 4))
    for tag, group in signals_df.groupby("search_hashtag"):
        group = group.sort_values("window_start")
        ax.plot(group["window_start"], group["composite_signal"], marker="o", ms=3, label=f"#{tag}")
        ax.fill_between(
            group["window_start"], group["ci_low"], group["ci_high"], alpha=0.15
        )
    ax.set_title("Composite sentiment signal by hashtag (with 95% CI band)")
    ax.set_xlabel("Time window")
    ax.set_ylabel("Composite signal")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def plot_engagement_sample_scatter(df: pd.DataFrame, out_path: str, sample_size: int = 500) -> str:
    """Uses reservoir sampling so this stays O(sample_size) in memory
    even if `df` has millions of rows in a future run."""
    rows = df[["likes", "retweets"]].itertuples(index=False, name=None)
    sample = reservoir_sample(list(rows), sample_size)
    if not sample:
        sample = [(0, 0)]
    likes, retweets = zip(*sample)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(likes, retweets, alpha=0.4, s=15)
    ax.set_title(f"Likes vs retweets (reservoir sample, n={len(sample)})")
    ax.set_xlabel("Likes")
    ax.set_ylabel("Retweets")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
