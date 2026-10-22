"""Diagnóstico seguro do HF: classificações e leitura do schema sem GPU."""
from __future__ import annotations
import sys
import types
from pathlib import Path
import unittest
from unittest.mock import patch
try:
    from automation import hf_diagnostics, garimpo
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import hf_diagnostics, garimpo


class HFDiagnosticsTests(unittest.TestCase):
    def test_error_classification_quota(self):
        x = ValueError("ZeroGPU quota exceeded: 0 seconds remaining")
        self.assertIn("limite", hf_diagnostics.classify_hf_error(x))

    def test_error_classification_auth(self):
        self.assertIn("autenticação", hf_diagnostics.classify_hf_error(
            PermissionError("401 Sign in required")))

    def test_error_classification_schema(self):
        self.assertIn("assinatura", hf_diagnostics.classify_hf_error(
            TypeError("Unexpected keyword argument: image")))

    def test_hidden_error_does_not_claim_quota_or_show_sensitive_content(self):
        x = ValueError("opaque-error token=secret-value-should-not-appear")
        result = hf_diagnostics.classify_hf_error(x)
        self.assertIn("não é possível concluir", result)
        self.assertNotIn("secret-value", result)

    def test_readonly_inspection_no_generation(self):
        class MockInfo:
            runtime = types.SimpleNamespace(stage="RUNNING", hardware="zero-a10g")
        class MockApi:
            def __init__(self, token): self.token = token
            def space_info(self, name): return MockInfo()
        class MockClient:
            def __init__(self, name, *, token, verbose):
                self.name, self.token, self.verbose = name, token, verbose
            def view_api(self, *, return_format):
                return {"named_endpoints": {"/infer": {"parameters": [
                    {"parameter_name": "image", "parameter_has_default": False},
                    {"parameter_name": "prompt", "parameter_has_default": False},
                    {"parameter_name": "seed", "parameter_has_default": True},
                ]}}}
            def predict(self, *args, **kwargs):
                raise AssertionError("Não deveria fazer inferência")
        with patch.dict(sys.modules, {
            "gradio_client": types.SimpleNamespace(Client=MockClient),
            "huggingface_hub": types.SimpleNamespace(HfApi=MockApi),
        }):
            diagnosis = hf_diagnostics.inspect_space("Qwen/Qwen-Image-Edit", "/infer")
        self.assertTrue(diagnosis["compatible"])
        self.assertEqual(diagnosis["required"], ["image", "prompt"])

    def test_extra_required_parameter_is_incompatible(self):
        class MockInfo:
            runtime = types.SimpleNamespace(stage="RUNNING", hardware="zero-a10g")
        class MockApi:
            def __init__(self, token): pass
            def space_info(self, name): return MockInfo()
        class MockClient:
            def __init__(self, *a, **kw): pass
            def view_api(self, *, return_format):
                return {"named_endpoints": {"/infer": {"parameters": [
                    {"parameter_name": "image", "parameter_has_default": False},
                    {"parameter_name": "prompt", "parameter_has_default": False},
                    {"parameter_name": "extra", "parameter_has_default": False}
                ]}}}
        with patch.dict(sys.modules, {
            "gradio_client": types.SimpleNamespace(Client=MockClient),
            "huggingface_hub": types.SimpleNamespace(HfApi=MockApi),
        }):
            diagnosis = hf_diagnostics.inspect_space("Qwen/Qwen-Image-Edit", "/infer")
        self.assertFalse(diagnosis["compatible"])

    def test_cli_has_read_only_diagnostic(self):
        args = garimpo.build_parser().parse_args([
            "hf-check", "--space", "Qwen/Qwen-Image-Edit", "--api-name", "/infer"
        ])
        self.assertEqual(args.command, "hf-check")


if __name__ == "__main__":
    unittest.main()
