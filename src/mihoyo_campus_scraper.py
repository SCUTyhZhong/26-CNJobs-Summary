import argparse
import csv
import datetime as dt
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMPANY = "米哈游"
BASE_SITE_URL = "https://jobs.mihoyo.com"
BASE_API_URL = "https://ats.openout.mihoyo.com/ats-portal"

API_JOB_LIST = f"{BASE_API_URL}/v1/job/list"
API_JOB_INFO = f"{BASE_API_URL}/v1/job/info"

# channelDetailIds=1 → 校招渠道；hireType=1 → 校园招聘
CHANNEL_DETAIL_IDS = [1]
HIRE_TYPE = 1

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://jobs.mihoyo.com",
    "Referer": "https://jobs.mihoyo.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    ),
}

_CSV_HEADER = [
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


# ── helpers ───────────────────────────────────────────────────────────────────

def clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    compact = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return compact or None


def post_json(
    url: str,
    payload: Dict[str, Any],
    timeout: float = 20.0,
    retries: int = 3,
    retry_base_seconds: float = 1.5,
) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        req = Request(url=url, data=body, headers=DEFAULT_HEADERS, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError("Response is not a JSON object")
                return parsed
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_err = exc
            if attempt >= retries:
                break
            time.sleep(retry_base_seconds * (2 ** (attempt - 1)) + random.uniform(0.0, 0.5))
    raise RuntimeError(f"POST failed after {retries} retries: {url} ({last_err})")


# ── API calls ─────────────────────────────────────────────────────────────────

def fetch_job_list(page_no: int, page_size: int, timeout: float, retries: int) -> Dict[str, Any]:
    payload = {
        "pageNo": page_no,
        "pageSize": page_size,
        "channelDetailIds": CHANNEL_DETAIL_IDS,
        "hireType": HIRE_TYPE,
    }
    resp = post_json(API_JOB_LIST, payload, timeout=timeout, retries=retries)
    data = resp.get("data")
    return data if isinstance(data, dict) else {}


def fetch_job_info(job_id: str, timeout: float, retries: int) -> Dict[str, Any]:
    payload = {
        "id": job_id,
        "channelDetailIds": CHANNEL_DETAIL_IDS,
        "hireType": HIRE_TYPE,
    }
    resp = post_json(API_JOB_INFO, payload, timeout=timeout, retries=retries)
    data = resp.get("data")
    return data if isinstance(data, dict) else {}


# ── normalisation ─────────────────────────────────────────────────────────────

def extract_cities(address_list: Any) -> List[str]:
    if not isinstance(address_list, list):
        return []
    cities: List[str] = []
    seen: set = set()
    for item in address_list:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("addressDetail"))
        if name and name not in seen:
            seen.add(name)
            cities.append(name)
    return cities


def extract_tags(tag_list: Any) -> List[str]:
    if not isinstance(tag_list, list):
        return []
    tags: List[str] = []
    seen: set = set()
    for item in tag_list:
        name: Optional[str] = None
        if isinstance(item, dict):
            name = clean_text(item.get("tagName") or item.get("name") or item.get("label"))
        elif isinstance(item, str):
            name = clean_text(item)
        if name and name not in seen:
            seen.add(name)
            tags.append(name)
    return tags


def normalize_record(
    list_item: Dict[str, Any],
    detail: Dict[str, Any],
    source_page: int,
    fetched_at: str,
) -> Dict[str, Any]:
    job_id = str(detail.get("id") or list_item.get("id") or "")
    cities = extract_cities(detail.get("addressDetailList") or list_item.get("addressDetailList"))
    tags = extract_tags(detail.get("tagList") or list_item.get("tagList"))

    return {
        "company": COMPANY,
        "job_id": job_id,
        "title": clean_text(detail.get("title") or list_item.get("title")),
        "recruit_type": clean_text(detail.get("projectName") or list_item.get("projectName")),
        "job_category": clean_text(detail.get("competencyType") or list_item.get("competencyType")),
        "job_function": clean_text(detail.get("jobNature") or list_item.get("jobNature")),
        "work_city": cities[0] if cities else None,
        "work_cities": cities,
        "responsibilities": clean_text(detail.get("description")),
        "requirements": clean_text(detail.get("jobRequire")),
        "bonus_points": clean_text(detail.get("addition")),
        "tags": tags,
        "publish_time": None,  # not exposed by the API
        "detail_url": f"{BASE_SITE_URL}/#/campus/position/{job_id}" if job_id else None,
        "fetched_at": fetched_at,
        "source_page": source_page,
    }


# ── crawler ───────────────────────────────────────────────────────────────────

def crawl_all(args: argparse.Namespace) -> List[Dict[str, Any]]:
    print(f"[start] target={API_JOB_LIST} page_size={args.page_size}")

    first_page = fetch_job_list(
        page_no=args.start_page,
        page_size=args.page_size,
        timeout=args.timeout,
        retries=args.retries,
    )

    total = int(first_page.get("total") or 0)
    total_pages = max(1, math.ceil(total / args.page_size))
    effective_end = min(args.end_page, total_pages)

    print(f"[info] total_jobs={total}, total_pages={total_pages}, crawl_range={args.start_page}-{effective_end}")

    records_by_id: Dict[str, Dict[str, Any]] = {}

    for page_no in range(args.start_page, effective_end + 1):
        if page_no == args.start_page:
            page_data = first_page
        else:
            page_data = fetch_job_list(
                page_no=page_no,
                page_size=args.page_size,
                timeout=args.timeout,
                retries=args.retries,
            )

        items = page_data.get("list")
        if not isinstance(items, list):
            items = []

        print(f"[page={page_no}] items={len(items)}")
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "")
            if not job_id:
                continue

            try:
                detail = fetch_job_info(job_id=job_id, timeout=args.timeout, retries=args.retries)
            except Exception as exc:
                print(f"[detail] job_id={job_id} failed: {exc}")
                detail = {}

            row = normalize_record(
                list_item=item,
                detail=detail,
                source_page=page_no,
                fetched_at=fetched_at,
            )
            records_by_id[job_id] = row

            time.sleep(random.uniform(args.detail_delay_min, args.detail_delay_max))

        time.sleep(random.uniform(args.page_delay_min, args.page_delay_max))

    rows = list(records_by_id.values())
    rows.sort(key=lambda x: x.get("job_id") or "")
    return rows


