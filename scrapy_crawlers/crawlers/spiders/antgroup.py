"""Ant Group (蚂蚁集团) campus jobs spider.

Flow: POST search (paginated, list only — no separate detail endpoint) → JobItem

All fields are returned directly from the search API.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

import scrapy
from scrapy.http import JsonRequest

from crawlers.items import JobItem

COMPANY  = "阿里巴巴(蚂蚁集团)"
BASE_URL = "https://hrcareersweb.antgroup.com"
SITE_URL = "https://talent.antgroup.com"

API_SEARCH = f"{BASE_URL}/api/campus/position/search"

DEFAULT_BATCH_IDS = ["26022600074513"]

_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": SITE_URL,
    "Referer": f"{SITE_URL}/campus-full-list",
}


def _clean(value: Any) -> str | None:
    if not value:
        return None
    s = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return s or None


class AntgroupSpider(scrapy.Spider):
    name = "antgroup"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.4,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def __init__(self, start_page: int = 1, end_page: int = 9999,
                 page_size: int = 20, keyword: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_page = int(start_page)
        self.end_page   = int(end_page)
        self.page_size  = int(page_size)
        self.keyword    = keyword
        self.batch_ids  = list(DEFAULT_BATCH_IDS)

    def start_requests(self):
        meta = {"page": self.start_page, "total_pages": 9999}
        yield self._search_request(self.start_page, meta)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _search_payload(self, page: int) -> dict:
        return {
            "channel": "campus_group_official_site",
            "language": "zh",
            "pageIndex": page,
            "pageSize": self.page_size,
            "regions": "",
            "subCategories": "",
            "bgCode": "",
            "key": self.keyword,
            "recruitType": [],
            "batchIds": self.batch_ids,
            "isStar": None,
        }

    def _search_request(self, page: int, meta: dict):
        return JsonRequest(
            url=API_SEARCH,
            data=self._search_payload(page),
            headers=_HEADERS,
            callback=self.parse_list,
            meta=dict(meta, page=page),
        )

    def parse_list(self, response):
        payload = response.json()
        # response may nest under "data" or be the result directly
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        meta = response.meta

        if meta["total_pages"] == 9999:
            total = int(data.get("total") or data.get("totalSize") or 0)
            meta["total_pages"] = max(1, math.ceil(total / self.page_size)) if total else self.start_page
            effective_end = min(self.end_page, meta["total_pages"])
            meta["effective_end"] = effective_end
            self.logger.info(
                f"[antgroup] total={total}, pages={meta['total_pages']}, "
                f"crawl={self.start_page}-{effective_end}"
            )

        items = data.get("positionInfos") or data.get("list") or []
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            yield self._make_item(item, meta["page"], fetched_at)

        page = meta["page"]
        effective_end = meta.get("effective_end", self.end_page)
        if page < min(self.end_page, effective_end):
            yield self._search_request(page + 1, meta)

    # ── Normalization ─────────────────────────────────────────────────────────

    def _make_item(self, item: dict, source_page: int, fetched_at: str) -> JobItem:
        job_id = item.get("id")

        work_cities = [
            _clean(c) for c in (item.get("workLocations") or [])
            if isinstance(c, str) and _clean(c)
        ]

        feature_tags = [_clean(t) for t in (item.get("featureTagList") or []) if isinstance(t, str)]
        position_tags = [
            _clean(t.get("tagName")) for t in (item.get("positionTagList") or [])
            if isinstance(t, dict)
        ]
        seen: set[str] = set()
        tags: list[str] = []
        for t in feature_tags + position_tags:
            if t and t not in seen:
                seen.add(t)
                tags.append(t)

        detail_url = None
        if job_id is not None:
            tid = _clean(item.get("tid"))
            detail_url = (
                f"{SITE_URL}/campus-position?positionId={job_id}&tid={tid}"
                if tid
                else f"{SITE_URL}/campus-position?positionId={job_id}"
            )

        return JobItem(
            company=COMPANY,
            job_id=str(job_id) if job_id is not None else None,
            title=_clean(item.get("name")),
            recruit_type=_clean(item.get("batchName") or item.get("batchTypeDesc")),
            job_category=_clean(item.get("categoryName")),
            job_function=_clean(item.get("positionType")),
            work_city=work_cities[0] if work_cities else None,
            work_cities=work_cities,
            team_intro=_clean(item.get("department") or item.get("project")),
            responsibilities=_clean(item.get("description")),
            requirements=_clean(item.get("requirement")),
            bonus_points=_clean(item.get("experience")),
            tags=tags,
            publish_time=_clean(item.get("publishTime")),
            detail_url=detail_url,
            fetched_at=fetched_at,
            source_page=source_page,
        )
