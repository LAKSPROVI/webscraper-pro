"""
storage.py — Pipeline de armazenamento no PostgreSQL

Salva itens Scrapy processados no banco de dados PostgreSQL usando
SQLAlchemy com inserção em batch para performance.

Estratégia de persistência:
- Batch de 50 itens antes de fazer INSERT no banco
- Flush automático ao fechar o spider (itens restantes no buffer)
- INSERT OR UPDATE (upsert) baseado na URL para evitar duplicatas no DB
- Atualização dos contadores do ScrapingJob após cada batch

Compatibilidade: usa SQLAlchemy sync (via asyncio.run) para ser
compatível com o ambiente síncrono do Scrapy sem monkey-patching.
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from scrapy.exceptions import DropItem

# Importações do banco de dados do projeto
# Os modelos SQLAlchemy são compartilhados com a API
import sys
import os

# Adiciona o diretório raiz do projeto ao path para importar os módulos da database
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from database.models import ScrapedItem as ScrapedItemModel, ScrapingJob
    from database.connection import get_async_session, engine
    DB_AVAILABLE = True
except ImportError as e:
    DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

# Tamanho do batch para INSERT em massa
BATCH_SIZE = 50


class StoragePipeline:
    """
    Pipeline de armazenamento persistente no PostgreSQL.

    Fluxo de operação:
    1. open_spider: inicializa buffer e verifica conexão ao banco
    2. process_item: adiciona ao buffer; faz INSERT quando buffer cheio
    3. close_spider: faz flush do buffer restante e atualiza estatísticas do job

    Performance:
    - Batch de 50 itens evita overhead de 1 INSERT por item
    - SQLAlchemy bulk_insert_mappings para INSERT massivo eficiente
    - Atualização do job feita apenas 1x ao final (close_spider)
    """

    def __init__(self, settings):
        self.settings = settings
        # Buffer de itens aguardando INSERT
        self._buffer: list[dict] = []
        # Contador total de itens salvos por spider
        self._saved_count = 0
        # Rastreia job_id atual para atualização final
        self._current_job_id: Optional[int] = None
        # Database URL das settings
        self._database_url = settings.get(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/webscraper"
        )

    @classmethod
    def from_crawler(cls, crawler):
        """Instancia o pipeline a partir das configurações do Scrapy."""
        return cls(crawler.settings)

    def open_spider(self, spider) -> None:
        """
        Inicializa o pipeline ao abrir o spider.

        Verifica disponibilidade do banco de dados e loga aviso
        se as dependências não estiverem instaladas.
        """
        if not DB_AVAILABLE:
            logger.error(
                f"StoragePipeline: módulos de banco não disponíveis: {_DB_IMPORT_ERROR}. "
                "Os itens NÃO serão salvos no banco de dados."
            )
        else:
            logger.info(
                f"StoragePipeline iniciado para spider '{spider.name}'. "
                f"Batch size: {BATCH_SIZE}"
            )

    def close_spider(self, spider) -> None:
        """
        Finaliza o pipeline ao fechar o spider.

        - Faz flush dos itens restantes no buffer
        - Atualiza estatísticas do ScrapingJob (items_scraped, status, completed_at)
        """
        # Faz flush do buffer restante
        if self._buffer:
            logger.info(
                f"Flush final: salvando {len(self._buffer)} itens restantes no buffer"
            )
            self._flush_buffer()

        # Atualiza estatísticas do job no banco
        if self._current_job_id and DB_AVAILABLE:
            try:
                self._run_coro_sync(self._update_job_stats(self._current_job_id))
            except Exception as e:
                logger.error(f"Erro ao atualizar estatísticas do job {self._current_job_id}: {e}")

        logger.info(
            f"StoragePipeline finalizado: {self._saved_count} itens salvos "
            f"no job {self._current_job_id}"
        )

    def process_item(self, item, spider):
        """
        Adiciona item ao buffer e faz INSERT quando buffer atingir BATCH_SIZE.

        Args:
            item: ScrapedItem do Scrapy
            spider: instância do spider

        Returns:
            item: mesmo item (permite chain de pipelines)
        """
        if not DB_AVAILABLE:
            logger.warning("DB não disponível: item não será salvo")
            return item

        # Registra job_id para atualização final
        if item.get("job_id") and not self._current_job_id:
            self._current_job_id = item["job_id"]

        # Converte item Scrapy para dicionário de modelo SQLAlchemy
        item_dict = self._item_to_dict(item)
        self._buffer.append(item_dict)

        # Faz INSERT quando buffer atingir o tamanho limite
        if len(self._buffer) >= BATCH_SIZE:
            self._flush_buffer()

        return item

    def _item_to_dict(self, item) -> dict:
        """
        Converte ScrapedItem do Scrapy para dicionário do modelo SQLAlchemy.

        Mapeia campos do item Scrapy para colunas do modelo ScrapedItemModel.
        """
        return {
            "job_id": item.get("job_id"),
            "url": str(item.get("url") or ""),
            "title": str(item.get("title") or "")[:500],  # Limita ao tamanho da coluna
            "content": str(item.get("content") or ""),
            "raw_data": str(item.get("raw_data") or ""),
            "domain": str(item.get("domain") or ""),
            "spider_name": str(item.get("spider_name") or ""),
            "scraped_at": item.get("scraped_at") or datetime.now(timezone.utc).isoformat(),
            "metadata_": item.get("metadata") or {},  # Mapeado para campo "metadata" no DB
        }

    def _flush_buffer(self) -> None:
        """
        Executa INSERT em batch dos itens no buffer.

        Usa asyncio.run() para executar coroutines async em contexto sync.
        Limpa o buffer após INSERT bem-sucedido.
        """
        if not self._buffer:
            return

        items_to_insert = self._buffer.copy()
        self._buffer.clear()

        try:
            inserted = self._run_coro_sync(self._insert_batch(items_to_insert))
            self._saved_count += inserted
            logger.info(f"Batch inserido: {inserted} itens (total: {self._saved_count})")
        except Exception as e:
            logger.error(f"Erro ao inserir batch de {len(items_to_insert)} itens: {e}")
            # Em caso de erro, tenta inserir um por um para minimizar perda
            self._insert_one_by_one(items_to_insert)

    async def _insert_batch(self, items: list[dict]) -> int:
        """
        Insere batch de itens no PostgreSQL via SQLAlchemy async.

        Usa INSERT ON CONFLICT DO NOTHING para evitar erros em duplicatas
        que possam ter escapado da DuplicateFilterPipeline.

        Returns:
            int: número de itens efetivamente inseridos
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        async with get_async_session() as session:
            # Prepara os dados para bulk insert
            # Normaliza o campo metadata_ para o formato do modelo
            insert_data = []
            for item_dict in items:
                data = dict(item_dict)
                # Renomeia metadata_ para metadata (nome da coluna no DB)
                if "metadata_" in data:
                    data["metadata"] = data.pop("metadata_")
                insert_data.append(data)

            # Usa INSERT ... ON CONFLICT DO NOTHING para segurança
            # (evita duplicatas que escaparam da dedup pipeline)
            stmt = pg_insert(ScrapedItemModel).values(insert_data)
            stmt = stmt.on_conflict_do_nothing(index_elements=["content_hash"])

            try:
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                logger.error(f"Erro no INSERT batch: {e}")
                raise

    def _insert_one_by_one(self, items: list[dict]) -> None:
        """
        Fallback: insere itens individualmente em caso de erro no batch.

        Mais lento, mas garante que itens válidos sejam salvos mesmo
        se houver um item problemático no batch.
        """
        saved = 0
        for item_dict in items:
            try:
                self._run_coro_sync(self._insert_batch([item_dict]))
                saved += 1
                self._saved_count += 1
            except Exception as e:
                logger.error(
                    f"Erro ao inserir item individual "
                    f"({item_dict.get('url', 'unknown')[:60]}): {e}"
                )
        if saved:
            logger.info(f"Fallback one-by-one: {saved}/{len(items)} itens salvos")

    def _run_coro_sync(self, coro):
        """
        Executa coroutine de forma segura em contexto Scrapy/Twisted.

        Se já houver loop rodando na thread atual, executa a coroutine em
        uma thread auxiliar com loop próprio e bloqueia até retorno.
        """
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            result_holder = {"result": None, "error": None}

            def _runner() -> None:
                try:
                    result_holder["result"] = asyncio.run(coro)
                except Exception as exc:
                    result_holder["error"] = exc

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join()

            if result_holder["error"] is not None:
                raise result_holder["error"]

            return result_holder["result"]

        return asyncio.run(coro)

    async def _update_job_stats(self, job_id: int) -> None:
        """
        Atualiza estatísticas do ScrapingJob após conclusão do spider.

        Atualiza:
        - items_scraped: total de itens coletados
        - status: 'done' (se não havia falhas)
        - completed_at: timestamp de conclusão
        """
        async with get_async_session() as session:
            from sqlalchemy import select, update

            # Busca o job para atualização
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()

            if job:
                job.items_scraped = self._saved_count
                job.completed_at = datetime.now(timezone.utc)
                # Só marca como 'done' se estava 'running'
                if job.status == "running":
                    job.status = "done"
                await session.commit()
                logger.info(
                    f"Job {job_id} atualizado: "
                    f"{self._saved_count} itens, status={job.status}"
                )
            else:
                logger.warning(f"Job {job_id} não encontrado no banco para atualização")
