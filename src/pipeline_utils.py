from __future__ import annotations

from pathlib import Path

UNIFIED_CSV_NAME = "jobs.csv"
UNIFIED_JSONL_NAME = "jobs.jsonl"
CSV_SUFFIX = "_jobs.csv"
SAMPLE_CSV_SUFFIX = "_sample.csv"


def discover_job_csv_files(data_dir: str | Path) -> list[Path]:
    """Discover CSV datasets under data directory.

    Preference order:
    1) unified file: data/jobs.csv
    2) legacy per-site files: data/*_jobs.csv (excluding *_sample.csv)
    """
    root = Path(data_dir)
    unified = root / UNIFIED_CSV_NAME
    if unified.exists() and unified.stat().st_size > 0:
        return [unified]

    files: list[Path] = []
    for path in sorted(root.glob(f"*{CSV_SUFFIX}")):
        if path.name.endswith(SAMPLE_CSV_SUFFIX):
            continue
        files.append(path)
    return files
