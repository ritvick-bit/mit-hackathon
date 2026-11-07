"""Narrow test-account adapters. Reads and explicit draft creation only; never send.

The caller owns PM authorization, durable request/idempotency records, document
revision checks and review of imported observations. No provider result here
changes a deployment gate or a paperwork acceptance state.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.message import EmailMessage
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


PROVIDERS = ("docusign", "gmail", "graph")
TOKEN_NAMES = {"docusign": "EQORE_DOCUSIGN_ACCESS_TOKEN",
               "gmail": "EQORE_GMAIL_ACCESS_TOKEN", "graph": "EQORE_GRAPH_ACCESS_TOKEN"}
BASES = {"docusign": "https://demo.docusign.net/restapi/v2.1",
         "gmail": "https://gmail.googleapis.com/gmail/v1/users/me",
         "graph": "https://graph.microsoft.com/v1.0/me"}
MAX_RESPONSE = 8 * 1024 * 1024
MAX_DOCUMENT = 4 * 1024 * 1024


class ConnectorError(Exception):
    """Safe to expose: never carries request/response bodies or credentials."""
    def __init__(self, code, message, retryable=False, ambiguous=False):
        super().__init__(message)
        self.code, self.message = code, message
        self.retryable, self.ambiguous = retryable, ambiguous

    def as_dict(self):
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "ambiguous": self.ambiguous}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _identifier(value, name, maximum=160):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,%d}" % maximum, value):
        raise ConnectorError("invalid_input", name + " must be a simple identifier.")
    return value


def _text(value, name, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ConnectorError("invalid_input", name + " is missing or exceeds the allowed size.")
    return value


def _email(value):
    if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", value):
        raise ConnectorError("invalid_input", "A valid recipient email is required.")
    return value


def _scope(payload, revision=False):
    result = {key: _identifier(payload.get(key), key) for key in ("project_id", "document_id")}
    if revision:
        value = payload.get("document_revision")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ConnectorError("invalid_input", "document_revision is required.")
        result["document_revision"] = _identifier(str(value), "document_revision")
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_transport(method, url, headers, body, timeout):
    # Redirects must not forward bearer credentials to an unexpected host.
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ConnectorError("response_too_large", "Provider response exceeds the permitted size.")
        return json.loads(content.decode("utf-8")) if content else {}


class PaperworkConnectors:
    def __init__(self, env=None, transport=None):
        self._env = dict(os.environ if env is None else env)
        self._transport = transport or _http_transport
        self._checks = {}

    def status(self):
        result = {}
        for provider in PROVIDERS:
            required = [TOKEN_NAMES[provider]]
            if provider == "docusign":
                required.append("EQORE_DOCUSIGN_ACCOUNT_ID")
            missing = [name for name in required if not self._env.get(name)]
            checked = self._checks.get(provider, {})
            result[provider] = {
                "provider": provider, "configured": not missing,
                "state": "unconfigured" if missing else checked.get("state", "not_tested"),
                "connected": not missing and checked.get("state") == "connected",
                "missing_env": missing, "last_checked_at": checked.get("checked_at"),
                "mode": "sandbox" if provider == "docusign" else "test_account",
                "capabilities": ["read", "create_draft"], "can_send": False,
                "error": checked.get("error"),
            }
            if provider == "docusign":
                # The account identifier is public configuration, not a credential.
                account = self._env.get("EQORE_DOCUSIGN_ACCOUNT_ID")
                result[provider]["account_id"] = account if isinstance(account, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,160}", account) else None
        return result

    def _provider(self, provider):
        if provider not in PROVIDERS:
            raise ConnectorError("invalid_provider", "Choose docusign, gmail, or graph.")
        if not self.status()[provider]["configured"]:
            raise ConnectorError("unconfigured", "Provider credentials are not configured.")
        return provider

    def _account_path(self):
        account = _identifier(self._env.get("EQORE_DOCUSIGN_ACCOUNT_ID"), "DocuSign account ID")
        return "/accounts/" + account

    def _request(self, provider, method, path, query=None, payload=None, extra_headers=None):
        self._provider(provider)
        if method not in ("GET", "POST") or not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise ConnectorError("invalid_endpoint", "Provider endpoint is not permitted.")
        allowed = {
            "docusign": {"GET": r"/accounts/[A-Za-z0-9_-]+(?:/envelopes(?:/[A-Za-z0-9_-]+)?)?",
                         "POST": r"/accounts/[A-Za-z0-9_-]+/envelopes"},
            "gmail": {"GET": r"/(?:profile|messages(?:/[A-Za-z0-9_-]+)?)", "POST": r"/drafts"},
            "graph": {"GET": r"/(?:mailFolders/inbox|messages(?:/[A-Za-z0-9%=_-]+)?)", "POST": r"/messages"},
        }
        if not re.fullmatch(allowed[provider][method], path):
            raise ConnectorError("invalid_endpoint", "Provider endpoint is not permitted.")
        # Keep all URLs internal; callers cannot supply a host or a pagination URL.
        url = BASES[provider] + path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != urllib.parse.urlsplit(BASES[provider]).hostname or parsed.port is not None:
            raise ConnectorError("invalid_endpoint", "Provider endpoint is not permitted.")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Authorization": "Bearer " + self._env[TOKEN_NAMES[provider]],
                   "Accept": "application/json", "Content-Type": "application/json"}
        headers.update(extra_headers or {})
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            value = self._transport(method, url, headers, body, 15)
            if not isinstance(value, dict):
                raise ValueError("Expected object")
            return value
        except urllib.error.HTTPError as exc:
            # Error pages can echo tokens, addresses, document text or request IDs.
            status = int(exc.code)
            safe_detail = ""
            # Only known, non-sensitive enum names may be surfaced; never echo
            # provider messages, document content, addresses or arbitrary codes.
            if provider == "docusign":
                known_codes = {"INVALID_RECIPIENT_ID", "RECIPIENT_ID_IS_INVALID", "INVALID_REQUEST_BODY",
                               "ANCHOR_TAB_STRING_NOT_FOUND", "INVALID_DOCUMENT_ID", "DOCUMENT_SIZE_EXCEEDED",
                               "INVALID_FILE_TYPE", "INVALID_TRANSACTION_ID", "INVALID_ENVELOPE_TRANSACTION_ID",
                               "ENVELOPE_IS_INCOMPLETE", "DOCUMENT_ALREADY_IN_ENVELOPE", "UNSPECIFIED_ERROR"}
                try:
                    body = json.loads(exc.read(4096).decode("utf-8"))
                    if body.get("errorCode") in known_codes:
                        safe_detail = " " + body["errorCode"]
                except Exception:
                    pass
            code = "authentication_failed" if status in (401, 403) else "provider_http_error"
            raise ConnectorError(code, "Provider %s request failed (HTTP %d).%s" % (method, status, safe_detail),
                                 retryable=method == "GET" and (status == 429 or status >= 500),
                                 ambiguous=method == "POST" and status >= 500) from None
        except ConnectorError:
            raise
        except Exception:
            raise ConnectorError("provider_unavailable", "Provider request could not be completed.",
                                 retryable=method == "GET", ambiguous=method == "POST") from None

    def test_connection(self, provider):
        if provider not in PROVIDERS:
            raise ConnectorError("invalid_provider", "Choose docusign, gmail, or graph.")
        if not self.status()[provider]["configured"]:
            return self.status()[provider]
        try:
            if provider == "docusign":
                self._request(provider, "GET", self._account_path())
            elif provider == "gmail":
                self._request(provider, "GET", "/profile")
            else:
                self._request(provider, "GET", "/mailFolders/inbox", {"$select": "id"})
            self._checks[provider] = {"state": "connected", "checked_at": _now()}
        except ConnectorError as exc:
            self._checks[provider] = {"state": "error", "checked_at": _now(), "error": exc.as_dict()}
        return self.status()[provider]

    def _envelope_observation(self, mapping, data):
        recipients = []
        recipient_data = data.get("recipients", {})
        if not isinstance(recipient_data, dict):
            raise ConnectorError("invalid_provider_response", "Provider returned an invalid recipient list.")
        for role, rows in recipient_data.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                recipients.append({"recipient_id": row.get("recipientId"), "role": role,
                                   "name": row.get("name"), "email": row.get("email"),
                                   "status": row.get("status", "unknown"),
                                   "routing_order": row.get("routingOrder"),
                                   "completed_at": row.get("signedDateTime"),
                                   "declined_at": row.get("declinedDateTime")})
        return {**mapping, "provider": "docusign", "mode": "sandbox", "source_mode": "provider",
                "envelope_status": data.get("status", "unknown"),
                "envelope_completed": data.get("status") == "completed",
                "recipients": recipients, "recipient_statuses": recipients,
                "completed_at": data.get("completedDateTime"),
                "sent_at": data.get("sentDateTime") or data.get("initialSentDateTime"),
                "provider_updated_at": data.get("statusChangedDateTime"),
                "provider_modified_at": data.get("lastModifiedDateTime"),
                "observed_at": _now(), "needs_review": True, "signing_url": None}

    def reconcile_envelopes(self, mappings):
        """Fetch only explicitly mapped envelopes; no account-wide document discovery."""
        if not isinstance(mappings, list) or len(mappings) > 20:
            raise ConnectorError("invalid_input", "Provide at most 20 known envelope mappings.")
        checked = []
        for mapping in mappings:
            item = _scope(mapping, revision=True)
            item["envelope_id"] = _identifier(mapping.get("envelope_id"), "envelope_id")
            checked.append(item)
        observations, errors = [], []
        for item in checked:
            try:
                data = self._request("docusign", "GET", self._account_path() + "/envelopes/" + item["envelope_id"],
                                     {"include": "recipients"})
                if data.get("envelopeId") != item["envelope_id"]:
                    raise ConnectorError("mapping_mismatch", "Provider returned a different envelope.")
                observations.append(self._envelope_observation(item, data))
            except ConnectorError as exc:
                errors.append({**item, **exc.as_dict()})
        return {"provider": "docusign", "observations": observations, "errors": errors, "observed_at": _now()}

    def _draft_identity(self, payload):
        scope = _scope(payload, revision=True)
        request_id = _identifier(payload.get("request_id"), "request_id", maximum=100)
        material = json.dumps([scope, request_id], sort_keys=True).encode()
        return scope, request_id, "eqore-" + hashlib.sha256(material).hexdigest()[:48]

    def recover_envelope_draft(self, payload):
        """Transaction lookup lasts seven days; caller must preserve longer-lived records."""
        scope, request_id, transaction_id = self._draft_identity(payload)
        data = self._request("docusign", "GET", self._account_path() + "/envelopes",
                             {"transaction_ids": transaction_id})
        rows = data.get("envelopeTransactionStatuses", [])
        matching = [row for row in rows if row.get("transactionId") == transaction_id and row.get("envelopeId")]
        if not matching:
            return None
        if len(matching) != 1:
            raise ConnectorError("ambiguous_mapping", "Multiple envelopes match this draft request; review is required.")
        row = matching[0]
        return {**scope, "provider": "docusign", "mode": "sandbox", "request_id": request_id,
                "transaction_id": transaction_id, "envelope_id": row["envelopeId"],
                "envelope_status": row.get("status", "unknown"), "recovered": True,
                "signing_url": None, "needs_review": True}

    def create_envelope_draft(self, payload):
        scope, request_id, transaction_id = self._draft_identity(payload)
        subject = _text(payload.get("subject"), "subject", 100)
        documents, recipients = payload.get("documents"), payload.get("recipients")
        if not isinstance(documents, list) or not 1 <= len(documents) <= 10:
            raise ConnectorError("invalid_input", "Provide 1–10 documents for the draft.")
        prepared_documents = []
        text_documents = []
        total = 0
        for index, doc in enumerate(documents, 1):
            if not isinstance(doc, dict):
                raise ConnectorError("invalid_input", "Each draft document must be a document object.")
            name = _text(doc.get("name"), "document name", 200)
            ext = _identifier(doc.get("file_extension"), "file_extension", 8).lower()
            if ext not in ("pdf", "docx", "txt"):
                raise ConnectorError("invalid_input", "Draft documents must be PDF, DOCX, or text.")
            content = doc.get("content_base64", "")
            try:
                if not isinstance(content, str) or len(content) > (MAX_DOCUMENT * 4 // 3 + 4):
                    raise ValueError()
                decoded = base64.b64decode(content, validate=True)
                if not decoded or len(decoded) > MAX_DOCUMENT:
                    raise ValueError()
                total += len(decoded)
            except (ValueError, TypeError):
                raise ConnectorError("invalid_input", "Each draft document must contain 1 byte to 4 MiB of valid base64 data.") from None
            prepared_documents.append({"documentBase64": content, "name": name,
                                       "fileExtension": ext, "documentId": str(index)})
            if ext == "txt":
                try:
                    text_documents.append((index - 1, decoded.decode("utf-8")))
                except UnicodeDecodeError:
                    raise ConnectorError("invalid_input", "Text draft documents must use UTF-8 encoding.") from None
        if total > MAX_DOCUMENT:
            raise ConnectorError("invalid_input", "Combined draft documents exceed 4 MiB.")
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 20:
            raise ConnectorError("invalid_input", "Provide 1–20 recipients.")
        signers, ids, recipient_map = [], set(), {}
        for signer_index, row in enumerate(recipients, 1):
            if not isinstance(row, dict):
                raise ConnectorError("invalid_input", "Each recipient must be a recipient object.")
            recipient_id = _identifier(row.get("recipient_id"), "recipient_id")
            if recipient_id in ids:
                raise ConnectorError("invalid_input", "Recipient IDs must be unique.")
            ids.add(recipient_id)
            # DocuSign IDs must be integer strings or GUIDs. Application actor
            # identifiers are independent and must never be used as wire IDs.
            wire_recipient_id = str(signer_index)
            recipient_map[wire_recipient_id] = recipient_id
            order = str(row.get("routing_order", "1"))
            if not re.fullmatch(r"[1-9][0-9]{0,3}", order):
                raise ConnectorError("invalid_input", "Recipient routing order must be 1–9999.")
            signers.append({"name": _text(row.get("name"), "recipient name", 100),
                            "email": _email(row.get("email")), "recipientId": wire_recipient_id,
                            "routingOrder": order})
        # The PM-reviewed prose remains intact. Append a deterministic signature
        # section to a text draft so every signer has their own required field.
        # PDF/DOCX uploads keep their bytes unchanged and require field placement
        # in DocuSign before sending. This adapter has no send endpoint.
        signing_field_mode = "manual_review_required"
        if text_documents:
            document_index, original = text_documents[-1]
            document_id = str(document_index + 1)
            blocks = ["\n\nSIGNATURES\n"]
            for signer in signers:
                material = json.dumps([scope, request_id, signer["recipientId"], original], sort_keys=True).encode()
                suffix = hashlib.sha256(material).hexdigest()[:20]
                sign_anchor, date_anchor = "[[rs_" + suffix + "]]", "[[rd_" + suffix + "]]"
                if sign_anchor in original or date_anchor in original:
                    raise ConnectorError("invalid_input", "A generated signature anchor already occurs in this document.")
                blocks.append("\n" + signer["name"] + "\nSignature:\n" + sign_anchor +
                              "\n\n\n\nDate signed:\n" + date_anchor + "\n\n\n")
                common = {"documentId": document_id, "recipientId": signer["recipientId"],
                          "anchorUnits": "pixels", "anchorXOffset": "0", "anchorYOffset": "0",
                          "anchorIgnoreIfNotPresent": "false", "anchorCaseSensitive": "true"}
                signer["tabs"] = {
                    "signHereTabs": [{**common, "anchorString": sign_anchor,
                                      "optional": "false", "tabLabel": "signature_" + suffix}],
                    "dateSignedTabs": [{**common, "anchorString": date_anchor,
                                        "tabLabel": "date_signed_" + suffix}],
                }
            rendered = (original + "".join(blocks)).encode("utf-8")
            total += len(rendered) - len(original.encode("utf-8"))
            if total > MAX_DOCUMENT:
                raise ConnectorError("invalid_input", "Draft documents and signature fields exceed 4 MiB.")
            prepared_documents[document_index]["documentBase64"] = base64.b64encode(rendered).decode()
            signing_field_mode = "anchored"
        recovered = self.recover_envelope_draft(payload)
        if recovered:
            # A recovered envelope could have been edited in DocuSign. Do not
            # claim that its current fields still match this request.
            recovered["signing_field_mode"] = "verify_existing_fields"
            recovered["recipient_map"] = recipient_map
            return recovered
        data = self._request("docusign", "POST", self._account_path() + "/envelopes", payload={
            "status": "created", "transactionId": transaction_id, "emailSubject": subject,
            "documents": prepared_documents, "recipients": {"signers": signers},
            "customFields": {"textCustomFields": [{"name": key, "value": value, "show": "false"}
                                                  for key, value in scope.items()]}})
        envelope_id = data.get("envelopeId")
        if not isinstance(envelope_id, str) or not envelope_id:
            raise ConnectorError("invalid_provider_response", "Draft response has no envelope ID; reconcile the request before retrying.", ambiguous=True)
        return {**scope, "provider": "docusign", "mode": "sandbox", "request_id": request_id,
                "transaction_id": transaction_id, "envelope_id": envelope_id,
                "envelope_status": data.get("status", "unknown"), "recovered": False,
                "signing_url": None, "needs_review": True, "signing_field_mode": signing_field_mode,
                "recipient_map": recipient_map}

    def _mail_scope(self, payload):
        scope = _scope(payload)
        token = payload.get("match_token") or "EQORE-" + scope["project_id"] + "-" + scope["document_id"]
        return scope, _identifier(token, "match_token", maximum=200)

    def pull_mail(self, provider, scope, limit=20):
        """A literal document token narrows retrieval. Matching is still a review cue."""
        if provider not in ("gmail", "graph"):
            raise ConnectorError("invalid_provider", "Choose gmail or graph for mailbox access.")
        mapping, token = self._mail_scope(scope)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ConnectorError("invalid_input", "Mailbox limit must be 1–20.")
        messages = []
        if provider == "gmail":
            found = self._request(provider, "GET", "/messages", {"q": 'subject:"' + token + '"', "maxResults": limit})
            rows = found.get("messages", [])[:limit]
            has_more = bool(found.get("nextPageToken"))
            for row in rows:
                mid = _identifier(row.get("id"), "message_id")
                meta = self._request(provider, "GET", "/messages/" + mid, {"format": "metadata", "metadataHeaders": "Subject"})
                subject = _gmail_headers(meta).get("subject", "")
                if not _has_token(subject, token):
                    continue
                data = self._request(provider, "GET", "/messages/" + mid, {"format": "full"})
                headers = _gmail_headers(data)
                # Recheck after the metadata/full read boundary.
                if not _has_token(headers.get("subject", ""), token):
                    continue
                messages.append({**mapping, "provider": provider, "message_id": mid,
                                 "thread_id": data.get("threadId"), "subject": headers.get("subject", ""),
                                 "from": headers.get("from", ""), "to": headers.get("to", ""),
                                 "received_at": data.get("internalDate"), "date_header": headers.get("date", ""),
                                 "body_text": _gmail_text(data.get("payload", {})),
                                 "attachments_downloaded": False, "source_mode": "provider",
                                 "needs_review": True, "acceptance_inferred": False})
        else:
            found = self._request(provider, "GET", "/messages", {
                "$search": '"subject:' + token + '"', "$top": limit, "$select": "id,subject"})
            rows = found.get("value", [])[:limit]
            has_more = bool(found.get("@odata.nextLink"))
            for row in rows:
                if not _has_token(row.get("subject", ""), token):
                    continue
                mid = row.get("id")
                if not isinstance(mid, str) or not mid or len(mid) > 1024:
                    raise ConnectorError("invalid_provider_response", "Provider returned an invalid message ID.")
                data = self._request(provider, "GET", "/messages/" + urllib.parse.quote(mid, safe=""),
                                     {"$select": "id,subject,from,toRecipients,receivedDateTime,body,conversationId"},
                                     extra_headers={"Prefer": 'outlook.body-content-type="text"'})
                if not _has_token(data.get("subject", ""), token):
                    continue
                messages.append({**mapping, "provider": provider, "message_id": mid,
                                 "thread_id": data.get("conversationId"), "subject": data.get("subject", ""),
                                 "from": data.get("from", {}).get("emailAddress", {}).get("address", ""),
                                 "to": [x.get("emailAddress", {}).get("address", "") for x in data.get("toRecipients", [])],
                                 "received_at": data.get("receivedDateTime"),
                                 "body_text": data.get("body", {}).get("content", "")[:262144],
                                 "body_content_type": data.get("body", {}).get("contentType"),
                                 "attachments_downloaded": False, "source_mode": "provider",
                                 "needs_review": True, "acceptance_inferred": False})
        for message in messages:
            message["id"], message["text"] = message["message_id"], message["body_text"]
        return {**mapping, "provider": provider, "match_token": token, "messages": messages,
                "has_more": has_more, "observed_at": _now(), "needs_review": True}

    def create_mail_draft(self, provider, payload):
        if provider not in ("gmail", "graph"):
            raise ConnectorError("invalid_provider", "Choose gmail or graph for a mailbox draft.")
        scope, token = self._mail_scope(payload)
        recipients = payload.get("to")
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 20:
            raise ConnectorError("invalid_input", "Provide 1–20 draft recipients.")
        recipients = [_email(x) for x in recipients]
        subject = _text(payload.get("subject"), "subject", 400)
        if "\r" in subject or "\n" in subject:
            raise ConnectorError("invalid_input", "Draft subject must be one line.")
        if not _has_token(subject, token):
            subject = "[" + token + "] " + subject
        body = _text(payload.get("body"), "body", 262144)
        if provider == "gmail":
            message = EmailMessage()
            message["To"], message["Subject"] = ", ".join(recipients), subject
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            data = self._request(provider, "POST", "/drafts", payload={"message": {"raw": raw}})
            draft_id = data.get("id")
        else:
            data = self._request(provider, "POST", "/messages", payload={
                "subject": subject, "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": address}} for address in recipients]})
            draft_id = data.get("id")
        if not isinstance(draft_id, str) or not draft_id:
            raise ConnectorError("invalid_provider_response", "Draft response has no ID; review the mailbox before retrying.", ambiguous=True)
        return {**scope, "provider": provider, "draft_id": draft_id, "match_token": token,
                "status": "draft", "sent": False, "signing_url": None,
                "created_at": _now(), "needs_review": True}


def _has_token(subject, token):
    return isinstance(subject, str) and re.search(r"(?<![A-Za-z0-9_-])" + re.escape(token) + r"(?![A-Za-z0-9_-])", subject) is not None


def _gmail_headers(data):
    return {str(item.get("name", "")).lower(): item.get("value", "")
            for item in data.get("payload", {}).get("headers", [])}


def _gmail_text(payload):
    # Text-only view of the original message, not an LLM or acceptance assertion.
    parts = []
    if payload.get("mimeType") == "text/plain" and not payload.get("filename"):
        encoded = payload.get("body", {}).get("data", "")
        if isinstance(encoded, str) and len(encoded) <= 400000:
            try:
                parts.append(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8", errors="replace"))
            except (ValueError, TypeError):
                pass
    for part in payload.get("parts", []):
        parts.append(_gmail_text(part))
    return "\n".join(x for x in parts if x)[:262144]
