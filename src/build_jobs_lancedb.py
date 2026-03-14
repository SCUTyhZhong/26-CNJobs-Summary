"""Build LanceDB table from unified job CSV file.

Data is stored as-is (no embeddings yet).  Each row includes a `rag_document`
field containing the full job text so that when you are ready for RAG you can:

    1.  Open the table with `lancedb.connect("data/lancedb").open_table("jobs")`
    2.  Compute embeddings for `row["rag_document"]` with any model
    3.  Add them back:  `table.add_vector_column("embedding", embeddings)`
    4.  Run vector search: `table.search(query_vec).limit(10).to_list()`

Run after each crawl:
    python src/build_jobs_lancedb.py

Optional args:
    --data-dir    path to data directory    (default: data/)
    --lancedb-dir path for LanceDB files    (default: data/lancedb/)
    --meta-path   path for meta sidecar     (default: data/lancedb_meta.json)
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import lancedb

from export_frontend_jobs import build_common_keywords
from pipeline_utils import discover_job_csv_files

TABLE_NAME = "jobs"
BATCH_SIZE = 500


def split_pipe(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            rec = {k: (v or "").strip() for k, v in row.items()}
            rows.append(
                {
                    "company":          rec.get("company", ""),
                    "job_id":           rec.get("job_id", ""),
                    "title":            rec.get("title", ""),
                    "recruit_type":     rec.get("recruit_type", ""),
                    "job_category":     rec.get("job_category", ""),
                    "job_function":     rec.get("job_function", ""),
                    "work_city":        rec.get("work_city", ""),
                    "work_cities_json": json.dumps(split_pipe(rec.get("work_cities", "")), ensure_ascii=False),
                    "team_intro":       rec.get("team_intro", ""),
                    "responsibilities": rec.get("responsibilities", ""),
                    "requirements":     rec.get("requirements", ""),
                    "bonus_points":     rec.get("bonus_points", ""),
                    "tags_json":        json.dumps(split_pipe(rec.get("tags", "")), ensure_ascii=False),
                    "publish_time":     rec.get("publish_time", ""),
                    "detail_url":       rec.get("detail_url", ""),
                    "fetched_at":       rec.get("fetched_at", ""),
                    "source_page":      rec.get("source_page", ""),
                    # Full text for future RAG embeddings.
                    "rag_document":     " ".join(filter(None, [
                        rec.get("title", ""),
                        rec.get("team_intro", ""),
                        rec.get("responsibilities", ""),
                        rec.get("requirements", ""),
                        rec.get("bonus_points", ""),
                    ])),
                }
            )
    return rows


def build_lancedb(data_dir: Path, lancedb_dir: Path, meta_path: Path) -> tuple[int, int]:
    files = discover_job_csv_files(data_dir)
    if not files:
        raise FileNotFoundError(
            f"No dataset CSV found under {data_dir}. Expected data/jobs.csv or legacy *_jobs.csv files."
        )
    rows_by_key: dict[tuple, dict] = {}
    for f in files:
        for row in load_rows(f):
            company = row["company"]
            job_id = row["job_id"]
            if company and job_id:
                rows_by_key[(company, job_id)] = row

    rows = sorted(rows_by_key.values(), key=lambda r: (r["company"], r["job_id"]))

    lancedb_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(lancedb_dir))

    if not rows:
        db.create_table(TABLE_NAME, data=[], mode="overwrite")
        print("  inserted 0/0")
    else:
        # Write in batches to give progress feedback
        first_batch = rows[:BATCH_SIZE]
        table = db.create_table(TABLE_NAME, data=first_batch, mode="overwrite")
        print(f"  inserted {len(first_batch)}/{len(rows)}")

        for i in range(BATCH_SIZE, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            table.add(batch)
            print(f"  inserted {min(i + BATCH_SIZE, len(rows))}/{len(rows)}")

    # Write meta sidecar (used by api_server to return meta in payload)
    # Reconstruct original row format for build_common_keywords
    common_kw_rows = [
        {
            "title": r["title"],
            "responsibilities": r["responsibilities"],
            "requirements": r["requirements"],
            "bonus_points": r["bonus_points"],
        }
        for r in rows
    ]
    common_keywords = build_common_keywords(common_kw_rows, top_n=18)
    meta = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "total_jobs":      len(rows),
        "source_files":    [p.name for p in files],
        "common_keywords": common_keywords,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return len(rows), len(files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build LanceDB from job CSV files")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir",    type=Path, default=root / "data")
    parser.add_argument("--lancedb-dir", type=Path, default=root / "data" / "lancedb")
    parser.add_argument("--meta-path",   type=Path, default=root / "data" / "lancedb_meta.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total, nfiles = build_lancedb(args.data_dir, args.lancedb_dir, args.meta_path)
    print(f"\nbuilt lancedb: {args.lancedb_dir}")
    print(f"rows={total}, source_files={nfiles}")


if __name__ == "__main__":
    main()
