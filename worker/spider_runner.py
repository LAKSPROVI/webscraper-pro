"""
spider_runner.py — Executa spiders Scrapy de forma controlada

Responsável por:
- Executar spiders Scrapy via CrawlerProcess programaticamente
- Capturar estatísticas de execução (itens coletados, erros, motivo de finalização)
- Publicar progresso periódico no Redis (a cada 10 items coletados)
- Executar em thread separada para não bloquear o event loop do Celery
- Aplicar timeout máximo de 10 minutos por job

Suporte a spiders com e sem renderização JavaScript (scrapy-playwright).
"""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Any

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

REDIS_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# Timeout máximo por execução de spider (segundos)
SPIDER_DEFAULT_TIMEOUT: int = int(os.getenv("SPIDER_TIMEOUT", "600"))  # 10 minutos

# Publicar progresso no Redis a cada N itens coletados
PROGRESS_PUBLISH_INTERVAL: int = 10


class SpiderRunner:
    """
    Executa spiders Scrapy de forma controlada e isolada por job.

    Cada chamada a run_spider() executa em uma thread separada com timeout,
    garantindo que o worker Celery não fique bloqueado indefinidamente.
    """

    def __init__(self, redis_url: str = REDIS_URL) -> None:
        """
        Inicializa o SpiderRunner.

        Args:
            redis_url: URL de conexão Redis para publicar progresso
        """
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None

    @property
    def redis_client(self) -> redis.Redis:
        """Cliente Redis com conexão lazy."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._redis

    def run_spider(
        self,
        job_id: int,
        url: str,
        spider_type: str,
        config: dict[str, Any],
        render_js: bool = False,
        use_proxy: bool | None = None,
        crawl_depth: int = 1,
        timeout: int = SPIDER_DEFAULT_TIMEOUT,
    ) -> int:
        """
        Executa um spider Scrapy e aguarda o resultado com timeout.

        Executa o spider em uma thread separada para:
        1. Não bloquear o event loop do Celery
        2. Permitir timeout forçado via ThreadPoolExecutor

        Args:
            job_id:      ID do job associado a esta execução
            url:         URL alvo do scraping
            spider_type: Tipo do spider ('generic', 'js', 'rss', 'api', 'sitemap')
            config:      Configurações extras para o spider (headers, seletores, etc.)
            render_js:   Se True, usa scrapy-playwright para renderizar JavaScript
            crawl_depth: Profundidade máxima de crawling
            timeout:     Timeout máximo em segundos (padrão: 10 min)

        Returns:
            Quantidade de itens coletados com sucesso.

        Raises:
            RuntimeError:  Se o spider falhar com erro fatal
            TimeoutError:  Se o spider ultrapassar o timeout máximo
        """
        logger.info(
            "Iniciando spider: job_id=%d, url=%s, spider_type=%s, render_js=%s, depth=%d",
            job_id,
            url,
            spider_type,
            render_js,
            crawl_depth,
        )

        # Resultado compartilhado da execução do spider
        resultado: dict[str, Any] = {
            "items_count": 0,
            "error": None,
            "finish_reason": "unknown",
            "stats": {},
        }

        # Executa no thread principal do processo worker. O Scrapy/Twisted
        # utiliza sinais de sistema e falha quando executado em thread secundária.
        self._executar_spider_em_thread(
            job_id=job_id,
            url=url,
            spider_type=spider_type,
            config=config,
            render_js=render_js,
            use_proxy=use_proxy,
            crawl_depth=crawl_depth,
            resultado=resultado,
        )

        # Verifica se houve erro durante a execução
        if resultado["error"] is not None:
            raise RuntimeError(str(resultado["error"]))

        items_count = resultado["items_count"]

        logger.info(
            "Spider finalizado: job_id=%d, items=%d, finish_reason=%s",
            job_id,
            items_count,
            resultado.get("finish_reason", "unknown"),
        )

        return items_count

    def _executar_spider_em_thread(
        self,
        job_id: int,
        url: str,
        spider_type: str,
        config: dict[str, Any],
        render_js: bool,
        use_proxy: bool | None,
        crawl_depth: int,
        resultado: dict[str, Any],
    ) -> None:
        """
        Executa o spider dentro de uma thread separada.

        Usa CrawlerProcess do Scrapy para criar e executar o crawler.
        Captura estatísticas ao final da execução.

        Args:
            job_id:      ID do job
            url:         URL alvo
            spider_type: Tipo do spider a instanciar
            config:      Configurações extras
            render_js:   Se deve usar Playwright
            crawl_depth: Profundidade de crawling
            resultado:   Dict compartilhado para retornar resultado à thread principal
        """
        try:
            # Import dentro da thread para evitar problemas com Twisted reactor
            from scrapy.crawler import CrawlerProcess  # noqa: PLC0415
            from scrapy.utils.project import get_project_settings  # noqa: PLC0415
            from scrapy.utils.log import configure_logging  # noqa: PLC0415

            # Configurações do Scrapy
            settings = get_project_settings()

            # Aplica configurações base para o job
            settings_override = {
                "JOBDIR": f"/tmp/scrapy_jobs/job_{job_id}",
                "DEPTH_LIMIT": crawl_depth,
                "DOWNLOAD_TIMEOUT": 30,
                "RETRY_TIMES": 3,
                "ROBOTSTXT_OBEY": config.get("obey_robots", False),
                "CONCURRENT_REQUESTS": config.get("concurrent_requests", 8),
                "DOWNLOAD_DELAY": config.get("download_delay", 0.5),
                "LOG_LEVEL": "WARNING",  # Reduz verbosidade no Celery
            }

            # Ativa suporte Playwright se necessário
            if render_js:
                settings_override.update({
                    "DOWNLOAD_HANDLERS": {
                        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                    },
                    "PLAYWRIGHT_BROWSER_TYPE": "chromium",
                    "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
                    "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30000,
                })

            settings.setdict(settings_override, priority="cmdline")

            # Seleciona a classe do spider conforme o tipo
            spider_cls = self._resolver_spider_class(spider_type)

            if spider_cls is None:
                raise ValueError(f"Tipo de spider desconhecido: {spider_type!r}")

            # Publisher de progresso via closure
            items_coletados = {"count": 0}
            publisher_redis = self.redis_client

            def publicar_progresso(count: int) -> None:
                """Publica progresso no Redis a cada N itens."""
                try:
                    canal = f"job_events:{job_id}"
                    import json  # noqa: PLC0415
                    payload = json.dumps({
                        "job_id": job_id,
                        "event": "job_progress",
                        "items_collected": count,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    })
                    publisher_redis.publish(canal, payload)
                    publisher_redis.publish("job_events:all", payload)
                except Exception as pub_err:
                    logger.debug("Falha ao publicar progresso: %s", pub_err)

            # Cria o processo Celery com cleanup automático
            processo = CrawlerProcess(settings, install_root_handler=False)

            # Configura callback para capturar estatísticas ao final
            def capturar_stats(spider, reason) -> None:  # noqa: ANN001
                resultado["finish_reason"] = reason
                stats = spider.crawler.stats.get_stats()
                resultado["stats"] = stats
                resultado["items_count"] = stats.get("item_scraped_count", 0)
                logger.debug(
                    "Stats do spider: %s — items=%d, reason=%s",
                    spider.name,
                    resultado["items_count"],
                    reason,
                )

            # Configurações passadas para o spider
            spider_kwargs = {
                "job_id": job_id,
                "start_url": url,
                "config": config,
                "render_js": render_js,
                "progress_callback": publicar_progresso,
                "progress_interval": PROGRESS_PUBLISH_INTERVAL,
            }

            if use_proxy is not None:
                spider_kwargs["use_proxy"] = bool(use_proxy)

            # Injeta configurações específicas do tipo
            if spider_type == "generic":
                spider_kwargs.update({
                    "allowed_domains": config.get("allowed_domains", []),
                    "css_selectors": config.get("css_selectors", {}),
                    "xpath_selectors": config.get("xpath_selectors", {}),
                })

            crawler = processo.create_crawler(spider_cls)
            crawler.signals.connect(capturar_stats, signal="spider_closed")

            processo.crawl(crawler, **spider_kwargs)
            processo.start()  # Bloqueia até o spider terminar

        except ImportError as exc:
            logger.error("Scrapy não disponível: %s", exc)
            resultado["error"] = f"Scrapy não instalado ou inacessível: {exc}"

        except Exception as exc:
            logger.exception("Erro ao executar spider job_id=%d: %s", job_id, exc)
            resultado["error"] = str(exc)

    def _resolver_spider_class(self, spider_type: str) -> type | None:
        """
        Retorna a classe do spider correspondente ao tipo solicitado.

        Args:
            spider_type: Identificador do tipo de spider

        Returns:
            Classe do spider ou None se o tipo não for reconhecido.
        """
        mapeamento: dict[str, str] = {
            "generic":  "scraper.spiders.generic_spider.GenericSpider",
            "jusbrasil": "scraper.spiders.jusbrasil_spider.JusbrasilSpider",
            "js":       "scraper.spiders.js_spider.JSSpider",
            "rss":      "scraper.spiders.rss_spider.RSSSpider",
            "api":      "scraper.spiders.api_spider.APISpider",
            "sitemap":  "scraper.spiders.sitemap_spider.SitemapSpider",
        }

        caminho_classe = mapeamento.get(spider_type.lower())

        if caminho_classe is None:
            logger.warning("Spider type desconhecido: %s", spider_type)
            return None

        try:
            modulo_path, nome_classe = caminho_classe.rsplit(".", 1)
            import importlib  # noqa: PLC0415
            modulo = importlib.import_module(modulo_path)
            return getattr(modulo, nome_classe)

        except (ImportError, AttributeError) as exc:
            logger.error(
                "Falha ao importar spider '%s' de '%s': %s",
                spider_type,
                caminho_classe,
                exc,
            )
            return None

    def close(self) -> None:
        """Fecha conexões de forma ordenada."""
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None
