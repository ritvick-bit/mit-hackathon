"""Paperwork is scoped, source-backed and distinct from operational permission."""
from copy import deepcopy
import unittest

from engine import DomainError
import paperwork as p


class PaperworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opening = p.seed()

    def state(self):
        return deepcopy(self.opening)

    def doc(self, state, project="cedar_foods", identity="D05"):
        return next(d for d in state["projects"][project]["documents"] if d["id"] == identity)

    def act(self, state, kind, project="cedar_foods", doc="D05", pm="pm_jordan", **fields):
        return p.apply(state, pm, dict(type=kind, project_id=project, doc_id=doc, **fields))

    def complete(self, state, project, identity):
        doc = self.doc(state, project, identity)
        pm = state["projects"][project]["pm_id"]
        if doc["status"] in ("ready", "draft"):
            state = self.act(state, "send_document", project, identity, pm)
        for recipient in self.doc(state, project, identity)["recipients"]:
            if recipient["status"] in ("signed", "received", "accepted"):
                continue
            event_type = {"esign": "recipient_signed", "review": "review_accepted", "record": "record_received"}[doc["kind"]]
            state = self.act(state, "simulate_event", project, identity, pm,
                             event_type=event_type, recipient_id=recipient["id"])
        return state

    def provider(self, state=None, status="sent"):
        state = self.state() if state is None else state
        state = self.act(state, "revise_document", reason="Prepare the exact current revision for a connected test account.")
        doc = self.doc(state)
        action = {"type": "bind_provider_envelope", "project_id": "cedar_foods", "doc_id": "D05",
                  "revision": doc["revision"], "provider": "docusign", "envelope_id": "verified-test-envelope",
                  "recipient_map": {str(i + 1): r["id"] for i, r in enumerate(doc["recipients"])}, "envelope_status": status, "sent_at": state["now"]}
        return p.apply(state, "pm_jordan", action, trusted_provider=True)

    def event(self, state, event_id="provider-event-1", recipient=0, **fields):
        doc = self.doc(state)
        r = doc["recipients"][recipient]
        event = {"id": event_id, "project_id": "cedar_foods", "doc_id": "D05", "revision": doc["revision"],
                 "envelope_id": doc["envelope_id"], "actor_id": r["id"], "provider_recipient_id": str(recipient + 1),
                 "type": "recipient_signed", "occurred_at": state["now"], "text": "Verified provider recipient-completed receipt.",
                 "source_mode": "provider", "source_kind": "esign_webhook"}
        event.update(fields)
        return event

    def receive(self, state, event):
        return p.apply(state, "pm_jordan", {"type": "record_event", "project_id": "cedar_foods", "event": event}, trusted_provider=True)

    def test_seed_is_deterministic_twenty_per_project_and_pm_scoped(self):
        state = self.state()
        self.assertEqual(state, p.seed())
        jordan = p.view(state, "pm_jordan")
        casey = p.view(state, "pm_casey")
        self.assertEqual((len(jordan["projects"]), len(casey["projects"])), (8, 2))
        self.assertEqual((len(jordan["archives"]), len(casey["archives"])), (1, 1))
        self.assertTrue(all(len(x["documents"]) == 20 for x in state["projects"].values()))
        self.assertEqual({d["id"] for d in state["projects"]["harbor_components"]["documents"]}, {"D%02d" % n for n in range(1, 21)})
        self.assertEqual(len(jordan["action_queue"]), jordan["metrics"]["actionable_documents"])
        self.assertTrue(all(q["project_id"] in {x["id"] for x in jordan["projects"]} for q in jordan["action_queue"]))
        with self.assertRaises(DomainError):
            p.view(state, "pm_jordan", "pine_assembly")
        with self.assertRaises(DomainError):
            self.act(state, "record_email", project="pine_assembly", sender_id="anything", event_id="x", subject="x", text="x")
        with self.assertRaises(DomainError):
            p.view(state, "invented_pm")
        self.assertFalse(state["quarantine"])

    def test_portfolio_map_uses_scoped_city_anchors_without_mutating_saved_projects(self):
        state = self.state()
        before = deepcopy(state)
        for pm_id, count in (("pm_jordan", 8), ("pm_casey", 2)):
            portfolio = p.view(state, pm_id)
            self.assertEqual(len(portfolio["projects"]), count)
            for summary in portfolio["projects"] + portfolio["archives"]:
                geo = summary["geography"]
                self.assertEqual(summary["site"], geo["city"] + ", " + geo["state"])
                self.assertTrue(geo["approximate"])
                self.assertTrue(24 < geo["lat"] < 50 and -125 < geo["lng"] < -66)
                self.assertEqual(summary["pm_id"], pm_id)
        self.assertEqual(state, before)
        self.assertIsNone(p.geography({"id": "unknown"})["lat"])

    def test_all_twelve_project_briefs_are_scoped_and_consistent_with_project_dates(self):
        state = self.state()
        before = deepcopy(state)
        seen = set()
        for pm_id in ("pm_jordan", "pm_casey"):
            portfolio = p.view(state, pm_id)
            for archived, summaries in ((False, portfolio["projects"]), (True, portfolio["archives"])):
                for summary in summaries:
                    with self.subTest(project=summary["id"]):
                        seen.add(summary["id"])
                        self.assertEqual(summary["pm_id"], pm_id)
                        profile = summary["profile"]
                        selected = p.view(state, pm_id, summary["id"])["selected_project"]
                        self.assertEqual(selected["profile"], profile)
                        self.assertTrue(profile["industry"] and profile["scope"])
                        self.assertGreater(profile["system_power_kw"], 0)
                        self.assertGreaterEqual(profile["system_energy_kwh"], profile["system_power_kw"])
                        self.assertGreater(profile["project_budget_usd"], 0)
                        self.assertLess(profile["contract_date"], profile["target_handover_date"])
                        self.assertLessEqual(profile["contract_date"], state["now"][:10])
                        self.assertEqual(profile["target_handover_date"] <= state["now"][:10], archived)
                        self.assertTrue(profile["site_constraints"])
                        self.assertIsNone(profile["utility"])
                        self.assertEqual(profile["provenance"]["source_kind"], "authored_case_brief")
                        self.assertIn("not real client data", profile["provenance"]["note"])
        self.assertEqual(seen, set(state["projects"]))
        self.assertEqual(len(seen), 12)
        self.assertEqual(state, before)
        self.assertTrue(all("profile" not in project for project in state["projects"].values()))
        with self.assertRaises(DomainError):
            p.view(state, "pm_casey", "summit_precision")

    def test_delivery_case_profiles_reuse_original_sizes_baselines_and_targets(self):
        state = self.state()
        for delivery in p.delivery_project_catalog():
            profile = p.project_profile(state["projects"][delivery["id"]])
            self.assertEqual(profile["system_power_kw"], delivery["system"]["power_kw"])
            self.assertEqual(profile["system_energy_kwh"], delivery["system"]["capacity_kwh"])
            self.assertEqual(profile["project_budget_usd"], delivery["budget_baseline"])
            self.assertEqual(profile["target_handover_date"], delivery["target_handoff"])
            self.assertIn("projects.py:list_projects:" + delivery["id"], profile["provenance"]["source_refs"])

    def test_saved_profiles_override_defaults_without_rewriting_existing_records(self):
        state = self.state()
        saved = {"industry": "Recorded customer industry", "system_power_kw": 125,
                 "system_energy_kwh": None, "project_budget_usd": 0, "site_constraints": [],
                 "scope": "", "utility": "Customer-supplied utility name pending verification",
                 "provenance": {"source_kind": "recorded_brief", "source_refs": ["customer-brief-12"]},
                 "custom_notes": {"source": "retained record"}}
        state["projects"]["harbor_components"]["profile"] = deepcopy(saved)
        before = deepcopy(state)
        result = p.view(state, "pm_jordan", "harbor_components")
        profile = result["selected_project"]["profile"]
        for field, value in saved.items():
            self.assertEqual(profile[field], value)
        self.assertEqual(profile["contract_date"], "2026-08-17")
        self.assertEqual(next(x for x in result["projects"] if x["id"] == "harbor_components")["profile"], profile)
        profile["site_constraints"].append("Client-only edit")
        profile["custom_notes"]["source"] = "Client-only edit"
        profile["provenance"]["source_refs"].append("Client-only edit")
        self.assertEqual(state, before)
        self.assertEqual(p.project_profile(state["projects"]["harbor_components"])["site_constraints"], [])
        untouched = p.project_profile(state["projects"]["summit_precision"])
        untouched["site_constraints"].clear()
        self.assertTrue(p.project_profile(state["projects"]["summit_precision"])["site_constraints"])

    def test_first_signature_is_not_document_completion_and_current_all_required(self):
        state = self.state()
        doc = self.doc(state)
        self.assertEqual(doc["status"], "partially_signed")
        self.assertEqual([r["status"] for r in doc["recipients"]], ["signed", "pending"])
        before = deepcopy(state)
        state = self.complete(state, "cedar_foods", "D05")
        self.assertEqual(self.doc(state)["status"], "completed")
        self.assertEqual(len([h for h in state["projects"]["cedar_foods"]["signed_history"] if h["doc_id"] == "D05"]), 2)
        self.assertEqual(before, self.opening)
        self.assertNotIn("gates", state)
        self.assertNotIn("tasks", state["projects"]["cedar_foods"])

    def test_dependencies_bind_exact_revision_and_rework_preserves_signed_history(self):
        state = self.complete(self.state(), "cedar_foods", "D05")
        history = deepcopy(state["projects"]["cedar_foods"]["signed_history"])
        state = self.act(state, "revise_document", doc="D04", reason="Engineer corrected the issued design scope.")
        projected = p.view(state, "pm_jordan", "cedar_foods")["selected_project"]
        dependent = next(d for d in projected["documents"] if d["id"] == "D05")
        self.assertEqual(dependent["status"], "blocked")
        self.assertEqual(dependent["lifecycle_status"], "completed")
        self.assertEqual(dependent["prerequisites"][0]["required_revision"], 1)
        self.assertEqual(dependent["prerequisites"][0]["current_revision"], 2)
        state = self.complete(state, "cedar_foods", "D04")
        self.assertEqual(p._status(state["projects"]["cedar_foods"], self.doc(state)), "blocked")
        state = self.act(state, "revise_document", reason="Revalidate customer acceptance against design revision 2.")
        self.assertEqual(self.doc(state)["revisions"][0]["status"], "completed")
        state = self.complete(state, "cedar_foods", "D05")
        self.assertEqual(self.doc(state)["dependency_revisions"], {"D04": 2})
        self.assertEqual(state["projects"]["cedar_foods"]["signed_history"][:len(history)], history)

    def test_downstream_rework_counts_distinguish_blocked_overdue_from_actionable_queue(self):
        state = self.act(self.state(), "revise_document", project="riverbend_logistics", doc="D04",
                         reason="Changed issued design requires downstream records to be revalidated.")
        result = p.view(state, "pm_jordan", "riverbend_logistics")
        metrics = result["metrics"]
        overdue_queue = [a for a in result["action_queue"] if p._dt(a["due_at"]) < p._dt(result["now"])]
        self.assertEqual(metrics["overdue_count"], 18)
        self.assertEqual(metrics["actionable_overdue_count"], len(overdue_queue))
        self.assertEqual(metrics["actionable_overdue_count"], 5)
        self.assertEqual(metrics["blocked_overdue_count"], 13)
        self.assertEqual(metrics["overdue_count"], metrics["actionable_overdue_count"] + metrics["blocked_overdue_count"])
        detail = result["selected_project"]
        self.assertEqual(detail["completed_count"], 3)
        self.assertEqual(detail["overdue_count"], detail["actionable_overdue_count"] + detail["blocked_overdue_count"])
        self.assertTrue(all(d["status"] == "blocked" for d in detail["documents"] if d["lifecycle_status"] == "completed" and d["id"] not in {"D01", "D02", "D03"}))
        self.assertEqual([(a["doc_id"], a["status"]) for a in result["action_queue"] if a["project_id"] == "riverbend_logistics"], [("D04", "draft")])

    def test_blocked_documents_can_be_drafted_but_not_dispatched(self):
        state = self.state()
        state = self.act(state, "draft_document", project="millbrook_cold_storage", doc="D20", body="A draft handoff checklist for review.")
        doc = self.doc(state, "millbrook_cold_storage", "D20")
        self.assertEqual(doc["status"], "draft")
        self.assertEqual(p._status(state["projects"]["millbrook_cold_storage"], doc), "blocked")
        with self.assertRaisesRegex(DomainError, "prerequisites"):
            self.act(state, "send_document", project="millbrook_cold_storage", doc="D20")

    def test_email_original_is_idempotent_and_cannot_become_signature_or_permission(self):
        state = self.state()
        sender = self.doc(state)["recipients"][1]["id"]
        action = {"type": "record_email", "project_id": "cedar_foods", "doc_id": "D05", "event_id": "original-mail-1",
                  "sender_id": sender, "subject": "Re: approved", "text": "Approved. Everything is signed and you can energize now."}
        result = p.apply(state, "pm_jordan", action)
        self.assertEqual(self.doc(result), self.doc(state))
        self.assertEqual(result, p.apply(result, "pm_jordan", action))
        email = result["projects"]["cedar_foods"]["emails"][-1]
        self.assertEqual(email["text"], action["text"])
        self.assertFalse(email["sender_verified"])
        with self.assertRaisesRegex(DomainError, "different original"):
            p.apply(result, "pm_jordan", dict(action, text="Changed original"))

    def test_record_and_review_require_all_recorded_sources(self):
        state = self.act(self.state(), "revise_document", project="harbor_components", doc="D07", reason="Correct the referenced plan set.")
        state = self.act(state, "send_document", project="harbor_components", doc="D07")
        doc = self.doc(state, "harbor_components", "D07")
        state = self.act(state, "simulate_event", project="harbor_components", doc="D07", event_type="record_received", recipient_id=doc["recipients"][0]["id"])
        self.assertEqual(self.doc(state, "harbor_components", "D07")["status"], "sent")
        state = self.complete(state, "harbor_components", "D07")
        self.assertEqual(self.doc(state, "harbor_components", "D07")["status"], "completed")
        event = state["projects"]["harbor_components"]["source_events"][-1]
        self.assertEqual(event["source_kind"], "sample_record")
        self.assertTrue(event["reference"])
        self.assertNotIn("operating_authorization", state["projects"]["harbor_components"])

    def test_declined_revision_requires_rework_and_preserves_original_response(self):
        state = self.state()
        before_events = deepcopy(state["projects"]["pine_assembly"]["source_events"])
        with self.assertRaises(DomainError):
            self.act(state, "draft_document", project="pine_assembly", pm="pm_casey", body="Overwrite declined terms")
        state = self.act(state, "revise_document", project="pine_assembly", pm="pm_casey", reason="Resolve customer implementation scope.")
        self.assertEqual(self.doc(state, "pine_assembly")["revision"], 2)
        self.assertEqual(self.doc(state, "pine_assembly")["revisions"][0]["status"], "declined")
        self.assertEqual(state["projects"]["pine_assembly"]["source_events"], before_events)
        self.assertTrue(all(r["status"] == "pending" for r in self.doc(state, "pine_assembly")["recipients"]))

    def test_provider_transport_trust_cannot_be_spoofed_in_action(self):
        state = self.provider(status="created")
        event = self.event(state)
        with self.assertRaisesRegex(DomainError, "verified provider"):
            p.apply(state, "pm_jordan", {"type": "record_event", "project_id": "cedar_foods", "event": event, "trusted_provider": True})
        with self.assertRaisesRegex(DomainError, "provider-managed"):
            self.act(state, "simulate_event", event_type="recipient_signed")
        with self.assertRaisesRegex(DomainError, "provider send"):
            self.act(state, "send_document")
        with self.assertRaisesRegex(DomainError, "provider-bound"):
            self.act(state, "draft_document", body="Silent edit after provider draft created")
        self.assertEqual(self.doc(state)["status"], "draft")

    def test_provider_all_signatures_still_require_verified_envelope_completion(self):
        state = self.provider()
        state = self.receive(state, self.event(state, "provider-recipient-1"))
        self.assertEqual(self.doc(state)["status"], "partially_signed")
        state = self.receive(state, self.event(state, "provider-recipient-2", recipient=1))
        self.assertEqual(self.doc(state)["status"], "partially_signed")
        self.assertEqual(self.doc(state)["envelope_status"], "sent")
        completion = self.event(state, "provider-envelope-1", type="envelope_completed", actor_id=self.doc(state)["owner_id"])
        state = self.receive(state, completion)
        self.assertEqual(self.doc(state)["status"], "completed")
        self.assertEqual(state, self.receive(state, completion))

    def test_out_of_order_envelope_event_quarantines_without_fabricating_missing_signatures(self):
        state = self.provider()
        event = self.event(state, type="envelope_completed", actor_id=self.doc(state)["owner_id"])
        state = self.receive(state, event)
        self.assertEqual(self.doc(state)["status"], "sent")
        self.assertEqual(len(state["quarantine"]), 1)
        self.assertIn("missing individual", state["quarantine"][0]["reason"])
        self.assertTrue(all(r["status"] == "pending" for r in self.doc(state)["recipients"]))
        self.assertEqual(state, self.receive(state, event))

    def test_cross_project_wrong_revision_and_pre_dispatch_events_are_quarantined(self):
        for fields, fragment in (({"project_id": "pine_assembly"}, "project"), ({"doc_id": "D99"}, "unknown document"),
                                 ({"revision": 1}, "revision"), ({"envelope_id": "other"}, "envelope"),
                                 ({"occurred_at": "2026-11-06T10:00:00-05:00"}, "predates"),
                                 ({"provider_recipient_id": "999"}, "mapping")):
            state = self.provider()
            original = deepcopy(self.doc(state))
            result = self.receive(state, self.event(state, **fields))
            self.assertEqual(self.doc(result), original)
            self.assertIn(fragment, result["quarantine"][-1]["reason"])
            self.assertEqual(result["projects"]["pine_assembly"], state["projects"]["pine_assembly"])

    def test_duplicate_provider_event_id_changed_content_is_quarantined(self):
        state = self.provider()
        event = self.event(state)
        state = self.receive(state, event)
        self.assertEqual(state, self.receive(state, event))
        result = self.receive(state, dict(event, type="recipient_declined"))
        self.assertEqual(self.doc(result)["status"], "partially_signed")
        self.assertIn("reused", result["quarantine"][-1]["reason"])

    def test_live_provider_observations_are_read_only_and_mapping_scoped(self):
        state = self.provider(status="created")
        doc = deepcopy(self.doc(state))
        observation = {"project_id": "cedar_foods", "document_id": "D05", "document_revision": str(doc["revision"]),
                       "envelope_id": doc["envelope_id"], "envelope_status": "completed", "recipients": [], "envelope_completed": True}
        action = {"type": "record_provider_observation", "project_id": "cedar_foods", "doc_id": "D05", "observation": observation}
        state = p.apply(state, "pm_jordan", action, trusted_provider=True)
        self.assertEqual(self.doc(state)["status"], "draft")
        self.assertEqual(self.doc(state)["envelope_status"], "created")
        self.assertTrue(self.doc(state)["provider_observations"][-1]["needs_review"])
        with self.assertRaises(DomainError):
            p.apply(state, "pm_jordan", dict(action, observation=dict(observation, document_revision="1")), trusted_provider=True)
        self.assertEqual(state, p.apply(state, "pm_jordan", dict(action, observation=dict(observation, observed_at="2026-11-07T11:00:00-05:00")), trusted_provider=True))

    def test_verified_dispatch_retains_provider_time_before_later_poll_and_signatures(self):
        state = self.provider(status="created")
        state["now"] = "2026-11-07T13:00:00-05:00"
        doc = self.doc(state)
        action = {"type": "record_provider_dispatch", "project_id": "cedar_foods", "doc_id": "D05", "revision": doc["revision"],
                  "envelope_id": doc["envelope_id"], "sent_at": "2026-11-07T10:30:00-05:00"}
        result = p.apply(state, "pm_jordan", action, trusted_provider=True)
        self.assertEqual(self.doc(result)["sent_at"], action["sent_at"])
        self.assertEqual(result, p.apply(result, "pm_jordan", action, trusted_provider=True))
        result = self.receive(result, self.event(result, occurred_at="2026-11-07T11:00:00-05:00"))
        self.assertEqual(self.doc(result)["status"], "partially_signed")
        self.assertFalse(result["quarantine"])
        with self.assertRaises(DomainError):
            p.apply(result, "pm_jordan", dict(action, sent_at="2026-11-07T12:00:00-05:00"), trusted_provider=True)

    def test_real_envelope_mapping_cannot_be_reused_on_another_revision(self):
        state = self.provider(status="created")
        state = self.act(state, "revise_document", reason="Prepare a corrected draft under a new envelope.")
        doc = self.doc(state)
        action = {"type": "bind_provider_envelope", "project_id": "cedar_foods", "doc_id": "D05", "provider": "docusign",
                  "envelope_id": "verified-test-envelope", "recipient_map": {str(i): r["id"] for i, r in enumerate(doc["recipients"])}}
        with self.assertRaisesRegex(DomainError, "already mapped"):
            p.apply(state, "pm_jordan", action, trusted_provider=True)

    def test_contact_edits_and_email_drafts_preserve_signed_originals(self):
        state = self.state()
        signature = deepcopy(state["projects"]["cedar_foods"]["signed_history"])
        recipient = self.doc(state)["recipients"][1]["id"]
        state = self.act(state, "configure_contact", stakeholder_id=recipient, email="teammate@example.com")
        state = self.act(state, "draft_email")
        draft = self.doc(state)["email_draft"]
        self.assertEqual(draft["to"], ["teammate@example.com"])
        self.assertEqual(draft["cc"], [])
        self.assertIn(draft["match_token"], draft["subject"])
        self.assertEqual(draft["match_token"], "EQORE-cedar_foods-D05-r1")
        self.assertNotIn(":", draft["match_token"])
        edited = self.act(state, "draft_email", subject="A shorter follow-up", body="Please review the current package.")
        self.assertIn("[EQORE-cedar_foods-D05-r1]", self.doc(edited)["email_draft"]["subject"])
        self.assertNotIn("https://", draft["body"])
        self.assertEqual(draft["mode"], "prepared")
        self.assertEqual(state["projects"]["cedar_foods"]["signed_history"], signature)
        self.assertEqual(self.doc(state)["status"], "partially_signed")

    def test_assistant_summary_is_separate_trusted_and_cannot_claim_missing_sources(self):
        state = self.state()
        source = state["projects"]["cedar_foods"]["emails"][0]["id"]
        action = {"type": "save_summary", "project_id": "cedar_foods", "doc_id": "D05", "summary": "One recipient remains outstanding.",
                  "source_ids": [source], "uncertainties": ["No response deadline confirmed by the recipient."]}
        with self.assertRaises(DomainError):
            p.apply(state, "pm_jordan", action)
        result = p.apply(state, "pm_jordan", action, trusted_assist=True)
        self.assertEqual(self.doc(result)["status"], self.doc(state)["status"])
        self.assertEqual(result["projects"]["cedar_foods"]["emails"], state["projects"]["cedar_foods"]["emails"])
        with self.assertRaises(DomainError):
            p.apply(state, "pm_jordan", dict(action, source_ids=["made-up-source"]), trusted_assist=True)

    def test_imported_email_retains_unknown_and_ambiguous_senders_without_acceptance(self):
        state = self.state()
        action = {"type": "import_provider_email", "project_id": "cedar_foods", "doc_id": "D05", "provider": "gmail",
                  "provider_message_id": "durable-mailbox-id", "from": "Outside reviewer <outside@example.com>",
                  "subject": "[EQORE:cedar_foods:D05:r1] Approval", "text": "Signed and approved for operation.", "occurred_at": p.NOW}
        with self.assertRaisesRegex(DomainError, "mailbox adapter"):
            p.apply(state, "pm_jordan", action)
        result = p.apply(state, "pm_jordan", action, trusted_provider=True)
        email = result["projects"]["cedar_foods"]["emails"][-1]
        self.assertEqual(email["original_from"], action["from"])
        self.assertEqual(email["sender_match"], "unknown")
        self.assertIsNone(email["matched_stakeholder_id"])
        self.assertFalse(email["sender_verified"])
        self.assertTrue(email["mailbox_retrieval_verified"])
        self.assertEqual(self.doc(result), self.doc(state))
        self.assertEqual(result, p.apply(result, "pm_jordan", action, trusted_provider=True))
        person = state["projects"]["cedar_foods"]["stakeholders"][0]
        matching = dict(action, provider_message_id="matched-message", **{"from": "PM <%s>" % person["email"]})
        result = p.apply(state, "pm_jordan", matching, trusted_provider=True)
        self.assertEqual(result["projects"]["cedar_foods"]["emails"][-1]["matched_stakeholder_id"], person["id"])
        self.assertFalse(result["projects"]["cedar_foods"]["emails"][-1]["sender_verified"])
        state["projects"]["cedar_foods"]["stakeholders"][1]["email"] = person["email"]
        result = p.apply(state, "pm_jordan", matching, trusted_provider=True)
        self.assertEqual(result["projects"]["cedar_foods"]["emails"][-1]["sender_match"], "ambiguous")
        self.assertIsNone(result["projects"]["cedar_foods"]["emails"][-1]["sender_id"])

    def test_archive_needs_complete_current_documents_and_explicit_closeout_and_is_read_only(self):
        state = self.state()
        with self.assertRaisesRegex(DomainError, "current paperwork"):
            self.act(state, "archive_project", attest_project_complete=True, attestation="Project complete.")
        state["projects"]["canal_metals"].update(status="active", closeout_attestation=None)
        with self.assertRaisesRegex(DomainError, "attestation"):
            self.act(state, "archive_project", project="canal_metals", attestation="Project is complete.")
        result = self.act(state, "archive_project", project="canal_metals", attest_project_complete=True,
                          attestation="I confirm physical delivery and customer closeout are complete and all current records are retained.")
        self.assertEqual(result["projects"]["canal_metals"]["status"], "archived")
        self.assertTrue(result["projects"]["canal_metals"]["closeout_attestation"]["project_complete"])
        with self.assertRaisesRegex(DomainError, "read-only"):
            self.act(result, "revise_document", project="canal_metals", doc="D01", reason="Try editing archive.")
        detail = p.view(result, "pm_jordan", "canal_metals")["selected_project"]
        self.assertFalse(detail["can_archive"])
        self.assertTrue(all(not d["allowed_actions"] for d in detail["documents"]))

    def test_failed_actions_are_atomic_and_actions_cannot_mutate_operational_state(self):
        state = self.state()
        before = deepcopy(state)
        with self.assertRaises(DomainError):
            self.act(state, "revise_document", reason="", body="Changed")
        self.assertEqual(state, before)
        with self.assertRaises(DomainError):
            self.act(state, "approve_and_commit", budget=1, gates={"utility": "approved"})
        self.assertEqual(state, before)
        projection = p.view(state, "pm_jordan", "cedar_foods")
        projection["selected_project"]["documents"][0]["body"] = "Edited public copy"
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
