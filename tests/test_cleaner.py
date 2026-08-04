import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processing.cleaner import (
    clean_text,
    extract_cashtags,
    normalize_unicode,
    strip_urls,
)


def test_strip_urls():
    assert strip_urls("check this https://t.co/abc123 out") == "check this  out"


def test_extract_cashtags():
    assert extract_cashtags("Buying $RELIANCE and $TCS today") == ["RELIANCE", "TCS"]


def test_clean_text_collapses_whitespace():
    assert clean_text("hello    world  \n\n") == "hello world"


def test_clean_text_preserves_devanagari():
    text = "निफ्टी आज तेज़ी में है #nifty50"
    cleaned = clean_text(text)
    assert "निफ्टी" in cleaned


def test_normalize_unicode_is_idempotent():
    text = "café"
    assert normalize_unicode(text) == normalize_unicode(normalize_unicode(text))
