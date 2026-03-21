"""
generic_spider.py — Spider configurável via arquivo YAML

Spider de propósito geral que lê sua configuração de um arquivo YAML,
permitindo scraping de diferentes sites sem alterar código Python.

Suporta:
- Seletores CSS e XPath para extração de dados
- Seguimento automático de links do mesmo domínio
- Paginação via seletor de próxima página
- Transformações de dados (to_float, to_int, strip, clean_html)
- Renderização JS via Playwright (se render_js=true no config)
- Logging estruturado em português
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Generator
from urllib.parse import urljoin, urlparse

import scrapy
import yaml
from parsel import Selector

from scraper.items import ScrapedItem

logger = logging.getLogger(__name__)


# ── Funções auxiliares de transformação de dados ──────────────────────────────

def transform_to_float(value: str) -> float | None:
    """Converte string para float, removendo formatação brasileira (R$, pontos)."""
    if not value:
        return None
    # Remove símbolos de moeda, espaços e converte vírgula decimal
    clean = re.sub(r"[R$\s]", "", value).replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        logger.warning(f"Não foi possível converter '{value}' para float")
        return None


def transform_to_int(value: str) -> int | None:
    """Converte string para inteiro, removendo formatação."""
    if not value:
        return None
    clean = re.sub(r"[^\d-]", "", value)
    try:
        return int(clean)
    except ValueError:
        logger.warning(f"Não foi possível converter '{value}' para int")
        return None


def transform_strip(value: str) -> str:
    """Remove espaços e quebras de linha extras."""
    if not value:
        return ""
    return " ".join(value.split())


def transform_clean_html(value: str) -> str:
    """Remove tags HTML do conteúdo, mantendo apenas texto."""
    if not value:
        return ""
    # Remove tags HTML usando regex simples
    clean = re.sub(r"<[^>]+>", " ", value)
    return " ".join(clean.split())


# Mapeamento de transformações disponíveis
TRANSFORMATIONS = {
    "to_float": transform_to_float,
    "to_int": transform_to_int,
    "strip": transform_strip,
    "clean_html": transform_clean_html,
}


class GenericSpider(scrapy.Spider):
    """
    Spider genérico configurado via YAML.

    Parâmetros de inicialização (via scrapy crawl ou programático):
    - config_path: caminho para o arquivo YAML de configuração
    - job_id: ID do job de scraping (para rastreamento)

    Estrutura esperada do YAML:
    ```yaml
    name: meu_site
    start_urls:
      - https://exemplo.com
    follow_links: true
    crawl_depth: 2
    render_js: false
    next_page_selector: "a.proxima-pagina::attr(href)"
    selectors:
      title:
        type: css
        query: "h1.titulo::text"
        transform: strip
      price:
        type: css
        query: "span.preco::text"
        transform: to_float
      description:
        type: xpath
        query: "//div[@class='descricao']//text()"
        transform: clean_html
        join: " "  # Une múltiplos resultados com este separador
    ```
    """

    name = "generic"  # Nome padrão; sobrescrito pelo config YAML

    def __init__(
        self,
        config_path: str = None,
        job_id: int = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.job_id = int(job_id) if job_id else None
        self.config = {}
        self.allowed_domains = []
        self._visited_urls: set[str] = set()  # Rastreia URLs visitadas

        # Carrega configuração do YAML se fornecido
        if config_path:
            self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        """Carrega e valida o arquivo de configuração YAML."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            logger.info(f"Configuração carregada de: {config_path}")
        except FileNotFoundError:
            logger.error(f"Arquivo de configuração não encontrado: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Erro ao parsear YAML: {e}")
            raise

        # Sobrescreve nome do spider se definido no config
        if "name" in self.config:
            self.name = self.config["name"]

        # Extrai domínios permitidos das URLs de início
        start_urls = self.config.get("start_urls", [])
        if start_urls:
            self.start_urls = start_urls
            self.allowed_domains = list({
                urlparse(url).netloc for url in start_urls
            })

    @property
    def start_urls(self) -> list[str]:
        """Retorna as URLs de início do config ou do atributo da classe."""
        return self.config.get("start_urls", [])

    @start_urls.setter
    def start_urls(self, value: list[str]) -> None:
        """Define as URLs de início no config."""
        self.config["start_urls"] = value

    def start_requests(self) -> Generator:
        """Gera requisições iniciais, com ou sem Playwright."""
        render_js = self.config.get("render_js", False)

        for url in self.start_urls:
            if render_js:
                # Usa Playwright para renderizar JavaScript
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    meta={
                        "playwright": True,
                        "playwright_include_page": True,
                        "playwright_context_kwargs": {
                            "java_script_enabled": True,
                        },
                    },
                )
            else:
                yield scrapy.Request(url, callback=self.parse)

    def parse(self, response) -> Generator:
        """
        Parser principal: extrai itens e segue links se configurado.

        Para cada página:
        1. Extrai item com parse_item()
        2. Segue links do mesmo domínio se follow_links=true
        3. Segue próxima página se next_page_selector definido
        """
        # Registra URL como visitada
        self._visited_urls.add(response.url)
        logger.debug(f"Parseando: {response.url}")

        # Extrai item da página atual
        item = self.parse_item(response)
        if item:
            yield item

        # Segue links do mesmo domínio se configurado
        if self.config.get("follow_links", False):
            yield from self._follow_links(response)

        # Segue para próxima página se houver paginação
        next_page_selector = self.config.get("next_page_selector")
        if next_page_selector:
            yield from self._follow_pagination(response, next_page_selector)

    def parse_item(self, response) -> ScrapedItem | None:
        """
        Extrai dados da página usando os seletores do config YAML.

        Para cada campo definido em 'selectors':
        - Aplica o seletor CSS ou XPath
        - Aplica transformação se definida
        - Une múltiplos resultados com 'join' se definido
        """
        selectors_config = self.config.get("selectors", {})
        if not selectors_config:
            logger.debug(f"Nenhum seletor definido para {response.url}")
            return None

        # Extrai campos dinâmicos baseados no config
        extracted_data: dict[str, Any] = {}
        for field_name, field_config in selectors_config.items():
            value = self._extract_field(response, field_config)
            if value is not None:
                extracted_data[field_name] = value

        # Extrai título padrão se não definido nos seletores
        title = extracted_data.pop("title", None) or self._extract_default_title(response)

        # Extrai conteúdo principal se não definido
        content = extracted_data.pop("content", None) or self._extract_default_content(response)

        # Constrói o item Scrapy
        item = ScrapedItem()
        item["url"] = response.url
        item["domain"] = urlparse(response.url).netloc
        item["job_id"] = self.job_id
        item["spider_name"] = self.name
        item["title"] = title
        item["content"] = content
        item["raw_data"] = response.text[:50000]  # Limita raw_data a 50KB
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["metadata"] = extracted_data  # Campos extras vão para metadata

        logger.info(f"Item extraído: {response.url} | título: {str(title)[:50]}")
        return item

    def _extract_field(self, response, field_config: dict) -> Any:
        """
        Extrai um campo usando o seletor definido no config.

        Suporta:
        - type: css | xpath
        - query: expressão do seletor
        - transform: to_float | to_int | strip | clean_html
        - join: string para unir múltiplos resultados
        - default: valor padrão se não encontrado
        """
        selector_type = field_config.get("type", "css")
        query = field_config.get("query", "")
        transform = field_config.get("transform")
        join_str = field_config.get("join")
        default = field_config.get("default")

        if not query:
            return default

        # Aplica o seletor CSS ou XPath
        try:
            if selector_type == "css":
                results = response.css(query).getall()
            elif selector_type == "xpath":
                results = response.xpath(query).getall()
            else:
                logger.warning(f"Tipo de seletor desconhecido: {selector_type}")
                return default
        except Exception as e:
            logger.error(f"Erro ao aplicar seletor '{query}': {e}")
            return default

        if not results:
            return default

        # Une múltiplos resultados se join definido, caso contrário usa primeiro
        if join_str is not None:
            value = join_str.join(str(r) for r in results)
        else:
            value = results[0] if len(results) == 1 else results

        # Aplica transformação se definida
        if transform and isinstance(value, str):
            transform_func = TRANSFORMATIONS.get(transform)
            if transform_func:
                value = transform_func(value)
            else:
                logger.warning(f"Transformação desconhecida: {transform}")

        return value

    def _extract_default_title(self, response) -> str:
        """Extrai título padrão da página (tag <title> ou primeiro <h1>)."""
        title = response.css("title::text").get("")
        if not title:
            title = response.css("h1::text").get("")
        return transform_strip(title)

    def _extract_default_content(self, response) -> str:
        """Extrai conteúdo padrão removendo scripts e estilos."""
        # Remove scripts, estilos e navbars comuns
        body_text = " ".join(
            response.css(
                "body *:not(script):not(style):not(nav):not(header):not(footer)::text"
            ).getall()
        )
        return transform_strip(body_text)[:100000]  # Limita a 100KB

    def _follow_links(self, response) -> Generator:
        """Segue links do mesmo domínio que ainda não foram visitados."""
        current_depth = response.meta.get("depth", 0)
        max_depth = self.config.get("crawl_depth", 2)

        if current_depth >= max_depth:
            return

        # Extrai todos os links da página
        for href in response.css("a::attr(href)").getall():
            url = urljoin(response.url, href)
            parsed = urlparse(url)

            # Verifica se pertence ao mesmo domínio e não foi visitado
            if (
                parsed.netloc in self.allowed_domains
                and url not in self._visited_urls
                and parsed.scheme in ("http", "https")
            ):
                self._visited_urls.add(url)
                render_js = self.config.get("render_js", False)

                if render_js:
                    yield scrapy.Request(
                        url,
                        callback=self.parse,
                        meta={
                            "depth": current_depth + 1,
                            "playwright": True,
                        },
                    )
                else:
                    yield scrapy.Request(
                        url,
                        callback=self.parse,
                        meta={"depth": current_depth + 1},
                    )

    def _follow_pagination(self, response, selector: str) -> Generator:
        """Segue para a próxima página via seletor de paginação."""
        next_url = response.css(selector).get()
        if not next_url:
            # Tenta como XPath se CSS não encontrou
            next_url = response.xpath(selector).get()

        if next_url:
            full_url = urljoin(response.url, next_url)
            if full_url not in self._visited_urls:
                self._visited_urls.add(full_url)
                logger.debug(f"Seguindo paginação: {full_url}")
                yield scrapy.Request(full_url, callback=self.parse)
