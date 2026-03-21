"""
env.py — Configuração do ambiente Alembic para migrações assíncronas

Suporta dois modos de execução:
1. offline: Gera SQL sem conectar ao banco (útil para revisão)
2. online:  Conecta ao banco e executa as migrações (modo padrão)

Variáveis de ambiente utilizadas:
    DATABASE_SYNC_URL — URL de conexão síncrona para o Alembic
                        (ex: postgresql://user:pass@host:5432/db)

Comandos úteis:
    # Aplicar todas as migrações pendentes
    alembic upgrade head

    # Reverter a última migração
    alembic downgrade -1

    # Gerar nova migração por autogenerate
    alembic revision --autogenerate -m "adiciona coluna X"

    # Ver histórico de migrações
    alembic history

    # Ver versão atual aplicada
    alembic current
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Importa os models para que o Alembic detecte alterações automaticamente
# ---------------------------------------------------------------------------
# IMPORTANTE: todos os models devem ser importados aqui para que o
# autogenerate do Alembic consiga detectar novas tabelas/colunas.
from database.models import Base  # noqa: F401 — necessário para autogenerate

# ---------------------------------------------------------------------------
# Configuração do Alembic (lida do alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Configura o logging usando as definições do alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata dos models para autogenerate de migrações
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# URL de conexão — prioriza variável de ambiente sobre alembic.ini
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    """
    Retorna a URL de conexão síncrona para o Alembic.

    Prioridade:
    1. Variável de ambiente DATABASE_SYNC_URL
    2. Variável de ambiente DATABASE_URL (converte asyncpg para psycopg2)
    3. Valor definido no alembic.ini
    """
    # Tenta DATABASE_SYNC_URL primeiro (URL síncrona dedicada)
    sync_url = os.getenv("DATABASE_SYNC_URL")
    if sync_url:
        return sync_url

    # Tenta converter DATABASE_URL assíncrona para síncrona
    async_url = os.getenv("DATABASE_URL")
    if async_url:
        # Converte postgresql+asyncpg:// para postgresql://
        return async_url.replace("postgresql+asyncpg://", "postgresql://")

    # Fallback para o valor do alembic.ini
    return config.get_main_option("sqlalchemy.url", "")


# ---------------------------------------------------------------------------
# Modo offline — Gera SQL sem conectar ao banco
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Executa migrações em modo offline (sem conexão ao banco).

    Útil para gerar scripts SQL para revisão antes de aplicar
    ou para ambientes onde a conexão direta não é permitida.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compara tipos para detectar mudanças de tipo de coluna
        compare_type=True,
        # Compara valores padrão das colunas
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Modo online — Conecta ao banco e executa migrações
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """
    Executa migrações em modo online (com conexão ao banco).

    Conecta ao PostgreSQL usando psycopg2 (driver síncrono)
    e aplica as migrações em uma transação.
    """
    # Sobrescreve a URL do alembic.ini com a variável de ambiente
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Sem pool para migrações (execução única)
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Compara tipos para detectar mudanças de tipo de coluna
            compare_type=True,
            # Compara valores padrão das colunas
            compare_server_default=True,
            # Inclui schemas além do public se necessário
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Ponto de entrada — seleciona o modo correto automaticamente
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
