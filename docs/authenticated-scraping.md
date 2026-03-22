# Authenticated Scraping Strategy

Este projeto suporta estrategia especifica para sites com assinatura legitima do cliente, como portais juridicos com area autenticada.

## Diretriz

Use sempre uma sessao autenticada fornecida pelo proprio assinante.
Nao dependa de automacao de login, quebra de captcha, bypass de MFA ou evasao de protecoes de acesso.

## Estrategia recomendada

1. Autenticar manualmente no navegador com a conta do assinante.
2. Exportar o estado autenticado do navegador.
3. Reutilizar esse estado no scraping via Playwright ou cookies HTTP.
4. Manter afinidade de sessao:
   - mesma conta
   - mesmo perfil de navegador
   - preferencialmente o mesmo IP/sessao de proxy residencial
5. Renovar o estado autenticado quando a sessao expirar.

## Variaveis suportadas para Jusbrasil

- `JUSBRASIL_STORAGE_STATE_PATH`
  - caminho para um arquivo `storage_state.json` exportado do Playwright/browser.
- `JUSBRASIL_COOKIES_JSON`
  - JSON com cookies autenticados.
- `JUSBRASIL_COOKIE_HEADER`
  - header `Cookie` pronto para requests HTTP sem JS.
- `JUSBRASIL_EXTRA_HEADERS_JSON`
  - headers extras em JSON para reproduzir melhor a sessao autenticada.

## Uso pratico

### Gerar storage state local (login manual)

1. Instalar browser do Playwright (uma vez):

```bash
.venv/bin/python -m playwright install chromium
```

2. Gerar sessao autenticada com login manual:

```bash
.venv/bin/python scripts/export_jusbrasil_storage_state.py \
  --output sessions/jusbrasil.storage-state.json
```

3. O script abre navegador visivel para voce logar manualmente.
4. Depois do login (e MFA, se houver), volte ao terminal e pressione ENTER.
5. O arquivo `sessions/jusbrasil.storage-state.json` sera criado para uso no deploy.

### Request via API

Exemplo de request com spider dedicado:

```json
{
  "url": "https://www.jusbrasil.com.br",
  "spider_type": "jusbrasil",
  "render_js": true,
  "use_proxy": false,
  "crawl_depth": 1,
  "metadata": {
    "source": "authenticated_session_test"
  }
}
```

### Configuracao operacional

1. Subir `storage_state.json` apenas no servidor.
2. Referenciar o caminho em `JUSBRASIL_STORAGE_STATE_PATH` no ambiente do worker.
3. Reiniciar apenas os services `webscraper-*`.
4. Rodar o teste no endpoint de scrape.

### Automacao via script

Use o script operacional para aplicar sessao e testar em uma execucao:

```bash
bash scripts/apply_jusbrasil_session.sh \
  --host 77.42.68.212 \
  --user webscraper \
  --state-file sessions/jusbrasil.storage-state.json \
  --api-url https://api.77.42.68.212.nip.io
```

O script executa:
1. Upload seguro do `storage_state.json` para `/opt/webscraper-pro/env/sessions/`.
2. Atualizacao de `JUSBRASIL_STORAGE_STATE_PATH` no `.env.production` remoto.
3. Reinicio de `webscraper-worker` e `webscraper-scheduler`.
4. Disparo de um smoke test no endpoint `POST /api/v1/scrape`.

## Observacoes

- Se o site devolver 403 mesmo com sessao valida, o proximo passo e ajustar sequencia de warm-up da sessao e afinidade de IP.
- Se houver conteudo disponivel apenas apos navegacao interna, o spider deve visitar primeiro home, busca ou pagina intermediaria antes da URL alvo.
- `render_js=true` costuma ser o modo mais consistente para conteudo autenticado.