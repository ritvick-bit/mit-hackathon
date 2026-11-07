"""Real loopback HTTP boundary; OAuth/provider transports are fully in memory."""
from contextlib import redirect_stderr
import io
import json
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.parse

from paperwork_api import PaperworkService
from paperwork_connectors import PaperworkConnectors
from paperwork_oauth import PaperworkOAuth
from server import Handler
from storage import Store


CLIENT = "11111111-2222-3333-4444-555555555555"


class NoJobs:
    def submit(self, function):
        raise AssertionError("No model job belongs in an OAuth HTTP test")


class OAuthTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(url)
        if url.endswith("/oauth/token"):
            return {"access_token": "never-return-access-token", "refresh_token": "never-return-refresh-token", "expires_in": 3600}
        return {"accounts": [{"account_id": "sandbox-1", "is_default": True, "base_uri": "https://demo.docusign.net"}]}


class PaperworkHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict("os.environ", {"EQORE_DOCUSIGN_CLIENT_ID": CLIENT}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = PaperworkService(Store(self.tmp.name + "/test.sqlite3"), NoJobs(), {"authenticated": False, "detail": "test"})
        self.transport = OAuthTransport()
        self.service.oauth = PaperworkOAuth({"EQORE_DOCUSIGN_CLIENT_ID": CLIENT}, self.transport)
        self.service.connectors = PaperworkConnectors({})
        self.api_calls = []
        def api_transport(method, url, headers, body, timeout):
            self.api_calls.append(url)
            return {"accountId": "sandbox-1"}
        self.factory = patch("paperwork_api.PaperworkConnectors", side_effect=lambda env=None: PaperworkConnectors(env or {}, api_transport))
        self.factory.start()
        self.addCleanup(self.factory.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.actual_port = self.server.server_address[1]
        # Match the fixed registered callback Host without binding the user's app port.
        self.server.server_address = ("127.0.0.1", 8765)
        self.server.app = SimpleNamespace(paperwork=self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.jordan = self.service.login("pm_jordan")["token"]
        self.casey = self.service.login("pm_casey")["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, payload=None, token=None, cookie=None, host="localhost:8765", origin=None):
        headers = {"Host": host}
        if token:
            headers["Authorization"] = "Bearer " + token
        if cookie:
            headers["Cookie"] = cookie
        if origin:
            headers["Origin"] = origin
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn = HTTPConnection("127.0.0.1", self.actual_port, timeout=3)
        try:
            conn.request("POST" if payload is not None else "GET", path,
                         json.dumps(payload) if payload is not None else None, headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            conn.close()

    def begin(self, token=None):
        status, headers, body = self.request("/api/paperwork/oauth/start", {"provider": "docusign"}, token or self.jordan)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(data["authorization_url"]).query)["state"][0]
        return state, headers["Set-Cookie"]

    def test_portfolio_map_assets_are_served_without_exposing_private_files(self):
        for path, expected in (("/paperwork-map.js", "javascript"), ("/paperwork-map.css", "text/css")):
            status, headers, body = self.request(path)
            self.assertEqual(200, status, path)
            self.assertIn(expected, headers["Content-Type"])
            self.assertTrue(body.strip())
        _, _, page = self.request("/")
        self.assertIn('/paperwork-map.js', page)
        self.assertLess(page.index('/paperwork-map.js'), page.index('/paperwork.js'))
        for path in ("/paperwork.py", "/data/eqore.sqlite3", "/../paperwork.py"):
            self.assertEqual(404, self.request(path)[0], path)

    @staticmethod
    def callback(state):
        return "/api/paperwork/oauth/callback/docusign?" + urllib.parse.urlencode({"state": state, "code": "never-log-auth-code"})

    def test_start_requires_pm_session_localhost_and_same_origin(self):
        for token, host, origin in ((None, "localhost:8765", None),
                                    (self.jordan, "127.0.0.1:8765", None),
                                    (self.jordan, "localhost:8765", "https://external.invalid")):
            status, _, _ = self.request("/api/paperwork/oauth/start", {"provider": "docusign"}, token, host=host, origin=origin)
            self.assertIn(status, (400, 403))
        self.assertEqual([], self.transport.calls)

    def test_cookie_binding_callback_and_response_do_not_leak_credentials(self):
        state, cookie = self.begin()
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/api/paperwork/oauth/", cookie)
        self.assertIn("Max-Age=600", cookie)
        status, headers, body = self.request(self.callback(state), cookie=cookie.split(";", 1)[0])
        self.assertEqual(200, status, body)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual("no-referrer", headers["Referrer-Policy"])
        self.assertNotIn("never-return", body)
        self.assertNotIn("never-log", body)
        self.assertNotIn(self.jordan, body)
        self.assertEqual(2, len(self.transport.calls))
        self.assertEqual(1, len(self.api_calls))
        _, _, jordan_body = self.request("/api/paperwork/connectors", token=self.jordan)
        _, _, casey_body = self.request("/api/paperwork/connectors", token=self.casey)
        self.assertTrue(json.loads(jordan_body)["configuration"]["docusign"]["connected"])
        self.assertFalse(json.loads(casey_body)["configuration"]["docusign"]["connected"])
        self.assertNotIn("never-return", jordan_body + casey_body)

    def test_callback_without_cookie_or_with_other_pm_is_rejected(self):
        state, cookie = self.begin()
        status, _, _ = self.request(self.callback(state))
        self.assertEqual(403, status)
        status, _, body = self.request(self.callback(state), cookie="eqore_oauth=" + self.casey)
        self.assertEqual(400, status)
        self.assertEqual("session_mismatch", json.loads(body)["code"])
        self.assertEqual([], self.transport.calls)
        status, _, _ = self.request(self.callback(state), cookie=cookie.split(";", 1)[0])
        self.assertEqual(200, status)

    def test_callback_replay_and_logged_out_session_cannot_exchange(self):
        state, cookie = self.begin()
        cookie = cookie.split(";", 1)[0]
        self.assertEqual(200, self.request(self.callback(state), cookie=cookie)[0])
        self.assertEqual(400, self.request(self.callback(state), cookie=cookie)[0])
        self.assertEqual(2, len(self.transport.calls))
        self.request("/api/paperwork/logout", {}, self.jordan)
        self.assertEqual({}, self.service.oauth.credentials(session_binding=self.jordan))
        self.assertNotIn(self.jordan, self.service.session_connectors)
        self.assertEqual(403, self.request(self.callback(state), cookie=cookie)[0])

    def test_oauth_success_error_and_start_urls_are_not_access_logged(self):
        logs = io.StringIO()
        with redirect_stderr(logs):
            state, cookie = self.begin()
            self.request(self.callback(state), cookie=cookie.split(";", 1)[0])
            self.request(self.callback(state), cookie=cookie.split(";", 1)[0])
        self.assertNotIn("never-log-auth-code", logs.getvalue())
        self.assertNotIn(state, logs.getvalue())
        self.assertNotIn("/api/paperwork/oauth/", logs.getvalue())


if __name__ == "__main__":
    unittest.main()
