"""Scrapy settings for job_info_collector crawlers."""
from __future__ import annotations

from pathlib import Path

BOT_NAME = "job_info_collector"
SPIDER_MODULES = ["crawlers.spiders"]
NEWSPIDER_MODULE = "crawlers.spiders"

# Project root is two levels up from this file: scrapy_crawlers/crawlers/settings.py → root
_ROOT = Path(__file__).resolve().parents[2]

# Data directory used by the incremental pipeline
DATA_DIR = str(_ROOT / "data")

# ── Politeness ────────────────────────────────────────────────────────────────
ROBOTSTXT_OBEY = False
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 0.3
RANDOMIZE_DOWNLOAD_DELAY = True

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 3.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# ── Headers ───────────────────────────────────────────────────────────────────
DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}

# ── Pipelines ─────────────────────────────────────────────────────────────────
ITEM_PIPELINES = {
    "crawlers.pipelines.IncrementalCsvPipeline": 300,
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"

# ── Misc ──────────────────────────────────────────────────────────────────────
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TELNETCONSOLE_ENABLED = False
