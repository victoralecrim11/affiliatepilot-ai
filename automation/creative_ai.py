"""Estilização de imagem: local gratuita (NÃO IA) ou OpenAI Images Edit (paga).

Nenhuma chamada à IA ocorre sem --provider openai --allow-paid-ai e chave.
Não altera o produto ou a fila publicada; saída requer revisão humana.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

try:
    from prompt_templates import make_prompt
except ModuleNotFoundError:
    from automation.prompt_templates import make_prompt


class CreativeError(ValueError):
    pass


def _photo(pin: dict) -> Image.Image:
    source = Path(pin.get("image_path") or "")
    if not source.is_file():
        raise CreativeError("Imagem base indisponível. Envie uma imagem autorizada ou conclua ingest-url.")
    try:
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            img.load()
            if img.width * img.height > 35_000_000:
                raise CreativeError("Imagem muito grande")
            return img.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise CreativeError("Imagem base inválida") from exc


def _local_enhance(pin: dict, target: Path):
    """Tratamento fotográfico + moldura, NÃO geração por IA."""
    photo = _photo(pin)
    photo = ImageEnhance.Contrast(photo).enhance(1.07)
    photo = ImageEnhance.Color(photo).enhance(1.04)
    photo = ImageOps.contain(photo, (920, 1110), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1024, 1536), "#EDEAE2")
    # Fundo gráfico discreto; a fotografia permanece intacta em proporção.
    canvas.paste(Image.new("RGB", (1024, 400), "#244E46"), (0, 0))
    shadow = Image.new("RGBA", (1024, 1536))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((45, 160, 979, 1405), radius=35, fill=(0, 0, 0, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow)
    overlay = Image.new("RGBA", (1024, 1536), (0, 0, 0, 0))
    dr = ImageDraw.Draw(overlay)
    dr.rounded_rectangle((42, 150, 982, 1400), radius=30, fill="#FDFCF8")
    canvas = Image.alpha_composite(canvas, overlay)
    x = (1024 - photo.width) // 2
    y = 220 + (1070 - photo.height) // 2
    canvas.paste(photo, (x, y))
    canvas.convert("RGB").save(target, "PNG", optimize=True)


def _openai_edit(pin: dict, target: Path, *, api_key: str | None = None):
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise CreativeError("OPENAI_API_KEY ausente; configure uma chave da API (pode haver cobrança).")
    photo = _photo(pin)
    source = BytesIO()
    photo.save(source, format="PNG")
    source_bytes = source.getvalue()
    boundary = "----garimpo" + secrets.token_hex(14)

    def part(name: str, data: bytes, filename: str | None = None, ctype: str | None = None) -> bytes:
        header = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:
            header += f'; filename="{filename}"'
        header += "\r\n"
        if ctype:
            header += f"Content-Type: {ctype}\r\n"
        return (header + "\r\n").encode("utf-8") + data + b"\r\n"

    body = b"".join([
        part("model", b"gpt-image-1.5"),
        part("size", b"1024x1536"),
        part("quality", b"medium"),
        part("prompt", make_prompt(pin).encode("utf-8")),
        part("image[]", source_bytes, "source.png", "image/png"),
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    request = Request("https://api.openai.com/v1/images/edits", method="POST", data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=150) as resp:
            data = resp.read(24 * 1024 * 1024)
        payload = json.loads(data)
        encoded = payload["data"][0]["b64_json"]
        result = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(result)) as image:
            image.verify()
        if len(result) > 20 * 1024 * 1024:
            raise CreativeError("Imagem retornada excede limite de tamanho")
        # O modelo retorna PNG quando output_format não está definido.
        target.write_bytes(result)
    except HTTPError as exc:
        raise CreativeError(f"Falha na API de imagens (HTTP {exc.code}); nenhuma imagem foi aprovada") from exc
    except (URLError, TimeoutError, OSError, KeyError, IndexError, ValueError) as exc:
        raise CreativeError("Falha ao gerar imagem por IA; verifique credencial, saldo e conexão") from exc


def stylize(pin: dict, out_dir: Path, *, provider: str = "local",
            allow_paid_ai: bool = False, api_key: str | None = None) -> Path:
    if provider not in ("local", "openai"):
        raise CreativeError("Provider válido: local (gratuito, sem IA) ou openai (IA paga)")
    if not pin.get("image_license_confirmed", True):
        raise CreativeError("É preciso confirmar direitos de uso da imagem antes de estilizar.")
    if provider == "openai" and not allow_paid_ai:
        raise CreativeError("Chamadas pagas requerem a opção explícita --allow-paid-ai.")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{pin['id']}-styled.png"
    tmp = out_dir / f".{pin['id']}-styled.tmp.png"
    try:
        if provider == "openai":
            _openai_edit(pin, tmp, api_key=api_key)
        else:
            _local_enhance(pin, tmp)
        tmp.replace(target)
        return target
    finally:
        tmp.unlink(missing_ok=True)
