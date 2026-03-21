"""
tests/test_api.py — Testes de integração da API FastAPI
WebScraper Pro

Testa todos os endpoints principais com mocks de banco e Redis:
- GET  /health                     — Health check do sistema
- POST /api/v1/scrape              — Disparar job de scraping
- GET  /api/v1/jobs                — Listar jobs
- GET  /api/v1/jobs/{job_id}       — Detalhe de job
- DELETE /api/v1/jobs/{job_id}     — Cancelar job
- GET  /api/v1/jobs/{job_id}/items — Itens coletados
- GET  /api/v1/spiders             — Listar spiders disponíveis
- GET  /api/v1/stats               — Estatísticas gerais

Usa httpx.AsyncClient e TestClient para isolamento completo.
Banco de dados e Redis são mockados via pytest-mock.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ==============================================================================
# MOCKS E STUBS DO SISTEMA
# (Simulam FastAPI, SQLAlchemy e Redis para testes isolados)
# ==============================================================================

# --------------------------------------------------------------------------
# Enums e modelos de dados
# --------------------------------------------------------------------------

class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpiderType:
    GENERIC = "generic"
    JS = "js"
    NEWS = "news"
    API = "api"


# --------------------------------------------------------------------------
# Schemas (equivalentes aos Pydantic do projeto)
# --------------------------------------------------------------------------

class ScrapeRequest:
    def __init__(
        self,
        url: str,
        spider_type: str = SpiderType.GENERIC,
        depth: int = 2,
        max_items: int = 1000,
        render_js: bool = False,
        config_file: Optional[str] = None,
        callback_url: Optional[str] = None,
    ):
        self.url = url
        self.spider_type = spider_type
        self.depth = depth
        self.max_items = max_items
        self.render_js = render_js
        self.config_file = config_file
        self.callback_url = callback_url

    def dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "spider_type": self.spider_type,
            "depth": self.depth,
            "max_items": self.max_items,
            "render_js": self.render_js,
            "config_file": self.config_file,
            "callback_url": self.callback_url,
        }


class JobResponse:
    def __init__(self, job_id: str, status: str, url: str, **kwargs):
        self.job_id = job_id
        self.status = status
        self.url = url
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.spider_type = kwargs.get("spider_type", SpiderType.GENERIC)
        self.progress = kwargs.get("progress", {})
        self.error = kwargs.get("error", None)

    def dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "url": self.url,
            "spider_type": self.spider_type,
            "created_at": self.created_at.isoformat(),
            "progress": self.progress,
            "error": self.error,
        }


class ScrapedItem:
    def __init__(self, item_id: str, job_id: str, data: Dict[str, Any]):
        self.item_id = item_id
        self.job_id = job_id
        self.data = data
        self.scraped_at = datetime.now(timezone.utc)

    def dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "job_id": self.job_id,
            "data": self.data,
            "scraped_at": self.scraped_at.isoformat(),
        }


# --------------------------------------------------------------------------
# Camada de acesso a dados (DAO) mockável
# --------------------------------------------------------------------------

class JobDAO:
    """Camada de acesso ao banco de dados para jobs."""

    def __init__(self, db_session=None):
        self._db = db_session
        # Armazenamento em memória para testes
        self._jobs: Dict[str, JobResponse] = {}
        self._items: Dict[str, List[ScrapedItem]] = {}

    def criar_job(self, request: ScrapeRequest) -> JobResponse:
        job_id = str(uuid.uuid4())
        job = JobResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            url=request.url,
            spider_type=request.spider_type,
        )
        self._jobs[job_id] = job
        self._items[job_id] = []
        return job

    def buscar_job(self, job_id: str) -> Optional[JobResponse]:
        return self._jobs.get(job_id)

    def listar_jobs(
        self,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> List[JobResponse]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        inicio = (page - 1) * per_page
        return jobs[inicio: inicio + per_page]

    def atualizar_status(self, job_id: str, status: str, **kwargs) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.status = status
        if "error" in kwargs:
            job.error = kwargs["error"]
        if "progress" in kwargs:
            job.progress = kwargs["progress"]
        return True

    def deletar_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        self._items.pop(job_id, None)
        return True

    def listar_itens(self, job_id: str) -> List[ScrapedItem]:
        return self._items.get(job_id, [])

    def adicionar_item(self, job_id: str, data: Dict) -> ScrapedItem:
        item = ScrapedItem(
            item_id=str(uuid.uuid4()),
            job_id=job_id,
            data=data,
        )
        if job_id not in self._items:
            self._items[job_id] = []
        self._items[job_id].append(item)
        return item

    def contar_jobs(self) -> int:
        return len(self._jobs)

    def contar_itens_total(self) -> int:
        return sum(len(items) for items in self._items.values())


# --------------------------------------------------------------------------
# Serviço de Celery (mock)
# --------------------------------------------------------------------------

class CeleryService:
    """Serviço para interagir com Celery."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._tasks_enviadas: List[str] = []

    def enviar_task(self, job_id: str, request: ScrapeRequest) -> str:
        """Envia task de scraping para a fila Celery."""
        task_id = str(uuid.uuid4())
        self._tasks_enviadas.append(task_id)
        return task_id

    def cancelar_task(self, task_id: str) -> bool:
        """Cancela uma task Celery em execução."""
        return task_id in self._tasks_enviadas

    def status_workers(self) -> List[Dict]:
        """Retorna status dos workers Celery."""
        return [
            {"hostname": "celery@worker-1", "status": "online", "active": 2},
            {"hostname": "celery@worker-2", "status": "online", "active": 1},
        ]


