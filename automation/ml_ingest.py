"""Importação supervisionada de anúncio ML por URL, sem scrapers nem dados fictícios.

Prioridade: API oficial /items/{id}. Se houver HTTP 403, metatags públicas
podem fornecer dados PARCIAIS, sempre marcados como não verificados.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

MAX_PAGE_BYTES = 1_500_000
MAX_IMAGE_BYTES = 15 * 1024 * 1024
ML_API = "https://api.mercadolibre.com/items/"
ITEM_REGEX = re.compile(r"(?<![A-Za-z0-9])MLB[-_]?([0-9]{6,18})(?![0-9])", re.I)


class IngestError(ValueError):
    pass


def _host_allowed(host: str, *, image: bool = False) -> bool:
    host = host.lower().rstrip(".")
    if image:
        return host == "mlstatic.com" or host.endswith(".mlstatic.com")
    return host in ("meli.la", "mercadolivre.com.br", "mercadolibre.com.br") or host.endswith(
        (".mercadolivre.com.br", ".mercadolibre.com.br")
    )


def validate_url(url: str, *, image: bool = False) -> str:
    try:
        p = urlsplit(url.strip())
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError as exc:
        raise IngestError("URL inválida") from exc
    if p.scheme != "https" or not _host_allowed(host, image=image) or p.username or p.password or port not in (None, 443):
        raise IngestError("URL fora dos domínios HTTPS permitidos do Mercado Livre")
    return url.strip()


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, *, image=False):
        self.image = image

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, image=self.image)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, *, image=False, max_bytes=MAX_PAGE_BYTES) -> tuple[str, bytes, str]:
    validate_url(url, image=image)
    opener = build_opener(_SafeRedirect(image=image))
    req = Request(url, headers={
        "User-Agent": "GarimpoDaVez/1.2 (curadoria autorizada)",
        "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*" if image else "text/html,application/xhtml+xml",
    })
    try:
        with opener.open(req, timeout=18) as response:
            final = validate_url(response.geturl(), image=image)
            content_type = (response.headers.get("Content-Type") or "").lower().split(";")[0]
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        code = getattr(exc, "code", "")
        raise IngestError(f"Não foi possível acessar página/imagem pública (HTTP {code or 'rede'})") from exc
    if len(data) > max_bytes:
        raise IngestError("Recurso remoto acima do tamanho permitido")
    return final, data, content_type


def extract_item_id(url: str) -> str:
    """Não confundir /p/MLB123 com anúncio individual (catálogo)."""
    p = urlsplit(url)
    path = p.path
    if re.search(r"/p/MLB[-_]?\d+", path, re.I):
        return ""
    match = ITEM_REGEX.search(path)
    return "MLB" + match.group(1) if match else ""


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self.page_title = ""
        self._title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == "title":
            self._title = True
        if tag.lower() != "meta":
            return
        name = (a.get("property") or a.get("name") or "").lower()
        if name in ("og:title", "og:image", "og:description", "description", "product:price:amount"):
            self.values[name] = a.get("content", "")[:1200]

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._title = False

    def handle_data(self, data):
        if self._title:
            self.page_title += data[:200]


def infer_category(title: str) -> str | None:
    t = title.casefold()
    candidates = {
        "tecnologia": ("notebook", "ssd", "monitor", "mouse", "teclado", "fone", "smartphone", "carregador", "gamer"),
        "casa": ("refletor", "quadro", "luminária", "tapete", "sofá", "jardim", "decor", "cortina"),
        "organizacao": ("organizador", "prateleira", "caixa organizadora", "suporte", "gaveta"),
        "lifestyle": ("bolsa", "mochila", "roupa", "fitness", "acessório"),
    }
    matches = [cat for cat, terms in candidates.items() if any(term in t for term in terms)]
    return matches[0] if len(matches) == 1 else None


def _official_item(item_id: str, *, token: str | None) -> dict | None:
    if not item_id:
        return None
    hdr = {"Accept": "application/json", "User-Agent": "GarimpoDaVez/1.2"}
    if token:
        hdr["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(ML_API + item_id, headers=hdr), timeout=17) as response:
            payload = response.read(750_000)
        obj = json.loads(payload)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get("id") != item_id:
        return None
    return obj


def get_product_metadata(url: str, *, token: str | None = None) -> dict:
    """Consulta página pública e API oficial; NÃO promete acesso a anúncios de terceiros."""
    url = validate_url(url)
    result = {
        "source_url": url, "resolved_url": url, "item_id": extract_item_id(url),
        "title": "", "summary": "", "image_url": "", "category": "",
        "ml_category_id": "",
        "metadata_verified": False, "metadata_source": "unavailable", "warnings": [],
    }
    # Resolve redirects (including meli.la), without following links outside ML.
    html = ""
    try:
        final, raw, ct = _download(url)
        result["resolved_url"] = final
        result["item_id"] = extract_item_id(final) or result["item_id"]
        if "html" in ct or (not ct and b"<html" in raw[:600].lower()):
            html = raw.decode("utf-8", errors="replace")
    except IngestError:
        result["warnings"].append("Página pública indisponível; a API oficial ainda será tentada.")

    obj = _official_item(result["item_id"], token=token)
    if obj and obj.get("status") == "active" and isinstance(obj.get("title"), str):
        result["title"] = obj["title"].strip()[:100]
        result["summary"] = "Confira detalhes e especificações do anúncio antes da compra."
        photos = obj.get("pictures") or []
        image_url = photos[0].get("secure_url") if photos and isinstance(photos[0], dict) else None
        result["image_url"] = image_url or obj.get("secure_thumbnail") or ""
        result["metadata_verified"] = True
        result["metadata_source"] = "official_api"
        category_id = obj.get("category_id")
        if isinstance(category_id, str) and re.fullmatch(r"MLB[0-9]{2,12}", category_id):
            result["ml_category_id"] = category_id
    elif obj and obj.get("status") != "active":
        result["warnings"].append("Anúncio não está ativo segundo a API; dados devem ser revisados.")
    if not result["metadata_verified"] and html:
        parser = _MetaParser()
        parser.feed(html)
        meta = parser.values
        result["title"] = (meta.get("og:title") or parser.page_title).strip()[:100]
        result["summary"] = (meta.get("og:description") or meta.get("description") or "")[:400]
        result["image_url"] = meta.get("og:image") or ""
        result["metadata_source"] = "public_page_unverified"
        result["warnings"].append("Metadados da página pública não equivalem a verificação da API.")
    if not result["item_id"]:
        result["warnings"].append("Nenhum ID de anúncio individual identificado (URL pode ser de catálogo).")
    if not result["title"]:
        result["warnings"].append("Título não encontrado; informe-o manualmente antes de preparar.")
    cat = infer_category(result["title"])
    result["category"] = cat or ""
    if not cat:
        result["warnings"].append("Categoria não foi identificada com confiança; selecione manualmente.")
    return result


def download_product_image(url: str, target_dir: Path, slug: str) -> Path:
    """Somente após confirmação explícita de direitos de uso; sem hotlink ou terceiros."""
    from PIL import Image, ImageOps
    _, raw, _ = _download(url, image=True, max_bytes=MAX_IMAGE_BYTES)
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im)
            im.load()
            if im.width * im.height > 35_000_000 or im.width < 180 or im.height < 180:
                raise IngestError("Dimensões de imagem não permitidas")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{slug}.png"
            # Remove metadados; normaliza formatos WebP/JPG/PNG para PNG.
            im.convert("RGB").save(target, "PNG", optimize=True)
            return target
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise IngestError("Imagem não suportada ou corrompida") from exc


def local_id(metadata: dict) -> str:
    return (metadata.get("item_id") or ("url-" + hashlib.sha256(metadata["source_url"].encode()).hexdigest()[:12])).lower()
