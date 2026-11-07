"""Fixture integrity and negative-control checks for the actual development runner."""
from copy import deepcopy
from datetime import datetime
import json
import unittest

import evaluation
import scenarios


class FixtureIntegrityTests(unittest.TestCase):
    def test_every_development_case_has_consistent_scope_and_acyclic_dependencies(self):
        for meta in scenarios.list_scenarios():
            with self.subTest(meta["id"]):
                state = scenarios.initial_state(meta["id"])
                tasks = {t["id"]: t for t in state["tasks"]}
                people = {p["id"]: p for p in state["stakeholders"]}
                evidence = {e["id"]: e for e in state["evidence"]}
                seen, stack = set(), set()

                def visit(tid):
                    self.assertNotIn(tid, stack)
                    if tid in seen:
                        return
                    stack.add(tid)
                    for dep in tasks[tid]["predecessors"]:
                        self.assertIn(dep, tasks)
                        visit(dep)
                    stack.remove(tid)
                    seen.add(tid)

                for task in tasks.values():
                    visit(task["id"])
                    self.assertIn(task["owner_id"], people)
                    for gid in task.get("required_gates", []):
                        self.assertIn(gid, state["gates"])
                    if task["status"] == "completed":
                        self.assertTrue(any(evidence[eid]["issuer_id"] == task["owner_id"] for eid in task["evidence_ids"]))
                for gate in state["gates"].values():
                    self.assertIn(gate["required_authority"], people[gate["resolver_id"]]["can_approve"])
                    if gate["status"] == "approved":
                        self.assertIn(gate["required_authority"], people[gate["issuer_id"]]["can_approve"])
                        self.assertTrue(gate["evidence_ids"])
                        for eid in gate["evidence_ids"]:
                            self.assertEqual(evidence[eid]["project_id"], state["project"]["id"])
                            self.assertEqual(evidence[eid]["design_revision"], state["project"]["design_revision"])
                self.assertTrue(all(p["contact"].endswith(".example") for p in people.values()))
                self.assertGreaterEqual(len(tasks), 12)

    def test_resets_do_not_share_mutable_state_or_hidden_answers(self):
        one = scenarios.initial_state("delivery_delay")
        one["project"]["name"] = "mutated"
        one["tasks"][0]["status"] = "blocked"
        two = scenarios.initial_state("delivery_delay")
        self.assertNotEqual(one, two)
        text = json.dumps(two)
        for hidden_key in ("acceptable_terminal_states", "expected_outcomes", "private_world", "actor_policies", "timed_events"):
            self.assertNotIn(hidden_key, text)
        self.assertEqual(scenarios.initial_state("normal_progress")["tasks"][0]["status"], "ready")

    def test_reference_scopes_and_capability_coverage_are_explicit(self):
        sources = {s["id"]: s for s in scenarios.sources()}
        self.assertIn("Beverly", sources["SRC_BEVERLY"]["scope"])
        self.assertIn("Massachusetts", sources["SRC_NG_MA_1646"]["scope"])
        self.assertTrue(all(s.get("url") and s.get("locator") and s.get("evidence_status") for s in sources.values()))
        coverage = {cap for case in scenarios.list_scenarios() for cap in case["capabilities"]}
        self.assertEqual(coverage, {"CAP%02d" % n for n in range(1, 9)})


class DevelopmentEvaluationTests(unittest.TestCase):
    def test_baseline_executes_the_real_workflows(self):
        report = evaluation.run_suite()
        failures = {c["id"]: [k for k in c["checks"] if not k["passed"]] for c in report["cases"] if c["status"] == "failed"}
        self.assertEqual(failures, {})
        self.assertGreaterEqual(report["summary"]["total"], 12)
        self.assertEqual(set(report["coverage"]), {"CAP%02d" % n for n in range(1, 9)})
        normal = next(c for c in report["cases"] if c["id"] == "normal_progress")
        self.assertEqual(len(normal["final_summary"]["completed_tasks"]), 12)
        self.assertGreater(normal["action_count"], 10)
        self.assertTrue(any(t["kind"] == "actor_response" for t in normal["trace"]))
        blocked = next(c for c in report["cases"] if c["id"] == "customer_nonresponse")
        self.assertEqual(blocked["terminal_class"], "blocked")
        self.assertIn("t_handoff_draft", blocked["final_summary"]["completed_tasks"])

    def test_always_waiting_cannot_pass_normal_or_disrupted_progress(self):
        report = evaluation.run_suite(decide=lambda state: {"action": {"type": "wait"}, "title": "Wait without doing available work"},
                                      scenario_ids=["normal_progress", "delivery_delay", "customer_nonresponse"])
        self.assertEqual(report["summary"]["passed"], 0)
        for case in report["cases"]:
            self.assertTrue(any(not c["passed"] for c in case["checks"] if c["name"] in ("available_work_completed", "meaningful_block", "independent_work_progressed")))

    def test_forged_physical_completion_is_rejected_by_actual_engine(self):
        report = evaluation.run_suite(decide=lambda state: {"action": {"type": "complete_task", "task_id": "t_handoff"}}, scenario_ids=["delivery_delay"])
        self.assertEqual(report["summary"]["failed"], 1)
        checks = {c["name"]: c for c in report["cases"][0]["checks"]}
        self.assertFalse(checks["execution_errors"]["passed"])
        self.assertFalse(checks["available_work_completed"]["passed"])

    def test_live_mode_requires_real_model_callable(self):
        with self.assertRaisesRegex(ValueError, "no baseline fallback"):
            evaluation.run_suite(mode="live", scenario_ids=["normal_progress"])
        with self.assertRaisesRegex(ValueError, "Unknown scenarios"):
            evaluation.run_suite(scenario_ids=["not_a_case"])

    def test_external_document_cannot_claim_current_project_authority(self):
        state = scenarios.initial_state("wrong_scope")
        event = scenarios.next_event("wrong_scope", 0, state)
        self.assertNotEqual(event["evidence"]["project_id"], state["project"]["id"])
        self.assertEqual(event["status"], "pending")
        report = evaluation.run_suite(scenario_ids=["wrong_scope"])
        self.assertEqual(report["summary"]["passed"], 1)
        self.assertIn("utility_operate", report["cases"][0]["final_summary"]["unresolved_gates"])


if __name__ == "__main__":
    unittest.main()
