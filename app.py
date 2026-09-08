"""Local, no-login dashboard for the Qode Market Intelligence pipeline.

Run with:
    streamlit run app.py

Every stage of the pipeline -- collect, clean/dedup, store, generate
signals, visualize -- is triggered by a button in this dashboard and runs
the exact same code as the CLI scripts (scripts/run_scraper.py,
scripts/run_pipeline.py, scripts/generate_sample_data.py). This file adds
no new pipeline logic; it's a thin, visual driver over what already
exists in src/.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config
from src.analysis.signal_generator import aggregate_signals, signals_to_dataframe
from src.analysis.visualization import (
    plot_engagement_sample_scatter,
    plot_signal_by_hashtag,
    plot_tweet_volume,
)
from src.processing.cleaner import clean_batch
from src.processing.deduplication import Deduplicator
from src.processing.storage import ParquetStorage

st.set_page_config(page_title="Qode Market Intelligence", layout="wide")

DASHBOARD_OUT_DIR = config.ROOT_DIR / "data" / "dashboard_output"
DASHBOARD_OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    "raw_tweets": None,
    "raw_source_label": None,
    "unique_tweets": None,
    "dedup_stats": None,
    "written_path": None,
    "df": None,
    "signals_df": None,
    "chart_paths": {},
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


def reset_pipeline():
    for key, val in DEFAULTS.items():
        st.session_state[key] = val


st.title("📈 Qode Market Intelligence Dashboard")
st.caption(
    "Collect hashtag tweets, clean and deduplicate them, store to Parquet, "
    "generate sentiment signals, and visualize -- one step at a time, "
    "each one showing exactly what happened."
)

# ---------------------------------------------------------------- Sidebar
st.sidebar.header("Configuration")

data_source = st.sidebar.radio(
    "Data source",
    ["Synthetic sample data", "Live scrape (X account)", "Load existing stored data"],
    help=(
        "Synthetic data needs no X account and always works. Live scrape "
        "needs TWITTER_AUTH_TOKEN in your local .env file. Loading existing "
        "data reads whatever is already in data/processed/."
    ),
)

hashtags_input = st.sidebar.text_input(
    "Hashtags (comma-separated)", value=",".join(config.HASHTAGS)
)
hashtags = [h.strip().lstrip("#") for h in hashtags_input.split(",") if h.strip()]

per_hashtag_count = 60
headless = True

if data_source == "Live scrape (X account)":
    if config.TWITTER_AUTH_TOKEN:
        st.sidebar.success("X session token found in .env")
    else:
        st.sidebar.error(
            "No TWITTER_AUTH_TOKEN in .env -- add one first (see "
            ".env.example), or this falls back to Nitter mirrors."
        )
    per_hashtag_count = st.sidebar.number_input(
        "Tweets per hashtag", min_value=5, max_value=2000, value=60, step=5
    )
    if per_hashtag_count > 300:
        st.sidebar.warning(
            "Live testing found X's rate-limiter escalates sharply above "
            "~300 tweets/hashtag in one session (see docs/FEASIBILITY.md). "
            "Consider smaller batches run over time instead."
        )
    headless = st.sidebar.checkbox("Headless browser", value=True)
elif data_source == "Synthetic sample data":
    per_hashtag_count = st.sidebar.number_input(
        "Synthetic tweets per hashtag", min_value=10, max_value=1000, value=130, step=10
    )
else:
    st.sidebar.info("Will load whatever is currently saved in data/processed/.")

st.sidebar.divider()
if st.sidebar.button("🔄 Reset pipeline", use_container_width=True):
    reset_pipeline()
    st.rerun()


def step_header(n: int, title: str, ready: bool):
    icon = "✅" if ready else "⬜"
    st.subheader(f"{icon} Step {n}: {title}")


# ------------------------------------------------------------ Step 1
step_header(1, "Data Collection", st.session_state.raw_tweets is not None or st.session_state.df is not None)

if data_source == "Load existing stored data":
    st.write("Loads whatever has already been scraped and stored in `data/processed/`.")
    if st.button("Load stored data", key="btn_load"):
        with st.status("Loading stored data...", expanded=True) as status:
            try:
                storage = ParquetStorage()
                df = storage.read_all()
                if df.empty:
                    status.update(label="No stored data found", state="error")
                    st.error(
                        "data/processed/ has no Parquet files yet. Run a live "
                        "scrape first, or switch to synthetic sample data."
                    )
                else:
                    st.session_state.df = df
                    status.update(
                        label=f"Loaded {len(df)} rows from data/processed/",
                        state="complete",
                    )
                    st.write(f"Loaded **{len(df)}** rows across "
                             f"{df['search_hashtag'].nunique()} hashtags.")
            except Exception as e:
                status.update(label="Load failed", state="error")
                st.error(f"{type(e).__name__}: {e}")
else:
    label = "Run synthetic data generation" if data_source == "Synthetic sample data" else "Run live scrape"
    if st.button(label, key="btn_collect"):
        with st.status(f"{label}...", expanded=True) as status:
            try:
                if data_source == "Synthetic sample data":
                    from scripts.generate_sample_data import generate_raw_tweets
                    raw = generate_raw_tweets(n_per_hashtag=int(per_hashtag_count))
                    st.session_state.raw_source_label = "synthetic"
                else:
                    from src.scraper.twitter_scraper import collect_tweets_by_hashtag
                    raw = [
                        tweet
                        for _tag, tweet in collect_tweets_by_hashtag(
                            hashtags=hashtags,
                            per_hashtag_count=int(per_hashtag_count),
                            headless=headless,
                        )
                    ]
                    st.session_state.raw_source_label = "live"

                if not raw:
                    status.update(label="Collected 0 tweets", state="error")
                    st.error(
                        "No tweets were collected. If this was a live scrape, "
                        "check your TWITTER_AUTH_TOKEN is current, or X may "
                        "have shown a login wall / rate limit -- see the "
                        "terminal log for details."
                    )
                else:
                    st.session_state.raw_tweets = raw
                    status.update(
                        label=f"Collected {len(raw)} raw tweets", state="complete"
                    )
                    st.write(f"Collected **{len(raw)}** raw tweets across "
                             f"**{len(hashtags)}** hashtag(s).")
            except Exception as e:
                status.update(label="Collection failed", state="error")
                st.error(f"{type(e).__name__}: {e}")

st.divider()

# ------------------------------------------------------------ Step 2
ready_for_step2 = st.session_state.raw_tweets is not None
step_header(2, "Clean & Deduplicate", st.session_state.unique_tweets is not None)

if data_source == "Load existing stored data":
    st.caption("Skipped -- stored data was already cleaned/deduped when it was written.")
else:
    if st.button(
        "Run cleaning & deduplication", key="btn_clean", disabled=not ready_for_step2
    ):
        with st.status("Cleaning and deduplicating...", expanded=True) as status:
            try:
                cleaned = clean_batch(st.session_state.raw_tweets)
                dedup = Deduplicator()
                unique = dedup.dedup_batch(cleaned)
                st.session_state.unique_tweets = unique
                st.session_state.dedup_stats = dedup.stats
                status.update(
                    label=f"{len(unique)} unique tweets after dedup", state="complete"
                )
                st.write(dedup.stats)
            except Exception as e:
                status.update(label="Cleaning/dedup failed", state="error")
                st.error(f"{type(e).__name__}: {e}")
    if not ready_for_step2:
        st.caption("Complete Step 1 first.")

st.divider()

# ------------------------------------------------------------ Step 3
ready_for_step3 = st.session_state.unique_tweets is not None
step_header(3, "Store (Parquet)", st.session_state.written_path is not None or (data_source == "Load existing stored data" and st.session_state.df is not None))

if data_source == "Load existing stored data":
    st.caption("Skipped -- already stored.")
else:
    if st.button("Write to Parquet storage", key="btn_store", disabled=not ready_for_step3):
        with st.status("Writing to storage...", expanded=True) as status:
            try:
                # Synthetic data must never land in data/processed/ -- that's
                # where real scraped tweets are stored, and Parquet writes
                # merge into the existing partition file rather than
                # replacing it, so mixing sources there would permanently
                # corrupt real collected data with fake rows.
                if st.session_state.raw_source_label == "synthetic":
                    storage = ParquetStorage(base_dir=DASHBOARD_OUT_DIR / "parquet")
                    st.caption("Synthetic run -- writing to data/dashboard_output/parquet/, not data/processed/.")
                else:
                    storage = ParquetStorage()
                partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                out_path = storage.write(st.session_state.unique_tweets, partition_date)
                st.session_state.written_path = out_path
                st.session_state.df = storage.read_all()
                status.update(label=f"Wrote to {out_path}", state="complete")
                st.write(f"Total rows now in this storage: **{len(st.session_state.df)}**")
            except Exception as e:
                status.update(label="Storage failed", state="error")
                st.error(f"{type(e).__name__}: {e}")
    if not ready_for_step3:
        st.caption("Complete Step 2 first.")

st.divider()

# ------------------------------------------------------------ Step 4
ready_for_step4 = st.session_state.df is not None
step_header(4, "Generate Sentiment Signals", st.session_state.signals_df is not None)

if st.button("Generate signals", key="btn_signals", disabled=not ready_for_step4):
    with st.status("Generating sentiment signals...", expanded=True) as status:
        try:
            signals = aggregate_signals(st.session_state.df, window="1h")
            signals_df = signals_to_dataframe(signals)
            st.session_state.signals_df = signals_df
            status.update(
                label=f"Generated {len(signals_df)} signal rows", state="complete"
            )
            st.dataframe(signals_df, use_container_width=True)
        except Exception as e:
            status.update(label="Signal generation failed", state="error")
            st.error(f"{type(e).__name__}: {e}")
if not ready_for_step4:
    st.caption("Complete Step 1-3 first (or load existing stored data).")

st.divider()

# ------------------------------------------------------------ Step 5
ready_for_step5 = st.session_state.df is not None
step_header(5, "Visualize & Summarize", bool(st.session_state.chart_paths))

if st.button("Generate charts & summary", key="btn_viz", disabled=not ready_for_step5):
    with st.status("Rendering charts...", expanded=True) as status:
        try:
            df = st.session_state.df
            paths = {}
            paths["volume"] = plot_tweet_volume(
                df, str(DASHBOARD_OUT_DIR / "tweet_volume.png")
            )
            if st.session_state.signals_df is not None and not st.session_state.signals_df.empty:
                paths["signal"] = plot_signal_by_hashtag(
                    st.session_state.signals_df, str(DASHBOARD_OUT_DIR / "sentiment_signal.png")
                )
            paths["engagement"] = plot_engagement_sample_scatter(
                df, str(DASHBOARD_OUT_DIR / "engagement_scatter.png")
            )
            st.session_state.chart_paths = paths
            status.update(label="Charts rendered", state="complete")
        except Exception as e:
            status.update(label="Visualization failed", state="error")
            st.error(f"{type(e).__name__}: {e}")
if not ready_for_step5:
    st.caption("Complete Step 1-3 first (or load existing stored data).")

if st.session_state.df is not None:
    df = st.session_state.df
    st.markdown("### Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total tweets", len(df))
    c2.metric("Hashtags", df["search_hashtag"].nunique())
    c3.metric("Unique authors", df["username"].nunique())
    c4.metric("Total engagement", int(df["engagement_score"].sum()))

    st.markdown("**Tweets per hashtag**")
    st.bar_chart(df["search_hashtag"].value_counts())

    if st.session_state.dedup_stats:
        st.markdown("**Deduplication (last run)**")
        st.json(st.session_state.dedup_stats)

    if st.session_state.chart_paths:
        cols = st.columns(len(st.session_state.chart_paths))
        for col, (name, path) in zip(cols, st.session_state.chart_paths.items()):
            with col:
                st.image(path, caption=name, use_column_width=True)

    st.markdown("**Sample data**")
    st.dataframe(
        df[["username", "content_clean", "likes", "retweets", "replies",
            "search_hashtag", "timestamp"]].head(50),
        use_container_width=True,
    )

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download full dataset as CSV", csv_bytes, "tweets.csv", "text/csv"
    )
