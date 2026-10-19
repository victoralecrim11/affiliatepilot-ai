"""Offline tests: never call Pinterest or Mercado Livre APIs."""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "garimpo.py"
spec = importlib.util.spec_from_file_location("garimpo", MODULE)
garimpo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(garimpo)


class GarimpoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "data" / "pins.json"
        self.out = self.root / "out"
        from PIL import Image
        Image.new("RGB", (480, 600), "#d69a72").save(self.root / "foto.jpg")
        self.csv = self.root / "produtos.csv"
        self.row = {
            "id": "test-product-1",
            "title": "Quadro decorativo com moldura natural",
            "category": "casa",
            "summary": "Quadro decorativo indicado para compor ambientes neutros e com detalhes em madeira.",
            "affiliate_url": "https://meli.la/17N84yk",
            "image_path": "foto.jpg",
            "image_license_confirmed": "sim",
        }
        self.write_csv([self.row])

    def write_csv(self, rows):
        with self.csv.open("w", encoding="utf-8", newline="") as fp:
            wr = csv.DictWriter(fp, fieldnames=garimpo.CSV_FIELDS)
            wr.writeheader()
            wr.writerows(rows)

    def staged_pin(self):
        garimpo.import_csv(self.csv, self.store)
        state = garimpo.load_store(self.store)
        pin = state["pins"]["test-product-1"]
        path = garimpo.prepare_image(pin, self.out)
        pin["preview_path"] = str(path)
        pin["status"] = "prepared"
        return state, pin

    def test_accept_approved_https_domains(self):
        for url in ("https://meli.la/abcdef", "https://www.mercadolivre.com.br/abc", "https://produto.mercadolivre.com.br/MLB-1"):
            self.assertEqual(garimpo.ensure_https_affiliate_link(url), url)

    def test_reject_unsafe_and_fake_urls(self):
        for url in ("http://meli.la/foo", "https://other.example/foo", "https://mercadolivre.com.br.evil.tld/x", "https://meli.la/", "https://x:pass@meli.la/a", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(garimpo.GarimpoError):
                garimpo.ensure_https_affiliate_link(url)

    def test_import_and_no_duplicate_overwrite(self):
        self.assertEqual(garimpo.import_csv(self.csv, self.store), 1)
        state = garimpo.load_store(self.store)
        self.assertEqual(state["pins"]["test-product-1"]["status"], "draft")
        self.assertIn("link de afiliado", state["pins"]["test-product-1"]["description"])
        with self.assertRaisesRegex(garimpo.GarimpoError, "IDs já existentes"):
            garimpo.import_csv(self.csv, self.store)

    def test_invalid_license_rejected_atomically(self):
        bad = self.row.copy()
        bad["id"] = "another"
        bad["image_license_confirmed"] = "nao"
        self.write_csv([self.row, bad])
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.import_csv(self.csv, self.store)
        self.assertFalse(self.store.exists())

    def test_invalid_category_and_metadata(self):
        bad = self.row.copy()
        bad["category"] = "eletronicos"
        with self.assertRaisesRegex(garimpo.GarimpoError, "category inválida"):
            garimpo.validate_row(bad, self.root)

    def test_prepared_image_dimensions_and_brand(self):
        from PIL import Image
        state, pin = self.staged_pin()
        with Image.open(pin["preview_path"]) as img:
            self.assertEqual(img.size, (1000, 1500))
            self.assertEqual(img.format, "JPEG")
        self.assertEqual(pin["category"], "casa")

    def test_approve_pin_binds_image_metadata_board(self):
        state, pin = self.staged_pin()
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.approve_pin(pin, "not_a_board")
        garimpo.approve_pin(pin, "123456789012345678")
        self.assertEqual(pin["status"], "approved")
        self.assertEqual(len(pin["approval_sha256"]), 64)
        self.assertEqual(garimpo.fingerprint(pin), pin["approval_sha256"])
        self.assertNotIn("pina", json.dumps(state))

    def test_publish_only_approved_and_content_immutable(self):
        state, pin = self.staged_pin()
        with self.assertRaises(garimpo.GarimpoError):
            garimpo.publish_pin(pin, token="pina_fake")
        garimpo.approve_pin(pin, "123456789012345678")
        pin["description"] += " Fabricado"
        with self.assertRaisesRegex(garimpo.GarimpoError, "Conteúdo mudou"):
            garimpo.publish_pin(pin, token="pina_fake")

    def test_mock_publish_payload_and_no_unapproved_activity(self):
        state, pin = self.staged_pin()
        garimpo.approve_pin(pin, "123456789012345678")
        captured = {}
        def fake_call(path, method, payload, *, token):
            captured.update({"path": path, "method": method, "payload": payload, "token": token})
            return {"id": "765432987654"}
        with patch.object(garimpo, "pinterest_call", side_effect=fake_call):
            result = garimpo.publish_pin(pin, token="FAKE_TOKEN")
        self.assertEqual(result["id"], "765432987654")
        self.assertEqual(captured["path"], "/pins")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["payload"]["link"], "https://meli.la/17N84yk")
        self.assertEqual(captured["payload"]["media_source"]["source_type"], "image_base64")
        self.assertEqual(captured["payload"]["board_id"], "123456789012345678")

    def test_publish_cli_requires_confirm_and_token(self):
        state, pin = self.staged_pin()
        garimpo.approve_pin(pin, "123456789012345678")
        garimpo.save_store(self.store, state)
        with patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": ""}):
            with self.assertRaisesRegex(garimpo.GarimpoError, "Falta PINTEREST_ACCESS_TOKEN"):
                garimpo.run(["--store", str(self.store), "publish", pin["id"], "--confirm"])
        self.assertEqual(garimpo.load_store(self.store)["pins"][pin["id"]]["status"], "approved")

    def test_publish_cli_records_success_and_refuses_replay(self):
        state, pin = self.staged_pin()
        garimpo.approve_pin(pin, "123456789012345678")
        garimpo.save_store(self.store, state)
        with patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": "fake"}), patch.object(garimpo, "pinterest_call", return_value={"id":"987654321"}) as fake:
            garimpo.run(["--store", str(self.store), "publish", pin["id"], "--confirm"])
            with self.assertRaises(garimpo.GarimpoError):
                garimpo.run(["--store", str(self.store), "publish", pin["id"], "--confirm"])
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(garimpo.load_store(self.store)["pins"][pin["id"]]["status"], "published")

    def test_publish_network_failure_sets_needs_check(self):
        state, pin = self.staged_pin()
        garimpo.approve_pin(pin, "123456789012345678")
        garimpo.save_store(self.store, state)
        with patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": "fake"}), patch.object(garimpo, "pinterest_call", side_effect=garimpo.GarimpoError("timeout")):
            with self.assertRaisesRegex(garimpo.GarimpoError, "timeout"):
                garimpo.run(["--store", str(self.store), "publish", pin["id"], "--confirm"])
        self.assertEqual(garimpo.load_store(self.store)["pins"][pin["id"]]["status"], "needs_check")

    def test_manually_reconcile_after_failure(self):
        state, pin = self.staged_pin()
        pin["status"] = "needs_check"
        garimpo.save_store(self.store, state)
        with self.assertRaises(SystemExit):
            garimpo.run(["--store", str(self.store), "reset", pin["id"]])
        garimpo.run(["--store", str(self.store), "reset", pin["id"], "--confirmed-not-published"])
        self.assertEqual(garimpo.load_store(self.store)["pins"][pin["id"]]["status"], "prepared")

if __name__ == "__main__":
    unittest.main()
