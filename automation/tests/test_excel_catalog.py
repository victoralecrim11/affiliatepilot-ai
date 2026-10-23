"""Offline regression tests: automatic XLSX mirror of real per-product queue."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:
    from automation import garimpo, excel_catalog
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import garimpo, excel_catalog


class ExcelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "data" / "pins.json"
        self.one = {
            "id": "produto-1",
            "item_id": "MLB6797156948",
            "title": "Kit Refletor LED para jardim",
            "category": "casa", "ml_category_id": "MLB123456",
            "description": "Confira especificações do produto."
                           "\n\n" + garimpo.DISCLOSURE,
            "affiliate_url": "",
            "affiliate_url_confirmed": False,
            "affiliate_link_source": "",
            "image_license_confirmed": False,
            "image_path": "",
            "status": "draft", "created_at": "2026-10-23T10:00:00+00:00",
            "source_url": "https://produto.mercadolivre.com.br/MLB-6797156948-teste-_JM",
            "preview_path": "",
        }

    def data(self, *pins):
        return {"version": 1, "pins": {p["id"]: p for p in pins}}

    def test_excel_is_created_automatically_when_queue_changes(self):
        garimpo.save_store(self.store, self.data(self.one))
        dest = self.store.parent / "produtos.xlsx"
        self.assertTrue(dest.is_file())
        with ZipFile(dest) as z:
            self.assertIsNone(z.testzip())
            names = z.namelist()
            for expected in (
                "[Content_Types].xml", "xl/workbook.xml",
                "xl/styles.xml", "xl/worksheets/sheet1.xml",
                "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml",
            ):
                self.assertIn(expected, names)
            products = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("MLB6797156948", products)
            self.assertIn("Kit Refletor LED", products)
            self.assertIn("autoFilter", products)
            summary = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertIn("COUNTIF", summary)
            self.assertIn("COUNTA", summary)
            sheet = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
            ns = "{" + excel_catalog.MAIN + "}"
            row_numbers = [int(row.get("r")) for row in
                           sheet.findall(f".//{ns}sheetData/{ns}row")]
            self.assertEqual(row_numbers, sorted(row_numbers))

    def test_per_product_links_and_categories_are_not_mixed(self):
        second = dict(self.one, id="produto-2", item_id="MLB6123456789",
                      category="tecnologia", title="Notebook Gamer com teclado",
                      affiliate_url="https://meli.la/LinkReal2",
                      affiliate_url_confirmed=True, status="prepared")
        first = dict(self.one, affiliate_url="https://meli.la/LinkReal1",
                     affiliate_url_confirmed=True)
        garimpo.save_store(self.store, self.data(first, second))
        rows = excel_catalog.read_products(self.store.parent / "produtos.xlsx")
        self.assertEqual(len(rows), 2)
        mapping = {r["ID local"]: r for r in rows}
        self.assertEqual(mapping["produto-1"]["Link afiliado"], "https://meli.la/LinkReal1")
        self.assertEqual(mapping["produto-2"]["Link afiliado"], "https://meli.la/LinkReal2")
        self.assertEqual(mapping["produto-2"]["Categoria"], "tecnologia")
        self.assertEqual(mapping["produto-2"]["Status"], "prepared")
        self.assertEqual(mapping["produto-1"]["Link confirmado"], "Sim")

    def test_newly_discovered_draft_goes_to_excel_without_link(self):
        garimpo.save_store(self.store, self.data(self.one))
        first = excel_catalog.read_products(self.store.parent / "produtos.xlsx")
        self.assertEqual(first[0]["Link afiliado"], "")
        self.assertEqual(first[0]["Direitos da imagem"], "Não")
        self.assertEqual(first[0]["Status"], "draft")
        self.assertEqual(first[0]["ID anúncio MLB"], "MLB6797156948")

    def test_excel_updates_after_link_confirmation_and_preparation(self):
        garimpo.save_store(self.store, self.data(self.one))
        self.one["affiliate_url"] = "https://meli.la/RealLink"
        self.one["affiliate_url_confirmed"] = True
        self.one["status"] = "prepared"
        self.one["preview_path"] = "C:/imagens/pin.jpg"
        garimpo.save_store(self.store, self.data(self.one))
        rows = excel_catalog.read_products(self.store.parent / "produtos.xlsx")
        self.assertEqual(rows[0]["Link confirmado"], "Sim")
        self.assertEqual(rows[0]["Status"], "prepared")
        self.assertEqual(rows[0]["Imagem Pin"], "C:/imagens/pin.jpg")

    def test_excel_escapes_formula_like_untrusted_product_titles(self):
        unusual = dict(self.one, title='=HYPERLINK("https://evil.example";"clique")')
        garimpo.save_store(self.store, self.data(unusual))
        with ZipFile(self.store.parent / "produtos.xlsx") as z:
            xml = z.read("xl/worksheets/sheet1.xml")
            self.assertNotIn(b"<f>", xml)
            self.assertIn(b"inlineStr", xml)

    def test_xlsx_sync_command_creates_empty_catalog_and_official_categories(self):
        self.assertEqual(garimpo.run([
            "--store", str(self.store), "excel-sync"
        ]), 0)
        file = self.store.parent / "produtos.xlsx"
        self.assertTrue(file.is_file())
        with ZipFile(file) as z:
            categories = z.read("xl/worksheets/sheet3.xml").decode("utf-8")
            self.assertIn("Fonte", categories)
            self.assertIn("API oficial", categories)
        self.assertFalse(self.store.exists())  # catalog creation does not mutate queue

    def test_import_xlsx_creates_unconfirmed_drafts_no_overwrites(self):
        generated = self.root / "entrada.xlsx"
        excel_catalog.sync_catalog(self.store, self.data(self.one), dest=generated)
        imported_store = self.root / "imported" / "pins.json"
        self.assertEqual(garimpo.run([
            "--store", str(imported_store), "import-xlsx", str(generated)
        ]), 0)
        pin = garimpo.load_store(imported_store)["pins"]["produto-1"]
        self.assertEqual(pin["item_id"], "MLB6797156948")
        self.assertFalse(pin["affiliate_url_confirmed"])
        self.assertFalse(pin["image_license_confirmed"])
        self.assertFalse(pin["title_confirmed"])
        self.assertEqual(pin["status"], "draft")
        self.assertEqual(garimpo.run([
            "--store", str(imported_store), "import-xlsx", str(generated)
        ]), 0)
        self.assertEqual(len(garimpo.load_store(imported_store)["pins"]), 1)

    def test_excel_import_never_confirms_even_when_sheet_claims_yes(self):
        pin = dict(self.one, affiliate_url="https://meli.la/LinkReal",
                   affiliate_url_confirmed=True,
                   image_license_confirmed=True)
        path = self.root / "entrada.xlsx"
        excel_catalog.sync_catalog(self.store, self.data(pin), dest=path)
        imported_store = self.root / "another" / "pins.json"
        self.assertEqual(excel_catalog.import_excel_drafts(path, imported_store), 1)
        entry = garimpo.load_store(imported_store)["pins"][pin["id"]]
        self.assertFalse(entry["affiliate_url_confirmed"])
        self.assertTrue(entry["affiliate_link_pending"])
        self.assertFalse(entry["image_license_confirmed"])

    def test_manual_edit_is_preserved_until_explicit_force(self):
        garimpo.save_store(self.store, self.data(self.one))
        dest = self.store.parent / "produtos.xlsx"
        with ZipFile(dest, "a") as archive:
            archive.writestr("custom_user_notes.txt", "edição manual")
        original_bytes = dest.read_bytes()
        updated = dict(self.one, affiliate_url="https://meli.la/NewRealLink")
        garimpo.save_store(self.store, self.data(updated))
        self.assertEqual(dest.read_bytes(), original_bytes)
        self.assertEqual(garimpo.load_store(self.store)["pins"]["produto-1"]["affiliate_url"],
                         "https://meli.la/NewRealLink")
        with self.assertRaisesRegex(garimpo.GarimpoError, "editado externamente"):
            garimpo.run(["--store", str(self.store), "excel-sync"])
        self.assertEqual(garimpo.run([
            "--store", str(self.store), "excel-sync", "--force"
        ]), 0)
        self.assertNotEqual(dest.read_bytes(), original_bytes)
        entries = excel_catalog.read_products(dest)
        self.assertEqual(entries[0]["Link afiliado"], "https://meli.la/NewRealLink")

    def test_locked_excel_keeps_json_and_can_resync(self):
        with patch.object(excel_catalog, "sync_catalog",
                          side_effect=excel_catalog.ExcelCatalogError("arquivo bloqueado")):
            garimpo.save_store(self.store, self.data(self.one))
        self.assertEqual(len(garimpo.load_store(self.store)["pins"]), 1)
        self.assertFalse((self.store.parent / "produtos.xlsx").exists())
        self.assertEqual(garimpo.run(["--store", str(self.store), "excel-sync"]), 0)
        self.assertTrue((self.store.parent / "produtos.xlsx").is_file())


if __name__ == "__main__":
    unittest.main()
