import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraper.twitter_scraper import (
    _parse_aria_label_count,
    _parse_engagement_count,
    extract_hashtags,
    extract_mentions,
)


def test_parse_aria_label_count_plain_number():
    assert _parse_aria_label_count("23 Reposts. Repost") == 23


def test_parse_aria_label_count_with_k_suffix():
    assert _parse_aria_label_count("1.2K Likes. Like") == 1200


def test_parse_aria_label_count_with_comma():
    assert _parse_aria_label_count("12,345 Likes. Like") == 12345


def test_parse_aria_label_count_no_number_means_zero():
    assert _parse_aria_label_count("Like") == 0


def test_parse_aria_label_count_empty_string():
    assert _parse_aria_label_count("") == 0


def test_parse_engagement_count_text_fallback():
    assert _parse_engagement_count("4.5M") == 4_500_000
    assert _parse_engagement_count("") == 0


def test_extract_hashtags():
    assert extract_hashtags("Bullish on #Nifty50 and #BankNifty today") == [
        "nifty50",
        "banknifty",
    ]


def test_extract_mentions():
    assert extract_mentions("cc @traderraj @quant_karan") == ["traderraj", "quant_karan"]
