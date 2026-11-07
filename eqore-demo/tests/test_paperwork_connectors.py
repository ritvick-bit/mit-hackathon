import base64
import copy
from email import message_from_bytes
import io
import json
import unittest
import urllib.error
import urllib.parse

from paperwork_connectors import ConnectorError, PaperworkConnectors


ENV = {"EQORE_DOCUSIGN_ACCESS_TOKEN": "secret-docusign", "EQORE_DOCUSIGN_ACCOUNT_ID": "account-1",
       "EQORE_GMAIL_ACCESS_TOKEN": "secret-gmail", "EQORE_GRAPH_ACCESS_TOKEN": "secret-graph"}
SCOPE = {"project_id": "p-1", "document_id": "D05", "document_revision": 2}


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "body": json.loads(body) if body else None, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(self.calls[-1])
        return response


def envelope_payload():
    return {**SCOPE, "request_id": "req-1", "subject": "Implementation acknowledgement",
            "documents": [{"name": "Draft.txt", "file_extension": "txt",
                           "content_base64": base64.b64encode(b"Review this draft").decode()}],
            "recipients": [{"name": "Customer", "email": "customer@example.com", "recipient_id": "customer"}],
            "status": "sent"}  # Caller cannot override the draft-only contract.


class PaperworkConnectorTests(unittest.TestCase):
    def test_unconfigured_never_calls_network_or_claims_connected(self):
        fake = FakeTransport()
        client = PaperworkConnectors({}, fake)
        status = client.test_connection("docusign")
        self.assertFalse(status["configured"])
        self.assertFalse(status["connected"])
        self.assertEqual("unconfigured", status["state"])
        self.assertEqual([], fake.calls)
        with self.assertRaises(ConnectorError) as ctx:
            client.create_mail_draft("gmail", {**SCOPE, "to": ["x@example.com"], "subject": "Follow up", "body": "Please review."})
        self.assertEqual("unconfigured", ctx.exception.code)

    def test_configuration_is_not_connection(self):
        client = PaperworkConnectors(ENV, FakeTransport({"accountId": "account-1"}))
        self.assertEqual("not_tested", client.status()["docusign"]["state"])
        self.assertTrue(client.test_connection("docusign")["connected"])
        self.assertNotIn("secret", json.dumps(client.status()))

    def test_one_recipient_complete_does_not_complete_envelope(self):
        fake = FakeTransport({"envelopeId": "env-1", "status": "sent", "sentDateTime": "2026-11-07T12:00:00Z", "recipients": {
            "signers": [{"recipientId": "customer", "status": "completed"},
                        {"recipientId": "commercial", "status": "sent"}]}})
        result = PaperworkConnectors(ENV, fake).reconcile_envelopes([{**SCOPE, "envelope_id": "env-1"}])
        item = result["observations"][0]
        self.assertFalse(item["envelope_completed"])
        self.assertEqual("2026-11-07T12:00:00Z", item["sent_at"])
        self.assertEqual("sent", item["envelope_status"])
        self.assertEqual(["completed", "sent"], [r["status"] for r in item["recipients"]])
        self.assertTrue(item["needs_review"])
        self.assertIsNone(item["signing_url"])
        self.assertEqual("GET", fake.calls[0]["method"])

    def test_reconciliation_checks_envelope_mapping_and_preserves_other_successes(self):
        fake = FakeTransport({"envelopeId": "wrong", "status": "completed"},
                             {"envelopeId": "env-2", "status": "completed", "completedDateTime": "2026-11-07T14:00:00Z"})
        result = PaperworkConnectors(ENV, fake).reconcile_envelopes([
            {**SCOPE, "envelope_id": "env-1"}, {**SCOPE, "document_id": "D12", "envelope_id": "env-2"}])
        self.assertEqual("mapping_mismatch", result["errors"][0]["code"])
        self.assertEqual("env-2", result["observations"][0]["envelope_id"])
        self.assertTrue(result["observations"][0]["envelope_completed"])

    def test_draft_creation_recovers_first_and_never_sends(self):
        fake = FakeTransport({"envelopeTransactionStatuses": []}, {"envelopeId": "env-new", "status": "created"})
        payload = envelope_payload()
        saved = copy.deepcopy(payload)
        result = PaperworkConnectors(ENV, fake).create_envelope_draft(payload)
        self.assertEqual(payload, saved)
        self.assertEqual("created", fake.calls[1]["body"]["status"])
        transaction = fake.calls[1]["body"]["transactionId"]
        self.assertIn(transaction, fake.calls[0]["url"])
        self.assertEqual("created", result["envelope_status"])
        self.assertIsNone(result["signing_url"])
        self.assertFalse(result["recovered"])
        self.assertEqual({'1': 'customer'}, result['recipient_map'])
        self.assertEqual('1', fake.calls[1]['body']['recipients']['signers'][0]['recipientId'])
        self.assertNotIn("views/recipient", " ".join(c["url"] for c in fake.calls))

    def test_retry_recovers_same_transaction_without_second_create(self):
        def existing(call):
            transaction = urllib.parse.parse_qs(urllib.parse.urlsplit(call["url"]).query)["transaction_ids"][0]
            return {"envelopeTransactionStatuses": [{"transactionId": transaction, "envelopeId": "env-existing", "status": "created"}]}
        fake = FakeTransport(existing)
        result = PaperworkConnectors(ENV, fake).create_envelope_draft(envelope_payload())
        self.assertTrue(result["recovered"])
        self.assertEqual({'1': 'customer'}, result['recipient_map'])
        self.assertEqual("env-existing", result["envelope_id"])
        self.assertEqual(["GET"], [c["method"] for c in fake.calls])

    def test_text_drafts_have_unique_required_fields_for_each_signer(self):
        fake = FakeTransport({"envelopeTransactionStatuses": []}, {"envelopeId": "env-new", "status": "created"})
        payload = envelope_payload()
        payload['recipients'].append({'name': 'Project manager', 'email': 'pm@example.com',
                                      'recipient_id': 'pm', 'routing_order': 2})
        result = PaperworkConnectors(ENV, fake).create_envelope_draft(payload)
        sent = fake.calls[1]['body']
        self.assertEqual('created', sent['status'])
        self.assertEqual('anchored', result['signing_field_mode'])
        self.assertEqual({'1': 'customer', '2': 'pm'}, result['recipient_map'])
        body = base64.b64decode(sent['documents'][0]['documentBase64']).decode()
        self.assertTrue(body.startswith('Review this draft'))
        anchors = set()
        for signer in sent['recipients']['signers']:
            for key in ('signHereTabs', 'dateSignedTabs'):
                tab = signer['tabs'][key][0]
                self.assertEqual('1', tab['documentId'])
                self.assertEqual(signer['recipientId'], tab['recipientId'])
                self.assertEqual('false', tab['anchorIgnoreIfNotPresent'])
                self.assertEqual(1, body.count(tab['anchorString']))
                self.assertNotIn(tab['anchorString'], anchors)
                anchors.add(tab['anchorString'])
            self.assertEqual('false', signer['tabs']['signHereTabs'][0]['optional'])
        self.assertEqual(['1', '2'], [r['routingOrder'] for r in sent['recipients']['signers']])
        self.assertEqual(['1', '2'], [r['recipientId'] for r in sent['recipients']['signers']])

    def test_signature_fields_are_stable_across_identical_requests(self):
        bodies = []
        for _ in range(2):
            fake = FakeTransport({'envelopeTransactionStatuses': []}, {'envelopeId': 'env-new', 'status': 'created'})
            PaperworkConnectors(ENV, fake).create_envelope_draft(envelope_payload())
            bodies.append(fake.calls[1]['body'])
        self.assertEqual(bodies[0], bodies[1])

    def test_binary_document_bytes_are_preserved_and_field_review_is_required(self):
        for extension in ('pdf', 'docx'):
            fake = FakeTransport({'envelopeTransactionStatuses': []}, {'envelopeId': 'env-new', 'status': 'created'})
            payload = envelope_payload()
            payload['documents'][0]['file_extension'] = extension
            original = payload['documents'][0]['content_base64']
            result = PaperworkConnectors(ENV, fake).create_envelope_draft(payload)
            self.assertEqual('manual_review_required', result['signing_field_mode'])
            self.assertEqual(original, fake.calls[1]['body']['documents'][0]['documentBase64'])
            self.assertNotIn('tabs', fake.calls[1]['body']['recipients']['signers'][0])

    def test_invalid_text_or_recipient_shape_never_calls_provider(self):
        malformed = []
        payload = envelope_payload()
        payload['documents'][0]['content_base64'] = base64.b64encode(b'\xff\xfe').decode()
        malformed.append(payload)
        payload = envelope_payload()
        payload['documents'] = ['not an object']
        malformed.append(payload)
        payload = envelope_payload()
        payload['recipients'] = ['not an object']
        malformed.append(payload)
        payload = envelope_payload()
        payload['recipients'][0]['routing_order'] = True
        malformed.append(payload)
        for payload in malformed:
            fake = FakeTransport()
            with self.assertRaises(ConnectorError):
                PaperworkConnectors(ENV, fake).create_envelope_draft(payload)
            self.assertEqual([], fake.calls)

    def test_bad_provider_recipient_shape_is_a_scoped_error(self):
        fake = FakeTransport({'envelopeId': 'env-1', 'status': 'completed', 'recipients': 'bad'},
                             {'envelopeId': 'env-2', 'status': 'sent', 'recipients': {}})
        result = PaperworkConnectors(ENV, fake).reconcile_envelopes([
            {**SCOPE, 'envelope_id': 'env-1'}, {**SCOPE, 'document_id': 'D12', 'envelope_id': 'env-2'}])
        self.assertEqual('invalid_provider_response', result['errors'][0]['code'])
        self.assertEqual('env-2', result['observations'][0]['envelope_id'])

    def test_http_error_details_and_token_are_redacted_and_post_is_ambiguous(self):
        error = urllib.error.HTTPError("https://example.invalid/?token=secret-docusign", 503,
                                       "secret-docusign", {}, io.BytesIO(b"secret-docusign private content"))
        fake = FakeTransport({"envelopeTransactionStatuses": []}, error)
        with self.assertRaises(ConnectorError) as ctx:
            PaperworkConnectors(ENV, fake).create_envelope_draft(envelope_payload())
        rendered = json.dumps(ctx.exception.as_dict())
        self.assertNotIn("secret", rendered)
        self.assertNotIn("private", rendered)
        self.assertTrue(ctx.exception.ambiguous)
        self.assertFalse(ctx.exception.retryable)

    def test_arbitrary_transport_exception_is_redacted(self):
        fake = FakeTransport(RuntimeError("secret-gmail Bearer leaked"))
        result = PaperworkConnectors(ENV, fake).test_connection("gmail")
        self.assertEqual("error", result["state"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(result["connected"])

    def test_gmail_search_does_not_fetch_unmatched_body_and_email_is_not_acceptance(self):
        token = "EQORE-p-1-D05"
        def gmail_message(subject, body="Signed, thanks"):
            return {"threadId": "thread-1", "internalDate": "1794050400000", "payload": {
                "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": "customer@example.com"}],
                "mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}}
        fake = FakeTransport({"messages": [{"id": "m1"}, {"id": "m2"}]},
                             gmail_message("Other project's D05"),
                             gmail_message("Re: [" + token + "] Please review"),
                             gmail_message("Re: [" + token + "] Please review"))
        result = PaperworkConnectors(ENV, fake).pull_mail("gmail", SCOPE)
        self.assertEqual(1, len(result["messages"]))
        item = result["messages"][0]
        self.assertEqual("Signed, thanks", item["text"])
        self.assertFalse(item["acceptance_inferred"])
        self.assertTrue(item["needs_review"])
        self.assertNotIn("/m1?format=full", " ".join(c["url"] for c in fake.calls))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0]["url"]).query)
        self.assertEqual('subject:"' + token + '"', query["q"][0])

    def test_scope_rejects_query_injection_before_network(self):
        fake = FakeTransport()
        with self.assertRaises(ConnectorError):
            PaperworkConnectors(ENV, fake).pull_mail("gmail", {**SCOPE, "match_token": 'x" OR in:anywhere'})
        self.assertEqual([], fake.calls)

    def test_graph_mail_uses_scoped_search_and_escapes_message_id(self):
        fake = FakeTransport({"value": [{"id": "abc+/=", "subject": "[EQORE-p-1-D05] Approval"}]},
                             {"id": "abc+/=", "subject": "[EQORE-p-1-D05] Approval",
                              "body": {"contentType": "text", "content": "Please review"}})
        result = PaperworkConnectors(ENV, fake).pull_mail("graph", SCOPE)
        self.assertEqual("Please review", result["messages"][0]["text"])
        self.assertIn("abc%2B%2F%3D", fake.calls[1]["url"])
        self.assertFalse(result["messages"][0]["acceptance_inferred"])

    def test_both_mailbox_draft_methods_never_call_send(self):
        payload = {**SCOPE, "to": ["customer@example.com"], "subject": "Please review", "body": "Review current document."}
        gmail, graph = FakeTransport({"id": "draft-1"}), FakeTransport({"id": "draft-2"})
        for provider, fake in (("gmail", gmail), ("graph", graph)):
            result = PaperworkConnectors(ENV, fake).create_mail_draft(provider, payload)
            self.assertEqual("draft", result["status"])
            self.assertFalse(result["sent"])
            self.assertNotIn("/send", fake.calls[0]["url"])
            self.assertEqual("POST", fake.calls[0]["method"])
        raw = base64.urlsafe_b64decode(gmail.calls[0]["body"]["message"]["raw"])
        message = message_from_bytes(raw)
        self.assertIn("EQORE-p-1-D05", str(message["Subject"]))
        self.assertEqual("customer@example.com", message["To"])

    def test_no_send_or_external_endpoint_can_pass_transport_allowlist(self):
        client, fake = None, FakeTransport()
        client = PaperworkConnectors(ENV, fake)
        for provider, path in (("gmail", "/drafts/send"), ("graph", "/messages/a/send"),
                               ("docusign", "/accounts/account-1/envelopes/a/views/recipient"),
                               ("gmail", "https://evil.invalid/")):
            with self.assertRaises(ConnectorError):
                client._request(provider, "POST", path, payload={})
        self.assertEqual([], fake.calls)

    def test_header_injection_rejected_before_draft_write(self):
        fake = FakeTransport()
        with self.assertRaises(ConnectorError):
            PaperworkConnectors(ENV, fake).create_mail_draft("gmail", {
                **SCOPE, "to": ["customer@example.com"], "subject": "Hi\r\nBcc: stranger@example.com", "body": "x"})
        self.assertEqual([], fake.calls)


if __name__ == "__main__":
    unittest.main()
