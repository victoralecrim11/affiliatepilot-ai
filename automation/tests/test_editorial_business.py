"""Offline integration for Pinterest editorial photos and manual Business handoff."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

try:
    from automation import garimpo, creative_ai, pinterest_business
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import garimpo
    import creative_ai
    import pinterest_business


class EditorialBusinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / "original.webp"
        Image.new("RGB", (400, 600), (190, 160, 120)).save(self.photo, "WEBP")
        self.pin = {
            "id": "refletor-001", "title": "Refletor LED",
            "description": "Produto verificado.\n\nEste conteúdo contém link de afiliado.",
            "affiliate_url": "https://meli.la/INDIVIDUAL_01",
            "affiliate_url_confirmed": True, "image_license_confirmed": True,
            "category": "casa", "image_path": str(self.photo), "status": "draft",
            "stylized_image_path": "",
        }

    def prep(self, style="editorial", source="best", pin=None):
        pin = pin or self.pin
        path = garimpo.prepare_image(pin, self.root / "out", style=style, source=source)
        pin["preview_path"] = str(path)
        pin["creative_style"] = style
        pin["status"] = "prepared"
        return path

    def test_editorial_default_has_no_added_ad_overlays(self):
        path = self.prep()
        with Image.open(path) as im:
            self.assertEqual(im.size, (1000, 1500))
            color_top = im.getpixel((40, 40))
            center = im.getpixel((500, 750))
            self.assertLess(sum(abs(a-b) for a,b in zip(color_top, center)), 20)
            self.assertGreater(color_top[0], 100)  # not branded dark-green header

    def test_branded_legacy_is_explicit_opt_in(self):
        path = self.prep("branded")
        with Image.open(path) as im:
            self.assertEqual(im.size, (1000, 1500))
            r,g,b = im.getpixel((25, 25))
            self.assertTrue(g > r and g > b)  # dark green header retained

    def test_editorial_source_original_bypasses_old_stylized_banner(self):
        stale = self.root / "old-stylized.png"
        Image.new("RGB", (400, 600), (0, 50, 0)).save(stale)
        self.pin["stylized_image_path"] = str(stale)
        path = self.prep(source="original")
        with Image.open(path) as im:
            pix = im.getpixel((500, 750))
            self.assertGreater(pix[0], pix[1])
        path = self.prep(source="best")
        with Image.open(path) as im:
            pix = im.getpixel((500, 750))
            self.assertGreater(pix[1], pix[0])

    def test_local_enhancement_preserves_resolution_and_no_banner(self):
        target = self.root / "enhanced.png"
        creative_ai._local_enhance(self.pin, target)
        with Image.open(target) as im:
            self.assertEqual(im.size, (400, 600))
            self.assertNotEqual(im.getpixel((0, 0)), (36, 78, 70))

    def test_two_products_keep_distinct_commission_urls(self):
        self.prep()
        dir_a = pinterest_business.export_business(self.pin, self.root / "business")
        second = dict(self.pin, id="notebook-002", title="Notebook", category="tecnologia",
                      affiliate_url="https://meli.la/INDIVIDUAL_02")
        second_img = self.root / "second.jpg"
        Image.new("RGB", (1000,1500), (80,40,100)).save(second_img)
        second["preview_path"] = str(second_img)
        dir_b = pinterest_business.export_business(second, self.root / "business")
        data_a = json.loads((dir_a / "fields.json").read_text(encoding="utf8"))
        data_b = json.loads((dir_b / "fields.json").read_text(encoding="utf8"))
        self.assertEqual(data_a["destination_url"], "https://meli.la/INDIVIDUAL_01")
        self.assertEqual(data_b["destination_url"], "https://meli.la/INDIVIDUAL_02")
        self.assertTrue((dir_a / "pin.jpg").is_file())
        self.assertTrue((dir_b / "checklist.md").is_file())
        self.assertTrue(data_a["publish_manually_only"])

    def test_no_export_without_affiliate_confirmation(self):
        self.prep()
        self.pin["affiliate_url_confirmed"] = False
        with self.assertRaisesRegex(pinterest_business.BusinessExportError, "link"):
            pinterest_business.export_business(self.pin, self.root / "business")
        self.assertFalse((self.root / "business" / self.pin["id"]).exists())

    def test_no_export_with_missing_license_or_pending_confirmation(self):
        self.prep()
        self.pin["image_license_confirmed"] = False
        with self.assertRaises(pinterest_business.BusinessExportError):
            pinterest_business.export_business(self.pin, self.root / "business")
        self.pin["image_license_confirmed"] = True
        self.pin["affiliate_link_pending"] = True
        with self.assertRaises(pinterest_business.BusinessExportError):
            pinterest_business.export_business(self.pin, self.root / "business")

    def test_new_url_pin_requires_title_category_confirmed(self):
        self.prep()
        self.pin.update(created_by_url=True, title_confirmed=False, category_confirmed=False)
        with self.assertRaises(pinterest_business.BusinessExportError):
            pinterest_business.export_business(self.pin, self.root / "business")

    def test_ai_indication_is_manual_not_platform_api_field(self):
        self.prep()
        self.pin["creative_provider"] = "hf-spaces"
        self.pin["stylized_image_path"] = str(self.root / "enhanced-ai.png")
        self.pin["prepared_source"] = "best"
        pkg = pinterest_business.export_business(self.pin, self.root / "business")
        fields = json.loads((pkg / "fields.json").read_text(encoding="utf8"))
        self.assertTrue(fields["mark_as_ai_modified_in_business"])
        self.assertIn("Marcar como modificado por IA", (pkg / "checklist.md").read_text(encoding="utf8"))
        self.pin["prepared_source"] = "original"
        pkg = pinterest_business.export_business(self.pin, self.root / "business")
        fields = json.loads((pkg / "fields.json").read_text(encoding="utf8"))
        self.assertFalse(fields["mark_as_ai_modified_in_business"])
        self.pin["prepared_source"] = "best"
        self.pin["creative_provider"] = "local"
        pkg = pinterest_business.export_business(self.pin, self.root / "business")
        fields = json.loads((pkg / "fields.json").read_text(encoding="utf8"))
        self.assertFalse(fields["mark_as_ai_modified_in_business"])

    def test_export_without_id_finds_all_eligible_and_keeps_individual_links(self):
        from unittest.mock import patch
        self.prep()
        older = dict(self.pin, prepared_at="2026-10-21T15:00:00+00:00")
        other_photo = self.root / "second.jpg"
        Image.new("RGB", (500, 700), (20, 70, 90)).save(other_photo)
        newer = dict(self.pin, id="notebook-002", title="Notebook",
                     category="tecnologia", preview_path=str(other_photo),
                     affiliate_url="https://meli.la/INDIVIDUAL_02",
                     prepared_at="2026-10-22T15:00:00+00:00")
        blocked = dict(self.pin, id="pending-003", status="draft",
                       affiliate_url="https://meli.la/OTHER")
        store = self.root / "pins.json"
        garimpo.save_store(store, {
            "version": 1, "pins": {p["id"]: p for p in [older, newer, blocked]}
        })
        export_dir = self.root / "bulk-business"
        with patch.object(garimpo, "pinterest_call") as api:
            code = garimpo.run(["--store", str(store), "export-business",
                                "--out", str(export_dir)])
        self.assertEqual(code, 0)
        api.assert_not_called()
        first = json.loads((export_dir / older["id"] / "fields.json").read_text("utf8"))
        second = json.loads((export_dir / newer["id"] / "fields.json").read_text("utf8"))
        self.assertEqual(first["destination_url"], "https://meli.la/INDIVIDUAL_01")
        self.assertEqual(second["destination_url"], "https://meli.la/INDIVIDUAL_02")
        self.assertEqual(second["product_local_id"], "notebook-002")
        self.assertFalse((export_dir / "pending-003").exists())
        self.assertEqual(garimpo.load_store(store)["pins"]["pending-003"]["status"], "draft")

    def test_export_latest_without_id_selects_only_latest_prepared(self):
        self.prep()
        older = dict(self.pin, prepared_at="2026-10-21T15:00:00+00:00")
        other_photo = self.root / "second.jpg"
        Image.new("RGB", (400, 600), (5, 40, 70)).save(other_photo)
        newer = dict(self.pin, id="notebook-002", title="Notebook",
                     affiliate_url="https://meli.la/INDIVIDUAL_02",
                     preview_path=str(other_photo),
                     prepared_at="2026-10-22T15:00:00+00:00")
        store = self.root / "pins.json"
        garimpo.save_store(store, {"version": 1, "pins": {
            older["id"]: older, newer["id"]: newer
        }})
        target = self.root / "one"
        self.assertEqual(garimpo.run(["--store", str(store), "export-business",
                                      "--latest", "--out", str(target)]), 0)
        self.assertFalse((target / older["id"]).exists())
        self.assertTrue((target / newer["id"] / "fields.json").is_file())

    def test_export_without_prepared_candidates_does_not_make_packages(self):
        state = {"version": 1, "pins": {
            self.pin["id"]: dict(self.pin, status="draft", affiliate_url_confirmed=True)
        }}
        store = self.root / "pins.json"
        garimpo.save_store(store, state)
        target = self.root / "business"
        with self.assertRaisesRegex(garimpo.GarimpoError, "Nenhum Pin|Primeiro prepare"):
            garimpo.run(["--store", str(store), "export-business", "--out", str(target)])
        self.assertFalse(target.exists())

    def test_export_explicit_id_still_supported_but_not_with_latest(self):
        self.prep()
        store = self.root / "pins.json"
        garimpo.save_store(store, {"version": 1, "pins": {self.pin["id"]: self.pin}})
        self.assertEqual(garimpo.run(["--store", str(store), "export-business",
                                     self.pin["id"], "--out", str(self.root/"explicit")]), 0)
        with self.assertRaisesRegex(garimpo.GarimpoError, "OU --latest"):
            garimpo.run(["--store", str(store), "export-business",
                         self.pin["id"], "--latest"])
        self.assertFalse((self.root / "out" / "business").exists())

    def test_invalid_style_and_cli_interface(self):
        with self.assertRaises(garimpo.GarimpoError):
            self.prep("billboard")
        parser = garimpo.build_parser()
        a = parser.parse_args(["prepare", "refletor-001"])
        self.assertEqual((a.style, a.source), ("editorial", "best"))
        a = parser.parse_args(["auto", "https://meli.la/some_link"])
        self.assertEqual((a.style, a.source), ("editorial", "best"))
        self.assertEqual(parser.parse_args(["export-business", "refletor-001"]).command,
                         "export-business")


if __name__ == "__main__":
    unittest.main()
