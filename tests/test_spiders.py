"""
tests/test_spiders.py — Testes unitários dos spiders e pipelines
WebScraper Pro

Testa:
- GenericSpider parseia configuração YAML corretamente
- CleanerPipeline remove HTML e normaliza texto
- DuplicateFilterPipeline detecta duplicatas por hash
- ProxyUpdater valida formato de proxy (host:porta)
- AntiBotMiddleware adiciona headers HTTP corretos
"""

import hashlib
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ==============================================================================
# FIXTURES E HELPERS
# ==============================================================================

CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def criar_config_yaml(conteudo: Dict[str, Any]) -> str:
    """Cria um arquivo YAML temporário com o conteúdo fornecido."""
    return yaml.dump(conteudo, allow_unicode=True, default_flow_style=False)


# Config YAML mínima válida para spider genérico
CONFIG_GENERIC_MINIMA = {
    "spider_type": "generic",
    "name": "teste-spider",
    "description": "Spider de teste",
    "start_urls": ["https://exemplo.com"],
    "crawl_settings": {
        "depth": 2,
        "follow_links": True,
        "render_js": False,
        "delay_min": 1.0,
        "delay_max": 3.0,
        "rate_limit": 2,
    },
    "extraction": {
        "item_selector": ".item",
        "fields": {
            "titulo": {"selector": "h2", "type": "text", "required": True},
            "preco": {"selector": ".preco", "type": "text", "transform": "to_float"},
        },
    },
    "pagination": {
        "enabled": True,
        "selector": "a.next",
        "max_pages": 5,
    },
    "output": {
        "save_raw_html": False,
        "deduplicate": True,
    },
}


# ==============================================================================
# CLASSES MÍNIMAS PARA TESTE
# (Simulam as classes reais do sistema enquanto não estão implementadas)
# ==============================================================================

class GenericSpider:
    """Spider genérico configurável via YAML."""

    REQUIRED_FIELDS = ["spider_type", "name", "start_urls", "extraction"]
    VALID_SPIDER_TYPES = ["generic", "js", "news", "api"]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._validar_config()

    def _validar_config(self):
        for campo in self.REQUIRED_FIELDS:
            if campo not in self.config:
                raise ValueError(f"Campo obrigatório ausente: '{campo}'")
        if self.config["spider_type"] not in self.VALID_SPIDER_TYPES:
            raise ValueError(
                f"spider_type inválido: '{self.config['spider_type']}'. "
                f"Valores válidos: {self.VALID_SPIDER_TYPES}"
            )
        if not self.config.get("start_urls"):
            raise ValueError("start_urls não pode ser vazio")

    @classmethod
    def from_yaml_string(cls, yaml_content: str) -> "GenericSpider":
        """Cria spider a partir de string YAML."""
        config = yaml.safe_load(yaml_content)
        return cls(config)

    @classmethod
    def from_yaml_file(cls, path: Path) -> "GenericSpider":
        """Cria spider a partir de arquivo YAML."""
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config)

    @property
    def name(self) -> str:
        return self.config["name"]

    @property
    def spider_type(self) -> str:
        return self.config["spider_type"]

    @property
    def start_urls(self) -> list:
        return self.config["start_urls"]

    @property
    def render_js(self) -> bool:
        return self.config.get("crawl_settings", {}).get("render_js", False)

    @property
    def max_pages(self) -> int:
        return self.config.get("pagination", {}).get("max_pages", 10)

    def get_field_config(self, field_name: str) -> Optional[Dict]:
        """Retorna configuração de um campo de extração."""
        return self.config["extraction"]["fields"].get(field_name)

    def get_required_fields(self) -> list:
        """Retorna lista de campos obrigatórios."""
        fields = self.config["extraction"].get("fields", {})
        return [nome for nome, cfg in fields.items() if cfg.get("required", False)]


