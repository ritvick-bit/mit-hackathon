"""Scoped rejection/retest regressions against actual public engine operations."""
import copy
from datetime import datetime, timedelta
import unittest

import engine
import evaluation
import reasoning
import scenarios


class ReworkTests(unittest.TestCase):
    def finish(self, state, limit=100):
        for _ in range(limit):
            if engine.project_complete(state):
                return state
            decision = engine.recommend(state)
            state = engine.apply_action(state, decision["action"])
            for request in list(state["requests"]):
                if request.get("status") not in engine.OPEN_REQUEST_STATUSES:
                    continue
                response = scenarios.actor_response(state, request)
                if response:
                    state = engine.apply_event(state, response)
        self.fail("Fixture did not reach current evidenced handoff")

    def completed(self):
        return self.finish(scenarios.initial_state("normal_progress"))

    def evidence(self, state, identity, actor, kind="review", **extra):
        item = {"id": identity, "issuer_id": actor, "project_id": state["project"]["id"],
                "design_revision": state["project"]["design_revision"], "verified": True, "kind": kind,
                "received_at": state["project"]["now"], "effective_at": state["project"]["now"],
                "body": "Synthetic scoped review record"}
        item.update(extra)
        return item

    def fault(self, state, identity="NETWORK_FAILURE", kind="commissioning_fault"):
        at = (datetime.fromisoformat(state["project"]["now"]) + timedelta(hours=1)).isoformat()
        return {"id": identity, "type": kind, "at": at, "gate_id": "network", "status": "blocked", "issuer_id": "it",
                "summary": "Previously accepted controls route no longer responds", "return_phase": "commissioning",
                "evidence": self.evidence(state, identity + "_DOC", "it", "network", effective_at=at, received_at=at)}

    def returned(self, state, **extra):
        event = {"id": "RETURNED_PERMIT", "type": "review_returned", "gate_id": "permit", "issuer_id": "inspector",
                 "correction_owner_id": "engineer", "return_phase": "site_design", "affected_task_ids": ["t_permit"],
                 "reason": "The amendment package omits the marked equipment-clearance detail",
                 "required_artifact": "A corrected drawing index and response to the returned comment",
                 "evidence": self.evidence(state, "RETURN_DOC", "inspector", "review_return")}
        event.update(extra)
        return event

    def correction(self, state):
        decision = engine.recommend(state)
        self.assertEqual("rework_correction", decision["action"].get("purpose"))
        reasoning.validate_reasoning(state, decision["reasoning"])
        state = engine.apply_action(state, decision["action"])
        request = state["requests"][-1]
        event = {"id": "CORRECTION_REPLY", "type": "request_response", "request_id": request["id"], "issuer_id": "engineer", "status": "corrected",
                 "evidence": self.evidence(state, "CORRECTION_DOC", "engineer", "correction_record", rework_id=request["rework_id"])}
        return state, event

    def test_withdrawal_after_handoff_reopens_acceptance_without_erasing_installation(self):
        before = self.completed()
        state = engine.apply_event(before, self.fault(before, kind="gate_update"))
        tasks = {t["id"]: t for t in state["tasks"]}
        prior = {t["id"]: t for t in before["tasks"]}
        self.assertEqual("active", state["project"]["status"])
        self.assertFalse(engine.project_complete(state))
        self.assertFalse(evaluation._is_done(state))
        self.assertNotEqual("Deployment handoff is complete", engine.recommend(state)["title"])
        for tid in ("t_unload", "t_electrical", "t_site", "t_verify"):
            self.assertEqual(prior[tid], tasks[tid])
        for tid in ("t_commission", "t_handoff"):
            self.assertEqual("planned", tasks[tid]["status"])
            self.assertEqual(prior[tid]["evidence_ids"], tasks[tid]["completion_history"][-1]["evidence_ids"])
        self.assertEqual("pending", state["gates"]["commissioned"]["status"])

    def test_network_repair_requires_separate_controls_retest_and_fresh_handoff(self):
        before = self.completed()
        state = engine.apply_event(before, self.fault(before))
        first = engine.recommend(state)
        self.assertEqual("it", first["action"]["recipient_id"])
        state = engine.apply_action(state, first["action"])
        state = engine.apply_event(state, scenarios.actor_response(state, state["requests"][-1]))
        self.assertEqual("approved", state["gates"]["network"]["status"])
        self.assertEqual("pending", state["gates"]["commissioned"]["status"])
        self.assertFalse(engine.project_complete(state))
        state = self.finish(state)
        self.assertEqual("resolved", state["rework"][-1]["status"])
        controls = [r for r in state["requests"] if r.get("recipient_id") == "controls" and r.get("rework_generation", 0) > 0]
        self.assertTrue(any(r.get("gate_id") == "commissioned" for r in controls))
        self.assertTrue(any(r.get("task_id") == "t_commission" for r in controls))
        self.assertEqual([], evaluation._invariants(before, state))

    def test_old_gate_and_completion_evidence_cannot_clear_new_cycle(self):
        before = self.completed()
        old_network = next(e for e in before["evidence"] if e["id"] in before["gates"]["network"]["evidence_ids"])
        commission = next(t for t in before["tasks"] if t["id"] == "t_commission")
        state = engine.apply_event(before, self.fault(before))
        with self.assertRaisesRegex(engine.DomainError, "fresh"):
            engine.apply_event(state, {"id": "REPLAY_APPROVAL", "type": "gate_update", "gate_id": "network", "status": "approved", "issuer_id": "it", "evidence": old_network})
        for gid, actor in (("network", "it"), ("commissioned", "controls")):
            state = engine.apply_event(state, {"id": "NEW_" + gid, "type": "gate_update", "gate_id": gid, "status": "approved", "issuer_id": actor,
                                              "evidence": self.evidence(state, "NEW_DOC_" + gid, actor, gid)})
        with self.assertRaisesRegex(engine.DomainError, "fresh"):
            engine.apply_action(state, {"type": "complete_task", "task_id": "t_commission", "evidence_ids": commission["evidence_ids"]})
        candidate = next(c for c in engine.analyze(state)["candidates"] if c["action"].get("task_id") == "t_commission")
        self.assertEqual("task_completion", candidate["action"]["purpose"])

    def test_late_response_to_superseded_request_is_rejected_atomically(self):
        state = self.completed()
        state = engine.apply_event(state, self.fault(state))
        state = engine.apply_action(state, engine.recommend(state)["action"])
        request = state["requests"][-1]
        response = scenarios.actor_response(state, request)
        state = engine.apply_event(state, self.fault(state, "SECOND_FAILURE"))
        original = copy.deepcopy(state)
        with self.assertRaisesRegex(engine.DomainError, "superseded"):
            engine.apply_event(state, response)
        self.assertEqual(original, state)

    def test_returned_review_routes_correction_before_separate_reapproval(self):
        before = self.completed()
        state = engine.apply_event(before, self.returned(before))
        self.assertEqual("correction_required", state["rework"][-1]["status"])
        self.assertEqual("site_design", state["rework"][-1]["return_phase"])
        with self.assertRaisesRegex(engine.DomainError, "correction"):
            engine.apply_event(state, {"id": "BYPASS", "type": "gate_update", "gate_id": "permit", "status": "approved", "issuer_id": "inspector",
                                      "evidence": self.evidence(state, "BYPASS_DOC", "inspector", "permit")})
        state, response = self.correction(state)
        state = engine.apply_event(state, response)
        self.assertEqual("awaiting_reapproval", state["rework"][-1]["status"])
        self.assertEqual("pending", state["gates"]["permit"]["status"])
        self.assertEqual(before["project"]["budget"], state["project"]["budget"])
        state = self.finish(state)
        self.assertEqual("resolved", state["rework"][-1]["status"])
        self.assertEqual("inspector", state["gates"]["permit"]["issuer_id"])
        self.assertTrue(state["rework"][-1]["correction_evidence_ids"])
        self.assertTrue(state["rework"][-1]["resolution_evidence_ids"])

    def test_correction_requires_named_owner_current_scope_and_actual_correction_record(self):
        state = self.completed()
        state = engine.apply_event(state, self.returned(state))
        state, response = self.correction(state)
        for changes in ({"issuer_id": "vendor"}, {"kind": "receipt"}, {"project_id": "OTHER"}, {"rework_id": "OTHER"}, {"effective_at": "2020-01-01T00:00:00-05:00"}):
            with self.subTest(changes=changes):
                bad = copy.deepcopy(response)
                bad["evidence"].update(changes)
                with self.assertRaises(engine.DomainError):
                    engine.apply_event(state, bad)

    def test_correction_record_is_not_a_separate_gate_acceptance(self):
        state = self.completed()
        state = engine.apply_event(state, self.returned(state, correction_owner_id="inspector"))
        state = engine.apply_action(state, engine.recommend(state)["action"])
        request = state["requests"][-1]
        evidence = self.evidence(state, "REVIEWER_CORRECTION", "inspector", "correction_record", rework_id=request["rework_id"])
        state = engine.apply_event(state, {"id": "CORRECTED", "type": "request_response", "request_id": request["id"], "issuer_id": "inspector", "status": "corrected", "evidence": evidence})
        with self.assertRaisesRegex(engine.DomainError, "separate approval"):
            engine.apply_event(state, {"id": "APPROVE_CORRECTION", "type": "gate_update", "gate_id": "permit", "status": "approved", "issuer_id": "inspector", "evidence": evidence})

    def test_unrelated_work_can_progress_while_correction_is_awaited(self):
        state = self.completed()
        state = engine.apply_event(state, self.returned(state))
        state["tasks"].append({"id": "independent", "title": "Prepare support-contact index", "status": "planned", "external": False,
                               "owner_id": "pm", "predecessors": [], "required_gates": [], "evidence_ids": []})
        state = engine.apply_action(state, engine.recommend(state)["action"])
        self.assertTrue(any(c["action"].get("task_id") == "independent" for c in engine.analyze(state)["candidates"]))

    def test_returned_review_cannot_be_invented_by_vendor_or_replayed_twice(self):
        before = self.completed()
        bad = self.returned(before, issuer_id="vendor", evidence=self.evidence(before, "BAD_RETURN", "vendor"))
        with self.assertRaisesRegex(engine.DomainError, "reviewer"):
            engine.apply_event(before, bad)
        event = self.returned(before)
        once = engine.apply_event(before, event)
        self.assertEqual(once, engine.apply_event(once, event))

    def test_design_revalidation_history_retains_prior_revision_and_authority_status(self):
        state = self.completed()
        event = {"id": "REVISION_V4", "type": "design_revision", "issuer_id": "engineer", "design_revision": "V4", "affected_gates": ["permit"],
                 "evidence": self.evidence(state, "ISSUED_V4", "engineer", "design", design_revision="V4")}
        state = engine.apply_event(state, event)
        permit = next(t for t in state["tasks"] if t["id"] == "t_permit")
        self.assertEqual("V3", permit["completion_history"][-1]["design_revision"])
        self.assertEqual("approved", state["gates"]["permit"]["acceptance_history"][-1]["status"])
        self.assertEqual("V3", state["gates"]["permit"]["acceptance_history"][-1]["design_revision"])
        self.assertEqual("V4", state["gates"]["utility_install"]["design_revision"])

    def test_current_evidence_and_authority_are_required_even_when_labels_say_complete(self):
        original = self.completed()
        for change in ("revoked_authority", "wrong_actor_scope", "missing_evidence", "old_revision", "future_evidence", "receipt", "correction_record", "cycle"):
            with self.subTest(change=change):
                state = copy.deepcopy(original)
                gate = state["gates"]["network"]
                evidence = next(e for e in state["evidence"] if e["id"] in gate["evidence_ids"])
                actor = next(p for p in state["stakeholders"] if p["id"] == "it")
                if change == "revoked_authority":
                    actor["can_approve"].remove("network")
                elif change == "wrong_actor_scope":
                    actor["project_ids"] = ["OTHER"]
                elif change == "missing_evidence":
                    gate["evidence_ids"] = []
                elif change == "old_revision":
                    evidence["design_revision"] = "V1"
                elif change == "future_evidence":
                    evidence["effective_at"] = "2099-01-01T00:00:00-05:00"
                elif change == "cycle":
                    gate["required_gates"] = ["commissioned"]
                else:
                    evidence["kind"] = change
                self.assertFalse(engine._gate_ready(state, "network"))
                self.assertFalse(engine._gate_ready(state, "commissioned"))
                self.assertFalse(engine.project_complete(state))
                task = next(t for t in state["tasks"] if t["id"] == "t_commission")
                task["status"] = "planned"
                with self.assertRaisesRegex(engine.DomainError, "gate"):
                    engine.apply_action(state, {"type": "complete_task", "task_id": task["id"], "evidence_ids": task["evidence_ids"]})


if __name__ == "__main__":
    unittest.main()
