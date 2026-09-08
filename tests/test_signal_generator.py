import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.signal_generator import (
    aggregate_signals,
    lexicon_sentiment,
    _weighted_mean_and_ci,
)


def test_lexicon_sentiment_bullish():
    assert lexicon_sentiment("Strong breakout, buy the dip, bullish rally ahead") > 0


def test_lexicon_sentiment_bearish():
    assert lexicon_sentiment("Breakdown below support, stoploss hit, bearish crash") < 0


def test_lexicon_sentiment_neutral_when_no_terms():
    assert lexicon_sentiment("Watching the market today") == 0.0


def test_aggregate_signals_empty_df_returns_empty_list():
    assert aggregate_signals(pd.DataFrame()) == []


def test_aggregate_signals_basic():
    df = pd.DataFrame(
        {
            "timestamp": [
                "2026-08-04T09:00:00+00:00",
                "2026-08-04T09:15:00+00:00",
                "2026-08-04T09:20:00+00:00",
            ],
            "search_hashtag": ["nifty50", "nifty50", "nifty50"],
            "content_clean": [
                "strong bullish breakout buy now",
                "another bullish rally target hit",
                "bearish breakdown sell now",
            ],
            "engagement_score": [100, 50, 10],
        }
    )
    signals = aggregate_signals(df, window="1h")
    assert len(signals) == 1
    assert signals[0].n_tweets == 3
    assert signals[0].mean_sentiment > 0  # 2 bullish, 1 bearish, bullish weighted higher


def test_single_tweet_window_has_wide_ci_not_zero_width():
    # A lone data point has zero variance around itself -- that must not
    # be reported as a confident, zero-width interval.
    import numpy as np

    mean, lo, hi = _weighted_mean_and_ci(np.array([1.0]), np.array([5.0]))
    assert mean == 1.0
    assert hi - lo > 0.5  # visibly wide, not a degenerate point


def test_ci_bounds_stay_within_sentiment_score_range():
    import numpy as np

    _, lo, hi = _weighted_mean_and_ci(np.array([1.0]), np.array([1.0]))
    assert -1.0 <= lo <= hi <= 1.0
