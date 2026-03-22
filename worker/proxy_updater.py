"""
proxy_updater.py — Módulo de atualização e validação do pool de proxies

Responsável por:
1. Buscar listas de proxies de múltiplas fontes públicas gratuitas
2. Validar cada proxy medindo latência real (GET httpbin.org/ip)
3. Salvar proxies válidos no PostgreSQL (tabela proxy_records)
4. Atualizar o SET Redis 'active_proxies' com os hosts funcionais

Usa httpx.AsyncClient para validação paralela com semáforo de concorrência.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://scraper:scraper_pass_change_me@localhost:5432/webscraper",
)
REDIS_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# Timeout para validação de cada proxy (segundos)
PROXY_VALIDATION_TIMEOUT: float = 5.0

# Latência máxima aceitável para considerar proxy válido (segundos)
PROXY_MAX_LATENCY: float = 3.0

# URL de teste para validação de proxies
VALIDATION_URL = "http://httpbin.org/ip"

# Concorrência máxima durante validação
MAX_CONCURRENT_VALIDATIONS = 50

# Fontes de proxies gratuitos
PROXY_SOURCES = {
    "proxyscrape": (
        "https://api.proxyscrape.com/v2/"
        "?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
    ),
    "clarketm": (
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"
    ),
    "speedx": (
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    ),
    "geonode": (
        "https://proxylist.geonode.com/api/proxy-list"
        "?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http"
    ),
}


class ProxyUpdater:
    """
    Gerencia o ciclo completo de atualização do pool de proxies.

    Fluxo:
        1. Busca proxies de múltiplas fontes
        2. Valida em paralelo (máx 50 simultâneos)
        3. Persiste no PostgreSQL
        4. Atualiza SET Redis
    """

    def __init__(
        self,
        database_url: str = DATABASE_URL,
        redis_url: str = REDIS_URL,
    ) -> None:
        """
        Inicializa o ProxyUpdater com conexões lazy.

        Args:
            database_url: URL de conexão PostgreSQL assíncrona
            redis_url:    URL de conexão Redis
        """
        self._database_url = database_url
        self._redis_url = redis_url

        # Engine e sessão SQLAlchemy (criados lazy)
        self._engine = create_async_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

        # Cliente Redis (criado lazy)
        self._redis: redis.Redis | None = None

    @property
    def redis_client(self) -> redis.Redis:
        """Retorna cliente Redis com conexão lazy."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._redis

    # ──────────────────────────────────────────────────────────────────────────
    # Busca de proxies das fontes externas
    # ──────────────────────────────────────────────────────────────────────────

    async def fetch_from_proxyscrape(self) -> list[str]:
        """
        Busca proxies da API ProxyScrape.

        Returns:
            Lista de strings 'host:porta' ou vazia em caso de falha.
        """
        return await self._fetch_text_list(PROXY_SOURCES["proxyscrape"], "proxyscrape")

    async def fetch_from_github_lists(self) -> list[str]:
        """
        Busca proxies das listas hospedadas no GitHub (clarketm e TheSpeedX).

        Returns:
            Lista combinada de proxies 'host:porta'.
        """
        resultados: list[str] = []

        for nome in ("clarketm", "speedx"):
            proxies = await self._fetch_text_list(PROXY_SOURCES[nome], nome)
            resultados.extend(proxies)
            logger.info("Fonte %s: %d proxies obtidos", nome, len(proxies))

        return resultados

    async def fetch_from_geonode(self) -> list[str]:
        """
        Busca proxies da API pública Geonode.

        Returns:
            Lista de strings 'host:porta'.
        """
        proxies: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(PROXY_SOURCES["geonode"])
                response.raise_for_status()
                data = response.json()

                for item in data.get("data", []):
                    host = item.get("ip", "").strip()
                    porta = item.get("port", "").strip()
                    if host and porta:
                        proxies.append(f"{host}:{porta}")

            logger.info("Fonte geonode: %d proxies obtidos", len(proxies))

        except Exception as exc:
            logger.warning("Falha ao buscar proxies da Geonode: %s", exc)

        return proxies

    async def _fetch_text_list(self, url: str, nome_fonte: str) -> list[str]:
        """
        Busca uma lista de proxies em formato texto (uma por linha).

        Args:
            url:        URL da fonte
            nome_fonte: Nome descritivo para logging

        Returns:
            Lista de strings 'host:porta'.
        """
        proxies: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                for linha in response.text.splitlines():
                    linha = linha.strip()
                    # Valida formato host:porta superficialmente
                    if ":" in linha and not linha.startswith("#"):
                        partes = linha.split(":")
                        if len(partes) == 2 and partes[1].isdigit():
                            proxies.append(linha)

            logger.info("Fonte %s: %d proxies obtidos de %s", nome_fonte, len(proxies), url)

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Erro HTTP ao buscar proxies de %s: status=%d",
                nome_fonte,
                exc.response.status_code,
            )
        except Exception as exc:
            logger.warning("Falha ao buscar proxies de %s: %s", nome_fonte, exc)

        return proxies

    # ──────────────────────────────────────────────────────────────────────────
    # Validação de proxies
    # ──────────────────────────────────────────────────────────────────────────

    async def validate_proxy(
        self,
        host: str,
        port: int,
        protocol: str = "http",
    ) -> dict[str, Any]:
        """
        Valida um proxy fazendo GET para httpbin.org/ip e mede latência.

        Args:
            host:     Endereço IP ou hostname do proxy
            port:     Porta do proxy
            protocol: Protocolo ('http', 'https', 'socks5')

        Returns:
            Dict com chaves:
              - 'valid':      bool — se o proxy está funcional
              - 'latency_ms': float — latência em ms (0 se inválido)
              - 'host':       str
              - 'port':       int
              - 'protocol':   str
        """
        proxy_url = f"{protocol}://{host}:{port}"
        resultado: dict[str, Any] = {
            "valid": False,
            "latency_ms": 0.0,
            "host": host,
            "port": port,
            "protocol": protocol,
        }

        try:
            inicio = time.monotonic()
            async with httpx.AsyncClient(
                proxies={"http://": proxy_url, "https://": proxy_url},
                timeout=PROXY_VALIDATION_TIMEOUT,
                follow_redirects=False,
            ) as client:
                response = await client.get(VALIDATION_URL)
                latencia = time.monotonic() - inicio

                if response.status_code == 200 and latencia <= PROXY_MAX_LATENCY:
                    resultado["valid"] = True
                    resultado["latency_ms"] = round(latencia * 1000, 2)

        except Exception:
            # Qualquer falha → proxy inválido (timeout, connection refused, etc.)
            pass

        return resultado

    async def validate_many(self, proxies: list[str]) -> list[dict[str, Any]]:
        """
        Valida múltiplos proxies em paralelo com controle de concorrência.

        Args:
            proxies: Lista de strings 'host:porta'

        Returns:
            Lista de dicts dos proxies válidos (com latência abaixo do limite).
        """
        semaforo = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)
        validos: list[dict[str, Any]] = []

        async def _validar_com_semaforo(proxy_str: str) -> dict[str, Any] | None:
            async with semaforo:
                if ":" not in proxy_str:
                    return None
                partes = proxy_str.split(":")
                if len(partes) != 2 or not partes[1].isdigit():
                    return None
                host = partes[0].strip()
                port = int(partes[1].strip())
                resultado = await self.validate_proxy(host, port)
                return resultado if resultado["valid"] else None

        logger.info("Validando %d proxies com max %d simultâneos...", len(proxies), MAX_CONCURRENT_VALIDATIONS)

        tarefas = [_validar_com_semaforo(p) for p in proxies]
        resultados = await asyncio.gather(*tarefas, return_exceptions=False)

        for r in resultados:
            if r is not None:
                validos.append(r)

        logger.info("Validação concluída: %d válidos de %d testados", len(validos), len(proxies))
        return validos

    # ──────────────────────────────────────────────────────────────────────────
    # Persistência no banco de dados
    # ──────────────────────────────────────────────────────────────────────────

    async def save_to_db(self, valid_proxies: list[dict[str, Any]]) -> int:
        """
        Salva proxies válidos no PostgreSQL com upsert (host+port+protocol).

        Atualiza latência e marca como ativo se o proxy já existir.

        Args:
            valid_proxies: Lista de dicts retornados por validate_proxy()

        Returns:
            Quantidade de registros inseridos/atualizados.
        """
        if not valid_proxies:
            return 0

        # Importação local para evitar dependência circular durante inicialização
        from database.models import ProxyRecord  # noqa: PLC0415

        count = 0

        async with self._session_factory() as session:
            try:
                agora = datetime.now(timezone.utc)

                for proxy_data in valid_proxies:
                    # Upsert: insere se não existir, atualiza se existir
                    stmt = (
                        pg_insert(ProxyRecord)
                        .values(
                            host=proxy_data["host"],
                            port=proxy_data["port"],
                            protocol=proxy_data["protocol"],
                            latency_ms=proxy_data["latency_ms"],
                            success_rate=1.0,
                            last_checked=agora,
                            active=True,
                        )
                        .on_conflict_do_update(
                            index_elements=["host", "port", "protocol"],
                            set_={
                                "latency_ms": proxy_data["latency_ms"],
                                "last_checked": agora,
                                "active": True,
                                "success_rate": ProxyRecord.success_rate * 0.8 + 0.2,
                            },
                        )
                    )
                    await session.execute(stmt)
                    count += 1

                await session.commit()
                logger.info("Banco atualizado: %d proxies válidos salvos", count)

            except Exception as exc:
                await session.rollback()
                logger.error("Erro ao salvar proxies no banco: %s", exc)
                raise

        return count

    # ──────────────────────────────────────────────────────────────────────────
    # Atualização do pool Redis
    # ──────────────────────────────────────────────────────────────────────────

    def update_redis_pool(self, valid_proxies: list[dict[str, Any]]) -> None:
        """
        Atualiza o SET Redis 'active_proxies' com os proxies funcionais.

        Substitui completamente o conjunto anterior (pipeline atômico).

        Args:
            valid_proxies: Lista de dicts retornados por validate_proxy()
        """
        if not valid_proxies:
            logger.warning("Nenhum proxy válido para atualizar no Redis")
            return

        try:
            pipe = self.redis_client.pipeline()

            # Remove os conjuntos antigos e recria ambos (compatibilidade)
            pipe.delete("active_proxies")
            pipe.delete("proxies:pool")

            for proxy_data in valid_proxies:
                proxy_str = f"{proxy_data['protocol']}://{proxy_data['host']}:{proxy_data['port']}"
                pipe.sadd("active_proxies", proxy_str)
                pipe.sadd("proxies:pool", proxy_str)

            # Expira em 2 horas (para garantir refresh)
            pipe.expire("active_proxies", 7200)
            pipe.expire("proxies:pool", 7200)

            pipe.execute()

            logger.info(
                "Redis atualizado: %d proxies nos SETs 'active_proxies' e 'proxies:pool'",
                len(valid_proxies),
            )

        except redis.RedisError as exc:
            logger.error("Erro ao atualizar pool Redis de proxies: %s", exc)
            raise

    # ──────────────────────────────────────────────────────────────────────────
    # Verificação de saúde dos proxies existentes
    # ──────────────────────────────────────────────────────────────────────────

    async def health_check_existing(self) -> dict[str, int]:
        """
        Re-verifica todos os proxies ativos no banco e desativa os ruins.

        Desativa proxies que:
        - Falharam na verificação atual (atualiza success_rate negativamente)
        - Têm success_rate < 50% após a verificação

        Returns:
            Dict com contagens: {'verificados': N, 'ativos': N, 'desativados': N}
        """
        from database.models import ProxyRecord  # noqa: PLC0415

        estatisticas = {"verificados": 0, "ativos": 0, "desativados": 0}

        async with self._session_factory() as session:
            try:
                # Busca todos os proxies ativos
                result = await session.execute(
                    select(ProxyRecord).where(ProxyRecord.active == True)  # noqa: E712
                )
                proxies_ativos = result.scalars().all()

                if not proxies_ativos:
                    logger.info("Nenhum proxy ativo para verificar")
                    return estatisticas

                logger.info("Verificando saúde de %d proxies ativos...", len(proxies_ativos))

                # Monta lista para validação em batch
                lista_validar = [
                    f"{p.host}:{p.port}" for p in proxies_ativos
                ]

                resultados = await self.validate_many(lista_validar)
                mapa_validos: dict[str, bool] = {
                    f"{r['host']}:{r['port']}": True for r in resultados
                }

                agora = datetime.now(timezone.utc)

                for proxy in proxies_ativos:
                    chave = f"{proxy.host}:{proxy.port}"
                    passou = mapa_validos.get(chave, False)
                    estatisticas["verificados"] += 1

                    if passou:
                        # Aumenta ligeiramente o success_rate
                        proxy.success_rate = min(1.0, proxy.success_rate * 0.9 + 0.1)
                        proxy.last_checked = agora
                        estatisticas["ativos"] += 1
                    else:
                        # Penaliza o proxy com falha
                        proxy.success_rate = max(0.0, proxy.success_rate * 0.7)
                        proxy.last_checked = agora

                        # Desativa se taxa de sucesso caiu abaixo de 50%
                        if proxy.success_rate < 0.5:
                            proxy.active = False
                            estatisticas["desativados"] += 1
                        else:
                            estatisticas["ativos"] += 1

                    session.add(proxy)

                await session.commit()

                logger.info(
                    "Health check concluído: %d verificados, %d ativos, %d desativados",
                    estatisticas["verificados"],
                    estatisticas["ativos"],
                    estatisticas["desativados"],
                )

            except Exception as exc:
                await session.rollback()
                logger.error("Erro no health check de proxies: %s", exc)
                raise

        return estatisticas

    # ──────────────────────────────────────────────────────────────────────────
    # Método principal: execução completa do ciclo de atualização
    # ──────────────────────────────────────────────────────────────────────────

    async def run_full_update(self) -> dict[str, int]:
        """
        Executa o ciclo completo de atualização do pool de proxies.

        Fluxo:
            1. Busca proxies de todas as fontes
            2. Remove duplicatas
            3. Valida em paralelo
            4. Salva no PostgreSQL
            5. Atualiza Redis

        Returns:
            Dict com estatísticas: {'total_coletados': N, 'validos': N, 'salvos': N}
        """
        logger.info("Iniciando atualização completa do pool de proxies...")

        # Busca de todas as fontes em paralelo
        fontes_resultados = await asyncio.gather(
            self.fetch_from_proxyscrape(),
            self.fetch_from_github_lists(),
            self.fetch_from_geonode(),
            return_exceptions=True,
        )

        todos_proxies: list[str] = []
        for resultado in fontes_resultados:
            if isinstance(resultado, list):
                todos_proxies.extend(resultado)
            elif isinstance(resultado, Exception):
                logger.warning("Fonte falhou durante coleta: %s", resultado)

        # Remove duplicatas mantendo ordem
        vistos: set[str] = set()
        proxies_unicos: list[str] = []
        for p in todos_proxies:
            if p not in vistos:
                vistos.add(p)
                proxies_unicos.append(p)

        logger.info(
            "Total coletado: %d proxies (%d únicos)",
            len(todos_proxies),
            len(proxies_unicos),
        )

        # Validação em paralelo
        validos = await self.validate_many(proxies_unicos)

        logger.info(
            "%d proxies válidos (<%.1fs latência) encontrados de %d testados",
            len(validos),
            PROXY_MAX_LATENCY,
            len(proxies_unicos),
        )

        # Persistência
        salvos = await self.save_to_db(validos)

        # Atualização Redis
        if validos:
            self.update_redis_pool(validos)

        return {
            "total_coletados": len(todos_proxies),
            "unicos": len(proxies_unicos),
            "validos": len(validos),
            "salvos": salvos,
        }

    async def close(self) -> None:
        """Fecha conexões de forma ordenada."""
        await self._engine.dispose()
        if self._redis:
            self._redis.close()
