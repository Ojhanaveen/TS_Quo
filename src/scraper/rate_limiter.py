"""Sliding-window rate limiter with exponential backoff.

Twitter/X and Nitter mirrors both throttle or soft-block aggressive
scraping. Rather than firing requests as fast as possible, we track
recent request timestamps in a deque (O(1) amortized push/evict) and
force the caller to wait once the window fills up. On top of that,
each detected block/CAPTCHA/empty-response doubles a backoff timer
(capped) so repeated failures don't hammer the same endpoint.
"""
import random
import time
from collections import deque

from src.config import (
    MAX_REQUESTS_PER_WINDOW,
    WINDOW_SECONDS,
    MIN_SCROLL_DELAY_S,
    MAX_SCROLL_DELAY_S,
    BACKOFF_BASE_S,
    BACKOFF_MAX_S,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    def __init__(
        self,
        max_requests: int = MAX_REQUESTS_PER_WINDOW,
        window_seconds: float = WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._consecutive_failures = 0

    def wait_if_needed(self) -> None:
        """Block until a new request is allowed under the sliding window."""
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] > self.window_seconds:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.max_requests:
            sleep_for = self.window_seconds - (now - self._timestamps[0]) + 1
            logger.info("Rate window full, sleeping %.1fs", sleep_for)
            time.sleep(max(sleep_for, 0))

        self._timestamps.append(time.monotonic())

    def human_delay(self) -> None:
        """Randomized delay mimicking human scroll/read pauses."""
        time.sleep(random.uniform(MIN_SCROLL_DELAY_S, MAX_SCROLL_DELAY_S))

    def register_failure(self) -> float:
        """Exponential backoff after a block/CAPTCHA/empty page. Returns sleep time."""
        self._consecutive_failures += 1
        backoff = min(
            BACKOFF_BASE_S * (2 ** (self._consecutive_failures - 1)),
            BACKOFF_MAX_S,
        )
        backoff *= random.uniform(0.85, 1.15)
        logger.warning(
            "Failure #%d detected, backing off %.0fs",
            self._consecutive_failures,
            backoff,
        )
        time.sleep(backoff)
        return backoff

    def register_success(self) -> None:
        self._consecutive_failures = 0
