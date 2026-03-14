"""miHoYo (米哈游) campus jobs spider.

Flow: POST list (paginated) → POST detail (per item) → JobItem
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

import scrapy
from scrapy.http import JsonRequest

from crawlers.items import JobItem

COMPANY      = "米哈游"
BASE_SITE    = "https://jobs.mihoyo.com"
BASE_API     = "https://ats.openout.mihoyo.com/ats-portal"

API_LIST   = f"{BASE_API}/v1/job/list"
API_DETAIL = f"{BASE_API}/v1/job/info"

CHANNEL_DETAIL_IDS = [1]  # 校招渠道
HIRE_TYPE          = 1    # 校园招聘

_HEADERS = {
    "Content-Type": "application/json",
    "Origin": BASE_SITE,
    "Referer": f"{BASE_SITE}/",
}


def _clean(value: Any) -> str | None:
    if not value:
        return None
    s = "\n".join(line.rstrip() for line in str(value).strip().splitlines())
    return s or None


def _cities(address_list: Any) -> list[str]:
    if not isinstance(address_list, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in address_list:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("addressDetail"))
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _tags(tag_list: Any) -> list[str]:
    if not isinstance(tag_list, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in tag_list:
        name: str | None = None
        if isinstance(item, dict):
            name = _clean(item.get("tagName") or item.get("name") or item.get("label"))
        elif isinstance(item, str):
            name = _clean(item)
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


class MihoyoSpider(scrapy.Spider):
    name = "mihoyo"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def __init__(self, start_page: int = 1, end_page: int = 9999,
                 page_size: int = 20, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_page = int(start_page)
        self.end_page   = int(end_page)
        self.page_size  = int(page_size)

    def start_requests(self):
        meta = {"page": self.start_page, "total_pages": 9999}
        yield self._list_request(self.start_page, meta)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _list_payload(self, page: int) -> dict:
        return {
            "pageNo": page,
            "pageSize": self.page_size,
            "channelDetailIds": CHANNEL_DETAIL_IDS,
            "hireType": HIRE_TYPE,
        }

    def _list_request(self, page: int, meta: dict):
        return JsonRequest(
            url=API_LIST,
            data=self._list_payload(page),
            headers=_HEADERS,
            callback=self.parse_list,
            meta=dict(meta, page=page),
        )

    def parse_list(self, response):
        raw_data = response.json().get("data") or {}
        meta = response.meta

        if meta["total_pages"] == 9999:
            total = int(raw_data.get("total") or 0)
            meta["total_pages"] = max(1, math.ceil(total / self.page_size)) if total else self.start_page
            effective_end = min(self.end_page, meta["total_pages"])
            meta["effective_end"] = effective_end
            self.logger.info(
                f"[mihoyo] total={total}, pages={meta['total_pages']}, "
                f"crawl={self.start_page}-{effective_end}"
            )

        items = raw_data.get("records") or raw_data.get("list") or []
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "").strip()
            if not job_id:
                continue
            yield JsonRequest(
                url=API_DETAIL,
                data={"id": job_id, "channelDetailIds": CHANNEL_DETAIL_IDS, "hireType": HIRE_TYPE},
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
        raw = response.json().get("data")
        detail = raw if isinstance(raw, dict) else {}
        item = m["list_item"]

        job_id = str(detail.get("id") or item.get("id") or "").strip()
        cities = _cities(detail.get("addressDetailList") or item.get("addressDetailList"))
        tag_list = _tags(detail.get("tagList") or item.get("tagList"))

        yield JobItem(
            company=COMPANY,
            job_id=job_id or None,
            title=_clean(detail.get("title") or item.get("title")),
            recruit_type=_clean(detail.get("projectName") or item.get("projectName")),
            job_category=_clean(detail.get("competencyType") or item.get("competencyType")),
            job_function=_clean(detail.get("jobNature") or item.get("jobNature")),
            work_city=cities[0] if cities else None,
            work_cities=cities,
            team_intro=None,
            responsibilities=_clean(detail.get("description")),
            requirements=_clean(detail.get("jobRequire")),
            bonus_points=_clean(detail.get("addition")),
            tags=tag_list,
            publish_time=None,
            detail_url=f"{BASE_SITE}/#/campus/position/{job_id}" if job_id else None,
            fetched_at=m["fetched_at"],
            source_page=m["source_page"],
        )
