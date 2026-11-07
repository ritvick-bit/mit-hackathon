"""Phase acceptance, parallel progress and historical evidence regressions."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

import phases
import projects


def _accepted_world():
    state = projects.initial_state("riverbend_logistics")
    for task in state["tasks"]:
        eid = "TEST_COMPLETE_" + task["id"]
        state["evidence"].append({"id": eid, "project_id": state["project"]["id"], "design_revision": state["project"]["design_revision"],
                                  "issuer_id": task["owner_id"], "kind": "task_completion", "task_id": task["id"], "verified": True,
                                  "effective_at": state["project"]["now"]})
        task.update(status="completed", evidence_ids=[eid], completed_at=state["project"]["now"])
    for gid, gate in state["gates"].items():
        eid = "TEST_GATE_" + gid
        state["evidence"].append({"id": eid, "project_id": state["project"]["id"], "design_revision": state["project"]["design_revision"],
                                  "issuer_id": gate["resolver_id"], "kind": gid, "verified": True, "effective_at": state["project"]["now"]})
        gate.update(status="approved", issuer_id=gate["resolver_id"], evidence_ids=[eid])
    state["alerts"] = []
    state["rework"] = []
    state["project"]["status"] = "completed"
    return state


class PhaseTests(unittest.TestCase):
    def test_all_project_tasks_belong_to_exactly_one_post_signing_phase(self):
        for project in projects.list_projects():
            state = projects.initial_state(project["id"])
            result = phases.summarize(state)
            assigned = [tid for phase in result["phases"] for tid in phase["task_ids"]]
            self.assertCountEqual(assigned, [t["id"] for t in state["tasks"]])
            self.assertEqual(len(assigned), len(set(assigned)))
            self.assertEqual(len(result["phases"]), 8)
            self.assertFalse(result["unmapped_task_ids"])
            self.assertFalse(result["all_accepted"])

    def test_phase_derivation_does_not_mutate_observed_records(self):
        state = projects.initial_state("harbor_components")
        before = deepcopy(state)
        result = phases.summarize(state)
        result["phases"][0]["exit_criteria"].append("mutation")
        self.assertEqual(state, before)
        self.assertNotIn("mutation", phases.CATALOG[0]["exit_criteria"])

    def test_parallel_tracks_not_forced_into_serial_phase_order(self):
        state = projects.initial_state("harbor_components")
        task = next(t for t in state["tasks"] if t["id"] == "t_procure")
        task.update(status="planned", evidence_ids=[])
        result = phases.summarize(state)
        rows = {p["id"]: p for p in result["phases"]}
        self.assertEqual(rows["reviews"]["status"], "current")
        self.assertEqual(rows["procurement_site"]["status"], "current")
        self.assertIn("t_procure", rows["procurement_site"]["ready_task_ids"])
        self.assertIn("reviews", result["active_phase_ids"])
        self.assertIn("procurement_site", result["active_phase_ids"])

    def test_internal_predecessor_does_not_make_future_installation_active(self):
        state = projects.initial_state("millbrook_cold_storage")
        result = phases.summarize(state)
        row = next(p for p in result["phases"] if p["id"] == "installation")
        self.assertEqual(row["status"], "upcoming")
        self.assertFalse(row["ready_task_ids"])
        self.assertFalse(row["actionable_gate_ids"])

    def test_late_revoked_permit_reopens_acceptance_without_erasing_work(self):
        state = _accepted_world()
        self.assertTrue(phases.summarize(state)["all_accepted"])
        history = deepcopy(state["tasks"])
        state["gates"]["permit"]["status"] = "blocked"
        result = phases.summarize(state)
        rows = {p["id"]: p for p in result["phases"]}
        self.assertFalse(result["all_accepted"])
        self.assertEqual(rows["reviews"]["status"], "rework")
        self.assertFalse(rows["handoff"]["acceptance_current"])
        self.assertTrue(rows["handoff"]["historical_work_complete"])
        self.assertIsNotNone(rows["handoff"]["milestones"]["actual_finish"])
        self.assertEqual(state["tasks"], history)
        self.assertTrue(result["warnings"])

    def test_wrong_project_receipt_or_revoked_issuer_cannot_complete_phase(self):
        for damage in ("wrong_project", "receipt", "revoked_authority", "old_design", "missing_evidence"):
            with self.subTest(damage):
                state = _accepted_world()
                gate = state["gates"]["utility_operate"]
                evidence = next(e for e in state["evidence"] if e["id"] == gate["evidence_ids"][0])
                if damage == "wrong_project":
                    evidence["project_id"] = "ANOTHER_SITE"
                elif damage == "receipt":
                    evidence["kind"] = "receipt"
                elif damage == "revoked_authority":
                    next(p for p in state["stakeholders"] if p["id"] == "utility")["can_approve"] = []
                elif damage == "old_design":
                    evidence["design_revision"] = "V0"
                else:
                    gate["evidence_ids"] = []
                result = phases.summarize(state)
                self.assertFalse(result["all_accepted"])
                self.assertFalse(next(p for p in result["phases"] if p["id"] == "verification")["acceptance_current"])

    def test_planned_dates_do_not_become_actual_dates(self):
        state = projects.initial_state("millbrook_cold_storage")
        result = phases.summarize(state)
        design = next(p for p in result["phases"] if p["id"] == "site_design")
        self.assertIsNotNone(design["milestones"]["planned_finish"])
        self.assertIsNone(design["milestones"]["actual_finish"])
        task = next(t for t in state["tasks"] if t["id"] == "t_survey")
        task.update(status="completed", completed_at=state["project"]["now"])
        record = next(r for p in phases.summarize(state)["phases"] for r in p["milestones"]["recorded_completions"] if r["task_id"] == "t_survey")
        self.assertFalse(record["evidenced"])
        self.assertIsNone(record["actual_finish"])

    def test_open_rework_remains_visible_until_explicitly_resolved(self):
        state = _accepted_world()
        state["rework"] = [{"id": "RW1", "status": "correction_required", "return_phase": "site_design", "gate_ids": ["design"],
                            "task_ids": ["t_design"], "reason": "Reviewer requested a revised layout", "generation": 1}]
        result = phases.summarize(state)
        self.assertFalse(result["all_accepted"])
        self.assertEqual(result["open_rework_count"], 1)
        self.assertEqual(next(p for p in result["phases"] if p["id"] == "site_design")["status"], "rework")
        state["rework"][0]["status"] = "resolved"
        result = phases.summarize(state)
        self.assertTrue(result["all_accepted"])
        self.assertEqual(result["open_rework_count"], 0)
        self.assertEqual(result["resolved_rework_count"], 1)

    def test_corrected_design_phase_closes_while_downstream_reapproval_continues(self):
        state = _accepted_world()
        state["gates"]["permit"]["status"] = "pending"
        state["rework"] = [{"id": "RW1", "status": "awaiting_reapproval", "return_phase": "site_design",
                            "gate_ids": ["design", "permit"], "task_ids": ["t_design", "t_permit"], "generation": 1}]
        result = phases.summarize(state)
        rows = {p["id"]: p for p in result["phases"]}
        self.assertEqual(rows["site_design"]["status"], "completed")
        self.assertEqual(rows["reviews"]["status"], "rework")
        self.assertFalse(result["all_accepted"])
        self.assertEqual(result["open_rework_count"], 1)

    def test_superseded_cycle_does_not_keep_project_open(self):
        state = _accepted_world()
        state["rework"] = [{"id": "RW_OLD", "status": "superseded", "return_phase": "site_design", "task_ids": ["t_design"], "gate_ids": ["design"]}]
        result = phases.summarize(state)
        self.assertTrue(result["all_accepted"])
        self.assertEqual(result["open_rework_count"], 0)
        self.assertEqual(result["superseded_rework_count"], 1)

    def test_invalidated_evidence_cannot_reclose_acceptance(self):
        state = _accepted_world()
        gate = state["gates"]["design"]
        gate["invalidated_evidence_ids"] = list(gate["evidence_ids"])
        result = phases.summarize(state)
        self.assertFalse(result["all_accepted"])
        row = next(p for p in result["phases"] if p["id"] == "site_design")
        self.assertFalse(row["acceptance_current"])

    def test_old_preinvalidation_approval_is_not_current_despite_approved_status(self):
        state = _accepted_world()
        gate = state["gates"]["permit"]
        invalidated_at = datetime.fromisoformat(state["project"]["now"]) + timedelta(hours=1)
        gate.update(invalidated_at=invalidated_at.isoformat(), invalidated_evidence_ids=[])
        state["project"]["now"] = (invalidated_at + timedelta(hours=1)).isoformat()
        self.assertEqual(gate["status"], "approved")
        result = phases.summarize(state)
        self.assertFalse(result["all_accepted"])
        self.assertFalse(next(p for p in result["phases"] if p["id"] == "reviews")["acceptance_current"])
        self.assertFalse(next(p for p in result["phases"] if p["id"] == "handoff")["acceptance_current"])

    def test_correction_request_and_draft_records_are_not_gate_approval(self):
        for kind in ("correction_record", "request", "draft"):
            with self.subTest(kind):
                state = _accepted_world()
                gate = state["gates"]["design"]
                evidence = next(e for e in state["evidence"] if e["id"] == gate["evidence_ids"][0])
                evidence["kind"] = kind
                result = phases.summarize(state)
                self.assertFalse(result["all_accepted"])
                self.assertFalse(next(p for p in result["phases"] if p["id"] == "site_design")["acceptance_current"])

    def test_explicit_unaffected_approval_carry_forward_requires_scoped_engineering_record(self):
        state = _accepted_world()
        state["project"]["design_revision"] = "V4"
        evidence = {e["id"]: e for e in state["evidence"]}
        for gate in state["gates"].values():
            gate["design_revision"] = "V4"
            for eid in gate["evidence_ids"]:
                evidence[eid]["design_revision"] = "V4"
        permit = state["gates"]["permit"]
        evidence[permit["evidence_ids"][0]]["design_revision"] = "V3"
        impact = {"id": "IMPACT_V4", "kind": "design_revision", "project_id": state["project"]["id"], "design_revision": "V4",
                  "issuer_id": "engineer", "verified": True, "effective_at": state["project"]["now"]}
        state["evidence"].append(impact)
        permit["carry_forward"] = {"from_revision": "V3", "to_revision": "V4", "evidence_id": impact["id"], "issuer_id": "engineer",
                                    "accepted_evidence_ids": list(permit["evidence_ids"])}
        self.assertTrue(phases.summarize(state)["all_accepted"])
        for damage in ("missing_record", "wrong_project", "unlisted_approval", "unauthorized_engineer", "old_impact_revision"):
            with self.subTest(damage):
                bad = deepcopy(state)
                bad_permit = bad["gates"]["permit"]
                bad_impact = next(e for e in bad["evidence"] if e["id"] == impact["id"])
                if damage == "missing_record":
                    bad_permit.pop("carry_forward")
                elif damage == "wrong_project":
                    bad_impact["project_id"] = "ANOTHER_SITE"
                elif damage == "unlisted_approval":
                    bad_permit["carry_forward"]["accepted_evidence_ids"] = []
                elif damage == "unauthorized_engineer":
                    next(p for p in bad["stakeholders"] if p["id"] == "engineer")["can_approve"] = []
                else:
                    bad_impact["design_revision"] = "V3"
                result = phases.summarize(bad)
                self.assertFalse(result["all_accepted"])
                reviews = next(p for p in result["phases"] if p["id"] == "reviews")
                self.assertFalse(next(g for g in reviews["gates"] if g["id"] == "permit")["acceptance_current"])

    def test_retest_route_uses_observed_trigger_gate_owner(self):
        state = _accepted_world()
        state["events"].append({"id": "FAULT1", "type": "commissioning_fault", "gate_id": "network", "resolver_id": "it"})
        state["rework"] = [{"id": "RW1", "status": "awaiting_reapproval", "trigger_event_id": "FAULT1", "return_phase": None,
                            "gate_ids": ["network", "commissioned"], "task_ids": ["t_commission"], "correction_owner_id": None}]
        route = phases.summarize(state)["rework_routes"][0]
        self.assertEqual(route["return_phase"], "commissioning")
        self.assertEqual(route["correction_owner_id"], "it")
        self.assertEqual(route["return_phase_basis"], "Phase owning the observed trigger gate")

    def test_new_task_without_mapping_is_visible_and_blocks_false_success(self):
        state = _accepted_world()
        task = deepcopy(state["tasks"][0])
        task["id"] = "new_unmapped_work"
        state["tasks"].append(task)
        result = phases.summarize(state)
        self.assertIn("new_unmapped_work", result["unmapped_task_ids"])
        self.assertFalse(result["all_accepted"])


if __name__ == "__main__":
    unittest.main()
