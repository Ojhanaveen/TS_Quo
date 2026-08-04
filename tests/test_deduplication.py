import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processing.deduplication import Deduplicator, hamming_distance, simhash


def test_exact_duplicate_detected():
    dedup = Deduplicator()
    assert dedup.is_duplicate("id1", "nifty is up today") is False
    assert dedup.is_duplicate("id1", "nifty is up today") is True
    assert dedup.stats["exact_duplicates_dropped"] == 1


def test_near_duplicate_detected():
    dedup = Deduplicator()
    assert dedup.is_duplicate("id1", "nifty50 breakout confirmed with strong volume today") is False
    assert dedup.is_duplicate(
        "id2", "nifty50 breakout confirmed with strong volume today!!"
    ) is True
    assert dedup.stats["near_duplicates_dropped"] == 1


def test_distinct_content_not_flagged():
    dedup = Deduplicator()
    assert dedup.is_duplicate("id1", "nifty bullish breakout today") is False
    assert dedup.is_duplicate("id2", "completely unrelated content about banknifty crash") is False
    assert dedup.stats["near_duplicates_dropped"] == 0


def test_hamming_distance_zero_for_identical_hash():
    fp = simhash("some sample tweet text")
    assert hamming_distance(fp, fp) == 0


def test_empty_text_simhash_is_zero():
    assert simhash("") == 0
