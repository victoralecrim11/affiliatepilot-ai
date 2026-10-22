"""Testes offline do pipeline URL + Playwright opcional + stylize, sem credenciais."""
from __future__ import annotations
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

try:
    from automation import garimpo, ml_ingest, creative_ai, affiliate_browser, prompt_templates
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import garimpo, ml_ingest, creative_ai, affiliate_browser, prompt_templates


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "pins.json"
        self.out = self.root / "out"
        self.photo = self.root / "refletor.webp"
        Image.new("RGB", (600, 600), "navy").save(self.photo, "WEBP")
        self.url = "https://produto.mercadolivre.com.br/MLB-6797156948-produto-exemplo-_JM"
        self.meta = {
            "source_url": self.url, "resolved_url": self.url,
            "item_id": "MLB6797156948", "title": "Kit Refletor LED verificado",
            "summary": "Confira especificações e condições atuais do produto.",
            "image_url": "https://http2.mlstatic.com/D_Q_NP_test.jpg",
            "category": "casa", "metadata_source": "official_api",
            "metadata_verified": True, "warnings": [],
        }
        self.flags = ["--image-file", str(self.photo), "--confirm-image-rights",
                      "--title", "Kit Refletor LED verificado", "--category", "casa",
                      "--affiliate-url", "https://meli.la/abc321", "--confirm-affiliate-link"]

    def test_item_id_does_not_confuse_catalog_and_sku(self):
        self.assertEqual(ml_ingest.extract_item_id(self.url), "MLB6797156948")
        self.assertEqual(ml_ingest.extract_item_id("https://www.mercadolivre.com.br/p/MLB999000111"), "")
        self.assertEqual(ml_ingest.extract_item_id("https://meli.la/abc321"), "")
        self.assertEqual(ml_ingest.extract_item_id("https://produto.mercadolivre.com.br/item/RS1033-VHDC"), "")

    def test_ssrf_and_invalid_affiliate_url_rejected(self):
        for s in ["http://127.0.0.1/item", "https://meli.la.evil.com/x",
                  "https://localhost/x", "ftp://meli.la/x", "https://u:p@meli.la/x"]:
            with self.subTest(url=s), self.assertRaises(ValueError):
                ml_ingest.validate_url(s)
        self.assertEqual(affiliate_browser.validate_affiliate_result(" <https://meli.la/abc321> "),
                         "https://meli.la/abc321")
        with self.assertRaises(ValueError):
            affiliate_browser.validate_affiliate_result("not_a_url")

    def test_official_api_metadata_first(self):
        item = {"id": "MLB6797156948", "title": "Refletor LED Teste", "status":"active",
                "pictures":[{"secure_url":"https://http2.mlstatic.com/pic.webp"}]}
        with patch.object(ml_ingest, "_download", return_value=(self.url, b"", "text/html")), \
             patch.object(ml_ingest, "_official_item", return_value=item):
            data = ml_ingest.get_product_metadata(self.url, token="fake")
        self.assertTrue(data["metadata_verified"])
        self.assertEqual(data["image_url"], item["pictures"][0]["secure_url"])
        self.assertEqual(data["category"], "casa")

    def test_api_forbidden_falls_back_to_unverified_public_metadata(self):
        html=b'<html><head><meta property="og:title" content="Kit refletor para jardim"><meta property="og:image" content="https://http2.mlstatic.com/p.webp"></head></html>'
        with patch.object(ml_ingest, "_download", return_value=(self.url, html, "text/html")), \
             patch.object(ml_ingest, "_official_item", return_value=None):
            data = ml_ingest.get_product_metadata(self.url)
        self.assertFalse(data["metadata_verified"])
        self.assertEqual(data["metadata_source"], "public_page_unverified")
        self.assertTrue(data["warnings"])

    def test_create_draft_and_no_unverified_approval(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_ACCESS_TOKEN":"FAKE"}), \
             patch.object(ml_ingest, "get_product_metadata", return_value=self.meta):
            pin = garimpo.ingest_product_url(self.url, self.store)
        self.assertEqual(pin["status"], "draft")
        self.assertFalse(pin["affiliate_url_confirmed"])
        self.assertFalse(pin["image_license_confirmed"])
        self.assertEqual(pin["id"], "mlb6797156948")
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.approve_pin(pin, "12345678912345")
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.ingest_product_url(self.url, self.store)

    def test_auto_creates_prepared_preview_without_publication(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_ACCESS_TOKEN":"FAKE"}), \
             patch.object(ml_ingest, "get_product_metadata", return_value=self.meta):
            garimpo.run(["--store",str(self.store),"auto",self.url,*self.flags,
                         "--provider","local","--out",str(self.out)])
        pin=garimpo.load_store(self.store)["pins"]["mlb6797156948"]
        self.assertEqual(pin["status"],"prepared")
        self.assertEqual(pin["creative_provider"],"local")
        self.assertFalse(pin.get("pin_id"))
        with Image.open(pin["preview_path"]) as im:
            self.assertEqual(im.size,(1000,1500))

    def test_review_required_and_link_confirm_workflow(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_ACCESS_TOKEN":"FAKE"}), \
             patch.object(ml_ingest, "get_product_metadata", return_value=self.meta):
            garimpo.ingest_product_url(self.url, self.store,
                title="Kit Refletor LED verificado", category="casa",
                affiliate_url="https://meli.la/abc321",
                image_file=str(self.photo), confirm_image_rights=True)
        state=garimpo.load_store(self.store)
        pin=state["pins"]["mlb6797156948"]
        pin["affiliate_link_pending"]=True
        pin["status"]="prepared"
        garimpo.save_store(self.store,state)
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.approve_pin(pin,"12345678912345")
        garimpo.run(["--store",str(self.store),"confirm-link",pin["id"],"--confirm"])
        state=garimpo.load_store(self.store)
        pin=state["pins"][pin["id"]]
        self.assertTrue(pin["affiliate_url_confirmed"])
        self.assertFalse(pin["affiliate_link_pending"])

    def test_paid_ai_requires_explicit_flag(self):
        pin={"id":"abc","image_path":str(self.photo),"image_license_confirmed":True}
        with self.assertRaisesRegex(creative_ai.CreativeError,"--allow-paid-ai"):
            creative_ai.stylize(pin,self.out,provider="openai")
        self.assertFalse((self.out/"abc-styled.png").exists())

    def test_skill_prompt_has_non_fabrication_rules(self):
        prompt = prompt_templates.make_prompt({"category":"casa","title":"Refletor"})
        self.assertIn("preserve",prompt.lower())
        self.assertIn("não",prompt.lower())
        self.assertIn("cenário residencial",prompt.lower())

    def test_openai_multipart_uses_real_crlf_no_network(self):
        pin={"id":"abc","title":"Refletor","category":"casa","image_path":str(self.photo)}
        fake=io.BytesIO()
        Image.new("RGB",(50,75),"#fafafa").save(fake,format="PNG")
        response=json.dumps({"data":[{"b64_json":base64.b64encode(fake.getvalue()).decode()}]}).encode()
        class Reply:
            def __enter__(self): return io.BytesIO(response)
            def __exit__(self,*_): pass
        self.out.mkdir(parents=True, exist_ok=True)
        with patch.object(creative_ai,"urlopen",return_value=Reply()) as called:
            creative_ai._openai_edit(pin,self.out/"edited.png",api_key="FAKE")
        body=called.call_args.args[0].data
        self.assertIn(b"\r\nContent-Disposition",body)
        self.assertNotIn(b"\\r\\nContent-Disposition",body)
        self.assertTrue((self.out/"edited.png").exists())


if __name__ == "__main__":
    unittest.main()
