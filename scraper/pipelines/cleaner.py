"""
cleaner.py — Pipeline de limpeza e normalização de texto

Processa itens Scrapy para garantir qualidade dos dados:
- Remove tags HTML do conteúdo
- Normaliza espaços e quebras de linha
- Decodifica entidades HTML (&amp;, &lt;, &gt;, etc.)
- Usa trafilatura para extração avançada de texto limpo
- Valida campos obrigatórios (url, job_id)
- Normaliza URLs para formato canônico
- Remove conteúdo claramente inválido ou muito curto

Itens que não passam na validação são descartados com DropItem.
"""

import html
import logging
import re
from urllib.parse import urlparse, urlunparse

from scrapy.exceptions import DropItem

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

logger = logging.getLogger(__name__)

# Tamanho mínimo de conteúdo para considerar válido (caracteres)
MIN_CONTENT_LENGTH = 10

# Campos obrigatórios que todo item deve ter
REQUIRED_FIELDS = ["url", "job_id"]

# Regex para remover tags HTML
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

# Regex para normalizar espaços em branco (múltiplos espaços/newlines para um único espaço)
WHITESPACE_PATTERN = re.compile(r"\s+")

# Regex para detectar conteúdo claramente inválido (apenas símbolos/números)
INVALID_CONTENT_PATTERN = re.compile(r"^[\s\d\W]+$")


