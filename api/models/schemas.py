"""
schemas.py — Schemas Pydantic v2 para a API do WebScraper Jurídico

Define todos os modelos de request/response usados pelos endpoints.
Utiliza Pydantic v2 com model_config, field_validator e computed_field.

Organização:
    - Schemas de Request: ScrapeRequest, BulkScrapeRequest, PreviewRequest, etc.
    - Schemas de Response: JobResponse, ItemResponse, etc.
    - Schemas Genéricos: PaginatedResponse[T], HealthResponse, etc.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# Tipo genérico para paginação
T = TypeVar("T")


# =============================================================================
# Schemas de Request — Scraping
# =============================================================================


class ScrapeRequest(BaseModel):
    """Request para disparar um scraping imediato de uma URL."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.tjsp.jus.br/jurisprudencia",
                "config_name": "tjsp_jurisprudencia",
                "spider_type": "generic",
                "render_js": False,
                "use_proxy": None,
                "crawl_depth": 1,
                "metadata": {"categoria": "acórdão", "tribunal": "TJSP"},
            }
        }
    )

    url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        description="URL alvo para scraping",
        examples=["https://www.tjsp.jus.br/jurisprudencia"],
    )
    config_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Nome da configuração de spider a utilizar",
    )
    spider_type: str = Field(
        default="generic",
        description="Tipo do spider: generic, scrapy, playwright, jusbrasil",
        examples=["generic", "scrapy", "playwright", "jusbrasil"],
    )
    render_js: bool = Field(
        default=False,
        description="Se deve renderizar JavaScript (usa Playwright)",
    )
    use_proxy: Optional[bool] = Field(
        default=None,
        description="Força uso de proxy: true/false. Null = segue configuração global/spider.",
    )
    crawl_depth: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Profundidade máxima de crawling (1 = apenas URL alvo)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais passados ao spider",
    )

    @field_validator("url")
    @classmethod
    def validar_url(cls, v: str) -> str:
        """Valida que a URL começa com http:// ou https://."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("A URL deve começar com http:// ou https://")
        return v.strip()

    @field_validator("spider_type")
    @classmethod
    def validar_spider_type(cls, v: str) -> str:
        """Valida que o tipo de spider é suportado."""
        tipos_validos = {"generic", "scrapy", "playwright", "requests", "jusbrasil"}
        if v not in tipos_validos:
            raise ValueError(f"Tipo de spider inválido. Use um de: {tipos_validos}")
        return v


class BulkScrapeRequest(BaseModel):
    """Request para disparar scraping de múltiplas URLs."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "urls": [
                    "https://www.tjsp.jus.br/pag1",
                    "https://www.tjsp.jus.br/pag2",
                ],
                "config_name": "tjsp_generic",
                "spider_type": "generic",
                "render_js": False,
                "use_proxy": None,
            }
        }
    )

    urls: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de URLs para scraping em lote (máx. 100)",
    )
    config_name: Optional[str] = Field(default=None, max_length=255)
    spider_type: str = Field(default="generic")
    render_js: bool = Field(default=False)
    use_proxy: Optional[bool] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("urls")
    @classmethod
    def validar_urls(cls, v: List[str]) -> List[str]:
        """Valida que todas as URLs são válidas."""
        urls_validas = []
        for url in v:
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"URL inválida: {url} — deve começar com http:// ou https://")
            urls_validas.append(url)
        return urls_validas


class PreviewRequest(BaseModel):
    """Request para preview de scraping sem salvar no banco."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.tjsp.jus.br/jurisprudencia",
                "selectors": {
                    "titulo": "h1.titulo",
                    "conteudo": "div.conteudo p",
                },
            }
        }
    )

    url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        description="URL para extrair preview",
    )
    selectors: Dict[str, str] = Field(
        default_factory=dict,
        description="Seletores CSS para extração de campos específicos",
        examples=[{"titulo": "h1", "conteudo": "article p"}],
    )
    render_js: bool = Field(default=False, description="Se deve renderizar JavaScript")

    @field_validator("url")
    @classmethod
    def validar_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("A URL deve começar com http:// ou https://")
        return v.strip()


# =============================================================================
# Schemas de Request — Spider Config
# =============================================================================


class CreateSpiderConfig(BaseModel):
    """Request para criar uma nova configuração de spider."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "tjsp_acórdãos",
                "config_yaml": "spider_type: generic\nstart_url: https://tjsp.jus.br",
                "description": "Spider para coleta de acórdãos do TJSP",
                "spider_type": "generic",
            }
        }
    )

    name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Nome único da configuração de spider",
    )
    config_yaml: str = Field(
        ...,
        min_length=10,
        description="Configuração do spider em formato YAML",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Descrição legível da configuração",
    )
    spider_type: Optional[str] = Field(
        default="generic",
        description="Tipo do spider: generic, scrapy, playwright",
    )

    @field_validator("name")
    @classmethod
    def validar_nome(cls, v: str) -> str:
        """Valida que o nome contém apenas caracteres alfanuméricos, hífens e underscores."""
        if not re.match(r"^[a-zA-Z0-9_\-À-ÿ ]+$", v):
            raise ValueError(
                "Nome deve conter apenas letras, números, hífens, underscores e espaços"
            )
        return v.strip()


