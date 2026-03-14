"""Bilibili campus jobs spider.

Flow: GET csrf_token → POST list (paginated) → [GET detail (optional)] → JobItem

Pass ``-a fetch_detail=1`` to enable per-position detail enrichment (slower).
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

import scrapy
from scrapy.http import JsonRequest

from crawlers.items import JobItem

COMPANY  = "哔哩哔哩"
BASE_URL = "https://jobs.bilibili.com"

API_CSRF   = f"{BASE_URL}/api/auth/v1/csrf/token"
API_LIST   = f"{BASE_URL}/api/campus/position/positionList"
API_DETAIL = f"{BASE_URL}/api/campus/position/detail"

_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/campus/positions?type=0",
    "x-appkey": "ops.ehr-api.auth",
    "x-usertype": "2",
    "x-channel": "campus",
}

_BONUS_SECTIONS = re.compile(r"\n{0,2}加分项\s*[：:]\s*", re.IGNORECASE)
_SECTION_SPLIT  = re.compile(r"(岗位职责:|任职要求:|岗位要求:|加分项:)", re.IGNORECASE)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def _strip_html(text: Any) -> str:
    raw = str(text or "")
    raw = raw.replace("<br/>", "\n").replace("<br>", "\n").replace("<br />", "\n")
    raw = re.sub(r"</p>\s*<p>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", "", raw)
    return raw.strip()


def _split_description(text: Any):
    """Return (responsibilities, requirements, bonus_points) from raw JD text."""
    plain = _strip_html(text)
    if not plain:
        return None, None, None
    normalized = plain.replace("：", ":")
    parts = _SECTION_SPLIT.split(normalized)
    if len(parts) < 3:
        return _clean(plain), None, None

    sections: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        key = parts[i].rstrip(":").strip()
        value = parts[i + 1].strip()
        sections[key] = value
        i += 2

    resp = _clean(sections.get("岗位职责") or sections.get("工作职责"))
    req  = _clean(sections.get("任职要求") or sections.get("岗位要求"))
    bonus = _clean(sections.get("加分项"))
    return resp, req, bonus


class BilibiliSpider(scrapy.Spider):
    name = "bilibili"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
    }

    def __init__(self, start_page: int = 1, end_page: int = 9999,
                 page_size: int = 10, fetch_detail: int = 0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_page  = int(start_page)
        self.end_page    = int(end_page)
        self.page_size   = int(page_size)
        self.fetch_detail = bool(int(fetch_detail))

    # ── CSRF bootstrap ────────────────────────────────────────────────────────

    def start_requests(self):
        yield scrapy.Request(
            url=API_CSRF,
            headers=_HEADERS,
            callback=self.parse_csrf,
        )

    def parse_csrf(self, response):
        payload = response.json()
        if payload.get("code") != 0:
            self.logger.error(f"[bilibili] csrf failed: {payload}")
            return
        token = str(payload.get("data") or "").strip()
        if not token:
            self.logger.error("[bilibili] csrf token empty")
            return
        headers = dict(_HEADERS, **{"x-csrf": token})
        meta = {
            "headers": headers,
            "page": self.start_page,
            "total_pages": 9999,
        }
        yield self._list_request(headers, self.start_page, meta)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _list_payload(self, page: int) -> dict:
        return {
            "pageSize": self.page_size,
            "pageNum": page,
            "positionName": "",
            "postCode": [],
            "postCodeList": [],
            "workLocationList": [],
            "workTypeList": ["0"],
            "positionTypeList": ["0"],
            "deptCodeList": [],
            "recruitType": None,
            "practiceTypes": [],
            "onlyHotRecruit": 0,
        }

    def _list_request(self, headers: dict, page: int, meta: dict):
        return JsonRequest(
            url=API_LIST,
            data=self._list_payload(page),
            headers=headers,
            callback=self.parse_list,
            meta=dict(meta, page=page),
        )

    def parse_list(self, response):
        payload = response.json()
        if payload.get("code") != 0:
            self.logger.warning(f"[bilibili] list error: {payload.get('message')}")
            return

        data = payload.get("data") or {}
        meta = response.meta

        if meta["total_pages"] == 9999:
            total = int(data.get("total") or 0)
            meta["total_pages"] = max(1, math.ceil(total / self.page_size)) if total else self.start_page
            effective_end = min(self.end_page, meta["total_pages"])
            meta["effective_end"] = effective_end
            self.logger.info(
                f"[bilibili] total={total}, pages={meta['total_pages']}, "
                f"crawl={self.start_page}-{effective_end}"
            )

        items = data.get("list") or []
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        headers = meta["headers"]

        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "").strip()
            if not job_id:
                continue
            if self.fetch_detail:
                yield scrapy.Request(
                    url=f"{API_DETAIL}/{job_id}",
                    headers=headers,
                    callback=self.parse_detail,
                    meta={"list_item": item, "source_page": meta["page"], "fetched_at": fetched_at},
                )
            else:
                yield self._make_item(item, {}, meta["page"], fetched_at)

        page = meta["page"]
        effective_end = meta.get("effective_end", self.end_page)
        if page < min(self.end_page, effective_end):
            page += 1
            yield self._list_request(headers, page, meta)

    def parse_detail(self, response):
        m = response.meta
        payload = response.json()
        detail: dict = {}
        if payload.get("code") == 0:
            d = payload.get("data")
            if isinstance(d, dict):
                detail = d
        yield self._make_item(m["list_item"], detail, m["source_page"], m["fetched_at"])

    # ── Normalization ─────────────────────────────────────────────────────────

    def _make_item(self, item: dict, detail: dict, source_page: int, fetched_at: str) -> JobItem:
        merged = dict(item)
        merged.update({k: v for k, v in detail.items() if v is not None})

        job_id = str(merged.get("id") or "").strip()
        work_city = _clean(merged.get("workLocation"))
        work_cities = [work_city] if work_city else []

        responsibilities, requirements, bonus = _split_description(merged.get("positionDescription"))

        tags: list[str] = []
        highlights = _clean(merged.get("jobHighlights"))
        if highlights:
            tags.append(highlights)

        return JobItem(
            company=COMPANY,
            job_id=job_id or None,
            title=_clean(merged.get("positionName")),
            recruit_type=_clean(merged.get("positionTypeName")),
            job_category=_clean(merged.get("postCodeName")),
            job_function=_clean(merged.get("positionTypeName")),
            work_city=work_city,
            work_cities=work_cities,
            team_intro=_clean(merged.get("deptIntro")),
            responsibilities=responsibilities,
            requirements=requirements,
            bonus_points=bonus,
            tags=tags,
            publish_time=_clean(merged.get("pushTime")),
            detail_url=f"{BASE_URL}/campus/positions/{job_id}" if job_id else None,
            fetched_at=fetched_at,
            source_page=source_page,
        )
