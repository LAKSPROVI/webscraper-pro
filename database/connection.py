"""
connection.py — Configuração da conexão assíncrona com PostgreSQL

Gerencia o engine SQLAlchemy com asyncpg, o pool de conexões,
a sessão assíncrona e as dependências para uso com FastAPI.

Variáveis de ambiente utilizadas:
    DATABASE_URL      — URL de conexão assíncrona (postgresql+asyncpg://...)
    DATABASE_SYNC_URL — URL de conexão síncrona (para Alembic)
    DB_POOL_SIZE      — Tamanho do pool (padrão: 10)
    DB_MAX_OVERFLOW   — Overflow máximo (padrão: 20)
    DB_POOL_TIMEOUT   — Timeout do pool em segundos (padrão: 30)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Leitura das variáveis de ambiente com valores padrão seguros
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://scraper:scraper_pass_change_me@localhost:5432/webscraper",
)

DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 min

# ---------------------------------------------------------------------------
# Criação do engine assíncrono com pool configurado
# ---------------------------------------------------------------------------

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    # Tamanho do pool de conexões mantidas abertas permanentemente
    pool_size=DB_POOL_SIZE,
    # Conexões extras permitidas além do pool_size
    max_overflow=DB_MAX_OVERFLOW,
    # Tempo máximo de espera por uma conexão disponível (segundos)
    pool_timeout=DB_POOL_TIMEOUT,
    # Tempo antes de reciclar uma conexão ociosa (segundos)
    pool_recycle=DB_POOL_RECYCLE,
    # Verifica conexões antes de entregar ao cliente
    pool_pre_ping=True,
    # Nível de log: INFO em produção, DEBUG para troubleshooting
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)

# ---------------------------------------------------------------------------
# Factory de sessão assíncrona
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # Não expira objetos automaticamente ao fechar a sessão
    expire_on_commit=False,
    # Não auto-flush antes de queries (controle manual para performance)
    autoflush=False,
    # Não auto-commit (transações explícitas)
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Dependency para FastAPI — get_db()
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injetável no FastAPI que fornece uma sessão de banco de dados.

    Abre uma sessão, injeta no endpoint e garante o fechamento ao final,
    fazendo rollback automático em caso de exceção.

    Uso:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Context manager para uso fora do FastAPI (workers, scripts)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager para obter uma sessão fora do contexto FastAPI.

    Uso:
        async with get_session() as session:
            result = await session.execute(select(ScrapingJob))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Inicialização do banco de dados (cria tabelas se não existirem)
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Cria todas as tabelas definidas nos models se ainda não existirem.

    ATENÇÃO: Em produção, prefira usar migrações Alembic em vez desta função.
    Use init_db() apenas em desenvolvimento ou testes.
    """
    logger.info("Inicializando banco de dados — criando tabelas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Banco de dados inicializado com sucesso.")


# ---------------------------------------------------------------------------
# Health check do banco de dados
# ---------------------------------------------------------------------------

async def check_db() -> dict[str, str | bool]:
    """
    Verifica a conectividade com o banco de dados.

    Executa uma query simples (SELECT 1) para confirmar que o banco
    está acessível e o pool de conexões está funcionando.

    Returns:
        Dict com 'status' ("ok" ou "error") e 'message' descritivo.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.scalar()
            if row == 1:
                return {"status": "ok", "message": "Banco de dados acessível"}
            return {"status": "error", "message": "Resposta inesperada do banco"}
    except Exception as exc:
        logger.error("Falha no health check do banco de dados: %s", exc)
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Encerramento do engine (para shutdown graceful)
# ---------------------------------------------------------------------------

async def close_db() -> None:
    """
    Fecha o engine e todas as conexões do pool de forma ordenada.

    Deve ser chamado no evento de shutdown da aplicação FastAPI.
    """
    logger.info("Fechando conexões do banco de dados...")
    await engine.dispose()
    logger.info("Conexões do banco de dados encerradas.")
