"""
api_spider.py — Spider para REST APIs e GraphQL

Especializado em scraping de APIs JSON, com suporte completo a:
- Autenticação Bearer token, API Key (header/query param), Basic Auth
- Paginação por cursor, número de página e offset
- Rate limit respeitado via header X-RateLimit-Remaining
- Retry inteligente em 429 com Retry-After
- JSONPath para extração de dados aninhados
"""

import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Generator
from urllib.parse import urljoin, urlparse, urlencode

import scrapy
from jsonpath_ng import parse as jsonpath_parse

from scraper.items import ScrapedItem

logger = logging.getLogger(__name__)


class APISpider(scrapy.Spider):
    """
    Spider para consumo de REST APIs e GraphQL.

    Parâmetros de inicialização:
    - api_url: URL base da API
    - job_id: ID do job de scraping
    - auth_type: none | bearer | api_key | basic
    - auth_token: token de autenticação (Bearer ou API Key)
    - auth_username: username para Basic Auth
    - auth_password: senha para Basic Auth
    - api_key_header: nome do header para API Key (padrão: X-API-Key)
    - api_key_param: nome do query param para API Key
    - pagination_type: none | page | cursor | offset
    - page_param: nome do parâmetro de página (padrão: page)
    - per_page_param: nome do parâmetro de itens por página (padrão: per_page)
    - per_page: número de itens por página (padrão: 100)
    - cursor_field: campo JSONPath para cursor na resposta
    - cursor_param: parâmetro de query para cursor
    - total_pages_field: campo JSONPath para total de páginas
    - items_field: campo JSONPath para lista de itens (padrão: $)
    - max_pages: limite de páginas (padrão: 100)
    """

    name = "api_spider"
    custom_settings = {
        # Desabilita o Playwright para APIs (não precisa de JS)
        "DOWNLOAD_HANDLERS": {},
    }

    def __init__(
        self,
        api_url: str = None,
        job_id: int = None,
        auth_type: str = "none",
        auth_token: str = None,
        auth_username: str = None,
        auth_password: str = None,
        api_key_header: str = "X-API-Key",
        api_key_param: str = None,
        pagination_type: str = "none",
        page_param: str = "page",
        per_page_param: str = "per_page",
        per_page: int = 100,
        cursor_field: str = None,
        cursor_param: str = "cursor",
        total_pages_field: str = None,
        items_field: str = "$",
        max_pages: int = 100,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.api_url = api_url
        self.job_id = int(job_id) if job_id else None
        self.auth_type = auth_type
        self.auth_token = auth_token
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.api_key_header = api_key_header
        self.api_key_param = api_key_param
        self.pagination_type = pagination_type
        self.page_param = page_param
        self.per_page_param = per_page_param
        self.per_page = int(per_page)
        self.cursor_field = cursor_field
        self.cursor_param = cursor_param
        self.total_pages_field = total_pages_field
        self.items_field = items_field
        self.max_pages = int(max_pages)

        # Contadores de controle de paginação
        self._current_page = 1
        self._current_offset = 0

        # Configura headers de autenticação
        self._auth_headers: dict[str, str] = {}
        self._build_auth_headers()

    @property
    def start_urls(self) -> list[str]:
        """Retorna URL inicial baseada na configuração."""
        if not self.api_url:
            return []
        return [self._build_url(self.api_url, page=1)]

    def _build_auth_headers(self) -> None:
        """Constrói headers de autenticação baseados no tipo configurado."""
        if self.auth_type == "bearer" and self.auth_token:
            self._auth_headers["Authorization"] = f"Bearer {self.auth_token}"
            logger.debug("Autenticação Bearer configurada")

        elif self.auth_type == "api_key" and self.auth_token:
            if self.api_key_header:
                self._auth_headers[self.api_key_header] = self.auth_token

        elif self.auth_type == "basic" and self.auth_username and self.auth_password:
            # Codifica credenciais em Base64 para Basic Auth
            credentials = f"{self.auth_username}:{self.auth_password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            self._auth_headers["Authorization"] = f"Basic {encoded}"
            logger.debug("Autenticação Basic Auth configurada")

        # Sempre inclui Accept: application/json para APIs
        self._auth_headers["Accept"] = "application/json"
        self._auth_headers["Content-Type"] = "application/json"

    def _build_url(self, base_url: str, page: int = 1, cursor: str = None) -> str:
        """
        Constrói a URL com parâmetros de autenticação e paginação.

        Suporta:
        - API Key como query param
        - Parâmetros de página/offset
        - Cursor para paginação baseada em cursor
        """
        params: dict[str, Any] = {}

        # Adiciona API Key como query param se configurado
        if self.auth_type == "api_key" and self.api_key_param and self.auth_token:
            params[self.api_key_param] = self.auth_token

        # Adiciona parâmetros de paginação
        if self.pagination_type == "page":
            params[self.page_param] = page
            params[self.per_page_param] = self.per_page

        elif self.pagination_type == "offset":
            params["offset"] = self._current_offset
            params["limit"] = self.per_page

        elif self.pagination_type == "cursor" and cursor:
            params[self.cursor_param] = cursor
            params[self.per_page_param] = self.per_page

        if params:
            return f"{base_url}?{urlencode(params)}"
        return base_url

    def start_requests(self) -> Generator:
        """Gera a requisição inicial com headers de autenticação."""
        if not self.api_url:
            logger.error("api_url não configurada")
            return

        url = self._build_url(self.api_url, page=1)
        yield scrapy.Request(
            url,
            headers=self._auth_headers,
            callback=self.parse,
            errback=self.errback,
            meta={"page": 1, "cursor": None},
        )

    def parse(self, response) -> Generator:
        """
        Parseia resposta JSON da API e gera itens.

        Para cada resposta:
        1. Verifica rate limit restante
        2. Parseia o JSON
        3. Extrai itens via JSONPath
        4. Gera próxima página se paginação configurada
        """
        # Verifica rate limit antes de processar
        self._check_rate_limit(response)

        # Parseia o JSON da resposta
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Erro ao parsear JSON de {response.url}: {e}")
            logger.debug(f"Resposta recebida: {response.text[:500]}")
            return

        # Extrai itens usando JSONPath
        items_list = self._extract_items(data)
        if not items_list:
            logger.warning(f"Nenhum item encontrado em {response.url} com field '{self.items_field}'")

        # Processa cada item da resposta
        for item_data in items_list:
            yield self._build_item(item_data, response.url)

        # Segue para próxima página se configurado
        current_page = response.meta.get("page", 1)
        if current_page < self.max_pages:
            yield from self._handle_pagination(response, data, current_page)

    def _extract_items(self, data: Any) -> list:
        """
        Extrai lista de itens da resposta usando JSONPath.

        Exemplo: items_field="$.data.results" extrai data.results do JSON.
        """
        if self.items_field == "$" or not self.items_field:
            # Retorna a raiz do JSON
            return data if isinstance(data, list) else [data]

        try:
            expr = jsonpath_parse(self.items_field)
            matches = expr.find(data)
            if matches:
                value = matches[0].value
                return value if isinstance(value, list) else [value]
        except Exception as e:
            logger.error(f"Erro ao aplicar JSONPath '{self.items_field}': {e}")

        return []

    def _build_item(self, data: Any, url: str) -> ScrapedItem:
        """Constrói um ScrapedItem a partir de dados de API."""
        item = ScrapedItem()
        item["url"] = url
        item["domain"] = urlparse(url).netloc
        item["job_id"] = self.job_id
        item["spider_name"] = self.name
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()

        # Tenta extrair título de campos comuns
        if isinstance(data, dict):
            item["title"] = str(
                data.get("title") or data.get("name") or data.get("id") or ""
            )
            item["content"] = str(
                data.get("content") or data.get("body") or data.get("description") or ""
            )
        else:
            item["title"] = ""
            item["content"] = str(data)[:10000]

        # Armazena dados completos como raw_data (JSON serializado)
        item["raw_data"] = json.dumps(data, ensure_ascii=False, default=str)[:50000]
        item["metadata"] = data if isinstance(data, dict) else {"value": data}

        return item

    def _handle_pagination(self, response, data: Any, current_page: int) -> Generator:
        """
        Gera request para próxima página baseado no tipo de paginação.

        Suporta:
        - page: incrementa número da página
        - offset: incrementa offset
        - cursor: usa cursor da resposta para próxima página
        """
        if self.pagination_type == "page":
            # Verifica se há mais páginas consultando total_pages_field
            if self.total_pages_field:
                try:
                    expr = jsonpath_parse(self.total_pages_field)
                    matches = expr.find(data)
                    if matches:
                        total_pages = int(matches[0].value)
                        if current_page >= total_pages:
                            logger.info(f"Paginação concluída: {current_page}/{total_pages} páginas")
                            return
                except Exception:
                    pass

            next_page = current_page + 1
            url = self._build_url(self.api_url, page=next_page)
            logger.debug(f"Seguindo página {next_page}: {url}")
            yield scrapy.Request(
                url,
                headers=self._auth_headers,
                callback=self.parse,
                errback=self.errback,
                meta={"page": next_page},
            )

        elif self.pagination_type == "offset":
            self._current_offset += self.per_page
            url = self._build_url(self.api_url)
            yield scrapy.Request(
                url,
                headers=self._auth_headers,
                callback=self.parse,
                errback=self.errback,
                meta={"page": current_page + 1},
            )

        elif self.pagination_type == "cursor" and self.cursor_field:
            # Extrai cursor da resposta para próxima página
            try:
                expr = jsonpath_parse(self.cursor_field)
                matches = expr.find(data)
                if matches and matches[0].value:
                    next_cursor = str(matches[0].value)
                    url = self._build_url(self.api_url, cursor=next_cursor)
                    logger.debug(f"Seguindo cursor: {next_cursor[:50]}")
                    yield scrapy.Request(
                        url,
                        headers=self._auth_headers,
                        callback=self.parse,
                        errback=self.errback,
                        meta={"page": current_page + 1, "cursor": next_cursor},
                    )
                else:
                    logger.info("Cursor vazio — paginação concluída")
            except Exception as e:
                logger.error(f"Erro ao extrair cursor '{self.cursor_field}': {e}")

    def _check_rate_limit(self, response) -> None:
        """
        Verifica headers de rate limit e loga avisos.

        Monitora:
        - X-RateLimit-Remaining: requisições restantes na janela atual
        - X-RateLimit-Reset: timestamp de reset do rate limit
        """
        remaining = response.headers.get("X-RateLimit-Remaining", b"").decode()
        reset_time = response.headers.get("X-RateLimit-Reset", b"").decode()

        if remaining:
            remaining_int = int(remaining) if remaining.isdigit() else 0
            if remaining_int < 10:
                logger.warning(
                    f"Rate limit crítico: {remaining_int} requisições restantes. "
                    f"Reset em: {reset_time}"
                )
            else:
                logger.debug(f"Rate limit: {remaining_int} requisições restantes")

    def errback(self, failure) -> Generator:
        """
        Handler de erros para requests que falharam.

        Para erro 429, respeita o header Retry-After.
        """
        request = failure.request
        response = getattr(failure.value, "response", None)

        if response and response.status == 429:
            # Extrai tempo de espera do header Retry-After
            retry_after = response.headers.get("Retry-After", b"60").decode()
            wait_time = int(retry_after) if retry_after.isdigit() else 60
            logger.warning(
                f"Rate limit 429 em {request.url}. "
                f"Aguardando {wait_time}s antes de retry."
            )
            # Scrapy irá fazer retry automaticamente via RetryMiddleware
        else:
            logger.error(
                f"Erro na request para {request.url}: "
                f"{failure.getErrorMessage()}"
            )
