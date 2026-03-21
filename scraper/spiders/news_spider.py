"""
news_spider.py — Spider especializado em notícias e feeds RSS/Atom

Extrai artigos de jornais, blogs e portais de notícias, com suporte a:
- Feeds RSS e Atom para descoberta de artigos
- Extração inteligente de conteúdo via trafilatura
- Detecção de data de publicação em múltiplos formatos
- Extração de autor, categoria e tags
- Seguimento de links de artigos individuais a partir do feed
"""

import logging
import re
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import urljoin, urlparse

import feedparser
import scrapy
import trafilatura
from dateutil import parser as dateutil_parser

from scraper.items import ScrapedItem

logger = logging.getLogger(__name__)


# ── Seletores HTML comuns para metadados de artigos ───────────────────────────

# Seletores de data de publicação (por ordem de prioridade)
DATE_SELECTORS = [
    'meta[property="article:published_time"]::attr(content)',
    'meta[name="pubdate"]::attr(content)',
    'meta[name="date"]::attr(content)',
    'meta[itemprop="datePublished"]::attr(content)',
    'time[itemprop="datePublished"]::attr(datetime)',
    'time[pubdate]::attr(datetime)',
    'time::attr(datetime)',
    '.published-date::text',
    '.post-date::text',
    '.article-date::text',
    '.entry-date::text',
]

# Seletores de autor
AUTHOR_SELECTORS = [
    'meta[name="author"]::attr(content)',
    'meta[property="article:author"]::attr(content)',
    '[itemprop="author"] [itemprop="name"]::text',
    '[itemprop="author"]::text',
    '.author-name::text',
    '.byline::text',
    'a[rel="author"]::text',
    '.post-author::text',
]

# Seletores de categorias/tags
CATEGORY_SELECTORS = [
    'meta[property="article:section"]::attr(content)',
    'meta[name="section"]::attr(content)',
    'a[rel="category tag"]::text',
    '.post-category::text',
    '.article-category::text',
]

TAG_SELECTORS = [
    'meta[property="article:tag"]::attr(content)',
    'a[rel="tag"]::text',
    '.post-tags a::text',
    '.article-tags a::text',
    '.tags a::text',
]


