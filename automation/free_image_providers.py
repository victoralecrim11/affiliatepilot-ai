"""Free-first cloud image adapters; never purchases credits or auto-publishes.

Sending a product photo to third-party workers requires explicit consent.
Commercial rights for source and model/Space must be checked by the user.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from PIL import Image, ImageOps

HORDE = "https://aihorde.net/api/v2"
MAX_RESULT = 15 * 1024 * 1024
MAX_WAIT = 180


class FreeProviderError(ValueError):
    pass


def validate_consent(*, public_processing: bool, model_license: bool) -> None:
    if not public_processing:
        raise FreeProviderError(
            "Nuvem comunitária pode expor imagem e prompt: informe --allow-public-processing "
            "após concordar com essa divulgação."
        )
    if not model_license:
        raise FreeProviderError(
            "Confira termos comerciais do modelo e direitos da imagem; informe --confirm-model-license."
        )


def _normalized_png(image_bytes: bytes, target: Path) -> None:
    if not image_bytes or len(image_bytes) > MAX_RESULT:
        raise FreeProviderError("Resposta de imagem vazia ou acima do limite")
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        with Image.open(BytesIO(image_bytes)) as img:
            img.load()
            if img.width < 128 or img.height < 128 or img.width * img.height > 30_000_000:
                raise FreeProviderError("Dimensão inesperada na imagem gerada")
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.save(target, "PNG", optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise FreeProviderError("A resposta não contém uma imagem válida") from exc


def _source_webp(pin: dict) -> str:
    source = Path(pin.get("image_path") or "")
    if not source.is_file():
        raise FreeProviderError("Imagem de origem não encontrada")
    try:
        with Image.open(source) as im:
            im = ImageOps.exif_transpose(im)
            im.load()
            if im.width * im.height > 30_000_000:
                raise FreeProviderError("Foto excede o limite de pixels")
            # Contain + canvas preserve o produto sem esticar a proporção.
            im = ImageOps.pad(im.convert("RGB"), (512, 768), color="#f5efe3")
            buff = BytesIO()
            im.save(buff, "WEBP", quality=83)
        return base64.b64encode(buff.getvalue()).decode("ascii")
    except (OSError, Image.DecompressionBombError) as exc:
        raise FreeProviderError("Imagem de origem inválida") from exc


def _horde_json(path: str, *, method: str = "GET", payload: dict | None = None,
                apikey: str = "") -> dict:
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]{1,160}", path):
        raise FreeProviderError("Rota AI Horde inválida")
    hdr = {"Client-Agent": "garimpo-da-vez:1.0:github.com/victoralecrim11/garimpo-da-vez",
           "Accept": "application/json", "apikey": apikey or "0000000000"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    request = Request(HORDE + path, data=data, headers=hdr, method=method)
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise FreeProviderError("Resposta AI Horde excessivamente grande")
        result = json.loads(raw)
    except HTTPError as exc:
        raise FreeProviderError(f"AI Horde indisponível ou sem cota (HTTP {exc.code})") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise FreeProviderError("Falha de conexão/resposta da AI Horde") from exc
    if not isinstance(result, dict):
        raise FreeProviderError("Formato de resposta AI Horde inesperado")
    return result


def _horde_output_bytes(value: str) -> bytes:
    """Accept inline base64 or provider-controlled image CDN URLs, never arbitrary URLs."""
    if value.startswith("https://"):
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        safe_hosts = (
            host == "aihorde.net" or host.endswith(".aihorde.net")
            or host == "stablehorde.net" or host.endswith(".stablehorde.net")
            or host.endswith(".r2.dev") or host.endswith(".cloudflarestorage.com")
        )
        if not safe_hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise FreeProviderError("URL de imagem retornada fora dos hosts permitidos")
        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                target = urlsplit(newurl)
                newhost = (target.hostname or "").lower()
                if target.scheme != "https" or not (
                    newhost.endswith(".r2.dev") or newhost.endswith(".cloudflarestorage.com")
                    or newhost.endswith(".aihorde.net") or newhost.endswith(".stablehorde.net")
                ):
                    raise FreeProviderError("Redirecionamento para host de imagem não autorizado")
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        try:
            with build_opener(SafeRedirect()).open(
                Request(value, headers={"User-Agent": "GarimpoDaVez/1.0"}), timeout=30
            ) as response:
                return response.read(MAX_RESULT + 1)
        except (OSError, URLError, TimeoutError, HTTPError) as exc:
            raise FreeProviderError("Não foi possível obter imagem da AI Horde") from exc
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise FreeProviderError("Resposta AI Horde sem base64 válido") from exc


def horde_edit(pin: dict, target: Path, *, prompt: str, model: str,
               timeout: int = MAX_WAIT) -> None:
    """One img2img job, bounded wait, model name explicitly supplied by user."""
    if not model or len(model) > 100 or not re.fullmatch(r"[\w .:/()-]+", model):
        raise FreeProviderError("Defina AIHORDE_MODEL com nome do modelo e licença conferida")
    if not 15 <= timeout <= 600:
        raise FreeProviderError("Timeout AI Horde deve ficar entre 15 e 600 segundos")
    source = _source_webp(pin)
    apikey = os.environ.get("AIHORDE_API_KEY", "").strip()
    request = {
        "prompt": prompt[:4000],
        "models": [model],
        "source_image": source,
        "source_processing": "img2img",
        "params": {"width": 512, "height": 768, "steps": 20, "n": 1,
                   "sampler_name": "k_euler_a", "cfg_scale": 6.5,
                   "denoising_strength": 0.27},
        "nsfw": False,
        "trusted_workers": True,
        "validated_backends": True,
        "r2": False,
        "shared": False if apikey else True,  # Anonymous use may force public sharing.
    }
    result = _horde_json("/generate/async", method="POST", payload=request, apikey=apikey)
    job = result.get("id")
    if not isinstance(job, str) or not re.fullmatch(r"[a-fA-F0-9-]{20,60}", job):
        raise FreeProviderError("AI Horde não devolveu ID válido de job")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            state = _horde_json("/generate/check/" + job, apikey=apikey)
            if state.get("faulted") or state.get("is_possible") is False:
                raise FreeProviderError("Job recusado ou sem workers compatíveis")
            if state.get("done"):
                data = _horde_json("/generate/status/" + job, apikey=apikey)
                generations = data.get("generations") or []
                if not generations or not isinstance(generations[0], dict):
                    raise FreeProviderError("Job finalizado sem imagem")
                first = generations[0]
                if first.get("censored"):
                    raise FreeProviderError("Imagem censurada pelo provedor")
                value = first.get("img")
                if not isinstance(value, str):
                    raise FreeProviderError("Resultado sem arquivo de imagem")
                _normalized_png(_horde_output_bytes(value), target)
                return
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        raise FreeProviderError("Fila AI Horde excedeu tempo máximo; imagem não alterada")
    finally:
        # Cancel only when job remains pending; status GET is read-only and non-billed.
        # AI Horde jobs expire server-side; avoid a second deletion if already done.
        pass


def _space_output_path(value) -> Path:
    # Gradio downloads outputs to local paths. Do not follow arbitrary remote URLs.
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            raise FreeProviderError("Space retornou URL remota em vez de arquivo baixado localmente")
        path = Path(value)
        if not path.is_file() or path.is_symlink():
            raise FreeProviderError("Space não retornou imagem local válida")
        return path
    if isinstance(value, dict) and isinstance(value.get("path"), str):
        return _space_output_path(value["path"])
    if isinstance(value, (list, tuple)):
        for entry in value:
            try:
                return _space_output_path(entry)
            except FreeProviderError:
                continue
    raise FreeProviderError("Formato de saída desconhecido do Hugging Face Space")


def hf_spaces_edit(pin: dict, target: Path, *, prompt: str, space: str, api_name: str,
                   image_arg: str = "image", prompt_arg: str = "prompt") -> None:
    """Generic public Gradio Space. Explicit endpoint & model-license review required."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,80}", space):
        raise FreeProviderError("Defina HF_SPACE_ID como 'autor/nome-do-space' público")
    if not re.fullmatch(r"/[A-Za-z0-9_-]{1,65}", api_name):
        raise FreeProviderError("Defina HF_SPACE_API_NAME (ex.: /edit)")
    if image_arg == prompt_arg or not all(
        re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,60}", k)
        for k in (image_arg, prompt_arg)
    ):
        raise FreeProviderError("Nomes dos argumentos da API do Space inválidos")
    try:
        from gradio_client import Client, handle_file
    except ImportError as exc:
        raise FreeProviderError(
            "Instale gradio_client: python -m pip install -r automation/requirements-cloud.txt"
        ) from exc
    # Anonymous public use only. No HF token, credit, duplication or hardware upgrade.
    # Supported Gradio client versions accept token=False, suppress cached credentials.
    try:
        client = Client(space, token=False, verbose=False)
        response = client.predict(
            api_name=api_name, **{image_arg: handle_file(str(Path(pin["image_path"]).resolve())),
                                  prompt_arg: prompt[:4000]}
        )
        output = _space_output_path(response)
        if output.stat().st_size > MAX_RESULT:
            raise FreeProviderError("Space retornou imagem grande demais")
        _normalized_png(output.read_bytes(), target)
    except FreeProviderError:
        raise
    except Exception as exc:
        try:
            from hf_diagnostics import classify_hf_error
        except ModuleNotFoundError:
            from automation.hf_diagnostics import classify_hf_error
        raise FreeProviderError(classify_hf_error(exc)) from exc
