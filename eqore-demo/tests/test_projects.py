"""Whole-project fixture, provenance, finance and lifecycle regression checks."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import unittest

import engine
import evaluation
import phases
import project_evaluation
import projects
import scenarios


class ProjectWorldTests(unittest.TestCase):
    def test_catalog_has_distinct_whole_projects_and_no_future_answers(self):
        catalog = projects.list_projects()
        self.assertEqual(len(catalog), 3)
        self.assertEqual(len({p["id"] for p in catalog}), 3)
        self.assertEqual(len({p["site"] for p in catalog}), 3)
        self.assertEqual(len({p["budget_baseline"] for p in catalog}), 3)
        self.assertEqual(len({p["system"]["capacity_kwh"] for p in catalog}), 3)
        self.assertEqual(len(scenarios.list_scenarios()), 14)
        for meta in catalog:
            state = projects.initial_state(meta["id"])
            self.assertTrue(meta["synthetic"])
            self.assertEqual(meta["event_count"], 5)
            self.assertEqual(len(state["tasks"]), 14)
            self.assertEqual(state["tasks"][0]["id"], "t_contract")
            self.assertEqual(state["tasks"][-1]["id"], "t_handoff")
            observed = json.dumps(state)
            for secret in ("timed_events", "expected_outcomes", "actor_policies", "EV_CT_DEFECT", "EV_UTILITY_RECEIPT"):
                self.assertNotIn(secret, observed)
            self.assertIsNone(projects.next_event(meta["id"], 0, state))
            self.assertGreaterEqual(len(engine.analyze(state)["constraints"]), 3)

    def test_all_scopes_contacts_and_dependencies_match_the_selected_project(self):
        for meta in projects.list_projects():
            with self.subTest(meta["id"]):
                state = projects.initial_state(meta["id"])
                project = state["project"]
                self.assertEqual(project["demo_project_id"], meta["id"])
                people = {p["id"]: p for p in state["stakeholders"]}
                tasks = {t["id"]: t for t in state["tasks"]}
                evidence = {e["id"]: e for e in state["evidence"]}
                self.assertEqual(len(evidence), len(state["evidence"]))
                for person in people.values():
                    self.assertEqual(person["project_ids"], [project["id"]])
                    self.assertTrue(person["contact"].endswith(".example"))
                for item in evidence.values():
                    self.assertEqual(item["project_id"], project["id"])
                    self.assertEqual(item["design_revision"], project["design_revision"])
                    self.assertNotIn(scenarios.PROJECT_ID, item["body"])
                    self.assertLessEqual(datetime.fromisoformat(item["received_at"]), datetime.fromisoformat(project["now"]))
                for task in tasks.values():
                    self.assertIn(task["owner_id"], people)
                    for dependency in task["predecessors"]:
                        self.assertIn(dependency, tasks)
                    for gate_id in task["required_gates"]:
                        self.assertIn(gate_id, state["gates"])
                    if task["status"] == "completed":
                        self.assertTrue(task["evidence_ids"])
                        self.assertTrue(any(evidence[eid]["issuer_id"] == task["owner_id"] for eid in task["evidence_ids"]))
                        finish = datetime.fromisoformat(task["planned_start"]) + timedelta(hours=task["duration_hours"])
                        self.assertLessEqual(finish, datetime.fromisoformat(project["now"]))
                    else:
                        self.assertGreaterEqual(datetime.fromisoformat(task["planned_start"]), datetime.fromisoformat(project["now"]))
                for gate in state["gates"].values():
                    self.assertIn(gate["required_authority"], people[gate["resolver_id"]]["can_approve"])
                    if gate["status"] == "approved":
                        self.assertTrue(gate["evidence_ids"])
                        self.assertIn(gate["required_authority"], people[gate["issuer_id"]]["can_approve"])
                if meta["id"] != "harbor_components":
                    self.assertNotIn("SRC_BEVERLY", project["source_ids"])

    def test_project_finances_and_labor_are_explicit_reconciled_snapshots(self):
        for meta in projects.list_projects():
            with self.subTest(meta["id"]):
                state = projects.initial_state(meta["id"])
                project = state["project"]
                finance = project["finance"]
                self.assertEqual(finance["as_of"], project["now"])
                self.assertEqual(finance["currency"], "USD")
                for field in ("budget", "baseline", "committed", "forecast"):
                    self.assertEqual(sum(line[field] for line in finance["lines"]), project["budget_baseline"])
                self.assertEqual(project["budget"]["committed"], project["budget_baseline"])
                for line in finance["lines"]:
                    self.assertGreaterEqual(line["actual"], 0)
                    self.assertLessEqual(line["actual"], line["committed"])
                lines = {line["id"]: line for line in finance["lines"]}
                for labor in project["labor"]:
                    self.assertEqual(labor["crew_size"] * labor["hours"] * labor["hourly_rate"], labor["cost"])
                    self.assertEqual(labor["cost"], lines[labor["line_id"]]["budget"])
                later = engine.apply_event(state, {"id": "clock-only", "type": "clock_advance", "at": "2027-01-01T09:00:00-05:00"})
                self.assertEqual(later["project"]["finance"], finance, "Elapsed time must not fabricate invoice transactions")

    def test_event_release_is_conditioned_on_work_and_is_project_scoped(self):
        prerequisites = {
            "harbor_components": ("t_permit", "t_site", "t_electrical", "t_verify", "t_commission"),
            "millbrook_cold_storage": ("t_survey", "t_design", "t_procure", "t_electrical", "t_commission"),
            "riverbend_logistics": ("t_verify", "t_verify", "t_commission", "t_commission", "t_closeout_documents"),
        }
        for project_id, required in prerequisites.items():
            state = projects.initial_state(project_id)
            for cursor, task_id in enumerate(required):
                state = projects.initial_state(project_id)
                self.assertIsNone(projects.next_event(project_id, cursor, state))
                next(t for t in state["tasks"] if t["id"] == task_id)["status"] = "completed"
                event = projects.next_event(project_id, cursor, state)
                self.assertIsNotNone(event)
                self.assertEqual(event["evidence"]["project_id"], state["project"]["id"])
                self.assertEqual(event["evidence"]["design_revision"], state["project"]["design_revision"])
                self.assertGreater(datetime.fromisoformat(event["at"]), datetime.fromisoformat(state["project"]["now"]))
            self.assertIsNone(projects.next_event(project_id, 5, state))
        with self.assertRaisesRegex(ValueError, "does not match"):
            projects.next_event("riverbend_logistics", 0, projects.initial_state("harbor_components"))

    def test_initial_states_and_catalog_are_independent_copies(self):
        for meta in projects.list_projects():
            original = projects.initial_state(meta["id"])
            changed = projects.initial_state(meta["id"])
            changed["project"]["finance"]["lines"][0]["budget"] = -100
            changed["stakeholders"][0]["name"] = "Mutation"
            self.assertEqual(original, projects.initial_state(meta["id"]))
        catalog = projects.list_projects()
        catalog[0]["system"]["power_kw"] = -1
        self.assertGreater(projects.list_projects()[0]["system"]["power_kw"], 0)
        with self.assertRaisesRegex(ValueError, "Unknown demo project"):
            projects.initial_state("missing")

    def test_every_project_executes_the_full_lifecycle_and_stage_events(self):
        report = project_evaluation.run_suite()
        self.assertEqual(report["summary"], {"total": 3, "passed": 3, "failed": 0})
        for case in report["cases"]:
            self.assertTrue(all(check["passed"] for check in case["checks"]), case)
            self.assertEqual(len(case["final_summary"]["completed_tasks"]), 14)
            self.assertEqual(sum(t["type"] == "project_update" for t in case["trace"]), 5)
            self.assertTrue(any(t.get("responses") for t in case["trace"]))
            self.assertTrue(case["final_summary"]["phases"]["all_accepted"])
            self.assertEqual(case["final_summary"]["phases"]["open_rework_count"], 0)
            self.assertTrue(all(p["status"] == "completed" for p in case["final_summary"]["phases"]["phases"]))
        harbor = next(case for case in report["cases"] if case["id"] == "harbor_components")
        self.assertEqual(harbor["final_summary"]["budget"]["committed"], 242400)

    def test_replies_are_actual_request_bound_and_cannot_cross_project_authority(self):
        for meta in projects.list_projects():
            state = projects.initial_state(meta["id"])
            decision = engine.recommend(state)
            state = engine.apply_action(state, decision["action"])
            request = state["requests"][-1]
            event = projects.actor_response(state, request)
            self.assertEqual(event["request_id"], request["id"])
            self.assertEqual(event["issuer_id"], request["recipient_id"])
            self.assertEqual(event["evidence"]["project_id"], state["project"]["id"])
            after = engine.apply_event(state, event)
            self.assertEqual(evaluation._invariants(state, after), [])
            foreign = deepcopy(event)
            foreign["evidence"]["project_id"] = "OTHER-PROJECT"
            with self.assertRaises(engine.DomainError):
                engine.apply_event(state, foreign)

    def test_review_receipt_does_not_close_fire_gate_but_later_scoped_result_does(self):
        state = projects.initial_state("harbor_components")
        action = {"type": "request_review", "gate_id": "fire_review", "subject_id": "fire_review", "recipient_id": "fire", "purpose": "gate_resolution", "request": "Review the current fire package."}
        state = engine.apply_action(state, action)
        receipt = projects.actor_response(state, state["requests"][-1])
        self.assertEqual(receipt["evidence"]["kind"], "receipt")
        state = engine.apply_event(state, receipt)
        self.assertEqual(state["gates"]["fire_review"]["status"], "pending")
        self.assertEqual(state["gates"]["permit"]["status"], "pending")
        acknowledged = state["requests"][-1]
        self.assertEqual(acknowledged["status"], "acknowledged")
        self.assertIsNone(projects.actor_response(state, acknowledged))
        again = engine.apply_action(state, action)
        self.assertEqual(len(again["requests"]), len(state["requests"]), "Receipt must not trigger an immediate duplicate request")
        state = engine.apply_event(state, {"id": "review-clock", "type": "clock_advance", "at": acknowledged["due_at"]})
        follow_up = dict(action, purpose="follow_up", parent_request_id=acknowledged["id"])
        state = engine.apply_action(state, follow_up)
        accepted = projects.actor_response(state, state["requests"][-1])
        state = engine.apply_event(state, accepted)
        self.assertEqual(state["gates"]["fire_review"]["status"], "approved")
        self.assertEqual(state["gates"]["permit"]["status"], "pending", "Fire acceptance must not invent another agency's approval")

    def test_shipping_estimate_cannot_substitute_for_physical_receiving(self):
        state = projects.initial_state("harbor_components")
        self.assertEqual(state["gates"]["delivery_receipt"]["status"], "pending")
        action = {"type": "request_information", "gate_id": "delivery_receipt", "subject_id": "delivery_receipt", "recipient_id": "facilities", "purpose": "gate_resolution", "request": "Supply signed physical receiving record."}
        state = engine.apply_action(state, action)
        event = projects.actor_response(state, state["requests"][-1])
        self.assertGreaterEqual(datetime.fromisoformat(event["at"]), datetime.fromisoformat(state["project"]["delivery_eta"]))
        self.assertEqual(event["issuer_id"], "facilities")
        self.assertEqual(state["gates"]["delivery_receipt"]["status"], "pending", "Generating a hypothetical reply cannot mutate observed state")
        state = engine.apply_event(state, event)
        self.assertEqual(state["gates"]["delivery_receipt"]["status"], "approved")
        self.assertNotEqual(next(t for t in state["tasks"] if t["id"] == "t_unload")["status"], "completed")

    def test_fleet_acceptance_cannot_arrive_before_closeout_documents(self):
        state = projects.initial_state("riverbend_logistics")
        request = {"id": "manual-request", "status": "pending", "gate_id": "fleet_ready", "subject_id": "fleet_ready", "purpose": "gate_resolution", "recipient_id": "fleet"}
        self.assertIsNone(projects.actor_response(state, request))
        next(t for t in state["tasks"] if t["id"] == "t_commission")["status"] = "completed"
        self.assertIsNone(projects.actor_response(state, request), "Commissioning alone does not establish a usable fleet document pack")
        next(t for t in state["tasks"] if t["id"] == "t_closeout_documents")["status"] = "completed"
        event = projects.actor_response(state, request)
        self.assertEqual(event["gate_id"], "fleet_ready")
        self.assertIn("telemetry", event["evidence"]["body"])

    def test_installer_correction_is_separate_from_independent_field_verification(self):
        state = projects.initial_state("harbor_components")
        next(t for t in state["tasks"] if t["id"] == "t_electrical")["status"] = "completed"
        event = projects.next_event("harbor_components", 2, state)
        state = engine.apply_event(state, event)
        self.assertEqual(state["gates"]["corrective_work"]["status"], "blocked")
        premature = {"id": "premature-verification", "status": "pending", "gate_id": "field_verified", "subject_id": "field_verified", "purpose": "gate_resolution", "recipient_id": "verifier"}
        self.assertIsNone(projects.actor_response(state, premature))
        action = {"type": "request_review", "gate_id": "corrective_work", "subject_id": "corrective_work", "recipient_id": "electrician", "purpose": "gate_resolution", "request": "Supply corrective-work evidence for the observed CT discrepancy."}
        state = engine.apply_action(state, action)
        response = projects.actor_response(state, state["requests"][-1])
        self.assertEqual(response["issuer_id"], "electrician")
        state = engine.apply_event(state, response)
        self.assertEqual(state["gates"]["corrective_work"]["status"], "approved")
        self.assertEqual(state["gates"]["field_verified"]["status"], "pending")
        self.assertIsNotNone(projects.actor_response(state, premature))

    def test_grounding_is_auditable_and_review_dates_are_not_compressed_to_days(self):
        with open("knowledge.json") as handle:
            knowledge = json.load(handle)
        sources = {source["id"]: source for source in knowledge["sources"]}
        for meta in projects.list_projects():
            state = projects.initial_state(meta["id"])
            self.assertEqual(state["project"]["world_version"], projects.VERSION)
            self.assertIn("SRC_EQORE_FLEET", state["project"]["source_ids"])
            for mapping in state["project"]["source_mapping"]:
                self.assertIn(mapping["source_id"], sources)
            for gate in state["gates"].values():
                self.assertTrue(gate["required_artifacts"])
                self.assertIn("Synthetic", gate["assumption"])
                for source_id in gate["source_ids"]:
                    self.assertIn(source_id, sources)
        state = projects.initial_state("millbrook_cold_storage")
        starts = {t["id"]: datetime.fromisoformat(t["planned_start"]) for t in state["tasks"]}
        self.assertGreater((starts["t_handoff"] - starts["t_contract"]).days, 75)
        self.assertGreater((starts["t_permit"] - starts["t_design"]).days, 30)
        self.assertGreater(starts["t_handoff"], starts["t_customer_training"])
        self.assertNotIn("SRC_BEVERLY", state["project"]["source_ids"])

    def test_signed_entry_and_historical_dates_are_explicit_recorded_assumptions(self):
        for meta in projects.list_projects():
            state = projects.initial_state(meta["id"])
            self.assertEqual(state["project"]["scope_start"], "post_signing")
            signed_at = datetime.fromisoformat(state["project"]["signed_at"])
            now = datetime.fromisoformat(state["project"]["now"])
            self.assertLessEqual(signed_at, now)
            evidence = {e["id"]: e for e in state["evidence"]}
            for task in state["tasks"]:
                if task["status"] != "completed":
                    self.assertNotIn("completed_at", task)
                    continue
                finished = datetime.fromisoformat(task["completed_at"])
                self.assertGreaterEqual(finished, signed_at)
                self.assertLessEqual(finished, now)
                self.assertTrue(any(evidence[eid]["effective_at"] == task["completed_at"] for eid in task["evidence_ids"]))
            self.assertEqual(phases.summarize(state)["signed_at"], state["project"]["signed_at"])
            if meta["id"] != "millbrook_cold_storage":
                self.assertEqual(signed_at.utcoffset(), timedelta(hours=-4), "August New York dates use daylight time")

    def test_project_trace_records_return_correction_reacceptance_and_late_retest(self):
        report = project_evaluation.run_suite()
        cases = {case["id"]: case for case in report["cases"]}
        for project_id in ("harbor_components", "millbrook_cold_storage"):
            trace = cases[project_id]["trace"]
            self.assertTrue(any(r["status"] == "correction_required" for step in trace for r in step["state"]["phases"]["rework"]))
            self.assertTrue(any(step.get("action", {}).get("purpose") == "rework_correction" for step in trace))
            self.assertTrue(any(r["status"] == "awaiting_reapproval" and r.get("correction_evidence_ids") for step in trace for r in step["state"]["phases"]["rework"]))
            self.assertTrue(any(r["status"] == "resolved" and r.get("correction_evidence_ids") and r.get("resolution_evidence_ids") for r in cases[project_id]["final_summary"]["phases"]["rework"]))
        river = cases["riverbend_logistics"]
        late = next(step for step in river["trace"] if step.get("event_id", "").endswith("late_network_fault"))
        self.assertNotIn("t_commission", late["state"]["completed_tasks"])
        self.assertIn("t_electrical", late["state"]["completed_tasks"], "A controls retest must preserve physical installation history")
        self.assertIn("t_commission", river["final_summary"]["completed_tasks"])
        self.assertTrue(next(check for check in river["checks"] if check["name"] == "correction_and_reacceptance_exercised")["passed"])

    def test_lifecycle_traces_exercise_receipt_then_review_and_all_closeout_tasks(self):
        report = project_evaluation.run_suite()
        for case in report["cases"]:
            self.assertEqual(case["status"], "passed")
            actions = [step["action"] for step in case["trace"] if step.get("action")]
            self.assertTrue(any(a.get("task_id") == "t_closeout_documents" for a in actions))
            self.assertTrue(any(a.get("task_id") == "t_customer_training" for a in actions))
            self.assertTrue(any(a.get("gate_id") == "fleet_ready" for a in actions))
            self.assertTrue(any("receipt" in response["summary"] for step in case["trace"] for response in step.get("responses", [])))


if __name__ == "__main__":
    unittest.main()
