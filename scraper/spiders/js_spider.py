"""
js_spider.py — Spider com Playwright para sites que requerem JavaScript

Especializado em sites que carregam conteúdo via JavaScript, SPA (Single
Page Applications) e sites com lazy loading.

Funcionalidades:
- Renderização completa de JavaScript via scrapy-playwright
- Scroll humanizado para revelar conteúdo com lazy loading
- Aguarda seletores específicos antes de extrair dados
- Captura screenshots em caso de erro para diagnóstico
- Interceptação de requisições de rede (XHR/fetch) para capturar dados de API
- Simulação de comportamento humano (delays, movimentos de mouse)
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from urllib.parse import urlparse

import scrapy
from playwright.async_api import Page, Route, Request as PlaywrightRequest

from scraper.items import ScrapedItem

logger = logging.getLogger(__name__)


class JSSpider(scrapy.Spider):
    """
    Spider para sites com JavaScript pesado.

    Parâmetros de inicialização:
    - start_urls_list: lista de URLs para raspar (separadas por vírgula)
    - job_id: ID do job de scraping
    - wait_for_selector: seletor CSS para aguardar antes de extrair
    - take_screenshots: se True, tira screenshot em erros
    - intercept_requests: se True, captura XHR/fetch responses
    - scroll_pages: número de scrolls para carregar lazy loading
    """

    name = "js_spider"
    custom_settings = {
        # Habilita Playwright para todas as requests deste spider
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        # Timeout maior para sites lentos
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 45000,
    }

    def __init__(
        self,
        start_urls_list: str = None,
        job_id: int = None,
        wait_for_selector: str = None,
        take_screenshots: bool = False,
        intercept_requests: bool = False,
        scroll_pages: int = 3,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.job_id = int(job_id) if job_id else None
        self.wait_for_selector = wait_for_selector
        self.take_screenshots = bool(take_screenshots)
        self.intercept_requests = bool(intercept_requests)
        self.scroll_pages = int(scroll_pages)

        # Converte lista de URLs de string para lista
        if start_urls_list:
            self.start_urls = [u.strip() for u in start_urls_list.split(",") if u.strip()]
        else:
            self.start_urls = []

        # Armazena dados interceptados das requests de rede
        self._intercepted_data: dict[str, list] = {}

    def start_requests(self) -> Generator:
        """Gera requisições com Playwright habilitado."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,  # Inclui objeto Page no response
                    "playwright_context_kwargs": {
                        "java_script_enabled": True,
                        "viewport": {"width": 1920, "height": 1080},
                        "user_agent": self._get_realistic_user_agent(),
                    },
                    "playwright_page_methods": [],  # Preenchido dinamicamente
                    "errback": self.errback,
                },
                errback=self.errback,
            )

    async def parse(self, response) -> AsyncGenerator:
        """
        Parser principal para p��ginas com JavaScript.

        Fluxo de execução:
        1. Obtém o objeto Page do Playwright
        2. Configura interceptação de rede se necessário
        3. Simula comportamento humano
        4. Realiza scrolls para lazy loading
        5. Aguarda seletor alvo se configurado
        6. Extrai dados da página renderizada
        """
        # Obtém o objeto Page do Playwright para interação direta
        page: Page = response.meta.get("playwright_page")
        if not page:
            logger.error(f"Objeto Page não disponível para: {response.url}")
            return

        try:
            # Configura interceptação de requisições de rede se habilitado
            if self.intercept_requests:
                await self._setup_network_interception(page, response.url)

            # Simula movimento de mouse humano para evitar detecção
            await self._simulate_human_behavior(page)

            # Realiza scrolls progressivos para carregar lazy loading
            await self._scroll_for_lazy_loading(page)

            # Aguarda seletor específico se configurado
            if self.wait_for_selector:
                await self._wait_for_content(page, self.wait_for_selector)

            # Obtém o HTML final após renderização completa
            content = await page.content()
            title = await page.title()

            # Extrai texto principal da página
            text_content = await page.evaluate("""
                () => {
                    // Remove scripts, estilos e elementos de navegação
                    const elements = document.querySelectorAll(
                        'script, style, nav, header, footer, .ad, .advertisement'
                    );
                    elements.forEach(el => el.remove());
                    return document.body ? document.body.innerText : '';
                }
            """)

            # Constrói o item com os dados coletados
            item = ScrapedItem()
            item["url"] = response.url
            item["domain"] = urlparse(response.url).netloc
            item["job_id"] = self.job_id
            item["spider_name"] = self.name
            item["title"] = title.strip() if title else ""
            item["content"] = " ".join(text_content.split()) if text_content else ""
            item["raw_data"] = content[:50000]  # Limita raw HTML a 50KB
            item["scraped_at"] = datetime.now(timezone.utc).isoformat()

            # Inclui dados interceptados se disponíveis
            intercepted = self._intercepted_data.get(response.url, [])
            item["metadata"] = {
                "intercepted_requests": intercepted,
                "rendered_js": True,
                "scroll_count": self.scroll_pages,
            }

            logger.info(f"JS Spider extraiu: {response.url} | {len(content)} bytes renderizados")
            yield item

        except Exception as e:
            logger.error(f"Erro ao parsear {response.url}: {e}")
            # Captura screenshot para diagnóstico se habilitado
            if self.take_screenshots and page:
                await self._take_error_screenshot(page, response.url)
        finally:
            # Sempre fecha a página para liberar memória
            await page.close()

    async def _setup_network_interception(self, page: Page, origin_url: str) -> None:
        """
        Configura interceptação de requisições XHR/fetch.

        Captura as respostas de API que a página faz durante o carregamento,
        permitindo extrair dados JSON diretamente da rede.
        """
        intercepted: list = []
        self._intercepted_data[origin_url] = intercepted

        async def handle_route(route: Route, request: PlaywrightRequest):
            """Intercepta e registra requisições de API."""
            # Continua a requisição normalmente
            await route.continue_()

            # Registra URLs de API (JSON/XHR)
            if "json" in request.headers.get("accept", "") or \
               request.resource_type in ("xhr", "fetch"):
                intercepted.append({
                    "url": request.url,
                    "method": request.method,
                    "type": request.resource_type,
                })

        # Intercepta todas as requisições da página
        await page.route("**/*", handle_route)
        logger.debug(f"Interceptação de rede configurada para: {origin_url}")

    async def _simulate_human_behavior(self, page: Page) -> None:
        """
        Simula comportamento humano para evitar detecção por bots.

        - Delay gaussiano antes de interagir
        - Movimentos aleatórios de mouse
        - Pausa natural antes do scroll
        """
        # Delay inicial simulando tempo de leitura
        await asyncio.sleep(random.gauss(1.5, 0.5))

        # Movimento de mouse aleatório (simula posicionamento humano)
        try:
            viewport = page.viewport_size
            if viewport:
                x = random.randint(100, viewport["width"] - 100)
                y = random.randint(100, viewport["height"] - 100)
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass  # Ignora erros de viewport

    async def _scroll_for_lazy_loading(self, page: Page) -> None:
        """
        Realiza scrolls progressivos para revelar conteúdo com lazy loading.

        Simula o comportamento humano de rolar a página lentamente,
        pausando para "ler" o conteúdo, para que elementos lazy load
        sejam acionados pelos IntersectionObservers.
        """
        for i in range(self.scroll_pages):
            # Scroll progressivo: divide a página em seções
            scroll_position = (i + 1) * (100 // self.scroll_pages)

            await page.evaluate(f"""
                window.scrollTo({{
                    top: document.documentElement.scrollHeight * {scroll_position / 100},
                    behavior: 'smooth'
                }});
            """)

            # Pausa humanizada entre scrolls (1.5s ± 0.5s)
            await asyncio.sleep(random.gauss(1.5, 0.5))

        # Volta ao início da página (comportamento humano comum)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        await asyncio.sleep(0.5)
        logger.debug(f"Realizados {self.scroll_pages} scrolls para lazy loading")

    async def _wait_for_content(self, page: Page, selector: str) -> None:
        """
        Aguarda um seletor específico aparecer na página.

        Útil para SPAs que carregam conteúdo assincronamente.
        Timeout de 15 segundos para evitar travamentos.
        """
        try:
            await page.wait_for_selector(selector, timeout=15000)
            logger.debug(f"Seletor '{selector}' encontrado na página")
        except Exception as e:
            logger.warning(f"Timeout aguardando seletor '{selector}': {e}")

    async def _take_error_screenshot(self, page: Page, url: str) -> None:
        """Captura screenshot em caso de erro para diagnóstico."""
        try:
            # Cria nome de arquivo seguro a partir da URL
            safe_name = urlparse(url).netloc.replace(".", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/error_{safe_name}_{timestamp}.png"

            await page.screenshot(path=filename, full_page=True)
            logger.info(f"Screenshot de erro salvo: {filename}")
        except Exception as e:
            logger.error(f"Falha ao capturar screenshot: {e}")

    async def errback(self, failure) -> None:
        """
        Handler de erros para requests que falharam.

        Registra o erro e, se configurado, tira screenshot do estado atual.
        """
        request = failure.request
        page: Page = request.meta.get("playwright_page")

        logger.error(
            f"Erro na request para {request.url}: "
            f"{failure.getErrorMessage()}"
        )

        if page and self.take_screenshots:
            await self._take_error_screenshot(page, request.url)
            await page.close()

    def _get_realistic_user_agent(self) -> str:
        """Retorna um User-Agent realista para o contexto Playwright."""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ]
        return random.choice(agents)
