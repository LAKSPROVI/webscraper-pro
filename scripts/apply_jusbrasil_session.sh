#!/usr/bin/env bash
# Aplica sessao autenticada do Jusbrasil no servidor e executa um smoke test.

set -euo pipefail

usage() {
  cat <<'EOF'
Uso:
  bash scripts/apply_jusbrasil_session.sh \
    --host 77.42.68.212 \
    --user webscraper \
    --state-file /caminho/local/storage_state.json \
    --api-url https://api-webscraper.jurislaw.com.br

Parametros obrigatorios:
  --host        Host do servidor
  --user        Usuario SSH
  --state-file  Arquivo local storage state JSON

Parametros opcionais:
  --api-url     URL publica da API para smoke test (padrao: sem teste)
  --env-file    Arquivo env remoto (padrao: /opt/webscraper-pro/env/.env.production)
  --remote-dir  Diretorio remoto para sessao (padrao: /opt/webscraper-pro/env/sessions)
  --ssh-port    Porta SSH (padrao: 22)

Observacoes:
  - Nao envia usuario/senha para o servidor, apenas o storage state.
  - Reinicia apenas webscraper-worker e webscraper-scheduler.
EOF
}

HOST=""
USER=""
STATE_FILE=""
API_URL=""
ENV_FILE="/opt/webscraper-pro/env/.env.production"
REMOTE_DIR="/opt/webscraper-pro/env/sessions"
SSH_PORT="22"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER="$2"; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    --api-url) API_URL="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
    --ssh-port) SSH_PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Argumento desconhecido: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [ -z "$HOST" ] || [ -z "$USER" ] || [ -z "$STATE_FILE" ]; then
  echo "Erro: --host, --user e --state-file sao obrigatorios." >&2
  usage
  exit 1
fi

if [ ! -f "$STATE_FILE" ]; then
  echo "Erro: arquivo nao encontrado: $STATE_FILE" >&2
  exit 1
fi

REMOTE_STATE_PATH="$REMOTE_DIR/jusbrasil.storage-state.json"
SSH_TARGET="$USER@$HOST"

echo "[1/5] Criando diretorio remoto de sessao..."
ssh -p "$SSH_PORT" "$SSH_TARGET" "mkdir -p '$REMOTE_DIR' && chmod 700 '$REMOTE_DIR'"

echo "[2/5] Enviando storage state para o servidor..."
scp -P "$SSH_PORT" "$STATE_FILE" "$SSH_TARGET:$REMOTE_STATE_PATH"

echo "[3/5] Ajustando permissoes do arquivo remoto..."
ssh -p "$SSH_PORT" "$SSH_TARGET" "chmod 600 '$REMOTE_STATE_PATH'"

echo "[4/5] Atualizando env e reiniciando services webscraper..."
ssh -p "$SSH_PORT" "$SSH_TARGET" "
  set -e
  touch '$ENV_FILE'
  if grep -q '^JUSBRASIL_STORAGE_STATE_PATH=' '$ENV_FILE'; then
    sed -i \"s|^JUSBRASIL_STORAGE_STATE_PATH=.*|JUSBRASIL_STORAGE_STATE_PATH=$REMOTE_STATE_PATH|\" '$ENV_FILE'
  else
    echo 'JUSBRASIL_STORAGE_STATE_PATH=$REMOTE_STATE_PATH' >> '$ENV_FILE'
  fi

  if grep -q '^JUSBRASIL_COOKIE_HEADER=' '$ENV_FILE'; then
    sed -i 's|^JUSBRASIL_COOKIE_HEADER=.*|JUSBRASIL_COOKIE_HEADER=|' '$ENV_FILE'
  fi

  if grep -q '^JUSBRASIL_COOKIES_JSON=' '$ENV_FILE'; then
    sed -i 's|^JUSBRASIL_COOKIES_JSON=.*|JUSBRASIL_COOKIES_JSON=|' '$ENV_FILE'
  fi

  sudo systemctl restart webscraper-worker webscraper-scheduler
  sudo systemctl --no-pager --full status webscraper-worker webscraper-scheduler | sed -n '1,20p'
"

if [ -n "$API_URL" ]; then
  echo "[5/5] Executando smoke test na API publica..."
  RESPONSE="$(curl -sS -X POST "$API_URL/api/v1/scrape" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://www.jusbrasil.com.br","spider_type":"jusbrasil","render_js":true,"use_proxy":false,"crawl_depth":1,"metadata":{"source":"session_script"}}')"

  echo "Resposta do scrape:"
  echo "$RESPONSE"
else
  echo "[5/5] Smoke test pulado (sem --api-url)."
fi

echo "Concluido. Sessao aplicada em: $REMOTE_STATE_PATH"
