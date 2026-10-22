"""Assistente Playwright para copiar link da interface oficial de afiliados.

Exige sessão autenticada INTERATIVA em perfil próprio, não usa APIs privadas,
não faz login automatizado, bypass de CAPTCHA ou scraping de credenciais.
A interface pode mudar; fallback manual mantém o fluxo funcionando.
"""
from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlsplit

try:
    from ml_ingest import validate_url
except ModuleNotFoundError:
    from automation.ml_ingest import validate_url


HOME = "https://www.mercadolivre.com.br/"
AFFILIATE_CANDIDATES = re.compile(r"central de afiliados|afiliados e criadores|central de criadores", re.I)
GENERATOR_CANDIDATES = re.compile(r"gerador de links|gerar links|gerador de link", re.I)
SHARE_CANDIDATES = re.compile(r"compartilhar|gerar link", re.I)
COPY_CANDIDATES = re.compile(r"copiar link|copiar", re.I)


class AffiliateBrowserError(ValueError):
    pass


def validate_affiliate_result(text: str) -> str:
    value = text.strip().strip("<>").strip()
    if len(value) > 1600:
        raise AffiliateBrowserError("URL copiada é longa demais")
    try:
        validate_url(value)
    except ValueError as exc:
        raise AffiliateBrowserError("A área de transferência não tem um link HTTPS do Mercado Livre") from exc
    if not urlsplit(value).path or urlsplit(value).path == "/":
        raise AffiliateBrowserError("URL inválida: sem identificação de produto/link")
    return value


def _click_any(page, pattern, timeout_ms: int = 3500) -> bool:
    """Usa roles sem seletores frágeis; nunca tenta clicar fora do site."""
    for role in ("link", "button"):
        locator = page.get_by_role(role, name=pattern).first
        try:
            locator.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _clipboard(page) -> str:
    try:
        copied = page.evaluate("navigator.clipboard.readText()")
        if isinstance(copied, str):
            return validate_affiliate_result(copied)
    except Exception:
        pass
    # Fallback apenas em contexto de confirmação explícita pelo usuário.
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            return validate_affiliate_result(root.clipboard_get())
        finally:
            root.destroy()
    except (Exception,):
        return ""


def copy_affiliate_link(product_url: str, profile_dir: Path, *,
                        interactive: bool = True, browser_channel: str = "msedge",
                        cdp_url: str = "") -> str:
    """Abre HOME -> Central -> Gerador de links, tenta copiar o link aprovado.

    Se a UI não corresponder, a pessoa deve clicar e copiar no navegador aberto.
    O script NÃO lê senhas. O perfil contém cookies sensíveis e deve ser privado.
    """
    validate_url(product_url)
    if not interactive:
        raise AffiliateBrowserError("Para gerar link, a Central exige sessão interativa.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AffiliateBrowserError(
            "Instale Playwright: python -m pip install -r automation/requirements-browser.txt"
        ) from exc
    if cdp_url:
        from urllib.parse import urlsplit
        endpoint = urlsplit(cdp_url)
        if endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "localhost") or endpoint.port is None or endpoint.username or endpoint.password or endpoint.path not in ("", "/"):
            raise AffiliateBrowserError("CDP deve usar somente http://127.0.0.1:PORTA")
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url, timeout=9000)
            except Exception as exc:
                raise AffiliateBrowserError("CDP indisponível. Inicie Edge com porta e perfil dedicados.") from exc
            if not browser.contexts:
                raise AffiliateBrowserError("CDP sem contexto de navegador.")
            context = browser.contexts[0]
            page = context.new_page()
            try:
                return _affiliate_flow(page, context, product_url)
            finally:
                page.close()
                browser.close()
    profile_dir.mkdir(parents=True, exist_ok=True)
    # Só usa perfil SEPARADO e explicitamente dedicado; nunca carrega perfil pessoal.
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir.resolve()),
                headless=False, channel=browser_channel, accept_downloads=False,
            )
        except Exception as exc:
            raise AffiliateBrowserError("Navegador Edge não disponível. Instale Edge e Playwright, ou use --browser chromium.") from exc
        try:
            page = context.pages[0] if context.pages else context.new_page()
            return _affiliate_flow(page, context, product_url)
        finally:
            context.close()


def _page_is_allowed(page) -> bool:
    try:
        validate_url(page.url)
        return True
    except ValueError:
        return False


def _affiliate_flow(page, context, product_url: str) -> str:
    print("Abrindo página inicial do Mercado Livre no navegador separado...")
    page.goto(HOME, wait_until="domcontentloaded", timeout=35000)
    print("Faça login manualmente se necessário. Não forneça sua senha ao script.")
    input("Quando estiver na conta de afiliados, pressione Enter para continuar...")
    print("Tentando abrir Central de Afiliados...")
    if not _click_any(page, AFFILIATE_CANDIDATES, 4500):
        print("Não encontrei o botão Central de Afiliados automaticamente.")
        input("Clique em Central de Afiliados no navegador e pressione Enter...")
    # Pode abrir outra aba: confere abas cujo domínio é ML.
    pages = [p for p in context.pages if _page_is_allowed(p)]
    page = pages[-1] if pages else page
    print("Tentando acessar Gerador de Links na Central...")
    if not _click_any(page, GENERATOR_CANDIDATES, 4500):
        print("Gerador não encontrado. Selecione o produto e clique em Compartilhar.")
        input("Depois de abrir a janela do produto na Central, pressione Enter...")
        pages = [p for p in context.pages if _page_is_allowed(p)]
        page = pages[-1] if pages else page
        _click_any(page, SHARE_CANDIDATES, 3500)
    else:
        # Gerador oficial: cole a URL no campo visível; se não existir, fallback manual.
        field = page.get_by_role("textbox").first
        try:
            field.fill(product_url, timeout=3500)
            _click_any(page, re.compile(r"gerar|criar link", re.I), 3500)
        except Exception:
            print("Não foi possível preencher o gerador; preencha a URL manualmente.")
    previous_clipboard = _clipboard(page)
    clicked = _click_any(page, re.compile(r"^copiar link$", re.I), 2500)
    copied = _clipboard(page)
    if clicked and copied and copied != previous_clipboard:
        # Mesmo após cópia, confirmação humana específica antes da aprovação.
        return copied
    print("Copie o link pelo botão oficial 'Copiar link' no navegador.")
    input("Após copiar, pressione Enter para importar da área de transferência...")
    copied = _clipboard(page)
    if not copied:
        raise AffiliateBrowserError("Link não obtido. Use --affiliate-url com o link oficial copiado manualmente.")
    print("Confira o link no terminal antes de confirmar; ele pode ser de outro produto.")
    return copied