class UpdateSpiderConfig(BaseModel):
    """Request para atualizar uma configuração de spider existente."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "config_yaml": "spider_type: playwright\nrender_js: true",
                "description": "Versão atualizada com suporte a JavaScript",
            }
        }
    )

    config_yaml: Optional[str] = Field(default=None, min_length=10)
    description: Optional[str] = Field(default=None, max_length=1000)
    spider_type: Optional[str] = Field(default=None)
    active: Optional[bool] = Field(default=None)


# =============================================================================
# Schemas de Request — Agendamentos
# =============================================================================


class CreateScheduledJob(BaseModel):
    """Request para criar um novo agendamento de scraping."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Coleta TJSP diária",
                "spider_config_id": 1,
                "cron_expression": "0 6 * * *",
                "enabled": True,
            }
        }
    )

    name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Nome descritivo do agendamento",
    )
    spider_config_id: int = Field(
        ...,
        gt=0,
        description="ID da configuração de spider a utilizar",
    )
    cron_expression: str = Field(
        ...,
        description="Expressão CRON (ex: '0 */6 * * *' = a cada 6 horas)",
        examples=["0 6 * * *", "*/30 * * * *", "0 0 * * 1"],
    )
    enabled: bool = Field(default=True, description="Se o agendamento começa ativo")

    @field_validator("cron_expression")
    @classmethod
    def validar_cron(cls, v: str) -> str:
        """Valida que a expressão CRON tem 5 campos."""
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "Expressão CRON inválida. Deve ter 5 campos: minuto hora dia_mês mês dia_semana"
            )
        return v.strip()