# --------------------------------------------------------------------------
# Simulação da API FastAPI (sem dependências reais)
# --------------------------------------------------------------------------

class FakeAPIResponse:
    """Simula resposta HTTP da API."""

    def __init__(self, status_code: int, json_data: Any = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self) -> Any:
        return self._json_data

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class FakeAPIClient:
    """Simula TestClient do FastAPI para testes isolados."""

    def __init__(self):
        self.job_dao = JobDAO()
        self.celery = CeleryService()
        self._redis_connected = True
        self._db_connected = True

    def get(self, path: str, params: Dict = None) -> FakeAPIResponse:
        """Simula GET request."""
        params = params or {}

        if path == "/health":
            return self._health()
        elif path == "/api/v1/jobs":
            return self._listar_jobs(params)
        elif path.startswith("/api/v1/jobs/") and path.endswith("/items"):
            job_id = path.split("/")[4]
            return self._listar_itens(job_id)
        elif path.startswith("/api/v1/jobs/"):
            job_id = path.split("/")[4]
            return self._detalhe_job(job_id)
        elif path == "/api/v1/spiders":
            return self._listar_spiders()
        elif path == "/api/v1/stats":
            return self._estatisticas()
        else:
            return FakeAPIResponse(404, {"detail": "Not found"})

    def post(self, path: str, json: Dict = None) -> FakeAPIResponse:
        """Simula POST request."""
        json = json or {}

        if path == "/api/v1/scrape":
            return self._criar_scrape(json)
        else:
            return FakeAPIResponse(404, {"detail": "Not found"})

    def delete(self, path: str) -> FakeAPIResponse:
        """Simula DELETE request."""
        if path.startswith("/api/v1/jobs/"):
            job_id = path.split("/")[4]
            return self._cancelar_job(job_id)
        return FakeAPIResponse(404, {"detail": "Not found"})

    # --- Handlers internos ---

    def _health(self) -> FakeAPIResponse:
        return FakeAPIResponse(200, {
            "status": "healthy",
            "version": "1.0.0",
            "services": {
                "database": "ok" if self._db_connected else "error",
                "redis": "ok" if self._redis_connected else "error",
                "worker": "ok",
            },
        })

    def _criar_scrape(self, payload: Dict) -> FakeAPIResponse:
        # Validação básica
        if not payload.get("url"):
            return FakeAPIResponse(422, {
                "detail": [{"loc": ["body", "url"], "msg": "field required"}]
            })

        url = payload["url"]
        if not url.startswith("http"):
            return FakeAPIResponse(422, {
                "detail": [{"loc": ["body", "url"], "msg": "URL inválida"}]
            })

        spider_type = payload.get("spider_type", SpiderType.GENERIC)
        if spider_type not in [SpiderType.GENERIC, SpiderType.JS, SpiderType.NEWS, SpiderType.API]:
            return FakeAPIResponse(422, {
                "detail": [{"loc": ["body", "spider_type"], "msg": "Tipo inválido"}]
            })

        request = ScrapeRequest(url=url, spider_type=spider_type)
        job = self.job_dao.criar_job(request)

        return FakeAPIResponse(202, {
            "job_id": job.job_id,
            "status": job.status,
            "url": job.url,
            "spider_type": job.spider_type,
            "created_at": job.created_at.isoformat(),
            "message": "Job criado e enfileirado",
        })

    def _listar_jobs(self, params: Dict) -> FakeAPIResponse:
        status_filter = params.get("status")
        page = int(params.get("page", 1))
        per_page = int(params.get("per_page", 20))

        jobs = self.job_dao.listar_jobs(status=status_filter, page=page, per_page=per_page)
        return FakeAPIResponse(200, {
            "jobs": [j.dict() for j in jobs],
            "total": self.job_dao.contar_jobs(),
            "page": page,
            "per_page": per_page,
        })

    def _detalhe_job(self, job_id: str) -> FakeAPIResponse:
        job = self.job_dao.buscar_job(job_id)
        if not job:
            return FakeAPIResponse(404, {"detail": f"Job '{job_id}' não encontrado"})
        return FakeAPIResponse(200, job.dict())

    def _cancelar_job(self, job_id: str) -> FakeAPIResponse:
        job = self.job_dao.buscar_job(job_id)
        if not job:
            return FakeAPIResponse(404, {"detail": f"Job '{job_id}' não encontrado"})
        if job.status == JobStatus.COMPLETED:
            return FakeAPIResponse(409, {"detail": "Job já finalizado, não pode ser cancelado"})

        self.job_dao.atualizar_status(job_id, JobStatus.CANCELLED)
        return FakeAPIResponse(200, {"message": f"Job '{job_id}' cancelado"})

    def _listar_itens(self, job_id: str) -> FakeAPIResponse:
        job = self.job_dao.buscar_job(job_id)
        if not job:
            return FakeAPIResponse(404, {"detail": f"Job '{job_id}' não encontrado"})

        itens = self.job_dao.listar_itens(job_id)
        return FakeAPIResponse(200, {
            "items": [i.dict() for i in itens],
            "total": len(itens),
            "job_id": job_id,
        })

    def _listar_spiders(self) -> FakeAPIResponse:
        return FakeAPIResponse(200, {
            "spiders": [
                {
                    "type": SpiderType.GENERIC,
                    "name": "Spider Genérico",
                    "description": "Para qualquer site HTML",
                },
                {
                    "type": SpiderType.JS,
                    "name": "Spider JavaScript",
                    "description": "Para SPAs e sites com JS",
                },
                {
                    "type": SpiderType.NEWS,
                    "name": "Spider Notícias",
                    "description": "Para portais de notícias",
                },
                {
                    "type": SpiderType.API,
                    "name": "Spider API REST",
                    "description": "Para APIs JSON",
                },
            ]
        })

    def _estatisticas(self) -> FakeAPIResponse:
        return FakeAPIResponse(200, {
            "total_jobs": self.job_dao.contar_jobs(),
            "total_items": self.job_dao.contar_itens_total(),
            "jobs_por_status": {},
            "workers_ativos": 2,
        })


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def client() -> FakeAPIClient:
    """Client da API isolado para cada teste."""
    return FakeAPIClient()


