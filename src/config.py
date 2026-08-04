"""Central configuration loaded from environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DATA_SAMPLE_DIR = ROOT_DIR / "data" / "sample_output"
LOG_DIR = ROOT_DIR / "logs"

for d in (DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_SAMPLE_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

TWITTER_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "")
NITTER_INSTANCES = [
    u.strip() for u in os.getenv(
        "NITTER_INSTANCES", "https://nitter.net"
    ).split(",") if u.strip()
]
HASHTAGS = [
    h.strip().lstrip("#") for h in os.getenv(
        "HASHTAGS", "nifty50,sensex,intraday,banknifty"
    ).split(",") if h.strip()
]
TARGET_TWEET_COUNT = int(os.getenv("TARGET_TWEET_COUNT", "2000"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Rate limiting defaults
MIN_SCROLL_DELAY_S = 2.0
MAX_SCROLL_DELAY_S = 5.5
MAX_REQUESTS_PER_WINDOW = 45
WINDOW_SECONDS = 15 * 60
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 900