class CleanerPipeline:
    """Remove HTML e normaliza texto dos campos extraídos."""

    # Tags HTML básicas para remoção
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
    # Espaços múltiplos
    WHITESPACE_PATTERN = re.compile(r"\s+")
    # Entidades HTML comuns
    HTML_ENTITIES = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&#39;": "'",
        "&nbsp;": " ",
        "&mdash;": "—",
        "&ndash;": "–",
    }

    def process_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Processa um item removendo HTML de campos texto."""
        resultado = {}
        for chave, valor in item.items():
            if isinstance(valor, str):
                resultado[chave] = self._limpar_texto(valor)
            elif isinstance(valor, list):
                resultado[chave] = [
                    self._limpar_texto(v) if isinstance(v, str) else v
                    for v in valor
                ]
            else:
                resultado[chave] = valor
        return resultado

    def _limpar_texto(self, texto: str) -> str:
        """Remove HTML, decodifica entidades e normaliza espaços."""
        # Remover tags HTML
        sem_html = self.HTML_TAG_PATTERN.sub("", texto)
        # Decodificar entidades HTML
        for entidade, caractere in self.HTML_ENTITIES.items():
            sem_html = sem_html.replace(entidade, caractere)
        # Normalizar espaços
        normalizado = self.WHITESPACE_PATTERN.sub(" ", sem_html).strip()
        return normalizado


class DuplicateFilterPipeline:
    """Detecta e descarta itens duplicados por hash do campo-chave."""

    def __init__(self, dedup_field: str = "url"):
        self.dedup_field = dedup_field
        self._hashes_vistos: set = set()

    def process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Retorna None se duplicata, ou o item se for novo."""
        chave = item.get(self.dedup_field, "")
        if not chave:
            # Item sem campo-chave: deixar passar
            return item

        hash_item = self._gerar_hash(str(chave))

        if hash_item in self._hashes_vistos:
            return None  # Duplicata — descartar

        self._hashes_vistos.add(hash_item)
        return item

    def _gerar_hash(self, texto: str) -> str:
        """Gera hash SHA-256 truncado para identificar duplicatas."""
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]

    @property
    def total_duplicatas(self) -> int:
        """Número de duplicatas detectadas (calculado indiretamente)."""
        return 0  # Simplificado para testes

    def reset(self):
        """Limpa o cache de hashes (para novos jobs)."""
        self._hashes_vistos.clear()


class ProxyUpdater:
    """Gerencia e valida lista de proxies."""

    # Formato: protocolo://usuario:senha@host:porta
    # ou simplesmente host:porta
    PROXY_PATTERN_COMPLETO = re.compile(
        r"^(https?|socks5)://"
        r"(?:[\w.-]+:[\w.-]+@)?"
        r"([\w.-]+|\d{1,3}(?:\.\d{1,3}){3})"
        r":(\d{1,5})$"
    )
    PROXY_PATTERN_SIMPLES = re.compile(
        r"^([\w.-]+|\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$"
    )

    def __init__(self):
        self._proxies: list = []
        self._indice_atual: int = 0

    def validar_proxy(self, proxy: str) -> bool:
        """Valida se o proxy está no formato correto."""
        proxy = proxy.strip()
        if not proxy:
            return False

        match_completo = self.PROXY_PATTERN_COMPLETO.match(proxy)
        match_simples = self.PROXY_PATTERN_SIMPLES.match(proxy)
        if not match_completo and not match_simples:
            return False

        try:
            if match_completo:
                port = int(match_completo.group(3))
            else:
                port = int(match_simples.group(2))
        except (TypeError, ValueError):
            return False

        return 1 <= port <= 65535

    def adicionar_proxy(self, proxy: str) -> bool:
        """Adiciona proxy se válido. Retorna True se adicionado."""
        if self.validar_proxy(proxy):
            self._proxies.append(proxy.strip())
            return True
        return False

    def adicionar_lista(self, proxies: list) -> int:
        """Adiciona lista de proxies. Retorna quantidade de válidos adicionados."""
        return sum(1 for p in proxies if self.adicionar_proxy(p))

    def proximo_proxy(self) -> Optional[str]:
        """Retorna próximo proxy em rotação circular."""
        if not self._proxies:
            return None
        proxy = self._proxies[self._indice_atual % len(self._proxies)]
        self._indice_atual += 1
        return proxy

    @property
    def total_proxies(self) -> int:
        return len(self._proxies)


