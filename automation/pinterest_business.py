"""Offline Pinterest Business handoff: copy-ready fields + approved image.

Never logs into Pinterest, publishes, schedules or generates affiliate tracking URLs.
Each package is created from exactly one product's own affiliate_url.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


class BusinessExportError(ValueError):
    pass


AI_PROVIDERS = {"openai", "hf-spaces", "aihorde"}


def validate_handoff(pin: dict) -> None:
    if pin.get("status") not in {"prepared", "approved"}:
        raise BusinessExportError("Primeiro prepare o Pin; exportação não publica conteúdo.")
    if pin.get("image_license_confirmed") is not True:
        raise BusinessExportError("Confirme os direitos comerciais da imagem.")
    if pin.get("affiliate_link_pending") or not pin.get("affiliate_url_confirmed"):
        raise BusinessExportError("Confirme o link individual na Central antes de exportar.")
    if pin.get("created_by_url") and not (
        pin.get("title_confirmed") and pin.get("category_confirmed")
    ):
        raise BusinessExportError("Revise título e categoria deste produto antes de exportar.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,49}", str(pin.get("id") or "")):
        raise BusinessExportError("ID local inválido")
    if not pin.get("title") or not pin.get("description"):
        raise BusinessExportError("Título/descrição do Pin ausentes.")
    if "afiliad" not in pin["description"].casefold():
        raise BusinessExportError("A descrição deve informar a relação de afiliado.")
    if not pin.get("affiliate_url"):
        raise BusinessExportError("O produto não possui link individual de afiliado.")
    try:
        from garimpo import ensure_https_affiliate_link
    except ModuleNotFoundError:
        from automation.garimpo import ensure_https_affiliate_link
    ensure_https_affiliate_link(pin["affiliate_url"])
    if not pin.get("preview_path") or not Path(pin["preview_path"]).is_file():
        raise BusinessExportError("Criativo final não encontrado: execute prepare.")


def export_business(pin: dict, out_dir: Path) -> Path:
    """Copies one prepared JPEG and explicit metadata for manual Pinterest upload.

    AI metadata is an instruction for the human-operated Business UI, NOT an
    undocumented Pinterest API field or a claim of automatic platform labeling.
    """
    validate_handoff(pin)
    dest = out_dir / pin["id"]
    dest.mkdir(parents=True, exist_ok=True)
    image_dest = dest / "pin.jpg"
    shutil.copyfile(Path(pin["preview_path"]), image_dest)
    ai_provider = pin.get("creative_provider", "")
    ai_modified = (ai_provider in AI_PROVIDERS
                   and pin.get("prepared_source", "best") != "original"
                   and bool(pin.get("stylized_image_path")))
    title = pin["title"]
    alt = str(pin.get("alt_text") or ("Fotografia do produto: " + title))[:500]
    fields = {
        "product_local_id": pin["id"],
        "item_id": pin.get("item_id") or "",
        "category": pin.get("category") or "",
        "title": title,
        "description": pin["description"],
        "destination_url": pin["affiliate_url"],
        "alt_text": alt,
        "image_file": "pin.jpg",
        "creative_style": pin.get("creative_style") or "branded_legacy_unknown",
        "creative_provider": ai_provider or "original",
        "mark_as_ai_modified_in_business": ai_modified,
        "choose_board_in_pinterest": True,
        "publish_manually_only": True,
        "affiliate_link_confirmed": bool(pin.get("affiliate_url_confirmed")),
    }
    (dest / "fields.json").write_text(
        json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest / "copy.txt").write_text(
        f"TÍTULO\n{title}\n\nDESCRIÇÃO\n{pin['description']}\n\n"
        f"LINK DE DESTINO (somente deste produto)\n{pin['affiliate_url']}\n\n"
        f"TEXTO ALTERNATIVO\n{alt}\n",
        encoding="utf-8")
    (dest / "checklist.md").write_text(
        "# Publicação manual Pinterest Business\n\n"
        "- [ ] Compare produto/quantidade/especificações com anúncio real\n"
        "- [ ] Confirme direito de uso comercial da fotografia\n"
        "- [ ] Confirme no painel da Central que este link pertence ao item correto\n"
        "- [ ] Escolha a pasta (board) correta no Pinterest Business\n"
        "- [ ] Cole título, descrição, link e texto alternativo de copy.txt\n"
        + ("- [ ] Ative 'Marcar como modificado por IA' na interface (imagem generativa)\n"
           if ai_modified else
           "- [ ] Revise se houve alteração generativa antes de marcar IA\n")
        + "- [ ] Confira políticas de afiliados e só então publique/agende manualmente\n",
        encoding="utf-8",
    )
    return dest
