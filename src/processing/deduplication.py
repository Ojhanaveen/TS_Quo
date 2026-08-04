"""Exact + near-duplicate detection.

Two layers, chosen for complexity/accuracy trade-offs at the target
scale (thousands to tens of thousands of tweets per run):

1. Exact dedup on tweet_id via a hash set -- O(1) average lookup/insert,
   O(n) total. Catches re-scrapes of the same tweet across overlapping
   hashtag searches (e.g. a tweet with both #nifty50 and #banknifty).

2. Near-duplicate dedup via SimHash -- catches retweet-with-comment,
   copy-paste "tips" spam, and bot networks posting near-identical text
   with small variations. A single prefix bucket misses near-duplicates
   whose differing bits happen to land in the prefix, so we use the
   standard multi-band LSH construction instead: the 64-bit fingerprint
   is split into several non-overlapping bands, each indexed in its own
   dict, and two tweets are compared only if they collide in at least
   one band. That keeps the check sub-linear (candidates come from a
   handful of small band buckets, not a full pairwise scan) while still
   catching duplicates whose edits are scattered across the fingerprint,
   which is what makes this tractable at 10x scale (see docs/TECHNICAL_APPROACH.md).
"""
import hashlib
from collections import defaultdict

SIMHASH_BITS = 64
NUM_BANDS = 8
BAND_BITS = SIMHASH_BITS // NUM_BANDS
HAMMING_THRESHOLD = 8
SHINGLE_SIZE = 4


def _tokenize(text: str) -> list:
    """Character shingles rather than whole-word tokens: tweets are short
    (~a few dozen words), so word-level simhash lets a single added/edited
    word swing a large fraction of the fingerprint's bits. Overlapping
    character n-grams spread each edit's influence over only the shingles
    that touch it, which is the standard construction for near-duplicate
    detection on short text."""
    normalized = "".join(text.lower().split())
    if len(normalized) < SHINGLE_SIZE:
        return [normalized] if normalized else []
    return [
        normalized[i : i + SHINGLE_SIZE]
        for i in range(len(normalized) - SHINGLE_SIZE + 1)
    ]


def simhash(text: str, bits: int = SIMHASH_BITS) -> int:
    tokens = _tokenize(text)
    if not tokens:
        return 0
    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class Deduplicator:
    """Streaming deduplicator: call `is_duplicate` per tweet, in order."""

    def __init__(
        self,
        hamming_threshold: int = HAMMING_THRESHOLD,
        num_bands: int = NUM_BANDS,
    ):
        self._seen_ids: set = set()
        self.num_bands = num_bands
        self.band_bits = SIMHASH_BITS // num_bands
        # one dict per band: band_value -> [(fingerprint, tweet_id)]
        self._band_buckets: list = [defaultdict(list) for _ in range(num_bands)]
        self.hamming_threshold = hamming_threshold
        self.exact_duplicates = 0
        self.near_duplicates = 0

    def _band_values(self, fingerprint: int) -> list:
        mask = (1 << self.band_bits) - 1
        return [
            (fingerprint >> (i * self.band_bits)) & mask
            for i in range(self.num_bands)
        ]

    def is_duplicate(self, tweet_id: str, content: str) -> bool:
        if tweet_id in self._seen_ids:
            self.exact_duplicates += 1
            return True
        self._seen_ids.add(tweet_id)

        fp = simhash(content)
        bands = self._band_values(fp)

        candidates_checked = set()
        for band_idx, band_value in enumerate(bands):
            for existing_fp, existing_id in self._band_buckets[band_idx][band_value]:
                if existing_id in candidates_checked:
                    continue
                candidates_checked.add(existing_id)
                if hamming_distance(fp, existing_fp) <= self.hamming_threshold:
                    self.near_duplicates += 1
                    return True

        for band_idx, band_value in enumerate(bands):
            self._band_buckets[band_idx][band_value].append((fp, tweet_id))
        return False

    def dedup_batch(self, cleaned_tweets: list) -> list:
        return [
            t for t in cleaned_tweets
            if not self.is_duplicate(t.tweet_id, t.content_clean)
        ]

    @property
    def stats(self) -> dict:
        return {
            "unique_ids_seen": len(self._seen_ids),
            "exact_duplicates_dropped": self.exact_duplicates,
            "near_duplicates_dropped": self.near_duplicates,
        }
