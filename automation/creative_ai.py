"""Imagens: Pillow local, serviços comunitários opcionais, OpenAI paga opt-in.

Serviços externos requerem consentimento, modelo licenciado e revisão humana.
Nenhuma geração publica Pins ou aprova conteúdo automaticamente.
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
    """Natural color/contrast improvement only; NEVER an ad-style frame or AI."""
    photo = _photo(pin)
    photo = ImageEnhance.Contrast(photo).enhance(1.06)
    photo = ImageEnhance.Color(photo).enhance(1.025)
    photo = ImageEnhance.Sharpness(photo).enhance(1.08)
    # Keep original subject, colors, captions already embedded in the input.
    # No synthetic product alterations, logos, overlays, branding or sales copy.
    photo.save(target, "PNG", optimize=True)

def _opencv_enhance(pin: dict, target: Path):
    """CPU-only photographic improvement, not a generative scene editor.

    CLAHE on luminance preserves product hues; conservative sharpening does
    not invent components. No billboards, text, logos, or fake lighting beams.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CreativeError(
            "OpenCV opcional ausente: python -m pip install -r automation/requirements-opencv.txt"
        ) from exc
    photo = _photo(pin)
    if max(photo.size) > 2200:
        photo.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
    rgb = np.asarray(photo, dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    # Low clip limit avoids highly artificial contrast/halo effects.
    clahe = cv2.createCLAHE(clipLimit=1.35, tileGridSize=(8, 8))
    l = clahe.apply(l)
    corrected = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2RGB)
    result = Image.fromarray(corrected, "RGB")
    result = ImageEnhance.Color(result).enhance(1.02)
    result = ImageEnhance.Sharpness(result).enhance(1.08)
    result.save(target, "PNG", optimize=True)


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
            allow_paid_ai: bool = False, api_key: str | None = None,
            allow_public_processing: bool = False, confirm_model_license: bool = False,
            horde_model: str = "", hf_space: str = "", hf_api_name: str = "",
            hf_image_arg: str = "image", hf_prompt_arg: str = "prompt",
            fallback_local: bool = False) -> Path:
    if provider not in ("local", "opencv", "openai", "aihorde", "hf-spaces"):
        raise CreativeError("Provider válido: local, opencv, aihorde, hf-spaces ou openai (pago)")
    # Older imported CSVs are accepted only if their input recorded authorization.
    if pin.get("image_license_confirmed") is not True:
        raise CreativeError("Confirme direitos de uso comercial da imagem antes de estilizar.")
    if provider == "openai" and not allow_paid_ai:
        raise CreativeError("Chamadas pagas requerem a opção explícita --allow-paid-ai.")
    try:
        from free_image_providers import FreeProviderError
    except ModuleNotFoundError:
        from automation.free_image_providers import FreeProviderError
    if provider in ("aihorde", "hf-spaces"):
        try:
            from free_image_providers import (
                validate_consent, FreeProviderError, horde_edit, hf_spaces_edit
            )
        except ModuleNotFoundError:
            from automation.free_image_providers import (
                validate_consent, FreeProviderError, horde_edit, hf_spaces_edit
            )
        try:
            validate_consent(public_processing=allow_public_processing,
                             model_license=confirm_model_license)
        except FreeProviderError as exc:
            raise CreativeError(str(exc)) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{pin['id']}-styled.png"
    tmp = out_dir / f".{pin['id']}-styled.tmp.png"
    pin.pop("_used_local_fallback", None)
    try:
        try:
            if provider == "openai":
                _openai_edit(pin, tmp, api_key=api_key)
            elif provider == "local":
                _local_enhance(pin, tmp)
            elif provider == "opencv":
                _opencv_enhance(pin, tmp)
            else:
                prompt = make_prompt(pin)
                if provider == "aihorde":
                    horde_edit(pin, tmp, prompt=prompt,
                               model=horde_model or os.environ.get("AIHORDE_MODEL", "").strip())
                else:
                    hf_spaces_edit(
                        pin, tmp, prompt=prompt,
                        space=hf_space or os.environ.get("HF_SPACE_ID", "").strip(),
                        api_name=hf_api_name or os.environ.get("HF_SPACE_API_NAME", "").strip(),
                        image_arg=hf_image_arg, prompt_arg=hf_prompt_arg
                    )
        except FreeProviderError as exc:
            if not fallback_local:
                raise CreativeError(str(exc)) from exc
            print(f"ATENÇÃO: IA comunitária indisponível ({exc}). Tratamento local sem IA.")
            _local_enhance(pin, tmp)
            pin["_used_local_fallback"] = True
        tmp.replace(target)
        return target
    finally:
        tmp.unlink(missing_ok=True)
