"""Cross-check project resource projections against canonical operational facts."""
from copy import deepcopy
import json
import unittest

import dashboard
import engine
import operations
import project_resources
import projects
import vendors
import workspace


class ProjectResourceTests(unittest.TestCase):
    def fresh(self, project="harbor_components"):
        return operations.ensure(projects.initial_state(project))

    def view(self, state, profiles=None):
        profiles = vendors.list_vendors() if profiles is None else profiles
        return project_resources.view(state, operations.summarize(state, profiles), profiles)

    def committed(self):
        state = operations.apply(self.fresh(), {"type": "simulate_vendor_replies"})
        case = operations.summarize(state)["cases"][0]
        option = next(option for option in case["options"] if option["eligible"])
        state = operations.apply(state, {"type": "propose_vendor", "case_id": case["id"], "vendor_id": option["vendor_id"]})
        proposal = state["operations"]["proposals"][-1]
        return operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]},
                                actor_id=proposal["required_approver_id"])

    def test_view_is_pure_and_has_no_future_vendor_response_or_own_crew_pool(self):
        state, profiles = self.fresh(), vendors.list_vendors()
        operation_view = operations.summarize(state, profiles)
        before = deepcopy((state, profiles, operation_view))
        result = project_resources.view(state, operation_view, profiles)
        self.assertEqual((state, profiles, operation_view), before)
        self.assertNotIn("demo_response", json.dumps(result))
        self.assertNotIn("crews", result)
        self.assertNotIn("utilization", result["metrics"])
        self.assertEqual(result["metrics"]["offered_packages"], 0)
        self.assertEqual(result["metrics"]["confirmed_work_packages"], 0)
        self.assertTrue(all(row["owner_id"] not in {"pm", "fleet", "ops", "utility", "inspector"} for row in result["subcontracts"]))

    def test_supplier_eta_and_order_do_not_prove_physical_receipt(self):
        state = self.fresh()
        result = self.view(state)
        self.assertEqual(result["procurement"]["order"]["status"], "completed")
        self.assertEqual(result["procurement"]["delivery"]["receipt_status"], "waiting")
        self.assertTrue(result["procurement"]["delivery"]["conflict"])
        self.assertIsNone(result["procurement"]["order"]["purchase_order_id"])
        self.assertIsNone(result["procurement"]["order"]["verified_lead_time_days"])
        state["project"]["delivery_eta"] = "2026-11-10T09:00:00-05:00"
        changed = self.view(state)
        self.assertFalse(changed["procurement"]["delivery"]["conflict"])
        self.assertEqual(changed["procurement"]["delivery"]["receipt_status"], "waiting")

    def test_gate_labels_follow_engine_acceptance_not_status_strings(self):
        state = self.fresh()
        state["gates"]["delivery_receipt"]["status"] = "approved"
        result = self.view(state)
        receipt = next(row for row in result["readiness"]["checks"] if row["id"] == "receipt")
        self.assertEqual(receipt["status"], "waiting")
        for row in result["readiness"]["checks"]:
            if row["gate_ids"]:
                accepted = all(engine._gate_ready(state, gate_id) for gate_id in row["gate_ids"])
                self.assertEqual(row["status"] == "accepted", accepted)

    def test_riverbend_receipt_installation_and_operation_are_distinct(self):
        result = self.view(self.fresh("riverbend_logistics"))
        checks = {row["id"]: row for row in result["readiness"]["checks"]}
        self.assertEqual(checks["receipt"]["status"], "accepted")
        self.assertEqual(checks["utility_install"]["status"], "accepted")
        self.assertEqual(checks["utility_operate"]["status"], "waiting")
        self.assertEqual(checks["field"]["status"], "waiting")
        self.assertEqual(checks["network"]["status"], "waiting")
        self.assertNotIn("score", result["readiness"])

    def test_resource_windows_are_availability_and_not_booking(self):
        result = self.view(self.fresh())
        task = next(row for row in result["calendar"] if row.get("task_id") == "t_electrical")
        self.assertEqual(task["status"], "planned")
        self.assertEqual(task["duration_hours"], 4)
        self.assertEqual(task["end"], "2026-11-14T12:00:00-05:00")
        self.assertIn("customer_access", task["resources"])
        self.assertTrue(task["resource_windows"])
        self.assertEqual(result["procurement"]["shutdown"]["status"], "waiting")

    def test_offer_is_separate_from_assigned_work_and_spend(self):
        state = operations.apply(self.fresh(), {"type": "simulate_vendor_replies"})
        result = self.view(state)
        quoted = [row for row in result["subcontracts"] if row["offers"]]
        self.assertTrue(quoted)
        self.assertTrue(all(not row["tasks"] and row["status"] == "offered" for row in quoted))
        self.assertTrue(all(row["committed_total"] is None for row in quoted))
        self.assertEqual(result["metrics"]["committed_total"], 240000)
        self.assertEqual(result["metrics"]["actual_total"], 90800)
        self.assertEqual(result["metrics"]["confirmed_work_packages"], 0)
        self.assertTrue(any(row["kind"] == "vendor_offer" for row in result["calendar"]))

    def test_committed_package_requires_named_counterpart_booking(self):
        state = self.committed()
        package_id = state["operations"]["cases"][0]["work_package_id"]
        result = self.view(state)
        task = next(row for row in result["calendar"] if row.get("task_id") == package_id)
        self.assertEqual(task["status"], "planned")
        booking = next(row for row in state["operations"]["bookings"] if row["task_id"] == package_id)
        confirmed = operations.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]}, actor_id=booking["recipient_id"])
        changed = self.view(confirmed)
        task = next(row for row in changed["calendar"] if row.get("task_id") == package_id)
        self.assertEqual(task["status"], "booking_confirmed")
        self.assertEqual(task["duration_hours"], 1)
        self.assertEqual(changed["metrics"]["committed_total"], 241200)
        self.assertEqual(changed["metrics"]["actual_total"], 90800)
        self.assertEqual(changed["procurement"]["delivery"]["receipt_status"], "waiting")

    def test_old_date_or_wrong_counterpart_confirmation_is_not_current(self):
        for field, value in [("planned_start", "2026-11-13T09:00:00-05:00"), ("recipient_id", "pm")]:
            with self.subTest(field=field):
                state = self.fresh()
                task = next(row for row in state["tasks"] if row["id"] == "t_unload")
                booking = {"id": "booking-test", "task_id": task["id"], "recipient_id": task["owner_id"],
                           "planned_start": task["planned_start"], "status": "confirmed"}
                booking[field] = value
                state["bookings"].append(booking)
                result = self.view(state)
                row = next(row for row in result["calendar"] if row.get("task_id") == "t_unload")
                self.assertEqual(row["status"], "planned")

    def test_qualification_must_cover_work_window_not_just_today(self):
        state = self.committed()
        package_id = state["operations"]["cases"][0]["work_package_id"]
        package = next(row for row in state["tasks"] if row["id"] == package_id)
        profiles = vendors.list_vendors()
        profile = next(row for row in profiles if row["id"] == package["owner_id"])
        profile["qualifications"][0]["expires_at"] = "2026-11-16T23:59:00-05:00"
        result = self.view(state, profiles)
        group = next(row for row in result["subcontracts"] if row["owner_id"] == package["owner_id"])
        self.assertEqual(group["qualifications"][0]["validity"], "expired_or_unverified")
        check = next(row for row in result["readiness"]["checks"] if row["id"] == "subcontracts")
        self.assertIn("Review qualifications", check["detail"])

    def test_shared_ledger_allocation_is_not_double_counted_per_provider(self):
        state = self.fresh()
        result = self.view(state)
        engineering = next(row for row in result["subcontracts"] if row["owner_id"] == "engineer")
        shared = next(row for row in engineering["cost_lines"] if row["id"] == "engineering")
        self.assertEqual(shared["allocation"], "shared")
        self.assertIsNone(engineering["committed_total"])
        canonical = workspace.finance({"finance": dashboard._finance(state)}, state, operations.summarize(state))["finance"]
        for key in ("baseline_total", "committed_total", "actual_total", "proposed_change"):
            self.assertEqual(result["metrics"][key], canonical[key])

    def test_takeover_does_not_transfer_retained_baseline_contract_to_new_vendor(self):
        state = self.committed()
        proposal = state["operations"]["proposals"][-1]
        result = self.view(state)
        replacement = next(row for row in result["subcontracts"] if row["owner_id"] == proposal["vendor_id"])
        self.assertEqual(replacement["committed_total"], 1200)
        self.assertEqual(replacement["actual_total"], 0)
        retained = next(row for row in replacement["cost_lines"] if row["id"] == "rigging")
        self.assertEqual(retained["committed"], 4800)
        self.assertEqual(retained["allocation"], "shared")
        self.assertEqual(retained["commercial_owner_status"], "unconfirmed_after_takeover")
        self.assertIn("no recorded commercial transfer", retained["allocation_note"])
        increment = next(row for row in replacement["cost_lines"] if row["id"] == proposal["id"])
        self.assertEqual(increment["allocation"], "exclusive")
        self.assertEqual(result["metrics"]["committed_total"], 241200)
        self.assertEqual(result["metrics"]["actual_total"], 90800)

    def test_map_uses_only_known_project_cities_and_unknown_stays_unknown(self):
        anchors = []
        for project in projects.list_projects():
            result = self.view(self.fresh(project["id"]))
            anchor = result["geography"]
            anchors.append((anchor["lat"], anchor["lng"]))
            self.assertEqual(anchor["state"], "MA")
            self.assertTrue(anchor["approximate"])
            self.assertIn("not a surveyed", anchor["source"])
        self.assertEqual(len(set(anchors)), 3)
        unknown = self.fresh()
        unknown["project"]["demo_project_id"] = "unmapped_project"
        self.assertIsNone(project_resources.geography(unknown)["lat"])

    def test_completion_has_history_but_does_not_close_independent_acceptance(self):
        state = self.fresh("riverbend_logistics")
        result = self.view(state)
        electrical = next(row for row in result["calendar"] if row.get("task_id") == "t_electrical")
        self.assertEqual(electrical["status"], "completed")
        self.assertTrue(electrical["evidence_ids"])
        field = next(row for row in result["readiness"]["checks"] if row["id"] == "field")
        self.assertEqual(field["status"], "waiting")
        self.assertEqual(result["readiness"]["next_milestone"]["task_id"], "t_verify")


if __name__ == "__main__":
    unittest.main()
