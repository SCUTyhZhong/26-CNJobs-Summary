#!/usr/bin/env python3
"""Export frontend payload files from unified jobs dataset.

Outputs:
- web/data/jobs.json
- web/data/jobs.index.json
- web/data/chunks/jobs-*.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        if "|" in value:
            return [s.strip() for s in value.split("|") if s.strip()]
        return [value.strip()]
    return [str(value)]


def _normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for field in REQUIRED_FIELDS:
        value = raw.get(field, "")
        if field in {"work_cities", "tags"}:
            record[field] = _ensure_list(value)
        else:
            record[field] = "" if value is None else value

    for optional in ("team_intro",):
        record[optional] = "" if raw.get(optional) is None else raw.get(optional, "")

    text_blob_parts = [
        record.get("title", ""),
        record.get("responsibilities", ""),
        record.get("requirements", ""),
        record.get("bonus_points", ""),
    ]
    record["search_blob"] = " ".join(str(part) for part in text_blob_parts if part).strip()
    record["search_blob_lower"] = record["search_blob"].lower()

    return record


def _record_key(record: dict[str, Any]) -> tuple[str, str]:
    company = str(record.get("company", "")).strip()
    job_id = str(record.get("job_id", "")).strip()
    detail_url = str(record.get("detail_url", "")).strip()
    if company and job_id:
        return (company, job_id)
    return ("detail_url", detail_url)


def _sort_time_key(record: dict[str, Any]) -> tuple[str, str]:
    publish_time = str(record.get("publish_time", ""))
    fetched_at = str(record.get("fetched_at", ""))
    return (publish_time, fetched_at)


@dataclass
class ChunkMeta:
    name: str
    count: int
    start: int
    end: int


class FrontendExporter:
    def __init__(self, input_path: Path, output_root: Path, chunk_size: int) -> None:
        self.input_path = input_path
        self.output_root = output_root
        self.chunk_size = max(1, chunk_size)
        self.output_data_dir = self.output_root / "data"
        self.chunks_dir = self.output_data_dir / "chunks"

    def run(self) -> dict[str, Any]:
        records = self._load_records()
        self._prepare_output_dirs()

        jobs_json_path = self.output_data_dir / "jobs.json"
        jobs_json_path.write_text(
            json.dumps(records, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        chunk_metas = self._write_chunks(records)
        index_path = self.output_data_dir / "jobs.index.json"

        index_payload = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "chunk_mode": "full",
            "chunk_size": self.chunk_size,
            "total": len(records),
            "files": {
                "jobs": "jobs.json",
                "chunks_dir": "chunks",
            },
            "chunks": [
                {
                    "file": meta.name,
                    "count": meta.count,
                    "start": meta.start,
                    "end": meta.end,
                }
                for meta in chunk_metas
            ],
        }
        index_path.write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "total": len(records),
            "chunks": len(chunk_metas),
            "jobs_json": str(jobs_json_path),
            "index_json": str(index_path),
        }

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

        dedup_map: dict[tuple[str, str], dict[str, Any]] = {}
        with self.input_path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    raw = json.loads(text)
                except json.JSONDecodeError:
                    continue
                record = _normalize_record(raw)
                key = _record_key(record)
                dedup_map[key] = record

        records = list(dedup_map.values())
        records.sort(key=_sort_time_key, reverse=True)
        return records

    def _prepare_output_dirs(self) -> None:
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        for file in self.chunks_dir.glob("jobs-*.json"):
            file.unlink()

    def _write_chunks(self, records: list[dict[str, Any]]) -> list[ChunkMeta]:
        chunk_metas: list[ChunkMeta] = []
        if not records:
            return chunk_metas

        for idx in range(0, len(records), self.chunk_size):
            chunk_index = idx // self.chunk_size + 1
            chunk_records = records[idx : idx + self.chunk_size]
            chunk_name = f"jobs-{chunk_index:04d}.json"
            chunk_path = self.chunks_dir / chunk_name
            chunk_path.write_text(
                json.dumps(chunk_records, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            chunk_metas.append(
                ChunkMeta(
                    name=chunk_name,
                    count=len(chunk_records),
                    start=idx,
                    end=idx + len(chunk_records) - 1,
                )
            )
        return chunk_metas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export frontend jobs payload")
    parser.add_argument(
        "--input",
        default="data/jobs.jsonl",
        help="Input jsonl file path (default: data/jobs.jsonl)",
    )
    parser.add_argument(
        "--output-root",
        default="web",
        help="Frontend web root path (default: web)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=120,
        help="Jobs per chunk (default: 120)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exporter = FrontendExporter(
        input_path=Path(args.input),
        output_root=Path(args.output_root),
        chunk_size=args.chunk_size,
    )
    result = exporter.run()

    print("Frontend data export completed")
    print(f"- total jobs: {result['total']}")
    print(f"- chunk files: {result['chunks']}")
    print(f"- jobs file: {result['jobs_json']}")
    print(f"- index file: {result['index_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