class UpdateScheduledJob(BaseModel):
    """Request para atualizar um agendamento existente."""

    name: Optional[str] = Field(default=None, min_length=3, max_length=255)
    cron_expression: Optional[str] = Field(default=None)
    enabled: Optional[bool] = Field(default=None)
    spider_config_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("cron_expression")
    @classmethod
    def validar_cron(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError("Expressão CRON inválida. Deve ter 5 campos.")
        return v.strip()


# =============================================================================
# Schemas de Response — Jobs
# =============================================================================


class JobResponse(BaseModel):
    """Response com dados completos de um job de scraping."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único do job")
    url: str = Field(..., description="URL alvo do scraping")
    config_name: Optional[str] = Field(default=None, description="Configuração de spider utilizada")
    status: str = Field(..., description="Status atual: pending, running, done, failed, cancelled")
    spider_type: Optional[str] = Field(default=None, description="Tipo do spider utilizado")
    render_js: bool = Field(default=False, description="Se utilizou renderização JavaScript")
    crawl_depth: int = Field(default=1, description="Profundidade de crawling utilizada")
    items_scraped: int = Field(default=0, description="Quantidade de itens coletados")
    error_msg: Optional[str] = Field(default=None, description="Mensagem de erro (se houver)")
    created_at: datetime = Field(..., description="Data/hora de criação")
    started_at: Optional[datetime] = Field(default=None, description="Data/hora de início")
    completed_at: Optional[datetime] = Field(default=None, description="Data/hora de conclusão")

    @computed_field
    @property
    def duracao_segundos(self) -> Optional[float]:
        """Calcula a duração do job em segundos (se disponível)."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return round(delta.total_seconds(), 2)
        return None

    @computed_field
    @property
    def duracao_formatada(self) -> Optional[str]:
        """Retorna a duração do job em formato legível (ex: '2min 30s')."""
        segundos = self.duracao_segundos
        if segundos is None:
            return None
        minutos = int(segundos // 60)
        segs = int(segundos % 60)
        if minutos > 0:
            return f"{minutos}min {segs}s"
        return f"{segs}s"


class JobCreatedResponse(BaseModel):
    """Response imediata ao criar um job de scraping."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": 42,
                "status": "pending",
                "created_at": "2024-01-15T10:30:00Z",
                "estimated_time": "O job deve ser processado em até 60 segundos",
            }
        }
    )

    job_id: int = Field(..., description="ID do job criado")
    status: str = Field(default="pending", description="Status inicial do job")
    created_at: datetime = Field(..., description="Data/hora de criação")
    estimated_time: str = Field(
        default="O job deve ser processado em até 60 segundos",
        description="Estimativa de tempo para processamento",
    )


class BulkJobCreatedResponse(BaseModel):
    """Response ao criar múltiplos jobs em lote."""

    job_ids: List[int] = Field(..., description="Lista de IDs dos jobs criados")
    total: int = Field(..., description="Total de jobs criados")
    status: str = Field(default="pending", description="Status inicial dos jobs")


# =============================================================================
# Schemas de Response — Items
# =============================================================================


class ItemResponse(BaseModel):
    """Response com dados de um item coletado."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único do item")
    job_id: int = Field(..., description="ID do job que gerou este item")
    url: str = Field(..., description="URL de onde o item foi coletado")
    title: Optional[str] = Field(default=None, description="Título extraído")
    content: Optional[str] = Field(default=None, description="Conteúdo textual (pode ser truncado)")
    domain: Optional[str] = Field(default=None, description="Domínio da URL de origem")
    content_hash: str = Field(..., description="Hash SHA-256 do conteúdo para deduplicação")
    scraped_at: datetime = Field(..., description="Data/hora da coleta")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados brutos em JSON")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="metadata_",
        description="Metadados adicionais",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    def truncar_content(self, max_chars: int = 500) -> "ItemResponse":
        """Retorna uma cópia com o conteúdo truncado para exibição em listagens."""
        if self.content and len(self.content) > max_chars:
            return self.model_copy(
                update={"content": self.content[:max_chars] + "..."}
            )
        return self


# =============================================================================
# Schemas de Response — Spider Config
# =============================================================================


class SpiderConfigResponse(BaseModel):
    """Response com dados de uma configuração de spider."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único da configuração")
    name: str = Field(..., description="Nome único da configuração")
    config_yaml: str = Field(..., description="Configuração em formato YAML")
    spider_type: Optional[str] = Field(default=None, description="Tipo do spider")
    description: Optional[str] = Field(default=None, description="Descrição legível")
    active: bool = Field(default=True, description="Se a configuração está ativa")
    created_at: datetime = Field(..., description="Data/hora de criação")
    updated_at: datetime = Field(..., description="Data/hora da última atualização")


class SpiderValidationResponse(BaseModel):
    """Response da validação de uma configuração YAML."""

    valid: bool = Field(..., description="Se o YAML é válido")
    errors: List[str] = Field(default_factory=list, description="Lista de erros encontrados")
    warnings: List[str] = Field(default_factory=list, description="Avisos não bloqueantes")
    parsed_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Configuração parseada (se válida)"
    )


# =============================================================================
# Schemas de Response — Agendamentos
# =============================================================================


class ScheduledJobResponse(BaseModel):
    """Response com dados de um agendamento."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único do agendamento")
    name: str = Field(..., description="Nome do agendamento")
    spider_config_id: int = Field(..., description="ID da configuração de spider")
    cron_expression: str = Field(..., description="Expressão CRON do agendamento")
    enabled: bool = Field(..., description="Se o agendamento está ativo")
    last_run: Optional[datetime] = Field(default=None, description="Última execução")
    next_run: Optional[datetime] = Field(default=None, description="Próxima execução")
    created_at: datetime = Field(..., description="Data/hora de criação")


# =============================================================================
# Schemas de Response — Health Check
# =============================================================================


class HealthComponentStatus(BaseModel):
    """Status de um componente individual no health check."""

    status: Literal["ok", "error", "degraded"] = Field(..., description="Status do componente")
    message: str = Field(..., description="Mensagem descritiva")
    latency_ms: Optional[float] = Field(default=None, description="Latência de resposta em ms")


class HealthResponse(BaseModel):
    """Response do endpoint /health com status de todos os componentes."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "1.0.0",
                "components": {
                    "database": {"status": "ok", "message": "Banco de dados acessível"},
                    "redis": {"status": "ok", "message": "Redis acessível"},
                },
            }
        }
    )

    status: Literal["ok", "error", "degraded"] = Field(..., description="Status geral da aplicação")
    version: str = Field(..., description="Versão da API")
    timestamp: datetime = Field(..., description="Data/hora da verificação")
    components: Dict[str, HealthComponentStatus] = Field(
        ..., description="Status individual de cada componente"
    )

    @computed_field
    @property
    def todos_ok(self) -> bool:
        """True se todos os componentes estão com status 'ok'."""
        return all(c.status == "ok" for c in self.components.values())


# =============================================================================
# Schemas Genéricos — Paginação e Busca
# =============================================================================


class PaginatedResponse(BaseModel, Generic[T]):
    """Response paginada genérica para listagens."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: List[T] = Field(..., description="Lista de itens da página atual")
    total: int = Field(..., description="Total de itens disponíveis (sem paginação)")
    page: int = Field(..., description="Página atual (começa em 1)")
    limit: int = Field(..., description="Máximo de itens por página")

    @computed_field
    @property
    def total_pages(self) -> int:
        """Calcula o número total de páginas."""
        if self.limit == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit

    @computed_field
    @property
    def has_next(self) -> bool:
        """True se há uma próxima página."""
        return self.page < self.total_pages

    @computed_field
    @property
    def has_prev(self) -> bool:
        """True se há uma página anterior."""
        return self.page > 1


