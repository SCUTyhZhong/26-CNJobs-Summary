"""
FastAPI server for job_info_collector.

Serves GET /api/jobs/payload in the exact format the frontend (web/assets/app.js)
already expects, reading from LanceDB built by build_jobs_lancedb.py.

LanceDB stores all job fields (no embeddings yet).  When you are ready for RAG,
add an "embedding" vector column to the table and run vector search with:
    table.search(query_vec).limit(10).to_list()

Build DB first:
    python src/build_jobs_lancedb.py

Run:
    uvicorn src.api_server:app --host 0.0.0.0 --port 8000 --reload
or:
    python src/api_server.py
"""
from __future__ import annotations

import json
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import lancedb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
LANCEDB_DIR = ROOT / "data" / "lancedb"
META_PATH   = ROOT / "data" / "lancedb_meta.json"

TABLE_NAME             = "jobs"
RESPONSIBILITY_PREVIEW = 88
REQUIREMENTS_PREVIEW   = 88
BONUS_PREVIEW          = 56
SEARCH_BLOB_LIMIT      = 220


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _preview(value: str, limit: int) -> str:
    value = _compact(value)
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


def _search_blob(m: dict) -> str:
    text = " ".join([
        _compact(m.get("title", "")),
        _compact(m.get("responsibilities", "")),
        _compact(m.get("requirements", "")),
        _compact(m.get("bonus_points", "")),
    ])
    if len(text) <= SEARCH_BLOB_LIMIT:
        return text
    return f"{text[:SEARCH_BLOB_LIMIT].rstrip()}..."


# ---------------------------------------------------------------------------
# LanceDB helpers
# ---------------------------------------------------------------------------

def _get_table() -> lancedb.table.Table:
    db = lancedb.connect(str(LANCEDB_DIR))
    return db.open_table(TABLE_NAME)


def _row_to_job(m: dict[str, Any]) -> dict[str, Any]:
    """Convert a LanceDB row dict to the job object the frontend expects."""
    return {
        "job_id":           m.get("job_id", ""),
        "company":          _compact(m.get("company", "")),
        "title":            _compact(m.get("title", "")),
        "recruit_type":     _compact(m.get("recruit_type", "")),
        "job_category":     _compact(m.get("job_category", "")),
        "work_city":        _compact(m.get("work_city", "")),
        "detail_url":       _compact(m.get("detail_url", "")),
        "responsibilities": _preview(m.get("responsibilities", ""), RESPONSIBILITY_PREVIEW),
        "requirements":     _preview(m.get("requirements", ""),     REQUIREMENTS_PREVIEW),
        "bonus_points":     _preview(m.get("bonus_points", ""),     BONUS_PREVIEW),
        "search_blob":      _search_blob(m),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not LANCEDB_DIR.exists():
        print(
            f"\n[api_server] WARNING: LanceDB not found at {LANCEDB_DIR}",
            file=sys.stderr,
        )
        print("[api_server] Build it first: python src/build_jobs_lancedb.py\n", file=sys.stderr)
    yield


app = FastAPI(title="Job Info Collector API", version="0.2.0", lifespan=lifespan)

# Allow any origin so the GitHub Pages frontend (and local dev) can reach this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "db": str(LANCEDB_DIR), "db_exists": LANCEDB_DIR.exists()}


@app.get("/api/jobs/payload")
def jobs_payload():
    if not LANCEDB_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not built yet. Run: python src/build_jobs_lancedb.py",
        )

    try:
        table = _get_table()
        rows = table.to_arrow().to_pylist()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LanceDB error: {exc}") from exc

    jobs = [_row_to_job(r) for r in rows]

    meta: dict[str, Any] = {}
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {"meta": meta, "jobs": jobs}


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
