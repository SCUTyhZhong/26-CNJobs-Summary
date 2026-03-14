from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pipeline_utils import discover_job_csv_files

FULL_CHUNK_SIZE = 120
SEARCH_BLOB_LIMIT = 220


def discover_csv_files(data_dir: Path) -> list[Path]:
    """Discover source CSVs (prefers unified data/jobs.csv)."""
    return discover_job_csv_files(data_dir)


def split_pipe(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items()}
            rows.append(
                {
                    "company": row.get("company", ""),
                    "job_id": row.get("job_id", ""),
                    "title": row.get("title", ""),
                    "recruit_type": row.get("recruit_type", ""),
                    "job_category": row.get("job_category", ""),
                    "job_function": row.get("job_function", ""),
                    "work_city": row.get("work_city", ""),
                    "work_cities": split_pipe(row.get("work_cities", "")),
                    "responsibilities": row.get("responsibilities", ""),
                    "requirements": row.get("requirements", ""),
                    "bonus_points": row.get("bonus_points", ""),
                    "tags": split_pipe(row.get("tags", "")),
                    "publish_time": row.get("publish_time", ""),
                    "detail_url": row.get("detail_url", ""),
                    "source_page": row.get("source_page", ""),
                    "fetched_at": row.get("fetched_at", ""),
                }
            )
    return rows


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def build_search_blob(job: dict) -> str:
    text = " ".join(
        [
            compact_text(job.get("title", "")),
            compact_text(job.get("responsibilities", "")),
            compact_text(job.get("requirements", "")),
            compact_text(job.get("bonus_points", "")),
        ]
    )
    if len(text) <= SEARCH_BLOB_LIMIT:
        return text
    return f"{text[:SEARCH_BLOB_LIMIT].rstrip()}..."


def build_full_chunk_job(job: dict) -> dict:
    merged = dict(job)
    merged["search_blob"] = build_search_blob(job)
    return merged


def export_jobs_json(data_dir: Path, output_file: Path) -> None:
    jobs = []
    files = discover_csv_files(data_dir)
    for file in files:
        jobs.extend(load_rows(file))

    common_keywords = build_common_keywords(jobs, top_n=18)
    generated_at = datetime.now(timezone.utc).isoformat()

    meta = {
        "generated_at": generated_at,
        "total_jobs": len(jobs),
        "source_files": [f.name for f in files],
        "common_keywords": common_keywords,
    }

    payload = {
        "meta": {
            **meta,
        },
        "jobs": jobs,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # Progressive-load artifacts for public web hosting.
    export_chunked_payload(output_file.parent, jobs, meta)


def export_chunked_payload(web_data_dir: Path, jobs: list[dict], meta: dict) -> None:
    chunks_dir = web_data_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    for stale_file in chunks_dir.glob("jobs-*.json"):
        stale_file.unlink(missing_ok=True)

    chunk_entries = []
    full_jobs = [build_full_chunk_job(job) for job in jobs]

    for idx in range(0, len(full_jobs), FULL_CHUNK_SIZE):
        chunk_jobs = full_jobs[idx : idx + FULL_CHUNK_SIZE]
        chunk_no = (idx // FULL_CHUNK_SIZE) + 1
        filename = f"jobs-{chunk_no:03d}.json"
        path = chunks_dir / filename
        chunk_payload = {
            "meta": {
                "chunk_no": chunk_no,
                "count": len(chunk_jobs),
                "mode": "full",
            },
            "jobs": chunk_jobs,
        }
        path.write_text(
            json.dumps(chunk_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        chunk_entries.append({"file": f"chunks/{filename}", "count": len(chunk_jobs)})

    index_payload = {
        "meta": {
            **meta,
            "chunk_size": FULL_CHUNK_SIZE,
            "chunk_count": len(chunk_entries),
            "chunk_mode": "full",
        },
        "chunks": chunk_entries,
    }
    (web_data_dir / "jobs.index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def build_common_keywords(jobs: list[dict], top_n: int = 18) -> list[str]:
    candidate_keywords = [
        "python", "java", "c++", "go", "javascript", "typescript", "sql",
        "机器学习", "深度学习", "推荐", "算法", "数据分析", "后端", "前端",
        "测试", "产品", "设计", "nlp", "llm", "pytorch", "tensorflow",
    ]

    counter = Counter()
    for job in jobs:
        text = " ".join([
            job.get("title", ""),
            job.get("responsibilities", ""),
            job.get("requirements", ""),
            job.get("bonus_points", ""),
        ]).lower()
        for kw in candidate_keywords:
            if re.search(re.escape(kw.lower()), text):
                counter[kw] += 1

    sorted_keywords = [kw for kw, _ in counter.most_common(top_n)]
    if not sorted_keywords:
        return candidate_keywords[:12]
    return sorted_keywords


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    output_file = root / "web" / "data" / "jobs.json"
    export_jobs_json(data_dir, output_file)
    print(f"Exported {output_file}")
