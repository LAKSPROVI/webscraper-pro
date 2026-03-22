"""
jusbrasil_spider.py — Spider dedicado para jusbrasil.com.br

Objetivo:
- Usar headers de navegador para reduzir bloqueios simples
- Extrair ao menos um item diagnostico por pagina (inclusive em 403/429)
- Permitir modo com Playwright quando render_js=true
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import urlparse

import scrapy

from scraper.items import ScrapedItem


class JusbrasilSpider(scrapy.Spider):
    name = "jusbrasil"

    default_request_headers: dict[str, str] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    }

    custom_settings = cast(Any, {
        "ROBOTSTXT_OBEY": False,
        "HTTPERROR_ALLOWED_CODES": [403, 429],
        "DOWNLOAD_DELAY": 1.0,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DEFAULT_REQUEST_HEADERS": default_request_headers,
    })

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
        self.cookies_json: list[dict[str, Any]] | None = None
        self.extra_headers: dict[str, str] = {}
        self.storage_state_path = self._resolve_str(
            "auth_storage_state_path",
            "JUSBRASIL_STORAGE_STATE_PATH",
        )
        self.cookie_header = self._resolve_str(
            "session_cookie_header",
            "JUSBRASIL_COOKIE_HEADER",
        )
        cookies_json = self._resolve_json(
            "cookies_json",
            "JUSBRASIL_COOKIES_JSON",
        )
        self.cookies_json = self._normalize_cookies(cookies_json)

        extra_headers = self._resolve_json(
            "extra_headers",
            "JUSBRASIL_EXTRA_HEADERS_JSON",
            expected_type=dict,
        )
        self.extra_headers = self._normalize_headers(extra_headers)

    def _warn(self, message: str, *args: Any) -> None:
        cast(Any, self).logger.warning(message, *args)

    def _normalize_cookies(self, value: Any) -> list[dict[str, Any]] | None:
        if not isinstance(value, list):
            return None
        normalized: list[dict[str, Any]] = []
        for entry in cast(list[dict[Any, Any]], value):
            normalized.append({str(key): entry[key] for key in entry})
        return normalized or None

    def _normalize_headers(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, header_value in cast(dict[Any, Any], value).items():
            normalized[str(key)] = str(header_value)
        return normalized

    def _resolve_str(self, config_key: str, env_name: str) -> str | None:
        value = self.config.get(config_key) or os.getenv(env_name)
        if not value:
            return None
        value = str(value).strip()
        return value or None

    def _resolve_json(
        self,
        config_key: str,
        env_name: str,
        *,
        expected_type: type[list[Any]] | type[dict[str, Any]] | None = list,
    ) -> Any:
        raw = self.config.get(config_key) or os.getenv(env_name)
        if not raw:
            return None
        if isinstance(raw, (list, dict)):
            return cast(Any, raw)
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError:
            self._warn("JSON inválido em %s", env_name)
            return None
        if expected_type is not None and not isinstance(parsed, expected_type):
            self._warn("Formato inesperado em %s", env_name)
            return None
        return cast(Any, parsed)

    def _build_cookie_header(self) -> str | None:
        if self.cookie_header:
            return self.cookie_header
        if self.cookies_json:
            pairs: list[str] = []
            for cookie in self.cookies_json:
                if cookie.get("name") and cookie.get("value"):
                    pairs.append(f"{cookie['name']}={cookie['value']}")
            if pairs:
                return "; ".join(pairs)
        return None

    def _build_headers(self) -> dict[str, str]:
        headers = dict(self.default_request_headers)
        headers.update(self.extra_headers)
        headers.setdefault("Referer", "https://www.jusbrasil.com.br/")
        cookie_header = self._build_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _build_playwright_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "playwright": True,
            "playwright_include_page": True,
            "handle_httpstatus_all": True,
            "playwright_context_kwargs": {
                "java_script_enabled": True,
                "locale": "pt-BR",
                "user_agent": self._build_headers().get("User-Agent"),
                "extra_http_headers": self._build_headers(),
            },
        }

        if self.storage_state_path:
            meta["playwright_context_kwargs"]["storage_state"] = self.storage_state_path
        elif self.cookies_json:
            meta["playwright_context_kwargs"]["storage_state"] = {
                "cookies": self.cookies_json,
                "origins": [],
            }

        return meta

    def start_requests(self):
        for url in self.start_urls:
            if self.render_js:
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    headers=self._build_headers(),
                    meta=self._build_playwright_meta(),
                    dont_filter=True,
                )
            else:
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    headers=self._build_headers(),
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
        parsed_url = urlparse(str(response.url))
        item["domain"] = str(parsed_url.netloc or "")
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
            "authenticated_session": bool(self.storage_state_path or self.cookie_header or self.cookies_json),
        }

        yield item
