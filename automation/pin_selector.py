"""Resolve produtos da fila por categoria/nicho/nome, sem decorar IDs.

Seleção assistida apenas no terminal interativo. Nunca escolhe arbitrariamente
entre vários candidatos, especialmente para aprovar/publicar.
"""
from __future__ import annotations

import sys
import unicodedata


class SelectionError(ValueError):
    pass


def fold(s: object) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "").casefold())
                   if not unicodedata.combining(ch))


ELIGIBLE = {
    "export-business": {"prepared", "approved"},
    "prepare": {"draft", "prepared"},
    "stylize": {"draft", "prepared"},
    "show": None,
    "knowledge": None,
    "review": {"draft", "prepared"},
    "affiliate-link": {"draft", "prepared"},
    "confirm-link": {"draft", "prepared"},
    "confirm-image-rights": {"draft", "prepared"},
    "approve": {"prepared"},
    "publish": {"approved"},
    "verify-ml": {"draft", "prepared"},
    "reset": {"needs_check", "publishing"},
}


def filter_pins(pins: dict, *, command: str, search: str = "",
                category: str = "") -> list[dict]:
    allowed = ELIGIBLE.get(command)
    results = []
    for pid, pin in pins.items():
        if allowed and pin.get("status") not in allowed:
            continue
        if search and fold(search) not in fold(" ".join((
            pid, pin.get("title", ""), pin.get("item_id", "")))):
            continue
        if category:
            aliases = [pin.get("category", ""), pin.get("ml_category_id", ""),
                       pin.get("ml_category_name", "")]
            try:
                try:
                    from prompt_templates import select_knowledge
                except ModuleNotFoundError:
                    from automation.prompt_templates import select_knowledge
                aliases.append(select_knowledge(pin)["slug"])
            except (ValueError, OSError, KeyError):
                pass
            if not any(fold(category) in fold(v) for v in aliases):
                continue
        results.append(pin)
    return sorted(results, key=lambda p: (
        fold(p.get("title", "")), fold(p.get("id", ""))
    ))


def resolve_pin(pins: dict, *, command: str, id_: str | None = None,
                search: str = "", category: str = "",
                input_fn=input, output=print, interactive: bool | None = None) -> dict:
    if id_:
        pin = pins.get(id_)
        if pin is None:
            raise SelectionError(f"Pin '{id_}' não cadastrado")
        return pin
    found = filter_pins(pins, command=command, search=search, category=category)
    if not found:
        raise SelectionError("Nenhum produto compatível na fila. Use 'list' ou 'ml-discover'.")
    output(f"Produtos cadastrados para '{command}' ({len(found)}):")
    for n, pin in enumerate(found, 1):
        output(f" {n:>2}. {pin.get('title', '?')} | {pin.get('category', '?')} "
               f"| {pin.get('status', '?')} | {pin.get('id', '?')}")
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        if len(found) == 1:
            output(f"Selecionado automaticamente: {found[0]['id']}")
            return found[0]
        raise SelectionError(
            "Há vários produtos. Execute em um PowerShell interativo para escolher "
            "o número, ou use --choose-search/--choose-category para filtrar."
        )
    while True:
        try:
            answer = input_fn("Escolha o número (ou 0 para cancelar): ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SelectionError("Seleção cancelada") from exc
        if answer == "0":
            raise SelectionError("Seleção cancelada")
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer) - 1]
        output("Número inválido.")
