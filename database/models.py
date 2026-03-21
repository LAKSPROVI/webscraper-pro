"""
models.py — Modelos SQLAlchemy 2.0 para o WebScraper Jurídico

Define todas as tabelas do banco de dados com suporte a:
- Tipos assíncronos (AsyncAttrs, mapped_column)
- JSONB para dados semi-estruturados
- Enums para status controlados
- Timestamps com timezone
- Relacionamentos entre tabelas
"""

from __future__ import annotations

import hashlib
import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.ext.asyncio import AsyncAttrs


# ---------------------------------------------------------------------------
# Enum de status do job de scraping
# ---------------------------------------------------------------------------

class JobStatus(str, enum.Enum):
    """Status possíveis de um job de scraping."""
    PENDING   = "pending"    # Aguardando execução
    RUNNING   = "running"    # Em andamento
    DONE      = "done"       # Concluído com sucesso
    FAILED    = "failed"     # Falhou com erro
    CANCELLED = "cancelled"  # Cancelado pelo usuário


# ---------------------------------------------------------------------------
# Base declarativa com suporte assíncrono
# ---------------------------------------------------------------------------

class Base(AsyncAttrs, DeclarativeBase):
    """Base para todos os models SQLAlchemy com suporte assíncrono."""
    pass


# ---------------------------------------------------------------------------
# Model: ScrapingJob
# ---------------------------------------------------------------------------

class ScrapingJob(Base):
    """
    Representa um job de scraping agendado ou executado.

    Armazena todos os metadados do processo de coleta:
    URL alvo, configuração usada, status atual, tempos de execução
    e estatísticas do resultado.
    """

    __tablename__ = "scraping_jobs"

    # Chave primária
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # URL alvo do scraping
    url: Mapped[str] = mapped_column(String(2048), nullable=False, comment="URL alvo do scraping")

    # Nome da configuração de spider utilizada
    config_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Nome da configuração de spider utilizada"
    )

    # Status atual do job (usa Enum controlado)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.PENDING.value,
        comment="Status do job: pending, running, done, failed, cancelled",
    )

    # Timestamps do ciclo de vida
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Data/hora de criação do job",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Data/hora de início da execução"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Data/hora de conclusão ou falha"
    )

    # Estatísticas de resultado
    items_scraped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Quantidade de itens coletados"
    )

    # Mensagem de erro (preenchida apenas se status == failed)
    error_msg: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Mensagem de erro em caso de falha"
    )

    # Tipo do spider utilizado
    spider_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Tipo do spider (ex: generic, scrapy, playwright)"
    )

    # Controle de renderização JavaScript
    render_js: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Se deve renderizar JavaScript na página"
    )

    # Profundidade máxima de crawling
    crawl_depth: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Profundidade máxima de crawling (1 = apenas URL alvo)"
    )

    # Metadados adicionais em formato JSONB
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
        comment="Metadados adicionais em formato JSON (ex: headers, proxies, opções extras)",
    )

    # Relacionamento com itens coletados
    items: Mapped[list["ScrapedItem"]] = relationship(
        "ScrapedItem", back_populates="job", lazy="select", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScrapingJob id={self.id} status={self.status} url={self.url[:50]}>"


# ---------------------------------------------------------------------------
# Model: ScrapedItem
# ---------------------------------------------------------------------------

class ScrapedItem(Base):
    """
    Representa um item coletado durante um job de scraping.

    Armazena o conteúdo extraído (título, texto, dados brutos)
    com deduplicação via SHA-256 do conteúdo.
    """

    __tablename__ = "scraped_items"

    # Restrições de unicidade na tabela
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_scraped_items_content_hash"),
    )

    # Chave primária
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Chave estrangeira para o job
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scraping_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID do job que gerou este item",
    )

    # URL de onde o item foi coletado
    url: Mapped[str] = mapped_column(String(2048), nullable=False, comment="URL de origem do item")

    # Título da página/item
    title: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True, comment="Título extraído"
    )

    # Conteúdo textual completo
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Conteúdo textual extraído"
    )

    # Dados brutos em JSONB (todos os campos coletados)
    raw_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, comment="Dados brutos coletados em formato JSON"
    )

    # Hash SHA-256 para deduplicação (conteúdo normalizado)
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 do conteúdo para deduplicação",
    )

    # Timestamp da coleta
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Data/hora em que o item foi coletado",
    )

    # Domínio extraído da URL
    domain: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Domínio extraído da URL (ex: tjsp.jus.br)"
    )

    # Metadados adicionais em JSONB
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
        comment="Metadados adicionais (ex: tags, categorias, paginação)",
    )

    # Relacionamento com o job pai
    job: Mapped["ScrapingJob"] = relationship("ScrapingJob", back_populates="items")

    def __repr__(self) -> str:
        return f"<ScrapedItem id={self.id} job_id={self.job_id} domain={self.domain}>"

    @staticmethod
    def compute_hash(content: str) -> str:
        """
        Calcula o hash SHA-256 do conteúdo normalizado.

        Args:
            content: Texto do conteúdo a ser hasheado.

        Returns:
            String hexadecimal de 64 caracteres (SHA-256).
        """
        normalized = content.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Model: SpiderConfig
