from __future__ import annotations

from pathlib import Path

CSV_SUFFIX = "_jobs.csv"
SAMPLE_CSV_SUFFIX = "_sample.csv"
JSONL_SUFFIX = "_jobs.jsonl"
SAMPLE_JSONL_SUFFIX = "_sample.jsonl"
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


def discover_job_data_files(data_dir: str | Path) -> list[Path]:
    """Discover full dataset files and prefer CSV when both CSV/JSONL exist."""
    root = Path(data_dir)
    candidates: list[Path] = []

    for path in sorted(root.glob(f"*{CSV_SUFFIX}")):
        if path.name.endswith(SAMPLE_CSV_SUFFIX):
            continue
        candidates.append(path)

    for path in sorted(root.glob(f"*{JSONL_SUFFIX}")):
        if path.name.endswith(SAMPLE_JSONL_SUFFIX):
            continue
        candidates.append(path)

    by_site: dict[str, Path] = {}
    for path in sorted(candidates):
        site = infer_site_name_from_dataset(path)
        current = by_site.get(site)
        if current is None:
            by_site[site] = path
            continue
        if current.suffix.lower() != ".csv" and path.suffix.lower() == ".csv":
            by_site[site] = path

    return [by_site[site] for site in sorted(by_site)]


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
    if name.endswith(JSONL_SUFFIX):
        return name[: -len(JSONL_SUFFIX)]
    return path.stem
