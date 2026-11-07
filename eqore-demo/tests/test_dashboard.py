"""Management view checks: root causes, ordering, money and known/unknown dates."""
from copy import deepcopy
import unittest

import dashboard
import engine
import scenarios


class DashboardTests(unittest.TestCase):
    def delayed(self):
        state = scenarios.initial_state("delivery_delay")
        return engine.apply_event(state, scenarios.next_event("delivery_delay", 0, state))

    def test_all_independent_roots_are_kept_and_dependents_not_duplicated(self):
        state = self.delayed()
        for gid in ("permit", "utility_install"):
            state["gates"][gid].update(status="pending", evidence_ids=[])
        state["calendars"]["electrical_crew"] = []
        view = dashboard.summarize(state)
        current = [b for b in view["bottlenecks"] if b["status"] != "upcoming"]
        ids = {b["id"] for b in current}
        self.assertTrue({"gate:permit", "gate:utility_install", "schedule:delivery", "schedule:resource:electrical_crew"}.issubset(ids))
        delivery = next(b for b in current if b["id"] == "schedule:delivery")
        self.assertIn("t_handoff", delivery["blocked_task_ids"])
        self.assertEqual(1, len([b for b in current if b["id"] == "schedule:delivery"]))
        self.assertFalse(any(b["id"] == "evidence:t_handoff" for b in current))
        self.assertGreater(next(b["score"] for b in current if b["id"] == "gate:permit"), delivery["score"])

    def test_future_prerequisites_are_visible_but_not_current_bottlenecks(self):
        state = scenarios.initial_state("normal_progress")
        view = dashboard.summarize(state)
        self.assertEqual(0, view["metrics"]["active_bottlenecks"])
        self.assertGreater(view["metrics"]["upcoming_prerequisites"], 0)
        self.assertTrue(all(b["status"] == "upcoming" for b in view["bottlenecks"]))
        self.assertTrue(all("action" not in b for b in view["bottlenecks"]))

    def test_alert_gate_and_pending_request_merge_into_one_cause(self):
        state = scenarios.initial_state("field_discrepancy")
        state = engine.apply_event(state, scenarios.next_event("field_discrepancy", 0, state))
        state = engine.apply_action(state, engine.recommend(state)["action"])
        view = dashboard.summarize(state)
        rows = [b for b in view["bottlenecks"] if b.get("gate_id") == "field_verified"]
        self.assertEqual(1, len(rows))
        self.assertEqual("waiting", rows[0]["status"])
        self.assertEqual(1, len(rows[0]["request_ids"]))
        self.assertFalse(any(b["id"].startswith("request:") for b in view["bottlenecks"]))

    def test_overdue_response_remains_visible_with_actionable_escalation(self):
        state = scenarios.initial_state("customer_nonresponse")
        action = next(c["action"] for c in engine.analyze(state)["candidates"] if c["action"].get("gate_id") == "customer_window")
        state = engine.apply_action(state, action)
        state["project"]["now"] = "2026-11-20T12:00:00-05:00"
        view = dashboard.summarize(state)
        row = next(b for b in view["bottlenecks"] if b["id"] == "gate:customer_window")
        self.assertTrue(row["overdue"])
        self.assertEqual("Urgent", row["priority_label"])
        self.assertEqual("escalation", row["action"]["purpose"])

    def test_every_exposed_action_is_an_engine_candidate_and_valid(self):
        for case in scenarios.list_scenarios():
            with self.subTest(case=case["id"]):
                state = scenarios.initial_state(case["id"])
                analysis = engine.analyze(state)
                actions = [c["action"] for c in analysis["candidates"]]
                before = deepcopy(state)
                view = dashboard.summarize(state, analysis)
                self.assertEqual(state, before)
                for row in view["bottlenecks"]:
                    if row.get("action"):
                        self.assertIn(row["action"], actions)
                        engine.apply_action(state, row["action"])

    def test_invalid_commit_candidate_is_not_offered(self):
        state = self.delayed()
        state = engine.apply_action(state, engine.recommend(state)["action"])
        proposal = state["proposals"][-1]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id="pm")
        state["gates"]["permit"]["status"] = "pending"
        view = dashboard.summarize(state)
        self.assertFalse(any(b.get("action", {}).get("type") == "commit_plan" for b in view["bottlenecks"]))

    def test_committed_finance_does_not_add_baseline_twice_or_stale_proposal(self):
        state = self.delayed()
        state["project"]["finance"] = {"as_of": state["project"]["now"], "lines": [
            {"id": "equipment", "category": "Equipment", "baseline": 200000, "committed": 200000, "actual": 100000},
            {"id": "labor", "category": "Labor", "baseline": 40000, "committed": 40000, "actual": 5000}]}
        state = engine.apply_action(state, engine.recommend(state)["action"])
        proposed = dashboard.summarize(state)["finance"]
        self.assertEqual(241200, proposed["estimated_total"])
        self.assertEqual(240000, proposed["committed_total"])
        proposal = state["proposals"][-1]
        state = engine.apply_action(state, {"type": "resolve_decision", "proposal_id": proposal["id"], "status": "approved"}, actor_id="pm")
        state = engine.apply_action(state, {"type": "commit_plan", "proposal_id": proposal["id"]})
        finance = dashboard.summarize(state)["finance"]
        self.assertEqual(241200, finance["committed_total"])
        self.assertEqual(241200, sum(l["committed"] for l in finance["lines"]))
        self.assertEqual(1200, finance["committed_change"])
        self.assertEqual(0, finance["proposed_change"])
        self.assertEqual(105000, finance["actual_total"])
        self.assertEqual(state["project"]["finance"]["as_of"], finance["actual_as_of"])
        state["project"]["budget"]["proposed"] = 99999
        self.assertEqual(0, dashboard.summarize(state)["finance"]["proposed_change"])

    def test_partial_or_missing_actuals_and_forecast_are_not_invented(self):
        state = scenarios.initial_state("normal_progress")
        state["project"]["finance"] = {"lines": [{"id": "a", "baseline": 10, "committed": 10, "actual": 5}, {"id": "b", "baseline": 20, "committed": 20}]}
        view = dashboard.summarize(state)
        self.assertIsNone(view["finance"]["actual_total"])
        self.assertIsNone(view["metrics"]["forecast_finish"])
        self.assertEqual("2026-11-25", view["metrics"]["planned_finish"][:10])
        self.assertEqual(0, view["metrics"]["planned_variance_days"])

    def test_no_arbitrary_limit_on_queue(self):
        state = scenarios.initial_state("normal_progress")
        for i in range(12):
            state["alerts"].append({"id": "issue-%s" % i, "title": "Distinct unresolved issue %s" % i, "resolver_id": "pm", "task_ids": ["t_contract"], "resolved": False})
        view = dashboard.summarize(state)
        self.assertEqual(12, len([r for r in view["bottlenecks"] if r["id"].startswith("alert:")]))
        self.assertEqual(list(range(1, len(view["bottlenecks"]) + 1)), [r["rank"] for r in view["bottlenecks"]])

    def test_authority_alert_does_not_invent_a_safety_priority(self):
        state = scenarios.initial_state("customer_nonresponse")
        state["alerts"].append({"id": "SHUTDOWN", "kind": "authority", "severity": "high", "title": "Shutdown authorization outstanding", "gate_id": "customer_window", "resolver_id": "ops", "task_ids": ["t_electrical"], "resolved": False})
        row = next(b for b in dashboard.summarize(state)["bottlenecks"] if b["id"] == "gate:customer_window")
        self.assertEqual("Required authority", row["category"])
        self.assertEqual("High", row["priority_label"])
        self.assertIn("base 850", row["ranking_reason"])

    def test_resource_contacts_distinguish_customer_authority_from_contractor(self):
        state = scenarios.initial_state("delivery_delay")
        resources = {r["id"]: r for r in dashboard.summarize(state)["resources"]}
        self.assertEqual(["ops"], resources["customer_access"]["owner_ids"])
        self.assertNotIn("electrician", resources["customer_access"]["owner_ids"])
        self.assertEqual(["electrician"], resources["electrical_crew"]["owner_ids"])
        self.assertEqual(["rigger"], resources["rigging_crew"]["owner_ids"])
        state["project"]["resource_owners"] = {"customer_access": ["facilities"]}
        resources = {r["id"]: r for r in dashboard.summarize(state)["resources"]}
        self.assertEqual(["facilities"], resources["customer_access"]["owner_ids"])
        self.assertEqual("ops", state["gates"]["customer_window"]["resolver_id"])

    def returned_review(self):
        state = scenarios.initial_state("delivery_delay")
        return engine.apply_event(state, {"id": "RETURNED_REVIEW", "type": "review_returned", "gate_id": "permit", "issuer_id": "inspector",
            "correction_owner_id": "engineer", "return_phase": "site_design", "affected_task_ids": ["t_permit"],
            "reason": "Amendment package omits the updated access detail", "required_artifact": "Corrected layout and comment-response index",
            "evidence": {"id": "RETURNED_DOC", "verified": True, "project_id": state["project"]["id"], "design_revision": state["project"]["design_revision"],
                         "issuer_id": "inspector", "kind": "review_return", "effective_at": state["project"]["now"]}})

    def test_returned_review_has_one_named_correction_root_before_reviewer_reapproval(self):
        state = self.returned_review()
        record = state["rework"][-1]
        rows = dashboard.summarize(state)["bottlenecks"]
        row = next(r for r in rows if r.get("rework_id") == record["id"])
        self.assertEqual("engineer", row["resolver_id"])
        self.assertEqual("rework_correction", row["action"]["purpose"])
        self.assertEqual("site_design", row["return_phase"])
        self.assertIn("Corrected layout", row["next_step"])
        self.assertFalse(any(r.get("gate_id") in record["gate_ids"] for r in rows))
        state = engine.apply_action(state, row["action"])
        request = state["requests"][-1]
        rows = dashboard.summarize(state)["bottlenecks"]
        waiting = next(r for r in rows if r.get("rework_id") == record["id"])
        self.assertEqual("waiting", waiting["status"])
        self.assertNotIn("action", waiting)
        self.assertEqual([request["id"]], waiting["request_ids"])
        self.assertFalse(any(r["id"] == "request:" + record["id"] for r in rows))
        state = engine.apply_event(state, {"id": "CORRECTED_REPLY", "type": "request_response", "request_id": request["id"], "issuer_id": "engineer", "status": "corrected",
            "evidence": {"id": "CORRECTED_DOC", "verified": True, "issuer_id": "engineer", "project_id": state["project"]["id"],
                         "design_revision": state["project"]["design_revision"], "effective_at": state["project"]["now"], "kind": "correction_record", "rework_id": record["id"]}})
        rows = dashboard.summarize(state)["bottlenecks"]
        self.assertFalse(any(r.get("rework_id") == record["id"] for r in rows))
        reviewer = next(r for r in rows if r.get("gate_id") == "permit")
        self.assertEqual("inspector", reviewer["resolver_id"])
        self.assertEqual("permit", reviewer["action"]["gate_id"])
        engine.apply_action(state, reviewer["action"])

    def test_correction_row_never_exposes_an_invalid_candidate(self):
        state = self.returned_review()
        analysis = engine.analyze(state)
        correction = next(c for c in analysis["candidates"] if c["action"].get("purpose") == "rework_correction")
        correction["action"]["recipient_id"] = "vendor"
        row = next(r for r in dashboard.summarize(state, analysis)["bottlenecks"] if r.get("rework_id"))
        self.assertEqual("engineer", row["resolver_id"])
        self.assertNotIn("action", row)

    def test_revoked_gate_authority_is_visible_even_if_status_still_says_approved(self):
        state = scenarios.initial_state("delivery_delay")
        next(p for p in state["stakeholders"] if p["id"] == "inspector")["can_approve"].remove("permit")
        self.assertEqual("approved", state["gates"]["permit"]["status"])
        self.assertFalse(dashboard._gate_ready(state, "permit"))
        self.assertTrue(any(r.get("gate_id") == "permit" for r in dashboard.summarize(state)["bottlenecks"]))


if __name__ == "__main__":
    unittest.main()
