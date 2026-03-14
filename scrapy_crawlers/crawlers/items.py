"""Scrapy Item for a single job posting (shared across all spiders)."""
from __future__ import annotations

import scrapy


class JobItem(scrapy.Item):
    company = scrapy.Field()
    job_id = scrapy.Field()
    title = scrapy.Field()
    recruit_type = scrapy.Field()
    job_category = scrapy.Field()
    job_function = scrapy.Field()
    work_city = scrapy.Field()
    work_cities = scrapy.Field()   # list[str]
    team_intro = scrapy.Field()
    responsibilities = scrapy.Field()
    requirements = scrapy.Field()
    bonus_points = scrapy.Field()
    tags = scrapy.Field()          # list[str]
    publish_time = scrapy.Field()
    detail_url = scrapy.Field()
    fetched_at = scrapy.Field()
    source_page = scrapy.Field()
