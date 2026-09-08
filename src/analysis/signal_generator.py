"""Converts cleaned tweet text into quantitative trading signals.

Pipeline:
  1. TF-IDF vectorization of tweet text -> sparse numerical features.
  2. Lexicon-based sentiment scoring tuned for Indian retail-trader
     slang (not just generic English sentiment -- "bhaag gaya", "upper
     circuit", "roka laga" carry direction that VADER-style lexicons
     miss).
  3. Aggregation into a composite signal per (hashtag, time-window):
     engagement-weighted mean sentiment, plus a 95% confidence interval
     computed from the standard error of the weighted mean so a signal
     built from 3 tweets is visibly less trustworthy than one built
     from 300.
"""
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

BULLISH_TERMS = {
    "buy", "bought", "long", "breakout", "upper circuit", "target hit",
    "rally", "bullish", "surge", "upside", "support held", "accumulate",
    "tejji", "upar", "green", "gap up", "all time high", "ath",
}
BEARISH_TERMS = {
    "sell", "sold", "short", "breakdown", "lower circuit", "stoploss hit",
    "sl hit", "crash", "bearish", "dump", "downside", "resistance",
    "mandi", "neeche", "red", "gap down", "profit booking", "correction",
}

WORD_RE = re.compile(r"[a-z]+(?:\s[a-z]+)?")


@dataclass
class WindowSignal:
    window_start: str
    search_hashtag: str
    n_tweets: int
    mean_sentiment: float
    ci_low: float
    ci_high: float
    composite_signal: float


def lexicon_sentiment(text: str) -> float:
    """Returns a score in [-1, 1]. 0 when no lexicon terms are present."""
    text_lower = (text or "").lower()
    bull_hits = sum(1 for term in BULLISH_TERMS if term in text_lower)
    bear_hits = sum(1 for term in BEARISH_TERMS if term in text_lower)
    total = bull_hits + bear_hits
    if total == 0:
        return 0.0
    return (bull_hits - bear_hits) / total


def build_tfidf_matrix(texts: list, max_features: int = 2000):
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        ngram_range=(1, 2),
        min_df=2,
        stop_words="english",
    )
    matrix = vectorizer.fit_transform(texts)
    return matrix, vectorizer


def _weighted_mean_and_ci(
    values: np.ndarray,
    weights: np.ndarray,
    z: float = 1.96,
    min_effective_n: float = 2.0,
    prior_std: float = 0.6,
):
    """Weighted mean +/- CI, with a variance floor for tiny samples.

    A window with one tweet has zero sample variance around its own value
    -- that's a fact about the sample, not evidence of low uncertainty.
    Using it directly gives a confidently wrong zero-width interval. Below
    ``min_effective_n``, fall back to ``prior_std`` (an assumed standard
    deviation for this lexicon's [-1, 1] sentiment score, roughly the std
    of a uniform distribution over that range) so small samples report
    visibly wide, honest intervals instead of false precision.
    """
    weights = np.where(weights <= 0, 1, weights)  # avoid zero-weight edge case
    mean = np.average(values, weights=weights)
    n_eff = (weights.sum() ** 2) / (weights**2).sum()  # effective sample size
    if n_eff < min_effective_n:
        se = prior_std / np.sqrt(max(n_eff, 1))
    else:
        variance = np.average((values - mean) ** 2, weights=weights)
        se = np.sqrt(variance / n_eff)
    lo = max(mean - z * se, -1.0)
    hi = min(mean + z * se, 1.0)
    return mean, lo, hi


def aggregate_signals(df: pd.DataFrame, window: str = "1h") -> list:
    """df must have: timestamp (parseable), search_hashtag, content_clean,
    engagement_score. Returns one WindowSignal per (hashtag, time window)."""
    if df.empty:
        return []

    work = df.copy()
    work["ts"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    work = work.dropna(subset=["ts"])
    work["sentiment"] = work["content_clean"].apply(lexicon_sentiment)
    work["weight"] = np.log1p(work["engagement_score"].clip(lower=0)) + 1.0

    results = []
    grouped = work.groupby(
        ["search_hashtag", pd.Grouper(key="ts", freq=window)]
    )
    for (tag, window_start), group in grouped:
        if group.empty:
            continue
        mean, lo, hi = _weighted_mean_and_ci(
            group["sentiment"].to_numpy(), group["weight"].to_numpy()
        )
        composite = mean * np.log1p(group["weight"].sum())
        results.append(
            WindowSignal(
                window_start=str(window_start),
                search_hashtag=tag,
                n_tweets=len(group),
                mean_sentiment=round(float(mean), 4),
                ci_low=round(float(lo), 4),
                ci_high=round(float(hi), 4),
                composite_signal=round(float(composite), 4),
            )
        )
    return results


def signals_to_dataframe(signals: list) -> pd.DataFrame:
    return pd.DataFrame([s.__dict__ for s in signals])
