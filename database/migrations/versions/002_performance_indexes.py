"""002_performance_indexes.py — índices adicionais de performance.

Revision ID: 002
Revises: 001
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Jobs: consultas por status + ordenação temporal.
    op.create_index(
        "ix_scraping_jobs_status_created_at",
        "scraping_jobs",
        ["status", "created_at"],
        unique=False,
    )

    # Jobs: agregações por tipo + status para dashboards.
    op.create_index(
        "ix_scraping_jobs_spider_type_status",
        "scraping_jobs",
        ["spider_type", "status"],
        unique=False,
    )

    # Itens: busca por job + data.
    op.create_index(
        "ix_scraped_items_job_id_scraped_at",
        "scraped_items",
        ["job_id", "scraped_at"],
        unique=False,
    )

    # Itens: filtro por domínio + data para relatórios.
    op.create_index(
        "ix_scraped_items_domain_scraped_at",
        "scraped_items",
        ["domain", "scraped_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scraped_items_domain_scraped_at", table_name="scraped_items")
    op.drop_index("ix_scraped_items_job_id_scraped_at", table_name="scraped_items")
    op.drop_index("ix_scraping_jobs_spider_type_status", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_status_created_at", table_name="scraping_jobs")
