from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pipeline_utils import CSV_SUFFIX, SAMPLE_CSV_SUFFIX, UNIFIED_CSV_NAME, UNIFIED_JSONL_NAME

CSV_HEADER = [
    "company", "job_id", "title", "recruit_type", "job_category", "job_function",
    "work_city", "work_cities", "team_intro", "responsibilities", "requirements",
    "bonus_points", "tags", "publish_time", "detail_url", "fetched_at", "source_page",
]


def _read_csv_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def _discover_legacy_csv_files(data_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(data_dir.glob(f"*{CSV_SUFFIX}")):
        if path.name == UNIFIED_CSV_NAME:
            continue
        if path.name.endswith(SAMPLE_CSV_SUFFIX):
            continue
        files.append(path)
    return files


def _discover_legacy_jsonl_files(data_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(data_dir.glob("*_jobs.jsonl")):
        if path.name == UNIFIED_JSONL_NAME:
            continue
        if "_sample" in path.name:
            continue
        files.append(path)
    return files


def merge_to_unified(data_dir: Path, cleanup: bool = False) -> tuple[int, int, int]:
    unified_csv = data_dir / UNIFIED_CSV_NAME
    unified_jsonl = data_dir / UNIFIED_JSONL_NAME

    rows_by_key: dict[tuple[str, str], dict] = {}

    # Keep existing unified rows first.
    if unified_csv.exists() and unified_csv.stat().st_size > 0:
        for row in _read_csv_rows(unified_csv):
            company = row.get("company", "")
            job_id = row.get("job_id", "")
            if company and job_id:
                rows_by_key[(company, job_id)] = row

    legacy_csv_files = _discover_legacy_csv_files(data_dir)
    for path in legacy_csv_files:
        for row in _read_csv_rows(path):
            company = row.get("company", "")
            job_id = row.get("job_id", "")
            if company and job_id:
                rows_by_key[(company, job_id)] = row

    rows = sorted(rows_by_key.values(), key=lambda r: (r.get("company", ""), r.get("job_id", "")))

    data_dir.mkdir(parents=True, exist_ok=True)
    with unified_csv.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_HEADER})

    with unified_jsonl.open("w", encoding="utf-8") as fp:
        for row in rows:
            obj = {k: row.get(k, "") for k in CSV_HEADER}
            obj["work_cities"] = [x for x in (obj.get("work_cities") or "").split("|") if x]
            obj["tags"] = [x for x in (obj.get("tags") or "").split("|") if x]
            fp.write(json.dumps(obj, ensure_ascii=False) + "\n")

    removed = 0
    if cleanup:
        for path in legacy_csv_files + _discover_legacy_jsonl_files(data_dir):
            path.unlink(missing_ok=True)
            removed += 1

    return len(rows), len(legacy_csv_files), removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge legacy *_jobs files into unified jobs.csv/jobs.jsonl")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--cleanup", action="store_true", help="Delete legacy per-site *_jobs files after merge")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total, n_legacy_csv, removed = merge_to_unified(args.data_dir, cleanup=args.cleanup)
    print(f"merged rows={total}, legacy_csv_files={n_legacy_csv}, removed_files={removed}")


if __name__ == "__main__":
    main()
