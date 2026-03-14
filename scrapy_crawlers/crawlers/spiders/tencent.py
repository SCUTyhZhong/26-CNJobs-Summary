"""Tencent campus jobs spider.

Flow: GET project_mapping → GET city_map → GET position_family
      → POST list (paginated) → POST detail (per item) → JobItem
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import scrapy
from scrapy.http import JsonRequest

from crawlers.items import JobItem

COMPANY = "腾讯"
BASE_URL = "https://join.qq.com"

API_SEARCH         = f"{BASE_URL}/api/v1/position/searchPosition"
API_DETAIL         = f"{BASE_URL}/api/v1/jobDetails/getJobDetailsByPostId"
API_PROJECT_MAP    = f"{BASE_URL}/api/v1/position/getProjectMapping"
API_CITY           = f"{BASE_URL}/api/v1/position/getPositionWorkCities"
API_FAMILY         = f"{BASE_URL}/api/v1/position/getPositionFamily"

POSITION_FAMILY_NAME_MAP = {1: "综合", 2: "技术", 3: "产品", 4: "设计", 5: "市场", 6: "职能"}

_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE_URL}/post.html",
}


def _clean(value: Any) -> str | None:
    if not value:
        return None
    text = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return text or None


class TencentSpider(scrapy.Spider):
    name = "tencent"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
    }

    def __init__(self, start_page: int = 1, end_page: int = 9999,
                 page_size: int = 10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_page = int(start_page)
        self.end_page = int(end_page)
        self.page_size = int(page_size)

    def start_requests(self):
        yield scrapy.Request(
            url=API_PROJECT_MAP,
            headers=_HEADERS,
            callback=self.parse_project_mapping,
        )

    # ── Setup chain ───────────────────────────────────────────────────────────

    def parse_project_mapping(self, response):
        data = response.json().get("data") or {}
        ids: list[int] = []
        for entry in (data.get("list") or []):
            pid = entry.get("id")
            if isinstance(pid, int):
                ids.append(pid)
        if not ids:
            ids = [2, 104, 1, 14, 20, 5]
        yield scrapy.Request(
            url=API_CITY,
            headers=_HEADERS,
            callback=self.parse_city_map,
            meta={"project_mapping_ids": ids},
        )

    def parse_city_map(self, response):
        meta = response.meta
        data = response.json().get("data") or {}
        city_map: dict[str, str] = {}
        for entry in (data.get("list") or []):
            code = str(entry.get("code") or "")
            name = str(entry.get("name") or "")
            if code and name:
                city_map[code] = name
        meta["city_map"] = city_map
        yield scrapy.Request(
            url=API_FAMILY,
            headers=_HEADERS,
            callback=self.parse_position_family,
            meta=meta,
        )

    def parse_position_family(self, response):
        meta = response.meta
        data = response.json().get("data") or {}
        title_map: dict[int, str] = {}
        for entry in (data.get("list") or []):
            pid = entry.get("id")
            name = entry.get("name")
            if isinstance(pid, int) and name:
                title_map[pid] = str(name)
        meta["position_title_map"] = title_map
        meta["page"] = self.start_page
        meta["total_pages"] = 9999
        yield self._list_request(meta)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _list_request(self, meta: dict):
        payload = {
            "pageIndex": meta["page"],
            "pageSize": self.page_size,
            "projectMappingIds": meta["project_mapping_ids"],
            "recruitCategoryList": [],
            "locationCodeList": [],
            "keyword": "",
            "categoryList": [],
            "positionFamilyList": [],
        }
        return JsonRequest(
            url=API_SEARCH,
            data=payload,
            headers=_HEADERS,
            callback=self.parse_list,
            meta=dict(meta),
        )

    def parse_list(self, response):
        data = response.json().get("data") or {}
        meta = response.meta

        if meta["total_pages"] == 9999:
            total = int(data.get("count") or 0)
            import math
            meta["total_pages"] = max(1, math.ceil(total / self.page_size))
            effective_end = min(self.end_page, meta["total_pages"])
            meta["effective_end"] = effective_end
            self.logger.info(
                f"[tencent] total={total}, pages={meta['total_pages']}, "
                f"crawl={self.start_page}-{effective_end}"
            )

        items = data.get("positionList") or []
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            post_id = str(item.get("postId") or "").strip()
            if not post_id:
                continue
            item_meta = {
                "city_map": meta["city_map"],
                "position_title_map": meta["position_title_map"],
                "list_item": item,
                "source_page": meta["page"],
                "fetched_at": fetched_at,
            }
            yield JsonRequest(
                url=API_DETAIL,
                data={"postId": post_id},
                headers=_HEADERS,
                callback=self.parse_detail,
                meta=item_meta,
            )

        page = meta["page"]
        effective_end = meta.get("effective_end", self.end_page)
        if page < min(self.end_page, effective_end):
            meta["page"] = page + 1
            yield self._list_request(meta)

    def parse_detail(self, response):
        detail = response.json().get("data") or {}
        m = response.meta
        item = m["list_item"]
        city_map = m["city_map"]
        position_title_map = m["position_title_map"]

        post_id = str(item.get("postId") or detail.get("postId") or "").strip()
        title = _clean(detail.get("title") or item.get("positionTitle") or "")

        # Work cities
        detail_city_list = detail.get("workCityList")
        if isinstance(detail_city_list, list):
            work_cities = [str(c).strip() for c in detail_city_list if str(c).strip()]
        else:
            work_cities = []
        if not work_cities:
            raw = detail.get("workCity") or ""
            for code in re.split(r"[,，\s]+", str(raw)):
                city = city_map.get(code.strip())
                if city:
                    work_cities.append(city)

        # Category
        position_id = item.get("position")
        category = _clean(str(detail.get("tidName") or ""))
        if not category:
            category = position_title_map.get(position_id) if isinstance(position_id, int) else None
        if not category:
            family = item.get("positionFamily")
            if isinstance(family, int):
                category = POSITION_FAMILY_NAME_MAP.get(family)
            if not category:
                category = _clean(str(family or ""))

        yield JobItem(
            company=COMPANY,
            job_id=post_id,
            title=title,
            recruit_type=_clean(str(item.get("recruitLabelName") or detail.get("recruitLabelName") or "")),
            job_category=category,
            job_function=None,
            work_city=work_cities[0] if work_cities else None,
            work_cities=work_cities,
            team_intro=_clean(str(detail.get("introduction") or "")),
            responsibilities=_clean(str(detail.get("desc") or "")),
            requirements=_clean(str(detail.get("request") or "")),
            bonus_points=_clean(str(detail.get("internBonus") or detail.get("graduateBonus") or "")),
            tags=[],
            publish_time=None,
            detail_url=f"{BASE_URL}/post_detail.html?postid={post_id}" if post_id else None,
            fetched_at=m["fetched_at"],
            source_page=m["source_page"],
        )
