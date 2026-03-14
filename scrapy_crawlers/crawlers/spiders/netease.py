"""NetEase interactive (网易互娱) campus jobs spider.

Flow: GET filters → POST list (paginated) → GET detail (per item) → JobItem
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any
from urllib.parse import urlencode

import scrapy
from scrapy.http import JsonRequest

from crawlers.items import JobItem

COMPANY  = "网易互娱"
BASE_URL = "https://campus.game.163.com"

API_LIST    = f"{BASE_URL}/api/recruitment/campus/position/list"
API_DETAIL  = f"{BASE_URL}/api/recruitment/campus/position/detail"
API_FILTERS = f"{BASE_URL}/api/recruitment/campus/position/filters"

# Default project ID for 网易互娱 campus recruitment
DEFAULT_PROJECT_ID = 30

_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE_URL}/position/{DEFAULT_PROJECT_ID}",
}


def _clean(value: Any) -> str | None:
    if not value:
        return None
    s = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return s or None


def _city_names(work_cities: Any) -> list[str]:
    if not isinstance(work_cities, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in work_cities:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("cityName"))
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _tag_names(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in tags:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("tagName"))
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _derive_category(info: dict, item: dict) -> str | None:
    category = _clean(info.get("positionTypeAbbreviation"))
    if category:
        return category
    position_types = info.get("positionTypes") or item.get("positionTypes") or []
    if isinstance(position_types, list) and position_types:
        names = [
            t.get("typeName") for t in position_types
            if isinstance(t, dict) and t.get("typeName")
        ]
        if names:
            return "-".join(_clean(n) for n in names if _clean(n))  # type: ignore[misc]
    return None


class NeteaseSpider(scrapy.Spider):
    name = "netease"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.4,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def __init__(self, start_page: int = 1, end_page: int = 9999,
                 page_size: int = 20, project_id: int = DEFAULT_PROJECT_ID,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_page = int(start_page)
        self.end_page   = int(end_page)
        self.page_size  = int(page_size)
        self.project_id = int(project_id)

    def start_requests(self):
        url = f"{API_FILTERS}?{urlencode({'projectId': self.project_id})}"
        yield scrapy.Request(url=url, headers=_HEADERS, callback=self.parse_filters)

    def parse_filters(self, response):
        # Filters endpoint just confirms project is accessible; pagination can start.
        meta = {"page": self.start_page, "total_pages": 9999}
        yield self._list_request(self.start_page, meta)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _list_request(self, page: int, meta: dict):
        payload = {
            "projectIds": [self.project_id],
            "positionTypeIds": [],
            "workplaceIds": [],
            "positionExternalTagIds": [],
            "attributeTypes": [],
            "pageNum": page,
        }
        return JsonRequest(
            url=API_LIST,
            data=payload,
            headers=_HEADERS,
            callback=self.parse_list,
            meta=dict(meta, page=page),
        )

    def parse_list(self, response):
        data = response.json().get("data") or {}
        meta = response.meta

        if meta["total_pages"] == 9999:
            total = int(data.get("totalCount") or data.get("total") or 0)
            meta["total_pages"] = max(1, math.ceil(total / self.page_size)) if total else self.start_page
            effective_end = min(self.end_page, meta["total_pages"])
            meta["effective_end"] = effective_end
            self.logger.info(
                f"[netease] total={total}, pages={meta['total_pages']}, "
                f"crawl={self.start_page}-{effective_end}"
            )

        items = data.get("positionList") or data.get("list") or []
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            position_id = item.get("positionId")
            if position_id is None:
                continue
            url = f"{API_DETAIL}?{urlencode({'positionId': position_id})}"
            yield scrapy.Request(
                url=url,
                headers=_HEADERS,
                callback=self.parse_detail,
                meta={"list_item": item, "source_page": meta["page"], "fetched_at": fetched_at},
            )

        page = meta["page"]
        effective_end = meta.get("effective_end", self.end_page)
        if page < min(self.end_page, effective_end):
            yield self._list_request(page + 1, meta)

    def parse_detail(self, response):
        m = response.meta
        raw = response.json().get("data") or {}
        detail = raw if isinstance(raw, dict) else {}
        item = m["list_item"]
        info = detail.get("info") if isinstance(detail.get("info"), dict) else {}

        position_id = item.get("positionId") or detail.get("positionId")
        work_cities = _city_names(info.get("workCities") or item.get("workCities"))
        tags = _tag_names(info.get("externalTags"))

        yield JobItem(
            company=COMPANY,
            job_id=str(position_id) if position_id is not None else None,
            title=_clean(info.get("externalPositionName") or item.get("externalPositionName")),
            recruit_type=_clean(info.get("projectName")),
            job_category=_derive_category(info, item),
            job_function=None,
            work_city=work_cities[0] if work_cities else None,
            work_cities=work_cities,
            team_intro=_clean(info.get("externalVolunteerDept")),
            responsibilities=_clean(info.get("positionDescription")),
            requirements=_clean(info.get("positionRequirement")),
            bonus_points=None,
            tags=tags,
            publish_time=_clean(detail.get("publishedAt") or item.get("publishedAt")),
            detail_url=f"{BASE_URL}/position-detail/{position_id}" if position_id is not None else None,
            fetched_at=m["fetched_at"],
            source_page=m["source_page"],
        )
