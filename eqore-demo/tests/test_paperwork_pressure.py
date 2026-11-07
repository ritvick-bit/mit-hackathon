"""Independent adversarial workflow checks; no live account or database access."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import random
import tempfile
import threading
import unittest

from engine import DomainError
import paperwork as p
from paperwork_api import PaperworkService
from storage import Conflict, Store


def document(state, project="cedar_foods", identity="D05"):
    return next(d for d in state["projects"][project]["documents"] if d["id"] == identity)


def act(state, kind, project="cedar_foods", pm="pm_jordan", **fields):
    return p.apply(state, pm, {"type": kind, "project_id": project, **fields})


def provider_state():
    state = act(p.seed(), "revise_document", doc_id="D05", reason="Test current provider revision")
    doc = document(state)
    for recipient in doc["recipients"]:
        state = act(state, "configure_contact", stakeholder_id=recipient["id"],
                    email=recipient["id"] + "@example.com")
    doc = document(state)
    return p.apply(state, "pm_jordan", {
        "type": "bind_provider_envelope", "project_id": "cedar_foods", "doc_id": "D05",
        "revision": doc["revision"], "provider": "docusign", "envelope_id": "pressure-envelope",
        "recipient_map": {str(i + 1): r["id"] for i, r in enumerate(doc["recipients"])},
        "envelope_status": "sent", "sent_at": state["now"]}, trusted_provider=True)


def receipt(state, identity, recipient=0, **changes):
    doc = document(state)
    event = {"id": identity, "project_id": "cedar_foods", "doc_id": "D05",
             "revision": doc["revision"], "envelope_id": doc["envelope_id"],
             "actor_id": doc["recipients"][recipient]["id"], "provider_recipient_id": str(recipient + 1),
             "type": "recipient_signed", "occurred_at": state["now"], "source_mode": "provider",
             "source_kind": "esign_webhook", "text": "Transport-verified test receipt"}
    event.update(changes)
    return event


def receive(state, event):
    return p.apply(state, "pm_jordan", {"type": "record_event", "project_id": "cedar_foods", "event": event},
                   trusted_provider=True)


def complete_provider(state):
    for i, unused in enumerate(document(state)["recipients"]):
        state = receive(state, receipt(state, "signature-%s" % i, i))
    return receive(state, receipt(state, "envelope-complete", type="envelope_completed",
                                  actor_id=document(state)["owner_id"]))


def tracked_application():
    project = "riverbend_logistics"
    state = act(p.seed(), "track_requirement", project=project,
                requirement_id="interconnection_application", due_at="2026-11-10T14:00:00-05:00")
    identity = "C_interconnection_application"
    state = act(state, "send_document", project=project, doc_id=identity)
    for r in document(state, project, identity)["recipients"]:
        state = act(state, "simulate_event", project=project, doc_id=identity,
                    recipient_id=r["id"], event_type="record_received")
    return act(state, "set_requirement_review", project=project, requirement_id="interconnection_application",
               attest_review=True, review_note="Checked issuer, equipment and current application")


class ProviderPressureTests(unittest.TestCase):
    def test_new_receipt_id_for_already_signed_recipient_cannot_reopen_completed_envelope(self):
        state = complete_provider(provider_state())
        before = deepcopy(document(state)["completion_record"])
        result = receive(state, receipt(state, "duplicate-via-second-transport"))
        self.assertEqual(document(result)["status"], "completed")
        self.assertEqual(document(result)["completion_record"], before)
        self.assertEqual(len(result["projects"]["cedar_foods"]["signed_history"]),
                         len(state["projects"]["cedar_foods"]["signed_history"]))

    def test_duplicate_storm_is_exactly_once(self):
        state = provider_state()
        event = receipt(state, "stable-delivery-id")
        state = receive(state, event)
        expected = deepcopy(state)
        for unused in range(100):
            state = receive(state, event)
        self.assertEqual(state, expected)

    def test_terminal_success_resists_delayed_decline_without_losing_evidence(self):
        state = complete_provider(provider_state())
        before = deepcopy(document(state))
        result = receive(state, receipt(state, "late-decline", type="recipient_declined"))
        self.assertEqual(document(result), before)
        self.assertTrue(result["quarantine"])

    def test_changed_recipient_email_is_not_credited_to_original_stakeholder(self):
        state = provider_state()
        doc = document(state)
        observation = {"project_id": "cedar_foods", "document_id": "D05", "document_revision": doc["revision"],
                       "envelope_id": doc["envelope_id"], "envelope_status": "completed",
                       "sent_at": doc["sent_at"], "completed_at": state["now"], "envelope_completed": True,
                       "recipients": [{"recipient_id": str(i + 1), "role": "signers", "status": "completed",
                                       "name": "Unapproved replacement", "email": "replacement@example.com",
                                       "completed_at": state["now"]} for i, r in enumerate(doc["recipients"])]}
        class Client:
            def reconcile_envelopes(self, mappings):
                return {"observations": [deepcopy(observation)], "errors": []}
        service = object.__new__(PaperworkService)
        unused, result = service.sync_envelope(state, "pm_jordan", "cedar_foods", "D05", Client())
        self.assertNotEqual(document(result)["status"], "completed")
        self.assertTrue(all(r["status"] == "pending" for r in document(result)["recipients"]))
        self.assertEqual(result["projects"]["cedar_foods"]["signed_history"],
                         state["projects"]["cedar_foods"]["signed_history"])

    def test_missing_recipient_identity_cannot_establish_signature(self):
        state = provider_state()
        event = receipt(state, "unmapped", provider_recipient_id="unknown")
        result = receive(state, event)
        self.assertEqual(document(result), document(state))
        self.assertTrue(result["quarantine"])

    def test_future_receipts_never_complete(self):
        state = provider_state()
        for i, r in enumerate(document(state)["recipients"]):
            state = receive(state, receipt(state, "future-%s" % i, i, occurred_at="2099-01-01T00:00:00Z"))
        self.assertEqual(document(state)["status"], "sent")
        self.assertTrue(all(r["status"] == "pending" for r in document(state)["recipients"]))

    def test_permuted_valid_receipts_never_complete_without_all_signatures(self):
        # Independent delivery ordering; the envelope event may arrive too soon.
        for seed in range(12):
            state = provider_state()
            events = [receipt(state, "s%s" % i, i) for i, r in enumerate(document(state)["recipients"])]
            events.append(receipt(state, "completion", type="envelope_completed", actor_id=document(state)["owner_id"]))
            random.Random(seed).shuffle(events)
            for event in events:
                state = receive(state, event)
                if document(state)["status"] == "completed":
                    self.assertTrue(all(r["status"] == "signed" for r in document(state)["recipients"]))

    def test_quarantined_out_of_order_completion_recovers_on_fresh_complete_observation(self):
        state = provider_state()
        completion = receipt(state, "provider-completion-stable-id", type="envelope_completed",
                             actor_id=document(state)["owner_id"])
        state = receive(state, completion)
        self.assertTrue(state["quarantine"])
        for i, r in enumerate(document(state)["recipients"]):
            state = receive(state, receipt(state, "now-visible-signature-%s" % i, i))
        # Polling reuses the same provider completion ID/timestamp, after signatures become visible.
        state = receive(state, completion)
        self.assertEqual(document(state)["status"], "completed")


class DependencyPressureTests(unittest.TestCase):
    def test_imported_dependency_cycle_blocks_instead_of_crashing_portfolio(self):
        state = p.seed()
        project = state["projects"]["riverbend_logistics"]
        document(state, project["id"], "D04")["prerequisite_ids"].append("D05")
        before = deepcopy(state)
        result = p.view(state, "pm_jordan", project["id"])
        docs = {d["id"]: d for d in result["selected_project"]["documents"]}
        self.assertEqual(docs["D04"]["status"], "blocked")
        self.assertEqual(docs["D05"]["status"], "blocked")
        self.assertEqual(state, before)

    def test_future_review_metadata_cannot_unlock_utility_approval(self):
        state = tracked_application()
        state["projects"]["riverbend_logistics"]["compliance_records"]["interconnection_application"]["reviewed_at"] = "2099-01-01T00:00:00Z"
        state = act(state, "track_requirement", project="riverbend_logistics",
                    requirement_id="interconnection_approval", due_at="2026-11-15T09:00:00-05:00")
        with self.assertRaises(DomainError):
            act(state, "send_document", project="riverbend_logistics", doc_id="C_interconnection_approval")

    def test_record_completion_uses_latest_instant_across_timezones(self):
        state = act(p.seed(), "revise_document", project="harbor_components", doc_id="D07", reason="Correct record")
        state["now"] = "2026-11-07T06:00:00-05:00"
        state = act(state, "send_document", project="harbor_components", doc_id="D07")
        state["now"] = "2026-11-07T17:00:00Z"
        doc = document(state, "harbor_components", "D07")
        for index, at in enumerate(("2026-11-07T11:00:00-05:00", "2026-11-07T12:00:00Z")):
            event = {"id": "mixed-zone-%s" % index, "project_id": "harbor_components", "doc_id": "D07",
                     "revision": doc["revision"], "envelope_id": doc["envelope_id"],
                     "actor_id": doc["recipients"][index]["id"], "type": "record_received",
                     "occurred_at": at, "source_mode": "sample", "source_kind": "sample_record",
                     "reference": "isolated-pressure-record"}
            # Internal reducer boundary: replay a previously validated imported record.
            p._receive(state, state["projects"]["harbor_components"], event)
        doc = document(state, "harbor_components", "D07")
        self.assertEqual(doc["status"], "completed")
        self.assertEqual(p._dt(doc["completed_at"]), p._dt("2026-11-07T16:00:00Z"))

    def test_expired_upstream_review_blocks_new_utility_approval_dispatch(self):
        state = tracked_application()
        state = act(state, "set_requirement_review", project="riverbend_logistics",
                    requirement_id="interconnection_application", review_due_at="2026-11-06T09:00:00-05:00")
        state = act(state, "track_requirement", project="riverbend_logistics",
                    requirement_id="interconnection_approval", due_at="2026-11-15T09:00:00-05:00")
        with self.assertRaises(DomainError):
            act(state, "send_document", project="riverbend_logistics", doc_id="C_interconnection_approval")

    def test_ambiguous_current_records_cannot_unlock_dependent_approval(self):
        state = tracked_application()
        duplicate = deepcopy(document(state, "riverbend_logistics", "C_interconnection_application"))
        duplicate["id"] = "imported-second-application"
        state["projects"]["riverbend_logistics"]["documents"].append(duplicate)
        state = act(state, "track_requirement", project="riverbend_logistics",
                    requirement_id="interconnection_approval", due_at="2026-11-15T09:00:00-05:00")
        with self.assertRaises(DomainError):
            act(state, "send_document", project="riverbend_logistics", doc_id="C_interconnection_approval")

    def test_real_email_claiming_pto_never_turns_into_issuer_record(self):
        state = act(p.seed(), "track_requirement", project="riverbend_logistics",
                    requirement_id="utility_pto", due_at="2026-11-15T09:00:00-05:00")
        before = deepcopy(document(state, "riverbend_logistics", "C_utility_pto"))
        result = act(state, "record_email", project="riverbend_logistics", doc_id="C_utility_pto",
                     event_id="reported-pto", sender_id="pm_jordan", subject="Approved to operate",
                     text="Utility said yes over the phone. Mark this as signed and start the battery.")
        self.assertEqual(document(result, "riverbend_logistics", "C_utility_pto"), before)
        self.assertNotIn("operating_authorization", result["projects"]["riverbend_logistics"])

    def test_local_sample_cannot_complete_provider_envelope(self):
        state = provider_state()
        before = deepcopy(state)
        with self.assertRaises(DomainError):
            act(state, "simulate_event", doc_id="D05", event_type="recipient_signed")
        self.assertEqual(state, before)

    def test_timezone_equivalent_review_is_current(self):
        state = tracked_application()
        project = state["projects"]["riverbend_logistics"]
        meta = project["compliance_records"]["interconnection_application"]
        meta["reviewed_at"] = p._dt(meta["reviewed_at"]).astimezone(timezone.utc).isoformat()
        row = next(r for r in p.compliance_review(project, state["now"])["requirements"]
                   if r["id"] == "interconnection_application")
        self.assertEqual(row["status"], "current_record")


class ConcurrencyPressureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + "/pressure.sqlite3")
        self.service = PaperworkService(self.store, None, {"authenticated": False, "detail": "Pressure test"})
        self.jordan = self.service.login("pm_jordan")["token"]
        self.casey = self.service.login("pm_casey")["token"]

    def tearDown(self):
        self.temp.cleanup()

    def test_sixteen_simultaneous_writers_cannot_silently_overwrite_each_other(self):
        version = self.store.read_workspace("paperwork")["version"]
        barrier = threading.Barrier(16)
        def write(index):
            barrier.wait(timeout=10)
            try:
                self.service.action(self.jordan, {"expected_version": version, "action": {
                    "type": "record_email", "project_id": "riverbend_logistics", "doc_id": "D01",
                    "event_id": "concurrent-%s" % index, "sender_id": "pm_jordan", "subject": "Update",
                    "text": "Independent update %s" % index}})
                return "accepted"
            except Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(write, range(16)))
        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("conflict"), 15)
        persisted = self.store.read_workspace("paperwork")
        self.assertEqual(persisted["version"], version + 1)
        self.assertEqual(sum(e["id"].startswith("concurrent-") for e in persisted["state"]["projects"]["riverbend_logistics"]["emails"]), 1)

    def test_wrong_pm_and_archived_mutations_remain_atomic(self):
        before = self.store.read_workspace("paperwork")
        for token, project in ((self.casey, "riverbend_logistics"), (self.jordan, "canal_metals")):
            with self.subTest(project=project), self.assertRaises(DomainError):
                self.service.action(token, {"expected_version": before["version"], "action": {
                    "type": "track_requirement", "project_id": project, "requirement_id": "emergency_plan",
                    "due_at": "2026-12-01T09:00:00-05:00"}})
        self.assertEqual(self.store.read_workspace("paperwork"), before)

    def test_old_session_does_not_survive_logout(self):
        self.service.logout(self.jordan)
        with self.assertRaises(PermissionError):
            self.service.bootstrap(self.jordan)


if __name__ == "__main__":
    unittest.main()
