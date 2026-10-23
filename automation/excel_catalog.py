"""Catálogo Excel .xlsx sem dependências extras: espelho local da fila real.

A fila privada pins.json continua sendo a fonte de verdade para aprovação,
estado de publicação e direitos. O Excel é atualizado em cada save_store.
Não há dados inventados nem obtenção de comissões pela API do Mercado Livre.

Escrita e leitura usando OOXML/ZIP padrão (stdlib), sem serviços externos.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import warnings
import zipfile
from xml.etree import ElementTree as ET

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XML = "http://www.w3.org/XML/1998/namespace"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("", MAIN)

HEADERS = (
    "ID local", "ID anúncio MLB", "Produto", "Categoria",
    "Nicho", "Categoria MLB", "Preço verificado (R$)", "Moeda",
    "URL anúncio", "Link afiliado", "Link confirmado", "Origem do link",
    "Imagem original", "Direitos da imagem", "Imagem Pin", "Estilo do Pin",
    "Provider visual", "Status", "Criado em", "Atualizado em", "Resumo / observações",
)
WIDTHS = (19, 20, 44, 19, 25, 20, 21, 11, 49, 40, 19,
          26, 45, 21, 43, 19, 17, 18, 23, 23, 66)
MAX_ROWS = 25000
SHEET_NAMES = ("Produtos", "Resumo", "Categorias")
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <fonts count="3">
  <font><sz val="11"/><name val="Aptos"/><color rgb="FF27333A"/></font>
  <font><b/><sz val="11"/><name val="Aptos"/><color rgb="FFFFFFFF"/></font>
  <font><b/><sz val="16"/><name val="Aptos Display"/><color rgb="FFFFFFFF"/></font>
 </fonts>
 <fills count="5">
  <fill><patternFill patternType="none"/></fill>
  <fill><patternFill patternType="gray125"/></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF244E46"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFEFF5F2"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFFFF3DC"/><bgColor indexed="64"/></patternFill></fill>
 </fills>
 <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
 <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
 <cellXfs count="7">
  <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
  <xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
  <xf numFmtId="0" fontId="0" fillId="4" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
  <xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
 </cellXfs>
 <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


class ExcelCatalogError(ValueError):
    pass


def _q(name: str) -> str:
    return "{" + MAIN + "}" + name


def _col(number: int) -> str:
    chars = ""
    while number:
        number, rest = divmod(number - 1, 26)
        chars = chr(65 + rest) + chars
    return chars


def _cell(row: ET.Element, idx: int, row_no: int, value, *, style: int = 0,
          formula: str = "") -> None:
    if value is None and not formula:
        return
    ref = f"{_col(idx)}{row_no}"
    attrs = {"r": ref}
    if style:
        attrs["s"] = str(style)
    if formula:
        element = ET.SubElement(row, _q("c"), attrs)
        ET.SubElement(element, _q("f")).text = formula.lstrip("=")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        element = ET.SubElement(row, _q("c"), attrs)
        ET.SubElement(element, _q("v")).text = str(value)
    else:
        # Explicit inline string avoids treating untrusted product names/notes
        # starting with =, +, - or @ as spreadsheet formulas.
        element = ET.SubElement(row, _q("c"), {**attrs, "t": "inlineStr"})
        inline = ET.SubElement(element, _q("is"))
        text = ET.SubElement(inline, _q("t"))
        text.set("{" + XML + "}space", "preserve")
        text.text = str(value or "")[:2000]


def _row(sheet: ET.Element, index: int, values, *, style: int = 0,
         height: int = 21, numeric_cols: set[int] | None = None) -> None:
    rows = sheet.find(_q("sheetData"))
    element = ET.SubElement(rows, _q("row"), {"r": str(index), "ht": str(height),
                                               "customHeight": "1"})
    for i, value in enumerate(values, 1):
        chosen_style = 5 if numeric_cols and i in numeric_cols and isinstance(value, (int,float)) else style
        _cell(element, i, index, value, style=chosen_style)


def _sheet(*, widths: tuple[int, ...], freeze_rows: int = 0) -> ET.Element:
    sheet = ET.Element(_q("worksheet"))
    if freeze_rows:
        views = ET.SubElement(sheet, _q("sheetViews"))
        view = ET.SubElement(views, _q("sheetView"), {"workbookViewId": "0"})
        ET.SubElement(view, _q("pane"), {"ySplit": str(freeze_rows),
                                         "topLeftCell": f"A{freeze_rows + 1}",
                                         "activePane": "bottomLeft",
                                         "state": "frozen"})
    cols = ET.SubElement(sheet, _q("cols"))
    for i, width in enumerate(widths, 1):
        ET.SubElement(cols, _q("col"), {"min": str(i), "max": str(i),
                                        "width": str(width), "customWidth": "1"})
    ET.SubElement(sheet, _q("sheetData"))
    return sheet


def _niche(pin: dict) -> str:
    try:
        try:
            from prompt_templates import select_knowledge
        except ModuleNotFoundError:
            from automation.prompt_templates import select_knowledge
        return select_knowledge(pin)["slug"]
    except (KeyError, ValueError, OSError):
        return ""


def product_values(pin: dict) -> list:
    verification = pin.get("ml_verification") or {}
    price = verification.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool):
        price = None
    description = str(pin.get("description") or "").split("\n\nEste conteúdo contém link de afiliado.")[0]
    notes = pin.get("notes")
    note = " | ".join(str(x) for x in notes) if isinstance(notes, list) else ""
    updated = max((
        str(pin.get(key) or "") for key in
        ("created_at", "affiliate_confirmed_at", "prepared_at", "approved_at", "published_at")
    ), default="")
    summary = description
    if note:
        summary = (description + " | " + note).strip(" |")
    return [
        pin.get("id") or "", pin.get("item_id") or "", pin.get("title") or "",
        pin.get("category") or "", _niche(pin), pin.get("ml_category_id") or "",
        price, verification.get("currency_id") or "",
        pin.get("source_url") or pin.get("resolved_url") or "",
        pin.get("affiliate_url") or "",
        "Sim" if pin.get("affiliate_url_confirmed") else "Não",
        pin.get("affiliate_link_source") or "",
        pin.get("image_path") or "",
        "Sim" if pin.get("image_license_confirmed") else "Não",
        pin.get("preview_path") or "",
        pin.get("creative_style") or "",
        pin.get("creative_provider") or "",
        pin.get("status") or "draft", pin.get("created_at") or "",
        updated, summary,
    ]


def _products_xml(pins: dict) -> bytes:
    if len(pins) > MAX_ROWS:
        raise ExcelCatalogError("Quantidade de produtos excedeu o limite do catálogo Excel")
    sh = _sheet(widths=WIDTHS, freeze_rows=4)
    _row(sh, 1, ["GARIMPO DA VEZ  |  CATÁLOGO DE PRODUTOS"], style=2, height=37)
    _row(sh, 2, ["Gerado automaticamente a partir da fila local. Não edite: revise dados pelo CLI."],
         style=3, height=24)
    _row(sh, 4, HEADERS, style=1, height=38)
    for idx, pin in enumerate(sorted(pins.values(),
                                    key=lambda p: (str(p.get("created_at") or ""),
                                                   str(p.get("id") or ""))), 5):
        style = 3 if pin.get("status") in {"prepared", "approved", "published"} else 4
        _row(sh, idx, product_values(pin), style=style, height=27, numeric_cols={7})
    data_end = max(4, 4 + len(pins))
    ET.SubElement(sh, _q("mergeCells"), {"count":"2"}).extend([
        ET.Element(_q("mergeCell"), {"ref": "A1:U1"}),
        ET.Element(_q("mergeCell"), {"ref": "A2:U2"}),
    ])
    ET.SubElement(sh, _q("autoFilter"), {"ref": f"A4:U{data_end}"})
    return ET.tostring(sh, encoding="utf-8", xml_declaration=True)


def _summary_xml() -> bytes:
    sh = _sheet(widths=(29, 15, 4, 28, 14, 4, 31, 17, 4, 49))
    _row(sh, 1, ["GARIMPO DA VEZ  |  RESUMO DO CATÁLOGO"], style=2, height=40)
    _row(sh, 2, ["Os indicadores usam fórmulas Excel; os dados vêm de Produtos."],
         style=3, height=24)
    _row(sh, 4, ["Produtos cadastrados", "", "", "Links confirmados", "", "",
                 "Pins preparados / aprovados", ""])
    _row(sh, 8, ["Situação", "Quantidade"])
    for num, name in enumerate(("draft", "prepared", "approved", "published", "needs_check"), 9):
        _row(sh, num, [name])
        row = sh.find(_q("sheetData")).findall(_q("row"))[-1]
        _cell(row, 2, num, None, formula=f'COUNTIF(Produtos!$R$5:$R$25004,A{num})')
    data = sh.find(_q("sheetData"))
    for row in data.findall(_q("row")):
        if row.get("r") == "4":
            for cell in row.findall(_q("c")):
                cell.set("s", "1")
    row5 = ET.SubElement(data, _q("row"), {"r": "5", "ht": "32", "customHeight": "1"})
    data.remove(row5)
    data.insert(3, row5)  # Excel requires ascending row numbers.
    for col, formula in [
        (1, "COUNTA(Produtos!$A$5:$A$25004)"),
        (4, 'COUNTIF(Produtos!$K$5:$K$25004,"Sim")'),
        (7, 'COUNTIF(Produtos!$R$5:$R$25004,"prepared")+COUNTIF(Produtos!$R$5:$R$25004,"approved")'),
    ]:
        _cell(row5, col, 5, None, formula=formula, style=6)
    merges = ET.SubElement(sh, _q("mergeCells"), {"count": "2"})
    ET.SubElement(merges, _q("mergeCell"), {"ref": "A1:J1"})
    ET.SubElement(merges, _q("mergeCell"), {"ref": "A2:J2"})
    return ET.tostring(sh, encoding="utf-8", xml_declaration=True)


def _categories_xml(cache: Path) -> bytes:
    sh = _sheet(widths=(23, 48, 25), freeze_rows=3)
    _row(sh, 1, ["CATEGORIAS OFICIAIS — MERCADO LIVRE BRASIL"], style=2, height=36)
    _row(sh, 2, ["Snapshot oficial, não representa elegibilidade a comissões."], style=3)
    _row(sh, 3, ["ID de categoria", "Nome oficial", "Fonte"], style=1, height=30)
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        categories = data.get("categories", []) if data.get("source") == "mercadolibre_official_api" else []
    except (OSError, ValueError, TypeError):
        categories = []
    for i, item in enumerate(categories, 4):
        if not isinstance(item, dict):
            continue
        _row(sh, i, [item.get("id",""), item.get("name",""), "API oficial (cache)"],
             style=3)
    merges = ET.SubElement(sh, _q("mergeCells"), {"count": "2"})
    ET.SubElement(merges, _q("mergeCell"), {"ref": "A1:C1"})
    ET.SubElement(merges, _q("mergeCell"), {"ref": "A2:C2"})
    return ET.tostring(sh, encoding="utf-8", xml_declaration=True)


def _package(pins: dict, category_cache: Path) -> dict[str, bytes]:
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN}" xmlns:r="{REL}">
 <bookViews><workbookView/></bookViews><sheets>
 <sheet name="Produtos" sheetId="1" r:id="rId1"/>
 <sheet name="Resumo" sheetId="2" r:id="rId2"/>
 <sheet name="Categorias" sheetId="3" r:id="rId3"/>
 </sheets><calcPr calcMode="auto" fullCalcOnLoad="1"/></workbook>'''
    book_rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL}">
 <Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>
 <Relationship Id="rId2" Type="{REL}/worksheet" Target="worksheets/sheet2.xml"/>
 <Relationship Id="rId3" Type="{REL}/worksheet" Target="worksheets/sheet3.xml"/>
 <Relationship Id="rId4" Type="{REL}/styles" Target="styles.xml"/>
 </Relationships>'''
    root_rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL}">
 <Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/>
 </Relationships>'''
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CT}">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
 <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
 <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
 <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
 <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
 </Types>'''
    return {
        "[Content_Types].xml": content_types.encode(),
        "_rels/.rels": root_rels.encode(),
        "xl/workbook.xml": workbook.encode(),
        "xl/_rels/workbook.xml.rels": book_rels.encode(),
        "xl/styles.xml": STYLES.encode(),
        "xl/worksheets/sheet1.xml": _products_xml(pins),
        "xl/worksheets/sheet2.xml": _summary_xml(),
        "xl/worksheets/sheet3.xml": _categories_xml(category_cache),
    }


def workbook_path(store: Path) -> Path:
    """In the same gitignored data/ folder as pins.json, not under git."""
    return store.parent / "produtos.xlsx"


def sync_catalog(store: Path, data: dict, *, dest: Path | None = None) -> Path:
    """Atomic XLSX snapshot; no network and no fake data."""
    path = dest or workbook_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(__file__).resolve().parent / "knowledge" / "catalog" / "mlb_categories.json"
    parts = _package(data.get("pins", {}), cache)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp.xlsx", delete=False) as f:
        staging = Path(f.name)
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, content in parts.items():
                z.writestr(name, content)
        os.replace(staging, path)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ExcelCatalogError(
            f"Não foi possível atualizar {path} (talvez aberto no Excel). "
            "Feche a planilha e execute 'excel-sync'. O cadastro JSON está preservado."
        ) from exc
    finally:
        staging.unlink(missing_ok=True)
    return path


def read_products(path: Path) -> list[dict]:
    """Read text fields from a human-edited Produtos sheet (read-only import).

    Supports standard inline/shared-string cells; formulas are ignored rather
    than executing unknown formulas or trusting cached computation.
    """
    if not path.is_file() or path.suffix.casefold() != ".xlsx" or path.stat().st_size > 20_000_000:
        raise ExcelCatalogError("Informe um .xlsx real de até 20 MB")
    try:
        with zipfile.ZipFile(path) as z:
            workbook = ET.fromstring(z.read("xl/workbook.xml"))
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            target_id = next((
                sh.get("{" + REL + "}id") for sh in workbook.findall(
                    f".//{_q('sheet')}") if sh.get("name") == "Produtos"
            ), None)
            if not target_id:
                raise ExcelCatalogError("A planilha precisa conter a aba 'Produtos'")
            target = next((r.get("Target") for r in rels if r.get("Id") == target_id), None)
            if not target:
                raise ExcelCatalogError("Não foi possível localizar a aba Produtos")
            from posixpath import normpath
            target = (target.lstrip("/") if target.startswith("/") else normpath("xl/" + target))
            if not re.fullmatch(r"xl/worksheets/[a-zA-Z0-9_.-]+\.xml", target):
                raise ExcelCatalogError("Referência de aba inesperada")
            sheet = ET.fromstring(z.read(target))
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = ["".join(t.text or "" for t in si.findall(f".//{_q('t')}"))
                          for si in root.findall(_q("si"))]
            rows = []
            for row in sheet.findall(f".//{_q('sheetData')}/{_q('row')}"):
                cells = {}
                for c in row.findall(_q("c")):
                    if c.find(_q("f")) is not None:
                        continue  # untrusted formulas never imported
                    cell_ref = c.get("r", "")
                    col = re.match(r"[A-Z]+", cell_ref)
                    if not col:
                        continue
                    ci = 0
                    for ch in col.group():
                        ci = ci*26 + ord(ch)-64
                    v = c.find(_q("v"))
                    inline = c.find(_q("is"))
                    text = (("".join(t.text or "" for t in inline.findall(f".//{_q('t')}")))
                            if inline is not None else (v.text or "") if v is not None else "")
                    if c.get("t") == "s":
                        pos = int(text or "0")
                        text = shared[pos] if 0 <= pos < len(shared) else ""
                    cells[ci] = text
                if cells:
                    rows.append(cells)
                if len(rows) > MAX_ROWS + 10:
                    raise ExcelCatalogError("Planilha contém mais linhas que o limite")
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        raise ExcelCatalogError("Planilha Excel inválida ou não suportada") from exc
    titles = {title: idx for idx, title in enumerate(HEADERS, 1)}
    header_at = next((i for i, r in enumerate(rows)
                      if r.get(titles["Produto"]) == "Produto"
                      and r.get(titles["ID local"]) == "ID local"), None)
    if header_at is None:
        raise ExcelCatalogError("Cabeçalhos 'ID local' e 'Produto' não encontrados")
    parsed = []
    for row in rows[header_at + 1:]:
        values = {name: str(row.get(pos, "")).strip()
                  for name, pos in titles.items()}
        if any(values.values()):
            parsed.append(values)
    return parsed


def import_excel_drafts(xlsx_path: Path, store_path: Path) -> int:
    """Import only NEW records; do not trust confirmations or overwrite approvals.

    Importing the generated snapshot itself is idempotent (zero new rows).
    For a manually filled sheet, IDs may be absent and will be derived from
    its verified item ID or a stable local hash, never guessed MLB numbers.
    """
    try:
        from garimpo import (load_store, save_store, ensure_https_affiliate_link,
                             GarimpoError, DISCLOSURE, CATEGORIES, now_iso)
    except ModuleNotFoundError:
        from automation.garimpo import (load_store, save_store, ensure_https_affiliate_link,
                                        GarimpoError, DISCLOSURE, CATEGORIES, now_iso)
    try:
        from ml_ingest import validate_url
    except ModuleNotFoundError:
        from automation.ml_ingest import validate_url

    rows = read_products(xlsx_path.resolve())
    state = load_store(store_path)
    created = {}
    for pos, row in enumerate(rows, 1):
        title = " ".join(row["Produto"].split())
        if not 5 <= len(title) <= 100:
            raise ExcelCatalogError(f"Linha de produto {pos}: informe título com 5 a 100 caracteres.")
        item_id = row["ID anúncio MLB"].strip().upper()
        if item_id and not re.fullmatch(r"MLB[0-9]{6,18}", item_id):
            raise ExcelCatalogError(f"Linha de produto {pos}: ID de anúncio MLB inválido.")
        category = row["Categoria"].strip().lower()
        if category not in CATEGORIES:
            raise ExcelCatalogError(
                f"Linha de produto {pos}: categoria deve ser "
                + ", ".join(CATEGORIES)
            )
        category_id = row["Categoria MLB"].strip().upper()
        if category_id and not re.fullmatch(r"MLB[0-9]{2,12}", category_id):
            raise ExcelCatalogError(f"Linha de produto {pos}: ID de categoria oficial inválido.")
        source_url = row["URL anúncio"].strip()
        if source_url:
            try:
                source_url = validate_url(source_url)
            except ValueError as exc:
                raise ExcelCatalogError(f"Linha de produto {pos}: URL de anúncio inválida.") from exc
        affiliate = row["Link afiliado"].strip()
        if affiliate:
            try:
                affiliate = ensure_https_affiliate_link(affiliate)
            except GarimpoError as exc:
                raise ExcelCatalogError(f"Linha de produto {pos}: link afiliado inválido.") from exc
        local_id = row["ID local"].strip() or (
            item_id.lower() if item_id else
            "excel-" + hashlib.sha256(
                (source_url + "|" + title).encode("utf-8")
            ).hexdigest()[:12]
        )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,49}", local_id):
            raise ExcelCatalogError(f"Linha de produto {pos}: ID local inválido.")
        # Never use an alternate local ID to duplicate a registered MLB item.
        if local_id in state["pins"] or local_id in created:
            continue
        if item_id and any(p.get("item_id") == item_id for p in
                           list(state["pins"].values()) + list(created.values())):
            continue
        image = row["Imagem original"].strip()
        if image:
            file = Path(image).expanduser()
            if not file.is_absolute():
                file = xlsx_path.parent / file
            if file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                raise ExcelCatalogError(f"Linha de produto {pos}: imagem inválida.")
            image = str(file.resolve())
        summary = (row["Resumo / observações"] or
                   "Confira detalhes e condições no anúncio original.").strip()[:560]
        pin = {
            "id": local_id, "item_id": item_id, "ml_category_id": category_id,
            "title": title, "description": summary + "\n\n" + DISCLOSURE,
            "category": category, "source_url": source_url,
            "resolved_url": source_url, "image_path": image,
            "image_license_confirmed": False,
            "affiliate_url": affiliate, "affiliate_url_confirmed": False,
            "affiliate_link_pending": bool(affiliate),
            "affiliate_link_source": "excel_unconfirmed" if affiliate else "",
            "affiliate_confirmed_at": "",
            "title_confirmed": False, "category_confirmed": False,
            "created_by_url": True, "created_at": now_iso(), "status": "draft",
            "preview_path": "", "stylized_image_path": "", "board_id": "",
            "approval_sha256": "", "pin_id": "",
            "notes": ["Importado do Excel: confirme título, categoria, foto e "
                      "link individual obtido na Central de Afiliados."],
        }
        created[local_id] = pin
    if created:
        state["pins"].update(created)
        save_store(store_path, state)
    return len(created)
