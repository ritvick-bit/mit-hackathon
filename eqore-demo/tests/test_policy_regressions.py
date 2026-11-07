"""Regression checks for independently discovered CH03/CH09 failures."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

import dashboard
import engine
import scenarios


class PolicyRegressionTests(unittest.TestCase):
    def approved(self):
        state = scenarios.initial_state("delivery_delay")
        state = engine.apply_event(state, scenarios.next_event("delivery_delay", 0, state))
        state = engine.apply_action(state, engine.recommend(state)["action"])
        proposal = state["proposals"][-1]
        return engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id="pm")

    def permit_request(self):
        state = scenarios.initial_state("delivery_delay")
        state["gates"]["permit"].update(status="pending", evidence_ids=[], issuer_id=None)
        return engine.apply_action(state, {"type": "request_information", "purpose": "gate_resolution", "gate_id": "permit",
            "subject_id": "permit", "recipient_id": "inspector", "request": "Provide scoped permit outcome."})

    def at(self, state, hours=0, seconds=0):
        started = datetime.fromisoformat(state["requests"][0]["created_at"])
        now = (started + timedelta(hours=hours, seconds=seconds)).isoformat()
        return engine.apply_event(state, {"id": "clock-" + now, "type": "clock_advance", "at": now})

    def acknowledge(self, state, status="acknowledged", kind="acknowledgement"):
        request = state["requests"][0]
        return engine.apply_event(state, {"id": "ACK", "type": "request_response", "request_id": request["id"],
            "issuer_id": "inspector", "status": status,
            "evidence": {"id": "ACK_DOC", "title": "Package received", "kind": kind, "issuer_id": "inspector",
                         "project_id": state["project"]["id"], "design_revision": state["project"]["design_revision"],
                         "verified": True, "received_at": state["project"]["now"], "effective_at": state["project"]["now"]}})

    def permit_candidates(self, state):
        return [c for c in engine.analyze(state)["candidates"] if c["action"].get("gate_id") == "permit"]

    def test_revoked_approver_cannot_commit_or_transfer_historical_approval(self):
        state = self.approved()
        next(p for p in state["stakeholders"] if p["id"] == "pm")["can_approve"] = []
        before = deepcopy(state)
        with self.assertRaisesRegex(engine.DomainError, "current approval authority"):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})
        self.assertEqual(state, before)
        self.assertEqual(240000, state["project"]["budget"]["committed"])
        actions = engine.analyze(state)["candidates"]
        self.assertFalse(any(c["action_type"] == "commit_plan" for c in actions))
        review = next(c for c in actions if c["action"].get("purpose") == "authority_revalidation")
        self.assertIn("new authorized review", review["why_now"])
        self.assertEqual(state["proposals"][-1]["required_approver_id"], "pm")

    def test_lowered_cost_delegation_invalidates_commit_without_revision_change(self):
        state = self.approved()
        next(p for p in state["stakeholders"] if p["id"] == "pm")["approval_limit"] = 100
        with self.assertRaisesRegex(engine.DomainError, "delegation"):
            engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})

    def test_unchanged_delegation_still_allows_authorized_commit(self):
        state = self.approved()
        state = engine.apply_action(state, {"type": "commit_plan", "proposal_id": state["proposals"][-1]["id"]})
        self.assertEqual(241200, state["project"]["budget"]["committed"])

    def test_acknowledgement_is_visible_and_does_not_trigger_immediate_duplicate(self):
        state = self.acknowledge(self.permit_request())
        self.assertEqual(state["requests"][0]["status"], "acknowledged")
        self.assertEqual(self.permit_candidates(state), [])
        before = deepcopy(state)
        engine.recommend(state)
        self.assertEqual(state, before)
        row = next(b for b in dashboard.summarize(state)["bottlenecks"] if b.get("gate_id") == "permit")
        self.assertEqual(row["status"], "waiting")
        self.assertEqual(row["request_ids"], [state["requests"][0]["id"]])
        duplicate = {"type": "request_information", "purpose": "gate_resolution", "subject_id": "permit", "gate_id": "permit", "recipient_id": "inspector"}
        self.assertEqual(len(engine.apply_action(state, duplicate)["requests"]), 1)

    def test_receipt_labeled_answered_is_still_an_unresolved_acknowledgement(self):
        state = self.acknowledge(self.permit_request(), status="answered", kind="receipt")
        self.assertEqual(state["requests"][0]["status"], "acknowledged")
        self.assertEqual(state["requests"][0]["response_status"], "answered")
        self.assertNotEqual(state["gates"]["permit"]["status"], "approved")
        self.assertEqual(self.permit_candidates(state), [])

    def test_follow_up_at_24h_and_escalation_at_48h_are_bounded(self):
        state = self.acknowledge(self.permit_request())
        state = self.at(state, hours=24, seconds=-1)
        self.assertEqual(self.permit_candidates(state), [])
        state = self.at(state, hours=24)
        follow = self.permit_candidates(state)[0]
        self.assertEqual(follow["action"]["purpose"], "follow_up")
        self.assertEqual(follow["action"]["recipient_id"], "inspector")
        self.assertIn("24 hours after the original request", follow["why_now"])
        state = engine.apply_action(state, follow["action"])
        state = engine.apply_action(state, follow["action"])
        self.assertEqual(len(state["requests"]), 2)
        self.assertEqual(self.permit_candidates(state), [])
        state = self.at(state, hours=48, seconds=-1)
        self.assertEqual(self.permit_candidates(state), [])
        state = self.at(state, hours=48)
        escalation = self.permit_candidates(state)[0]
        self.assertEqual(escalation["action"]["purpose"], "escalation")
        self.assertEqual(escalation["action"]["recipient_id"], "pm")
        state = engine.apply_action(state, escalation["action"])
        state = engine.apply_action(state, escalation["action"])
        self.assertEqual(sum(r["recipient_id"] == "inspector" for r in state["requests"]), 2)
        self.assertEqual(sum(r["purpose"] == "escalation" for r in state["requests"]), 1)
        self.assertEqual(self.permit_candidates(state), [])

    def test_late_acknowledgement_does_not_restart_original_clock(self):
        state = self.at(self.permit_request(), hours=23)
        state = self.acknowledge(state)
        state = self.at(state, hours=24)
        self.assertEqual(self.permit_candidates(state)[0]["action"]["purpose"], "follow_up")

    def test_direct_action_cannot_bypass_followup_and_escalation_thresholds(self):
        state = self.acknowledge(self.permit_request())
        for purpose, recipient in (("follow_up", "inspector"), ("escalation", "pm")):
            with self.subTest(purpose=purpose), self.assertRaisesRegex(engine.DomainError, "interval has not elapsed"):
                engine.apply_action(state, {"type": "request_information", "purpose": purpose, "subject_id": "permit",
                    "gate_id": "permit", "recipient_id": recipient, "parent_request_id": state["requests"][0]["id"]})

    def test_unrelated_ready_work_remains_available_while_waiting(self):
        state = scenarios.initial_state("customer_nonresponse")
        state = engine.apply_action(state, engine.recommend(state)["action"])
        request = state["requests"][0]
        state = engine.apply_event(state, {"id": "OPS_ACK", "type": "request_response", "request_id": request["id"], "issuer_id": "ops", "status": "acknowledged"})
        decision = engine.recommend(state)
        self.assertEqual(decision["action"]["type"], "complete_task")
        self.assertEqual(decision["action"]["task_id"], "t_handoff_draft")


if __name__ == "__main__":
    unittest.main()
