import argparse
import csv
import datetime as dt
import json
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page, sync_playwright

COMPANY = "字节跳动"
BASE_LIST_URL = "https://jobs.bytedance.com/campus/position"
PROJECT_ID = "7194661126919358757"

# ── text-splitting helpers ────────────────────────────────────────────────────
_BONUS_RE = re.compile(r"\n{0,2}加分项\s*[：:]\s*", re.IGNORECASE)
_TEAM_INTRO_RE = re.compile(r"团队介绍\s*[：:]\s*")
_NUMBERED_RE = re.compile(r"^\s*\d+\s*[、．.]\s*", re.MULTILINE)


def split_requirement(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (requirements, bonus_points) by splitting on '加分项：'."""
    if not text:
        return None, None
    parts = _BONUS_RE.split(text, maxsplit=1)
    main = parts[0].strip() or None
    bonus = parts[1].strip() if len(parts) > 1 else None
    return main, bonus


def split_description(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (team_intro, responsibilities) extracted from raw description."""
    if not text:
        return None, None
    intro_match = _TEAM_INTRO_RE.search(text)
    if not intro_match:
        numbered = _NUMBERED_RE.search(text)
        if numbered:
            return None, text[numbered.start():].strip() or None
        return None, text.strip() or None
    after_intro = text[intro_match.end():]
    numbered = _NUMBERED_RE.search(after_intro)
    if numbered:
        team_intro = after_intro[: numbered.start()].strip() or None
        responsibilities = after_intro[numbered.start() :].strip() or None
    else:
        team_intro = after_intro.strip() or None
        responsibilities = None
    return team_intro, responsibilities


# ── URL helpers ───────────────────────────────────────────────────────────────

def build_list_url(current: int, limit: int) -> str:
    return (
        f"{BASE_LIST_URL}?keywords=&category=&location=&"
        f"project={PROJECT_ID}&type=&job_hot_flag=&"
        f"current={current}&limit={limit}&functionCategory=&tag=&storefront_id_list="
    )


# ── API response parsing ──────────────────────────────────────────────────────

def extract_posts_from_responses(responses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for payload in reversed(responses):
        if payload.get("code") == 0:
            data = payload.get("data") or {}
            posts = data.get("job_post_list") or []
            if isinstance(posts, list):
                return posts
    return []


def capture_page_posts(page: Page, list_url: str) -> List[Dict[str, Any]]:
    api_payloads: List[Dict[str, Any]] = []

    def on_response(response):
        if "/api/v1/search/job/posts" not in response.url:
            return
        if response.request.method.upper() != "POST":
            return
        if response.status != 200:
            return
        try:
            body = response.json()
            if isinstance(body, dict):
                api_payloads.append(body)
        except Exception:
            return

    page.on("response", on_response)
    try:
        # Some telemetry requests keep connections open, so use DOM load + short wait.
        page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
    finally:
        page.remove_listener("response", on_response)

    return extract_posts_from_responses(api_payloads)


def fallback_extract_cards(page: Page, current_page: int, list_url: str, fetched_at: str) -> List[Dict[str, Any]]:
    cards = page.eval_on_selector_all(
        "a[href*='/campus/position/'][href*='/detail']",
        r"""
        els => els.map(el => {
          const href = el.getAttribute('href') || '';
          const abs = href.startsWith('http') ? href : `https://jobs.bytedance.com${href}`;
          const text = (el.innerText || '').trim();
          const firstLine = text.split('\n').map(x => x.trim()).filter(Boolean)[0] || null;
          const m = abs.match(/\/position\/(\d+)\/detail/);
          return {
            job_id: m ? m[1] : null,
            title: firstLine,
            description: text || null,
            detail_url: abs,
          };
        })
        """,
    )

    records: List[Dict[str, Any]] = []
    for card in cards:
        job_id = str((card or {}).get("job_id") or "").strip()
        if not job_id:
            continue
        _, responsibilities = split_description(card.get("description"))
        records.append(
            {
                "company": COMPANY,
                "job_id": job_id,
                "title": card.get("title"),
                "recruit_type": None,
                "job_category": None,
                "job_function": None,
                "work_city": None,
                "work_cities": [],
                "team_intro": None,
                "responsibilities": responsibilities,
                "requirements": None,
                "bonus_points": None,
                "tags": [],
                "publish_time": None,
                "detail_url": card.get("detail_url"),
                "fetched_at": fetched_at,
                "source_page": current_page,
            }
        )

    unique: Dict[str, Dict[str, Any]] = {}
    for row in records:
        unique[row["job_id"]] = row
    return list(unique.values())


def normalize_post(post: Dict[str, Any], current_page: int, list_url: str, fetched_at: str) -> Dict[str, Any]:
    city_info = post.get("city_info") or {}
    city_list = post.get("city_list") or []
    recruit_type_obj = post.get("recruit_type") or {}
    job_category_obj = post.get("job_category") or {}
    job_function_obj = post.get("job_function") or {}
    tag_list = post.get("tag_list") or []

    job_id = str(post.get("id", "")).strip()
    work_cities = [c.get("name") for c in city_list if isinstance(c, dict) and c.get("name")]
    tags = [t.get("name") for t in tag_list if isinstance(t, dict) and t.get("name")]

    team_intro, responsibilities = split_description(post.get("description"))
    requirements, bonus_points = split_requirement(post.get("requirement"))

    return {
        "company": COMPANY,
        "job_id": job_id,
        "title": post.get("title"),
        "recruit_type": recruit_type_obj.get("name"),
        "job_category": job_category_obj.get("name"),
        "job_function": job_function_obj.get("name") if isinstance(job_function_obj, dict) else None,
        "work_city": city_info.get("name"),
        "work_cities": work_cities,
        "team_intro": team_intro,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "bonus_points": bonus_points,
        "tags": tags,
        "publish_time": post.get("publish_time"),
        "detail_url": f"https://jobs.bytedance.com/campus/position/{job_id}/detail" if job_id else None,
        "fetched_at": fetched_at,
        "source_page": current_page,
    }


def crawl_range(
    context: BrowserContext,
    start_page: int,
    end_page: int,
    limit: int,
    delay_min: float,
    delay_max: float,
    auto_stop_after: int = 3,
) -> List[Dict[str, Any]]:
    page = context.new_page()
    records_by_id: Dict[str, Dict[str, Any]] = {}
    empty_streak = 0

    for current in range(start_page, end_page + 1):
        list_url = build_list_url(current=current, limit=limit)
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        try:
            posts = capture_page_posts(page=page, list_url=list_url)
        except Exception as exc:
            print(f"[page={current}] capture failed: {exc}")
            posts = []

        if posts:
            print(f"[page={current}] posts={len(posts)} via api")
            for post in posts:
                record = normalize_post(post=post, current_page=current, list_url=list_url, fetched_at=fetched_at)
                job_id = record.get("job_id")
                if not job_id:
                    continue
                records_by_id[job_id] = record
            empty_streak = 0
        else:
            fallback_rows = fallback_extract_cards(
                page=page,
                current_page=current,
                list_url=list_url,
                fetched_at=fetched_at,
            )
            if fallback_rows:
                print(f"[page={current}] posts={len(fallback_rows)} via dom fallback")
                for row in fallback_rows:
                    records_by_id[row["job_id"]] = row
                empty_streak = 0
            else:
                empty_streak += 1
                print(f"[page={current}] empty ({empty_streak}/{auto_stop_after})")
                if empty_streak >= auto_stop_after:
                    print(f"[auto-stop] {auto_stop_after} consecutive empty pages — stopping at page {current}.")
                    break

        sleep_seconds = random.uniform(delay_min, delay_max)
        time.sleep(sleep_seconds)

    page.close()
    return list(records_by_id.values())


def _load_existing_keys(csv_path: Path) -> set[Tuple[str, str]]:
    keys: set[Tuple[str, str]] = set()
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return keys
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = (row.get("company") or "").strip()
            j = (row.get("job_id") or "").strip()
            if c and j:
                keys.add((c, j))
    return keys


# Ordered columns for CSV output
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


def append_incremental(csv_path: Path, jsonl_path: Path, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Append only unseen (company, job_id) rows into unified dataset files."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_existing_keys(csv_path)
    seen_this_run: set[Tuple[str, str]] = set()

    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
    written = 0
    skipped = 0

    with csv_path.open("a", encoding="utf-8", newline="") as csv_fh, jsonl_path.open("a", encoding="utf-8") as jsonl_fh:
        writer = csv.DictWriter(csv_fh, fieldnames=_CSV_HEADER, extrasaction="ignore")
        if needs_header:
            writer.writeheader()

        for row in rows:
            key = ((row.get("company") or "").strip(), (row.get("job_id") or "").strip())
            if not key[0] or not key[1]:
                skipped += 1
                continue
            if key in existing or key in seen_this_run:
                skipped += 1
                continue

            output = dict(row)
            output["work_cities"] = "|".join(output.get("work_cities") or [])
            output["tags"] = "|".join(output.get("tags") or [])
            writer.writerow(output)

            jsonl_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            seen_this_run.add(key)
            written += 1

    return written, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ByteDance campus jobs crawler")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=999,
                        help="Last page to crawl. Combined with auto-stop, 999 effectively means 'all'.")
    parser.add_argument("--limit", type=int, default=10, help="Jobs per page (max 20).")
    parser.add_argument("--delay-min", type=float, default=1.5)
    parser.add_argument("--delay-max", type=float, default=3.0)
    parser.add_argument("--auto-stop-after", type=int, default=3,
                        help="Stop after N consecutive empty pages (default 3).")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode.")
    parser.add_argument(
        "--browser-channel",
        type=str,
        default="msedge",
        choices=["msedge", "chrome", "chromium"],
        help="Browser channel. Use 'chromium' for Playwright bundled browser.",
    )
    parser.add_argument("--jsonl", type=Path, default=Path("data/jobs.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("data/jobs.csv"))
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.start_page < 1 or args.end_page < args.start_page:
        raise ValueError("Invalid page range")
    if args.limit < 1:
        raise ValueError("limit must be >= 1")
    if args.delay_min < 0 or args.delay_max < args.delay_min:
        raise ValueError("Invalid delay range")


def main() -> None:
    args = parse_args()
    validate_args(args)

    print(f"Crawl range: page {args.start_page}–{args.end_page}, limit={args.limit}")
    print(f"Auto-stop after {args.auto_stop_after} consecutive empty pages.")
    print(f"Output → {args.jsonl}  /  {args.csv}")

    with sync_playwright() as p:
        launch_kwargs: Dict[str, Any] = {"headless": not args.headed}
        if args.browser_channel != "chromium":
            launch_kwargs["channel"] = args.browser_channel

        try:
            browser = p.chromium.launch(**launch_kwargs)
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                print("Playwright browser executable not found.")
                print("Run:  python -m playwright install chromium")
                print("Or:   --browser-channel msedge / chrome")
            raise

        context = browser.new_context(locale="zh-CN")
        try:
            rows = crawl_range(
                context=context,
                start_page=args.start_page,
                end_page=args.end_page,
                limit=args.limit,
                delay_min=args.delay_min,
                delay_max=args.delay_max,
                auto_stop_after=args.auto_stop_after,
            )
        finally:
            context.close()
            browser.close()

    rows.sort(key=lambda x: x.get("job_id") or "")
    written, skipped = append_incremental(args.csv, args.jsonl, rows)
    print(
        f"\ndone: crawled={len(rows)}, written={written}, skipped={skipped}  "
        f"→ {args.jsonl} / {args.csv}"
    )


if __name__ == "__main__":
    main()