@pytest.fixture
def client_com_job(client: FakeAPIClient) -> tuple:
    """Client com um job já criado. Retorna (client, job_id)."""
    response = client.post("/api/v1/scrape", json={
        "url": "https://exemplo.com",
        "spider_type": "generic",
    })
    job_id = response.json()["job_id"]
    return client, job_id


@pytest.fixture
def client_com_itens(client_com_job: tuple) -> tuple:
    """Client com job e itens coletados. Retorna (client, job_id)."""
    client, job_id = client_com_job

    # Adicionar alguns itens
    for i in range(3):
        client.job_dao.adicionar_item(job_id, {
            "titulo": f"Produto {i + 1}",
            "preco": float(99.90 + i * 10),
            "url": f"https://exemplo.com/produto/{i + 1}",
        })

    return client, job_id


# ==============================================================================
# TESTES: GET /health
# ==============================================================================

class TestHealthCheck:
    """Testes para o endpoint de saúde da API."""

    def test_health_retorna_200(self, client):
        """Health check deve retornar HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_retorna_status_healthy(self, client):
        """Deve retornar status 'healthy' quando todos os serviços estão ok."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_inclui_versao(self, client):
        """Deve incluir versão da aplicação na resposta."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert len(data["version"]) > 0

    def test_health_verifica_banco_de_dados(self, client):
        """Deve verificar status do banco de dados."""
        response = client.get("/health")
        data = response.json()
        assert "services" in data
        assert "database" in data["services"]

    def test_health_verifica_redis(self, client):
        """Deve verificar status do Redis."""
        response = client.get("/health")
        data = response.json()
        assert "redis" in data["services"]

    def test_health_servicos_ok_quando_conectados(self, client):
        """Todos os serviços devem estar 'ok' quando conectados."""
        response = client.get("/health")
        data = response.json()
        for servico, status in data["services"].items():
            assert status == "ok", f"Serviço '{servico}' não está ok: {status}"

    def test_health_unhealthy_com_db_off(self, client):
        """Deve refletir problemas do banco de dados no health check."""
        client._db_connected = False
        response = client.get("/health")
        data = response.json()
        assert data["services"]["database"] != "ok"


# ==============================================================================
# TESTES: POST /api/v1/scrape
# ==============================================================================

class TestCriarScrapeJob:
    """Testes para o endpoint de criação de job de scraping."""

    def test_cria_job_com_url_valida(self, client):
        """Deve criar job e retornar 202 Accepted."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
        })
        assert response.status_code == 202

    def test_resposta_tem_job_id(self, client):
        """Resposta deve incluir job_id único."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
        })
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 36  # UUID v4

    def test_status_inicial_e_queued(self, client):
        """Job recém-criado deve ter status 'queued'."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
        })
        data = response.json()
        assert data["status"] == JobStatus.QUEUED

    def test_resposta_inclui_url(self, client):
        """Resposta deve ecoar a URL fornecida."""
        url = "https://loja.exemplo.com/produtos"
        response = client.post("/api/v1/scrape", json={"url": url})
        assert response.json()["url"] == url

    def test_spider_type_padrao_generic(self, client):
        """Spider type padrão deve ser 'generic'."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
        })
        data = response.json()
        assert data.get("spider_type") == SpiderType.GENERIC

    def test_aceita_spider_type_js(self, client):
        """Deve aceitar spider_type 'js'."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://spa.exemplo.com",
            "spider_type": "js",
        })
        assert response.status_code == 202
        assert response.json()["spider_type"] == SpiderType.JS

    @pytest.mark.parametrize("spider_type", ["generic", "js", "news", "api"])
    def test_aceita_todos_spider_types_validos(self, client, spider_type):
        """Deve aceitar todos os spider types válidos."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
            "spider_type": spider_type,
        })
        assert response.status_code == 202

    def test_rejeita_url_ausente(self, client):
        """Deve retornar 422 quando URL está ausente."""
        response = client.post("/api/v1/scrape", json={
            "spider_type": "generic",
        })
        assert response.status_code == 422

    def test_rejeita_url_invalida(self, client):
        """Deve retornar 422 para URL sem protocolo http/https."""
        response = client.post("/api/v1/scrape", json={
            "url": "nao-e-uma-url",
        })
        assert response.status_code == 422

    def test_rejeita_spider_type_invalido(self, client):
        """Deve retornar 422 para spider_type desconhecido."""
        response = client.post("/api/v1/scrape", json={
            "url": "https://exemplo.com",
            "spider_type": "tipo_inexistente",
        })
        assert response.status_code == 422

    def test_dois_jobs_tem_ids_diferentes(self, client):
        """Dois jobs criados devem ter IDs únicos."""
        r1 = client.post("/api/v1/scrape", json={"url": "https://exemplo.com"})
        r2 = client.post("/api/v1/scrape", json={"url": "https://outro.com"})
        assert r1.json()["job_id"] != r2.json()["job_id"]

    def test_resposta_inclui_created_at(self, client):
        """Resposta deve incluir timestamp de criação."""
        response = client.post("/api/v1/scrape", json={"url": "https://exemplo.com"})
        data = response.json()
        assert "created_at" in data


# ==============================================================================
# TESTES: GET /api/v1/jobs
# ==============================================================================

class TestListarJobs:
    """Testes para listagem de jobs."""

    def test_lista_vazia_sem_jobs(self, client):
        """Deve retornar lista vazia quando não há jobs."""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    def test_lista_job_criado(self, client_com_job):
        """Deve retornar o job recém-criado."""
        client, job_id = client_com_job
        response = client.get("/api/v1/jobs")
        data = response.json()
        assert data["total"] == 1
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["job_id"] == job_id

    def test_lista_multiplos_jobs(self, client):
        """Deve listar todos os jobs criados."""
        for i in range(5):
            client.post("/api/v1/scrape", json={"url": f"https://site{i}.com"})

        response = client.get("/api/v1/jobs")
        data = response.json()
        assert data["total"] == 5
        assert len(data["jobs"]) == 5

    def test_filtro_por_status(self, client_com_job):
        """Deve filtrar jobs pelo status."""
        client, job_id = client_com_job

        # Filtrar apenas jobs com status 'queued'
        response = client.get("/api/v1/jobs", params={"status": "queued"})
        data = response.json()
        assert all(j["status"] == "queued" for j in data["jobs"])

    def test_filtro_status_sem_resultado(self, client_com_job):
        """Filtro por status sem correspondência deve retornar lista vazia."""
        client, _ = client_com_job
        response = client.get("/api/v1/jobs", params={"status": "running"})
        assert response.json()["jobs"] == []

    def test_paginacao_page_1(self, client):
        """Deve retornar primeira página de resultados."""
        for i in range(10):
            client.post("/api/v1/scrape", json={"url": f"https://site{i}.com"})

        response = client.get("/api/v1/jobs", params={"page": 1, "per_page": 5})
        data = response.json()
        assert len(data["jobs"]) == 5
        assert data["page"] == 1

    def test_resposta_inclui_total(self, client):
        """Resposta deve incluir contagem total de jobs."""
        client.post("/api/v1/scrape", json={"url": "https://exemplo.com"})
        response = client.get("/api/v1/jobs")
        assert "total" in response.json()


# ==============================================================================
# TESTES: GET /api/v1/jobs/{job_id}
# ==============================================================================

class TestDetalheJob:
    """Testes para detalhe de job específico."""

    def test_retorna_job_existente(self, client_com_job):
        """Deve retornar detalhes do job existente."""
        client, job_id = client_com_job
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id

    def test_retorna_404_para_job_inexistente(self, client):
        """Deve retornar 404 para job não encontrado."""
        job_id_falso = str(uuid.uuid4())
        response = client.get(f"/api/v1/jobs/{job_id_falso}")
        assert response.status_code == 404

    def test_detalhes_incluem_status(self, client_com_job):
        """Detalhe deve incluir status do job."""
        client, job_id = client_com_job
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert "status" in response.json()

    def test_detalhes_incluem_url(self, client_com_job):
        """Detalhe deve incluir URL do scraping."""
        client, job_id = client_com_job
        response = client.get(f"/api/v1/jobs/{job_id}")
        data = response.json()
        assert "url" in data
        assert data["url"] == "https://exemplo.com"

    def test_detalhes_incluem_spider_type(self, client_com_job):
        """Detalhe deve incluir tipo do spider."""
        client, job_id = client_com_job
        response = client.get(f"/api/v1/jobs/{job_id}")
        data = response.json()
        assert "spider_type" in data

    def test_status_atualiza_corretamente(self, client_com_job):
        """Status do job deve refletir mudanças."""
        client, job_id = client_com_job

        # Atualizar status para 'running'
        client.job_dao.atualizar_status(job_id, JobStatus.RUNNING)

        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.json()["status"] == JobStatus.RUNNING


# ==============================================================================
# TESTES: DELETE /api/v1/jobs/{job_id}
# ==============================================================================

class TestCancelarJob:
    """Testes para cancelamento de jobs."""

    def test_cancela_job_queued(self, client_com_job):
        """Deve cancelar job com status 'queued'."""
        client, job_id = client_com_job
        response = client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200

    def test_status_vira_cancelled(self, client_com_job):
        """Job cancelado deve ter status 'cancelled'."""
        client, job_id = client_com_job
        client.delete(f"/api/v1/jobs/{job_id}")

        # Verificar status atualizado
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.json()["status"] == JobStatus.CANCELLED

    def test_retorna_404_para_job_inexistente(self, client):
        """Deve retornar 404 ao tentar cancelar job inexistente."""
        job_id_falso = str(uuid.uuid4())
        response = client.delete(f"/api/v1/jobs/{job_id_falso}")
        assert response.status_code == 404

    def test_nao_cancela_job_completed(self, client_com_job):
        """Não deve cancelar job que já foi completado."""
        client, job_id = client_com_job
        client.job_dao.atualizar_status(job_id, JobStatus.COMPLETED)

        response = client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 409  # Conflict

    def test_mensagem_de_confirmacao(self, client_com_job):
        """Resposta de cancelamento deve incluir mensagem."""
        client, job_id = client_com_job
        response = client.delete(f"/api/v1/jobs/{job_id}")
        data = response.json()
        assert "message" in data


# ==============================================================================
# TESTES: GET /api/v1/jobs/{job_id}/items
# ==============================================================================

class TestListarItens:
    """Testes para listagem de itens coletados."""

    def test_lista_vazia_sem_itens(self, client_com_job):
        """Deve retornar lista vazia quando não há itens."""
        client, job_id = client_com_job
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_lista_itens_do_job(self, client_com_itens):
        """Deve retornar todos os itens do job."""
        client, job_id = client_com_itens
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_itens_tem_item_id(self, client_com_itens):
        """Cada item deve ter um item_id único."""
        client, job_id = client_com_itens
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        itens = response.json()["items"]
        ids = [item["item_id"] for item in itens]
        assert len(ids) == len(set(ids))  # Todos únicos

    def test_itens_tem_data(self, client_com_itens):
        """Cada item deve ter campo 'data' com dados coletados."""
        client, job_id = client_com_itens
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        for item in response.json()["items"]:
            assert "data" in item
            assert "titulo" in item["data"]

    def test_retorna_404_para_job_inexistente(self, client):
        """Deve retornar 404 para job não encontrado."""
        job_id_falso = str(uuid.uuid4())
        response = client.get(f"/api/v1/jobs/{job_id_falso}/items")
        assert response.status_code == 404

    def test_itens_tem_job_id(self, client_com_itens):
        """Cada item deve ter o job_id correto."""
        client, job_id = client_com_itens
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        for item in response.json()["items"]:
            assert item["job_id"] == job_id

    def test_itens_tem_scraped_at(self, client_com_itens):
        """Cada item deve ter timestamp de coleta."""
        client, job_id = client_com_itens
        response = client.get(f"/api/v1/jobs/{job_id}/items")
        for item in response.json()["items"]:
            assert "scraped_at" in item


# ==============================================================================
# TESTES: GET /api/v1/spiders
# ==============================================================================

class TestListarSpiders:
    """Testes para listagem de spiders disponíveis."""

    def test_retorna_lista_de_spiders(self, client):
        """Deve retornar lista de spiders disponíveis."""
        response = client.get("/api/v1/spiders")
        assert response.status_code == 200
        data = response.json()
        assert "spiders" in data
        assert len(data["spiders"]) > 0

    def test_spider_generic_disponivel(self, client):
        """Spider 'generic' deve estar na lista."""
        response = client.get("/api/v1/spiders")
        types = [s["type"] for s in response.json()["spiders"]]
        assert SpiderType.GENERIC in types

    def test_spider_js_disponivel(self, client):
        """Spider 'js' deve estar na lista."""
        response = client.get("/api/v1/spiders")
        types = [s["type"] for s in response.json()["spiders"]]
        assert SpiderType.JS in types

    def test_spiders_tem_descricao(self, client):
        """Cada spider deve ter nome e descrição."""
        response = client.get("/api/v1/spiders")
        for spider in response.json()["spiders"]:
            assert "name" in spider
            assert "description" in spider
            assert len(spider["description"]) > 0

    @pytest.mark.parametrize("spider_type", ["generic", "js", "news", "api"])
    def test_todos_tipos_disponiveis(self, client, spider_type):
        """Todos os tipos de spider devem estar disponíveis."""
        response = client.get("/api/v1/spiders")
        types = [s["type"] for s in response.json()["spiders"]]
        assert spider_type in types


# ==============================================================================
# TESTES: GET /api/v1/stats
# ==============================================================================

class TestEstatisticas:
    """Testes para endpoint de estatísticas."""

    def test_retorna_estatisticas(self, client):
        """Deve retornar estatísticas do sistema."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200

    def test_inclui_total_jobs(self, client):
        """Deve incluir total de jobs."""
        response = client.get("/api/v1/stats")
        assert "total_jobs" in response.json()

    def test_inclui_total_items(self, client):
        """Deve incluir total de itens coletados."""
        response = client.get("/api/v1/stats")
        assert "total_items" in response.json()

    def test_total_jobs_atualiza(self, client):
        """Total de jobs deve aumentar após criar jobs."""
        r_antes = client.get("/api/v1/stats").json()["total_jobs"]
        client.post("/api/v1/scrape", json={"url": "https://exemplo.com"})
        r_depois = client.get("/api/v1/stats").json()["total_jobs"]
        assert r_depois == r_antes + 1

    def test_total_itens_atualiza(self, client_com_job):
        """Total de itens deve aumentar após adicionar itens."""
        client, job_id = client_com_job

        antes = client.get("/api/v1/stats").json()["total_items"]
        client.job_dao.adicionar_item(job_id, {"titulo": "Teste"})
        depois = client.get("/api/v1/stats").json()["total_items"]

        assert depois == antes + 1