# ── output ────────────────────────────────────────────────────────────────────

def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["work_cities"] = "|".join(output.get("work_cities") or [])
            output["tags"] = "|".join(output.get("tags") or [])
            writer.writerow(output)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MiHoYo campus jobs crawler (no browser required)")
    parser.add_argument("--page-size", type=int, default=100, help="Jobs per list request (max ~100).")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=999, help="999 = crawl all pages.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--page-delay-min", type=float, default=0.3)
    parser.add_argument("--page-delay-max", type=float, default=0.8)
    parser.add_argument("--detail-delay-min", type=float, default=0.1)
    parser.add_argument("--detail-delay-max", type=float, default=0.3)
    parser.add_argument("--jsonl", type=Path, default=Path("data/mihoyo_jobs.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("data/mihoyo_jobs.csv"))
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.page_size < 1:
        raise ValueError("page-size must be >= 1")
    if args.start_page < 1 or args.end_page < args.start_page:
        raise ValueError("Invalid page range")
    if args.timeout <= 0:
        raise ValueError("timeout must be > 0")
    if args.retries < 1:
        raise ValueError("retries must be >= 1")
    if args.page_delay_min < 0 or args.page_delay_max < args.page_delay_min:
        raise ValueError("Invalid page delay range")
    if args.detail_delay_min < 0 or args.detail_delay_max < args.detail_delay_min:
        raise ValueError("Invalid detail delay range")


def main() -> None:
    args = parse_args()
    validate_args(args)
    rows = crawl_all(args)
    write_jsonl(args.jsonl, rows)
    write_csv(args.csv, rows)
    print(f"done: total_rows={len(rows)}")
    print(f"jsonl → {args.jsonl}")
    print(f"csv   → {args.csv}")


if __name__ == "__main__":
    main()
