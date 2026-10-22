"""Offline contract tests: no paid calls, no live user images or tokens."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image

try:
    from automation import free_image_providers as cloud, creative_ai, garimpo
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import free_image_providers as cloud
    import creative_ai
    import garimpo


def sample_png():
    stream = BytesIO()
    Image.new("RGB", (512, 768), "#f4caba").save(stream, "PNG")
    return stream.getvalue()


class FreeCloudTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        image = self.root / "item.webp"
        Image.new("RGB", (450, 700), "navy").save(image, "WEBP")
        self.pin = {"id": "sample", "title": "Kit Refletor LED",
                    "category": "casa", "image_path": str(image),
                    "image_license_confirmed": True}
        self.out = self.root / "out"
        self.flags = dict(allow_public_processing=True, confirm_model_license=True)

    def test_all_external_providers_require_both_consents(self):
        for provider in ("aihorde", "hf-spaces"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(creative_ai.CreativeError, "allow-public-processing"):
                    creative_ai.stylize(self.pin, self.out, provider=provider)
                with self.assertRaisesRegex(creative_ai.CreativeError, "confirm-model-license"):
                    creative_ai.stylize(
                        self.pin, self.out, provider=provider, allow_public_processing=True
                    )
        self.assertFalse(self.out.exists())

    def test_image_rights_are_mandatory(self):
        p = dict(self.pin, image_license_confirmed=False)
        with self.assertRaisesRegex(creative_ai.CreativeError, "direitos"):
            creative_ai.stylize(p, self.out, provider="aihorde", **self.flags)
        self.assertFalse(self.out.exists())

    def test_source_image_is_real_webp_with_contain(self):
        encoded = cloud._source_webp(self.pin)
        with Image.open(BytesIO(base64.b64decode(encoded))) as im:
            self.assertEqual(im.size, (512, 768))
            self.assertEqual(im.format, "WEBP")

    def test_horde_payload_uses_existing_image_and_no_money(self):
        png = base64.b64encode(sample_png()).decode()
        calls = []
        def fake_request(path, *, method="GET", payload=None, apikey=""):
            calls.append((path, method, payload, apikey))
            if path == "/generate/async":
                return {"id": "12345678-aaaa-bbbb-cccc-0123456789ab"}
            if path.startswith("/generate/check"):
                return {"done": True, "faulted": False}
            if path.startswith("/generate/status"):
                return {"generations": [{"img": png, "censored": False}]}
            raise AssertionError(path)
        with patch.object(cloud, "_horde_json", side_effect=fake_request), \
             patch.dict("os.environ", {"AIHORDE_API_KEY": ""}):
            cloud.horde_edit(self.pin, self.root/"output.png",
                             prompt="Edit faithfully", model="Licensed Test Model")
        req = calls[0][2]
        self.assertEqual(calls[0][0], "/generate/async")
        self.assertEqual(req["source_processing"], "img2img")
        self.assertEqual(req["models"], ["Licensed Test Model"])
        self.assertEqual(req["params"]["denoising_strength"], 0.27)
        self.assertEqual(req["params"]["n"], 1)
        self.assertTrue(req["shared"])  # Anonymous may be publicly shared.
        self.assertNotIn("payment", json.dumps(req))
        self.assertTrue((self.root/"output.png").is_file())

    def test_horde_rejects_arbitrary_output_hosts_and_bad_images(self):
        with self.assertRaises(cloud.FreeProviderError):
            cloud._horde_output_bytes("http://127.0.0.1/secret.png")
        with self.assertRaises(cloud.FreeProviderError):
            cloud._horde_output_bytes("https://evil.example/private.png")
        with self.assertRaisesRegex(cloud.FreeProviderError, "imagem"):
            cloud._normalized_png(b"not an image", self.root/"bad.png")
        self.assertFalse((self.root/"bad.png").exists())

    def test_horde_error_keeps_existing_image(self):
        self.out.mkdir()
        dest = self.out / "sample-styled.png"
        dest.write_bytes(sample_png())
        before = dest.read_bytes()
        with patch.object(cloud, "_horde_json", return_value={"message": "rejected"}):
            with self.assertRaises(creative_ai.CreativeError):
                creative_ai.stylize(
                    self.pin, self.out, provider="aihorde", horde_model="LicensedModel",
                    **self.flags
                )
        self.assertEqual(dest.read_bytes(), before)

    def test_explicit_fallback_to_local_keeps_provider_truth(self):
        with patch.object(cloud, "horde_edit", side_effect=cloud.FreeProviderError("offline")):
            output = creative_ai.stylize(
                self.pin, self.out, provider="aihorde", horde_model="LicensedModel",
                fallback_local=True, **self.flags
            )
        self.assertTrue(output.is_file())
        self.assertTrue(self.pin.pop("_used_local_fallback"))

    def test_hf_space_requires_configuration(self):
        with self.assertRaises(cloud.FreeProviderError):
            cloud.hf_spaces_edit(
                self.pin, self.root/"test.png", prompt="hi",
                space="https://evil.com", api_name="/predict"
            )
        with self.assertRaises(cloud.FreeProviderError):
            cloud.hf_spaces_edit(
                self.pin, self.root/"test.png", prompt="hi",
                space="owner/space", api_name="/not-a/real/endpoint"
            )

    def test_hf_space_public_gradio_uses_no_token(self):
        captured = {}
        class FakeClient:
            def __init__(self, space, *, token, verbose):
                captured.update(space=space, token=token, verbose=verbose)
            def predict(self, *, api_name, **kwargs):
                captured.update(api_name=api_name, kwargs=kwargs)
                image = self_input.root / "generated.png"
                image.write_bytes(sample_png())
                return str(image)
        self_input = self
        fake = types.SimpleNamespace(Client=FakeClient, handle_file=lambda value: value)
        with patch.dict(sys.modules, {"gradio_client": fake}):
            cloud.hf_spaces_edit(
                self.pin, self.root/"hf-out.png", prompt="Scene",
                space="person/public-space", api_name="/edit",
                image_arg="photo", prompt_arg="instruction"
            )
        self.assertIs(captured["token"], False)
        self.assertEqual(captured["api_name"], "/edit")
        self.assertEqual(captured["kwargs"]["instruction"], "Scene")
        self.assertEqual(captured["kwargs"]["photo"], str(Path(self.pin["image_path"]).resolve()))
        self.assertTrue((self.root/"hf-out.png").exists())

    def test_cli_auto_and_stylize_accept_free_provider_flags(self):
        parser = garimpo.build_parser()
        for command in ("stylize", "auto"):
            params = ["PRODUCT"] if command == "stylize" else ["https://meli.la/abc123"]
            result = parser.parse_args([
                command, *params, "--provider", "aihorde",
                "--horde-model", "LicensedModel",
                "--allow-public-processing", "--confirm-model-license",
                "--fallback-local"
            ])
            self.assertTrue(result.allow_public_processing)
            self.assertEqual(garimpo.cloud_options_from_args(result)["horde_model"], "LicensedModel")
            self.assertTrue(result.fallback_local)

    def test_local_fallback_status_is_local_not_fake_ai(self):
        with patch.object(cloud, "horde_edit", side_effect=cloud.FreeProviderError("offline")):
            image = garimpo.stylize_draft(
                dict(self.pin, status="draft"), self.root, "aihorde",
                allow_paid_ai=False,
                cloud_options=dict(self.flags, horde_model="LicensedModel",
                                   fallback_local=True),
            )
        self.assertTrue(image.is_file())


if __name__ == "__main__":
    unittest.main()