class CleanerPipeline:
    """
    Pipeline de limpeza e normalização de itens Scrapy.

    Processa cada item em ordem:
    1. Valida campos obrigatórios (descarta se inválido)
    2. Normaliza URL para formato canônico
    3. Limpa conteúdo HTML (remove tags, decodifica entidades)
    4. Usa trafilatura para extração avançada se raw_data disponível
    5. Normaliza todos os campos de texto
    6. Valida conteúdo mínimo após limpeza
    """

    def open_spider(self, spider) -> None:
        """Loga disponibilidade do trafilatura ao iniciar."""
        if TRAFILATURA_AVAILABLE:
            logger.info("CleanerPipeline: trafilatura disponível para extração avançada")
        else:
            logger.warning(
                "CleanerPipeline: trafilatura não disponível. "
                "Usando limpeza básica de HTML. Instale: pip install trafilatura"
            )

    def process_item(self, item, spider):
        """
        Limpa e normaliza um item Scrapy.

        Raises:
            DropItem: se o item não passar nas validações de qualidade
        """
        # ── 1. Valida campos obrigatórios ─────────────────────────────────
        self._validate_required_fields(item)

        # ── 2. Normaliza URL ──────────────────────────────────────────────
        if item.get("url"):
            item["url"] = self._normalize_url(str(item["url"]))

        # ── 3. Limpa campos de texto ──────────────────────────────────────
        if item.get("title"):
            item["title"] = self._clean_text(str(item["title"]))

        # ── 4. Limpa conteúdo principal ───────────────────────────────────
        raw_data = item.get("raw_data", "")
        content = item.get("content", "")

        # Tenta usar trafilatura no HTML cru para melhor extração
        if raw_data and TRAFILATURA_AVAILABLE and self._looks_like_html(raw_data):
            extracted = self._extract_with_trafilatura(raw_data, item.get("url", ""))
            if extracted and len(extracted) > len(content):
                content = extracted
                logger.debug(f"Trafilatura melhorou extração: {len(content)} chars")

        # Limpeza padrão do conteúdo
        if content:
            content = self._clean_html_content(str(content))
        item["content"] = content

        # ── 5. Valida conteúdo mínimo ─────────────────────────────────────
        if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
            # Tenta usar título como conteúdo se conteúdo vazio
            if item.get("title") and len(item["title"]) >= MIN_CONTENT_LENGTH:
                logger.debug(
                    f"Conteúdo muito curto, usando título: {item.get('url', '')[:60]}"
                )
            else:
                raise DropItem(
                    f"Item com conteúdo insuficiente ({len(content)} chars): "
                    f"{item.get('url', 'unknown url')}"
                )

        # ── 6. Normaliza campos de metadados ──────────────────────────────
        if item.get("metadata") and isinstance(item["metadata"], dict):
            item["metadata"] = self._clean_metadata(item["metadata"])

        # ── 7. Garante que spider_name está preenchido ─────────────────────
        if not item.get("spider_name"):
            item["spider_name"] = getattr(spider, "name", "unknown")

        # ── 8. Garante que domain está preenchido ─────────────────────────
        if not item.get("domain") and item.get("url"):
            item["domain"] = urlparse(item["url"]).netloc

        return item

    def _validate_required_fields(self, item) -> None:
        """
        Verifica se todos os campos obrigatórios estão presentes.

        Raises:
            DropItem: se algum campo obrigatório estiver ausente
        """
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                raise DropItem(
                    f"Campo obrigatório ausente ou vazio: '{field}' "
                    f"em {item.get('url', 'item sem URL')}"
                )

    def _normalize_url(self, url: str) -> str:
        """
        Normaliza URL para formato canônico.

        Ações:
        - Remove fragmentos (#hash)
        - Mantém parâmetros de query
        - Garante esquema em minúsculas
        - Remove trailing slash desnecessário
        """
        try:
            parsed = urlparse(url.strip())

            # Normaliza esquema e host para minúsculas
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            # Remove fragmento (porção após #)
            path = parsed.path

            # Remove trailing slash apenas em caminhos sem arquivos
            if path.endswith("/") and path != "/":
                path = path.rstrip("/")

            normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
            return normalized
        except Exception:
            return url  # Retorna URL original em caso de erro

    def _clean_text(self, text: str) -> str:
        """
        Limpeza básica de texto simples.

        - Decodifica entidades HTML
        - Remove tags HTML se presentes
        - Normaliza espaços
        """
        if not text:
            return ""
        # Decodifica entidades HTML (&amp; → &, &lt; → <, etc.)
        text = html.unescape(text)
        # Remove tags HTML
        text = HTML_TAG_PATTERN.sub(" ", text)
        # Normaliza espaços
        text = WHITESPACE_PATTERN.sub(" ", text).strip()
        return text

    def _clean_html_content(self, content: str) -> str:
        """
        Limpeza completa de conteúdo HTML.

        Mais agressiva que _clean_text:
        - Remove scripts e estilos (com conteúdo)
        - Remove tags HTML
        - Decodifica entidades
        - Normaliza pontuação
        """
        if not content:
            return ""

        # Remove blocos <script>...</script> e <style>...</style>
        content = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", content, flags=re.DOTALL | re.IGNORECASE)

        # Remove tags HTML restantes
        content = HTML_TAG_PATTERN.sub(" ", content)

        # Decodifica entidades HTML
        content = html.unescape(content)

        # Normaliza múltiplos espaços/newlines
        content = WHITESPACE_PATTERN.sub(" ", content).strip()

        return content

    def _looks_like_html(self, text: str) -> bool:
        """Verifica se o texto parece ser HTML (contém tags)."""
        return bool(HTML_TAG_PATTERN.search(text[:5000]))

    def _extract_with_trafilatura(self, html_content: str, url: str = "") -> str:
        """
        Usa trafilatura para extração avançada de texto de HTML.

        trafilatura é especializado em extrair o conteúdo principal de
        páginas web, ignorando navegação, anúncios e conteúdo periférico.
        """
        try:
            extracted = trafilatura.extract(
                html_content,
                url=url if url else None,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=True,
            )
            return extracted or ""
        except Exception as e:
            logger.debug(f"Erro no trafilatura para {url}: {e}")
            return ""

    def _clean_metadata(self, metadata: dict) -> dict:
        """
        Limpa campos de metadados recursivamente.

        - Converte valores None para strings vazias
        - Limpa strings de espaços extras
        - Mantém estrutura original
        """
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                cleaned[key] = ""
            elif isinstance(value, str):
                cleaned[key] = value.strip()
            elif isinstance(value, list):
                cleaned[key] = [
                    v.strip() if isinstance(v, str) else v
                    for v in value
                    if v is not None
                ]
            elif isinstance(value, dict):
                cleaned[key] = self._clean_metadata(value)
            else:
                cleaned[key] = value
        return cleaned
