"""Loopback test-account OAuth; credentials stay in this process, never the UI.

The HTTP layer owns PM authentication and an HttpOnly session cookie on localhost.
It must suppress callback query strings in access logs. This is not a production
identity service or a durable token vault.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request

from paperwork_connectors import ConnectorError


CALLBACKS = {provider: "http://localhost:8765/api/paperwork/oauth/callback/" + provider
             for provider in ("docusign", "graph", "gmail")}
AUTH = {"docusign": "https://account-d.docusign.com/oauth/auth",
        "graph": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "gmail": "https://accounts.google.com/o/oauth2/v2/auth"}
TOKEN = {"docusign": "https://account-d.docusign.com/oauth/token",
         "graph": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
         "gmail": "https://oauth2.googleapis.com/token"}
SCOPES = {"docusign": "signature", "graph": "https://graph.microsoft.com/Mail.ReadWrite",
          "gmail": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose"}


def _now():
    return datetime.now(timezone.utc)


def _binding(value):
    if not isinstance(value, str) or not value:
        raise ConnectorError("session_required", "The same signed-in PM session is required.")
    return hashlib.sha256(value.encode()).hexdigest()


def _client_id(value, provider="docusign"):
    pattern = (r"[A-Za-z0-9_-]{3,200}\.apps\.googleusercontent\.com" if provider == "gmail"
               else r"[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}")
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ConnectorError("client_id_required", "Configure this application's valid integration or client ID.")
    return value


def _tenant_id(value):
    if value in ("organizations", "common", "consumers"):
        return value
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value) and ".." not in value:
        return value
    raise ConnectorError("invalid_tenant", "Configure a valid Microsoft tenant identifier.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(method, url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        content = response.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("Response exceeds limit")
        return json.loads(content.decode())


class PaperworkOAuth:
    def __init__(self, env=None, transport=None):
        self._env = dict(os.environ if env is None else env)
        self._transport = transport or _transport
        self._pending, self._credentials, self._metadata = {}, {}, {}
        self._generations = {}
        self._lock = threading.RLock()

    def begin(self, provider, session_binding, client_id=None, tenant_id=None):
        if provider not in CALLBACKS:
            raise ConnectorError("invalid_provider", "OAuth supports docusign, graph, or gmail.")
        binding_hash = _binding(session_binding)
        client = _client_id(client_id or self._env.get("EQORE_" + provider.upper() + "_CLIENT_ID"), provider)
        tenant = _tenant_id(tenant_id or self._env.get("EQORE_GRAPH_TENANT_ID", "organizations")) if provider == "graph" else None
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        expires = _now() + timedelta(minutes=10)
        scope = SCOPES[provider]
        with self._lock:
            self._pending = {key: value for key, value in self._pending.items() if value["expires_at"] > _now()}
            if len(self._pending) >= 100:
                raise ConnectorError("too_many_attempts", "Finish an existing sign-in or try again shortly.")
            self._pending[state] = {"provider": provider, "binding": binding_hash, "client_id": client,
                                    "tenant": tenant, "verifier": verifier, "expires_at": expires, "scope": scope,
                                    "generation": self._generations.get(binding_hash, 0)}
        params = {"response_type": "code", "client_id": client, "redirect_uri": CALLBACKS[provider],
                  "scope": scope, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
        if provider == "graph":
            params.update(response_mode="query", prompt="select_account")
        elif provider == "gmail":
            # This process keeps access tokens only; do not request offline access.
            params.update(access_type="online", prompt="select_account")
        return {"provider": provider, "auth_url": AUTH[provider].format(tenant=tenant) + "?" + urllib.parse.urlencode(params),
                "state": state, "redirect_uri": CALLBACKS[provider], "expires_at": expires.isoformat()}

    def _request(self, provider, method, url, form=None, token=None):
        parsed = urllib.parse.urlsplit(url)
        allowed = (provider == "docusign" and parsed.hostname == "account-d.docusign.com"
                   and ((method == "POST" and parsed.path == "/oauth/token")
                        or (method == "GET" and parsed.path == "/oauth/userinfo"))) or (
                   provider == "graph" and parsed.hostname == "login.microsoftonline.com" and method == "POST"
                   and re.fullmatch(r"/[A-Za-z0-9.-]+/oauth2/v2.0/token", parsed.path)) or (
                   provider == "gmail" and parsed.hostname == "oauth2.googleapis.com" and method == "POST"
                   and parsed.path == "/token")
        if not allowed or parsed.scheme != "https" or parsed.port is not None or parsed.query or parsed.fragment or parsed.username:
            raise ConnectorError("invalid_endpoint", "OAuth endpoint is not permitted.")
        headers = {"Accept": "application/json"}
        body = None
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(form).encode()
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            result = self._transport(method, url, headers, body, 15)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("Invalid response")
            return result
        except Exception:
            # Never surface provider error bodies, codes, secrets, or token values.
            raise ConnectorError("oauth_failed", "Provider authorization could not be completed. Start a new sign-in.") from None

    def complete(self, provider, query, session_binding=None):
        if provider not in CALLBACKS or not isinstance(query, dict):
            raise ConnectorError("invalid_callback", "Invalid authorization callback.")
        # parse_qs dictionaries and direct string dictionaries are both accepted.
        def parameter(name):
            value = query.get(name)
            if isinstance(value, list):
                return value[0] if len(value) == 1 else None
            return value
        state = parameter("state")
        if not isinstance(state, str) or not state or len(state) > 200:
            raise ConnectorError("invalid_state", "Authorization state is missing or invalid.")
        binding_hash = _binding(session_binding)
        with self._lock:
            pending = self._pending.get(state)
            if not pending or pending["provider"] != provider or pending["expires_at"] <= _now():
                self._pending.pop(state, None)
                raise ConnectorError("invalid_state", "This sign-in has expired or was already used. Start again.")
            if not secrets.compare_digest(pending["binding"], binding_hash):
                raise ConnectorError("session_mismatch", "Return to the same PM session that started sign-in.")
            # Consume before network exchange; replay cannot produce a second token request.
            self._pending.pop(state)
        if parameter("error"):
            raise ConnectorError("authorization_declined", "Provider sign-in was not authorized.")
        code = parameter("code")
        if not isinstance(code, str) or not 1 <= len(code) <= 8192:
            raise ConnectorError("invalid_callback", "The provider did not return an authorization code.")
        form = {"grant_type": "authorization_code", "code": code, "client_id": pending["client_id"],
                "code_verifier": pending["verifier"], "redirect_uri": CALLBACKS[provider]}
        if provider == "graph":
            form["scope"] = pending["scope"]
        if provider in ("graph", "gmail"):
            secret = self._env.get("EQORE_" + provider.upper() + "_CLIENT_SECRET")
            if secret:
                # A secret belongs to one configured confidential client, not an arbitrary UI ID.
                if pending["client_id"] != self._env.get("EQORE_" + provider.upper() + "_CLIENT_ID"):
                    raise ConnectorError("client_mismatch", "The configured secret belongs to a different application.")
                form["client_secret"] = secret
        result = self._request(provider, "POST", TOKEN[provider].format(tenant=pending["tenant"]), form=form)
        with self._lock:
            if self._generations.get(binding_hash, 0) != pending["generation"]:
                raise ConnectorError("session_ended", "This PM session ended during provider sign-in.")
        access = result.get("access_token")
        try:
            lifetime = int(result.get("expires_in", 0))
        except (TypeError, ValueError):
            lifetime = 0
        if not isinstance(access, str) or not access or lifetime <= 0 or lifetime > 366 * 86400:
            raise ConnectorError("invalid_token_response", "The provider did not return a valid access token and expiry.")
        token_type = result.get("token_type", "Bearer")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ConnectorError("invalid_token_response", "The provider did not return a bearer access token.")
        if provider == "docusign" and "scope" in result:
            granted = result["scope"]
            if not isinstance(granted, str) or "signature" not in granted.split():
                raise ConnectorError("insufficient_scope", "DocuSign signature access was not granted. No token was saved.")
        if provider == "gmail" and "scope" in result:
            granted = result["scope"]
            if not isinstance(granted, str) or not set(SCOPES[provider].split()).issubset(set(granted.split())):
                raise ConnectorError("insufficient_scope", "Gmail read and draft permissions were not both granted. No token was saved.")
        credentials = {"EQORE_" + provider.upper() + "_ACCESS_TOKEN": access}
        metadata = {"provider": provider, "authorized": True, "expires_at": (_now() + timedelta(seconds=lifetime)).isoformat(),
                    "authorized_at": _now().isoformat(), "mode": "sandbox" if provider == "docusign" else "test_account",
                    "client_id": pending["client_id"], "requires_connection_test": True}
        if provider == "docusign":
            user = self._request(provider, "GET", "https://account-d.docusign.com/oauth/userinfo", token=access)
            accounts = user.get("accounts", [])
            if not isinstance(accounts, list) or any(not isinstance(a, dict) for a in accounts):
                raise ConnectorError("invalid_account", "The provider returned an invalid account list.")
            preferred = self._env.get("EQORE_DOCUSIGN_ACCOUNT_ID")
            if preferred:
                candidates = [a for a in accounts if a.get("account_id") == preferred]
            else:
                candidates = [a for a in accounts if a.get("is_default") is True or str(a.get("is_default")).lower() == "true"]
                if not candidates and len(accounts) == 1:
                    candidates = accounts
            if len(candidates) != 1:
                raise ConnectorError("account_selection_required", "Configure the intended DocuSign API account ID and reconnect.")
            account = candidates[0]
            account_id = account.get("account_id")
            if not isinstance(account_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", account_id):
                raise ConnectorError("invalid_account", "The provider returned an invalid account ID.")
            if str(account.get("base_uri", "")).rstrip("/") != "https://demo.docusign.net":
                raise ConnectorError("sandbox_required", "This integration currently accepts DocuSign developer accounts only.")
            credentials["EQORE_DOCUSIGN_ACCOUNT_ID"] = account_id
            metadata["account_id"] = account_id
        with self._lock:
            if self._generations.get(binding_hash, 0) != pending["generation"]:
                raise ConnectorError("session_ended", "This PM session ended during provider sign-in.")
            self._credentials.setdefault(binding_hash, {})[provider] = credentials
            self._metadata.setdefault(binding_hash, {})[provider] = metadata
        return dict(metadata)

    def credentials(self, provider=None, session_binding=None):
        """SERVER ONLY: never serialize this return value into an HTTP response."""
        if provider is not None and provider not in CALLBACKS:
            raise ConnectorError("invalid_provider", "OAuth supports docusign, graph, or gmail.")
        binding_hash = _binding(session_binding)
        with self._lock:
            result = {}
            for key, values in self._credentials.get(binding_hash, {}).items():
                if provider is None or key == provider:
                    if datetime.fromisoformat(self._metadata[binding_hash][key]["expires_at"]) > _now():
                        result.update(values)
            return result

    def status(self, session_binding=None):
        binding_hash = _binding(session_binding)
        with self._lock:
            result = {}
            for provider in CALLBACKS:
                metadata = dict(self._metadata.get(binding_hash, {}).get(provider, {"provider": provider, "authorized": False}))
                if provider == "gmail" and not metadata["authorized"] and not self._env.get("EQORE_GMAIL_CLIENT_ID"):
                    metadata.update(state="unconfigured", configured=False)
                    result[provider] = metadata
                    continue
                if metadata.get("expires_at") and datetime.fromisoformat(metadata["expires_at"]) <= _now():
                    metadata.update(authorized=False, state="expired")
                else:
                    metadata["state"] = "authorized" if metadata["authorized"] else "not_authorized"
                result[provider] = metadata
            return result

    def forget(self, session_binding):
        """Erase local credentials and pending flows; does not claim provider revocation."""
        binding_hash = _binding(session_binding)
        with self._lock:
            self._generations[binding_hash] = self._generations.get(binding_hash, 0) + 1
            self._credentials.pop(binding_hash, None)
            self._metadata.pop(binding_hash, None)
            self._pending = {key: value for key, value in self._pending.items() if value["binding"] != binding_hash}
        return {"forgotten": True, "provider_revoked": False}
