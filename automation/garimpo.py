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
        reader = csv.DictReader(fp)
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
    token = token or os.environ.get("MERCADOLIVRE_ACCESS_TOKEN", "")
    if not token:
        raise GarimpoError("Configure MERCADOLIVRE_ACCESS_TOKEN autorizado; não é seu token Pinterest")
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


def prepare_image(pin: dict, out_dir: Path) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise GarimpoError("Pillow ausente. Instale com: python -m pip install -r automation/requirements.txt") from exc
    inp = Path(pin["image_path"])
    if not inp.is_file():
        raise GarimpoError("Imagem de origem não encontrada: " + str(inp))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{pin['id']}.jpg"
    # Designed for 2:3 Pins; photo is contained, never filled with fabricated details.
    canvas = Image.new("RGB", (1000, 1500), "#F5EFE3")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1000, 205), fill="#244E46")
    draw.text((66, 60), "GARIMPO DA VEZ", font=load_font(48), fill="#F5EFE3")
    draw.text((67, 130), "ACHADOS ÚTEIS PARA A VIDA REAL", font=load_font(20), fill="#D69A72")
    draw.rounded_rectangle((52, 250, 948, 1090), radius=30, fill="#FFFFFF")
    try:
        with Image.open(inp) as photo:
            photo = ImageOps.exif_transpose(photo)
            photo = ImageOps.contain(photo.convert("RGB"), (840, 775), Image.Resampling.LANCZOS)
            x = (1000 - photo.width) // 2
            y = 280 + (780 - photo.height) // 2
            canvas.paste(photo, (x, y))
    except (OSError, ValueError) as exc:
        raise GarimpoError(f"Imagem inválida: {exc}") from exc
    draw.text((65, 1143), CATEGORIES[pin["category"]], fill="#B06E45", font=load_font(25))
    font = load_font(51)
    lines = text_lines(pin["title"], font, draw, max_width=875, max_lines=3)
    for i, line in enumerate(lines):
        draw.text((64, 1199 + 65 * i), line, fill="#244E46", font=font)
    draw.line((65, 1429, 935, 1429), fill="#C9CDBF", width=2)
    draw.text((66, 1444), "Contém link de afiliado • Confira os detalhes no Pin", fill="#536E63", font=load_font(18, False))
    canvas.save(target, "JPEG", quality=87, optimize=True, subsampling=0)
    if target.stat().st_size > 18 * 1024 * 1024:
        target.unlink(missing_ok=True)
        raise GarimpoError("Imagem gerada excedeu 18 MiB")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Garimpo da Vez — curadoria e publicação supervisionada de Pins")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE, help="Fila JSON privada (padrão: automation/data/pins.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    im = sub.add_parser("import-csv", help="Importa produtos reais de um CSV sem sobrescrever existentes")
    im.add_argument("csv", type=Path)
    ls = sub.add_parser("list", help="Exibe situação dos Pins")
    ls.add_argument("--status", choices=["draft", "prepared", "approved", "publishing", "published", "needs_check"])
    prep = sub.add_parser("prepare", help="Gera imagem vertical do Pin sem publicar")
    prep.add_argument("id")
    prep.add_argument("--out", type=Path, default=DEFAULT_OUT)
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
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import-csv":
        amount = import_csv(args.csv, args.store)
        print(f"{amount} produto(s) importado(s). Execute 'list' e 'prepare ID'.")
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
    if args.command == "verify-ml":
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
        path = prepare_image(pin, args.out.resolve())
        pin["preview_path"] = str(path)
        pin["status"] = "prepared"
        pin["approval_sha256"] = ""
        print(f"Criativo pronto: {path}\nRevise imagem, título e link antes de aprovar.")
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