class AntiBotMiddleware:
    """Adiciona headers HTTP para evitar detecção de bot."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

    def __init__(self, rotate_ua: bool = True):
        self.rotate_ua = rotate_ua
        self._ua_index = 0

    def get_headers(self, url: str = "", referer: str = "") -> Dict[str, str]:
        """Retorna headers completos para uma requisição."""
        headers = dict(self.BASE_HEADERS)

        # User-Agent (rotação ou primeiro da lista)
        if self.rotate_ua:
            ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
            self._ua_index += 1
        else:
            ua = self.USER_AGENTS[0]

        headers["User-Agent"] = ua

        # Adicionar Referer se fornecido
        if referer:
            headers["Referer"] = referer

        return headers

    def aplicar_em_request(self, request: Dict) -> Dict:
        """Aplica headers anti-bot em um objeto de requisição."""
        url = request.get("url", "")
        referer = request.get("referer", "")
        request["headers"] = self.get_headers(url, referer)
        return request


# ==============================================================================
# TESTES: GenericSpider
# ==============================================================================

class TestGenericSpider:
    """Testes para GenericSpider — parsing e validação de YAML."""

    def test_carrega_config_valida(self):
        """Spider deve carregar configuração YAML válida sem erros."""
        spider = GenericSpider(CONFIG_GENERIC_MINIMA)

        assert spider.name == "teste-spider"
        assert spider.spider_type == "generic"
        assert spider.start_urls == ["https://exemplo.com"]

    def test_carrega_a_partir_de_yaml_string(self):
        """Spider deve ser criado a partir de string YAML."""
        yaml_str = criar_config_yaml(CONFIG_GENERIC_MINIMA)
        spider = GenericSpider.from_yaml_string(yaml_str)

        assert spider.name == "teste-spider"
        assert spider.render_js is False
        assert spider.max_pages == 5

    def test_lanca_erro_sem_spider_type(self):
        """Deve lançar ValueError quando spider_type está ausente."""
        config = dict(CONFIG_GENERIC_MINIMA)
        del config["spider_type"]

        with pytest.raises(ValueError, match="spider_type"):
            GenericSpider(config)

    def test_lanca_erro_spider_type_invalido(self):
        """Deve lançar ValueError para spider_type desconhecido."""
        config = {**CONFIG_GENERIC_MINIMA, "spider_type": "invalido"}

        with pytest.raises(ValueError, match="spider_type inválido"):
            GenericSpider(config)

    def test_lanca_erro_sem_start_urls(self):
        """Deve lançar ValueError quando start_urls está ausente."""
        config = dict(CONFIG_GENERIC_MINIMA)
        del config["start_urls"]

        with pytest.raises(ValueError, match="start_urls"):
            GenericSpider(config)

    def test_lanca_erro_start_urls_vazio(self):
        """Deve lançar ValueError quando start_urls é lista vazia."""
        config = {**CONFIG_GENERIC_MINIMA, "start_urls": []}

        with pytest.raises(ValueError, match="start_urls"):
            GenericSpider(config)

    def test_lanca_erro_sem_extraction(self):
        """Deve lançar ValueError quando extraction está ausente."""
        config = dict(CONFIG_GENERIC_MINIMA)
        del config["extraction"]

        with pytest.raises(ValueError, match="extraction"):
            GenericSpider(config)

    def test_get_field_config_existente(self):
        """Deve retornar configuração de campo existente."""
        spider = GenericSpider(CONFIG_GENERIC_MINIMA)
        campo = spider.get_field_config("titulo")

        assert campo is not None
        assert campo["selector"] == "h2"
        assert campo["type"] == "text"
        assert campo["required"] is True

    def test_get_field_config_inexistente(self):
        """Deve retornar None para campo não configurado."""
        spider = GenericSpider(CONFIG_GENERIC_MINIMA)
        assert spider.get_field_config("campo_inexistente") is None

    def test_get_required_fields(self):
        """Deve retornar apenas os campos marcados como required=True."""
        spider = GenericSpider(CONFIG_GENERIC_MINIMA)
        campos_obrigatorios = spider.get_required_fields()

        assert "titulo" in campos_obrigatorios
        assert "preco" not in campos_obrigatorios  # preco não tem required=True

    def test_aceita_spider_type_js(self):
        """Deve aceitar spider_type='js'."""
        config = {**CONFIG_GENERIC_MINIMA, "spider_type": "js"}
        spider = GenericSpider(config)
        assert spider.spider_type == "js"

    def test_render_js_default_false(self):
        """render_js deve ser False por padrão."""
        spider = GenericSpider(CONFIG_GENERIC_MINIMA)
        assert spider.render_js is False

    def test_render_js_true_quando_configurado(self):
        """render_js deve ser True quando configurado assim."""
        config = dict(CONFIG_GENERIC_MINIMA)
        config["crawl_settings"] = {**config["crawl_settings"], "render_js": True}
        spider = GenericSpider(config)
        assert spider.render_js is True

    def test_carrega_arquivo_generic_yml_real(self):
        """Deve carregar o arquivo configs/generic.yml do projeto."""
        caminho = CONFIGS_DIR / "generic.yml"
        if not caminho.exists():
            pytest.skip(f"Arquivo não encontrado: {caminho}")

        spider = GenericSpider.from_yaml_file(caminho)
        assert spider.name is not None
        assert spider.spider_type in GenericSpider.VALID_SPIDER_TYPES

    @pytest.mark.parametrize("spider_type", ["generic", "js", "news", "api"])
    def test_todos_tipos_validos(self, spider_type):
        """Todos os spider_types válidos devem ser aceitos."""
        config = {**CONFIG_GENERIC_MINIMA, "spider_type": spider_type}
        spider = GenericSpider(config)
        assert spider.spider_type == spider_type


# ==============================================================================
# TESTES: CleanerPipeline
# ==============================================================================

class TestCleanerPipeline:
    """Testes para CleanerPipeline — limpeza de HTML."""

    @pytest.fixture
    def pipeline(self):
        return CleanerPipeline()

    def test_remove_tags_html_simples(self, pipeline):
        """Deve remover tags HTML básicas."""
        item = {"titulo": "<h1>Produto de Teste</h1>"}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == "Produto de Teste"

    def test_remove_tags_html_aninhadas(self, pipeline):
        """Deve remover tags HTML aninhadas."""
        item = {"descricao": "<p><strong>Descrição</strong> do <em>produto</em></p>"}
        resultado = pipeline.process_item(item)
        assert resultado["descricao"] == "Descrição do produto"

    def test_decodifica_entidades_html(self, pipeline):
        """Deve decodificar entidades HTML como &amp;, &lt;, etc."""
        item = {"titulo": "Produto &amp; Acessório"}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == "Produto & Acessório"

    def test_decodifica_nbsp(self, pipeline):
        """Deve converter &nbsp; em espaço."""
        item = {"preco": "R$&nbsp;99,90"}
        resultado = pipeline.process_item(item)
        assert "&nbsp;" not in resultado["preco"]

    def test_normaliza_espacos_multiplos(self, pipeline):
        """Deve reduzir múltiplos espaços para um único espaço."""
        item = {"titulo": "Produto   com   espaços   extras"}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == "Produto com espaços extras"

    def test_remove_quebras_de_linha(self, pipeline):
        """Deve normalizar quebras de linha em espaços."""
        item = {"descricao": "Linha 1\nLinha 2\r\nLinha 3"}
        resultado = pipeline.process_item(item)
        assert "\n" not in resultado["descricao"]
        assert "\r" not in resultado["descricao"]

    def test_strip_espacos_nas_bordas(self, pipeline):
        """Deve remover espaços no início e fim do texto."""
        item = {"titulo": "   Produto com espaços   "}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == "Produto com espaços"

    def test_preserva_campos_nao_string(self, pipeline):
        """Deve preservar campos que não são strings (números, listas, etc.)."""
        item = {"preco": 99.90, "ativo": True, "quantidade": 5}
        resultado = pipeline.process_item(item)
        assert resultado["preco"] == 99.90
        assert resultado["ativo"] is True
        assert resultado["quantidade"] == 5

    def test_limpa_lista_de_strings(self, pipeline):
        """Deve limpar HTML de itens dentro de listas."""
        item = {"tags": ["<span>tag1</span>", "<em>tag2</em>"]}
        resultado = pipeline.process_item(item)
        assert resultado["tags"] == ["tag1", "tag2"]

    def test_trata_string_vazia(self, pipeline):
        """Deve retornar string vazia quando input é vazio."""
        item = {"titulo": ""}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == ""

    def test_trata_html_complexo(self, pipeline):
        """Deve remover HTML complexo mantendo apenas texto."""
        html = textwrap.dedent("""
            <div class="produto">
                <h1 class="titulo">Nome do <span>Produto</span></h1>
                <p>Descrição <a href="#">com link</a></p>
            </div>
        """).strip()
        item = {"conteudo": html}
        resultado = pipeline.process_item(item)
        assert "<" not in resultado["conteudo"]
        assert ">" not in resultado["conteudo"]
        assert "Nome do Produto" in resultado["conteudo"]

    def test_decodifica_aspas_html(self, pipeline):
        """Deve decodificar &quot; e &#39; em aspas."""
        item = {"titulo": "Produto &quot;Premium&quot;"}
        resultado = pipeline.process_item(item)
        assert resultado["titulo"] == 'Produto "Premium"'


