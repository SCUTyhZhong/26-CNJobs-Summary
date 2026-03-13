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
from urllib.parse import urlencode
from urllib.request import Request, urlopen

COMPANY = "网易互娱"
BASE_URL = "https://campus.game.163.com"

API_POSITION_LIST = f"{BASE_URL}/api/recruitment/campus/position/list"
API_POSITION_DETAIL = f"{BASE_URL}/api/recruitment/campus/position/detail"
API_POSITION_FILTERS = f"{BASE_URL}/api/recruitment/campus/position/filters"

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE_URL}/position/30",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
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


def get_json(endpoint: str, params: Optional[Dict[str, Any]], timeout: float, retries: int) -> Dict[str, Any]:
    query = urlencode(params or {})
    url = endpoint if not query else f"{endpoint}?{query}"
    return request_json("GET", url, timeout=timeout, retries=retries)


def post_json(endpoint: str, payload: Dict[str, Any], timeout: float, retries: int) -> Dict[str, Any]:
    return request_json("POST", endpoint, payload=payload, timeout=timeout, retries=retries)


def build_list_payload(project_id: int, page_num: int) -> Dict[str, Any]:
    return {
        "projectIds": [project_id],
        "positionTypeIds": [],
        "workplaceIds": [],
        "positionExternalTagIds": [],
        "attributeTypes": [],
        "pageNum": page_num,
    }


def fetch_filters(project_id: int, timeout: float, retries: int) -> Dict[str, Any]:
    payload = get_json(API_POSITION_FILTERS, {"projectId": project_id}, timeout=timeout, retries=retries)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def fetch_position_list(project_id: int, page_num: int, timeout: float, retries: int) -> Dict[str, Any]:
    payload = post_json(
        API_POSITION_LIST,
        payload=build_list_payload(project_id=project_id, page_num=page_num),
        timeout=timeout,
        retries=retries,
    )
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def fetch_position_detail(position_id: int, timeout: float, retries: int) -> Dict[str, Any]:
    payload = get_json(API_POSITION_DETAIL, {"positionId": position_id}, timeout=timeout, retries=retries)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def extract_city_names(work_cities: Any) -> List[str]:
    if not isinstance(work_cities, list):
        return []
    cities: List[str] = []
    seen = set()
    for item in work_cities:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("cityName"))
        if not name or name in seen:
            continue
        seen.add(name)
        cities.append(name)
    return cities


def extract_tag_names(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []
    out: List[str] = []
    seen = set()
    for item in tags:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("tagName"))
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def derive_job_category(info: Dict[str, Any], item: Dict[str, Any]) -> Optional[str]:
    category = clean_text(info.get("positionTypeAbbreviation"))
    if category:
        return category

    position_types = info.get("positionTypes") or item.get("positionTypes") or []
    if isinstance(position_types, list) and position_types:
        readable = []
        for entry in position_types:
            if not isinstance(entry, dict):
                continue
            type_name = clean_text(entry.get("typeName"))
            if type_name:
                readable.append(type_name)
        if readable:
            return "-".join(readable)
    return None


def normalize_record(item: Dict[str, Any], detail: Dict[str, Any], source_page: int, fetched_at: str) -> Dict[str, Any]:
    info = detail.get("info") if isinstance(detail.get("info"), dict) else {}
    position_id = item.get("positionId") or detail.get("positionId")
    work_cities = extract_city_names(info.get("workCities") or item.get("workCities"))
    tags = extract_tag_names(info.get("externalTags"))

    return {
        "company": COMPANY,
        "job_id": str(position_id) if position_id is not None else None,
        "title": clean_text(info.get("externalPositionName") or item.get("externalPositionName")),
        "recruit_type": clean_text(info.get("projectName")),
        "job_category": derive_job_category(info, item),
        "job_function": None,
        "work_city": work_cities[0] if work_cities else None,
        "work_cities": work_cities,
        "team_intro": clean_text(info.get("externalVolunteerDept")),
        "responsibilities": clean_text(info.get("positionDescription")),
        "requirements": clean_text(info.get("positionRequirement")),
        "bonus_points": None,
        "tags": tags,
        "publish_time": clean_text(detail.get("publishedAt") or item.get("publishedAt")),
        "detail_url": f"{BASE_URL}/position-detail/{position_id}" if position_id is not None else None,
        "fetched_at": fetched_at,
        "source_page": source_page,
    }


def crawl_all(args: argparse.Namespace) -> List[Dict[str, Any]]:
    filters = fetch_filters(project_id=args.project_id, timeout=args.timeout, retries=args.retries)
    first_page = fetch_position_list(
        project_id=args.project_id,
        page_num=args.start_page,
        timeout=args.timeout,
        retries=args.retries,
    )

    total_count = int(first_page.get("count") or 0)
    page_size = len(first_page.get("list") or []) or 15
    total_pages = max(1, math.ceil(total_count / page_size))
    effective_end = min(args.end_page, total_pages)

    print(f"project_id={args.project_id}")
    print(f"filters_loaded={bool(filters)}")
    print(f"total_count={total_count}, page_size={page_size}, total_pages={total_pages}")
    print(f"crawl page range: {args.start_page}-{effective_end}")

    records_by_id: Dict[str, Dict[str, Any]] = {}

    for page_num in range(args.start_page, effective_end + 1):
        if page_num == args.start_page:
            page_data = first_page
        else:
            page_data = fetch_position_list(
                project_id=args.project_id,
                page_num=page_num,
                timeout=args.timeout,
                retries=args.retries,
            )

        items = page_data.get("list")
        if not isinstance(items, list):
            items = []

        print(f"[page={page_num}] list_items={len(items)}")
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue

            position_id = item.get("positionId")
            if not isinstance(position_id, int):
                continue

            try:
                detail = fetch_position_detail(position_id=position_id, timeout=args.timeout, retries=args.retries)
            except Exception as exc:
                print(f"[detail] positionId={position_id} failed: {exc}")
                detail = {}

            row = normalize_record(item=item, detail=detail, source_page=page_num, fetched_at=fetched_at)
            if row.get("job_id"):
                records_by_id[row["job_id"]] = row

            time.sleep(random.uniform(args.detail_delay_min, args.detail_delay_max))

        time.sleep(random.uniform(args.page_delay_min, args.page_delay_max))

    rows = list(records_by_id.values())
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
    parser = argparse.ArgumentParser(description="NetEase campus jobs crawler")
    parser.add_argument("--project-id", type=int, default=30, help="Project ID from /position/{id} URL.")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument(
        "--end-page",
        type=int,
        default=999,
        help="Last page to crawl. 999 means crawl to the current site max page.",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--page-delay-min", type=float, default=0.2)
    parser.add_argument("--page-delay-max", type=float, default=0.6)
    parser.add_argument("--detail-delay-min", type=float, default=0.05)
    parser.add_argument("--detail-delay-max", type=float, default=0.2)
    parser.add_argument("--jsonl", type=Path, default=Path("data/netease_jobs.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("data/netease_jobs.csv"))
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.project_id < 1:
        raise ValueError("project-id must be >= 1")
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
    print(f"jsonl: {args.jsonl}")
    print(f"csv:   {args.csv}")


if __name__ == "__main__":
    main()