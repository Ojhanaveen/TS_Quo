"""Text cleaning and normalization for tweet content.

Indian stock-market Twitter is heavily code-mixed: Devanagari (Hindi),
other Indic scripts, emoji, cashtags ($NIFTY), and Latin script in the
same tweet. We normalize to NFC (so visually-identical strings compare
equal), strip noise (URLs, control chars) without destroying non-Latin
text, and keep hashtags/mentions/cashtags as separate structured fields
rather than deleting them from the body.
"""
import re
import unicodedata
from dataclasses import dataclass

URL_RE = re.compile(r"https?://\S+")
CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,15})\b")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MULTI_SPACE_RE = re.compile(r"\s+")


@dataclass
class CleanedTweet:
    tweet_id: str
    username: str
    timestamp: str
    content_raw: str
    content_clean: str
    mentions: list
    hashtags: list
    cashtags: list
    likes: int
    retweets: int
    replies: int
    engagement_score: int
    source: str
    search_hashtag: str
    scraped_at: str


def normalize_unicode(text: str) -> str:
    """NFC-normalize so combining-character variants of the same glyph
    (common in Devanagari/Indic input methods) hash and compare equal."""
    return unicodedata.normalize("NFC", text or "")


def strip_urls(text: str) -> str:
    return URL_RE.sub("", text)


def extract_cashtags(text: str) -> list:
    return [c.upper() for c in CASHTAG_RE.findall(text or "")]


def clean_text(text: str) -> str:
    text = normalize_unicode(text)
    text = strip_urls(text)
    text = CONTROL_CHAR_RE.sub("", text)
    text = MULTI_SPACE_RE.sub(" ", text).strip()
    return text


def clean_tweet(raw) -> CleanedTweet:
    """raw: RawTweet (duck-typed -- also accepts a dict with the same keys)."""
    get = raw.__dict__.get if hasattr(raw, "__dict__") else raw.get
    content_raw = get("content", "")
    content_clean = clean_text(content_raw)
    likes, retweets, replies = get("likes", 0), get("retweets", 0), get("replies", 0)

    return CleanedTweet(
        tweet_id=str(get("tweet_id", "")),
        username=normalize_unicode(get("username", "")).lstrip("@").strip(),
        timestamp=get("timestamp", "") or "",
        content_raw=content_raw,
        content_clean=content_clean,
        mentions=get("mentions", []) or [],
        hashtags=get("hashtags", []) or [],
        cashtags=extract_cashtags(content_raw),
        likes=likes,
        retweets=retweets,
        replies=replies,
        engagement_score=likes + 2 * retweets + replies,
        source=get("source", ""),
        search_hashtag=get("search_hashtag", ""),
        scraped_at=get("scraped_at", ""),
    )


def clean_batch(raw_tweets) -> list:
    return [clean_tweet(t) for t in raw_tweets]