# ==============================================================================
# TESTES: DuplicateFilterPipeline
# ==============================================================================

class TestDuplicateFilterPipeline:
    """Testes para DuplicateFilterPipeline — deduplicação."""

    @pytest.fixture
    def pipeline(self):
        return DuplicateFilterPipeline(dedup_field="url")

    def test_primeiro_item_passado(self, pipeline):
        """Primeiro item com URL única deve passar."""
        item = {"url": "https://exemplo.com/produto/1", "titulo": "Produto 1"}
        resultado = pipeline.process_item(item)
        assert resultado is not None
        assert resultado["titulo"] == "Produto 1"

    def test_item_duplicado_descartado(self, pipeline):
        """Item com mesma URL deve ser descartado na segunda ocorrência."""
        item = {"url": "https://exemplo.com/produto/1", "titulo": "Produto 1"}
        pipeline.process_item(item)  # Primeiro passe
        resultado = pipeline.process_item(item)  # Segundo passe
        assert resultado is None

    def test_itens_diferentes_passam(self, pipeline):
        """Itens com URLs diferentes devem passar todos."""
        itens = [
            {"url": "https://exemplo.com/produto/1"},
            {"url": "https://exemplo.com/produto/2"},
            {"url": "https://exemplo.com/produto/3"},
        ]
        resultados = [pipeline.process_item(item) for item in itens]
        assert all(r is not None for r in resultados)

    def test_item_sem_campo_dedup_passa(self, pipeline):
        """Item sem o campo de deduplicação deve passar (não filtrar)."""
        item = {"titulo": "Produto sem URL"}
        resultado = pipeline.process_item(item)
        assert resultado is not None

    def test_reset_limpa_cache(self, pipeline):
        """Após reset, item previamente visto deve passar novamente."""
        item = {"url": "https://exemplo.com/produto/1"}
        pipeline.process_item(item)  # Primeiro passe
        pipeline.reset()
        resultado = pipeline.process_item(item)  # Após reset
        assert resultado is not None

    def test_dedup_por_campo_diferente(self):
        """Deve usar o campo de deduplicação configurado."""
        pipeline = DuplicateFilterPipeline(dedup_field="sku")
        item1 = {"sku": "SKU-001", "titulo": "Produto A"}
        item2 = {"sku": "SKU-001", "titulo": "Produto B (duplicado)"}

        r1 = pipeline.process_item(item1)
        r2 = pipeline.process_item(item2)

        assert r1 is not None
        assert r2 is None  # Mesmo SKU = duplicata

    def test_dedup_case_sensitive(self, pipeline):
        """Deduplicação deve ser case-sensitive."""
        item1 = {"url": "https://exemplo.com/Produto/1"}
        item2 = {"url": "https://exemplo.com/produto/1"}  # URL diferente (case)

        r1 = pipeline.process_item(item1)
        r2 = pipeline.process_item(item2)

        # As URLs são diferentes (case-sensitive), ambas devem passar
        assert r1 is not None
        assert r2 is not None

    def test_multiplos_duplicados(self, pipeline):
        """Deve filtrar múltiplas ocorrências da mesma URL."""
        item = {"url": "https://exemplo.com/produto/1"}
        resultados = [pipeline.process_item(item) for _ in range(5)]

        assert resultados[0] is not None  # Primeira passagem
        assert all(r is None for r in resultados[1:])  # Demais são duplicatas


