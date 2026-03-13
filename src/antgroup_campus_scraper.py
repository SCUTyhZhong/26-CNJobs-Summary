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

COMPANY = "阿里巴巴(蚂蚁集团)"
BASE_URL = "https://hrcareersweb.antgroup.com"

API_POSITION_SEARCH = f"{BASE_URL}/api/campus/position/search"

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://talent.antgroup.com",
    "Referer": "https://talent.antgroup.com/campus-full-list",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}

DEFAULT_BATCH_IDS = ["26022600074513"]

_CSV_HEADER = [
    "company",
    "job_id",
    "title",
    "recruit_type",
    "job_category",
    "job_function",
    "work_city",
    "work_cities",
    "team_intro",
    "responsibilities",
    "requirements",
    "bonus_points",
    "tags",
    "publish_time",
    "detail_url",
    "fetched_at",
    "source_page",
]


def clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    compact = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return compact or None


def request_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
    retries: int = 3,
    retry_base_seconds: float = 1.2,
) -> Dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        req = Request(url=url, data=body, headers=DEFAULT_HEADERS, method=method.upper())
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

    raise RuntimeError(f"Request failed after {retries} retries: {url} ({last_err})")


def search_positions(
    page_index: int,
    page_size: int,
    keyword: str,
    batch_ids: List[str],
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    payload = {
        "channel": "campus_group_official_site",
        "language": "zh",
        "pageIndex": page_index,
        "pageSize": page_size,
        "regions": "",
        "subCategories": "",
        "bgCode": "",
        "key": keyword,
        "recruitType": [],
        "batchIds": batch_ids,
        "isStar": None,
    }
    return request_json("POST", API_POSITION_SEARCH, payload=payload, timeout=timeout, retries=retries)


def normalize_record(item: Dict[str, Any], source_page: int, fetched_at: str) -> Dict[str, Any]:
    job_id = item.get("id")
    title = clean_text(item.get("name"))

    work_cities = [
        clean_text(city)
        for city in (item.get("workLocations") or [])
        if isinstance(city, str) and clean_text(city)
    ]

    feature_tags = [
        clean_text(tag)
        for tag in (item.get("featureTagList") or [])
        if isinstance(tag, str) and clean_text(tag)
    ]

    position_tags = [
        clean_text(tag.get("tagName"))
        for tag in (item.get("positionTagList") or [])
        if isinstance(tag, dict) and clean_text(tag.get("tagName"))
    ]

    tags = []
    seen = set()
    for tag in feature_tags + position_tags:
        if tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)

    recruit_type = clean_text(item.get("batchName") or item.get("batchTypeDesc"))
    publish_time = clean_text(item.get("publishTime"))

    detail_url = None
    if job_id is not None:
        tid = clean_text(item.get("tid"))
        if tid:
            detail_url = f"https://talent.antgroup.com/campus-position?positionId={job_id}&tid={tid}"
        else:
            detail_url = f"https://talent.antgroup.com/campus-position?positionId={job_id}"

    return {
        "company": COMPANY,
        "job_id": str(job_id) if job_id is not None else None,
        "title": title,
        "recruit_type": recruit_type,
        "job_category": clean_text(item.get("categoryName")),
        "job_function": clean_text(item.get("positionType")),
        "work_city": work_cities[0] if work_cities else None,
        "work_cities": work_cities,
        "team_intro": clean_text(item.get("department") or item.get("project")),
        "responsibilities": clean_text(item.get("description")),
        "requirements": clean_text(item.get("requirement")),
        "bonus_points": clean_text(item.get("experience")),
        "tags": tags,
        "publish_time": publish_time,
        "detail_url": detail_url,
        "fetched_at": fetched_at,
        "source_page": source_page,
    }


def crawl_all(args: argparse.Namespace) -> List[Dict[str, Any]]:
    first_payload = search_positions(
        page_index=args.start_page,
        page_size=args.page_size,
        keyword=args.keyword,
        batch_ids=args.batch_ids,
        timeout=args.timeout,
        retries=args.retries,
    )

    if not first_payload.get("success", False):
        raise RuntimeError(f"Search API returned non-success: {first_payload}")

    total_count = int(first_payload.get("totalCount") or 0)
    total_pages = max(1, math.ceil(total_count / args.page_size)) if total_count > 0 else args.start_page
    effective_end = min(args.end_page, total_pages)

    print(f"batch_ids={args.batch_ids}")
    print(f"total_count={total_count}, page_size={args.page_size}, total_pages={total_pages}")
    print(f"crawl page range: {args.start_page}-{effective_end}")

    rows_by_id: Dict[str, Dict[str, Any]] = {}

    for page_index in range(args.start_page, effective_end + 1):
        if page_index == args.start_page:
            payload = first_payload
        else:
            payload = search_positions(
                page_index=page_index,
                page_size=args.page_size,
                keyword=args.keyword,
                batch_ids=args.batch_ids,
                timeout=args.timeout,
                retries=args.retries,
            )

        items = payload.get("content")
        if not isinstance(items, list):
            items = []

        print(f"[page={page_index}] list_items={len(items)}")
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            row = normalize_record(item=item, source_page=page_index, fetched_at=fetched_at)
            if row.get("job_id"):
                rows_by_id[row["job_id"]] = row

        time.sleep(random.uniform(args.page_delay_min, args.page_delay_max))

    rows = list(rows_by_id.values())
    rows.sort(key=lambda x: x.get("job_id") or "")
    return rows


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ant Group campus jobs crawler")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument(
        "--end-page",
        type=int,
        default=999,
        help="Last page to crawl. 999 means crawl to the current site max page.",
    )
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--keyword", type=str, default="", help="Optional keyword filter.")
    parser.add_argument(
        "--batch-id",
        dest="batch_ids",
        action="append",
        default=None,
        help="Campus batch ID. Can be specified multiple times.",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--page-delay-min", type=float, default=0.2)
    parser.add_argument("--page-delay-max", type=float, default=0.6)
    parser.add_argument("--jsonl", type=Path, default=Path("data/antgroup_jobs.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("data/antgroup_jobs.csv"))
    args = parser.parse_args()
    args.batch_ids = args.batch_ids or list(DEFAULT_BATCH_IDS)
    return args


def validate_args(args: argparse.Namespace) -> None:
    if args.start_page < 1 or args.end_page < args.start_page:
        raise ValueError("Invalid page range")
    if args.page_size < 1:
        raise ValueError("page-size must be >= 1")
    if args.timeout <= 0:
        raise ValueError("timeout must be > 0")
    if args.retries < 1:
        raise ValueError("retries must be >= 1")
    if args.page_delay_min < 0 or args.page_delay_max < args.page_delay_min:
        raise ValueError("Invalid page delay range")
    if not args.batch_ids:
        raise ValueError("At least one batch-id is required")


def main() -> None:
    args = parse_args()
    validate_args(args)

    rows = crawl_all(args)
    write_jsonl(args.jsonl, rows)
    write_csv(args.csv, rows)

    print(f"done: total_rows={len(rows)}")
    print(f"jsonl: {args.jsonl}")
    print(f"csv:   {args.csv}")


if __name__ == "__main__":
    main()
