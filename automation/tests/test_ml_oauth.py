"""Testes offline do OAuth Mercado Livre: nenhuma chamada externa real."""
from __future__ import annotations
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

PATH = Path(__file__).resolve().parents[1] / "ml_oauth.py"
spec = importlib.util.spec_from_file_location("ml_oauth", PATH)
oauth = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = oauth
spec.loader.exec_module(oauth)

class FakeVault:
    def __init__(self):
        self.contents = {}
    def get_password(self, service, account):
        return self.contents.get((service, account))
    def set_password(self, service, account, value):
        self.contents[(service, account)] = value
    def delete_password(self, service, account):
        self.contents.pop((service, account))

class FakeResponse:
    def __init__(self, data):
        self.raw = json.dumps(data).encode("utf-8")
    def __enter__(self):
        return io.BytesIO(self.raw)
    def __exit__(self, *args):
        return None

class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.vault = FakeVault()
        p = patch.object(oauth, "keyring_client", return_value=self.vault)
        p.start()
        self.addCleanup(p.stop)

    def test_pkce_s256_random_and_43_character_challenge(self):
        first, chall1 = oauth.create_pkce()
        second, chall2 = oauth.create_pkce()
        self.assertNotEqual(first, second)
        self.assertNotEqual(chall1, chall2)
        self.assertGreaterEqual(len(first), 43)
        self.assertEqual(len(chall1), 43)

    def test_authorization_url_redirect_state_challenge(self):
        url = oauth.authorization_url("1234567890123456", "challenge", "secure-state")
        self.assertTrue(url.startswith("https://auth.mercadolivre.com.br/authorization?"))
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["redirect_uri"], [oauth.REDIRECT_URI])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], ["secure-state"])

    def test_callback_rejects_injection_missing_and_mismatched_state(self):
        self.assertEqual(oauth.parse_oauth_callback("/callback?state=correct&code=abc", "correct"), "abc")
        for bad in (
            "/callback?state=evil&code=abc",
            "/callback?code=abc",
            "/callback?state=correct&code=a&code=b",
            "/callback?state=correct&state=correct&code=a",
            "/different?state=correct&code=abc",
            "/callback?state=correct&error=access_denied",
            "/callback?state=correct&code=abc&error=access_denied",
        ):
            with self.subTest(path=bad), self.assertRaises(oauth.OAuthError):
                oauth.parse_oauth_callback(bad, "correct")

    def test_exchange_pkce_and_refresh_response(self):
        result = {"access_token":"ACCESS_NEW","refresh_token":"REFRESH_NEW","expires_in":21600,"scope":"read"}
        with patch.object(oauth, "urlopen", return_value=FakeResponse(result)) as opener:
            info = oauth.exchange_token({
                "grant_type":"authorization_code","client_id":"123456789",
                "client_secret":"secret","code":"CODE",
                "redirect_uri":oauth.REDIRECT_URI,"code_verifier":"VERIFIER"})
        self.assertEqual(info["refresh_token"], "REFRESH_NEW")
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, oauth.TOKEN_URL)
        self.assertEqual(request.get_method(), "POST")
        fields = parse_qs(request.data.decode())
        self.assertEqual(fields["code_verifier"], ["VERIFIER"])
        self.assertEqual(fields["redirect_uri"], [oauth.REDIRECT_URI])
        self.assertGreater(info["expires_at"], time.time())

    def test_incomplete_token_response_is_rejected(self):
        with patch.object(oauth, "urlopen", return_value=FakeResponse({"access_token":"abc","expires_in":21600})):
            with self.assertRaisesRegex(oauth.OAuthError, "refresh_token"):
                oauth.exchange_token({"grant_type":"authorization_code"})
        self.assertFalse(self.vault.contents)

    def test_refresh_rotates_token_once_and_saves_bundle(self):
        old = {"client_id":"123456789","client_secret":"SECRET","access_token":"OLD",
               "refresh_token":"OLD_REFRESH","expires_at":int(time.time())-10}
        oauth.save_credentials(old)
        newest = {"access_token":"NEW","refresh_token":"NEW_REFRESH",
                  "expires_at":int(time.time())+21600}
        seen = []
        def response(body):
            seen.append(body)
            return dict(newest)
        with patch.object(oauth,"exchange_token",side_effect=response):
            self.assertEqual(oauth.get_access_token(), "NEW")
            self.assertEqual(oauth.get_access_token(), "NEW")
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]["refresh_token"], "OLD_REFRESH")
        current = oauth.read_credentials()
        self.assertEqual(current["refresh_token"], "NEW_REFRESH")
        self.assertEqual(current["client_secret"], "SECRET")

    def test_explicit_token_overrides_os_vault(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_ACCESS_TOKEN":"MANUAL"}):
            with patch.object(oauth,"read_credentials",side_effect=AssertionError("vault accessed")):
                self.assertEqual(oauth.get_access_token(),"MANUAL")

    def test_missing_session_message(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_ACCESS_TOKEN":""}):
            with self.assertRaisesRegex(oauth.OAuthError, "login"):
                oauth.get_access_token()

    def test_refresh_failure_does_not_overwrite_old_bundle(self):
        old = {"client_id":"123456789","client_secret":"SECRET","access_token":"OLD",
               "refresh_token":"OLD_REFRESH","expires_at":int(time.time())-10}
        oauth.save_credentials(old)
        with patch.object(oauth,"exchange_token",side_effect=oauth.OAuthError("HTTP 400")):
            with self.assertRaises(oauth.OAuthError):
                oauth.refresh_access_token()
        self.assertEqual(oauth.read_credentials()["refresh_token"],"OLD_REFRESH")


    def test_login_end_to_end_mock_state_pkce_and_keyring(self):
        """Simula login completo sem chamar endpoints externos nem abrir navegador."""
        observed = {}
        def fake_wait(state, timeout, on_ready):
            self.assertGreaterEqual(len(state), 32)
            self.assertIsNotNone(on_ready)
            observed["state"] = state
            return "TEST_CODE"
        def fake_exchange(payload):
            self.assertEqual(payload["grant_type"], "authorization_code")
            self.assertEqual(payload["code"], "TEST_CODE")
            self.assertEqual(payload["redirect_uri"], oauth.REDIRECT_URI)
            self.assertGreaterEqual(len(payload["code_verifier"]), 43)
            observed["verifier"] = payload["code_verifier"]
            return {"access_token":"TEST_ACCESS","refresh_token":"TEST_REFRESH",
                    "expires_at":int(time.time())+21600}
        with patch.dict(os.environ, {"MERCADOLIVRE_CLIENT_ID":"1234567890123456",
                                    "MERCADOLIVRE_CLIENT_SECRET":"TEST_SECRET"}), \
             patch.object(oauth, "wait_for_local_callback", side_effect=fake_wait), \
             patch.object(oauth, "exchange_token", side_effect=fake_exchange), \
             patch.object(oauth.webbrowser, "open") as opened:
            oauth.login()
        # A senha não aparece no navegador e o cofre recebe o bundle completo.
        saved = oauth.read_credentials()
        self.assertEqual(saved["client_id"], "1234567890123456")
        self.assertEqual(saved["access_token"], "TEST_ACCESS")
        self.assertEqual(saved["refresh_token"], "TEST_REFRESH")
        self.assertEqual(saved["client_secret"], "TEST_SECRET")
        url = oauth.authorization_url(saved["client_id"], "test", observed["state"])
        self.assertEqual(parse_qs(urlsplit(url).query)["state"], [observed["state"]])

    def test_static_bridge_points_only_to_local_oauth_receiver(self):
        html = (PATH.parents[1] / "oauth" / "callback" / "index.html").read_text(encoding="utf-8")
        self.assertIn('new URL("http://127.0.0.1:8765/callback")', html)
        self.assertIn("history.replaceState(null", html)
        self.assertIn("validCode !== validError", html)
        self.assertNotIn("MERCADOLIVRE_CLIENT_SECRET", html)
        self.assertNotIn("Bearer ", html)


    def test_login_opens_devcenter_before_requesting_secret_then_oauth(self):
        events = []

        def fake_browser(url, **_kwargs):
            events.append(("browser", url))
            return True

        def fake_prompt(message):
            events.append(("secret_prompt", message))
            return "SECRET_FROM_DEV_CENTER"

        def fake_wait(state, timeout, on_ready):
            events.append(("wait", state))
            on_ready()
            return "CODE_FOR_TEST"

        def fake_exchange(payload):
            events.append(("exchange", payload["client_secret"]))
            self.assertEqual(payload["code"], "CODE_FOR_TEST")
            return {"access_token": "TEST_TOKEN", "refresh_token": "TEST_REFRESH",
                    "expires_at": int(time.time()) + 3600}

        with patch.dict(os.environ, {"MERCADOLIVRE_CLIENT_ID": "1234567890123456",
                                    "MERCADOLIVRE_CLIENT_SECRET": ""}), \
             patch.object(oauth.webbrowser, "open", side_effect=fake_browser), \
             patch.object(oauth.getpass, "getpass", side_effect=fake_prompt), \
             patch.object(oauth, "wait_for_local_callback", side_effect=fake_wait), \
             patch.object(oauth, "exchange_token", side_effect=fake_exchange):
            oauth.login()

        self.assertEqual(events[0], ("browser", oauth.DEVELOPER_APPS_URL))
        self.assertEqual(events[1][0], "secret_prompt")
        self.assertEqual(events[2][0], "wait")
        self.assertEqual(events[3][0], "browser")
        self.assertTrue(events[3][1].startswith(oauth.AUTH_URL + "?"))
        self.assertEqual(events[4], ("exchange", "SECRET_FROM_DEV_CENTER"))
        self.assertEqual(oauth.read_credentials()["client_secret"], "SECRET_FROM_DEV_CENTER")

    def test_login_no_browser_never_launches_devcenter_or_oauth(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_CLIENT_ID": "1234567890123456",
                                    "MERCADOLIVRE_CLIENT_SECRET": ""}), \
             patch.object(oauth.webbrowser, "open") as opened, \
             patch.object(oauth.getpass, "getpass", return_value="SECRET"), \
             patch.object(oauth, "wait_for_local_callback", return_value="CODE"), \
             patch.object(oauth, "exchange_token", return_value={
                 "access_token":"AT","refresh_token":"RT",
                 "expires_at":int(time.time())+3600
             }):
            oauth.login(no_browser=True)
        opened.assert_not_called()

    def test_devcenter_browser_failure_keeps_manual_fallback(self):
        with patch.object(oauth.webbrowser, "open", return_value=False), \
             patch.object(oauth.getpass, "getpass", return_value="SECRET") as prompted, \
             patch("builtins.print") as printed:
            self.assertEqual(oauth.prompt_client_secret(), "SECRET")
        prompted.assert_called_once()
        self.assertTrue(any(oauth.DEVELOPER_APPS_URL in str(call) for call in printed.call_args_list))

    def test_login_env_secret_skips_devcenter_prompt(self):
        with patch.dict(os.environ, {"MERCADOLIVRE_CLIENT_ID": "1234567890123456",
                                    "MERCADOLIVRE_CLIENT_SECRET": "ENV_SECRET"}), \
             patch.object(oauth, "prompt_client_secret") as prompt, \
             patch.object(oauth, "wait_for_local_callback", return_value="CODE"), \
             patch.object(oauth, "exchange_token", return_value={
                 "access_token":"AT","refresh_token":"RT",
                 "expires_at":int(time.time())+3600
             }):
            oauth.login(no_browser=True)
        prompt.assert_not_called()

if __name__ == "__main__":
    unittest.main()