# ==============================================================================
# TESTES: ProxyUpdater
# ==============================================================================

class TestProxyUpdater:
    """Testes para ProxyUpdater — validação e gerenciamento de proxies."""

    @pytest.fixture
    def updater(self):
        return ProxyUpdater()

    @pytest.mark.parametrize("proxy_valido", [
        "192.168.1.1:8080",
        "10.0.0.1:3128",
        "proxy.exemplo.com:8080",
        "http://192.168.1.1:8080",
        "https://proxy.servidor.com:443",
        "socks5://192.168.1.1:1080",
        "http://usuario:senha@proxy.com:8080",
        "socks5://user:pass@10.0.0.1:1080",
    ])
    def test_valida_proxies_corretos(self, updater, proxy_valido):
        """Deve aceitar proxies em formatos válidos."""
        assert updater.validar_proxy(proxy_valido) is True

    @pytest.mark.parametrize("proxy_invalido", [
        "",
        "nao-e-um-proxy",
        "192.168.1.1",           # Sem porta
        ":8080",                  # Sem host
        "192.168.1.1:99999",     # Porta > 65535
        "http://",               # URL incompleta
        "ftp://proxy.com:21",    # Protocolo não suportado
    ])
    def test_rejeita_proxies_invalidos(self, updater, proxy_invalido):
        """Deve rejeitar proxies em formatos inválidos."""
        assert updater.validar_proxy(proxy_invalido) is False

    def test_adiciona_proxy_valido(self, updater):
        """Deve adicionar proxy válido e retornar True."""
        resultado = updater.adicionar_proxy("192.168.1.1:8080")
        assert resultado is True
        assert updater.total_proxies == 1

    def test_rejeita_proxy_invalido_na_adicao(self, updater):
        """Deve retornar False e não adicionar proxy inválido."""
        resultado = updater.adicionar_proxy("nao-e-proxy")
        assert resultado is False
        assert updater.total_proxies == 0

    def test_adiciona_lista_de_proxies(self, updater):
        """Deve adicionar múltiplos proxies válidos de uma lista."""
        proxies = [
            "192.168.1.1:8080",
            "10.0.0.1:3128",
            "invalido",  # Este deve ser ignorado
            "proxy.server.com:8080",
        ]
        validos_adicionados = updater.adicionar_lista(proxies)
        assert validos_adicionados == 3  # 3 de 4 são válidos
        assert updater.total_proxies == 3

    def test_rotacao_de_proxies(self, updater):
        """Deve rotacionar proxies em ordem circular."""
        proxies = ["1.1.1.1:8080", "2.2.2.2:8080", "3.3.3.3:8080"]
        updater.adicionar_lista(proxies)

        obtidos = [updater.proximo_proxy() for _ in range(6)]
        # Os 3 primeiros devem ser os 3 proxies
        assert set(obtidos[:3]) == set(proxies)
        # Devem se repetir em loop
        assert obtidos[0] == obtidos[3]

    def test_retorna_none_sem_proxies(self, updater):
        """Deve retornar None quando não há proxies configurados."""
        assert updater.proximo_proxy() is None

    def test_proxy_com_espacos_e_aceito(self, updater):
        """Deve aceitar proxy com espaços nas bordas (fazer strip)."""
        resultado = updater.adicionar_proxy("  192.168.1.1:8080  ")
        assert resultado is True


