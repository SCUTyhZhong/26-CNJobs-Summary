from __future__ import annotations

from pathlib import Path

CSV_SUFFIX = "_jobs.csv"
SAMPLE_CSV_SUFFIX = "_sample.csv"
SCRAPER_SUFFIX = "_campus_scraper.py"


def discover_job_csv_files(data_dir: str | Path) -> list[Path]:
    """Discover all full dataset CSV files under data directory."""
    root = Path(data_dir)
    files: list[Path] = []
    for path in sorted(root.glob(f"*{CSV_SUFFIX}")):
        if path.name.endswith(SAMPLE_CSV_SUFFIX):
            continue
        files.append(path)
    return files


def discover_scraper_scripts(src_dir: str | Path) -> list[Path]:
    """Discover scraper entry scripts by naming convention."""
    root = Path(src_dir)
    scripts: list[Path] = []
    for path in sorted(root.glob(f"*{SCRAPER_SUFFIX}")):
        if path.name.startswith("_"):
            continue
        scripts.append(path)
    return scripts


def infer_site_name_from_dataset(path: Path) -> str:
    """Infer site id from data/<site>_jobs.csv file name."""
    name = path.name
    if name.endswith(CSV_SUFFIX):
        return name[: -len(CSV_SUFFIX)]
    return path.stem
