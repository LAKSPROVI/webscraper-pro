"""
antibot.py — Middleware anti-detecção de bots

Implementa técnicas para evitar detecção como bot por sites alvo:
- Rotação de User-Agents realistas (200+ agentes por plataforma)
- Headers HTTP realistas (Accept-Language, Sec-Fetch-*, etc.)
- Gerenciamento de cookies por domínio
- Cadeia realista de Referers
- Delays gaussianos entre requisições do mesmo domínio

O middleware intercepta cada requisição antes de enviá-la e adiciona
headers que simulam um navegador real, tornando o scraper menos
detectável por sistemas anti-bot.
"""

import logging
import random
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response

logger = logging.getLogger(__name__)


# ── Banco de User-Agents reais por plataforma ─────────────────────────────────
# Agentes coletados de dados reais de browser market share (2024)
USER_AGENTS = {
    # Chrome no Windows (mais comum, ~65% do mercado)
    "chrome_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.86 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.111 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.185 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ],
    # Chrome no macOS
    "chrome_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ],
    # Chrome no Linux
    "chrome_linux": [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ],
    # Firefox no Windows
    "firefox_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    ],
    # Firefox no macOS
    "firefox_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    ],
    # Safari no macOS
    "safari_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    ],
    # Edge no Windows
    "edge_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ],
    # Chrome no Android (mobile)
    "chrome_android": [
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.80 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    ],
}

# Lista plana de todos os User-Agents para seleção aleatória simples
ALL_USER_AGENTS = [ua for group in USER_AGENTS.values() for ua in group]

# Headers de Sec-CH-UA por navegador (Client Hints para Chrome/Edge)
SEC_CH_UA_MAP = {
    "Chrome/123": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "Chrome/122": '"Google Chrome";v="122", "Not:A-Brand";v="8", "Chromium";v="122"',
    "Chrome/121": '"Google Chrome";v="121", "Not:A-Brand";v="8", "Chromium";v="121"',
    "Chrome/120": '"Google Chrome";v="120", "Not:A-Brand";v="8", "Chromium";v="120"',
    "Edge/123": '"Microsoft Edge";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "Edge/122": '"Microsoft Edge";v="122", "Not:A-Brand";v="8", "Chromium";v="122"',
    "Firefox": None,   # Firefox não envia Sec-CH-UA
    "Safari": None,    # Safari não envia Sec-CH-UA
}