class NewsSpider(scrapy.Spider):
    """
    Spider para extração de notícias e artigos.

    Parâmetros de inicialização:
    - rss_urls: URLs de feeds RSS/Atom (separadas por vírgula)
    - start_urls_list: URLs diretas de páginas de notícias
    - job_id: ID do job de scraping
    - follow_articles: se True, segue links de artigos do feed
    - max_articles: número máximo de artigos a coletar (0 = sem limite)
    """

    name = "news_spider"
    custom_settings = {
        # Headers adequados para sites de notícias
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    }

    def __init__(
        self,
        rss_urls: str = None,
        start_urls_list: str = None,
        job_id: int = None,
        follow_articles: bool = True,
        max_articles: int = 0,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.job_id = int(job_id) if job_id else None
        self.follow_articles = bool(follow_articles)
        self.max_articles = int(max_articles)
        self._articles_count = 0

        # Processa URLs de feeds RSS
        self._rss_urls = []
        if rss_urls:
            self._rss_urls = [u.strip() for u in rss_urls.split(",") if u.strip()]

        # Processa URLs diretas
        self._direct_urls = []
        if start_urls_list:
            self._direct_urls = [u.strip() for u in start_urls_list.split(",") if u.strip()]

    @property
    def start_urls(self) -> list[str]:
        """Combina feeds RSS com URLs diretas."""
        return self._rss_urls + self._direct_urls

    def start_requests(self) -> Generator:
        """Gera requisições diferenciando feeds RSS de URLs normais."""
        # Processa feeds RSS
        for url in self._rss_urls:
            yield scrapy.Request(
                url,
                callback=self.parse_rss,
                meta={"is_rss": True},
            )

        # Processa URLs diretas de artigos
        for url in self._direct_urls:
            yield scrapy.Request(
                url,
                callback=self.parse_article,
            )

    def parse_rss(self, response) -> Generator:
        """
        Parseia feed RSS/Atom usando feedparser.

        Extrai:
        - Lista de artigos do feed
        - Metadados básicos (título, data, autor, link)
        - Segue link de cada artigo para extração completa se configurado
        """
        logger.info(f"Parseando feed RSS: {response.url}")

        # Usa feedparser para parsear o XML do feed
        feed = feedparser.parse(response.text)

        if feed.bozo:
            # bozo=True indica erro no XML do feed
            logger.warning(f"Feed com formato irregular em {response.url}: {feed.bozo_exception}")

        entries = feed.get("entries", [])
        logger.info(f"Encontrados {len(entries)} artigos no feed {response.url}")

        for entry in entries:
            # Verifica limite de artigos
            if self.max_articles > 0 and self._articles_count >= self.max_articles:
                logger.info(f"Limite de {self.max_articles} artigos atingido")
                return

            # Extrai metadados básicos do feed
            article_url = entry.get("link", "")
            if not article_url:
                continue

            # Metadados pré-extraídos do feed (evita request adicional)
            rss_metadata = {
                "rss_title": entry.get("title", ""),
                "rss_author": entry.get("author", ""),
                "rss_published": self._parse_rss_date(entry),
                "rss_summary": entry.get("summary", "")[:2000],
                "rss_tags": [tag.term for tag in entry.get("tags", [])],
                "rss_categories": [cat.term for cat in entry.get("categories", [])],
            }

            if self.follow_articles:
                # Segue para artigo completo
                yield scrapy.Request(
                    article_url,
                    callback=self.parse_article,
                    meta={"rss_metadata": rss_metadata},
                )
            else:
                # Cria item apenas com dados do feed (sem visitar o artigo)
                yield self._build_item_from_feed(article_url, rss_metadata)

    def parse_article(self, response) -> Generator:
        """
        Parseia artigo individual extraindo conteúdo completo.

        Usa trafilatura para extração inteligente do texto principal,
        ignorando anúncios, navegação e conteúdo irrelevante.
        """
        # Verifica limite de artigos
        if self.max_articles > 0 and self._articles_count >= self.max_articles:
            return

        logger.debug(f"Extraindo artigo: {response.url}")

        # Metadados pré-carregados do feed RSS (se disponível)
        rss_metadata = response.meta.get("rss_metadata", {})

        # ── Extrai conteúdo principal com trafilatura ─────────────────────
        # trafilatura identifica e extrai o corpo principal do artigo
        extracted_text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )

        if not extracted_text:
            # Fallback: extrai texto de parágrafos se trafilatura falhar
            extracted_text = " ".join(
                response.css("p::text, article::text, .content p::text").getall()
            )
            logger.debug(f"Usando fallback para extração em: {response.url}")

        # ── Extrai título ────────────────────────────────────────────────
        title = (
            rss_metadata.get("rss_title")
            or response.css("h1::text").get("")
            or response.css("title::text").get("")
        ).strip()

        # ── Extrai data de publicação ────────────────────────────────────
        pub_date = rss_metadata.get("rss_published") or self._extract_date(response)

        # ── Extrai autor ─────────────────────────────────────────────────
        author = rss_metadata.get("rss_author") or self._extract_metadata(
            response, AUTHOR_SELECTORS
        )

        # ── Extrai categorias e tags ──────────────────────────────────────
        categories = rss_metadata.get("rss_categories") or response.css(
            ", ".join(CATEGORY_SELECTORS)
        ).getall()

        tags = rss_metadata.get("rss_tags") or response.css(
            ", ".join(TAG_SELECTORS)
        ).getall()

        # ── Constrói o item ───────────────────────────────────────────────
        item = ScrapedItem()
        item["url"] = response.url
        item["domain"] = urlparse(response.url).netloc
        item["job_id"] = self.job_id
        item["spider_name"] = self.name
        item["title"] = title
        item["content"] = extracted_text or ""
        item["raw_data"] = response.text[:50000]
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["metadata"] = {
            "author": author,
            "published_at": pub_date,
            "categories": categories,
            "tags": tags,
            "rss_summary": rss_metadata.get("rss_summary", ""),
        }

        self._articles_count += 1
        logger.info(
            f"Artigo extraído [{self._articles_count}]: {title[:60]} | "
            f"Autor: {author} | Data: {pub_date}"
        )

        yield item

    def _build_item_from_feed(self, url: str, rss_metadata: dict) -> ScrapedItem:
        """Constrói item apenas com dados do feed, sem visitar o artigo."""
        item = ScrapedItem()
        item["url"] = url
        item["domain"] = urlparse(url).netloc
        item["job_id"] = self.job_id
        item["spider_name"] = self.name
        item["title"] = rss_metadata.get("rss_title", "")
        item["content"] = rss_metadata.get("rss_summary", "")
        item["raw_data"] = ""
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["metadata"] = {
            "author": rss_metadata.get("rss_author", ""),
            "published_at": rss_metadata.get("rss_published", ""),
            "categories": rss_metadata.get("rss_categories", []),
            "tags": rss_metadata.get("rss_tags", []),
            "from_feed_only": True,
        }

        self._articles_count += 1
        return item

    def _extract_date(self, response) -> str:
        """
        Extrai data de publicação tentando múltiplos seletores.

        Normaliza para formato ISO 8601 para consistência.
        """
        for selector in DATE_SELECTORS:
            date_str = response.css(selector).get()
            if date_str:
                parsed = self._normalize_date(date_str.strip())
                if parsed:
                    return parsed

        # Tenta extrair data do texto da página via regex
        date_pattern = r'\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b'
        page_text = response.text[:5000]
        match = re.search(date_pattern, page_text)
        if match:
            try:
                day, month, year = match.groups()
                dt = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass

        return ""

    def _extract_metadata(self, response, selectors: list[str]) -> str:
        """Tenta extrair texto usando uma lista de seletores em ordem de prioridade."""
        for selector in selectors:
            value = response.css(selector).get()
            if value:
                return value.strip()
        return ""

    def _parse_rss_date(self, entry: dict) -> str:
        """Extrai e normaliza data de entrada RSS."""
        # feedparser converte datas para struct_time
        published_parsed = entry.get("published_parsed")
        if published_parsed:
            try:
                dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except (TypeError, ValueError):
                pass

        # Fallback: string da data
        date_str = entry.get("published", "") or entry.get("updated", "")
        return self._normalize_date(date_str) if date_str else ""

    def _normalize_date(self, date_str: str) -> str:
        """
        Normaliza string de data para ISO 8601.

        Usa dateutil para parsear formatos variados:
        - RFC 2822 (email/RSS): "Mon, 21 Mar 2024 12:00:00 +0000"
        - ISO 8601: "2024-03-21T12:00:00Z"
        - Data simples: "21/03/2024", "2024-03-21"
        """
        if not date_str:
            return ""
        try:
            dt = dateutil_parser.parse(date_str, fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, OverflowError, dateutil_parser.ParserError):
            logger.debug(f"Não foi possível parsear data: '{date_str}'")
            return ""