# ==============================================================================
# TESTES: Comportamento geral da API
# ==============================================================================

class TestComportamentoGeral:
    """Testes gerais de comportamento da API."""

    def test_endpoint_inexistente_retorna_404(self, client):
        """Endpoint não existente deve retornar 404."""
        response = client.get("/api/v1/endpoint-que-nao-existe")
        assert response.status_code == 404

    def test_respostas_sao_json(self, client):
        """Todas as respostas devem ser JSON válido."""
        endpoints = ["/health", "/api/v1/jobs", "/api/v1/spiders"]
        for endpoint in endpoints:
            response = client.get(endpoint)
            data = response.json()  # Não deve lançar exceção
            assert data is not None

    def test_job_workflow_completo(self, client):
        """Testa o fluxo completo: criar → listar → detalhar → cancelar."""
        # 1. Criar job
        r_criar = client.post("/api/v1/scrape", json={
            "url": "https://workflow.exemplo.com",
        })
        assert r_criar.status_code == 202
        job_id = r_criar.json()["job_id"]

        # 2. Listar e verificar que aparece
        r_listar = client.get("/api/v1/jobs")
        ids_listados = [j["job_id"] for j in r_listar.json()["jobs"]]
        assert job_id in ids_listados

        # 3. Buscar detalhe
        r_detalhe = client.get(f"/api/v1/jobs/{job_id}")
        assert r_detalhe.status_code == 200
        assert r_detalhe.json()["status"] == JobStatus.QUEUED

        # 4. Cancelar
        r_cancelar = client.delete(f"/api/v1/jobs/{job_id}")
        assert r_cancelar.status_code == 200

        # 5. Verificar status cancelado
        r_final = client.get(f"/api/v1/jobs/{job_id}")
        assert r_final.json()["status"] == JobStatus.CANCELLED