class DomainStats(BaseModel):
    """Estatísticas de um domínio scrapeado."""

    domain: str = Field(..., description="Nome do domínio")
    total_items: int = Field(..., description="Total de itens coletados deste domínio")
    last_scraped: Optional[datetime] = Field(
        default=None, description="Data/hora da última coleta"
    )
    total_jobs: int = Field(default=0, description="Total de jobs executados para este domínio")


class SearchResult(BaseModel):
    """Resultado de busca full-text."""

    item: ItemResponse = Field(..., description="Item encontrado")
    relevance_score: Optional[float] = Field(
        default=None, description="Score de relevância (0.0 a 1.0)"
    )
    matched_fields: List[str] = Field(
        default_factory=list,
        description="Campos onde houve correspondência",
    )


class SearchResponse(BaseModel):
    """Response completa de uma busca full-text."""

    results: List[ItemResponse] = Field(..., description="Itens encontrados")
    total: int = Field(..., description="Total de resultados")
    query_time_ms: float = Field(..., description="Tempo de execução da query em ms")
    query: str = Field(..., description="Termo buscado")
    page: int = Field(default=1)
    limit: int = Field(default=20)


class ExportMeta(BaseModel):
    """Metadados de uma exportação de dados."""

    format: Literal["json", "csv"] = Field(..., description="Formato do arquivo exportado")
    total_items: int = Field(..., description="Total de itens no arquivo")
    generated_at: datetime = Field(..., description="Data/hora de geração")
    file_size_bytes: Optional[int] = Field(default=None, description="Tamanho do arquivo em bytes")
    filters_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Filtros aplicados na exportação",
    )


# =============================================================================
# Schemas de Response — Erros
# =============================================================================


class ErrorResponse(BaseModel):
    """Response padrão para erros da API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "erro": "Recurso não encontrado",
                "detalhes": "Job com ID 999 não foi encontrado",
                "codigo": 404,
            }
        }
    )

    erro: str = Field(..., description="Mensagem de erro principal")
    detalhes: Optional[str] = Field(default=None, description="Detalhes adicionais do erro")
    codigo: int = Field(..., description="Código HTTP do erro")
    campo: Optional[str] = Field(default=None, description="Campo com erro de validação")


class ValidationErrorResponse(BaseModel):
    """Response para erros de validação (422 Unprocessable Entity)."""

    erro: str = Field(default="Erro de validação nos dados enviados")
    campos_invalidos: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de campos com erros",
    )
    codigo: int = Field(default=422)


# =============================================================================
# Schemas de Response — Preview
# =============================================================================


class PreviewResponse(BaseModel):
    """Response do endpoint de preview de scraping."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "extracted_data": {"titulo": "Acórdão 1234", "conteudo": "..."},
                "raw_html_snippet": "<html>...</html>",
                "time_ms": 1250.5,
                "url": "https://www.tjsp.jus.br",
                "success": True,
            }
        }
    )

    extracted_data: Dict[str, Any] = Field(
        ..., description="Dados extraídos pelos seletores fornecidos"
    )
    raw_html_snippet: str = Field(
        ..., description="Trecho do HTML bruto da página (primeiros 2000 chars)"
    )
    time_ms: float = Field(..., description="Tempo de execução em milissegundos")
    url: str = Field(..., description="URL processada")
    success: bool = Field(..., description="Se o preview foi bem-sucedido")
    error: Optional[str] = Field(default=None, description="Erro (se success=False)")


# =============================================================================
# Schemas de Eventos WebSocket
# =============================================================================


class WebSocketEvent(BaseModel):
    """Evento enviado pelo WebSocket de monitoramento de jobs."""

    event: str = Field(
        ...,
        description="Tipo do evento: job_created, job_started, job_progress, job_done, job_failed",
    )
    job_id: int = Field(..., description="ID do job relacionado ao evento")
    data: Dict[str, Any] = Field(default_factory=dict, description="Dados do evento")
    timestamp: datetime = Field(..., description="Data/hora do evento")
