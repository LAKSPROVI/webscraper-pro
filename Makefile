# ==============================================================================
# Makefile — WebScraper Pro
# Comandos facilitados para gerenciar a stack Docker
# Uso: make <target> [VARIÁVEIS]
# ==============================================================================

# Variáveis configuráveis via linha de comando
COMPOSE_FILE   := docker-compose.yml
PROJECT_NAME   := webscraper
API_SERVICE    := scraper-api
WORKER_SERVICE := scraper-worker
DB_SERVICE     := postgres
DB_NAME        := webscraper
DB_USER        := scraper

# Cores para output no terminal
VERDE  := \033[0;32m
AMARELO := \033[1;33m
AZUL   := \033[0;34m
RESET  := \033[0m

# Marca targets sem arquivos correspondentes como "phony"
.PHONY: help up down restart logs logs-api logs-worker logs-db logs-redis \
        shell-api shell-worker shell-db migrate migrate-rollback \
        scrape scrape-js scrape-api status clean clean-all backup-db \
        test test-unit test-api build build-api build-worker ps stats \
        monitor urls lint format check-env

# ==============================================================================
# TARGET PADRÃO — Exibe ajuda
# ==============================================================================

## Exibe esta mensagem de ajuda
help:
	@echo ""
	@echo "$(AZUL)╔══════════════════════════════════════════════════════════╗$(RESET)"
	@echo "$(AZUL)║           WebScraper Pro — Comandos Disponíveis          ║$(RESET)"
	@echo "$(AZUL)╚══════════════════════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(VERDE)🐳 DOCKER COMPOSE$(RESET)"
	@echo "  make up              Sobe toda a stack em background"
	@echo "  make down            Para e remove todos os containers"
	@echo "  make restart         Reinicia todos os serviços"
	@echo "  make build           Build de todas as imagens"
	@echo "  make ps              Lista containers rodando"
	@echo "  make status          Status detalhado de cada serviço"
	@echo "  make stats           Uso de CPU/RAM dos containers"
	@echo ""
	@echo "$(VERDE)📋 LOGS$(RESET)"
	@echo "  make logs            Logs de todos os serviços (follow)"
	@echo "  make logs-api        Logs apenas da API FastAPI"
	@echo "  make logs-worker     Logs do worker Celery"
	@echo "  make logs-db         Logs do PostgreSQL"
	@echo "  make logs-redis      Logs do Redis"
	@echo ""
	@echo "$(VERDE)🔧 SHELLS$(RESET)"
	@echo "  make shell-api       Shell bash dentro do container da API"
	@echo "  make shell-worker    Shell bash dentro do container do worker"
	@echo "  make shell-db        Conecta ao PostgreSQL (psql)"
	@echo ""
	@echo "$(VERDE)🗄️  BANCO DE DADOS$(RESET)"
	@echo "  make migrate         Roda migrações Alembic pendentes"
	@echo "  make migrate-rollback Reverte última migração"
	@echo "  make backup-db       Backup do PostgreSQL (.sql.gz)"
	@echo ""
	@echo "$(VERDE)🕷️  SCRAPING$(RESET)"
	@echo "  make scrape URL=https://site.com        Dispara scrape genérico"
	@echo "  make scrape-js URL=https://site.com     Scrape com JavaScript"
	@echo "  make scrape-api URL=https://api.com     Scrape de API REST"
	@echo ""
	@echo "$(VERDE)🧪 TESTES$(RESET)"
	@echo "  make test            Roda todos os testes"
	@echo "  make test-unit       Apenas testes unitários"
	@echo "  make test-api        Apenas testes da API"
	@echo ""
	@echo "$(VERDE)🧹 LIMPEZA$(RESET)"
	@echo "  make clean           Para a stack e remove volumes"
	@echo "  make clean-all       Remove tudo incluindo imagens e cache"
	@echo ""
	@echo "$(VERDE)🌐 URLS$(RESET)"
	@echo "  make urls            Exibe todas as URLs de acesso"
	@echo ""

# ==============================================================================
# DOCKER COMPOSE — Operações principais
# ==============================================================================

## Sobe toda a stack em modo background
up: check-env
	@echo "$(VERDE)▶ Subindo a stack WebScraper...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) up -d
	@echo "$(VERDE)✓ Stack no ar! Execute 'make urls' para ver os endereços.$(RESET)"

## Para e remove todos os containers (preserva volumes)
down:
	@echo "$(AMARELO)■ Parando a stack...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) down
	@echo "$(VERDE)✓ Stack parada.$(RESET)"

## Reinicia todos os serviços
restart:
	@echo "$(AMARELO)↺ Reiniciando a stack...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) restart
	@echo "$(VERDE)✓ Stack reiniciada.$(RESET)"

## Build de todas as imagens Docker
build:
	@echo "$(AZUL)🔨 Construindo imagens Docker...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) build --no-cache
	@echo "$(VERDE)✓ Build concluído.$(RESET)"

## Build apenas da imagem da API
build-api:
	@echo "$(AZUL)🔨 Construindo imagem da API...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) build --no-cache $(API_SERVICE)

## Build apenas da imagem do worker
build-worker:
	@echo "$(AZUL)🔨 Construindo imagem do Worker...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) build --no-cache $(WORKER_SERVICE)

## Lista containers em execução
ps:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) ps

## Status detalhado de cada serviço (inclui health check)
status:
	@echo "$(AZUL)📊 Status dos serviços:$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

## Estatísticas de CPU e RAM dos containers
stats:
	@echo "$(AZUL)📈 Estatísticas de recursos (Ctrl+C para sair):$(RESET)"
	docker stats $$(docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) ps -q)

# ==============================================================================
# LOGS — Acompanhar saída dos serviços
# ==============================================================================

## Logs de todos os serviços (follow, últimas 100 linhas)
logs:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=100

## Logs apenas da API FastAPI
logs-api:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=200 $(API_SERVICE)

## Logs do worker Celery
logs-worker:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=200 $(WORKER_SERVICE)

## Logs do PostgreSQL
logs-db:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=100 $(DB_SERVICE)

## Logs do Redis
logs-redis:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=100 redis

# ==============================================================================
# SHELLS — Acesso interativo aos containers
# ==============================================================================

## Abre shell bash no container da API
shell-api:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) /bin/bash

## Abre shell bash no container do worker
shell-worker:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(WORKER_SERVICE) /bin/bash

## Conecta ao PostgreSQL via psql
shell-db:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(DB_SERVICE) \
		psql -U $(DB_USER) -d $(DB_NAME)

# ==============================================================================
# BANCO DE DADOS — Migrações e backup
# ==============================================================================

## Roda migrações Alembic pendentes
migrate:
	@echo "$(AZUL)🗄️  Rodando migrações...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		alembic upgrade head
	@echo "$(VERDE)✓ Migrações aplicadas.$(RESET)"

## Reverte a última migração Alembic
migrate-rollback:
	@echo "$(AMARELO)⚠ Revertendo última migração...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		alembic downgrade -1
	@echo "$(VERDE)✓ Migração revertida.$(RESET)"

## Exibe histórico de migrações
migrate-history:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		alembic history --verbose

## Backup do PostgreSQL comprimido com gzip
backup-db:
	@echo "$(AZUL)💾 Criando backup do banco de dados...$(RESET)"
	@mkdir -p backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		BACKUP_FILE="backups/backup_$(PROJECT_NAME)_$${TIMESTAMP}.sql.gz" && \
		docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec -T $(DB_SERVICE) \
			pg_dump -U $(DB_USER) $(DB_NAME) | gzip > $${BACKUP_FILE} && \
		echo "$(VERDE)✓ Backup salvo em: $${BACKUP_FILE}$(RESET)" && \
		ls -lh $${BACKUP_FILE}
	@echo "$(AZUL)📁 Backups disponíveis:$(RESET)"
	@ls -lht backups/*.sql.gz 2>/dev/null | head -10

## Restaura backup do banco de dados
## Uso: make restore-db FILE=backups/backup_webscraper_20240101_120000.sql.gz
restore-db:
	@if [ -z "$(FILE)" ]; then \
		echo "$(AMARELO)⚠ Uso: make restore-db FILE=backups/arquivo.sql.gz$(RESET)"; \
		exit 1; \
	fi
	@echo "$(AMARELO)⚠ ATENÇÃO: Isso irá sobrescrever o banco atual!$(RESET)"
	@echo "$(AZUL)📥 Restaurando backup: $(FILE)$(RESET)"
	@gunzip -c $(FILE) | docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) \
		exec -T $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME)
	@echo "$(VERDE)✓ Backup restaurado.$(RESET)"

# ==============================================================================
# SCRAPING — Disparar jobs via API
# ==============================================================================

## Dispara scrape genérico
## Uso: make scrape URL=https://exemplo.com [DEPTH=2] [LIMIT=10]
scrape:
	@if [ -z "$(URL)" ]; then \
		echo "$(AMARELO)⚠ Uso: make scrape URL=https://exemplo.com$(RESET)"; \
		exit 1; \
	fi
	@echo "$(AZUL)🕷️  Iniciando scrape: $(URL)$(RESET)"
	@curl -s -X POST http://localhost:8000/api/v1/scrape \
		-H "Content-Type: application/json" \
		-d '{"url": "$(URL)", "spider_type": "generic", "depth": $(or $(DEPTH),2), "max_items": $(or $(LIMIT),100)}' \
		| python3 -m json.tool || echo "$(AMARELO)⚠ API não respondeu. Execute 'make up' primeiro.$(RESET)"

## Dispara scrape com renderização JavaScript (Playwright)
## Uso: make scrape-js URL=https://spa.exemplo.com
scrape-js:
	@if [ -z "$(URL)" ]; then \
		echo "$(AMARELO)⚠ Uso: make scrape-js URL=https://spa.exemplo.com$(RESET)"; \
		exit 1; \
	fi
	@echo "$(AZUL)🕷️  Iniciando scrape JS: $(URL)$(RESET)"
	@curl -s -X POST http://localhost:8000/api/v1/scrape \
		-H "Content-Type: application/json" \
		-d '{"url": "$(URL)", "spider_type": "js", "render_js": true, "depth": $(or $(DEPTH),1)}' \
		| python3 -m json.tool || echo "$(AMARELO)⚠ API não respondeu.$(RESET)"

## Dispara scrape de API REST
## Uso: make scrape-api URL=https://api.exemplo.com CONFIG=configs/api.yml
scrape-api:
	@if [ -z "$(URL)" ]; then \
		echo "$(AMARELO)⚠ Uso: make scrape-api URL=https://api.exemplo.com$(RESET)"; \
		exit 1; \
	fi
	@echo "$(AZUL)🕷️  Iniciando scrape API: $(URL)$(RESET)"
	@curl -s -X POST http://localhost:8000/api/v1/scrape \
		-H "Content-Type: application/json" \
		-d '{"url": "$(URL)", "spider_type": "api", "config_file": "$(or $(CONFIG),configs/api.yml)"}' \
		| python3 -m json.tool || echo "$(AMARELO)⚠ API não respondeu.$(RESET)"

## Lista todos os jobs de scraping
jobs:
	@echo "$(AZUL)📋 Jobs de scraping:$(RESET)"
	@curl -s http://localhost:8000/api/v1/jobs | python3 -m json.tool

## Status de um job específico
## Uso: make job-status JOB_ID=abc123
job-status:
	@if [ -z "$(JOB_ID)" ]; then \
		echo "$(AMARELO)⚠ Uso: make job-status JOB_ID=<id>$(RESET)"; \
		exit 1; \
	fi
	@curl -s http://localhost:8000/api/v1/jobs/$(JOB_ID) | python3 -m json.tool

# ==============================================================================
# TESTES — Rodar suíte de testes
# ==============================================================================

## Roda todos os testes
test:
	@echo "$(AZUL)🧪 Rodando todos os testes...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		python -m pytest tests/ -v --tb=short
	@echo "$(VERDE)✓ Testes concluídos.$(RESET)"

## Apenas testes unitários
test-unit:
	@echo "$(AZUL)🧪 Rodando testes unitários...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		python -m pytest tests/test_spiders.py -v --tb=short

## Apenas testes da API
test-api:
	@echo "$(AZUL)🧪 Rodando testes da API...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		python -m pytest tests/test_api.py -v --tb=short

## Testes com coverage report
test-coverage:
	@echo "$(AZUL)🧪 Rodando testes com coverage...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		python -m pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
	@echo "$(VERDE)✓ Relatório de cobertura salvo em htmlcov/$(RESET)"

# ==============================================================================
# QUALIDADE DE CÓDIGO
# ==============================================================================

## Roda linter (ruff)
lint:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		python -m ruff check . --fix

## Formata código (black + isort)
format:
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) exec $(API_SERVICE) \
		sh -c "python -m black . && python -m isort ."

# ==============================================================================
# LIMPEZA — Remover artefatos
# ==============================================================================

## Para a stack e remove volumes de dados
clean:
	@echo "$(AMARELO)⚠ Parando stack e removendo volumes...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) down -v
	@echo "$(VERDE)✓ Stack e volumes removidos.$(RESET)"

## Remove tudo: containers, volumes, imagens e cache Docker
clean-all:
	@echo "$(AMARELO)⚠ ATENÇÃO: Isso remove TODOS os dados! Pressione Ctrl+C para cancelar.$(RESET)"
	@sleep 5
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) down -v --rmi all --remove-orphans
	docker builder prune -f
	@echo "$(VERDE)✓ Limpeza total concluída.$(RESET)"

# ==============================================================================
# INFORMAÇÕES — Exibir URLs e status
# ==============================================================================

## Exibe URLs de acesso a todos os serviços
urls:
	@echo ""
	@echo "$(AZUL)╔══════════════════════════════════════╗$(RESET)"
	@echo "$(AZUL)║     WebScraper Pro — URLs de Acesso  ║$(RESET)"
	@echo "$(AZUL)╚══════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "  🚀 API REST:         http://localhost:8000"
	@echo "  📚 Docs (Swagger):   http://localhost:8000/docs"
	@echo "  📋 Docs (ReDoc):     http://localhost:8000/redoc"
	@echo "  💐 Flower (Celery):  http://localhost:5555"
	@echo "  📊 Grafana:          http://localhost:3000  (admin/admin)"
	@echo "  🔥 Prometheus:       http://localhost:9090"
	@echo "  🗄️  PgAdmin:          http://localhost:5050"
	@echo "  🌸 Frontend:         http://localhost:3001"
	@echo ""

## Verifica se o arquivo .env existe
check-env:
	@if [ ! -f .env ]; then \
		echo "$(AMARELO)⚠ Arquivo .env não encontrado!$(RESET)"; \
		echo "$(AZUL)  Execute: cp .env.example .env$(RESET)"; \
		echo "$(AZUL)  Depois edite o .env com suas configurações.$(RESET)"; \
		exit 1; \
	fi

## Verifica saúde da API
health:
	@echo "$(AZUL)🏥 Verificando saúde dos serviços...$(RESET)"
	@curl -s http://localhost:8000/health | python3 -m json.tool \
		|| echo "$(AMARELO)⚠ API não está respondendo$(RESET)"

## Exibe variáveis de ambiente configuradas (sem senhas)
env-check:
	@echo "$(AZUL)⚙ Variáveis de ambiente:$(RESET)"
	@grep -v "PASSWORD\|SECRET\|TOKEN\|KEY" .env 2>/dev/null || echo "$(AMARELO).env não encontrado$(RESET)"

## Monitora logs em tempo real (todos os serviços)
monitor:
	@echo "$(AZUL)📡 Monitorando todos os serviços (Ctrl+C para sair)...$(RESET)"
	docker compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f --tail=50
