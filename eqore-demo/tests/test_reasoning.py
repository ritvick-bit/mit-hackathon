"""Causal explanations must reflect observed facts and remain outside model prose."""
import copy
import unittest
from unittest.mock import patch

import engine
import llm
import reasoning
import scenarios
import projects


class ReasoningTests(unittest.TestCase):
    def delayed(self, case="delivery_delay"):
        state = scenarios.initial_state(case)
        return engine.apply_event(state, scenarios.next_event(case, 0, state))

    def proposed(self):
        state = self.delayed()
        return engine.apply_action(state, engine.recommend(state)["action"])

    def approved(self):
        state = self.proposed()
        proposal = state["proposals"][-1]
        return engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"],
                                          "status": "approved"}, actor_id=proposal["required_approver_id"])

    def test_approval_retains_original_schedule_cause_and_cost(self):
        state = self.proposed()
        decision = engine.recommend(state)
        self.assertEqual(decision["action_type"], "request_approval")
        self.assertIn("Nov 13", decision["why_now"])
        self.assertIn("Nov 12", decision["why_now"])
        self.assertIn("later than", decision["why_now"])
        self.assertIn("$1,200", decision["why_now"])
        self.assertIn("Jordan Lee", decision["why_now"])
        self.assertIn("Nov 17", decision["request"])
        self.assertEqual(decision["request"], decision["action"]["request"])
        self.assertEqual(decision["why_now"], decision["reasoning"]["summary"])
        self.assertTrue(reasoning.validate_reasoning(state, decision["reasoning"]))

    def test_slack_does_not_invent_a_schedule_conflict(self):
        state = self.delayed("delay_with_slack")
        analysis = engine.analyze(state)
        self.assertEqual(analysis["impacts"], [])
        for candidate in analysis["candidates"]:
            self.assertNotIn("later than", candidate["why_now"])
            self.assertNotEqual("schedule_feasibility_and_authorization", candidate["reasoning"]["constraint"]["id"])

    def test_committed_plan_does_not_claim_external_booking(self):
        state = self.approved()
        commit = engine.recommend(state)
        self.assertEqual(commit["action_type"], "commit_plan")
        self.assertIn("unchanged proposal is approved", commit["why_now"])
        state = engine.apply_action(state, commit["action"])
        booking = next(c for c in engine.analyze(state)["candidates"] if c["action_type"] == "confirm_booking")
        self.assertIn("external booking is required", booking["why_now"])
        self.assertEqual(booking["reasoning"]["constraint"]["id"], "external_booking_confirmation")
        self.assertIn("only after", booking["reasoning"]["expected_unlocks"][0])

    def test_gate_explanation_identifies_contact_scope_and_affected_work(self):
        state = scenarios.initial_state("utility_receipt")
        candidate = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("gate_id") == "utility_operate")
        self.assertIn("Utility operating authorization", candidate["why_now"])
        self.assertIn("Quinn Ellis", candidate["why_now"])
        self.assertIn("commissioning", candidate["why_now"])
        self.assertEqual(candidate["reasoning"]["constraint"]["id"], "scoped_gate_authority")

    def test_rejected_recovery_explains_why_resubmission_is_useless(self):
        state = self.proposed()
        proposal = state["proposals"][-1]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "rejected"}, actor_id="pm")
        decision = engine.recommend(state)
        self.assertEqual(decision["action"]["purpose"], "rejected_plan")
        self.assertIn("Nov 13", decision["why_now"])
        self.assertIn("rejected", decision["why_now"])
        self.assertIn("unchanged", decision["reasoning"]["consequence"])

    def test_no_feasible_schedule_names_conflict_without_inventing_slots(self):
        state = self.delayed()
        state["calendars"]["rigging_crew"] = []
        decision = engine.recommend(state)
        self.assertEqual(decision["action"].get("purpose"), "schedule_recovery")
        self.assertIn("Nov 13", decision["why_now"])
        self.assertIn("No feasible recovery", decision["why_now"])
        self.assertNotIn("Nov 17", decision["why_now"])

    def test_resource_conflict_explains_named_unavailable_window(self):
        state = scenarios.initial_state("delivery_delay")
        state["calendars"]["rigging_crew"] = []
        decision = engine.recommend(state)
        self.assertIn("rigging crew", decision["why_now"])
        self.assertIn("Nov 12", decision["why_now"])
        self.assertNotIn("delivery estimate is later", decision["why_now"])

    def test_overdue_response_references_actual_deadline(self):
        state = scenarios.initial_state("customer_nonresponse")
        gate_request = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("gate_id") == "customer_window")
        state = engine.apply_action(state, gate_request["action"])
        state = engine.apply_event(state, {"id": "CLOCK_FOR_TEST", "type": "clock_advance", "at": "2026-11-20T09:00:00-05:00"})
        escalation = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("purpose") == "escalation")
        self.assertIn("response deadline", escalation["why_now"])
        self.assertEqual(escalation["reasoning"]["constraint"]["id"], "overdue_response_escalation")
        self.assertTrue(any(f["ref"].endswith("/due_at") for f in escalation["reasoning"]["facts"]))

    def test_completion_request_distinguishes_ready_from_done(self):
        state = scenarios.initial_state("delivery_delay")
        decision = engine.recommend(state)
        self.assertEqual(decision["action"].get("purpose"), "task_completion")
        self.assertIn("no accepted completion record", decision["why_now"])
        self.assertIn("ready task is not a completed task", decision["reasoning"]["constraint"]["description"])

    def test_every_candidate_has_complete_resolvable_public_record(self):
        for meta in scenarios.list_scenarios():
            state = scenarios.initial_state(meta["id"])
            for decision in engine.analyze(state)["candidates"]:
                with self.subTest(case=meta["id"], action=decision["action_type"]):
                    record = decision["reasoning"]
                    self.assertTrue(record["facts"])
                    self.assertTrue(record["constraint"]["description"])
                    self.assertTrue(record["consequence"])
                    self.assertTrue(record["authorized_action"]["description"])
                    self.assertTrue(record["uncertainties"])
                    self.assertTrue(record["reconsider_when"])
                    reasoning.validate_reasoning(state, record)

    def test_unversioned_fact_change_invalidates_saved_reasoning(self):
        state = self.proposed()
        record = engine.recommend(state)["reasoning"]
        state["project"]["delivery_eta"] = "2026-11-11T09:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "stale"):
            reasoning.validate_reasoning(state, record)

    def test_unknown_and_modified_fact_references_are_rejected(self):
        state = self.proposed()
        record = engine.recommend(state)["reasoning"]
        with self.assertRaisesRegex(ValueError, "unknown decision fact"):
            reasoning.validate_reasoning(state, record, ["F999"])
        modified = copy.deepcopy(record)
        modified["facts"][0]["value"] = "made up"
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            reasoning.validate_reasoning(state, modified)
        modified = copy.deepcopy(record)
        modified["evidence_ids"].append("DOES_NOT_EXIST")
        with self.assertRaisesRegex(ValueError, "Unknown decision evidence"):
            reasoning.validate_reasoning(state, modified)

    def _model(self, role, instruction, context, schema):
        output = {k: [] if v["type"] == "array" else "Invented Nov 1 $999,999 approval by a stranger" for k, v in schema["properties"].items()}
        if "candidate_id" in output:
            candidate = context["permitted_candidates"][0]
            output.update(candidate_id=candidate["candidate_id"], supporting_fact_ids=[candidate["reasoning"]["facts"][0]["id"]], priority_basis=["downstream_work"])
        return {"role": role, "output": output}

    def test_model_prose_cannot_overwrite_action_dates_cost_or_authority(self):
        state = self.proposed()
        canonical = engine.recommend(state)
        with patch("llm._call", side_effect=self._model):
            actual = llm.decide(state)
        for field in ("why_now", "title", "request", "authority", "action", "reasoning", "unlocks"):
            self.assertEqual(actual[field], canonical[field], field)
        self.assertNotIn("999,999", actual["model_judgment"]["summary"])
        self.assertEqual(actual["model_judgment"]["priority_basis"], ["downstream_work"])

    def test_model_unknown_fact_selection_is_rejected(self):
        def unknown(role, instruction, context, schema):
            result = self._model(role, instruction, context, schema)
            if role == "Coordinator":
                result["output"]["supporting_fact_ids"] = ["F999"]
            return result
        with patch("llm._call", side_effect=unknown), self.assertRaisesRegex(llm.ModelError, "unknown decision fact"):
            llm.decide(self.proposed())

    def test_alert_does_not_bypass_gate_prerequisite_work(self):
        state = scenarios.initial_state("delivery_delay")
        state["alerts"].append({"id": "FUTURE_GATE", "gate_id": "field_verified", "resolver_id": "verifier",
                                "title": "Future inspection needs correction", "resolved": False})
        self.assertFalse(any(c["action"].get("gate_id") == "field_verified" for c in engine.analyze(state)["candidates"]))

    def test_execution_receipt_gates_work_but_does_not_prevent_future_plan(self):
        state = self.approved()
        state["gates"]["delivery_receipt"] = {"id": "delivery_receipt", "status": "pending", "execution_only": True}
        next(t for t in state["tasks"] if t["id"] == "t_unload")["required_gates"].append("delivery_receipt")
        state = engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})
        self.assertEqual(state["proposals"][-1]["status"], "committed")
        with self.assertRaisesRegex(engine.DomainError, "gates are unresolved"):
            engine.apply_action(state, {"type": "complete_task", "task_id": "t_unload", "evidence_ids": []})

    def test_proposed_revision_does_not_imply_design_acceptance_for_early_work(self):
        state = projects.initial_state("millbrook_cold_storage")
        self.assertEqual(state["gates"]["design"]["status"], "pending")
        survey = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("task_id") == "t_survey")
        self.assertIn("scoped to recorded revision V3", survey["request"])
        self.assertIn("acceptance for this revision is not yet recorded", survey["request"])
        self.assertNotIn("current approved design", survey["request"])
        facts = {f["ref"]: f for f in survey["reasoning"]["facts"]}
        self.assertEqual(facts["/project/design_revision"]["label"], "Recorded design revision")
        self.assertEqual(facts["/gates/design/status"]["value"], "pending")
        self.assertIn("does not establish an issued or approved design", " ".join(survey["reasoning"]["uncertainties"]))
        self.assertFalse(any(c["action"].get("task_id") == "t_electrical" for c in engine.analyze(state)["candidates"]))

    def test_document_issued_title_does_not_override_pending_or_stale_acceptance(self):
        state = projects.initial_state("millbrook_cold_storage")
        next(e for e in state["evidence"] if e["id"] == "DESIGN_V3").update(title="Issued design V3", body="Issued by an email sender; review status is still separate.")
        for status, revision in (("pending", "V3"), ("approved", "V2")):
            with self.subTest(status=status, revision=revision):
                state["gates"]["design"].update(status=status, design_revision=revision)
                survey = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("task_id") == "t_survey")
                self.assertIn("acceptance for this revision is not yet recorded", survey["request"])
                self.assertNotIn("Current issued design", str(survey["reasoning"]))

    def test_current_scoped_acceptance_is_described_separately_from_revision(self):
        state = scenarios.initial_state("delivery_delay")
        self.assertEqual(state["gates"]["design"]["status"], "approved")
        work = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("task_id") == "t_unload")
        self.assertIn("scoped to recorded revision V3", work["request"])
        self.assertIn("Design acceptance for this revision is recorded", work["request"])
        facts = {f["ref"]: f for f in work["reasoning"]["facts"]}
        self.assertEqual(facts["/project/design_revision"]["label"], "Recorded design revision")
        self.assertEqual(facts["/gates/design/status"]["value"], "approved")

    def test_design_acceptance_claim_requires_authorized_current_scoped_evidence(self):
        for corruption in ("wrong_project", "wrong_revision", "wrong_issuer", "unverified", "receipt"):
            with self.subTest(corruption=corruption):
                state = scenarios.initial_state("delivery_delay")
                record = next(e for e in state["evidence"] if e["id"] in state["gates"]["design"]["evidence_ids"])
                if corruption == "wrong_project":
                    record["project_id"] = "OTHER_PROJECT"
                elif corruption == "wrong_revision":
                    record["design_revision"] = "V2"
                elif corruption == "wrong_issuer":
                    record["issuer_id"] = "vendor"
                elif corruption == "unverified":
                    record["verified"] = False
                else:
                    record["kind"] = "receipt"
                self.assertFalse(reasoning.design_acceptance_recorded(state))
                work = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("task_id") == "t_unload")
                self.assertIn("acceptance for this revision is not yet recorded", work["request"])


if __name__ == "__main__":
    unittest.main()
