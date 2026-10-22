#!/usr/bin/env python3
"""Sincronização opcional, somente leitura, das categorias raiz do Mercado Livre Brasil.

A API não fornece diretrizes de design; textos knowledge são curadoria editorial.
Falhas HTTP (inclusive 403) não sobrescrevem o cache local existente.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEST = Path(__file__).resolve().parent / "knowledge" / "catalog" / "mlb_categories.json"
API_URL = "https://api.mercadolibre.com/sites/MLB/categories"


def fetch_categories(token: str = "") -> list[dict]:
    headers = {"Accept": "application/json", "User-Agent": "GarimpoDaVez/1.3 category sync"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(API_URL, headers=headers)
    with urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError("Resposta não OK da API oficial")
        payload = resp.read(300_000)
    items = json.loads(payload)
    if not isinstance(items, list) or not 1 <= len(items) <= 250:
        raise ValueError("Lista de categorias inválida")
    validated = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("Entrada inválida no retorno da API")
        name, id_ = entry.get("name"), entry.get("id")
        if not isinstance(name, str) or not name.strip() or not isinstance(id_, str) or not re.fullmatch(r"MLB\d{2,12}", id_):
            raise ValueError("ID/nome de categoria inválido")
        validated.append({"id": id_, "name": name.strip()[:120]})
    return validated


def sync(*, with_oauth: bool = False, output: Path = DEST) -> int:
    token = ""
    if with_oauth:
        try:
            try:
                from ml_oauth import get_access_token
            except ModuleNotFoundError:
                from automation.ml_oauth import get_access_token
            token = get_access_token()
        except Exception:
            print("OAuth indisponível; catálogo existente preservado.")
            return 2
    try:
        data = fetch_categories(token)
    except HTTPError as exc:
        print(f"API oficial retornou HTTP {exc.code}. Cache anterior mantido (se existir).")
        return 2
    except (URLError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print("Não foi possível sincronizar categorias:", type(exc).__name__, "- cache anterior preservado.")
        return 2
    obj = {"source": "mercadolibre_official_api", "site_id": "MLB",
           "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "categories": data}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent,
                                     suffix=".tmp", delete=False) as handle:
        tmp = Path(handle.name)
        json.dump(obj, handle, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Sincronizadas {len(data)} categorias raiz oficiais no arquivo {output}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Consultar a árvore raiz do Mercado Livre Brasil")
    parser.add_argument("--with-oauth", action="store_true", help="Usar token local já autorizado (não será exibido)")
    args = parser.parse_args()
    return sync(with_oauth=args.with_oauth)


if __name__ == "__main__":
    raise SystemExit(main())
