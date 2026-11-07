import base64
from datetime import timedelta
import hashlib
import io
import json
import unittest
import urllib.error
import urllib.parse

from paperwork_connectors import ConnectorError
from paperwork_oauth import PaperworkOAuth, _now


CLIENT = "11111111-2222-3333-4444-555555555555"
GOOGLE_CLIENT = "123456789012-exampleclient.apps.googleusercontent.com"
ENV = {"EQORE_DOCUSIGN_CLIENT_ID": CLIENT, "EQORE_GRAPH_CLIENT_ID": CLIENT}


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "form": urllib.parse.parse_qs(body.decode()) if body else None, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def token():
    return {"access_token": "private-access-value", "expires_in": 3600, "refresh_token": "private-refresh-value"}


def account(base="https://demo.docusign.net"):
    return {"accounts": [{"account_id": "acct-1", "base_uri": base, "is_default": True}]}


class PaperworkOAuthTests(unittest.TestCase):
    def test_missing_client_requires_configuration_without_network(self):
        transport = Transport()
        with self.assertRaises(ConnectorError) as ctx:
            PaperworkOAuth({}, transport).begin("docusign", "pm-token")
        self.assertEqual("client_id_required", ctx.exception.code)
        self.assertEqual([], transport.calls)

    def test_pkce_docusign_callback_and_secret_free_exchange(self):
        transport = Transport(token(), account())
        oauth = PaperworkOAuth(ENV, transport)
        start = oauth.begin("docusign", "pm-token")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(start["auth_url"]).query)
        self.assertEqual("http://localhost:8765/api/paperwork/oauth/callback/docusign", start["redirect_uri"])
        self.assertEqual("signature", query["scope"][0])
        status = oauth.complete("docusign", {"state": start["state"], "code": "one-time-code"}, "pm-token")
        form = transport.calls[0]["form"]
        computed = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(computed, query["code_challenge"][0])
        self.assertNotIn("client_secret", form)
        self.assertEqual("https://account-d.docusign.com/oauth/token", transport.calls[0]["url"])
        self.assertEqual("acct-1", status["account_id"])
        self.assertTrue(status["requires_connection_test"])
        self.assertNotIn("private-", json.dumps(status))
        self.assertEqual("private-access-value", oauth.credentials(session_binding="pm-token")["EQORE_DOCUSIGN_ACCESS_TOKEN"])

    def test_callback_is_single_use_even_after_network_failure(self):
        transport = Transport(RuntimeError("private-access-value"))
        oauth = PaperworkOAuth(ENV, transport)
        start = oauth.begin("docusign", "pm-token")
        for expected in ("oauth_failed", "invalid_state"):
            with self.assertRaises(ConnectorError) as ctx:
                oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-token")
            self.assertEqual(expected, ctx.exception.code)
            self.assertNotIn("private", str(ctx.exception))
        self.assertEqual(1, len(transport.calls))

    def test_wrong_session_cannot_consume_or_read_another_session(self):
        transport = Transport(token(), account())
        oauth = PaperworkOAuth(ENV, transport)
        start = oauth.begin("docusign", "pm-a")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-b")
        self.assertEqual("session_mismatch", ctx.exception.code)
        self.assertEqual([], transport.calls)
        oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-a")
        self.assertEqual({}, oauth.credentials(session_binding="pm-b"))
        self.assertFalse(oauth.status(session_binding="pm-b")["docusign"]["authorized"])
        self.assertTrue(oauth.status(session_binding="pm-a")["docusign"]["authorized"])

    def test_expired_pending_state_never_exchanges(self):
        transport = Transport()
        oauth = PaperworkOAuth(ENV, transport)
        start = oauth.begin("docusign", "pm-token")
        oauth._pending[start["state"]]["expires_at"] = _now() - timedelta(seconds=1)
        with self.assertRaises(ConnectorError):
            oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual([], transport.calls)

    def test_denied_consent_is_safe_and_consumes_state(self):
        oauth = PaperworkOAuth(ENV, Transport())
        start = oauth.begin("docusign", "pm-token")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("docusign", {"state": [start["state"]], "error": ["access_denied"],
                                       "error_description": ["private text"]}, "pm-token")
        self.assertEqual("authorization_declined", ctx.exception.code)
        self.assertNotIn("private", str(ctx.exception))
        self.assertNotIn(start["state"], oauth._pending)

    def test_token_error_does_not_echo_provider_body_or_secret(self):
        error = urllib.error.HTTPError("https://provider/?code=private-code", 400, "private-code", {}, io.BytesIO(b"private-secret"))
        oauth = PaperworkOAuth(ENV, Transport(error))
        start = oauth.begin("graph", "pm-token")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("graph", {"state": start["state"], "code": "private-code"}, "pm-token")
        self.assertNotIn("private", json.dumps(ctx.exception.as_dict()))
        self.assertEqual({}, oauth.credentials(session_binding="pm-token"))

    def test_docusign_rejects_production_or_unknown_account(self):
        for userinfo in (account("https://www.docusign.net"), {"accounts": [
                {"account_id": "a", "base_uri": "https://demo.docusign.net"},
                {"account_id": "b", "base_uri": "https://demo.docusign.net"}]}):
            oauth = PaperworkOAuth(ENV, Transport(token(), userinfo))
            start = oauth.begin("docusign", "pm-token")
            with self.assertRaises(ConnectorError):
                oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-token")
            self.assertEqual({}, oauth.credentials(session_binding="pm-token"))

    def test_docusign_rejects_partial_scope_or_non_bearer_token(self):
        for response in (dict(token(), scope='openid'), dict(token(), token_type='MAC'),
                         dict(token(), token_type=None)):
            transport = Transport(response, account())
            oauth = PaperworkOAuth(ENV, transport)
            start = oauth.begin('docusign', 'pm-token')
            with self.assertRaises(ConnectorError):
                oauth.complete('docusign', {'state': start['state'], 'code': 'code'}, 'pm-token')
            self.assertEqual({}, oauth.credentials(session_binding='pm-token'))
            self.assertEqual(1, len(transport.calls), 'Reject the token before account discovery.')

    def test_docusign_malformed_account_list_is_a_safe_error(self):
        for malformed in ({'accounts': None}, {'accounts': ['not an object']}):
            oauth = PaperworkOAuth(ENV, Transport(token(), malformed))
            start = oauth.begin('docusign', 'pm-token')
            with self.assertRaises(ConnectorError) as ctx:
                oauth.complete('docusign', {'state': start['state'], 'code': 'code'}, 'pm-token')
            self.assertEqual('invalid_account', ctx.exception.code)
            self.assertEqual({}, oauth.credentials(session_binding='pm-token'))

    def test_graph_scope_is_draft_capable_without_send(self):
        transport = Transport(token())
        oauth = PaperworkOAuth(ENV, transport)
        start = oauth.begin("graph", "pm-token", tenant_id="example.onmicrosoft.com")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(start["auth_url"]).query)
        self.assertIn("Mail.ReadWrite", query["scope"][0])
        self.assertNotIn("Mail.Send", query["scope"][0])
        self.assertNotIn("offline_access", query["scope"][0])
        oauth.complete("graph", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual("https://login.microsoftonline.com/example.onmicrosoft.com/oauth2/v2.0/token", transport.calls[0]["url"])

    def test_graph_secret_cannot_be_used_with_unrelated_client_id(self):
        oauth = PaperworkOAuth(dict(ENV, EQORE_GRAPH_CLIENT_SECRET="private-secret"), Transport())
        start = oauth.begin("graph", "pm-token", client_id="11111111-1111-1111-1111-111111111111")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("graph", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual("client_mismatch", ctx.exception.code)

    def test_forget_drops_only_that_session_tokens_and_pending_states(self):
        oauth = PaperworkOAuth(ENV, Transport(token(), account()))
        start = oauth.begin("docusign", "pm-a")
        oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-a")
        other = oauth.begin("graph", "pm-b")
        result = oauth.forget("pm-a")
        self.assertFalse(result["provider_revoked"])
        self.assertEqual({}, oauth.credentials(session_binding="pm-a"))
        self.assertIn(other["state"], oauth._pending)

    def test_expired_credentials_are_not_returned(self):
        oauth = PaperworkOAuth(ENV, Transport(token(), account()))
        start = oauth.begin("docusign", "pm-token")
        oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-token")
        binding = hashlib.sha256(b"pm-token").hexdigest()
        oauth._metadata[binding]["docusign"]["expires_at"] = (_now() - timedelta(seconds=1)).isoformat()
        self.assertEqual({}, oauth.credentials(session_binding="pm-token"))
        self.assertEqual("expired", oauth.status(session_binding="pm-token")["docusign"]["state"])

    def test_logout_during_token_exchange_cannot_restore_credentials(self):
        calls = []
        oauth = None
        def logout_during_exchange(method, url, headers, body, timeout):
            calls.append(url)
            oauth.forget("pm-token")
            return token()
        oauth = PaperworkOAuth(ENV, logout_during_exchange)
        start = oauth.begin("docusign", "pm-token")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("docusign", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual("session_ended", ctx.exception.code)
        self.assertEqual({}, oauth.credentials(session_binding="pm-token"))
        self.assertEqual(1, len(calls), "Logout stops account discovery as well as token storage.")

    def test_arbitrary_oauth_hosts_and_tenant_injection_rejected(self):
        transport = Transport()
        oauth = PaperworkOAuth(ENV, transport)
        with self.assertRaises(ConnectorError):
            oauth.begin("graph", "pm-token", tenant_id="tenant/../../evil")
        with self.assertRaises(ConnectorError):
            oauth._request("graph", "POST", "https://evil.invalid/oauth/token", form={})
        self.assertEqual([], transport.calls)

    def test_gmail_missing_configuration_does_not_connect_or_accept_uuid(self):
        transport = Transport()
        oauth = PaperworkOAuth({}, transport)
        self.assertEqual("unconfigured", oauth.status(session_binding="pm-token")["gmail"]["state"])
        for value in (None, CLIENT, "example.apps.googleusercontent.com.evil.invalid"):
            with self.assertRaises(ConnectorError):
                oauth.begin("gmail", "pm-token", client_id=value)
        self.assertEqual([], transport.calls)
        self.assertEqual({}, oauth.credentials("gmail", session_binding="pm-token"))

    def test_gmail_pkce_uses_google_client_format_and_minimal_read_draft_scopes(self):
        transport = Transport(token())
        oauth = PaperworkOAuth({"EQORE_GMAIL_CLIENT_ID": GOOGLE_CLIENT}, transport)
        start = oauth.begin("gmail", "pm-token")
        parsed = urllib.parse.urlsplit(start["auth_url"])
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual("accounts.google.com", parsed.hostname)
        self.assertEqual("/o/oauth2/v2/auth", parsed.path)
        self.assertEqual("http://localhost:8765/api/paperwork/oauth/callback/gmail", start["redirect_uri"])
        self.assertEqual({"https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"}, set(query["scope"][0].split()))
        self.assertEqual("online", query["access_type"][0])
        status = oauth.complete("gmail", {"state": start["state"], "code": "google-code"}, "pm-token")
        form = transport.calls[0]["form"]
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(expected_challenge, query["code_challenge"][0])
        self.assertEqual("https://oauth2.googleapis.com/token", transport.calls[0]["url"])
        self.assertNotIn("client_secret", form)
        self.assertNotIn("private-", json.dumps(status))
        self.assertEqual({"EQORE_GMAIL_ACCESS_TOKEN": "private-access-value"}, oauth.credentials("gmail", session_binding="pm-token"))

    def test_gmail_secret_stays_on_server_and_is_bound_to_its_client(self):
        transport = Transport(token())
        oauth = PaperworkOAuth({"EQORE_GMAIL_CLIENT_ID": GOOGLE_CLIENT,
                                "EQORE_GMAIL_CLIENT_SECRET": "private-google-secret"}, transport)
        start = oauth.begin("gmail", "pm-token")
        self.assertNotIn("private-google-secret", json.dumps(start))
        status = oauth.complete("gmail", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual(["private-google-secret"], transport.calls[0]["form"]["client_secret"])
        self.assertNotIn("private-google-secret", json.dumps(status))
        other = oauth.begin("gmail", "pm-token", client_id="987654321098-different.apps.googleusercontent.com")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("gmail", {"state": other["state"], "code": "code"}, "pm-token")
        self.assertEqual("client_mismatch", ctx.exception.code)
        self.assertEqual(1, len(transport.calls))

    def test_gmail_cross_session_and_replay_are_rejected(self):
        transport = Transport(token())
        oauth = PaperworkOAuth({"EQORE_GMAIL_CLIENT_ID": GOOGLE_CLIENT}, transport)
        start = oauth.begin("gmail", "pm-a")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("gmail", {"state": start["state"], "code": "code"}, "pm-b")
        self.assertEqual("session_mismatch", ctx.exception.code)
        oauth.complete("gmail", {"state": start["state"], "code": "code"}, "pm-a")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("gmail", {"state": start["state"], "code": "code"}, "pm-a")
        self.assertEqual("invalid_state", ctx.exception.code)
        self.assertEqual({}, oauth.credentials("gmail", session_binding="pm-b"))
        self.assertEqual(1, len(transport.calls))

    def test_gmail_partial_consent_is_not_saved_as_full_access(self):
        partial = dict(token(), scope="https://www.googleapis.com/auth/gmail.readonly")
        oauth = PaperworkOAuth({"EQORE_GMAIL_CLIENT_ID": GOOGLE_CLIENT}, Transport(partial))
        start = oauth.begin("gmail", "pm-token")
        with self.assertRaises(ConnectorError) as ctx:
            oauth.complete("gmail", {"state": start["state"], "code": "code"}, "pm-token")
        self.assertEqual("insufficient_scope", ctx.exception.code)
        self.assertEqual({}, oauth.credentials("gmail", session_binding="pm-token"))

    def test_gmail_token_url_allowlist_does_not_follow_other_google_hosts(self):
        transport = Transport()
        oauth = PaperworkOAuth({}, transport)
        for url in ("https://accounts.google.com/token", "https://oauth2.googleapis.com.evil.invalid/token",
                    "http://oauth2.googleapis.com/token", "https://oauth2.googleapis.com:443/token"):
            with self.assertRaises(ConnectorError):
                oauth._request("gmail", "POST", url, form={})
        self.assertEqual([], transport.calls)


if __name__ == "__main__":
    unittest.main()
