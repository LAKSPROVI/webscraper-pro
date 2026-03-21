"""001_initial.py — Migration inicial: cria todas as tabelas e índices

Revision ID: 001
Revises: (nenhuma — é a primeira migration)
Create Date: 2026-03-21

Esta migration cria as seguintes tabelas:
    - scraping_jobs      — Jobs de scraping
    - scraped_items      — Itens coletados com deduplicação SHA-256
    - spider_configs     — Configurações de spiders em YAML
    - scheduled_jobs     — Agendamentos CRON
    - proxy_records      — Pool de proxies com saúde monitorada

Índices criados:
    - scraped_items.content_hash (UNIQUE)
    - scraped_items.domain
    - scraped_items.scraped_at
    - scraped_items.raw_data (GIN — busca JSONB)
    - scraping_jobs.status
    - scraping_jobs.created_at
    - proxy_records (host, port, protocol) — UNIQUE para upsert
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Metadados da revisão (gerenciados pelo Alembic)
# ---------------------------------------------------------------------------
revision: str = "001"
down_revision: str | None = None  # Primeira migration — sem dependência
branch_labels: str | None = None
depends_on: str | None = None


# ---------------------------------------------------------------------------
# upgrade() — Cria todas as tabelas e índices
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """Cria as tabelas do WebScraper com todos os índices necessários."""

    # -------------------------------------------------------------------------
    # Tabela: scraping_jobs
    # -------------------------------------------------------------------------
    op.create_table(
        "scraping_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("config_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="Status do job: pending, running, done, failed, cancelled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_scraped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("spider_type", sa.String(length=100), nullable=True),
        sa.Column("render_js", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("crawl_depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Metadados adicionais do job em formato JSON",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Índice em status (filtragem por jobs pendentes/rodando)
    op.create_index(
        "ix_scraping_jobs_status",
        "scraping_jobs",
        ["status"],
        unique=False,
    )

    # Índice em created_at (ordenação e filtragem temporal)
    op.create_index(
        "ix_scraping_jobs_created_at",
        "scraping_jobs",
        ["created_at"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # Tabela: spider_configs
    # -------------------------------------------------------------------------
    op.create_table(
        "spider_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config_yaml", sa.Text(), nullable=False),
        sa.Column("spider_type", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_spider_configs_name"),
    )

    # Índice no nome para buscas rápidas
    op.create_index(
        "ix_spider_configs_name",
        "spider_configs",
        ["name"],
        unique=True,
    )

    # -------------------------------------------------------------------------
    # Tabela: scheduled_jobs
    # -------------------------------------------------------------------------
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("spider_config_id", sa.Integer(), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["spider_config_id"],
            ["spider_configs.id"],
            ondelete="CASCADE",
            name="fk_scheduled_jobs_spider_config",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Índice em next_run para o scheduler verificar jobs devidos
    op.create_index(
        "ix_scheduled_jobs_next_run",
        "scheduled_jobs",
        ["next_run"],
        unique=False,
    )

    # Índice composto para listar jobs habilitados com próxima execução
    op.create_index(
        "ix_scheduled_jobs_enabled_next_run",
        "scheduled_jobs",
        ["enabled", "next_run"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # Tabela: scraped_items
    # -------------------------------------------------------------------------
    op.create_table(
        "scraped_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Dados brutos coletados em formato JSON",
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 do conteúdo para deduplicação",
        ),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Metadados adicionais do item em formato JSON",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["scraping_jobs.id"],
            ondelete="CASCADE",
            name="fk_scraped_items_job",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_scraped_items_content_hash"),
    )

    # Índice UNIQUE em content_hash (deduplicação — mais crítico)
    op.create_index(
        "ix_scraped_items_content_hash",
        "scraped_items",
        ["content_hash"],
        unique=True,
    )

    # Índice em domain (filtragem por site de origem)
    op.create_index(
        "ix_scraped_items_domain",
        "scraped_items",
        ["domain"],
        unique=False,
    )

    # Índice em scraped_at (consultas temporais)
    op.create_index(
        "ix_scraped_items_scraped_at",
        "scraped_items",
        ["scraped_at"],
        unique=False,
    )

    # Índice em job_id (join com scraping_jobs)
    op.create_index(
        "ix_scraped_items_job_id",
        "scraped_items",
        ["job_id"],
        unique=False,
    )

    # GIN index em raw_data (JSONB) — permite busca eficiente dentro do JSON
    # Ex: WHERE raw_data @> '{"tipo": "acórdão"}'
    op.create_index(
        "ix_scraped_items_raw_data_gin",
        "scraped_items",
        ["raw_data"],
        unique=False,
        postgresql_using="gin",
    )

    # -------------------------------------------------------------------------
    # Tabela: proxy_records
    # -------------------------------------------------------------------------
    op.create_table(
        "proxy_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.SmallInteger(), nullable=False),
        sa.Column("protocol", sa.String(length=20), nullable=False, server_default="http"),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        # Índice único composto para upsert (host + port + protocol)
        sa.UniqueConstraint(
            "host", "port", "protocol",
            name="uq_proxy_records_host_port_protocol",
        ),
    )

    # Índice composto para busca de proxies ativos com boa taxa de sucesso
    op.create_index(
        "ix_proxy_records_active_success",
        "proxy_records",
        ["active", "success_rate"],
        unique=False,
    )


# ---------------------------------------------------------------------------
# downgrade() — Remove todas as tabelas e índices (ordem inversa)
# ---------------------------------------------------------------------------

def downgrade() -> None:
    """Remove todas as tabelas criadas nesta migration (ordem inversa das FKs)."""

    # Remove tabelas dependentes primeiro (FK constraints)
    op.drop_index("ix_scraped_items_raw_data_gin", table_name="scraped_items")
    op.drop_index("ix_scraped_items_job_id", table_name="scraped_items")
    op.drop_index("ix_scraped_items_scraped_at", table_name="scraped_items")
    op.drop_index("ix_scraped_items_domain", table_name="scraped_items")
    op.drop_index("ix_scraped_items_content_hash", table_name="scraped_items")
    op.drop_table("scraped_items")

    op.drop_index("ix_scheduled_jobs_enabled_next_run", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_next_run", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")

    op.drop_index("ix_scraping_jobs_created_at", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_status", table_name="scraping_jobs")
    op.drop_table("scraping_jobs")

    op.drop_index("ix_spider_configs_name", table_name="spider_configs")
    op.drop_table("spider_configs")

    op.drop_index("ix_proxy_records_active_success", table_name="proxy_records")
    op.drop_table("proxy_records")
