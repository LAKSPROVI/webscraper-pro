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
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa navegador sem interface grafica",
    )
    parser.add_argument(
        "--auto-login",
        action="store_true",
        help="Tenta login automatico com JUSBRASIL_EMAIL e JUSBRASIL_PASSWORD",
    )
    parser.add_argument(
        "--proxy-server",
        default="",
        help="Proxy Playwright no formato protocolo://host:porta",
    )
    parser.add_argument(
        "--proxy-username",
        default="",
        help="Usuario do proxy (opcional)",
    )
    parser.add_argument(
        "--proxy-password",
        default="",
        help="Senha do proxy (opcional)",
    )
    return parser.parse_args()


def _build_proxy_config(args: argparse.Namespace) -> dict[str, str] | None:
    server = (args.proxy_server or os.getenv("JUSBRASIL_PLAYWRIGHT_PROXY_SERVER", "")).strip()
    username = (args.proxy_username or os.getenv("JUSBRASIL_PLAYWRIGHT_PROXY_USERNAME", "")).strip()
    password = (args.proxy_password or os.getenv("JUSBRASIL_PLAYWRIGHT_PROXY_PASSWORD", "")).strip()

    if not server:
        host = os.getenv("BRIGHTDATA_PROXY_HOST", "").strip()
        port = os.getenv("BRIGHTDATA_PROXY_PORT", "").strip()
        if host and port:
            server = f"http://{host}:{port}"
        if not username:
            username = os.getenv("BRIGHTDATA_PROXY_USER", "").strip()
        if not password:
            password = os.getenv("BRIGHTDATA_PROXY_PASS", "").strip()

    if not server:
        return None

    parsed = urlparse(server)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        raise ValueError("Proxy inválido. Use formato protocolo://host:porta")

    proxy: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy


def _try_auto_login(page: Any, timeout_ms: int) -> bool:
    email = os.getenv("JUSBRASIL_EMAIL", "").strip()
    password = os.getenv("JUSBRASIL_PASSWORD", "").strip()

    if not email or not password:
        print("Auto-login habilitado, mas variaveis JUSBRASIL_EMAIL/JUSBRASIL_PASSWORD estao vazias.")
        return False

    print("Tentando login automatico com variaveis de ambiente...")

    # Seletores comuns para fluxo de login web.
    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[id*="email"]',
        'input[autocomplete="username"]',
    ]
    password_selectors = [
        'input[type="password"]',
        'input[name="password"]',
        'input[id*="senha"]',
        'input[autocomplete="current-password"]',
    ]
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Entrar")',
        'button:has-text("Login")',
    ]

    email_field = None
    for sel in email_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            email_field = loc.first
            break

    password_field = None
    for sel in password_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            password_field = loc.first
            break

    if email_field is None or password_field is None:
        print("Nao foi possivel localizar campos de login automaticamente.")
        return False

    email_field.fill(email)
    password_field.fill(password)

    submitted = False
    for sel in submit_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            submitted = True
            break

    if not submitted:
        password_field.press("Enter")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        print("Timeout apos tentativa de submit. Prosseguindo para validacao de sessao.")

    return True


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    proxy_config = _build_proxy_config(args)

    print("Abrindo navegador para login manual no Jusbrasil...")
    if proxy_config:
        print(f"Usando proxy fixo para exportacao: {proxy_config['server']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context_kwargs: dict[str, Any] = {"locale": "pt-BR"}
        if proxy_config:
            context_kwargs["proxy"] = proxy_config
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            page.goto(args.start_url, wait_until="domcontentloaded")

            auto_done = False
            if args.auto_login:
                auto_done = _try_auto_login(page, args.timeout)

            if not auto_done:
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