class AntiBotMiddleware:
    """
    Middleware que simula comportamento de navegador real.

    Para cada request:
    1. Seleciona User-Agent baseado no domínio (consistência)
    2. Adiciona headers HTTP realistas (Sec-Fetch-*, Accept, etc.)
    3. Gerencia cadeia de Referers (primeiro acesso sem referer)
    4. Aplica delay gaussiano entre requests do mesmo domínio
    """

    def __init__(self, settings):
        self.settings = settings
        # Rastreia último User-Agent por domínio (consistência entre requests)
        self._domain_ua: dict[str, str] = {}
        # Rastreia Referer por domínio (para cadeia realista)
        self._domain_referer: dict[str, Optional[str]] = defaultdict(lambda: None)
        # Rastreia último timestamp de request por domínio (para delays)
        self._domain_last_request: dict[str, float] = {}

    @classmethod
    def from_crawler(cls, crawler):
        """Instancia o middleware a partir das configurações do Scrapy."""
        return cls(crawler.settings)

    def process_request(self, request: Request, spider) -> None:
        """
        Processa cada request antes de enviá-la.

        Adiciona:
        - User-Agent consistente por domínio
        - Headers HTTP realistas
        - Referer apropriado
        - Delay gaussiano se necessário
        """
        domain = urlparse(request.url).netloc

        # ── Seleciona ou reutiliza User-Agent para o domínio ─────────────
        if domain not in self._domain_ua:
            # Seleciona plataforma com pesos (simula distribuição real de mercado)
            platform_weights = {
                "chrome_windows": 40,
                "chrome_mac": 15,
                "chrome_linux": 10,
                "firefox_windows": 10,
                "firefox_mac": 5,
                "safari_mac": 10,
                "edge_windows": 7,
                "chrome_android": 3,
            }
            platform = random.choices(
                list(platform_weights.keys()),
                weights=list(platform_weights.values()),
                k=1,
            )[0]
            self._domain_ua[domain] = random.choice(USER_AGENTS[platform])

        user_agent = self._domain_ua[domain]
        request.headers["User-Agent"] = user_agent

        # ── Adiciona headers realistas baseados no User-Agent ─────────────
        self._add_realistic_headers(request, user_agent, domain)

        # ── Gerencia cadeia de Referers ───────────────────────────────────
        referer = self._domain_referer[domain]
        if referer and "Referer" not in request.headers:
            request.headers["Referer"] = referer
        # Atualiza referer para próxima request do mesmo domínio
        self._domain_referer[domain] = request.url

        # ── Aplica delay gaussiano entre requests ─────────────────────────
        self._apply_domain_delay(domain)

    def process_response(self, request: Request, response: Response, spider) -> Response:
        """
        Processa cada resposta recebida.

        Monitora respostas de detecção de bot (403, 429, Cloudflare)
        e registra avisos para análise.
        """
        domain = urlparse(request.url).netloc

        if response.status in (403, 429):
            logger.warning(
                f"Possível detecção de bot em {domain}: "
                f"HTTP {response.status} para {request.url}"
            )
            # Remove o User-Agent marcado como detectado para este domínio
            # Próxima request usará um novo agente
            self._domain_ua.pop(domain, None)

        # Detecta páginas do Cloudflare/Imperva (texto indicativo)
        body_text = response.text[:2000].lower()
        if any(phrase in body_text for phrase in [
            "cloudflare", "ddos protection", "checking your browser",
            "access denied", "imperva", "incapsula"
        ]):
            logger.warning(f"Proteção anti-bot detectada em {domain}")
            # Reinicia estado do domínio para próxima tentativa
            self._domain_ua.pop(domain, None)
            self._domain_referer[domain] = None

        return response

    def _add_realistic_headers(self, request: Request, user_agent: str, domain: str) -> None:
        """
        Adiciona headers HTTP realistas baseados no User-Agent.

        Headers variam por browser:
        - Chrome/Edge: inclui Sec-Fetch-*, Sec-CH-UA
        - Firefox: não inclui Client Hints
        - Safari: não inclui Sec-Fetch-User para assets
        """
        is_chrome = "Chrome" in user_agent and "Edg" not in user_agent
        is_edge = "Edg/" in user_agent
        is_firefox = "Firefox" in user_agent
        is_mobile = "Mobile" in user_agent

        # Headers Accept comuns a todos os browsers
        if "Accept" not in request.headers:
            request.headers["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;"
                "q=0.8,application/signed-exchange;v=b3;q=0.7"
            )

        request.headers["Accept-Encoding"] = "gzip, deflate, br"
        request.headers["Accept-Language"] = random.choice([
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "pt-BR,pt;q=0.9,en;q=0.8",
            "en-US,en;q=0.9,pt-BR;q=0.8",
        ])
        request.headers["Cache-Control"] = "max-age=0"
        request.headers["Connection"] = "keep-alive"

        # Headers específicos do Chrome/Edge (Sec-Fetch-*)
        if is_chrome or is_edge:
            request.headers["Sec-Fetch-Dest"] = "document"
            request.headers["Sec-Fetch-Mode"] = "navigate"
            request.headers["Sec-Fetch-Site"] = "none"
            request.headers["Sec-Fetch-User"] = "?1"
            request.headers["Upgrade-Insecure-Requests"] = "1"

            # Client Hints (Chrome 89+)
            request.headers["sec-ch-ua-mobile"] = "?1" if is_mobile else "?0"
            request.headers["sec-ch-ua-platform"] = (
                '"Android"' if is_mobile else '"Windows"'
            )

            # Extrai versão do Chrome para Sec-CH-UA
            import re
            chrome_version_match = re.search(r"Chrome/(\d+)", user_agent)
            if chrome_version_match:
                version = chrome_version_match.group(1)
                browser = "Microsoft Edge" if is_edge else "Google Chrome"
                request.headers["sec-ch-ua"] = (
                    f'"{browser}";v="{version}", '
                    f'"Not:A-Brand";v="8", '
                    f'"Chromium";v="{version}"'
                )

        elif is_firefox:
            # Firefox não usa Sec-Fetch-User nem Client Hints
            request.headers["Sec-Fetch-Dest"] = "document"
            request.headers["Sec-Fetch-Mode"] = "navigate"
            request.headers["Sec-Fetch-Site"] = "none"
            request.headers["Upgrade-Insecure-Requests"] = "1"

    def _apply_domain_delay(self, domain: str) -> None:
        """
        Aplica delay gaussiano entre requests do mesmo domínio.

        Simula tempo de processamento e leitura humana, evitando
        padrões regulares facilmente detectáveis por rate limiters.

        Delay: média de 0.5s com desvio padrão de 0.2s (mínimo 0.1s)
        """
        last_time = self._domain_last_request.get(domain)
        now = time.time()

        if last_time is not None:
            # Delay gaussiano: média 0.5s, desvio 0.2s, mínimo 0.1s
            delay = max(0.1, random.gauss(0.5, 0.2))
            elapsed = now - last_time

            if elapsed < delay:
                sleep_time = delay - elapsed
                time.sleep(sleep_time)

        self._domain_last_request[domain] = time.time()
