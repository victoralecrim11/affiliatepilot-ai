#!/usr/bin/env python3
"""OAuth 2.0 Mercado Livre (Authorization Code + state + PKCE S256).

Inicie o login localmente com: python automation/ml_oauth.py login
O callback HTTPS do GitHub Pages apenas encaminha code/state ao loopback local.
O secret e os tokens ficam no cofre do sistema operacional via keyring.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import getpass
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
DEVELOPER_APPS_URL = "https://developers.mercadolivre.com.br/devcenter"
REDIRECT_URI = "https://victoralecrim11.github.io/garimpo-da-vez/oauth/callback/"
SERVICE = "garimpo-da-vez-mercadolivre-oauth"
ACCOUNT = "default"
CALLBACK_PORT = 8765
TIMEOUT_SECONDS = 240
EXPIRY_SKEW_SECONDS = 120
BASE_DIR = Path(__file__).resolve().parent


class OAuthError(Exception):
    """Erro claro, sem expor códigos, tokens ou segredos."""


def keyring_client():
    try:
        import keyring
        backend = keyring.get_keyring()
    except Exception as exc:
        raise OAuthError("Instale keyring e configure o cofre do sistema operacional.") from exc
    module = type(backend).__module__.lower()
    # Fail closed: nunca aceitar cofre de texto puro ou backend alternativo desconhecido.
    trusted = ("keyring.backends.windows", "keyring.backends.macos",
               "keyring.backends.secretservice", "keyring.backends.kwallet")
    if not module.startswith(trusted) or getattr(backend, "priority", 0) <= 0:
        raise OAuthError("Cofre seguro indisponível. No Windows, utilize Credential Manager; sem fallback plaintext.")
    return keyring


def read_credentials() -> dict | None:
    vault = keyring_client()
    try:
        raw = vault.get_password(SERVICE, ACCOUNT)
    except Exception as exc:
        raise OAuthError("Não foi possível acessar o cofre do sistema.") from exc
    if not raw:
        return None
    try:
        data = json.loads(raw)
        required = ("client_id", "client_secret", "access_token", "refresh_token", "expires_at")
        if not isinstance(data, dict) or any(not data.get(name) for name in required):
            raise ValueError("incompleto")
        return data
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OAuthError("Credenciais locais corrompidas; refaça auth login.") from exc


def save_credentials(data: dict) -> None:
    required = ("client_id", "client_secret", "access_token", "refresh_token", "expires_at")
    if any(not data.get(name) for name in required):
        raise OAuthError("Resposta OAuth incompleta: tokens não foram gravados.")
    vault = keyring_client()
    try:
        vault.set_password(SERVICE, ACCOUNT, json.dumps(data, ensure_ascii=False))
    except Exception as exc:
        raise OAuthError("Falha ao gravar no cofre seguro. Refazer login antes de nova renovação.") from exc


def delete_credentials() -> None:
    vault = keyring_client()
    try:
        vault.delete_password(SERVICE, ACCOUNT)
    except Exception as exc:
        raise OAuthError("Não foi possível remover a sessão do cofre.") from exc


def create_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(client_id: str, challenge: str, state: str) -> str:
    if not re.fullmatch(r"[0-9]{5,30}", client_id):
        raise OAuthError("Client ID inválido. Configure MERCADOLIVRE_CLIENT_ID no terminal.")
    return AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def exchange_token(payload: dict) -> dict:
    req = Request(TOKEN_URL, data=urlencode(payload).encode("ascii"), method="POST",
                  headers={"Content-Type": "application/x-www-form-urlencoded",
                           "Accept": "application/json", "User-Agent": "GarimpoDaVez-OAuth/1.0"})
    try:
        with urlopen(req, timeout=25) as response:
            result = json.loads(response.read(32_768).decode("utf-8"))
    except HTTPError as exc:
        # Não imprimir body, query, refresh_token ou código de autorização.
        raise OAuthError(f"Mercado Livre rejeitou a troca OAuth (HTTP {exc.code}); revise redirect URI e permissões.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OAuthError("Falha de rede na troca de tokens; confirme o estado da sessão antes de tentar novamente.") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthError("Resposta inválida do servidor OAuth.") from exc
    if not isinstance(result, dict):
        raise OAuthError("Resposta OAuth inesperada.")
    if not isinstance(result.get("access_token"), str) or not result["access_token"]:
        raise OAuthError("A API não retornou access_token.")
    if not isinstance(result.get("refresh_token"), str) or not result["refresh_token"]:
        raise OAuthError("A API não retornou novo refresh_token; é necessário novo login.")
    try:
        expires = int(result["expires_in"])
    except (ValueError, TypeError, KeyError) as exc:
        raise OAuthError("A API não retornou expires_in válido.") from exc
    if expires <= 0 or expires > 7 * 86400:
        raise OAuthError("Duração do token inesperada.")
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_at": int(time.time()) + expires,
        "user_id": result.get("user_id"),
        "scope": result.get("scope", ""),
    }


def parse_oauth_callback(path: str, state: str) -> str:
    parsed = urlsplit(path)
    if parsed.path != "/callback" or len(path) > 4096:
        raise OAuthError("Callback inválido.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if len(query.get("state", [])) != 1 or not hmac.compare_digest(query["state"][0], state):
        raise OAuthError("State ausente ou incorreto; autorização recusada.")
    if "error" in query:
        if "code" in query or len(query["error"]) != 1:
            raise OAuthError("Callback conflitante: contém código e erro.")
        raise OAuthError("Autorização negada/cancelada pelo Mercado Livre.")
    if len(query.get("code", [])) != 1 or not query["code"][0]:
        raise OAuthError("Código de autorização ausente.")
    if len(query["code"][0]) > 2048:
        raise OAuthError("Código de autorização inválido.")
    return query["code"][0]


def wait_for_local_callback(state: str, timeout: int = TIMEOUT_SECONDS, on_ready=None) -> str:
    class LocalServer(HTTPServer):
        allow_reuse_address = True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *args):
            # Nunca registrar o URL completo, que contém o código OAuth.
            return

        def do_GET(self):
            if self.headers.get("Host", "") not in {f"127.0.0.1:{CALLBACK_PORT}", f"localhost:{CALLBACK_PORT}"}:
                self.reply(400, "Host inválido.")
                return
            try:
                code = parse_oauth_callback(self.path, state)
            except OAuthError:
                self.reply(400, "Retorno inválido. Confira a janela do terminal e tente novamente.")
                return
            self.server.oauth_code = code
            self.reply(200, "Autorização recebida. Volte ao terminal do Garimpo da Vez.")

        def reply(self, status: int, message: str):
            data = ("<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
                    "<meta name='referrer' content='no-referrer'><title>Garimpo da Vez</title>"
                    "<p>" + message + "</p></html>").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'none'")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    try:
        server = LocalServer(("127.0.0.1", CALLBACK_PORT), Handler)
    except OSError as exc:
        raise OAuthError(f"Porta local {CALLBACK_PORT} indisponível. Encerre outro processo que a utiliza.") from exc
    with server:
        server.timeout = 1
        if on_ready is not None:
            on_ready()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            server.handle_request()
            if getattr(server, "oauth_code", None):
                return server.oauth_code
    raise OAuthError("Tempo de autorização esgotado. Refaça o login; nenhum token foi gravado.")


@contextmanager
def refresh_lock():
    # Um único processo pode consumir o Refresh Token rotativo.
    lock = BASE_DIR / "data" / ".ml-oauth-refresh.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OAuthError("OAuth em uso por outro processo. Verifique antes de remover um lock residual.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def refresh_access_token(force: bool = False) -> str:
    with refresh_lock():
        data = read_credentials()
        if data is None:
            raise OAuthError("Sessão não existe. Execute: python automation/ml_oauth.py login")
        if not force and int(data["expires_at"]) > time.time() + EXPIRY_SKEW_SECONDS:
            return data["access_token"]
        result = exchange_token({
            "grant_type": "refresh_token", "client_id": data["client_id"],
            "client_secret": data["client_secret"], "refresh_token": data["refresh_token"],
        })
        # Uma gravação do bundle inteiro; nunca reutilizar refresh_token anterior.
        new_data = dict(data, **result)
        save_credentials(new_data)
        return new_data["access_token"]


def get_access_token() -> str:
    # Compatibilidade: token explicitamente definido no processo tem prioridade.
    manual = os.environ.get("MERCADOLIVRE_ACCESS_TOKEN", "").strip()
    if manual:
        return manual
    data = read_credentials()
    if data is None:
        raise OAuthError("Sessão OAuth não configurada. Execute python automation/ml_oauth.py login.")
    if int(data["expires_at"]) > time.time() + EXPIRY_SKEW_SECONDS:
        return data["access_token"]
    return refresh_access_token()


def prompt_client_secret(*, no_browser: bool = False) -> str:
    """Abre o DevCenter antes de solicitar o secret, sem tentar lê-lo por API.

    Mesmo sem navegador, exibe a URL para acesso manual. Nenhuma chave é
    registrada em logs, parâmetros de URL ou no próprio repositório.
    """
    print("Abra o Mercado Livre Developers e acesse Minhas aplicações → Editar → Chave secreta:")
    print(DEVELOPER_APPS_URL)
    if not no_browser:
        try:
            opened = webbrowser.open(DEVELOPER_APPS_URL, new=2)
        except Exception:
            opened = False
        if not opened:
            print("Não foi possível abrir o navegador automaticamente. Use o link acima.")
    print("Copie somente o Client Secret e cole no terminal. Ele ficará oculto.")
    return getpass.getpass("Client Secret (não será exibido): ").strip()


def login(*, no_browser: bool = False, timeout: int = TIMEOUT_SECONDS) -> None:
    client_id = os.environ.get("MERCADOLIVRE_CLIENT_ID", "").strip()
    if not re.fullmatch(r"[0-9]{5,30}", client_id):
        raise OAuthError("Defina MERCADOLIVRE_CLIENT_ID com o App ID do Mercado Livre.")
    # Falhe antes de solicitar o segredo se o cofre seguro estiver indisponível.
    keyring_client()
    client_secret = os.environ.get("MERCADOLIVRE_CLIENT_SECRET", "").strip()
    if not client_secret:
        client_secret = prompt_client_secret(no_browser=no_browser)
    if not client_secret:
        raise OAuthError("Client Secret não informado.")
    verifier, challenge = create_pkce()
    state = secrets.token_urlsafe(32)
    url = authorization_url(client_id, challenge, state)
    print("Abra esta URL para autorizar o aplicativo na conta principal do Mercado Livre:")
    print(url)
    print(f"Aguardando callback no computador (127.0.0.1:{CALLBACK_PORT}), por até {timeout}s.")
    code = wait_for_local_callback(state, timeout, on_ready=(lambda: webbrowser.open(url)) if not no_browser else None)
    result = exchange_token({
        "grant_type": "authorization_code", "client_id": client_id,
        "client_secret": client_secret, "code": code,
        "redirect_uri": REDIRECT_URI, "code_verifier": verifier,
    })
    save_credentials({"client_id": client_id, "client_secret": client_secret, **result})
    print("Mercado Livre autorizado e credenciais protegidas no cofre do sistema.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OAuth local Garimpo da Vez / Mercado Livre")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("login", help="Autoriza a aplicação com PKCE e callback local")
    start.add_argument("--no-browser", action="store_true", help="Apenas mostra a URL, sem abrir navegador")
    start.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS)
    commands.add_parser("status", help="Exibe somente o status; não mostra tokens")
    commands.add_parser("refresh", help="Renovação manual; também ocorre automaticamente na consulta")
    commands.add_parser("logout", help="Remove credenciais do cofre local")
    args = parser.parse_args(argv)
    if args.command == "login":
        if not 30 <= args.timeout <= 600:
            raise OAuthError("O timeout deve estar entre 30 e 600 segundos.")
        login(no_browser=args.no_browser, timeout=args.timeout)
    elif args.command == "status":
        data = read_credentials()
        if not data:
            print("Não autorizado. Execute 'login'.")
        else:
            ttl = int(data["expires_at"]) - int(time.time())
            print(f"Conta autorizada | App ID: {data['client_id']} | token {'válido' if ttl > EXPIRY_SKEW_SECONDS else 'expirado/quase expirado'}")
            print("A renovação ocorrerá quando o token vencer (sem mostrar credenciais).")
    elif args.command == "refresh":
        refresh_access_token(force=True)
        print("Access Token e Refresh Token renovados no cofre seguro.")
    elif args.command == "logout":
        delete_credentials()
        print("Credenciais locais excluídas do cofre. Revogue o app no Mercado Livre se necessário.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OAuthError, KeyboardInterrupt) as exc:
        print("ERRO:", str(exc) if isinstance(exc, OAuthError) else "Interrompido.", file=sys.stderr)
        sys.exit(1)
