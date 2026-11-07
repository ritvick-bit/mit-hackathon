"""Adversarial tool-boundary tests; these assert effects, not prose similarity."""
import copy
import unittest

import engine
import scenarios


class EngineTests(unittest.TestCase):
    def delayed(self, scenario="delivery_delay"):
        state = scenarios.initial_state(scenario)
        return engine.apply_event(state, scenarios.next_event(scenario, 0, state))

    def proposed(self, scenario="delivery_delay"):
        state = self.delayed(scenario)
        decision = engine.recommend(state)
        self.assertEqual("propose_plan", decision["action_type"])
        return engine.apply_action(state, decision["action"])

    def approved(self):
        state = self.proposed()
        proposal = state["proposals"][-1]
        return engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id=proposal["required_approver_id"])

    def evidence(self, state, identity="TEST_EVIDENCE", issuer="utility", kind="utility_operate", **extra):
        item = {"id": identity, "title": "Test evidence", "body": "Scoped synthetic record", "issuer_id": issuer,
                "project_id": state["project"]["id"], "design_revision": state["project"]["design_revision"],
                "effective_at": state["project"]["now"], "received_at": state["project"]["now"], "verified": True, "kind": kind}
        item.update(extra)
        return item

    def gate_event(self, state, **extra):
        event = {"id": "TEST_GATE", "type": "gate_update", "gate_id": "utility_operate", "status": "approved",
                 "issuer_id": "utility", "evidence": self.evidence(state)}
        event.update(extra)
        return event

    def test_delay_finds_feasible_windows_and_cost(self):
        state = self.delayed()
        option = engine.analyze(state)["schedule_options"][0]
        changes = {c["task_id"]: c["planned_start"] for c in option["changes"]}
        self.assertEqual("2026-11-17", changes["t_unload"][:10])
        self.assertEqual("2026-11-21", changes["t_electrical"][:10])
        self.assertEqual(1200, option["cost_delta"])

    def test_slack_delay_does_not_reschedule(self):
        state = self.delayed("delay_with_slack")
        self.assertEqual([], engine.analyze(state)["schedule_options"])
        self.assertNotEqual("propose_plan", engine.recommend(state)["action_type"])

    def test_other_project_resource_is_respected(self):
        state = self.delayed("shared_resource")
        changes = engine.analyze(state)["schedule_options"][0]["changes"]
        self.assertEqual("2026-11-19", next(c for c in changes if c["task_id"] == "t_unload")["planned_start"][:10])

    def test_original_state_never_mutated(self):
        state = self.delayed()
        original = copy.deepcopy(state)
        engine.apply_action(state, engine.recommend(state)["action"])
        self.assertEqual(original, state)

    def test_failed_commit_is_atomic(self):
        state = self.proposed()
        original = copy.deepcopy(state)
        with self.assertRaises(engine.DomainError):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})
        self.assertEqual(original, state)

    def test_action_cannot_impersonate_approver(self):
        state = self.proposed()
        with self.assertRaisesRegex(engine.DomainError, "authority"):
            engine.apply_action(state, {"type": "resolve_decision", "proposal_id": state["proposals"][-1]["id"], "status": "approved", "actor_id": "pm"})

    def test_approval_does_not_invalidate_its_proposal(self):
        state = self.proposed()
        revision = state["project"]["revision"]
        proposal = state["proposals"][-1]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id="pm")
        self.assertEqual(revision, state["project"]["revision"])
        self.assertEqual("approved", state["proposals"][-1]["status"])
        state = engine.apply_action(state, {"type": "commit_plan", "proposal_id": proposal["id"]})
        self.assertEqual("committed", state["proposals"][-1]["status"])
        self.assertEqual(241200, state["project"]["budget"]["committed"])

    def test_expensive_recovery_requires_commercial_authority(self):
        state = self.proposed("cost_approval")
        proposal = state["proposals"][-1]
        self.assertEqual("commercial", proposal["required_approver_id"])
        with self.assertRaises(engine.DomainError):
            engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id="pm")

    def test_understating_cost_cannot_bypass_delegation(self):
        state = self.delayed("cost_approval")
        action = engine.recommend(state)["action"]
        action["cost_delta"] = 0
        with self.assertRaisesRegex(engine.DomainError, "understates"):
            engine.apply_action(state, action)

    def test_changed_resource_invalidates_approval(self):
        state = self.approved()
        proposal_id = state["proposals"][-1]["id"]
        state = engine.apply_event(state, {"id": "WITHDRAW", "type": "resource_update", "resource": "rigging_crew", "windows": []})
        self.assertEqual("stale", state["proposals"][-1]["status"])
        with self.assertRaises(engine.DomainError):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": proposal_id})

    def test_commit_rechecks_constraints_even_if_revision_is_wrongly_unchanged(self):
        state = self.approved()
        state["calendars"]["rigging_crew"] = []
        with self.assertRaisesRegex(engine.DomainError, "revalidation"):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})

    def test_commit_rechecks_readiness_gates(self):
        state = self.approved()
        state["gates"]["customer_window"]["status"] = "pending"
        with self.assertRaisesRegex(engine.DomainError, "gate"):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})

    def test_duplicate_proposal_and_commit_are_idempotent(self):
        state = self.delayed()
        action = engine.recommend(state)["action"]
        state = engine.apply_action(engine.apply_action(state, action), action)
        self.assertEqual(1, len(state["proposals"]))
        identity = state["proposals"][-1]["id"]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": identity, "status": "approved"}, actor_id="pm")
        commit = {"type": "commit_plan", "proposal_id": identity}
        state = engine.apply_action(state, commit)
        once = copy.deepcopy(state)
        self.assertEqual(once, engine.apply_action(state, commit))

    def test_duplicate_event_has_no_extra_effect(self):
        state = scenarios.initial_state("duplicate_delivery")
        event = scenarios.next_event("duplicate_delivery", 0, state)
        state = engine.apply_event(state, event)
        self.assertEqual(state, engine.apply_event(state, event))

    def test_old_estimate_is_retained_without_reverting_eta(self):
        state = self.delayed("duplicate_delivery")
        old = scenarios.next_event("duplicate_delivery", 2, state)
        revision = state["project"]["revision"]
        state = engine.apply_event(state, old)
        self.assertEqual("2026-11-13", state["project"]["delivery_eta"][:10])
        self.assertEqual(revision, state["project"]["revision"])
        self.assertTrue(any(e["id"] == "DOC_EV_OLD" for e in state["evidence"]))

    def test_evidence_identity_cannot_be_overwritten(self):
        state = self.delayed()
        item = copy.deepcopy(state["evidence"][-1])
        item["body"] = "Altered content"
        with self.assertRaisesRegex(engine.DomainError, "immutable"):
            engine.apply_event(state, {"id": "NEW_EVENT", "type": "evidence", "evidence": item})

    def test_receipt_cannot_approve_operation(self):
        state = scenarios.initial_state("utility_receipt")
        event = self.gate_event(state, evidence=self.evidence(state, kind="receipt"))
        with self.assertRaisesRegex(engine.DomainError, "Receipt"):
            engine.apply_event(state, event)

    def test_other_project_document_cannot_approve(self):
        state = scenarios.initial_state("utility_receipt")
        event = self.gate_event(state, evidence=self.evidence(state, project_id="OTHER"))
        with self.assertRaisesRegex(engine.DomainError, "project and design"):
            engine.apply_event(state, event)

    def test_old_design_approval_cannot_clear_gate(self):
        state = scenarios.initial_state("utility_receipt")
        event = self.gate_event(state, evidence=self.evidence(state, design_revision="V2"))
        with self.assertRaises(engine.DomainError):
            engine.apply_event(state, event)

    def test_vendor_cannot_approve_utility_gate(self):
        state = scenarios.initial_state("utility_receipt")
        event = self.gate_event(state, issuer_id="vendor", evidence=self.evidence(state, issuer="vendor"))
        with self.assertRaisesRegex(engine.DomainError, "authority"):
            engine.apply_event(state, event)

    def test_evidence_issuer_must_match_approval_actor(self):
        state = scenarios.initial_state("utility_receipt")
        event = self.gate_event(state, evidence=self.evidence(state, issuer="vendor"))
        with self.assertRaisesRegex(engine.DomainError, "issuer"):
            engine.apply_event(state, event)

    def test_draft_design_does_not_replace_issued_design(self):
        state = scenarios.initial_state("normal_progress")
        event = {"id": "DRAFT", "type": "design_revision", "issuer_id": "engineer", "design_revision": "V4",
                 "evidence": self.evidence(state, issuer="engineer", kind="design", status="draft", design_revision="V4")}
        state = engine.apply_event(state, event)
        self.assertEqual("V3", state["project"]["design_revision"])
        self.assertEqual(1, state["project"]["revision"])

    def test_design_change_invalidates_only_evidenced_scope(self):
        state = scenarios.initial_state("design_revision")
        state = engine.apply_event(state, scenarios.next_event("design_revision", 0, state))
        self.assertEqual("V4", state["project"]["design_revision"])
        self.assertEqual("pending", state["gates"]["permit"]["status"])
        self.assertEqual("approved", state["gates"]["utility_install"]["status"])
        self.assertEqual("V4", state["gates"]["utility_install"]["design_revision"])

    def test_physical_completion_cannot_be_invented(self):
        state = scenarios.initial_state("delivery_delay")
        with self.assertRaisesRegex(engine.DomainError, "completion evidence"):
            engine.apply_action(state, {"type": "complete_task", "task_id": "t_unload", "evidence_ids": ["DESIGN_V3"]})

    def test_physical_completion_cannot_happen_before_work_window(self):
        state = scenarios.initial_state("delivery_delay")
        item = self.evidence(state, issuer="rigger", kind="task_completion", task_id="t_unload")
        event = {"id": "EARLY", "type": "task_completed", "task_id": "t_unload", "issuer_id": "rigger", "evidence": item}
        with self.assertRaisesRegex(engine.DomainError, "before"):
            engine.apply_event(state, event)

    def test_booking_is_a_request_until_counterpart_responds(self):
        state = self.approved()
        state = engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})
        action = engine.recommend(state)["action"]
        self.assertEqual("confirm_booking", action["type"])
        state = engine.apply_action(state, action)
        self.assertEqual("pending", state["bookings"][0]["status"])
        state = engine.apply_action(state, action)
        self.assertEqual(1, len(state["requests"]))
        response = scenarios.actor_response(state, state["requests"][-1])
        state = engine.apply_event(state, response)
        self.assertEqual("confirmed", state["bookings"][0]["status"])

    def test_request_cannot_be_answered_by_other_person(self):
        state = scenarios.initial_state("customer_nonresponse")
        state = engine.apply_action(state, engine.recommend(state)["action"])
        request = state["requests"][-1]
        with self.assertRaisesRegex(engine.DomainError, "recipient"):
            engine.apply_event(state, {"id": "WRONG_ACTOR", "type": "request_response", "request_id": request["id"], "issuer_id": "vendor", "status": "approved"})

    def test_no_feasible_window_escalates_without_fabricated_slot(self):
        state = self.delayed()
        state["calendars"]["rigging_crew"] = []
        decision = engine.recommend(state)
        self.assertEqual([], engine.analyze(state)["schedule_options"])
        self.assertEqual("schedule_recovery", decision["action"]["purpose"])

    def test_waiting_does_not_freeze_independent_digital_work(self):
        state = scenarios.initial_state("customer_nonresponse")
        state = engine.apply_action(state, engine.recommend(state)["action"])
        next_action = engine.recommend(state)["action"]
        self.assertEqual("complete_task", next_action["type"])
        self.assertEqual("t_handoff_draft", next_action["task_id"])

    def test_gate_request_waits_for_own_prerequisites(self):
        state = scenarios.initial_state("utility_receipt")
        actions = [d["action"] for d in engine.analyze(state)["candidates"]]
        self.assertFalse(any(a.get("gate_id") == "commissioned" for a in actions))

    def test_unknown_model_operation_is_rejected(self):
        with self.assertRaises(engine.DomainError):
            engine.apply_action(scenarios.initial_state("normal_progress"), {"type": "grant_all_permissions"})

    def test_rejected_proposal_cannot_commit(self):
        state = self.proposed()
        identity = state["proposals"][-1]["id"]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": identity, "status": "rejected"}, actor_id="pm")
        with self.assertRaises(engine.DomainError):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": identity})

    def test_rejected_plan_is_not_repeated_without_new_facts(self):
        state = self.delayed()
        original_action = engine.recommend(state)["action"]
        state = engine.apply_action(state, original_action)
        identity = state["proposals"][-1]["id"]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": identity, "status": "rejected"}, actor_id="pm")
        with self.assertRaisesRegex(engine.DomainError, "rejected"):
            engine.apply_action(state, original_action)
        decision = engine.recommend(state)
        self.assertEqual("request_review", decision["action_type"])
        self.assertEqual("rejected_plan", decision["action"]["purpose"])


if __name__ == "__main__":
    unittest.main()