# ==============================================================================
# TESTES: AntiBotMiddleware
# ==============================================================================

class TestAntiBotMiddleware:
    """Testes para AntiBotMiddleware — headers anti-detecção."""

    @pytest.fixture
    def middleware(self):
        return AntiBotMiddleware(rotate_ua=True)

    def test_retorna_user_agent(self, middleware):
        """Headers devem incluir User-Agent."""
        headers = middleware.get_headers()
        assert "User-Agent" in headers
        assert len(headers["User-Agent"]) > 20

    def test_user_agent_e_navegador_real(self, middleware):
        """User-Agent deve conter string de navegador real."""
        headers = middleware.get_headers()
        ua = headers["User-Agent"]
        # Deve ser Mozilla ou algum navegador real
        assert any(browser in ua for browser in ["Mozilla", "Chrome", "Firefox", "Safari"])

    def test_headers_obrigatorios_presentes(self, middleware):
        """Todos os headers básicos obrigatórios devem estar presentes."""
        headers_obrigatorios = [
            "Accept",
            "Accept-Language",
            "Accept-Encoding",
            "User-Agent",
        ]
        headers = middleware.get_headers()
        for header in headers_obrigatorios:
            assert header in headers, f"Header '{header}' está ausente"

    def test_accept_language_pt_br(self, middleware):
        """Accept-Language deve incluir pt-BR."""
        headers = middleware.get_headers()
        assert "pt-BR" in headers["Accept-Language"]

    def test_rotacao_user_agent(self, middleware):
        """Com rotate_ua=True, deve rotacionar os User-Agents."""
        uas_obtidos = {middleware.get_headers()["User-Agent"] for _ in range(10)}
        # Com 10 requisições, deve haver pelo menos 2 UAs diferentes
        assert len(uas_obtidos) >= 2

    def test_sem_rotacao_ua_fixo(self):
        """Com rotate_ua=False, deve sempre usar o mesmo User-Agent."""
        middleware = AntiBotMiddleware(rotate_ua=False)
        uas = [middleware.get_headers()["User-Agent"] for _ in range(5)]
        # Todos devem ser iguais
        assert len(set(uas)) == 1

    def test_adiciona_referer_quando_fornecido(self, middleware):
        """Deve incluir Referer quando fornecido."""
        headers = middleware.get_headers(referer="https://google.com")
        assert "Referer" in headers
        assert headers["Referer"] == "https://google.com"

    def test_sem_referer_quando_nao_fornecido(self, middleware):
        """Não deve incluir Referer quando não fornecido."""
        headers = middleware.get_headers()
        assert "Referer" not in headers

    def test_aplicar_em_request(self, middleware):
        """Deve adicionar headers em objeto de request."""
        request = {"url": "https://exemplo.com", "method": "GET"}
        request_com_headers = middleware.aplicar_em_request(request)

        assert "headers" in request_com_headers
        assert "User-Agent" in request_com_headers["headers"]
        assert "Accept" in request_com_headers["headers"]

    def test_accept_html_nos_headers(self, middleware):
        """Accept deve incluir text/html."""
        headers = middleware.get_headers()
        assert "text/html" in headers["Accept"]

    def test_dnt_header_presente(self, middleware):
        """Header DNT (Do Not Track) deve estar presente."""
        headers = middleware.get_headers()
        assert "DNT" in headers


