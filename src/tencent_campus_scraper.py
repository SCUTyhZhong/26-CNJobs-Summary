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

COMPANY = "腾讯"
BASE_URL = "https://join.qq.com"

API_POSITION_SEARCH = f"{BASE_URL}/api/v1/position/searchPosition"
API_JOB_DETAIL = f"{BASE_URL}/api/v1/jobDetails/getJobDetailsByPostId"
API_PROJECT_MAPPING = f"{BASE_URL}/api/v1/position/getProjectMapping"
API_POSITION_WORK_CITIES = f"{BASE_URL}/api/v1/position/getPositionWorkCities"
API_POSITION_FAMILY = f"{BASE_URL}/api/v1/position/getPositionFamily"

DEFAULT_PROJECT_MAPPING_IDS = [2, 104, 1, 14, 20, 5]
POSITION_FAMILY_NAME_MAP = {
    1: "综合",
    2: "技术",
    3: "产品",
    4: "设计",
    5: "市场",
    6: "职能",
}
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE_URL}/post.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
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


def now_ms() -> int:
    return int(time.time() * 1000)


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
            sleep_seconds = retry_base_seconds * (2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Request failed after {retries} retries: {url} ({last_err})")


def get_json(endpoint: str, timeout: float, retries: int) -> Dict[str, Any]:
    query = urlencode({"timestamp": now_ms()})
    url = f"{endpoint}?{query}"
    return request_json("GET", url, payload=None, timeout=timeout, retries=retries)


def post_json(endpoint: str, payload: Dict[str, Any], timeout: float, retries: int) -> Dict[str, Any]:
    query = urlencode({"timestamp": now_ms()})
    url = f"{endpoint}?{query}"
    return request_json("POST", url, payload=payload, timeout=timeout, retries=retries)


def get_project_mapping_ids(timeout: float, retries: int) -> List[int]:
    payload = get_json(API_PROJECT_MAPPING, timeout=timeout, retries=retries)
    data = payload.get("data")
    if not isinstance(data, list):
        return DEFAULT_PROJECT_MAPPING_IDS

    ids: List[int] = []
    for group in data:
        if not isinstance(group, dict):
            continue
        sub_projects = group.get("subProjectList")
        if not isinstance(sub_projects, list):
            continue
        for project in sub_projects:
            if not isinstance(project, dict):
                continue
            mapping_id = project.get("mappingId")
            status = str(project.get("status") or "1")
            if isinstance(mapping_id, int) and status == "1":
                ids.append(mapping_id)

    if not ids:
        return DEFAULT_PROJECT_MAPPING_IDS

    ordered_unique: List[int] = []
    seen = set()
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        ordered_unique.append(value)
    return ordered_unique


def get_work_city_map(timeout: float, retries: int) -> Dict[str, str]:
    payload = get_json(API_POSITION_WORK_CITIES, timeout=timeout, retries=retries)
    data = payload.get("data")
    mapping: Dict[str, str] = {}
    if not isinstance(data, dict):
        return mapping

    for group in data.values():
        if not isinstance(group, list):
            continue
        for city in group:
            if not isinstance(city, dict):
                continue
            code = str(city.get("code") or "").strip()
            name = str(city.get("name") or "").strip()
            if code and name:
                mapping[code] = name

    # Align with site display wording.
    if mapping.get("1") == "深圳":
        mapping["1"] = "深圳总部"

    return mapping


def get_position_title_map(timeout: float, retries: int) -> Dict[int, str]:
    payload = get_json(API_POSITION_FAMILY, timeout=timeout, retries=retries)
    data = payload.get("data")
    mapping: Dict[int, str] = {}
    if not isinstance(data, dict):
        return mapping

    for category_list in data.values():
        if not isinstance(category_list, list):
            continue
        for item in category_list:
            if not isinstance(item, dict):
                continue
            position_id = item.get("id")
            title = str(item.get("title") or "").strip()
            if isinstance(position_id, int) and title:
                mapping[position_id] = title
    return mapping


def search_positions_page(
    page_index: int,
    page_size: int,
    project_mapping_ids: List[int],
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    payload = {
        "projectIdList": [],
        "projectMappingIdList": project_mapping_ids,
        "keyword": "",
        "bgList": [],
        "workCountryType": 0,
        "workCityList": [],
        "recruitCityList": [],
        "positionFidList": [],
        "pageIndex": page_index,
        "pageSize": page_size,
    }
    return post_json(API_POSITION_SEARCH, payload=payload, timeout=timeout, retries=retries)


def get_job_detail(post_id: str, timeout: float, retries: int) -> Dict[str, Any]:
    query = urlencode({"timestamp": now_ms(), "postId": post_id})
    url = f"{API_JOB_DETAIL}?{query}"
    payload = request_json("GET", url, timeout=timeout, retries=retries)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def parse_city_codes(raw: Optional[str], city_map: Dict[str, str]) -> List[str]:
    if not raw:
        return []
    out: List[str] = []
    seen = set()
    for code in str(raw).split(","):
        token = code.strip()
        if not token:
            continue
        city = city_map.get(token, token)
        if city in seen:
            continue
        seen.add(city)
        out.append(city)
    return out


def normalize_record(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    city_map: Dict[str, str],
    position_title_map: Dict[int, str],
    source_page: int,
    fetched_at: str,
) -> Dict[str, Any]:
    post_id = str(item.get("postId") or detail.get("postId") or "").strip()

    title = clean_text(str(detail.get("title") or item.get("positionTitle") or ""))
    recruit_type = clean_text(str(item.get("recruitLabelName") or detail.get("recruitLabelName") or ""))

    position_id = item.get("position")
    category_name = clean_text(str(detail.get("tidName") or ""))
    if not category_name:
        category_name = position_title_map.get(position_id) if isinstance(position_id, int) else None
    if not category_name:
        family = item.get("positionFamily")
        if isinstance(family, int):
            category_name = POSITION_FAMILY_NAME_MAP.get(family)
        if not category_name:
            category_name = clean_text(str(family or ""))

    detail_city_list = detail.get("workCityList")
    if isinstance(detail_city_list, list):
        work_cities = [str(city).strip() for city in detail_city_list if str(city).strip()]
    else:
        work_cities = []

    if not work_cities:
        work_cities = parse_city_codes(detail.get("workCity"), city_map)
    if not work_cities:
        raw_cities = clean_text(str(item.get("workCities") or ""))
        if raw_cities:
            work_cities = [c for c in raw_cities.split() if c]

    bonus_points = clean_text(str(detail.get("internBonus") or detail.get("graduateBonus") or ""))

    return {
        "company": COMPANY,
        "job_id": post_id,
        "title": title,
        "recruit_type": recruit_type,
        "job_category": category_name,
        "job_function": None,
        "work_city": work_cities[0] if work_cities else None,
        "work_cities": work_cities,
        "team_intro": clean_text(str(detail.get("introduction") or "")),
        "responsibilities": clean_text(str(detail.get("desc") or "")),
        "requirements": clean_text(str(detail.get("request") or "")),
        "bonus_points": bonus_points,
        "tags": [],
        "publish_time": None,
        "detail_url": f"{BASE_URL}/post_detail.html?postid={post_id}" if post_id else None,
        "fetched_at": fetched_at,
        "source_page": source_page,
    }


def crawl_all(args: argparse.Namespace) -> List[Dict[str, Any]]:
    project_mapping_ids = get_project_mapping_ids(timeout=args.timeout, retries=args.retries)
    city_map = get_work_city_map(timeout=args.timeout, retries=args.retries)
    position_title_map = get_position_title_map(timeout=args.timeout, retries=args.retries)

    first_page = search_positions_page(
        page_index=args.start_page,
        page_size=args.page_size,
        project_mapping_ids=project_mapping_ids,
        timeout=args.timeout,
        retries=args.retries,
    )

    first_data = first_page.get("data") or {}
    total_count = int(first_data.get("count") or 0)
    total_pages = max(1, math.ceil(total_count / args.page_size))

    effective_end = min(args.end_page, total_pages)
    print(f"project_mapping_ids={project_mapping_ids}")
    print(f"total_count={total_count}, page_size={args.page_size}, total_pages={total_pages}")
    print(f"crawl page range: {args.start_page}-{effective_end}")

    records_by_id: Dict[str, Dict[str, Any]] = {}

    for page_index in range(args.start_page, effective_end + 1):
        if page_index == args.start_page:
            page_payload = first_page
        else:
            page_payload = search_positions_page(
                page_index=page_index,
                page_size=args.page_size,
                project_mapping_ids=project_mapping_ids,
                timeout=args.timeout,
                retries=args.retries,
            )

        data = page_payload.get("data") or {}
        items = data.get("positionList") or []
        if not isinstance(items, list):
            items = []

        print(f"[page={page_index}] list_items={len(items)}")
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue

            post_id = str(item.get("postId") or "").strip()
            if not post_id:
                continue

            try:
                detail = get_job_detail(post_id=post_id, timeout=args.timeout, retries=args.retries)
            except Exception as exc:
                print(f"[detail] postId={post_id} failed: {exc}")
                detail = {}

            row = normalize_record(
                item=item,
                detail=detail,
                city_map=city_map,
                position_title_map=position_title_map,
                source_page=page_index,
                fetched_at=fetched_at,
            )
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
    parser = argparse.ArgumentParser(description="Tencent campus jobs crawler")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument(
        "--end-page",
        type=int,
        default=999,
        help="Last page to crawl. 999 means crawl to the current site max page.",
    )
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)

    parser.add_argument("--page-delay-min", type=float, default=0.2)
    parser.add_argument("--page-delay-max", type=float, default=0.6)
    parser.add_argument("--detail-delay-min", type=float, default=0.05)
    parser.add_argument("--detail-delay-max", type=float, default=0.2)

    parser.add_argument("--jsonl", type=Path, default=Path("data/tencent_jobs.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("data/tencent_jobs.csv"))
    return parser.parse_args()


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
