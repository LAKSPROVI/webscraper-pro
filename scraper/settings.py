"""
settings.py — Configurações completas do Scrapy para o WebScraper Jurídico

Centraliza todas as configurações do motor de scraping:
- Configurações gerais do Scrapy
- Middlewares customizados (anti-detecção, proxy, rate limit)
- Pipelines de processamento (dedup, cleaner, storage)
- Configurações do Playwright para renderização JS
- Auto-throttle para controle de velocidade
- Retry automático em erros HTTP
"""

import os

# ── Identificação do bot ──────────────────────────────────────────────────────
BOT_NAME = "webscraper_juridico"
SPIDER_MODULES = ["scraper.spiders"]
NEWSPIDER_MODULE = "scraper.spiders"

# ── Respeito ao robots.txt (configurável via variável de ambiente) ─────────────
# Setar ROBOTSTXT_OBEY=false no ambiente para ignorar em casos controlados
ROBOTSTXT_OBEY = os.getenv("ROBOTSTXT_OBEY", "true").lower() == "true"

# ── Concorrência e delays ─────────────────────────────────────────────────────
# Máximo de requisições simultâneas (todas as URLs)
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "16"))

# Máximo de requisições simultâneas por domínio
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.getenv("CONCURRENT_REQUESTS_PER_DOMAIN", "4"))

# Delay base entre requisições (0 = sem delay fixo, usa autothrottle)
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "0.5"))

# ── Auto-throttle: ajusta velocidade automaticamente baseado no servidor ───────
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0      # Delay inicial em segundos
AUTOTHROTTLE_MAX_DELAY = 10.0       # Delay máximo permitido em segundos
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0  # Número alvo de requests paralelos
AUTOTHROTTLE_DEBUG = os.getenv("AUTOTHROTTLE_DEBUG", "false").lower() == "true"

# ── Cookies ───────────────────────────────────────────────────────────────────
COOKIES_ENABLED = True
COOKIES_DEBUG = False  # Ativa log detalhado de cookies se True

# ── Headers padrão realistas ──────────────────────────────────────────────────
# Simula browser Chrome moderno para evitar detecção de bot
DEFAULT_REQUEST_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;"
        "q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ── Middlewares de download (baixar a página) ─────────────────────────────────
# Ordem de execução: menor número = executado primeiro no process_request
#                                   executado ÚLTIMO no process_response
DOWNLOADER_MIDDLEWARES = {
    # Middleware anti-detecção: adiciona headers realistas e rotaciona User-Agents
    "scraper.middlewares.antibot.AntiBotMiddleware": 100,

    # Middleware de proxy: rotaciona proxies e monitora saúde
    "scraper.middlewares.proxy.ProxyMiddleware": 200,

    # Middleware de rate limit: controla velocidade por domínio via Redis
    "scraper.middlewares.ratelimit.RateLimitMiddleware": 300,

    # Desabilita o middleware padrão de User-Agent do Scrapy
    # (substituído pelo AntiBotMiddleware)
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,

    # Habilita retry automático (configurado abaixo)
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,

    # Suporte ao Playwright para renderização JS
    "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler": 585,
}

# ── Pipelines de processamento ────────────────────────────────────────────────
# Ordem de execução: menor número = executado primeiro
ITEM_PIPELINES = {
    # Filtra itens duplicados via SHA-256 no Redis
    "scraper.pipelines.dedup.DuplicateFilterPipeline": 100,

    # Limpa e normaliza o conteúdo extraído
    "scraper.pipelines.cleaner.CleanerPipeline": 200,

    # Salva no PostgreSQL via SQLAlchemy
    "scraper.pipelines.storage.StoragePipeline": 300,
}

# ── Configurações do Playwright ───────────────────────────────────────────────
# Tipo de browser para renderização (chromium, firefox, webkit)
PLAYWRIGHT_BROWSER_TYPE = os.getenv("PLAYWRIGHT_BROWSER_TYPE", "chromium")

# Argumentos extras para o browser Playwright
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,           # Roda sem interface gráfica
    "args": [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",  # Oculta flag de automação
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
    ],
}

# Contexto padrão do Playwright com configurações anti-detecção
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = int(
    os.getenv("PLAYWRIGHT_TIMEOUT", "30000")  # 30 segundos
)

# Handlers de download: substitui handler padrão pelo Playwright
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# Necessário para o Playwright funcionar corretamente com Twisted
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# ── Retry automático ──────────────────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = int(os.getenv("RETRY_TIMES", "3"))  # Tentativas máximas
RETRY_HTTP_CODES = [500, 502, 503, 504, 429]  # Códigos que disparam retry
RETRY_PRIORITY_ADJUST = -1  # Reduz prioridade de retries

# ── Timeouts ──────────────────────────────────────────────────────────────────
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "30"))  # Segundos

# ── Configurações de log ──────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

# ── Desabilita funcionalidades não necessárias ────────────────────────────────
TELNETCONSOLE_ENABLED = False   # Desabilita console Telnet (segurança)
MEMDEBUG_ENABLED = False        # Debug de memória (apenas desenvolvimento)

# ── Feed exports desabilitados por padrão (usamos pipeline customizado) ───────
FEEDS = {}

# ── DNS cache ────────────────────────────────────────────────────────────────
DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000

# ── Compressão de resposta ────────────────────────────────────────────────────
COMPRESSION_ENABLED = True

# ── Configurações de extensões do Scrapy ─────────────────────────────────────
EXTENSIONS = {
    "scrapy.extensions.corestats.CoreStats": 500,
    "scrapy.extensions.telnet.TelnetConsole": None,  # Desabilitado
}

# ── Profundidade máxima de crawling (0 = sem limite) ─────────────────────────
DEPTH_LIMIT = int(os.getenv("DEPTH_LIMIT", "3"))
DEPTH_PRIORITY = 1  # Prioriza páginas mais rasas (breadth-first)

# ── Configurações de memória ──────────────────────────────────────────────────
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = int(os.getenv("MEMUSAGE_LIMIT_MB", "512"))
MEMUSAGE_WARNING_MB = int(os.getenv("MEMUSAGE_WARNING_MB", "400"))

# ── Redis (usado pelos middlewares e pipelines) ───────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Banco de dados PostgreSQL ─────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/webscraper"
)
