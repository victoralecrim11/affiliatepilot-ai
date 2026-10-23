"""Menu de categorias e anúncios reais via API oficial Mercado Livre Brasil.

Não gera links de afiliados; IDs MLB de ANÚNCIO são diferentes de IDs de
categoria e MLBU/produtos de catálogo. A API pode recusar buscas (403).
Nenhuma listagem fictícia ou scraping/contorno de acesso é permitido.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.mercadolibre.com"
CATEGORY_RE = re.compile(r"MLB[0-9]{2,12}\Z")
ITEM_RE = re.compile(r"MLB[0-9]{6,18}\Z")
CACHE = Path(__file__).resolve().parent / "knowledge" / "catalog" / "mlb_categories.json"


class DiscoveryError(ValueError):
    pass


def _api_get(path: str, params: dict | None = None, token: str = "") -> object:
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]{1,140}", path):
        raise DiscoveryError("Caminho de API não permitido")
    url = API + path + (("?" + urlencode(params)) if params else "")
    headers = {"Accept": "application/json", "User-Agent": "GarimpoDaVez/2.0 (official API)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers), timeout=18) as resp:
            raw = resp.read(1_500_001)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise DiscoveryError(
                f"Busca oficial bloqueada (HTTP {exc.code}) para este acesso. "
                "Continue pelo site Mercado Livre: selecione o anúncio e use "
                "'ingest-url URL_DO_ANUNCIO'. Não usar catálogo como anúncio nem contornar a API."
            ) from exc
        if exc.code == 429:
            raise DiscoveryError("API com limite de requisições (429); tente mais tarde.") from exc
        raise DiscoveryError(f"Falha na API Mercado Livre (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DiscoveryError("API Mercado Livre indisponível/rede sem resposta.") from exc
    if len(raw) > 1_500_000:
        raise DiscoveryError("Resposta da API maior que o limite")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise DiscoveryError("API devolveu JSON inválido") from exc


def root_categories(*, token: str = "") -> tuple[list[dict], str]:
    """Preferir API; cache oficial do repositório somente se endpoint falhar."""
    try:
        raw = _api_get("/sites/MLB/categories", token=token)
        if not isinstance(raw, list):
            raise DiscoveryError("Resposta de categorias inesperada")
        rows = normalize_categories(raw)
        if not rows:
            raise DiscoveryError("API não retornou categorias")
        return rows, "api"
    except DiscoveryError:
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("source") != "mercadolibre_official_api":
                raise ValueError("cache sem fonte oficial")
            rows = normalize_categories(cached.get("categories", []))
            if rows:
                return rows, "cache_oficial"
        except (OSError, ValueError, TypeError):
            pass
        raise


def normalize_categories(rows: list) -> list[dict]:
    out = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        code, name = x.get("id"), x.get("name")
        if isinstance(code, str) and CATEGORY_RE.fullmatch(code) and isinstance(name, str) and name.strip():
            out.append({"id": code, "name": name.strip()[:120]})
    return out


def children_of(category_id: str, *, token: str = "") -> tuple[list[dict], dict]:
    if not CATEGORY_RE.fullmatch(category_id):
        raise DiscoveryError("ID de categoria inválido")
    raw = _api_get("/categories/" + category_id, token=token)
    if not isinstance(raw, dict) or raw.get("id") != category_id:
        raise DiscoveryError("Detalhe da categoria inválido")
    children = normalize_categories(raw.get("children_categories") or [])
    return children, {
        "id": category_id, "name": str(raw.get("name") or "")[:120],
        "path": normalize_categories(raw.get("path_from_root") or []),
    }


def search_listings(query: str, *, category_id: str = "", limit: int = 15,
                    token: str = "") -> list[dict]:
    """Busca listagens (MLB...), NUNCA produtos de catálogo MLBU/MLB de /products."""
    query = " ".join(query.split())
    if not 2 <= len(query) <= 100:
        raise DiscoveryError("Busca exige 2 a 100 caracteres de descrição do produto")
    if category_id and not CATEGORY_RE.fullmatch(category_id):
        raise DiscoveryError("ID de categoria inválido")
    if not 1 <= limit <= 30:
        raise DiscoveryError("Limite deve ser entre 1 e 30")
    params = {"q": query, "limit": limit}
    if category_id:
        params["category"] = category_id
    raw = _api_get("/sites/MLB/search", params, token=token)
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        raise DiscoveryError("Resposta de busca inesperada ou acesso indisponível")
    try:
        from ml_ingest import validate_url, extract_item_id
    except ModuleNotFoundError:
        from automation.ml_ingest import validate_url, extract_item_id
    found = []
    seen = set()
    for obj in raw["results"][:limit]:
        if not isinstance(obj, dict):
            continue
        item_id, link = obj.get("id"), obj.get("permalink")
        if not isinstance(item_id, str) or not ITEM_RE.fullmatch(item_id) or item_id in seen:
            continue
        if not isinstance(link, str) or not link:
            continue
        try:
            validate_url(link)
            if extract_item_id(link) != item_id:
                continue  # no product catalog URL or mismatching advertisement
        except (ValueError, TypeError):
            continue
        status = obj.get("status")
        if status not in (None, "active"):
            continue
        title = str(obj.get("title") or "").strip()[:100]
        if not title:
            continue
        cat_id = obj.get("category_id")
        if not isinstance(cat_id, str) or not CATEGORY_RE.fullmatch(cat_id):
            cat_id = ""
        price = obj.get("price")
        if not isinstance(price, (float, int)) or isinstance(price, bool) or price < 0:
            price = None
        found.append({
            "id": item_id, "title": title,
            "category_id": cat_id, "permalink": link,
            "price": price, "currency": obj.get("currency_id") or "",
            "source": "mercadolivre_official_search",
        })
        seen.add(item_id)
    return found


def read_token() -> str:
    """Usa sessão OAuth local autorizada; nunca grava/imprime token."""
    value = os.environ.get("MERCADOLIVRE_ACCESS_TOKEN", "").strip()
    if value:
        return value
    try:
        try:
            from ml_oauth import get_access_token
        except ModuleNotFoundError:
            from automation.ml_oauth import get_access_token
        return get_access_token() or ""
    except Exception:
        return ""


def pick_one(options: list[dict], heading: str, *, selection: int | None = None,
             allow_zero: bool = False, input_fn=input, output=print) -> int:
    if not options:
        raise DiscoveryError("Nenhum resultado disponível para selecionar")
    output(heading)
    for i, row in enumerate(options, 1):
        suffix = f"  ({row['id']})" if row.get("id") else ""
        output(f" {i:>2}. {row.get('name') or row.get('title')}{suffix}")
    if allow_zero:
        output("  0. Usar categoria atual")
    if selection is not None:
        if not (0 if allow_zero else 1) <= selection <= len(options):
            raise DiscoveryError(f"Seleção deve ser de {0 if allow_zero else 1} a {len(options)}")
        return selection
    if not sys.stdin.isatty() and input_fn is input:
        raise DiscoveryError("Terminal não interativo: passe --pick N ou --category-id e --query.")
    while True:
        try:
            value = input_fn("Escolha o número: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise DiscoveryError("Seleção cancelada") from exc
        if value.isdigit() and (0 if allow_zero else 1) <= int(value) <= len(options):
            return int(value)
        output("Número inválido, tente novamente.")


def browse_categories(*, token: str, category_id: str = "", max_depth: int = 5,
                      input_fn=input, output=print) -> dict:
    """Explora a árvore por cliques numéricos. Categoria folha ou pai permitida."""
    if category_id:
        if not CATEGORY_RE.fullmatch(category_id):
            raise DiscoveryError("Categoria inválida")
        try:
            _, detail = children_of(category_id, token=token)
            return detail
        except DiscoveryError as exc:
            # ID official root cached can remain useful even on API 403.
            roots, _ = root_categories(token=token)
            match = next((x for x in roots if x["id"] == category_id), None)
            if match:
                return {"id": match["id"], "name": match["name"], "path": [match]}
            raise exc

    roots, origin = root_categories(token=token)
    output(f"Categorias principais MLB ({origin}):")
    index = pick_one(roots, "Selecione uma categoria:", input_fn=input_fn, output=output)
    current = roots[index - 1]
    path = [current]
    for _ in range(max_depth):
        try:
            children, _ = children_of(current["id"], token=token)
        except DiscoveryError as exc:
            output(f"Não foi possível consultar subcategorias ({exc}). Mantendo categoria atual.")
            break
        if not children:
            break
        index = pick_one(children, f"Subcategorias de {current['name']}:", allow_zero=True,
                         input_fn=input_fn, output=output)
        if index == 0:
            break
        current = children[index - 1]
        path.append(current)
    return {"id": current["id"], "name": current["name"], "path": path}
