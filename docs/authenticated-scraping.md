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

## Observacoes

- Se o site devolver 403 mesmo com sessao valida, o proximo passo e ajustar sequencia de warm-up da sessao e afinidade de IP.
- Se houver conteudo disponivel apenas apos navegacao interna, o spider deve visitar primeiro home, busca ou pagina intermediaria antes da URL alvo.
- `render_js=true` costuma ser o modo mais consistente para conteudo autenticado.