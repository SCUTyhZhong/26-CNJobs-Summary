"""Incremental pipeline: only writes jobs not already in unified dataset files.

Incremental update logic
------------------------
On ``open_spider``, the pipeline reads ``jobs.csv`` in DATA_DIR and loads the
set of ``(company, job_id)`` pairs that already exist.

In ``process_item``, any item whose key is already known is dropped silently
(DropItem). New items are appended to unified files:
``jobs.csv`` and ``jobs.jsonl``.

This means subsequent crawl runs only write genuinely new postings, leaving
historical data intact.

Data directory is read from ``settings.DATA_DIR``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from scrapy.exceptions import DropItem

_CSV_HEADER = [
    "company", "job_id", "title", "recruit_type", "job_category", "job_function",
    "work_city", "work_cities", "team_intro", "responsibilities", "requirements",
    "bonus_points", "tags", "publish_time", "detail_url", "fetched_at", "source_page",
]

class IncrementalCsvPipeline:
    """Filters duplicates and appends new job records to unified CSV/JSONL files."""

    def open_spider(self, spider):
        self._data_dir = Path(spider.settings.get("DATA_DIR", "data"))
        self._csv_path = self._data_dir / "jobs.csv"
        self._jsonl_path = self._data_dir / "jobs.jsonl"
        self._existing_keys: set[tuple[str, str]] = self._load_existing_keys()
        self._seen_this_run: set[tuple[str, str]] = set()
        self._writer = None
        self._csv_fh = None
        self._jsonl_fh = None
        self._new_count = 0
        self._skip_count = 0
        self._open_handles()
        spider.logger.info(
            f"IncrementalPipeline: loaded {len(self._existing_keys)} existing job keys from {self._data_dir}"
        )

    def _load_existing_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        csv_path = self._csv_path
        if not csv_path.exists() or csv_path.stat().st_size == 0:
            return keys
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    c = (row.get("company") or "").strip()
                    j = (row.get("job_id") or "").strip()
                    if c and j:
                        keys.add((c, j))
        except Exception:
            pass  # corrupted file: safe to skip
        return keys

    def _open_handles(self) -> None:
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)

        needs_header = not self._csv_path.exists() or self._csv_path.stat().st_size == 0
        self._csv_fh = self._csv_path.open("a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._csv_fh, fieldnames=_CSV_HEADER, extrasaction="ignore")
        if needs_header:
            self._writer.writeheader()

        self._jsonl_fh = self._jsonl_path.open("a", encoding="utf-8")

    def process_item(self, item, spider):
        company = (item.get("company") or "").strip()
        job_id = (item.get("job_id") or "").strip()

        if not company or not job_id:
            raise DropItem(f"Missing company or job_id: {dict(item)}")

        key = (company, job_id)
        if key in self._existing_keys or key in self._seen_this_run:
            self._skip_count += 1
            raise DropItem(f"[incremental] skip existing: {key}")

        self._seen_this_run.add(key)
        self._existing_keys.add(key)

        row = {k: (item.get(k) or "") for k in _CSV_HEADER}
        row["work_cities"] = "|".join(item.get("work_cities") or [])
        row["tags"] = "|".join(item.get("tags") or [])
        self._writer.writerow(row)

        self._jsonl_fh.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
        self._new_count += 1
        return item

    def close_spider(self, spider):
        if self._csv_fh:
            self._csv_fh.flush()
            self._csv_fh.close()
        if self._jsonl_fh:
            self._jsonl_fh.flush()
            self._jsonl_fh.close()
        spider.logger.info(
            f"IncrementalPipeline: new={self._new_count} written, "
            f"skipped={self._skip_count} duplicates"
        )
