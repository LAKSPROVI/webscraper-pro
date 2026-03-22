"""
jusbrasil_spider.py — Spider dedicado para jusbrasil.com.br

Objetivo:
- Usar headers de navegador para reduzir bloqueios simples
- Extrair ao menos um item diagnostico por pagina (inclusive em 403/429)
- Permitir modo com Playwright quando render_js=true
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import scrapy

from scraper.items import ScrapedItem


class JusbrasilSpider(scrapy.Spider):
    name = "jusbrasil"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 1.0,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        },
    }

    def __init__(
        self,
        start_url: str | None = None,
        job_id: int | None = None,
        config: dict[str, Any] | None = None,
        render_js: bool = False,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.job_id = int(job_id) if job_id else None
        self.render_js = bool(render_js)
        self.config = config or {}
        self.start_urls = [start_url] if start_url else []

    def start_requests(self):
        for url in self.start_urls:
            if self.render_js:
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    meta={
                        "playwright": True,
                        "playwright_include_page": True,
                        "handle_httpstatus_all": True,
                    },
                    dont_filter=True,
                )
            else:
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    meta={"handle_httpstatus_all": True},
                    dont_filter=True,
                )

    async def parse(self, response: Any, **kwargs: Any):
        page = response.meta.get("playwright_page")
        html_text = response.text or ""
        title = (response.css("title::text").get() or "").strip()

        if page is not None:
            try:
                html_text = await page.content()
                title = (await page.title() or "").strip()
            finally:
                await page.close()

        clean_text = " ".join(
            response.css("body *:not(script):not(style)::text").getall()
        ).strip()

        status_code = int(getattr(response, "status", 0) or 0)
        if not clean_text:
            if status_code in (403, 429):
                clean_text = f"blocked_by_target status={status_code} url={response.url}"
            else:
                clean_text = f"empty_content status={status_code} url={response.url}"

        item = ScrapedItem()
        item["url"] = response.url
        item["domain"] = urlparse(response.url).netloc
        item["job_id"] = self.job_id
        item["spider_name"] = self.name
        item["title"] = title or "Jusbrasil"
        item["content"] = clean_text[:100000]
        item["raw_data"] = html_text[:50000]
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["metadata"] = {
            "status_code": status_code,
            "render_js": self.render_js,
            "source": "jusbrasil_spider",
        }

        yield item
