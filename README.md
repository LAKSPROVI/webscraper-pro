# 🕷️ WebScraper Pro

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.3+-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Playwright](https://img.shields.io/badge/Playwright-JS_Rendering-45ba4b?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev)
[![Grafana](https://img.shields.io/badge/Grafana-Monitoring-F46800?style=for-the-badge&logo=grafana&logoColor=white)](https://grafana.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**Sistema profissional de coleta de dados web com anti-bot, monitoramento e dashboard.**
**Pronto para produção em menos de 5 minutos.**

[🚀 Quick Start](#-quick-start--5-minutos) · [📚 Documentação](#-configuração) · [🔌 API](#-api-reference) · [📊 Dashboard](#-dashboard)

</div>

---

## 📖 Visão Geral

O **WebScraper Pro** é um sistema completo de coleta de dados web (web scraping) construído para escala e confiabilidade. Diferentemente de scrapers simples, oferece:

- **API REST** para disparar e gerenciar jobs de scraping programaticamente
- **Workers assíncronos** com Celery para processar múltiplos sites em paralelo
- **Renderização JavaScript** via Playwright para SPAs e sites modernos
- **Anti-bot sofisticado**: rotação de proxies, fingerprinting, delays aleatórios
- **Monitoramento completo** com Grafana, Prometheus e Loki
- **Configuração por YAML** — crie novos spiders sem escrever código
- **Deduplicação inteligente** para evitar coleta de dados repetidos

---

## ✨ Features

### 🕸️ Coleta de Dados
- ✅ Suporte a HTML estático, SPAs JavaScript (Playwright), APIs REST/JSON
- ✅ Configuração declarativa por arquivo YAML — sem código
- ✅ Templates prontos: E-commerce, Notícias, API REST, Site JS
- ✅ Extração por seletores CSS e XPath
- ✅ Transformações de dados: `to_float`, `to_date`, `to_bool`, `strip`
- ✅ Paginação automática: clique, parâmetro URL, cursor
- ✅ Coleta de múltiplos valores (listas, tabelas)
- ✅ Seguimento de links para páginas de detalhe
- ✅ Feeds RSS/Atom para portais de notícias

### 🛡️ Anti-Bot & Stealth
- ✅ Rotação automática de User-Agents (500+ perfis)
- ✅ Rotação de proxies residenciais e datacenter
- ✅ Delays aleatórios configuráveis entre requisições
- ✅ Rate limiting por domínio
- ✅ Headers HTTP realistas (Accept-Language, Referer, etc.)
- ✅ Fingerprinting de navegador com Playwright
- ✅ Respeito a `robots.txt` (configurável)
- ✅ Detecção e bypass de CAPTCHAs simples

### ⚡ Performance & Escala
- ✅ Workers Celery distribuídos (escala horizontal)
- ✅ Pool de conexões HTTP com `httpx` assíncrono
- ✅ Cache de páginas com Redis (evita re-fetching)
- ✅ Processamento paralelo de múltiplos domínios
- ✅ Limite de memória por worker configurável
- ✅ Retry automático com backoff exponencial

### 📊 Monitoramento & Observabilidade
- ✅ Dashboard Grafana com métricas em tempo real
- ✅ Prometheus para coleta de métricas
- ✅ Loki + Promtail para logs centralizados
- ✅ Flower para monitoramento de filas Celery
- ✅ Alertas configuráveis (taxa de erro, latência)
- ✅ Health checks em todos os serviços

### 🔌 API & Integração
- ✅ API REST com documentação automática (Swagger/ReDoc)
- ✅ Webhooks para notificação de conclusão de jobs
- ✅ Export em JSON, CSV e JSONL
- ✅ Filtros e busca nos dados coletados
- ✅ Autenticação via API Key e JWT

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE ENTRADA                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Frontend    │  │  API REST    │  │  CLI / Scripts           │  │
│  │  React + TS  │  │  FastAPI     │  │  Makefile / bash         │  │
│  │  :3001       │  │  :8000       │  │                          │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬─────────────┘  │
└─────────┼─────────────────┼──────────────────────┼────────────────┘
          │                 │                        │
┌─────────▼─────────────────▼────────────────────────▼───────────────┐
│                       CAMADA DE FILA                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Redis — Broker + Cache + Rate Limiting           │  │
│  │                          :6379                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬───────────────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────────┐
│                      CAMADA DE WORKERS                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Worker      │  │  Worker      │  │  Worker JS               │  │
│  │  Celery      │  │  Celery      │  │  Playwright              │  │
│  │  (HTTP)      │  │  (API)       │  │  (SPA/JS)                │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬─────────────┘  │
│         │  ┌──────────────┘                        │               │
│         ▼  ▼                                        ▼               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  Pipeline de Processamento                    │  │
│  │  CleanerPipeline → DuplicateFilter → Validation → Storage    │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬───────────────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────────┐
│                     CAMADA DE DADOS                                 │
│  ┌───────────────────────────────┐  ┌───────────────────────────┐  │
│  │     PostgreSQL 16             │  │      Volumes Docker       │  │
│  │     Jobs + Items + Logs       │  │      Exports (JSON/CSV)   │  │
│  │     :5432                     │  │                           │  │
│  └───────────────────────────────┘  └───────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────────┐
│                  CAMADA DE OBSERVABILIDADE                          │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  Grafana   │  │  Prometheus │  │   Loki   │  │   Flower    │  │
│  │  :3000     │  │  :9090      │  │  :3100   │  │   :5555     │  │
│  └────────────┘  └─────────────┘  └──────────┘  └─────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (< 5 minutos)

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2.20+
- 2GB RAM disponível
- Portas 8000, 3000, 3001, 5555 livres

### 1. Clone e Configure

```bash
# Clonar repositório
git clone https://github.com/seu-usuario/webscraper-pro.git
cd webscraper-pro

# Copiar configurações de ambiente
cp .env.example .env

# Editar configurações (opcional para começar)
nano .env
```

### 2. Suba a Stack

```bash
# Subir todos os serviços
make up

# Acompanhar inicialização
make logs
```

### 3. Acesse o Sistema

```bash
# Ver todas as URLs
make urls
```

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| 🌐 Frontend | http://localhost:3001 | — |
| 🚀 API Docs | http://localhost:8000/docs | — |
| 📊 Grafana | http://localhost:3000 | admin / admin |
| 💐 Flower | http://localhost:5555 | flower / flower |

### 4. Faça seu Primeiro Scrape

```bash
# Via Makefile
make scrape URL=https://books.toscrape.com

# Via curl
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://books.toscrape.com", "spider_type": "generic"}'
```

---

## 📦 Stack Tecnológica

| Componente | Tecnologia | Versão | Função |
|-----------|------------|--------|--------|
| **API** | FastAPI | 0.110+ | API REST assíncrona |
| **Workers** | Celery | 5.3+ | Processamento distribuído |
| **Scraping** | httpx + parsel | latest | HTTP + parsing HTML |
| **JS Rendering** | Playwright | latest | Sites SPA/JavaScript |
| **Banco de Dados** | PostgreSQL | 16 | Armazenamento persistente |
| **Cache/Broker** | Redis | 7 | Filas e cache |
| **Migração** | Alembic | 1.13+ | Versionamento do banco |
| **Monitoramento** | Grafana | 10 | Dashboards e alertas |
| **Métricas** | Prometheus | 2.49+ | Coleta de métricas |
| **Logs** | Loki + Promtail | 2.9+ | Agregação de logs |
| **Task UI** | Flower | 2.0+ | Monitor de filas Celery |
| **Frontend** | React + TypeScript | 18 + 5 | Interface web |
| **Container** | Docker Compose | v2 | Orquestração local |

---

## 🔌 API Reference

### Sessao autenticada para sites assinados (ex.: Jusbrasil)

Para alvos que exigem assinatura ativa, use sessao autenticada legitima do assinante.

Fluxo rapido:

```bash
# 1) Gerar storage state local com login manual
.venv/bin/python scripts/export_jusbrasil_storage_state.py \
  --output sessions/jusbrasil.storage-state.json

# 2) Aplicar no servidor e disparar smoke test
bash scripts/apply_jusbrasil_session.sh \
  --host 77.42.68.212 \
  --user webscraper \
  --state-file sessions/jusbrasil.storage-state.json \
  --api-url https://api.77.42.68.212.nip.io
```

Guia completo: `docs/authenticated-scraping.md`

### Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "database": "ok",
    "redis": "ok",
    "worker": "ok"
  }
}
```

### Disparar Scrape

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://exemplo.com/produtos",
    "spider_type": "generic",
    "depth": 2,
    "max_items": 500,
    "render_js": false
  }'
```

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "url": "https://exemplo.com/produtos",
  "created_at": "2024-01-15T10:30:00Z",
  "estimated_time": "2-5 minutos"
}
```

### Scrape com Configuração YAML

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "config_file": "configs/ecommerce.yml",
    "variables": {
      "start_url": "https://minha-loja.com/produtos"
    }
  }'
```

### Verificar Status do Job

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
```

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "running",
  "progress": {
    "pages_scraped": 15,
    "items_collected": 342,
    "errors": 2,
    "elapsed_seconds": 87
  },
  "started_at": "2024-01-15T10:30:05Z"
}
```

### Listar Jobs

```bash
# Todos os jobs
curl "http://localhost:8000/api/v1/jobs"

# Filtrar por status
curl "http://localhost:8000/api/v1/jobs?status=completed&limit=10"

# Com paginação
curl "http://localhost:8000/api/v1/jobs?page=2&per_page=20"
```

### Recuperar Dados Coletados

```bash
# Dados de um job
curl "http://localhost:8000/api/v1/jobs/{job_id}/items"

# Com filtros e busca
curl "http://localhost:8000/api/v1/jobs/{job_id}/items?search=notebook&min_price=1000"

# Download como CSV
curl "http://localhost:8000/api/v1/jobs/{job_id}/export?format=csv" -o dados.csv

# Download como JSON Lines
curl "http://localhost:8000/api/v1/jobs/{job_id}/export?format=jsonl" -o dados.jsonl
```

### Cancelar Job

```bash
curl -X DELETE http://localhost:8000/api/v1/jobs/{job_id}
```

### Listar Spiders Disponíveis

```bash
curl http://localhost:8000/api/v1/spiders
```

---

## ⚙️ Configuração

### Variáveis de Ambiente (`.env`)

```bash
# Banco de dados
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=webscraper_db
POSTGRES_USER=webscraper_user
POSTGRES_PASSWORD=senha_segura_aqui

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=senha_redis_aqui

# API
SECRET_KEY=chave_secreta_jwt_aqui
API_WORKERS=4                    # Workers Uvicorn
MAX_CONCURRENT_SPIDERS=10        # Spiders simultâneos

# Celery
CELERY_WORKERS=4                 # Workers Celery
CELERY_MAX_TASKS_PER_CHILD=100   # Reiniciar worker após N tasks

# Proxy (opcional)
PROXY_ENABLED=false
PROXY_LIST_URL=https://api.proxyprovider.com/list
PROXY_API_KEY=sua_chave_aqui

# Monitoramento
GRAFANA_PASSWORD=admin123
FLOWER_USERNAME=flower
FLOWER_PASSWORD=flower123

# Notificações (opcional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Criar um Spider YAML

Crie um arquivo em `configs/meu-spider.yml`:

```yaml
spider_type: generic
name: "meu-site"
start_urls:
  - "https://meu-site.com/lista"

extraction:
  item_selector: ".item"
  fields:
    titulo:
      selector: "h2"
      type: "text"
      required: true
    preco:
      selector: ".preco"
      type: "text"
      transform: "to_float"

pagination:
  enabled: true
  selector: "a.proxima"
  max_pages: 10
```

E dispare via API:

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"config_file": "configs/meu-spider.yml"}'
```

### Templates de Configuração Disponíveis

| Arquivo | Descrição |
|---------|-----------|
| `configs/generic.yml` | Template genérico para qualquer site |
| `configs/ecommerce.yml` | Lojas online (preços, produtos, estoque) |
| `configs/news.yml` | Portais de notícias e blogs |
| `configs/js_site.yml` | SPAs e sites JavaScript |
| `configs/api.yml` | APIs REST/JSON |

---

## 📊 Dashboard

### Grafana (http://localhost:3000)

Login: `admin` / `admin` (altere no primeiro acesso)

**Dashboards disponíveis:**

- **WebScraper Main** — Visão geral do sistema
  - Total de itens coletados
  - Jobs ativos e na fila
  - Taxa de sucesso (%)
  - Itens/hora nas últimas 24h
  - Top 10 domínios por volume
  - Erros por spider
  - Latência de requests (histogram)
  - Status dos workers Celery

Para importar o dashboard manualmente:
1. Acesse Grafana → Dashboards → Import
2. Faça upload de `monitoring/grafana/dashboards/webscraper_main.json`

### Flower — Monitor Celery (http://localhost:5555)

Login: `flower` / `flower`

Visualize:
- Workers ativos e suas capacidades
- Tasks em execução, pendentes e falhas
- Histórico de execução
- Métricas de throughput

---

## 🛡️ Anti-Bot Features

O sistema inclui múltiplas camadas de proteção contra detecção:

| Feature | Descrição |
|---------|-----------|
| **User-Agent Rotation** | 500+ perfis reais de navegadores (Chrome, Firefox, Safari) |
| **Request Headers** | Accept-Language, Accept-Encoding, Referer realistas |
| **Delays Aleatórios** | Distribuição normal entre `delay_min` e `delay_max` |
| **Proxy Rotation** | Suporte a proxies residenciais e datacenter |
| **Browser Fingerprint** | Playwright emula navegador real (Canvas, WebGL, fonts) |
| **Rate Limiting** | Limite de requisições por domínio respeitando robots.txt |
| **Session Management** | Cookies e sessões persistentes por domínio |
| **IP Rotation** | Troca de IP a cada N requisições (com provedor de proxy) |
| **JavaScript Execution** | Playwright executa JS igual a um navegador real |

---

## ☁️ Deploy na Nuvem

### 🟠 Oracle Cloud Free Tier (Recomendado — Gratuito Permanente)

Oracle oferece 2 VMs gratuitas para sempre com **4 OCPUs + 24GB RAM** total:

```bash
# 1. Crie conta em: https://signup.cloud.oracle.com
#    (não precisa de cartão, mas solicita verificação de identidade)

# 2. Crie instância: VM.Standard.A1.Flex (ARM)
#    - Shape: 2 OCPU, 12GB RAM
#    - OS: Ubuntu 22.04
#    - Adicione sua chave SSH pública

# 3. Configure Security List (equivalente ao firewall):
#    Ingress Rules: TCP 22, 80, 443, 8000, 3000, 5555

# 4. Conecte via SSH
ssh ubuntu@SEU_IP_ORACLE

# 5. Execute o script de setup
curl -sSL https://raw.githubusercontent.com/seu-usuario/webscraper/main/scripts/setup_vps.sh | bash
```

### 🔵 Hetzner Cloud (Mais Barato com Previsibilidade)

Hetzner oferece VPS a partir de €3.99/mês (CX22: 2 vCPU, 4GB RAM):

```bash
# 1. Crie conta: https://www.hetzner.com/cloud
#    Use código de referral para €20 de crédito

# 2. Crie servidor:
#    - Tipo: CX22 (2 vCPU, 4GB RAM) — suficiente para começar
#    - Local: Nuremberg (mais barato)
#    - OS: Ubuntu 22.04 LTS
#    - SSH Key: adicione sua chave pública

# 3. Configure firewall via Hetzner Console:
#    Adicionar regras de entrada: 22, 80, 443, 8000, 3000, 5555

# 4. Deploy
ssh root@SEU_IP_HETZNER
bash <(curl -sSL https://raw.githubusercontent.com/seu-usuario/webscraper/main/scripts/setup_vps.sh)
```

### 🟢 DigitalOcean / Vultr / Linode

Qualquer VPS com Ubuntu 22.04 funciona:

```bash
# Setup automático (script detecta Ubuntu 22.04)
bash scripts/setup_vps.sh

# Ou manualmente
cp .env.example .env
nano .env  # Configure senhas
make up
```

### Configurar HTTPS com Nginx + Let's Encrypt

```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx -y

# Criar configuração Nginx
sudo nano /etc/nginx/sites-available/webscraper

# Obter certificado SSL
sudo certbot --nginx -d api.seudominio.com -d app.seudominio.com

# Renovação automática já configurada pelo certbot
```

---

## 🧪 Testes

```bash
# Todos os testes
make test

# Apenas testes unitários (spiders, pipelines)
make test-unit

# Apenas testes da API
make test-api

# Com relatório de cobertura
make test-coverage
```

---

## 📁 Estrutura do Projeto

```
webscraper/
├── api/                    # FastAPI — API REST
│   ├── main.py             # Aplicação principal
│   ├── routes/             # Endpoints da API
│   ├── schemas/            # Modelos Pydantic
│   └── Dockerfile
├── worker/                 # Celery — Workers de scraping
│   ├── tasks.py            # Tasks Celery
│   ├── spiders/            # Implementações de spiders
│   ├── pipelines/          # Processamento de dados
│   └── Dockerfile
├── frontend/               # React + TypeScript
│   ├── src/
│   └── Dockerfile
├── database/               # PostgreSQL
│   ├── models.py           # Modelos SQLAlchemy
│   ├── migrations/         # Alembic migrations
│   └── connection.py
├── configs/                # Templates YAML de spiders
│   ├── generic.yml
│   ├── ecommerce.yml
│   ├── news.yml
│   ├── js_site.yml
│   └── api.yml
├── monitoring/             # Observabilidade
│   ├── grafana/            # Dashboards e datasources
│   ├── prometheus/         # Configuração e alertas
│   ├── loki/               # Agregação de logs
│   └── promtail/           # Coleta de logs
├── scripts/                # Automação
│   ├── setup_vps.sh        # Setup servidor do zero
│   ├── backup.sh           # Backup PostgreSQL
│   └── update.sh           # Atualização zero-downtime
├── tests/                  # Testes automatizados
│   ├── test_spiders.py
│   └── test_api.py
├── docker-compose.yml      # Definição dos serviços
├── .env.example            # Template de variáveis
├── Makefile                # Comandos facilitados
└── README.md               # Esta documentação
```

---

## 🔐 Hardening e Segurança

O backend agora inclui um conjunto de proteções ativas por padrão:

- `Rate limiting` global e por endpoint com `slowapi`
- `Security headers` em todas as respostas
- `TrustedHostMiddleware` para controlar hosts válidos
- `GZipMiddleware` para reduzir payload em respostas maiores
- `Cache-Control` explícito para endpoints de leitura e exportação

Variáveis úteis de segurança:

```bash
# Hosts permitidos (separados por vírgula)
API_ALLOWED_HOSTS=localhost,127.0.0.1,api.seu-dominio.com

# Rate limiting já ativo por default (200/min global)
# Limites específicos são definidos por rota
```

---

## ✅ CI/CD

Pipeline configurado em [.github/workflows/ci.yml](.github/workflows/ci.yml):

- Backend:
  - Instala dependências de `api`, `worker`, `scraper`
  - Lint com Ruff
  - Type-check com mypy
  - Testes com pytest
- Frontend:
  - `npm ci`
  - Type-check (`tsc --noEmit`)
  - Build de produção (`vite build`)

Deploy automático de produção em [.github/workflows/deploy.yml](.github/workflows/deploy.yml):

- Dispara automaticamente após `CI` bem-sucedida em `master/main`
- Também pode ser executado manualmente via `workflow_dispatch`
- No servidor, executa:
  - `git pull --ff-only`
  - restart de `webscraper-api`, `webscraper-worker`, `webscraper-scheduler`
  - build do frontend + sync de `dist`
  - `nginx -t` + `reload`
  - smoke test opcional da API

Secrets necessários no GitHub (Settings -> Secrets and variables -> Actions):

- `DEPLOY_HOST`: IP/DNS do servidor
- `DEPLOY_PORT`: porta SSH (opcional, default 22)
- `DEPLOY_USER`: usuário SSH com privilégios de deploy
- `DEPLOY_PASSWORD`: senha SSH desse usuário
- `DEPLOY_API_HEALTH_URL`: URL de health check pública (opcional)

Com esses secrets configurados, o deploy deixa de depender de execução manual via Codespace.

---

## 🧰 Operação

Scripts operacionais úteis:

- [scripts/backup.sh](scripts/backup.sh): backup PostgreSQL com retenção
- [scripts/update.sh](scripts/update.sh): atualização com rollback
- [scripts/healthcheck.sh](scripts/healthcheck.sh): verificação rápida da stack

Exemplo:

```bash
bash scripts/healthcheck.sh
```

---

## ☸️ Kubernetes (base)

Manifests iniciais em [k8s/api-deployment.yaml](k8s/api-deployment.yaml) e [k8s/worker-deployment.yaml](k8s/worker-deployment.yaml).

Aplicação de exemplo:

```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
```

---

## 🧪 Frontend QA

Ferramentas adicionadas no frontend:

- Error Boundary global para evitar crash total da SPA
- Vitest + Testing Library para testes de componentes
- ESLint para qualidade de código
- Storybook para documentação visual de componentes

Comandos:

```bash
cd frontend
npm run lint
npm run test
npm run storybook
```

---

## 🤝 Contribuição

1. Fork o repositório
2. Crie sua branch: `git checkout -b feature/nova-funcionalidade`
3. Commit suas mudanças: `git commit -m 'feat: adicionar nova funcionalidade'`
4. Push para a branch: `git push origin feature/nova-funcionalidade`
5. Abra um Pull Request

---

## 📝 Licença

Distribuído sob a licença MIT. Veja [`LICENSE`](LICENSE) para mais informações.

---

<div align="center">

Feito com ❤️ para a comunidade de dados

**[⬆ Voltar ao topo](#-webscraper-pro)**

</div>
