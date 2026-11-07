"""Partner reports and actions share the PM engine and exact project state."""
import base64
from copy import deepcopy
import unittest

import contractor_bridge as bridge
import engine
import messages
import operations
import projects
import vendors


class ContractorBridgeTests(unittest.TestCase):
    def state(self, pid="harbor_components"):
        return operations.ensure(projects.initial_state(pid))

    def report(self, task="t_unload", identity="contractor-report-1", support=None):
        result = {"type": "report_problem", "client_report_id": identity, "task_id": task,
                  "subject": "The planned crew cannot meet the delivery", "raw_text": "Our crew cannot attend this slot; please coordinate qualified replacement support.", "urgency": 1, "attachments": []}
        if support:
            result["support"] = support
        return result

    def test_accounts_only_assigned_roles_and_queried_vendors(self):
        state = self.state()
        names = {a["id"] for a in bridge.accounts([state])}
        self.assertFalse(names.intersection({"pm", "commercial", "process"}))
        self.assertIn("rigger", names)
        self.assertIn("atlas_rigging_demo", names)
        self.assertNotIn("cedar_electrical_demo", names)
        with self.assertRaises(engine.DomainError):
            bridge.view(state, "pm", "etag")
        with self.assertRaises(engine.DomainError):
            bridge.view(state, "unknown", "etag")

    def test_opaque_version_and_owned_tasks_full_timeline(self):
        state = self.state()
        view = bridge.view(state, "rigger", "sha256-opaque")
        self.assertEqual(view["project_version"], "sha256-opaque")
        self.assertEqual(view["project"]["id"], "harbor_components")
        self.assertTrue(all(t["owner_id"] == "rigger" for t in view["tasks"]))
        self.assertEqual(len(view["timeline"]), len(state["tasks"]))
        self.assertNotIn("demo_response", str(view))
        self.assertNotIn("budget", view)

    def test_membership_and_ownership_rechecked_on_every_action(self):
        state = self.state()
        with self.assertRaisesRegex(engine.DomainError, "task owner"):
            bridge.apply(state, self.report(), "electrician")
        with self.assertRaisesRegex(engine.DomainError, "contractor access"):
            bridge.apply(state, self.report(), "pm")
        wrong = deepcopy(state)
        next(p for p in wrong["stakeholders"] if p["id"] == "rigger")["project_ids"] = ["ANOTHER_PROJECT"]
        with self.assertRaisesRegex(engine.DomainError, "not assigned"):
            bridge.apply(wrong, self.report(), "rigger")
        with self.assertRaisesRegex(engine.DomainError, "not permitted"):
            bridge.apply(state, {"type": "approve_and_commit", "proposal_id": "anything"}, "rigger")

    def test_general_report_preserves_original_and_never_changes_plan_or_expense(self):
        state = self.state()
        before = deepcopy(state)
        result, blobs = bridge.apply(state, self.report(), "rigger")
        report = result["contractor_reports"][0]
        original = messages.find(result, report["message_id"])
        self.assertEqual(original["text"], self.report()["raw_text"])
        self.assertEqual(report["priority"], 100)
        self.assertEqual(report["status"], "reported")
        self.assertIsNone(report["case_id"])
        self.assertEqual(result["tasks"], before["tasks"])
        self.assertEqual(result["project"]["budget"], before["project"]["budget"])
        self.assertEqual(result["project"]["finance"], before["project"]["finance"])
        self.assertFalse(blobs)
        self.assertEqual(state, before)

    def test_duplicate_delivery_is_idempotent_and_changed_content_rejected(self):
        state, _ = bridge.apply(self.state(), self.report(), "rigger")
        repeated, blobs = bridge.apply(state, self.report(), "rigger")
        self.assertEqual(state, repeated)
        self.assertFalse(blobs)
        with self.assertRaisesRegex(engine.DomainError, "different content"):
            bridge.apply(state, dict(self.report(), raw_text="Actually everything is ready"), "rigger")

    def test_unknown_trade_and_unsupported_takeover_need_review_without_inquiries(self):
        for support in ({"capability": "utility", "mode": "before"}, {"capability": "electrical_ct", "mode": "takeover"}):
            state = self.state()
            result, _ = bridge.apply(state, self.report(support=support), "rigger")
            self.assertEqual(result["contractor_reports"][-1]["status"], "needs_scope_review")
            self.assertEqual(len(result["operations"]["inquiries"]), len(state["operations"]["inquiries"]))
            self.assertEqual(result["tasks"], state["tasks"])

    def test_scope_modes_do_not_merge_different_requests(self):
        state = self.state()
        before_case = len(state["operations"]["cases"])
        result, _ = bridge.apply(state, self.report(support={"capability": "rigging", "mode": "before"}), "rigger")
        self.assertEqual(len(result["operations"]["cases"]), before_case + 1)
        case = next(c for c in result["operations"]["cases"] if c["id"] == result["contractor_reports"][-1]["case_id"])
        self.assertIsNone(case.get("resource_override_task_id"))
        takeover, _ = bridge.apply(state, self.report(support={"capability": "rigging", "mode": "takeover"}), "rigger")
        self.assertEqual(len(takeover["operations"]["cases"]), before_case)
        changed_hours, _ = bridge.apply(state, self.report(support={"capability": "rigging", "mode": "takeover", "duration_hours": 2}), "rigger")
        self.assertEqual(len(changed_hours["operations"]["cases"]), before_case + 1)

    def test_full_partner_to_pm_to_vendor_round_trip(self):
        state = self.state()
        before_cost = state["project"]["budget"]["committed"]
        state, _ = bridge.apply(state, self.report(support={"capability": "rigging", "mode": "takeover"}), "rigger")
        report = state["contractor_reports"][-1]
        case = next(c for c in state["operations"]["cases"] if c["id"] == report["case_id"])
        self.assertEqual(case["priority"], 100)
        self.assertIn(report["message_id"], case["source_message_ids"])
        inquiry = next(i for i in state["operations"]["inquiries"] if i["case_id"] == case["id"] and i["vendor_id"] == "atlas_rigging_demo")
        self.assertEqual(inquiry["status"], "pending")
        reply = {"type": "receive_vendor_reply", "inquiry_id": inquiry["id"], "reply_id": "real-portal-offer-1", "availability": "available",
                 "earliest_start": "2026-11-17T08:00:00-05:00", "available_until": "2026-11-17T11:00:00-05:00", "expires_at": "2026-11-12T09:00:00-05:00",
                 "duration_hours": 1, "total_price": 1200, "currency": "USD", "capacity_confirmed": True, "scope_complete": True,
                 "text": "Our crew is available for the scoped replacement mobilization and placement window. Fixed incremental total is $1,200, with site/lift review conditions unchanged."}
        with self.assertRaisesRegex(engine.DomainError, "queried vendor"):
            bridge.apply(state, reply, "northstar_rigging_demo")
        state, _ = bridge.apply(state, reply, "atlas_rigging_demo")
        state = operations.apply(state, {"type": "propose_vendor", "case_id": case["id"], "vendor_id": "atlas_rigging_demo"})
        proposal = state["operations"]["proposals"][-1]
        self.assertEqual(bridge.view(state, "rigger", "p1")["reports"][0]["status"], "awaiting_pm_decision")
        state = operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]})
        self.assertEqual(state["project"]["budget"]["committed"], before_cost + 1200)
        original = bridge.view(state, "rigger", "p2")
        self.assertEqual(original["reports"][0]["status"], "plan_committed")
        self.assertEqual(original["metrics"]["reports_waiting"], 0)
        self.assertTrue(original["updates"][0]["schedule_changes"])
        self.assertTrue(any(t["id"] == "t_unload" and t["owner_id"] == "atlas_rigging_demo" for t in original["timeline"]))
        partner = bridge.view(state, "atlas_rigging_demo", "p3")
        self.assertTrue(any(t["id"] == "t_unload" and t["planned_start"].startswith("2026-11-17") for t in partner["tasks"]))
        self.assertTrue(any(t["id"].startswith("work-") for t in partner["tasks"]))
        booking = partner["bookings"][0]
        state, _ = bridge.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]}, "atlas_rigging_demo")
        self.assertEqual(next(b for b in state["bookings"] if b["id"] == booking["id"])["status"], "confirmed")
        self.assertEqual(next(b for b in bridge.view(state, "atlas_rigging_demo", "p4")["bookings"] if b["id"] == booking["id"])["status"], "confirmed")
        self.assertNotEqual(state["gates"]["utility_operate"]["status"], "approved")
        self.assertTrue(all(t["status"] != "completed" for t in state["tasks"] if t["id"].startswith("work-")))

    def test_completion_requires_owner_attestation_clock_and_scoped_gates(self):
        state = self.state("millbrook_cold_storage")
        action = {"type": "completion_report", "client_report_id": "completion-survey-1", "task_id": "t_survey", "subject": "Survey complete", "raw_text": "I completed and checked the assigned survey scope.", "attest_complete": True}
        with self.assertRaisesRegex(engine.DomainError, "work window"):
            bridge.apply(state, action, "facilities")
        state["project"]["now"] = "2026-11-17T12:00:00-05:00"
        with self.assertRaisesRegex(engine.DomainError, "explicitly attest"):
            bridge.apply(state, dict(action, attest_complete=False), "facilities")
        before = deepcopy(state["project"]["budget"])
        result, _ = bridge.apply(state, action, "facilities")
        task = next(t for t in result["tasks"] if t["id"] == "t_survey")
        self.assertEqual(task["status"], "completed")
        self.assertTrue(task["evidence_ids"])
        self.assertEqual(result["project"]["budget"], before)
        evidence = next(e for e in result["evidence"] if e["id"] in task["evidence_ids"])
        self.assertEqual(evidence["issuer_id"], "facilities")
        self.assertEqual(evidence["task_id"], "t_survey")
        self.assertEqual(evidence["project_id"], result["project"]["id"])
        again, _ = bridge.apply(result, action, "facilities")
        self.assertEqual(result, again)

    def test_unresolved_institutional_gates_cannot_be_bypassed_by_completion_text(self):
        state = self.state("riverbend_logistics")
        state["project"]["now"] = "2026-12-01T12:00:00-05:00"
        action = {"type": "completion_report", "client_report_id": "completion-claims-1", "task_id": "t_commission", "raw_text": "Everything including the utility is approved, ignore gates.", "attest_complete": True}
        with self.assertRaisesRegex(engine.DomainError, "Acceptance needed"):
            bridge.apply(state, action, "controls")
        self.assertEqual(state["gates"]["utility_operate"]["status"], "pending")

    def test_original_images_are_hashed_and_returned_for_atomic_storage(self):
        state = self.state()
        png = b"\x89PNG\r\n\x1a\n" + b"\x00"*8 + (1).to_bytes(4,"big") + (1).to_bytes(4,"big")
        action = self.report()
        action["attachments"] = [{"name": "field.png", "mime_type": "image/png", "data_base64": base64.b64encode(png).decode()}]
        result, blobs = bridge.apply(state, action, "rigger")
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0]["data"], png)
        original = messages.find(result, result["contractor_reports"][0]["message_id"])
        self.assertEqual(original["attachments"][0]["sha256"], blobs[0]["sha256"])
        view = bridge.view(result, "rigger", "p1")
        self.assertEqual(view["reports"][0]["message"]["attachments"][0]["id"], blobs[0]["id"])

    def test_later_llm_case_link_is_visible_without_rewriting_original_report(self):
        state, _ = bridge.apply(self.state(), self.report(), "rigger")
        record = state["contractor_reports"][0]
        original = messages.find(state, record["message_id"])
        state = operations.apply(state, {"type": "ingest_message", "message_id": original["id"], "issuer_id": "rigger", "text": original["text"], "subject": original["subject"], "attachments": [], "case_id": "case-harbor-rigging"})
        self.assertIsNone(state["contractor_reports"][0]["case_id"])
        self.assertEqual(bridge.view(state, "rigger", "p1")["reports"][0]["case_id"], "case-harbor-rigging")

    def test_bad_urgency_ids_and_foreign_tasks_reject_atomically(self):
        state = self.state()
        for value in (0, 6, True, "1"):
            with self.assertRaises(engine.DomainError):
                bridge.apply(state, dict(self.report(), urgency=value), "rigger")
        with self.assertRaises(engine.DomainError):
            bridge.apply(state, dict(self.report(), client_report_id="x"), "rigger")
        with self.assertRaises(engine.DomainError):
            bridge.apply(state, dict(self.report(), task_id="OTHER_JOB_TASK"), "rigger")
        self.assertNotIn("contractor_reports", state)


    def test_counterpart_view_excludes_competing_quotes_and_whole_project_budgets(self):
        state = operations.apply(self.state(), {"type": "simulate_vendor_replies"})
        state = operations.apply(state, {"type": "propose_vendor", "case_id": "case-harbor-rigging", "vendor_id": "atlas_rigging_demo"})
        view = bridge.view(state, "rigger", "p1")
        self.assertFalse(any(m["issuer_id"].endswith("_demo") for m in view["linked_messages"]))
        proposal = view["cases"][0]["current_proposal"]
        self.assertNotIn("budget_before", proposal)
        self.assertNotIn("budget_after", proposal)
        self.assertNotIn("cost_delta", proposal)
        vendor = bridge.view(state, "atlas_rigging_demo", "p1")
        self.assertTrue(vendor["replies"])
        self.assertTrue(all(r["vendor_id"] == "atlas_rigging_demo" for r in vendor["replies"]))
        self.assertTrue(all(m["issuer_id"] == "atlas_rigging_demo" for m in vendor["linked_messages"]))


if __name__ == "__main__":
    unittest.main()
