"""Diagnóstico somente leitura de Hugging Face Spaces (não consome GPU).

Não envia imagens, não carrega token HF e não executa predict/submit.
Classificação de exceções deliberadamente não reproduz dados privados da resposta.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import re


class HFDiagnosticError(ValueError):
    pass


def classify_hf_error(exc: BaseException) -> str:
    fragments = []
    seen = set()
    current = exc
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        fragments.append((type(current).__name__ + ": " + str(current)[:1700]).lower())
        current = current.__cause__ or current.__context__
    text = " ".join(fragments)
    if any(word in text for word in ("quota", "zerogpu", "gpu limit", "credits exceeded",
                                     "429", "rate limit", "too many requests")):
        return ("Hugging Face: provável limite de GPU/uso anônimo excedido. "
                "O script usa token=False (sem conta); tente novamente quando a cota "
                "reiniciar ou use um Space gratuito compatível. Não há cobrança automática.")
    if any(word in text for word in ("sign in", "log in", "unauthorized", "401",
                                     "forbidden", "403", "authentication required")):
        return ("Hugging Face: Space requer autenticação ou bloqueou acesso anônimo. "
                "Este adapter não usa tokens para evitar consumo de créditos pagos. "
                "Teste a interface pública no navegador.")
    if any(word in text for word in ("unexpected keyword", "unexpected parameter",
                                     "missing required", "missing argument",
                                     "validationerror", "invalid parameter", "schema")):
        return ("Hugging Face: assinatura da API não corresponde a imagem/prompt. "
                "Execute 'python automation/garimpo.py hf-check' para conferir endpoint "
                "e nomes de parâmetros antes de tentar novamente.")
    if any(word in text for word in ("timeout", "timed out", "connection", "502", "503",
                                     "504", "unavailable", "bad gateway")):
        return ("Hugging Face: falha temporária de rede, fila ou servidor. "
                "Nenhuma imagem será aprovada automaticamente.")
    return (f"Hugging Face: falha remota ({type(exc).__name__}). "
            "O serviço pode ocultar a mensagem interna, então não é possível concluir "
            "que seja cota ou parâmetros. Rode 'hf-check' (sem usar GPU) e verifique "
            "se a interface do Space exige login.")


def inspect_space(space: str, api_name: str, *, image_arg: str = "image",
                  prompt_arg: str = "prompt") -> dict:
    """Metadata only; no user photo, predict, account token or GPU calls."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,80}", space):
        raise HFDiagnosticError("Space inválido; formato correto: autor/nome")
    if not re.fullmatch(r"/[A-Za-z0-9_-]{1,65}", api_name):
        raise HFDiagnosticError("Endpoint inválido; exemplo: /infer")
    try:
        from gradio_client import Client
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise HFDiagnosticError("Instale automation/requirements-cloud.txt") from exc
    try:
        info = HfApi(token=False).space_info(space)
        runtime = getattr(info, "runtime", None)
        stage = str(getattr(runtime, "stage", "unknown"))
        hardware = str(getattr(runtime, "hardware", "unknown"))
        # Client logs endpoint detail otherwise; suppress to keep diagnostic compact.
        with redirect_stdout(StringIO()):
            client = Client(space, token=False, verbose=False)
            spec = client.view_api(return_format="dict")
        endpoints = spec.get("named_endpoints", {})
        endpoint = endpoints.get(api_name)
        if endpoint is None:
            return {
                "space": space, "stage": stage, "hardware": hardware,
                "endpoint": api_name, "available": sorted(endpoints),
                "compatible": False, "issue": "Endpoint não listado pelo Space",
            }
        params = endpoint.get("parameters", [])
        names = [str(x.get("parameter_name", "")) for x in params]
        required = [str(x.get("parameter_name")) for x in params
                    if not x.get("parameter_has_default", False)]
        missing = sorted(set(required) - {image_arg, prompt_arg})
        matched = image_arg in names and prompt_arg in names and not missing
        return {
            "space": space, "stage": stage, "hardware": hardware,
            "endpoint": api_name, "available": sorted(endpoints),
            "required": required, "image_arg": image_arg,
            "prompt_arg": prompt_arg, "compatible": matched,
            "issue": ("OK: parâmetros obrigatórios compatíveis" if matched
                      else "Verifique parâmetros obrigatórios, imagem e prompt"),
        }
    except HFDiagnosticError:
        raise
    except Exception as exc:
        raise HFDiagnosticError(classify_hf_error(exc)) from exc