# ==============================================================================
# TESTES DE INTEGRAÇÃO DOS CONFIGS YAML
# ==============================================================================

class TestConfigsYamlReais:
    """Valida que todos os arquivos YAML de configuração são válidos."""

    @pytest.mark.parametrize("arquivo", [
        "generic.yml",
        "ecommerce.yml",
        "news.yml",
        "js_site.yml",
        "api.yml",
    ])
    def test_arquivo_yaml_e_valido(self, arquivo):
        """Cada arquivo YAML deve ser parseável sem erros."""
        caminho = CONFIGS_DIR / arquivo
        if not caminho.exists():
            pytest.skip(f"Arquivo não encontrado: {caminho}")

        with open(caminho, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert isinstance(config, dict)

    @pytest.mark.parametrize("arquivo", [
        "generic.yml",
        "ecommerce.yml",
        "js_site.yml",
    ])
    def test_yaml_tem_campos_obrigatorios(self, arquivo):
        """Configs genéricas devem ter spider_type e name."""
        caminho = CONFIGS_DIR / arquivo
        if not caminho.exists():
            pytest.skip(f"Arquivo não encontrado: {caminho}")

        with open(caminho, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert "spider_type" in config, f"{arquivo}: 'spider_type' ausente"
        assert "name" in config, f"{arquivo}: 'name' ausente"

    def test_ecommerce_yml_tem_campos_produto(self):
        """ecommerce.yml deve ter campos essenciais de produto."""
        caminho = CONFIGS_DIR / "ecommerce.yml"
        if not caminho.exists():
            pytest.skip("ecommerce.yml não encontrado")

        with open(caminho, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        campos = config.get("extraction", {}).get("fields", {})
        campos_esperados = ["nome", "preco"]

        for campo in campos_esperados:
            assert campo in campos, f"ecommerce.yml: campo '{campo}' ausente"

    def test_js_site_yml_tem_render_js_true(self):
        """js_site.yml deve ter render_js=True."""
        caminho = CONFIGS_DIR / "js_site.yml"
        if not caminho.exists():
            pytest.skip("js_site.yml não encontrado")

        with open(caminho, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert config.get("render_js") is True, "js_site.yml deve ter render_js: true"
