from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = [
    "company",
    "job_id",
    "title",
    "recruit_type",
    "job_category",
    "job_function",
    "work_city",
    "work_cities",
    "responsibilities",
    "requirements",
    "bonus_points",
    "tags",
    "publish_time",
    "detail_url",
    "fetched_at",
    "source_page",
]


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value).strip()


def _split_multi_value(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [item for item in (_to_text(v) for v in value) if item]

    if isinstance(value, tuple):
        return [item for item in (_to_text(v) for v in value) if item]

    text = _to_text(value)
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [item for item in (_to_text(v) for v in parsed) if item]
        except Exception:
            pass

    parts = re.split(r"[|,;/、]+", text)
    return [item.strip() for item in parts if item and item.strip()]


def normalize_job_record(raw: dict[str, Any], source_file: str = "") -> dict[str, Any]:
    row = raw or {}

    work_cities = _split_multi_value(row.get("work_cities"))
    if not work_cities and _to_text(row.get("work_city")):
        work_cities = [_to_text(row.get("work_city"))]

    tags = _split_multi_value(row.get("tags"))

    normalized = {
        "company": _to_text(row.get("company")),
        "job_id": _to_text(row.get("job_id")),
        "title": _to_text(row.get("title")),
        "recruit_type": _to_text(row.get("recruit_type")),
        "job_category": _to_text(row.get("job_category")),
        "job_function": _to_text(row.get("job_function")),
        "work_city": _to_text(row.get("work_city")),
        "work_cities": work_cities,
        "responsibilities": _to_text(row.get("responsibilities")),
        "requirements": _to_text(row.get("requirements")),
        "bonus_points": _to_text(row.get("bonus_points")),
        "tags": tags,
        "publish_time": _to_text(row.get("publish_time")),
        "detail_url": _to_text(row.get("detail_url")),
        "fetched_at": _to_text(row.get("fetched_at")),
        "source_page": _to_text(row.get("source_page")),
        "source_file": source_file,
    }

    for field in REQUIRED_FIELDS:
        normalized.setdefault(field, "" if field not in {"work_cities", "tags"} else [])

    return normalized


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for raw in reader:
            normalized = normalize_job_record(raw or {}, source_file=path.name)
            rows.append(normalized)
    return rows


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            rows.append(normalize_job_record(raw, source_file=path.name))
    return rows


def load_jobs_from_file(path: str | Path) -> list[dict[str, Any]]:
    data_path = Path(path)
    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        return _load_csv_rows(data_path)
    if suffix == ".jsonl":
        return _load_jsonl_rows(data_path)
    return []
