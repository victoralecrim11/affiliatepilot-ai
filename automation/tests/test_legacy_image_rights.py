"""Compatibilidade com fila antiga: autorização explícita sem falsificar direitos."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

try:
    from automation import garimpo, creative_ai
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import garimpo
    import creative_ai


class LegacyRightsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "pins.json"
        self.image = self.root / "photo.webp"
        Image.new("RGB", (300, 350), "navy").save(self.image, "WEBP")
        self.pin = {
            "id": "legacy-item", "status": "prepared",
            "image_path": str(self.image), "title": "Produto real",
            "category": "casa", "affiliate_url": "https://meli.la/example",
            "preview_path": str(self.root / "old.jpg"),
            "stylized_image_path": str(self.root / "old-styled.png"),
            "approval_sha256": "", "board_id": "",
        }
        garimpo.save_store(self.store, {"version": 1, "pins": {self.pin["id"]: self.pin}})

    def _saved(self):
        return garimpo.load_store(self.store)["pins"]["legacy-item"]

    def test_legacy_pin_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(creative_ai.CreativeError, "direitos"):
            creative_ai.stylize(self.pin, self.root / "generated", provider="local")
        with self.assertRaises(SystemExit):
            garimpo.run(["--store", str(self.store), "confirm-image-rights", "legacy-item"])
        self.assertNotIn("image_license_confirmed", self._saved())

    def test_explicit_authorization_migrates_old_pin_and_invalidates_old_preview(self):
        garimpo.run(["--store", str(self.store), "confirm-image-rights", "legacy-item", "--confirm"])
        pin = self._saved()
        self.assertIs(pin["image_license_confirmed"], True)
        self.assertEqual(pin["status"], "draft")
        self.assertEqual(pin["preview_path"], "")
        self.assertEqual(pin["stylized_image_path"], "")
        self.assertEqual(pin["approval_sha256"], "")
        self.assertEqual(pin["board_id"], "")
        output = creative_ai.stylize(pin, self.root / "generated", provider="local")
        self.assertTrue(output.is_file())

    def test_missing_image_refuses_confirmation_and_preserves_queue(self):
        self.pin["image_path"] = str(self.root / "missing.webp")
        garimpo.save_store(self.store, {"version": 1, "pins": {"legacy-item": self.pin}})
        with self.assertRaisesRegex(garimpo.GarimpoError, "Imagem autorizada"):
            garimpo.run(["--store", str(self.store), "confirm-image-rights", "legacy-item", "--confirm"])
        self.assertNotIn("image_license_confirmed", self._saved())

    def test_approved_or_published_pin_cannot_be_changed(self):
        for status in ("approved", "published", "publishing"):
            with self.subTest(status=status):
                self.pin["status"] = status
                garimpo.save_store(self.store, {"version": 1, "pins": {"legacy-item": self.pin}})
                with self.assertRaisesRegex(garimpo.GarimpoError, "não aprovados"):
                    garimpo.run(["--store", str(self.store), "confirm-image-rights", "legacy-item", "--confirm"])
                self.assertNotIn("image_license_confirmed", self._saved())

    def test_explicit_replace_with_authorized_photo(self):
        newer = self.root / "authorized.png"
        Image.new("RGB", (300, 400), "green").save(newer)
        garimpo.run(["--store", str(self.store), "confirm-image-rights", "legacy-item",
                     "--image-file", str(newer), "--confirm"])
        self.assertEqual(self._saved()["image_path"], str(newer.resolve()))


if __name__ == "__main__":
    unittest.main()
