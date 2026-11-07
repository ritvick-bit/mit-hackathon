"""Phase views cross the API and model boundary without changing saved history."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

import engine
import llm
import phases
import projects
from server import APP_VERSION, Application, Handler


def returned_review(state):
    issuer = state["gates"]["permit"]["resolver_id"]
    return engine.apply_event(state, {
        "id": "PHASE_REVIEW_RETURNED", "type": "review_returned", "gate_id": "permit",
        "issuer_id": issuer, "correction_owner_id": "engineer", "return_phase": "site_design",
        "reason": "The equipment access detail needs a revised drawing.",
        "required_artifact": "Corrected access detail for the current project package",
        "evidence": {"id": "PHASE_REVIEW_COMMENTS", "project_id": state["project"]["id"],
                     "design_revision": state["project"]["design_revision"], "issuer_id": issuer,
                     "kind": "review_comments", "verified": True, "effective_at": state["project"]["now"]},
    })


class PhaseAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = patch("llm.runtime_status", return_value={"available": True, "authenticated": True, "detail": "test"})
        self.auth.start()
        self.app = Application(self.tmp.name + "/phases.sqlite3")

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.auth.stop()
        self.tmp.cleanup()

    def test_bootstrap_exposes_verified_source_review_and_observed_phases(self):
        before = self.app.store.read()
        result = self.app.bootstrap()
        self.assertEqual(result["version"], "0.4.0")
        self.assertEqual(Handler.server_version, "EqoreDemo/" + APP_VERSION)
        self.assertEqual(result["phases"], phases.summarize(before["state"], result["analysis"]))
        self.assertEqual(result["workflow_review"]["status"], "partially_verified")
        self.assertEqual(result["workflow_review"]["scope"], "post_signing")
        self.assertIn("missing_content", result["workflow_review"])
        source_ids = {item["id"] for item in result["sources"]}
        self.assertTrue(set(result["workflow_review"]["source_ids"]).issubset(source_ids))
        self.assertEqual(self.app.store.read(), before)

    def test_catalog_uses_each_saved_world_and_updates_after_returned_review(self):
        first = self.app.bootstrap()
        active_id = first["state"]["project"]["demo_project_id"]
        others_before = {p["id"]: p["phase_summary"] for p in first["projects"] if p["id"] != active_id}
        changed = returned_review(first["state"])
        self.app.store.write(changed, expected=first["session_version"], operation="phase_test_returned_review")
        after = self.app.bootstrap()
        current = next(p for p in after["projects"] if p["id"] == active_id)
        self.assertEqual(current["current_phase_titles"], after["phases"]["active_phase_titles"])
        self.assertGreater(current["phase_summary"]["open_rework_count"], 0)
        rows = {row["id"]: row for row in current["phase_summary"]["statuses"]}
        self.assertEqual(rows["reviews"]["status"], "rework")
        for item in after["projects"]:
            if item["id"] != active_id:
                self.assertEqual(item["phase_summary"], others_before[item["id"]])
        self.assertEqual(after["phases"]["rework_routes"][0]["reason"], changed["rework"][0]["reason"])

    def test_legacy_records_gain_a_read_only_view_without_erasing_saved_history(self):
        record = self.app.store.read()
        legacy = copy.deepcopy(record["state"])
        legacy.pop("rework", None)
        for task in legacy["tasks"]:
            task.pop("phase_id", None)
        self.app.store.write(legacy, expected=record["version"], operation="legacy_record_fixture")
        saved = self.app.store.read()
        result = self.app.bootstrap()
        self.assertTrue(result["phases"]["phases"])
        self.assertEqual(result["phases"]["unmapped_task_ids"], [])
        self.assertEqual(result["state"], legacy)
        self.assertEqual(self.app.store.read(), saved)


class PhaseLLMIntegrationTests(unittest.TestCase):
    def test_model_receives_observed_rework_and_phase_scope_without_future_events(self):
        state = returned_review(projects.initial_state("harbor_components"))
        state["private_events"] = [{"secret": "FUTURE_EVENT_NOT_FOR_MODEL"}]
        state["expected_outcome"] = "ORACLE_NOT_FOR_MODEL"
        seen = []

        def model(role, instruction, context, schema):
            seen.append((role, instruction, copy.deepcopy(context)))
            output = {key: [] if field["type"] == "array" else "Test draft"
                      for key, field in schema["properties"].items()}
            if role == "Coordinator":
                candidate = next(c for c in context["permitted_candidates"]
                                 if c["action"].get("purpose") == "rework_correction")
                output.update(candidate_id=candidate["candidate_id"], priority_basis=["evidence_quality"],
                              supporting_fact_ids=[candidate["reasoning"]["facts"][0]["id"]])
            return {"role": role, "output": output}

        before = copy.deepcopy(state)
        with patch("llm._call", side_effect=model):
            result = llm.decide(state)
        self.assertEqual(len(seen), 3)
        self.assertEqual(result["action"]["purpose"], "rework_correction")
        for role, instruction, context in seen:
            with self.subTest(role=role):
                self.assertEqual(context["rework"], state["rework"])
                self.assertGreater(context["phases"]["open_rework_count"], 0)
                self.assertIn("Post-signing", context["phases"]["scope"])
                self.assertNotIn("scenario_id", context["project"])
                self.assertNotIn("demo_project_id", context["project"])
                self.assertNotIn("private_events", context)
                self.assertNotIn("expected_outcome", context)
                serialized = json.dumps(context)
                self.assertNotIn("FUTURE_EVENT_NOT_FOR_MODEL", serialized)
                self.assertNotIn("ORACLE_NOT_FOR_MODEL", serialized)
                # Repeated acceptance histories are omitted from the compact phase
                # context; the underlying observed records remain available above.
                self.assertTrue(all("milestones" not in row for row in context["phases"]["phases"]))
        planner_instruction = next(instruction for role, instruction, _ in seen if role == "Recovery planner")
        self.assertIn("concurrently", planner_instruction)
        self.assertIn("preserving unaffected work", planner_instruction)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
