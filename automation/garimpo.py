#!/usr/bin/env python3
"""Garimpo da Vez: drafts and individual authorized Pinterest Pin publishing.

No scraping, no automatic purchasing/link generation and no unattended publishing.
Python 3.11+; only Pillow is needed for branded image generation.
"""
from __future__ import annotations

import argparse
import base64
import csv
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STORE = BASE_DIR / "data" / "pins.json"
DEFAULT_OUT = BASE_DIR / "out"
PINTEREST_API = "https://api.pinterest.com/v5"
MERCADOLIVRE_ITEMS_API = "https://api.mercadolibre.com/items/"
DISCLOSURE = "Este conteúdo contém link de afiliado. Posso receber comissão por compras elegíveis."
CATEGORIES = {
    "casa": "CASA & DECORAÇÃO",
    "tecnologia": "TECNOLOGIA & SETUP",
    "organizacao": "ORGANIZAÇÃO & UTILIDADES",
    "lifestyle": "ACESSÓRIOS & LIFESTYLE",
}
CSV_FIELDS = ("id", "title", "category", "summary", "affiliate_url", "image_path", "image_license_confirmed")


class GarimpoError(Exception):
    """An actionable input, state or API error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_https_affiliate_link(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise GarimpoError("URL de afiliado inválida") from exc
    allowed = host in {"meli.la", "mercadolivre.com.br", "www.mercadolivre.com.br"} or host.endswith(".mercadolivre.com.br")
    if parsed.scheme != "https" or not allowed or parsed.path in {"", "/"} or parsed.username or parsed.password:
        raise GarimpoError("Use um link HTTPS real e gerado pelo Mercado Livre (domínio meli.la ou mercadolivre.com.br)")
    return candidate


def validate_row(row: dict[str, str], csv_dir: Path) -> dict:
    for key in CSV_FIELDS:
        if not (row.get(key) or "").strip():
            raise GarimpoError(f"Coluna obrigatória vazia: {key}")
    id_ = row["id"].strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,49}", id_):
        raise GarimpoError("id deve conter 2 a 50 caracteres ASCII: letras, números, '_' ou '-'")
    title = " ".join(row["title"].split())
    summary = " ".join(row["summary"].split())
    cat = row["category"].strip().lower()
    if cat not in CATEGORIES:
        raise GarimpoError(f"category inválida: use {', '.join(CATEGORIES)}")
    if len(title) > 100 or len(title) < 5:
        raise GarimpoError("title deve conter entre 5 e 100 caracteres")
    if len(summary) > 560 or len(summary) < 15:
        raise GarimpoError("summary deve conter entre 15 e 560 caracteres")
    if row["image_license_confirmed"].strip().lower() not in {"sim", "yes", "true", "1"}:
        raise GarimpoError("Confirme os direitos de uso da imagem: image_license_confirmed=sim")
    image = Path(row["image_path"].strip()).expanduser()
    if not image.is_absolute():
        image = csv_dir / image
    image = image.resolve()
    if not image.is_file() or image.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise GarimpoError(f"Imagem inexistente ou formato inválido: {image}")
    if image.stat().st_size > 18 * 1024 * 1024:
        raise GarimpoError("Imagem acima de 18 MiB; reduza o arquivo antes de importar")
    desc = summary + "\n\n" + DISCLOSURE
    if len(desc) > 800:
        raise GarimpoError("Descrição final excedeu 800 caracteres")
    item_id = (row.get("item_id") or "").strip().upper()
    if item_id and not re.fullmatch(r"MLB[0-9]{6,18}", item_id):
        raise GarimpoError("item_id inválido: use um ID de anúncio MLB numérico e real")
    return {
        "id": id_,
        "item_id": item_id,
        "ml_verification": None,
        "title": title,
        "description": desc,
        "category": cat,
        "affiliate_url": ensure_https_affiliate_link(row["affiliate_url"]),
        "affiliate_url_confirmed": True,
        "affiliate_link_source": "csv_manual",
        "affiliate_confirmed_at": now_iso(),
        "image_license_confirmed": True,
        "image_path": str(image),
        "status": "draft",
        "board_id": "",
        "preview_path": "",
        "approval_sha256": "",
        "pin_id": "",
        "created_at": now_iso(),
    }


def load_store(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "pins": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GarimpoError(f"Não foi possível ler a fila {path}: {exc}") from exc
    if data.get("version") != 1 or not isinstance(data.get("pins"), dict):
        raise GarimpoError("Formato de fila incompatível")
    return data


def save_store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace limits partial writes; file stays local and is gitignored.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".queue_", suffix=".tmp", delete=False) as fp:
        tmp_path = Path(fp.name)
        json.dump(data, fp, indent=2, ensure_ascii=False)
        fp.write("\n")
        fp.flush()
        os.fsync(fp.fileno())
    try:
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def import_csv(csv_path: Path, store_path: Path) -> int:
    csv_path = csv_path.resolve()
    with csv_path.open(encoding="utf-8-sig", newline="") as fp:
        # Ignore empty/whitespace-only lines, including those before the header.
        reader = csv.DictReader(line for line in fp if line.strip())
        if not reader.fieldnames or not set(CSV_FIELDS).issubset(set(reader.fieldnames)):
            raise GarimpoError("CSV deve conter: " + ", ".join(CSV_FIELDS))
        pending = {}
        for i, row in enumerate(reader, start=2):
            try:
                entry = validate_row(row, csv_path.parent)
            except GarimpoError as exc:
                raise GarimpoError(f"CSV linha {i}: {exc}") from exc
            if entry["id"] in pending:
                raise GarimpoError(f"ID duplicado no CSV: {entry['id']}")
            pending[entry["id"]] = entry
    state = load_store(store_path)
    conflicts = set(pending) & set(state["pins"])
    if conflicts:
        raise GarimpoError("IDs já existentes na fila (nunca sobrescrevemos aprovações): " + ", ".join(sorted(conflicts)))
    state["pins"].update(pending)
    save_store(store_path, state)
    return len(pending)


def fetch_mercadolivre_item(item_id: str, *, token: str | None = None) -> dict:
    """Confere os metadados de UM anúncio na API oficial; não cria links de afiliado.

    Precisa de um token autorizado para os recursos do Mercado Livre.
    Os dados são uma fotografia momentânea e não atestam elegibilidade a comissões.
    """
    if not re.fullmatch(r"MLB[0-9]{6,18}", item_id):
        raise GarimpoError("item_id inválido. Exemplo de formato: MLB123456789")
    if token is None:
        token = os.environ.get("MERCADOLIVRE_ACCESS_TOKEN", "")
        if not token:
            try:
                from ml_oauth import get_access_token, OAuthError
            except ModuleNotFoundError:
                from automation.ml_oauth import get_access_token, OAuthError
            try:
                token = get_access_token()
            except OAuthError as exc:
                raise GarimpoError("MERCADOLIVRE_ACCESS_TOKEN ausente e OAuth indisponível: " + str(exc)) from exc
    req = Request(MERCADOLIVRE_ITEMS_API + item_id, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "User-Agent": "GarimpoDaVez/1.1 (authorized read-only item check)",
    })
    try:
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read(500_000).decode("utf-8"))
    except HTTPError as exc:
        raise GarimpoError(f"Mercado Livre HTTP {exc.code}; verifique token, escopos e ID do item") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GarimpoError(f"Conexão com Mercado Livre falhou: {type(exc).__name__}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GarimpoError("Mercado Livre retornou resposta inválida") from exc
    if not isinstance(data, dict) or data.get("id") != item_id:
        raise GarimpoError("A API não confirmou o ID do anúncio solicitado")
    if data.get("status") != "active":
        raise GarimpoError(f"Anúncio não ativo: {data.get('status', 'desconhecido')}")
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise GarimpoError("A API não retornou título verificável")
    # Campos descritivos vêm da API; NÃO substituir o link rastreado oficial.
    return {
        "item_id": item_id,
        "title": title.strip(),
        "status": "active",
        "price": data.get("price") if isinstance(data.get("price"), (int, float)) and not isinstance(data.get("price"), bool) else None,
        "currency_id": data.get("currency_id") if isinstance(data.get("currency_id"), str) else None,
        "checked_at": now_iso(),
    }


@contextmanager
def exclusive_publish_lock(store: Path):
    """Evita dois processos locais dispararem a mesma publicação simultaneamente.

    Lock residual após uma queda deve ser removido MANUALMENTE após conciliar no Pinterest.
    """
    lock = Path(str(store.resolve()) + ".publish.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise GarimpoError(f"Outra publicação pode estar em andamento: {lock}. Não apague sem conferir o Pinterest.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(f"PID {os.getpid()} - {now_iso()}\\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def publish_one_approved(store: Path, id_: str) -> None:
    """Reserva, publica UMA vez e persiste estado para conciliação de falhas."""
    if not os.environ.get("PINTEREST_ACCESS_TOKEN"):
        raise GarimpoError("Falta PINTEREST_ACCESS_TOKEN (OAuth oficial Pinterest).")
    with exclusive_publish_lock(store):
        state = load_store(store)
        pin = get_pin(state, id_)
        if pin["status"] != "approved" or fingerprint(pin) != pin["approval_sha256"]:
            raise GarimpoError("Aprovação ausente ou conteúdo modificado. Prepare e aprove novamente.")
        pin["status"] = "publishing"
        save_store(store, state)
        try:
            approved_snapshot = dict(pin)
            approved_snapshot["status"] = "approved"
            result = publish_pin(approved_snapshot)
            if not result.get("id"):
                raise GarimpoError("Resposta sem ID; confira manualmente no Pinterest antes de nova tentativa")
            pin["status"] = "published"
            pin["pin_id"] = str(result["id"])
            pin["published_at"] = now_iso()
        except Exception:
            # O sucesso remoto pode ter ocorrido antes da falha local.
            pin["status"] = "needs_check"
            save_store(store, state)
            raise
        save_store(store, state)
        print(f"Pin publicado: https://www.pinterest.com/pin/{pin['pin_id']}/")


def get_pin(state: dict, id_: str) -> dict:
    pin = state["pins"].get(id_)
    if not pin:
        raise GarimpoError(f"Pin '{id_}' não existe na fila")
    return pin


def load_font(size: int, bold: bool = True):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise GarimpoError("Instale Pillow: python -m pip install -r automation/requirements.txt") from exc
    names = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default(size=size)


def text_lines(text: str, font, draw, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
            if draw.textbbox((0, 0), current, font=font)[2] > max_width:
                raise GarimpoError(f"Palavra longa demais para o design: {word}")
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise GarimpoError("Título longo demais para o layout. Use um título mais curto no CSV.")
    return lines


def prepare_image(pin: dict, out_dir: Path, *, style: str = "editorial",
                  source: str = "best") -> Path:
    """Prepare a truthful 2:3 image; editorial is photo-only, branded opt-in.

    Never invent portions of the actual product; a softened copy of the source
    photograph fills unused edges. Product itself is always contained uncut.
    """
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
    except ImportError as exc:
        raise GarimpoError("Pillow ausente. Instale com: python -m pip install -r automation/requirements.txt") from exc
    if style not in {"editorial", "branded"}:
        raise GarimpoError("Estilo válido: editorial ou branded")
    if source not in {"best", "original"}:
        raise GarimpoError("Fonte válida: best ou original")
    if pin.get("image_license_confirmed") is not True:
        raise GarimpoError("Confirme direitos de uso comercial da imagem antes de preparar.")
    source_path = pin.get("image_path") if source == "original" else (
        pin.get("stylized_image_path") or pin.get("image_path"))
    if not source_path:
        raise GarimpoError("Sem imagem de origem; use review --image-file ou ingest-url.")
    inp = Path(source_path)
    if not inp.is_file():
        raise GarimpoError("Imagem de origem não encontrada: " + str(inp))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{pin['id']}.jpg"
    try:
        with Image.open(inp) as img:
            img = ImageOps.exif_transpose(img)
            img.load()
            if img.width * img.height > 35_000_000:
                raise GarimpoError("Imagem de origem acima do limite de pixels")
            photo = img.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise GarimpoError(f"Imagem inválida: {exc}") from exc

    if style == "editorial":
        # No text, watermark, stickers, fake product features or brand header.
        # Preserve the entire reference frame in the foreground (no cutting).
        canvas = ImageOps.fit(photo, (1000, 1500), Image.Resampling.LANCZOS)
        canvas = canvas.filter(ImageFilter.GaussianBlur(42))
        canvas = ImageEnhance.Brightness(canvas).enhance(0.87)
        foreground = ImageOps.contain(photo, (1000, 1500), Image.Resampling.LANCZOS)
        x = (1000 - foreground.width) // 2
        y = (1500 - foreground.height) // 2
        canvas.paste(foreground, (x, y))
    else:
        # Legacy visual retained only when explicitly requested.
        canvas = Image.new("RGB", (1000, 1500), "#F5EFE3")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 1000, 205), fill="#244E46")
        draw.text((66, 60), "GARIMPO DA VEZ", font=load_font(48), fill="#F5EFE3")
        draw.text((67, 130), "ACHADOS ÚTEIS PARA A VIDA REAL",
                  font=load_font(20), fill="#D69A72")
        draw.rounded_rectangle((52, 250, 948, 1090), radius=30, fill="#FFFFFF")
        foreground = ImageOps.contain(photo, (840, 775), Image.Resampling.LANCZOS)
        canvas.paste(foreground, ((1000 - foreground.width)//2,
                                 280 + (780 - foreground.height)//2))
        draw.text((65, 1143), CATEGORIES[pin["category"]],
                  fill="#B06E45", font=load_font(25))
        font = load_font(51)
        lines = text_lines(pin["title"], font, draw, max_width=875, max_lines=3)
        for i, line in enumerate(lines):
            draw.text((64, 1199 + 65*i), line, fill="#244E46", font=font)
        draw.line((65, 1429, 935, 1429), fill="#C9CDBF", width=2)
        draw.text((66, 1444), "Contém link de afiliado • Confira os detalhes no Pin",
                  fill="#536E63", font=load_font(18, False))

    # Save atomically to avoid losing the previous good preview on failure.
    with tempfile.NamedTemporaryFile(dir=out_dir, suffix=".jpg", delete=False) as fp:
        staging = Path(fp.name)
    try:
        canvas.save(staging, "JPEG", quality=90, optimize=True, subsampling=0)
        if staging.stat().st_size > 18 * 1024 * 1024:
            raise GarimpoError("Imagem gerada excedeu 18 MiB")
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    return target

def fingerprint(pin: dict) -> str:
    image = Path(pin["preview_path"])
    if not image.is_file():
        raise GarimpoError("Imagem final não existe. Execute prepare novamente.")
    digest = hashlib.sha256()
    for field in ("title", "description", "affiliate_url", "board_id"):
        digest.update(pin[field].encode("utf-8"))
        digest.update(b"\x00")
    digest.update(image.read_bytes())
    return digest.hexdigest()


def approve_pin(pin: dict, board_id: str) -> None:
    if pin["status"] != "prepared":
        raise GarimpoError("Primeiro prepare o Pin (status=prepared)")
    if pin.get("affiliate_link_pending"):
        raise GarimpoError("Confirme o link obtido no navegador com confirm-link ID --confirm.")
    if pin.get("created_by_url"):
        if not pin.get("affiliate_url_confirmed") or not pin.get("affiliate_url"):
            raise GarimpoError("Confirme um link oficial de afiliado antes de aprovar.")
        if not pin.get("image_license_confirmed"):
            raise GarimpoError("Confirme direitos de uso da imagem antes de aprovar.")
        if not pin.get("title_confirmed") or not pin.get("category_confirmed"):
            raise GarimpoError("Revise o título e a categoria antes de aprovar.")
    if not re.fullmatch(r"[0-9]{5,30}", board_id):
        raise GarimpoError("Informe o ID numérico real da pasta (board) obtido pela API do Pinterest")
    pin["board_id"] = board_id
    pin["approval_sha256"] = fingerprint(pin)
    pin["approved_at"] = now_iso()
    pin["status"] = "approved"


def pinterest_call(path: str, method: str = "GET", payload: dict | None = None, *, token: str | None = None) -> dict:
    token = token or os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    if not token:
        raise GarimpoError("PINTEREST_ACCESS_TOKEN não configurado. Use OAuth 2.0, não sua senha do Pinterest.")
    if path not in {"/boards", "/pins"}:
        raise GarimpoError("Endpoint não permitido")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(PINTEREST_API + path, method=method, data=body, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "GarimpoDaVez/1.0 (Pinterest OAuth authorized publishing)",
    })
    try:
        with urlopen(req, timeout=28) as resp:
            result = json.loads(resp.read(2_000_000).decode("utf-8"))
            if not isinstance(result, dict):
                raise GarimpoError("Formato de resposta inesperado do Pinterest")
            return result
    except HTTPError as exc:
        data = exc.read(1200).decode("utf-8", errors="replace")
        # Generic response, never print credentials.
        raise GarimpoError(f"Pinterest HTTP {exc.code}: {data}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GarimpoError(f"Falha de conexão com Pinterest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GarimpoError("Pinterest retornou resposta não JSON") from exc


def publish_pin(pin: dict, *, token: str | None = None) -> dict:
    if pin["status"] != "approved":
        raise GarimpoError("Somente Pins aprovados individualmente podem ser publicados")
    if pin.get("affiliate_link_pending"):
        raise GarimpoError("Link de afiliado ainda não confirmado.")
    if pin.get("created_by_url") and (
        not pin.get("affiliate_url_confirmed")
        or not pin.get("image_license_confirmed")
        or not pin.get("title_confirmed")
        or not pin.get("category_confirmed")
    ):
        raise GarimpoError("Pin não revisado: verifique direitos, dados e link oficial.")
    if pin["approval_sha256"] != fingerprint(pin):
        raise GarimpoError("Conteúdo mudou após aprovação. Prepare e aprove novamente.")
    image = Path(pin["preview_path"])
    payload = {
        "title": pin["title"],
        "description": pin["description"],
        "link": pin["affiliate_url"],
        "board_id": pin["board_id"],
        "alt_text": pin["title"],
        "media_source": {
            "source_type": "image_base64",
            "content_type": "image/jpeg",
            "data": base64.b64encode(image.read_bytes()).decode("ascii"),
        },
    }
    return pinterest_call("/pins", "POST", payload, token=token)



def capture_affiliate_link(product_url: str, browser: str = "msedge", cdp_url: str = "") -> str:
    try:
        from affiliate_browser import copy_affiliate_link, AffiliateBrowserError
    except ModuleNotFoundError:
        from automation.affiliate_browser import copy_affiliate_link, AffiliateBrowserError
    try:
        return ensure_https_affiliate_link(copy_affiliate_link(
            product_url, BASE_DIR / "data" / "browser-profile", browser_channel=browser,
            cdp_url=cdp_url))
    except AffiliateBrowserError as exc:
        raise GarimpoError(str(exc)) from exc


def ingest_product_url(url: str, store: Path, *, affiliate_url: str = "",
                       category: str = "", title: str = "", image_file: str = "",
                       confirm_image_rights: bool = False,
                       confirm_affiliate_link: bool = False) -> dict:
    """Cria rascunho sem inventar dados e sem sobrescrever produtos existentes."""
    try:
        from ml_ingest import get_product_metadata, download_product_image, local_id
    except ModuleNotFoundError:
        from automation.ml_ingest import get_product_metadata, download_product_image, local_id
    token = os.environ.get("MERCADOLIVRE_ACCESS_TOKEN", "")
    if not token:
        try:
            from ml_oauth import get_access_token
            token = get_access_token()
        except Exception:
            # Sem OAuth ativo, API pública e metatags podem funcionar.
            token = ""
    metadata = get_product_metadata(url, token=token or None)
    id_ = local_id(metadata)
    state = load_store(store)
    if id_ in state["pins"]:
        raise GarimpoError(f"Produto {id_} já existe na fila. Use review/stylize/prepare.")
    cat = category or metadata["category"] or "lifestyle"
    if cat not in CATEGORIES:
        raise GarimpoError("Categoria inválida: " + ", ".join(CATEGORIES))
    selected_title = (title or metadata["title"] or f"Dados pendentes: {id_}").strip()[:100]
    summary = (metadata["summary"] or "Informações disponíveis no anúncio; confirme detalhes e especificações antes da compra.").strip()[:550]
    url_link = affiliate_url or (url if urlsplit(url).hostname == "meli.la" else "")
    if url_link:
        url_link = ensure_https_affiliate_link(url_link)
    if confirm_affiliate_link and not url_link:
        raise GarimpoError("Informe um link gerado no Portal de Afiliados antes de confirmá-lo.")
    image_path = ""
    if image_file:
        source = Path(image_file).expanduser().resolve()
        if source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not source.is_file():
            raise GarimpoError("Arquivo local de imagem inexistente ou formato inválido")
        image_path = str(source)
    elif confirm_image_rights and metadata.get("image_url"):
        try:
            image_path = str(download_product_image(
                metadata["image_url"], BASE_DIR / "data" / "sources", id_
            ))
        except (ValueError, OSError) as exc:
            metadata["warnings"].append(f"Imagem indisponível: {exc}")
    pin = {
        "id": id_, "item_id": metadata["item_id"], "ml_verification": None,
        "ml_category_id": metadata.get("ml_category_id", ""),
        "title": selected_title, "description": summary + "\n\n" + DISCLOSURE,
        "category": cat, "affiliate_url": url_link,
        "affiliate_link_source": "central_manual" if affiliate_url else "",
        "affiliate_confirmed_at": now_iso() if confirm_affiliate_link else "",
        "affiliate_url_confirmed": bool(confirm_affiliate_link),
        "image_license_confirmed": bool(confirm_image_rights and image_path),
        "title_confirmed": bool(title),
        "category_confirmed": bool(category),
        "image_path": image_path, "source_image_url": metadata["image_url"],
        "source_url": url, "resolved_url": metadata["resolved_url"],
        "metadata_source": metadata["metadata_source"],
        "metadata_verified": metadata["metadata_verified"],
        "notes": metadata["warnings"],
        "created_by_url": True, "stylized_image_path": "",
        "creative_provider": "", "status": "draft", "board_id": "",
        "preview_path": "", "approval_sha256": "", "pin_id": "",
        "created_at": now_iso(),
    }
    state["pins"][id_] = pin
    save_store(store, state)
    return pin


def review_url_draft(pin: dict, *, title: str = "", category: str = "",
                     affiliate_url: str = "", image_file: str = "",
                     confirm_title: bool = False, confirm_category: bool = False,
                     confirm_image_rights: bool = False,
                     confirm_affiliate_link: bool = False) -> None:
    if pin["status"] not in {"draft", "prepared"}:
        raise GarimpoError("Não edite Pins aprovados ou publicados.")
    if not pin.get("created_by_url"):
        raise GarimpoError("Este comando é para produtos importados por URL.")
    if title:
        if not 5 <= len(title.strip()) <= 100:
            raise GarimpoError("Título deve ter 5-100 caracteres")
        pin["title"] = title.strip()
        pin["title_confirmed"] = False
    if category:
        if category not in CATEGORIES:
            raise GarimpoError("Categoria inválida")
        pin["category"] = category
        pin["category_confirmed"] = False
    if affiliate_url:
        pin["affiliate_url"] = ensure_https_affiliate_link(affiliate_url)
        pin["affiliate_url_confirmed"] = False
    if image_file:
        source = Path(image_file).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise GarimpoError("Imagem local não encontrada")
        pin["image_path"] = str(source)
        pin["image_license_confirmed"] = False
    if confirm_image_rights:
        if not pin.get("image_path") and pin.get("source_image_url"):
            try:
                from ml_ingest import download_product_image
            except ModuleNotFoundError:
                from automation.ml_ingest import download_product_image
            pin["image_path"] = str(download_product_image(
                pin["source_image_url"], BASE_DIR / "data" / "sources", pin["id"]))
        if not pin.get("image_path"):
            raise GarimpoError("Sem imagem disponível para autorizar; informe --image-file.")
        pin["image_license_confirmed"] = True
    if confirm_affiliate_link:
        if not pin["affiliate_url"]:
            raise GarimpoError("Informe --affiliate-url gerado no Portal do Afiliado.")
        pin["affiliate_url_confirmed"] = True
        pin["affiliate_link_pending"] = False
    if confirm_title:
        if pin["title"].startswith("Dados pendentes:"):
            raise GarimpoError("Informe o título verdadeiro antes de confirmar.")
        pin["title_confirmed"] = True
    if confirm_category:
        pin["category_confirmed"] = True
    # Uma mudança na revisão invalida criativo antigo e impede publicação desatualizada.
    pin["status"] = "draft"
    pin["preview_path"] = ""
    pin["stylized_image_path"] = ""
    pin["approval_sha256"] = ""


def stylize_draft(pin: dict, out: Path, provider: str, *, allow_paid_ai: bool,
                 cloud_options: dict | None = None) -> Path:
    if pin["status"] not in {"draft", "prepared"}:
        raise GarimpoError("Não estilize um Pin aprovado/publicado.")
    try:
        from creative_ai import stylize, CreativeError
    except ModuleNotFoundError:
        from automation.creative_ai import stylize, CreativeError
    try:
        target = stylize(pin, out / "styled", provider=provider,
                         allow_paid_ai=allow_paid_ai, **(cloud_options or {}))
    except CreativeError as exc:
        raise GarimpoError(str(exc)) from exc
    pin["stylized_image_path"] = str(target)
    pin["creative_provider"] = "local" if pin.pop("_used_local_fallback", False) else provider
    pin["ai_modified"] = pin["creative_provider"] in {"openai", "aihorde", "hf-spaces"}
    pin["status"] = "draft"
    pin["preview_path"] = ""
    pin["approval_sha256"] = ""
    return target


def missing_for_creative(pin: dict) -> list[str]:
    missing = []
    if not pin.get("image_path") or not Path(pin["image_path"]).is_file():
        missing.append("imagem (use --confirm-image-rights ou review --image-file)")
    if not pin.get("image_license_confirmed", True):
        missing.append("autorização de direitos da imagem")
    if pin.get("title", "").startswith("Dados pendentes:"):
        missing.append("título real")
    return missing


def cloud_options_from_args(args: argparse.Namespace) -> dict:
    """Cloud controls are passed only from explicit CLI arguments."""
    return {
        "allow_public_processing": args.allow_public_processing,
        "confirm_model_license": args.confirm_model_license,
        "horde_model": args.horde_model,
        "hf_space": args.hf_space,
        "hf_api_name": args.hf_api_name,
        "hf_image_arg": args.hf_image_arg,
        "hf_prompt_arg": args.hf_prompt_arg,
        "fallback_local": args.fallback_local,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Garimpo da Vez — curadoria e publicação supervisionada de Pins")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE, help="Fila JSON privada (padrão: automation/data/pins.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    im = sub.add_parser("import-csv", help="Importa produtos reais de um CSV sem sobrescrever existentes")
    im.add_argument("csv", type=Path)
    for name in ("ingest-url", "auto"):
        cmd = sub.add_parser(name, help="Obtém dados permitidos do anúncio via URL; auto também prepara um Pin local")
        cmd.add_argument("url", help="URL HTTPS de produto Mercado Livre ou link curto meli.la")
        cmd.add_argument("--affiliate-url", default="", help="Link oficial gerado na Central de Afiliados")
        cmd.add_argument("--category", choices=list(CATEGORIES), default="")
        cmd.add_argument("--title", default="", help="Título verificado manualmente, se a API bloquear")
        cmd.add_argument("--image-file", default="", help="Foto de origem local, se acesso remoto falhar")
        cmd.add_argument("--confirm-image-rights", action="store_true", help="Declara direitos de uso comercial e autoriza baixar a foto")
        cmd.add_argument("--confirm-affiliate-link", action="store_true", help="Confirma que o link foi gerado no Portal de Afiliados")
        cmd.add_argument("--affiliate-browser", action="store_true",
                         help="Abre Central de Afiliados com Playwright para copiar link (login humano)")
        cmd.add_argument("--browser", choices=["msedge", "chromium"], default="msedge")
        cmd.add_argument("--cdp-url", default="", help="Edge local já aberto via CDP, ex.: http://127.0.0.1:9333")
        if name == "auto":
            cmd.add_argument("--provider", choices=["local", "aihorde", "hf-spaces", "openai", "none"], default="local")
            cmd.add_argument("--allow-paid-ai", action="store_true")
        cmd.add_argument("--allow-public-processing", action="store_true",
                         help="Consente em enviar foto/prompt a terceiros (workers/Space público)")
        cmd.add_argument("--confirm-model-license", action="store_true",
                         help="Confirma licença comercial do modelo/Space escolhido")
        cmd.add_argument("--horde-model", default="", help="Modelo AI Horde com licença conferida")
        cmd.add_argument("--hf-space", default="", help="Space público no formato autor/nome")
        cmd.add_argument("--hf-api-name", default="", help="Endpoint Gradio documentado, ex.: /edit")
        cmd.add_argument("--hf-image-arg", default="image", help="Nome do parâmetro de imagem do Space")
        cmd.add_argument("--hf-prompt-arg", default="prompt", help="Nome do parâmetro de prompt do Space")
        cmd.add_argument("--fallback-local", action="store_true",
                         help="Se nuvem falhar, usar tratamento Pillow sem IA")
        if name == "auto":
            cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
            cmd.add_argument("--style", choices=["editorial", "branded"], default="editorial")
            cmd.add_argument("--source", choices=["best", "original"], default="best")
    rev = sub.add_parser("review", help="Completa campos e autorizações pendentes de um rascunho importado por URL")
    rev.add_argument("id")
    rev.add_argument("--title", default="")
    rev.add_argument("--category", choices=list(CATEGORIES), default="")
    rev.add_argument("--affiliate-url", default="")
    rev.add_argument("--image-file", default="")
    for flag in ("confirm-title", "confirm-category", "confirm-image-rights", "confirm-affiliate-link"):
        rev.add_argument("--" + flag, action="store_true")
    link = sub.add_parser("affiliate-link", help="Obtém link pela Central em navegador interativo para um rascunho")
    link.add_argument("id")
    link.add_argument("--product-url", default="", help="URL normal do anúncio; padrão: source_url")
    link.add_argument("--browser", choices=["msedge", "chromium"], default="msedge")
    link.add_argument("--cdp-url", default="", help="Reutiliza Edge dedicado via CDP")
    confirm_link = sub.add_parser("confirm-link", help="Confirma após revisão humana que o link pertence ao produto")
    confirm_link.add_argument("id")
    confirm_link.add_argument("--confirm", action="store_true", required=True)
    rights = sub.add_parser("confirm-image-rights", help="Registra autorização comercial da foto em um rascunho antigo")
    rights.add_argument("id")
    rights.add_argument("--image-file", default="", help="Opcional: substituir pela imagem autorizada")
    rights.add_argument("--confirm", action="store_true", required=True,
                        help="Declara que você possui direitos de uso comercial desta imagem")
    st = sub.add_parser("stylize", help="Gera versão local gratuita ou estiliza com IA paga opcional")
    st.add_argument("id")
    st.add_argument("--provider", choices=["local", "aihorde", "hf-spaces", "openai"], default="local")
    st.add_argument("--allow-paid-ai", action="store_true")
    st.add_argument("--allow-public-processing", action="store_true",
                     help="Consente em enviar foto/prompt a terceiros (workers/Space público)")
    st.add_argument("--confirm-model-license", action="store_true",
                     help="Confirma licença comercial do modelo/Space escolhido")
    st.add_argument("--horde-model", default="", help="Modelo AI Horde com licença conferida")
    st.add_argument("--hf-space", default="", help="Space público no formato autor/nome")
    st.add_argument("--hf-api-name", default="", help="Endpoint Gradio documentado, ex.: /edit")
    st.add_argument("--hf-image-arg", default="image", help="Nome do parâmetro de imagem do Space")
    st.add_argument("--hf-prompt-arg", default="prompt", help="Nome do parâmetro de prompt do Space")
    st.add_argument("--fallback-local", action="store_true",
                     help="Se nuvem falhar, usar tratamento Pillow sem IA")
    st.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ls = sub.add_parser("list", help="Exibe situação dos Pins")
    ls.add_argument("--status", choices=["draft", "prepared", "approved", "publishing", "published", "needs_check"])
    show = sub.add_parser("show", help="Mostra dados e pendências do produto para revisão")
    show.add_argument("id")
    knowledge = sub.add_parser("knowledge", help="Mostra os textos knowledge selecionados para o criativo")
    knowledge.add_argument("id")
    knowledge.add_argument("--prompt", action="store_true", help="Exibe o prompt editorial completo")
    prep = sub.add_parser("prepare", help="Gera imagem vertical do Pin sem publicar")
    prep.add_argument("id")
    prep.add_argument("--out", type=Path, default=DEFAULT_OUT)
    prep.add_argument("--style", choices=["editorial", "branded"], default="editorial",
                      help="Editorial sem banner (padrão) ou layout antigo com marca")
    prep.add_argument("--source", choices=["best", "original"], default="best",
                      help="best usa edição disponível; original usa fotografia de origem")
    exp = sub.add_parser("export-business", help="Exporta campos + foto para Pinterest Business manual, sem API")
    exp.add_argument("id")
    exp.add_argument("--out", type=Path, default=DEFAULT_OUT / "business")
    app = sub.add_parser("approve", help="Aprova um Pin e uma pasta específicos")
    app.add_argument("id")
    app.add_argument("--board-id", required=True)
    app.add_argument("--confirm", action="store_true", required=True)
    pub = sub.add_parser("publish", help="Publica UM Pin aprovado via Pinterest API oficial")
    pub.add_argument("id")
    pub.add_argument("--confirm", action="store_true", required=True)
    verify = sub.add_parser("verify-ml", help="Consulta um anúncio via API oficial ML (somente leitura)")
    verify.add_argument("id", help="ID local do Pin importado")
    verify.add_argument("--item-id", help="ID MLB real do anúncio (se não informado no CSV)")
    reset = sub.add_parser("reset", help="Libera novo preparo depois de conciliar uma publicação incerta")
    reset.add_argument("id")
    reset.add_argument("--confirmed-not-published", action="store_true", required=True)
    sub.add_parser("boards", help="Lista pastas acessíveis pelo token Pinterest (somente leitura)")
    check = sub.add_parser("hf-check", help="Inspeciona Space/endpoint Gradio sem imagem nem cota de GPU")
    check.add_argument("--space", default="", help="Space (autor/nome); padrão HF_SPACE_ID")
    check.add_argument("--api-name", default="", help="Endpoint; padrão HF_SPACE_API_NAME")
    check.add_argument("--image-arg", default="image")
    check.add_argument("--prompt-arg", default="prompt")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import-csv":
        amount = import_csv(args.csv, args.store)
        print(f"{amount} produto(s) importado(s). Execute 'list' e 'prepare ID'.")
        return 0
    if args.command in {"ingest-url", "auto"}:
        affiliate_url = args.affiliate_url
        if args.affiliate_browser:
            if affiliate_url:
                raise GarimpoError("Escolha --affiliate-url ou --affiliate-browser, não ambos.")
            affiliate_url = capture_affiliate_link(args.url, args.browser, args.cdp_url)
        pin = ingest_product_url(
            args.url, args.store,
            affiliate_url=affiliate_url, category=args.category,
            title=args.title, image_file=args.image_file,
            confirm_image_rights=args.confirm_image_rights,
            confirm_affiliate_link=args.confirm_affiliate_link,
        )
        print(f"Rascunho criado: {pin['id']} | dados: {pin['metadata_source']} | MLB: {pin['item_id'] or 'não confirmado'}")
        for note in pin["notes"]:
            print("ATENÇÃO:", note)
        if args.affiliate_browser:
            pin["affiliate_link_pending"] = True
            pin["affiliate_url_confirmed"] = False
            state = load_store(args.store)
            state["pins"][pin["id"]] = pin
            save_store(args.store, state)
            print("Link coletado no navegador: confirme produto e origem com confirm-link ID --confirm.")
        if args.command == "auto":
            missing = missing_for_creative(pin)
            if missing:
                print("Preparação pausada; pendências:", "; ".join(missing))
                print("Use review ID para complementar. Nenhum Pin foi publicado.")
            else:
                if args.provider != "none":
                    styled = stylize_draft(pin, args.out.resolve(), args.provider,
                                           allow_paid_ai=args.allow_paid_ai,
                                           cloud_options=cloud_options_from_args(args))
                    print(f"Imagem estilizada ({args.provider}): {styled}")
                path = prepare_image(pin, args.out.resolve(), style=args.style, source=args.source)
                pin["preview_path"] = str(path)
                pin["creative_style"] = args.style
                pin["prepared_source"] = args.source
                pin["status"] = "prepared"
                print(f"Pin preparado: {path}. Revisão e aprovação ainda obrigatórias.")
            state = load_store(args.store)
            state["pins"][pin["id"]] = pin
            save_store(args.store, state)
        return 0
    if args.command == "hf-check":
        try:
            from hf_diagnostics import inspect_space, HFDiagnosticError
        except ModuleNotFoundError:
            from automation.hf_diagnostics import inspect_space, HFDiagnosticError
        try:
            diagnosis = inspect_space(
                args.space or os.environ.get("HF_SPACE_ID", ""),
                args.api_name or os.environ.get("HF_SPACE_API_NAME", ""),
                image_arg=args.image_arg, prompt_arg=args.prompt_arg,
            )
        except HFDiagnosticError as exc:
            raise GarimpoError(str(exc)) from exc
        print(json.dumps(diagnosis, ensure_ascii=False, indent=2))
        print("Somente leitura: nenhuma imagem enviada e nenhuma GPU usada.")
        if not diagnosis.get("compatible"):
            raise GarimpoError("Space não compatível com os parâmetros configurados.")
        return 0
    if args.command == "boards":
        resp = pinterest_call("/boards")
        for board in resp.get("items", []):
            print(f"{board.get('id', '?')} | {board.get('name', 'Sem nome')}")
        if resp.get("bookmark"):
            print("Há mais pastas. Este comando mostra somente a primeira página da API.")
        return 0
    if args.command == "publish":
        if not args.confirm:
            raise GarimpoError("Publicação exige --confirm")
        publish_one_approved(args.store, args.id)
        return 0
    state = load_store(args.store)
    if args.command == "list":
        for id_, pin in sorted(state["pins"].items()):
            if not args.status or pin["status"] == args.status:
                print(f"{id_:<20} {pin['status']:<13} {pin['title']}")
        return 0
    pin = get_pin(state, args.id)
    if args.command == "knowledge":
        try:
            from prompt_templates import select_knowledge, make_prompt, knowledge_path
        except ModuleNotFoundError:
            from automation.prompt_templates import select_knowledge, make_prompt, knowledge_path
        selection = select_knowledge(pin)
        print(f"Conhecimento: {selection['slug']} | origem: {selection['reason']}")
        print(f"Documento: {knowledge_path(pin)}")
        if args.prompt:
            print(make_prompt(pin))
        return 0
    if args.command == "show":
        fields = ("id", "status", "title", "category", "source_url", "item_id", "ml_category_id",
                  "metadata_source", "metadata_verified", "image_path", "image_license_confirmed",
                  "affiliate_url", "affiliate_url_confirmed", "affiliate_link_pending",
                  "title_confirmed", "category_confirmed", "stylized_image_path", "preview_path",
                  "creative_provider", "creative_style", "prepared_source", "ai_modified",
                  "affiliate_link_source", "affiliate_confirmed_at", "notes")
        print(json.dumps({field: pin.get(field) for field in fields}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "affiliate-link":
        if pin["status"] not in {"draft", "prepared"}:
            raise GarimpoError("Não altere links de Pins aprovados/publicados.")
        product_url = args.product_url or pin.get("source_url")
        if not product_url:
            raise GarimpoError("Informe --product-url com URL real do anúncio.")
        pin["affiliate_url"] = capture_affiliate_link(product_url, args.browser, args.cdp_url)
        pin["affiliate_link_source"] = "mercadolivre_central_browser"
        pin["affiliate_confirmed_at"] = ""
        pin["affiliate_link_pending"] = True
        pin["affiliate_url_confirmed"] = False
        pin["status"] = "draft"
        pin["approval_sha256"] = ""
        pin["preview_path"] = ""
        print("Link coletado; confira o produto e execute confirm-link ID --confirm.")
    elif args.command == "confirm-link":
        if pin["status"] not in {"draft", "prepared"} or not args.confirm:
            raise GarimpoError("Confirmação apenas para rascunhos, com --confirm")
        if not pin.get("affiliate_url"):
            raise GarimpoError("Rascunho sem link de afiliado")
        pin["affiliate_url_confirmed"] = True
        pin["affiliate_confirmed_at"] = now_iso()
        pin["affiliate_link_pending"] = False
        print("Link individual do produto confirmado. Ainda não foi publicado.")
    elif args.command == "confirm-image-rights":
        if pin["status"] not in {"draft", "prepared"} or not args.confirm:
            raise GarimpoError("A confirmação só é permitida em Pins não aprovados, com --confirm.")
        source = Path(args.image_file).expanduser().resolve() if args.image_file else Path(pin.get("image_path") or "")
        if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise GarimpoError("Imagem autorizada não encontrada; use --image-file com um arquivo real.")
        if source.stat().st_size > 18 * 1024 * 1024:
            raise GarimpoError("Imagem acima do limite de 18 MiB.")
        pin["image_path"] = str(source.resolve())
        pin["image_license_confirmed"] = True
        pin["status"] = "draft"
        pin["preview_path"] = ""
        pin["stylized_image_path"] = ""
        pin["approval_sha256"] = ""
        pin["board_id"] = ""
        print("Confirmação de uso comercial registrada. Execute stylize e prepare antes de aprovar; nenhum Pin foi publicado.")
    elif args.command == "review":
        review_url_draft(
            pin, title=args.title, category=args.category, affiliate_url=args.affiliate_url,
            image_file=args.image_file, confirm_title=args.confirm_title,
            confirm_category=args.confirm_category,
            confirm_image_rights=args.confirm_image_rights,
            confirm_affiliate_link=args.confirm_affiliate_link,
        )
        print(f"Revisão salva: {pin['id']}; agora execute stylize/prepare.")
    elif args.command == "stylize":
        target = stylize_draft(pin, args.out.resolve(), args.provider,
                               allow_paid_ai=args.allow_paid_ai,
                               cloud_options=cloud_options_from_args(args))
        print(f"Tratamento ({args.provider}) salvo em: {target}; execute prepare e revise.")
    elif args.command == "verify-ml":
        if pin["status"] not in {"draft", "prepared"}:
            raise GarimpoError("Verifique o anúncio antes da aprovação/publicação")
        item_id = (args.item_id or pin.get("item_id") or "").strip().upper()
        verification = fetch_mercadolivre_item(item_id)
        pin["item_id"] = item_id
        pin["ml_verification"] = verification
        print(f"Anúncio conferido: {item_id} | {verification['title']}")
        if verification["price"] is not None:
            print(f"Preço no momento da consulta: {verification['currency_id']} {verification['price']}")
        print("Consulte elegibilidade a comissão e mantenha o link oficial de afiliado do CSV.")
    elif args.command == "prepare":
        if pin["status"] not in {"draft", "prepared"}:
            raise GarimpoError("Pin já aprovado/enviado. Não é permitido alterar criativo aprovado.")
        path = prepare_image(pin, args.out.resolve(), style=args.style, source=args.source)
        pin["preview_path"] = str(path)
        pin["creative_style"] = args.style
        pin["prepared_source"] = args.source
        pin["status"] = "prepared"
        pin["approval_sha256"] = ""
        print(f"Criativo {args.style} pronto: {path}\nRevise imagem, título e link antes de aprovar.")
    elif args.command == "export-business":
        try:
            from pinterest_business import export_business, BusinessExportError
        except ModuleNotFoundError:
            from automation.pinterest_business import export_business, BusinessExportError
        try:
            folder = export_business(pin, args.out.resolve())
        except BusinessExportError as exc:
            raise GarimpoError(str(exc)) from exc
        print(f"Pacote Pinterest Business: {folder}")
        print("Leia checklist.md, copie fields.json/copy.txt e publique manualmente.")
    elif args.command == "approve":
        if not args.confirm:
            raise GarimpoError("É necessário --confirm após revisar o criativo")
        approve_pin(pin, args.board_id)
        print(f"Aprovado: {args.id} na pasta {args.board_id}. Ainda NÃO publicado.")
    elif args.command == "reset":
        if not args.confirmed_not_published or pin["status"] not in {"needs_check", "publishing"}:
            raise GarimpoError("Reset exige needs_check/publishing e --confirmed-not-published; remova lock residual apenas após conciliar")
        pin["status"] = "prepared"
        pin["approval_sha256"] = ""
        pin["board_id"] = ""
        print("Liberado para nova aprovação. Verifique o conteúdo antes de aprovar.")
    save_store(args.store, state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (GarimpoError, FileNotFoundError, PermissionError) as exc:
        print("ERRO:", exc, file=sys.stderr)
        sys.exit(1)
