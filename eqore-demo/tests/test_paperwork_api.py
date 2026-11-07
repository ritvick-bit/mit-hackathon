"""Service-boundary checks over real durable paperwork records, without network calls."""
import copy
from datetime import datetime, timedelta, timezone
import json
import tempfile
import urllib.parse
import unittest
from unittest.mock import patch

from engine import DomainError
from paperwork_api import PaperworkService
from paperwork_connectors import ConnectorError, PaperworkConnectors
from storage import Conflict, Store


class DeferredPool:
    """Keep model work pending so concurrent revision changes are deterministic."""
    def __init__(self):
        self.pending = []

    def submit(self, function):
        self.pending.append(function)

    def run_next(self):
        self.pending.pop(0)()


class Transport:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else {"id": "provider-draft-1"}
        self.error, self.calls = error, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url,
                           "body": json.loads(body) if body else None})
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)


class SequenceTransport(Transport):
    def __init__(self, *responses):
        super().__init__()
        self.responses = list(responses)

    def __call__(self, method, url, headers, body, timeout):
        call = {"method": method, "url": url, "body": json.loads(body) if body else None}
        self.calls.append(call)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response(call) if callable(response) else copy.deepcopy(response)


class PaperworkServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name + "/paperwork.sqlite3")
        self.pool = DeferredPool()
        self.service = PaperworkService(self.store, self.pool, {
            "available": True, "authenticated": True, "detail": "Isolated test model"})
        self.jordan = self.service.login("pm_jordan")["token"]
        self.casey = self.service.login("pm_casey")["token"]
        self.transport = Transport()
        self.service.connectors = PaperworkConnectors({
            "EQORE_GRAPH_ACCESS_TOKEN": "test-secret-graph-token",
            "EQORE_DOCUSIGN_ACCESS_TOKEN": "test-secret-signing-token",
            "EQORE_DOCUSIGN_ACCOUNT_ID": "sandbox-account-1",
        }, self.transport)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self):
        return self.store.read_workspace("paperwork")

    def perform(self, action_type, project_id="harbor_components", token=None, **fields):
        return self.service.action(token or self.jordan, {
            "expected_version": self.record()["version"],
            "action": {"type": action_type, "project_id": project_id, **fields}})

    def ready_doc(self, project_id="harbor_components"):
        project = self.service.bootstrap(self.jordan, project_id)["selected_project"]
        return next(d for d in project["documents"] if "send_document" in d["allowed_actions"])

    @staticmethod
    def authority(state):
        """Fields that a prose-reading result is never allowed to decide."""
        return {project_id: [{key: copy.deepcopy(doc.get(key)) for key in (
            "id", "status", "revision", "recipients", "envelope_id", "envelope_status",
            "completion_record", "source_event_ids", "dependency_revisions")}
            for doc in project["documents"]]
            for project_id, project in state["projects"].items()}

    @staticmethod
    def model_result(**overrides):
        data = {"summary": "One recipient still needs to respond.", "subject": "Review the current document",
                "body": "Please review the current revision. This is a draft only.",
                "source_ids": [], "uncertainties": []}
        data.update(overrides)
        return {"output": data, "model": "test-model", "role": "Paperwork reader"}

    def submit_assist(self, doc_id, token=None, project_id="harbor_components", kind="summary"):
        return self.service.assist(token or self.jordan, {
            "expected_version": self.record()["version"], "project_id": project_id,
            "doc_id": doc_id, "kind": kind})["job_id"]

    def test_session_and_read_views_enforce_pm_project_membership(self):
        before = self.record()
        jordan = self.service.bootstrap(self.jordan)
        casey = self.service.bootstrap(self.casey)
        jordan_ids = {p["id"] for p in jordan["projects"] + jordan["archives"]}
        casey_ids = {p["id"] for p in casey["projects"] + casey["archives"]}
        self.assertTrue(jordan_ids)
        self.assertTrue(casey_ids)
        self.assertFalse(jordan_ids & casey_ids)
        for token, project_id in ((self.casey, next(iter(jordan_ids))),
                                  (self.jordan, next(iter(casey_ids)))):
            with self.subTest(project_id=project_id), self.assertRaises((DomainError, PermissionError)):
                self.service.bootstrap(token, project_id)
        self.assertEqual(before, self.record(), "Reading or selecting a project must not change shared records.")

    def test_forged_pm_field_cannot_expand_write_access(self):
        before = self.record()
        with self.assertRaises((DomainError, PermissionError)):
            self.service.action(self.casey, {"expected_version": before["version"], "pm_id": "pm_jordan",
                "action": {"type": "draft_email", "project_id": "harbor_components",
                           "doc_id": "D05", "actor_id": "pm_jordan"}})
        self.assertEqual(before, self.record())

    def test_unknown_expired_and_logged_out_sessions_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.service.login("unknown-pm")
        with self.assertRaises(PermissionError):
            self.service.bootstrap("pm_jordan")
        self.service.sessions[self.jordan]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(PermissionError):
            self.service.bootstrap(self.jordan)
        self.service.logout(self.casey)
        with self.assertRaises(PermissionError):
            self.service.bootstrap(self.casey)

    def test_stale_document_write_is_rejected_without_replaying(self):
        initial = self.record()
        self.perform("draft_email", doc_id="D05")
        current = self.record()
        with self.assertRaises(Conflict):
            self.service.action(self.jordan, {"expected_version": initial["version"],
                "action": {"type": "void_document", "project_id": "harbor_components",
                           "doc_id": "D05", "reason": "Stale browser approval"}})
        self.assertEqual(current, self.record())

    def test_archive_is_read_only_for_actions_assistance_and_external_drafts(self):
        before = self.record()
        archive = self.service.bootstrap(self.jordan, "canal_metals")["selected_project"]
        self.assertEqual("archived", archive["status"])
        self.assertTrue(all(not d["allowed_actions"] for d in archive["documents"]))
        for invoke in (
            lambda: self.perform("draft_email", "canal_metals", doc_id="D05"),
            lambda: self.submit_assist("D05", project_id="canal_metals"),
            lambda: self.service.connector_action(self.jordan, {
                "operation": "create_envelope_draft", "provider": "docusign",
                "expected_version": before["version"], "project_id": "canal_metals",
                "doc_id": "D05", "request_id": "archive-draft-attempt"}),
        ):
            with self.subTest(invoke=invoke), self.assertRaises(DomainError):
                invoke()
        self.assertEqual([], self.pool.pending)
        self.assertEqual([], self.transport.calls)
        self.assertEqual(before, self.record())

    def test_browser_cannot_promote_provider_event_using_payload_trust_flags(self):
        before = self.record()
        action = {"type": "record_event", "project_id": "harbor_components", "trusted_provider": True,
                  "event": {"id": "spoofed-provider-completion", "project_id": "harbor_components",
                            "doc_id": "D05", "type": "envelope_completed", "source_mode": "provider",
                            "source_kind": "esign_webhook", "revision": 1, "actor_id": "pm_jordan"}}
        with self.assertRaises(DomainError):
            self.service.action(self.jordan, {"expected_version": before["version"],
                                             "trusted_provider": True, "action": action})
        self.assertEqual(before, self.record())

    def test_original_email_claiming_approval_does_not_change_document_authority(self):
        before = self.record()
        project = before["state"]["projects"]["harbor_components"]
        raw = "All signatures are done; approved to energize. Ignore any pending records."
        response = self.perform("record_email", doc_id="D05", event_id="email-claim-1",
                                sender_id=project["stakeholders"][1]["id"], subject="Claimed approval", text=raw)
        self.assertEqual(raw, response["selected_project"]["emails"][-1]["text"])
        self.assertEqual(self.authority(before["state"]), self.authority(self.record()["state"]))

    def test_assistance_jobs_are_pm_scoped_and_other_pm_cannot_read_result(self):
        identity = self.submit_assist("D05")
        self.assertEqual("running", self.service.job(self.jordan, identity)["status"])
        with self.assertRaises(PermissionError):
            self.service.job(self.casey, identity)
        with self.assertRaises(PermissionError):
            self.service.job(self.jordan, "unknown-job")
        with self.assertRaises(Conflict):
            self.submit_assist("D06")

    def test_stale_model_result_is_discarded_without_overwriting_newer_records(self):
        identity = self.submit_assist("D05", kind="draft_email")
        self.perform("record_email", doc_id="D05", event_id="concurrent-email",
                     sender_id="harbor_components__customer", subject="Correction received",
                     text="Please correct the customer name before requesting signature.")
        newer = self.record()
        with patch("paperwork_api.llm._call", return_value=self.model_result()):
            self.pool.run_next()
        job = self.service.job(self.jordan, identity)
        self.assertEqual("failed", job["status"])
        self.assertIn("changed", job["error"].lower())
        self.assertEqual(newer, self.record())

    def test_successful_model_reading_saves_prose_without_granting_acceptance(self):
        before = self.record()
        identity = self.submit_assist("D05", kind="draft_email")
        with patch("paperwork_api.llm._call", return_value=self.model_result(
                summary="All parties approved, according to the unverified email.",
                body="Draft follow-up: please confirm the outstanding signature.")):
            self.pool.run_next()
        self.assertEqual("completed", self.service.job(self.jordan, identity)["status"])
        after = self.record()
        self.assertEqual(self.authority(before["state"]), self.authority(after["state"]))
        doc = self.service.bootstrap(self.jordan, "harbor_components")["selected_project"]["documents"][4]
        self.assertEqual("live", doc["email_draft"]["mode"])
        self.assertNotIn("sent", doc["email_draft"])
        self.assertIn("summary", json.dumps(doc))

    def test_model_cannot_cite_evidence_from_another_document(self):
        before = self.record()
        identity = self.submit_assist("D05")
        with patch("paperwork_api.llm._call", return_value=self.model_result(source_ids=["foreign-project-source"])):
            self.pool.run_next()
        self.assertEqual("failed", self.service.job(self.jordan, identity)["status"])
        self.assertEqual(before, self.record())

    def test_unavailable_model_does_not_create_a_fallback_completion_or_job(self):
        self.service.auth["authenticated"] = False
        before = self.record()
        with self.assertRaises(ValueError):
            self.submit_assist("D05")
        self.assertEqual([], self.pool.pending)
        self.assertEqual(before, self.record())

    def test_sample_recipient_addresses_cannot_reach_real_mailbox_draft_transport(self):
        self.perform("draft_email", doc_id="D05")
        before = self.record()
        with self.assertRaises((ValueError, ConnectorError)):
            self.service.connector_action(self.jordan, {
                "operation": "create_email_draft", "provider": "graph",
                "expected_version": before["version"], "project_id": "harbor_components", "doc_id": "D05"})
        self.assertEqual([], self.transport.calls, "Placeholder recipients must be rejected before outbound draft creation.")
        self.assertEqual(before, self.record())

    def test_sample_signer_addresses_cannot_reach_docusign_transport(self):
        project_id = "bayview_packaging"
        d = next(d for d in self.service.bootstrap(self.jordan, project_id)["selected_project"]["documents"]
                 if d["kind"] == "esign" and "send_document" in d["allowed_actions"])
        before = self.record()
        with self.assertRaises((ValueError, ConnectorError)):
            self.service.connector_action(self.jordan, {
                "operation": "create_envelope_draft", "provider": "docusign",
                "expected_version": before["version"], "project_id": project_id,
                "doc_id": d["id"], "request_id": "placeholder-envelope-attempt"})
        self.assertEqual([], self.transport.calls)
        self.assertEqual(before, self.record())

    def test_provider_test_failure_redacts_credentials_and_preserves_document_state(self):
        self.transport.error = RuntimeError("Bearer test-secret-graph-token private inbox text")
        before = self.record()
        response = self.service.connector_action(self.jordan, {"operation": "test", "provider": "graph"})
        public = json.dumps(response)
        self.assertFalse(response["connector_result"]["connected"])
        self.assertNotIn("test-secret", public)
        self.assertNotIn("private inbox", public)
        self.assertNotIn("Bearer", public)
        self.assertEqual(before, self.record())

    def test_cross_pm_external_draft_denied_before_transport(self):
        before = self.record()
        with self.assertRaises((DomainError, PermissionError)):
            self.service.connector_action(self.casey, {
                "operation": "create_email_draft", "provider": "graph",
                "expected_version": before["version"], "project_id": "harbor_components", "doc_id": "D05"})
        self.assertEqual([], self.transport.calls)
        self.assertEqual(before, self.record())


    def test_external_account_connection_is_scoped_to_the_pm_browser_session(self):
        private = PaperworkConnectors({"EQORE_GRAPH_ACCESS_TOKEN": "private-jordan-token"}, Transport())
        self.service.session_connectors[self.jordan] = private
        self.service.connectors = PaperworkConnectors({}, Transport())
        jordan = self.service.bootstrap(self.jordan)["connectors"]["configuration"]
        casey = self.service.bootstrap(self.casey)["connectors"]["configuration"]
        self.assertTrue(jordan["graph"]["configured"])
        self.assertFalse(casey["graph"]["configured"])
        self.assertNotIn("private-jordan-token", json.dumps(jordan))
        self.service.logout(self.jordan)
        self.assertNotIn(self.jordan, self.service.session_connectors)
        with self.assertRaises(PermissionError):
            self.service.client(self.jordan)

    def configure_real_signers(self, project_id, doc_id):
        project = self.service.bootstrap(self.jordan, project_id)["selected_project"]
        doc = next(d for d in project["documents"] if d["id"] == doc_id)
        for index, recipient in enumerate(doc["recipients"]):
            self.perform("configure_contact", project_id, stakeholder_id=recipient["id"],
                         email="reviewer%s@sample-mailbox.org" % index)

    def test_created_provider_draft_has_no_signatures_and_is_not_dispatched(self):
        project_id, doc_id = "bayview_packaging", "D12"
        self.configure_real_signers(project_id, doc_id)
        transport = SequenceTransport({"envelopeTransactionStatuses": []},
                                      {"envelopeId": "env-created-1", "status": "created"})
        self.service.connectors = PaperworkConnectors({
            "EQORE_DOCUSIGN_ACCESS_TOKEN": "local-test-token", "EQORE_DOCUSIGN_ACCOUNT_ID": "account-1"}, transport)
        before = self.record()
        result = self.service.connector_action(self.jordan, {
            "operation": "create_envelope_draft", "provider": "docusign",
            "expected_version": before["version"], "project_id": project_id,
            "doc_id": doc_id, "request_id": "reviewed-envelope-draft-1"})
        current = next(d for d in result["selected_project"]["documents"] if d["id"] == doc_id)
        self.assertEqual("docusign", current["provider"])
        self.assertEqual("created", current["envelope_status"])
        self.assertNotIn(current["status"], ("sent", "partially_signed", "completed"))
        self.assertTrue(all(r["status"] == "pending" for r in current["recipients"]))
        self.assertIsNone(current["completed_at"])
        self.assertEqual(["GET", "POST"], [c["method"] for c in transport.calls])
        self.assertEqual("created", transport.calls[-1]["body"]["status"])
        self.assertNotIn("/send", transport.calls[-1]["url"])

    def test_ambiguous_envelope_creation_recovers_same_request_without_second_post(self):
        project_id, doc_id = "bayview_packaging", "D12"
        self.configure_real_signers(project_id, doc_id)
        def recovered(call):
            transaction = urllib.parse.parse_qs(urllib.parse.urlsplit(call["url"]).query)["transaction_ids"][0]
            return {"envelopeTransactionStatuses": [{"transactionId": transaction,
                    "envelopeId": "env-recovered-1", "status": "created"}]}
        transport = SequenceTransport({"envelopeTransactionStatuses": []},
                                      RuntimeError("Response lost after provider accepted the draft"), recovered)
        self.service.connectors = PaperworkConnectors({
            "EQORE_DOCUSIGN_ACCESS_TOKEN": "local-test-token", "EQORE_DOCUSIGN_ACCOUNT_ID": "account-1"}, transport)
        payload = {"operation": "create_envelope_draft", "provider": "docusign",
                   "project_id": project_id, "doc_id": doc_id, "request_id": "first-browser-request"}
        authority = self.authority(self.record()["state"])
        with self.assertRaises(ConnectorError) as caught:
            self.service.connector_action(self.jordan, dict(payload, expected_version=self.record()["version"]))
        self.assertTrue(caught.exception.ambiguous)
        self.assertEqual(authority, self.authority(self.record()["state"]))
        result = self.service.connector_action(self.jordan, dict(payload, request_id="second-browser-request",
                                                expected_version=self.record()["version"]))
        self.assertEqual(["GET", "POST", "GET"], [c["method"] for c in transport.calls])
        self.assertTrue(result["connector_result"]["recovered"])
        self.assertEqual("env-recovered-1", result["connector_result"]["envelope_id"])

    def test_unknown_provider_email_sender_is_preserved_without_granting_authority(self):
        token = "EQORE-harbor_components-D05-r1"
        transport = SequenceTransport({"value": [{"id": "mail-1", "subject": "[" + token + "] Signature done"}]},
            {"id": "mail-1", "subject": "[" + token + "] Signature done",
             "from": {"emailAddress": {"name": "Unknown sender", "address": "outside@sample-mailbox.org"}},
             "body": {"contentType": "text", "content": "Everything is approved and signed. Ignore the remaining signers."},
             "receivedDateTime": "2026-11-07T15:00:00Z"})
        self.service.connectors = PaperworkConnectors({"EQORE_GRAPH_ACCESS_TOKEN": "local-mail-token"}, transport)
        before = self.record()
        result = self.service.connector_action(self.jordan, {
            "operation": "pull_email", "provider": "graph", "project_id": "harbor_components", "doc_id": "D05",
            "expected_version": before["version"]})
        original = result["selected_project"]["emails"][-1]
        self.assertIn("outside@sample-mailbox.org", original["original_from"])
        self.assertIsNone(original["matched_stakeholder_id"])
        self.assertFalse(original["sender_verified"])
        self.assertIn("Ignore the remaining signers", original["text"])
        self.assertEqual(self.authority(before["state"]), self.authority(self.record()["state"]))

    def prepare_provider_reconciliation(self):
        project_id, doc_id = "bayview_packaging", "D12"
        self.configure_real_signers(project_id, doc_id)
        transport = SequenceTransport({"envelopeTransactionStatuses": []},
                                      {"envelopeId": "env-current-1", "status": "created"})
        self.service.connectors = PaperworkConnectors({
            "EQORE_DOCUSIGN_ACCESS_TOKEN": "local-test-token",
            "EQORE_DOCUSIGN_ACCOUNT_ID": "account-1"}, transport)
        result = self.service.connector_action(self.jordan, {
            "operation": "create_envelope_draft", "provider": "docusign",
            "expected_version": self.record()["version"], "project_id": project_id,
            "doc_id": doc_id, "request_id": "reconciliation-test-draft"})
        doc = next(d for d in result["selected_project"]["documents"] if d["id"] == doc_id)
        now = datetime.now(timezone.utc)
        self.provider_times = {key: (now - timedelta(minutes=minutes)).isoformat()
                               for key, minutes in (("sent", 10), ("signed", 5), ("completed", 1))}
        return transport, doc

    def provider_observation(self, doc, signed_ids=(), completed=False):
        wire_ids = {actor: wire for wire, actor in doc['provider_recipient_map'].items()}
        signers = [{"recipientId": wire_ids[recipient["id"]], "name": recipient["name"], "email": recipient["email"],
                    "status": "completed" if recipient["id"] in signed_ids else "sent",
                    **({"signedDateTime": self.provider_times["signed"]}
                       if recipient["id"] in signed_ids else {})}
                   for recipient in doc["recipients"]]
        return {"envelopeId": doc["envelope_id"], "status": "completed" if completed else "sent",
                "sentDateTime": self.provider_times["sent"],
                "statusChangedDateTime": self.provider_times["completed"],
                **({"completedDateTime": self.provider_times["completed"]} if completed else {}),
                "recipients": {"signers": signers}}

    def reconcile_provider(self):
        return self.service.connector_action(self.jordan, {
            "operation": "sync_envelope", "provider": "docusign",
            "expected_version": self.record()["version"],
            "project_id": "bayview_packaging", "doc_id": "D12"})

    @staticmethod
    def reconciled_doc(result):
        return next(d for d in result["selected_project"]["documents"] if d["id"] == "D12")

    def test_verified_dispatch_partial_signature_and_envelope_completion_are_separate(self):
        transport, doc = self.prepare_provider_reconciliation()
        recipient_ids = [r["id"] for r in doc["recipients"]]
        self.assertGreater(len(recipient_ids), 1, "This fixture must exercise multiple required signers.")
        transport.responses.append(self.provider_observation(doc, recipient_ids[:1]))
        partial = self.reconcile_provider()
        partial_doc = self.reconciled_doc(partial)
        self.assertEqual("partially_signed", partial_doc["status"])
        self.assertEqual(self.provider_times["sent"], partial_doc["sent_at"])
        self.assertEqual(1, sum(r["status"] == "signed" for r in partial_doc["recipients"]))
        self.assertIsNone(partial_doc["completed_at"])

        # Even all individual signatures do not substitute for envelope completion.
        transport.responses.append(self.provider_observation(doc, recipient_ids))
        all_signed = self.reconcile_provider()
        self.assertTrue(all(r["status"] == "signed" for r in self.reconciled_doc(all_signed)["recipients"]))
        self.assertNotEqual("completed", self.reconciled_doc(all_signed)["status"])

        complete_observation = self.provider_observation(doc, recipient_ids, completed=True)
        transport.responses.append(complete_observation)
        completed = self.reconcile_provider()
        completed_doc = self.reconciled_doc(completed)
        self.assertEqual("completed", completed_doc["status"])
        self.assertEqual(self.provider_times["completed"], completed_doc["completed_at"])
        signatures = [r for r in completed["selected_project"]["signed_history"] if r["doc_id"] == "D12"]
        self.assertEqual(set(recipient_ids), {r["recipient_id"] for r in signatures})
        self.assertEqual(len(recipient_ids), len(signatures))
        self.assertTrue(all(r["source_mode"] == "provider" for r in signatures))
        self.assertEqual([], completed["selected_project"]["quarantine"])

        # Polling the same provider result must not create extra signatures or acceptance.
        authority = self.authority(self.record()["state"])
        transport.responses.append(complete_observation)
        duplicate = self.reconcile_provider()
        self.assertEqual(authority, self.authority(self.record()["state"]))
        self.assertEqual(completed["selected_project"]["signed_history"],
                         duplicate["selected_project"]["signed_history"])
        self.assertTrue(all(c["method"] == "GET" for c in transport.calls[2:]))

    def test_provider_envelope_completion_cannot_fill_missing_signatures(self):
        transport, doc = self.prepare_provider_reconciliation()
        transport.responses.append(self.provider_observation(doc, completed=True))
        result = self.reconcile_provider()
        current = self.reconciled_doc(result)
        self.assertNotEqual("completed", current["status"])
        self.assertIsNone(current["completed_at"])
        self.assertTrue(all(r["status"] == "pending" for r in current["recipients"]))
        self.assertTrue(any("missing individual recipient signatures" in q["reason"]
                            for q in result["selected_project"]["quarantine"]))

    def test_provider_reconciliation_rejects_a_different_envelope(self):
        transport, doc = self.prepare_provider_reconciliation()
        observation = self.provider_observation(doc, [r["id"] for r in doc["recipients"]], completed=True)
        observation["envelopeId"] = "env-another-project"
        transport.responses.append(observation)
        authority = self.authority(self.record()["state"])
        result = self.reconcile_provider()
        self.assertEqual([], result["connector_result"]["observations"])
        self.assertEqual("mapping_mismatch", result["connector_result"]["errors"][0]["code"])
        self.assertEqual(authority, self.authority(self.record()["state"]))
        self.assertIn("/envelopes/" + doc["envelope_id"], transport.calls[-1]["url"])

    def test_non_signer_roles_and_unmapped_recipients_cannot_supply_required_signatures(self):
        transport, doc = self.prepare_provider_reconciliation()
        observation = self.provider_observation(doc)
        observation["recipients"]["carbonCopies"] = [{
            "recipientId": next(iter(doc['provider_recipient_map'])), "status": "completed",
            "signedDateTime": self.provider_times["signed"]}]
        observation["recipients"]["signers"].append({
            "recipientId": "999", "status": "completed",
            "signedDateTime": self.provider_times["signed"]})
        transport.responses.append(observation)
        result = self.reconcile_provider()
        current = self.reconciled_doc(result)
        self.assertEqual("sent", current["status"])
        self.assertTrue(all(r["status"] == "pending" for r in current["recipients"]))
        self.assertFalse(any(r["doc_id"] == "D12" for r in result["selected_project"]["signed_history"]))
        self.assertFalse(any(e["type"] == "recipient_signed" for e in current["source_events"]))


if __name__ == "__main__":
    unittest.main()
