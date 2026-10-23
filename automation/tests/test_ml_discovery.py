"""Offline official API contracts, safe selections and CLI integration."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from PIL import Image

try:
    from automation import ml_discovery as ml, pin_selector, garimpo, ml_ingest
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import ml_discovery as ml
    import pin_selector
    import garimpo
    import ml_ingest


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = self.path / "pins.json"
        self.image = self.path / "product.webp"
        Image.new("RGB", (320, 450), "navy").save(self.image, "WEBP")
        self.url = "https://produto.mercadolivre.com.br/MLB-6797156948-produto-_JM"
        self.example = {"id": "MLB6797156948", "title": "Refletor LED",
                        "permalink": self.url, "price": 96.0,
                        "currency_id": "BRL", "category_id": "MLB888555",
                        "status": "active", "catalog_product_id": "MLB999999"}
        self.product = {"id": "RS1033-VHDC", "title": "Refletor LED",
                        "category": "casa", "image_path": str(self.image),
                        "image_license_confirmed": True, "status": "prepared",
                        "affiliate_url": "https://meli.la/UNIQUE_ABC",
                        "affiliate_url_confirmed": True,
                        "description": "Produto em destaque. Contém link de afiliado.",
                        "preview_path": str(self.image), "prepared_at": "2026-10-22T19:00:00+00:00"}

    def test_official_root_categories_cache_and_live(self):
        entries = [{"id": "MLB1000", "name": "Casa"}, {"id": "MLB2222", "name": "Moda"}]
        with patch.object(ml, "_api_get", return_value=entries):
            cats, origin = ml.root_categories()
        self.assertEqual(origin, "api")
        self.assertEqual(cats, entries)
        with patch.object(ml, "_api_get", side_effect=ml.DiscoveryError("HTTP 403")):
            cats, origin = ml.root_categories()
        self.assertEqual(origin, "cache_oficial")
        self.assertGreaterEqual(len(cats), 20)

    def test_children_path_from_root(self):
        sample = {"id":"MLB1000","name":"Casa","path_from_root":[{"id":"MLB1000","name":"Casa"}],
                  "children_categories":[{"id":"MLB1111","name":"Iluminação"},
                                         {"id":"??","name":"invalid"}]}
        with patch.object(ml, "_api_get", return_value=sample):
            children, detail = ml.children_of("MLB1000")
        self.assertEqual([c["id"] for c in children], ["MLB1111"])
        self.assertEqual(detail["path"][0]["name"], "Casa")
        with self.assertRaises(ml.DiscoveryError):
            ml.children_of("../../secrets")

    def test_listing_search_never_treats_catalog_product_as_item(self):
        payload = {"results": [self.example,
            dict(self.example, id="MLBU231000008", title="CATALOG PRODUCT"),
            dict(self.example, id="MLB12345678", title="Wrong linked item"),
            dict(self.example, id="MLB12457890",
                 permalink="https://evil.example/MLB-12457890-product"),
            dict(self.example, id="MLB12457891",
                 permalink="https://www.mercadolivre.com.br/p/MLB12457891"),
            dict(self.example, id="MLB12345678", permalink="https://produto.mercadolivre.com.br/MLB-12345678-p-_JM",
                 status="paused")]}
        with patch.object(ml, "_api_get", return_value=payload) as call:
            found = ml.search_listings("refletor led", category_id="MLB1000", limit=10)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["id"], "MLB6797156948")
        self.assertNotEqual(found[0]["id"], self.example["catalog_product_id"])
        self.assertEqual(call.call_args.args[0], "/sites/MLB/search")
        self.assertEqual(call.call_args.args[1]["category"], "MLB1000")
        self.assertNotIn("affiliate_url", found[0])

    def test_403_returns_actionable_error_not_fake_results(self):
        exc = HTTPError(ml.API+"/sites/MLB/search", 403, "Forbidden", None, None)
        with patch.object(ml, "urlopen", side_effect=exc):
            with self.assertRaisesRegex(ml.DiscoveryError, "HTTP 403"):
                ml.search_listings("refletor led")
        with self.assertRaises(ml.DiscoveryError):
            ml.search_listings("r")
        with self.assertRaises(ml.DiscoveryError):
            ml.search_listings("refletor", limit=100)

    def test_browse_category_root_by_number(self):
        cats = [{"id": "MLB1000", "name": "Casa"}]
        with patch.object(ml, "root_categories", return_value=(cats, "api")), \
             patch.object(ml, "children_of", return_value=([{
                 "id": "MLB1100", "name": "Iluminação"}], {})):
            out = []
            choices = iter(["1", "0"])
            result = ml.browse_categories(token="", input_fn=lambda prompt: next(choices),
                                          output=out.append)
        self.assertEqual(result["id"], "MLB1000")
        self.assertEqual(result["path"], cats)

    def test_select_existing_product_by_category_and_name(self):
        second = dict(self.product, id="note-002", title="Notebook Gamer",
                      category="tecnologia", item_id="MLB1234567891")
        store = {p["id"]: p for p in (self.product, second)}
        out = []
        chosen = pin_selector.resolve_pin(
            store, command="prepare", category="tecnologia", interactive=False,
            output=out.append)
        self.assertEqual(chosen["id"], "note-002")
        self.assertEqual(len(out), 3)
        with self.assertRaises(pin_selector.SelectionError):
            pin_selector.resolve_pin(store, command="prepare", interactive=False,
                                     output=lambda x: None)
        selected = pin_selector.resolve_pin(store, command="prepare", interactive=True,
                                            input_fn=lambda prompt:"2", output=lambda x:None)
        self.assertEqual(selected["id"], "RS1033-VHDC")

    def test_cli_prepare_without_id_when_only_one(self):
        garimpo.save_store(self.store, {"version":1, "pins": {self.product["id"]: self.product}})
        result = garimpo.run(["--store", str(self.store), "prepare",
                              "--out", str(self.path/"out")])
        self.assertEqual(result, 0)
        saved = garimpo.load_store(self.store)["pins"][self.product["id"]]
        self.assertEqual(saved["status"], "prepared")
        self.assertEqual(saved["creative_style"], "editorial")

    def test_cli_discover_from_official_result_requires_user_pick(self):
        payload = {
            "source_url": self.url, "resolved_url": self.url, "item_id": "MLB6797156948",
            "title": "Refletor LED", "summary": "Leia detalhes do anúncio.",
            "image_url": "", "category": "casa", "ml_category_id": "MLB888555",
            "metadata_verified": False, "metadata_source": "public_page_unverified",
            "warnings": ["Sem detalhes de item confirmados"],
        }
        with patch.object(ml, "read_token", return_value=""), \
             patch.object(ml, "search_listings", return_value=[dict(self.example,
                 source="mercadolivre_official_search", category_id="MLB888555")]), \
             patch.object(ml_ingest, "get_product_metadata", return_value=payload):
            result = garimpo.run(["--store", str(self.store), "ml-discover",
                                  "--query", "refletor led", "--any-category", "--pick", "1"])
        self.assertEqual(result, 0)
        store = garimpo.load_store(self.store)
        pin = next(iter(store["pins"].values()))
        self.assertEqual(pin["item_id"], "MLB6797156948")
        self.assertEqual(pin["discovered_via"], "mercadolivre_official_search")
        self.assertEqual(pin["affiliate_url"], "")
        self.assertFalse(pin["affiliate_url_confirmed"])
        self.assertFalse(pin["image_license_confirmed"])
        self.assertEqual(pin["status"], "draft")
        self.assertTrue(pin["created_by_url"])

    def test_cli_discover_list_only_does_not_write(self):
        with patch.object(ml, "read_token", return_value=""), \
             patch.object(ml, "search_listings", return_value=[dict(self.example, source="api")]):
            self.assertEqual(garimpo.run(["--store", str(self.store), "ml-discover",
                                          "--query", "refletor led",
                                          "--any-category", "--list-only"]), 0)
        self.assertFalse(self.store.exists())

    def test_commands_accept_optional_id_and_filters(self):
        parser=garimpo.build_parser()
        for name in ("prepare","show","knowledge","stylize","review",
                     "affiliate-link","confirm-link","confirm-image-rights",
                     "approve","publish","verify-ml","reset"):
            with self.subTest(command=name):
                argv=[name, "--choose-category","casa","--choose-search","refletor"]
                if name=="approve":
                    argv.extend(["--board-id","123456789"])
                if name in ("publish","confirm-link","reset","confirm-image-rights"):
                    if name=="reset":
                        argv.append("--confirmed-not-published")
                    else:
                        argv.append("--confirm")
                parsed=parser.parse_args(argv)
                self.assertIsNone(parsed.id)
                self.assertEqual(parsed.choose_category, "casa")

    def test_export_business_choice_keeps_only_one_link(self):
        self.product["preview_path"] = str(self.path/"final.jpg")
        Image.new("RGB",(1000,1500),"navy").save(self.product["preview_path"])
        next_item=dict(self.product, id="note-002", title="Notebook Gamer", category="tecnologia",
                       affiliate_url="https://meli.la/UNIQUE_DEF")
        garimpo.save_store(self.store, {"version":1,"pins":{
            self.product["id"]:self.product, next_item["id"]:next_item}})
        out=self.path/"business"
        args=["--store",str(self.store),"export-business","--choose",
              "--choose-category","tecnologia","--out",str(out)]
        self.assertEqual(garimpo.run(args),0)
        self.assertTrue((out/"note-002"/"fields.json").exists())
        self.assertFalse((out/"RS1033-VHDC").exists())
        fields=json.loads((out/"note-002"/"fields.json").read_text(encoding="utf8"))
        self.assertEqual(fields["destination_url"],"https://meli.la/UNIQUE_DEF")


if __name__=="__main__":
    unittest.main()