# ---------------------------------------------------------------------------

class SpiderConfig(Base):
    """
    Configuração de spider armazenada como YAML.

    Permite definir e reutilizar configurações de scraping
    sem precisar alterar o código-fonte.
    """

    __tablename__ = "spider_configs"

    # Chave primária
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Nome único da configuração
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, comment="Nome único da configuração"
    )

    # YAML da configuração completa
    config_yaml: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Configuração do spider em formato YAML"
    )

    # Tipo do spider
    spider_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Tipo do spider (ex: scrapy, playwright, requests)"
    )

    # Descrição legível da configuração
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Descrição humana da configuração"
    )

    # Se a configuração está ativa (não deletada logicamente)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Se a configuração está ativa"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Data/hora de criação",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Data/hora da última atualização",
    )

    # Relacionamento com jobs agendados
    scheduled_jobs: Mapped[list["ScheduledJob"]] = relationship(
        "ScheduledJob", back_populates="spider_config", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<SpiderConfig id={self.id} name={self.name} active={self.active}>"


# ---------------------------------------------------------------------------
# Model: ScheduledJob
# ---------------------------------------------------------------------------

class ScheduledJob(Base):
    """
    Job agendado com expressão CRON.

    Permite configurar execuções periódicas automáticas
    de um spider baseado em uma configuração existente.
    """

    __tablename__ = "scheduled_jobs"

    # Chave primária
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Nome do agendamento
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Nome descritivo do agendamento"
    )

    # Referência à configuração do spider
    spider_config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("spider_configs.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID da configuração do spider",
    )

    # Expressão CRON para agendamento
    cron_expression: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Expressão CRON do agendamento (ex: '0 */6 * * *' = a cada 6 horas)",
    )

    # Se o agendamento está habilitado
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Se o agendamento está habilitado"
    )

    # Última execução
    last_run: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Data/hora da última execução"
    )

    # Próxima execução calculada
    next_run: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Data/hora da próxima execução"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Data/hora de criação do agendamento",
    )

    # Relacionamento com a configuração do spider
    spider_config: Mapped["SpiderConfig"] = relationship(
        "SpiderConfig", back_populates="scheduled_jobs"
    )

    def __repr__(self) -> str:
        return f"<ScheduledJob id={self.id} name={self.name} enabled={self.enabled}>"


# ---------------------------------------------------------------------------
# Model: ProxyRecord
# ---------------------------------------------------------------------------

class ProxyRecord(Base):
    """
    Registro de proxy disponível para uso no scraping.

    Armazena informações de saúde e desempenho para rotação
    inteligente de proxies durante o processo de coleta.
    """

    __tablename__ = "proxy_records"

    # Chave primária
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Endereço do host
    host: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Host ou IP do proxy"
    )

    # Porta do proxy
    port: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Porta do proxy"
    )

    # Protocolo (http, https, socks5, etc.)
    protocol: Mapped[str] = mapped_column(
        String(20), nullable=False, default="http", comment="Protocolo do proxy (http, https, socks5)"
    )

    # País de origem (ISO 3166-1 alpha-2)
    country: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True, comment="Código do país de origem (ISO 3166-1 alpha-2, ex: BR)"
    )

    # Latência em milissegundos
    latency_ms: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Latência medida em milissegundos"
    )

    # Taxa de sucesso (0.0 a 1.0)
    success_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, comment="Taxa de sucesso (0.0 = 0%, 1.0 = 100%)"
    )

    # Última verificação de saúde
    last_checked: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Data/hora da última verificação de saúde"
    )

    # Se o proxy está ativo/disponível
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Se o proxy está ativo e disponível"
    )

    def __repr__(self) -> str:
        return f"<ProxyRecord id={self.id} {self.protocol}://{self.host}:{self.port} active={self.active}>"

    @property
    def url(self) -> str:
        """Retorna a URL completa do proxy."""
        return f"{self.protocol}://{self.host}:{self.port}"
