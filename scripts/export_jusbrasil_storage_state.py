#!/usr/bin/env python3
"""Gera storage state autenticado do Jusbrasil via login manual.

Fluxo:
1. Abre navegador visivel.
2. Usuario faz login manual (incluindo MFA, se houver).
3. Usuario confirma no terminal.
4. Script salva storage_state JSON para uso no worker.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta storage state autenticado do Jusbrasil",
    )
    parser.add_argument(
        "--output",
        default="sessions/jusbrasil.storage-state.json",
        help="Arquivo de saida do storage state",
    )
    parser.add_argument(
        "--start-url",
        default="https://www.jusbrasil.com.br/login",
        help="URL inicial para abrir no navegador",
    )
    parser.add_argument(
        "--post-login-url",
        default="https://www.jusbrasil.com.br",
        help="URL esperada apos login para validacao simples",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180000,
        help="Timeout em milissegundos para espera de navegacao apos login",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Abrindo navegador para login manual no Jusbrasil...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="pt-BR")
        page = context.new_page()

        try:
            page.goto(args.start_url, wait_until="domcontentloaded")
            print("\nFaca login manualmente no navegador aberto.")
            print("Depois de concluir login e abrir uma pagina autenticada, volte ao terminal.")
            input("Pressione ENTER para continuar e salvar a sessao... ")

            try:
                page.goto(args.post_login_url, wait_until="domcontentloaded", timeout=args.timeout)
            except PlaywrightTimeoutError:
                print("Aviso: timeout ao abrir URL de validacao. Continuando para salvar sessao.")

            context.storage_state(path=str(output_path))
            print(f"\nSessao salva com sucesso em: {output_path}")
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
