"""Domain checks for PM cases, immutable originals and conditional vendor packages."""
from copy import deepcopy
from datetime import timedelta
import unittest

import dashboard
import engine
import operations
import phases
import projects
import vendors


class OperationsTests(unittest.TestCase):
    def fresh(self, pid="harbor_components"):
        return operations.ensure(projects.initial_state(pid))

    def quoted(self, pid="harbor_components"):
        state = self.fresh(pid)
        return operations.apply(state, {"type": "simulate_vendor_replies"})

    def proposed(self, pid="harbor_components", choice=0):
        state = self.quoted(pid)
        case = operations.summarize(state)["cases"][0]
        vendor = [o for o in case["options"] if o["eligible"]][choice]
        return operations.apply(state, {"type": "propose_vendor", "case_id": case["id"], "vendor_id": vendor["vendor_id"]})

    def committed(self, pid="harbor_components"):
        state = self.proposed(pid)
        proposal = state["operations"]["proposals"][-1]
        return operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]}, actor_id=proposal["required_approver_id"])

    def test_additive_initialization_is_idempotent_and_pure(self):
        raw = projects.initial_state("harbor_components")
        original = deepcopy(raw)
        state = operations.ensure(raw)
        self.assertEqual(raw, original)
        self.assertEqual(state, operations.ensure(state))
        self.assertEqual(state["project"]["budget"], raw["project"]["budget"])
        self.assertEqual(len(state["operations"]["cases"]), 1)
        self.assertEqual(len(state["operations"]["inquiries"]), 3)
        self.assertFalse(state["operations"]["replies"])
        self.assertTrue(all(i["status"] == "pending" for i in state["operations"]["inquiries"]))

    def test_three_projects_have_specific_roles_and_distinct_scope(self):
        capabilities = set()
        for project in projects.list_projects():
            state = self.fresh(project["id"])
            case = operations.summarize(state)["cases"][0]
            capabilities.add(case["vendor_capability"])
            self.assertGreaterEqual(len(case["stakeholder_ids"]), 4)
            self.assertIn(case["source_message_ids"][0], {m["id"] for m in state["operations"]["messages"]})
        self.assertEqual(capabilities, {"rigging", "electrical_ct", "epc_interconnection"})

    def test_public_catalog_does_not_leak_future_responses(self):
        view = operations.summarize(self.fresh())
        self.assertTrue(all("demo_response" not in v for v in view["vendors"]))
        self.assertTrue(all("demo_response" not in v for v in vendors.public_profiles()))
        self.assertTrue(all(o["total_price"] is None for o in view["cases"][0]["options"]))

    def test_no_proposal_without_received_quote(self):
        state = self.fresh()
        with self.assertRaisesRegex(engine.DomainError, "reply"):
            operations.apply(state, {"type": "propose_vendor", "case_id": "case-harbor-rigging", "vendor_id": "atlas_rigging_demo"})

    def test_unknown_price_and_expired_qualification_are_excluded(self):
        state = self.quoted()
        options = {o["vendor_id"]: o for o in operations.summarize(state)["cases"][0]["options"]}
        self.assertIsNone(options["bay_rigging_demo"]["total_price"])
        self.assertFalse(options["bay_rigging_demo"]["eligible"])
        self.assertFalse(options["expired_trade_demo"]["eligible"])
        self.assertTrue(any("expired" in r for r in options["expired_trade_demo"]["exclusion_reasons"]))

    def test_reply_simulation_idempotent_preserves_raw_quote_evidence(self):
        state = self.quoted()
        again = operations.apply(state, {"type": "simulate_vendor_replies"})
        self.assertEqual(state["operations"]["replies"], again["operations"]["replies"])
        self.assertEqual(state["operations"]["messages"], again["operations"]["messages"])
        self.assertEqual(state["project"]["revision"], again["project"]["revision"])
        for quote in state["operations"]["replies"]:
            self.assertTrue(quote["text"])
            self.assertIn("message-" + quote["id"], {m["id"] for m in state["operations"]["messages"]})

    def test_immutable_original_allows_separate_reading_summary_and_later_case_link(self):
        state = self.fresh()
        payload = {"type": "ingest_message", "message_id": "original-1", "issuer_id": "electrician", "subject": "Additional crew", "text": "Please source qualified support.", "attachments": [{"name": "field.png", "sha256": "a"*64, "url": "/api/attachments/blob1", "mime_type": "image/png"}]}
        state = operations.apply(state, payload)
        message = state["operations"]["messages"][-1]
        original_hash = message["content_hash"]
        message["reading_summary"] = {"text": "Crew needed", "mode": "LLM"}
        request = {"title": "Qualified support", "why": "A scope review is needed", "request": "Qualified electrical support", "vendor_capability": "electrical_ct", "affected_task_ids": ["t_verify"], "stakeholder_ids": ["electrician"], "duration_hours": 4}
        linked = operations.apply(state, dict(payload, validated_request=request))
        linked_message = next(m for m in linked["operations"]["messages"] if m["id"] == "original-1")
        self.assertEqual(original_hash, linked_message["content_hash"])
        self.assertTrue(linked_message["case_id"])
        self.assertIn("reading_summary", linked_message)
        self.assertIn("customer_window", linked["operations"]["cases"][-1]["required_gates"])
        with self.assertRaisesRegex(engine.DomainError, "immutable"):
            operations.apply(linked, dict(payload, text="Changed original"))

    def test_replies_reject_strings_as_booleans_and_wrong_scope(self):
        state = self.fresh()
        inquiry = state["operations"]["inquiries"][0]
        payload = {"type": "receive_vendor_reply", "inquiry_id": inquiry["id"], "reply_id": "reply-test", "availability": "unavailable", "duration_hours": 1, "text": "No crew", "scope_complete": "false"}
        with self.assertRaisesRegex(engine.DomainError, "boolean"):
            operations.apply(state, payload, actor_id=inquiry["vendor_id"])
        payload.update(scope_complete=False, project_id="OTHER_PROJECT")
        with self.assertRaisesRegex(engine.DomainError, "different project"):
            operations.apply(state, payload, actor_id=inquiry["vendor_id"])
        payload.pop("project_id")
        with self.assertRaisesRegex(engine.DomainError, "queried vendor"):
            operations.apply(state, payload)

    def test_duplicate_raw_reply_is_idempotent_but_changed_reply_needs_new_id(self):
        state = self.fresh()
        inquiry = state["operations"]["inquiries"][0]
        payload = {"type": "receive_vendor_reply", "inquiry_id": inquiry["id"], "reply_id": "reply-no-crew", "availability": "unavailable", "duration_hours": 1, "text": "No crew available"}
        state = operations.apply(state, payload, actor_id=inquiry["vendor_id"])
        again = operations.apply(state, payload, actor_id=inquiry["vendor_id"])
        self.assertEqual(state["operations"]["replies"], again["operations"]["replies"])
        self.assertEqual(state["project"]["revision"], again["project"]["revision"])
        with self.assertRaisesRegex(engine.DomainError, "immutable"):
            operations.apply(state, dict(payload, text="Actually available"), actor_id=inquiry["vendor_id"])

    def test_complete_cost_and_downstream_dates_apply_only_after_approval(self):
        state = self.proposed()
        proposal = state["operations"]["proposals"][-1]
        self.assertEqual(state["project"]["budget"]["committed"], 240000)
        self.assertEqual(proposal["budget_after"], 241200)
        self.assertEqual(operations.summarize(state)["proposed_cost"], 1200)
        old_actual = sum(x["actual"] for x in state["project"]["finance"]["lines"])
        committed = operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]})
        tasks = {t["id"]: t for t in committed["tasks"]}
        self.assertTrue(tasks["t_unload"]["planned_start"].startswith("2026-11-17"))
        self.assertTrue(tasks["t_electrical"]["planned_start"].startswith("2026-11-21"))
        self.assertIn("work-case-harbor-rigging", tasks["t_unload"]["predecessors"])
        self.assertEqual(committed["project"]["budget"]["committed"], 241200)
        self.assertEqual(sum(x["actual"] for x in committed["project"]["finance"]["lines"]), old_actual)
        self.assertEqual(sum(x["committed"] for x in committed["project"]["finance"]["lines"]), 241200)
        self.assertTrue(all(b["status"] == "required" for b in committed["operations"]["bookings"]))
        self.assertEqual(operations.summarize(committed)["proposed_cost"], 0)
        self.assertFalse(engine.project_complete(committed))

    def test_double_commit_does_not_double_spend(self):
        state = self.committed()
        before = deepcopy(state)
        proposal = state["operations"]["proposals"][-1]
        state = operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]})
        self.assertEqual(state, before)

    def test_pm_cannot_approve_over_delegation_or_forge_actor_in_payload(self):
        state = self.proposed("millbrook_cold_storage")
        proposal = state["operations"]["proposals"][-1]
        self.assertEqual(proposal["required_approver_id"], "commercial")
        before = deepcopy(state)
        with self.assertRaisesRegex(engine.DomainError, "commercial"):
            operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"], "actor_id": "commercial"})
        self.assertEqual(state, before)
        pending = operations.apply(state, {"type": "request_approval", "proposal_id": proposal["id"]})
        self.assertEqual(pending["operations"]["proposals"][-1]["status"], "pending")
        approved = operations.apply(pending, {"type": "simulate_authority_response", "proposal_id": proposal["id"]}, actor_id="commercial")
        self.assertEqual(approved["operations"]["proposals"][-1]["status"], "approved")
        committed = operations.apply(approved, {"type": "commit_proposal", "proposal_id": proposal["id"]})
        self.assertEqual(committed["project"]["budget"]["committed"], 398600)
        self.assertEqual(committed["gates"]["utility_install"]["status"], "pending")
        self.assertEqual(committed["gates"]["utility_operate"]["status"], "pending")

    def test_revision_and_quote_expiry_invalidate_approval(self):
        for reason in ("revision", "time"):
            state = self.proposed()
            proposal = state["operations"]["proposals"][-1]
            state = operations.apply(state, {"type": "approve_proposal", "proposal_id": proposal["id"]})
            if reason == "revision":
                state["project"]["revision"] += 1
            else:
                state["project"]["now"] = "2026-11-13T09:00:00-05:00"
            view = operations.summarize(state)
            self.assertEqual(view["cases"][0]["current_proposal"]["status"], "stale")
            with self.assertRaises(engine.DomainError):
                operations.apply(state, {"type": "commit_proposal", "proposal_id": proposal["id"]})
            self.assertEqual(state["project"]["budget"]["committed"], 240000)

    def test_delegate_changed_after_approval_requires_new_decision(self):
        state = self.proposed()
        proposal = state["operations"]["proposals"][-1]
        state = operations.apply(state, {"type": "approve_proposal", "proposal_id": proposal["id"]})
        next(p for p in state["stakeholders"] if p["id"] == "pm")["approval_limit"] = 100
        with self.assertRaisesRegex(engine.DomainError, "authority changed"):
            operations.apply(state, {"type": "commit_proposal", "proposal_id": proposal["id"]})

    def test_profile_expiring_during_work_is_excluded(self):
        state = self.quoted()
        profiles = vendors.list_vendors()
        next(v for v in profiles if v["id"] == "atlas_rigging_demo")["qualifications"][0]["expires_at"] = "2026-11-17T09:00:00-05:00"
        option = next(o for o in operations.summarize(state, profiles)["cases"][0]["options"] if o["vendor_id"] == "atlas_rigging_demo")
        self.assertFalse(option["eligible"])

    def test_other_project_reservation_blocks_commit_and_confirmation(self):
        state = self.proposed()
        proposal = state["operations"]["proposals"][-1]
        state = operations.apply(state, {"type": "approve_proposal", "proposal_id": proposal["id"]})
        profiles = vendors.list_vendors()
        vendor = next(v for v in profiles if v["id"] == proposal["vendor_id"])
        vendor["reservations"] = [{"project_id": "OTHER", "case_id": "OTHER", "status": "confirmed", "start": "2026-11-17T08:00:00-05:00", "end": "2026-11-17T12:00:00-05:00"}]
        with self.assertRaisesRegex(engine.DomainError, "conflicts"):
            operations.apply(state, {"type": "commit_proposal", "proposal_id": proposal["id"]}, vendor_profiles=profiles)
        committed = operations.apply(state, {"type": "commit_proposal", "proposal_id": proposal["id"]})
        booking = committed["operations"]["bookings"][0]
        with self.assertRaisesRegex(engine.DomainError, "conflicts"):
            operations.apply(committed, {"type": "confirm_booking", "booking_id": booking["id"]}, actor_id=booking["recipient_id"], vendor_profiles=profiles)

    def test_rejection_and_clarification_preserve_open_problem(self):
        state = self.proposed()
        proposal = state["operations"]["proposals"][-1]
        rejected = operations.apply(state, {"type": "reject_proposal", "proposal_id": proposal["id"], "reason": "Need another date"})
        self.assertEqual(rejected["operations"]["cases"][0]["status"], "clarification_required")
        self.assertEqual(rejected["project"]["budget"]["committed"], 240000)
        clarified = operations.apply(state, {"type": "request_clarification", "case_id": proposal["case_id"], "text": "Please verify the lift plan scope."})
        self.assertEqual(clarified["operations"]["proposals"][-1]["status"], "superseded")
        self.assertFalse(clarified["alerts"][-1]["resolved"])

    def test_pm_approval_does_not_confirm_booking_or_complete_work(self):
        state = self.committed("riverbend_logistics")
        booking = state["operations"]["bookings"][0]
        with self.assertRaisesRegex(engine.DomainError, "counterpart"):
            operations.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]})
        confirmed = operations.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]}, actor_id=booking["recipient_id"])
        self.assertEqual(confirmed["operations"]["bookings"][0]["status"], "confirmed")
        task = next(t for t in confirmed["tasks"] if t["id"] == booking["task_id"])
        self.assertEqual(task["status"], "planned")
        self.assertEqual(confirmed["gates"]["field_verified"]["status"], "pending")
        self.assertEqual(confirmed["gates"]["utility_operate"]["status"], "pending")

    def test_scope_hold_prevents_generic_engine_bypassing_reported_problem(self):
        state = self.fresh("riverbend_logistics")
        case = state["operations"]["cases"][0]
        gate = state["gates"][case["scope_hold_gate_id"]]
        self.assertIn(gate["id"], next(t for t in state["tasks"] if t["id"] == "t_verify")["required_gates"])
        ev = {"id": "BYPASS", "project_id": state["project"]["id"], "design_revision": "V3", "verified": True, "issuer_id": "engineer", "kind": "acceptance", "effective_at": state["project"]["now"]}
        with self.assertRaisesRegex(engine.DomainError, "prerequisites"):
            engine._update_gate(state, gate["id"], "approved", "engineer", ev)

    def test_generic_pending_plan_is_invalidated_and_phase_contains_package(self):
        state = self.proposed()
        state["proposals"].append({"id": "legacy", "status": "approved"})
        proposal = state["operations"]["proposals"][-1]
        committed = operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]})
        self.assertEqual(committed["proposals"][0]["status"], "stale")
        task = next(t for t in committed["tasks"] if t["id"].startswith("work-"))
        self.assertEqual(task["phase_id"], "installation")
        self.assertEqual(phases._task_phase(task), "installation")

    def test_design_change_can_trigger_fresh_inquiries(self):
        state = self.quoted()
        old_count = len(state["operations"]["inquiries"])
        state["project"]["design_revision"] = "V4"
        state["project"]["revision"] += 1
        state = operations.apply(state, {"type": "request_availability", "case_id": "case-harbor-rigging"})
        self.assertEqual(len(state["operations"]["inquiries"]), old_count + 3)
        self.assertTrue(all(i["design_revision"] == "V4" for i in state["operations"]["inquiries"][-3:]))

    def test_tampered_proposal_cannot_change_price_under_existing_approval(self):
        state = self.proposed()
        proposal = state["operations"]["proposals"][-1]
        proposal["cost_delta"] = 1
        with self.assertRaisesRegex(engine.DomainError, "immutable"):
            operations.apply(state, {"type": "approve_and_commit", "proposal_id": proposal["id"]})


    def test_all_added_packages_finish_through_existing_evidence_and_gate_tools(self):
        for pid in ("harbor_components", "millbrook_cold_storage", "riverbend_logistics"):
            with self.subTest(project=pid):
                state = self.committed(pid)
                for step in range(80):
                    if engine.project_complete(state):
                        break
                    action = engine.recommend(state)["action"]
                    state = engine.apply_action(state, action)
                    response_count = 0
                    for request in list(state["requests"]):
                        if request.get("status") in ("pending", "sent", "open"):
                            reply = projects.actor_response(state, request)
                            if reply:
                                state = engine.apply_event(state, reply)
                                response_count += 1
                    state = operations.ensure(state)
                    if action["type"] == "wait" and not response_count:
                        deadlines = [r["due_at"] for r in state["requests"] if r.get("status") == "acknowledged" and r.get("due_at") and engine._dt(r["due_at"]) > engine._dt(state["project"]["now"])]
                        if deadlines:
                            state = engine.apply_event(state, {"id": "ops-test-clock-" + str(step), "type": "clock_advance", "at": min(deadlines)})
                        else:
                            break
                self.assertTrue(engine.project_complete(state))
                case = operations.summarize(state)["cases"][0]
                self.assertEqual(case["status"], "resolved")
                package = next(t for t in state["tasks"] if t["id"] == case["work_package_id"])
                self.assertEqual(package["status"], "completed")
                self.assertTrue(package["evidence_ids"])
                self.assertTrue(engine._gate_ready(state, case["scope_hold_gate_id"]))

    def test_booking_has_portfolio_capacity_window_and_superseded_cannot_confirm(self):
        state = self.committed()
        booking = state["operations"]["bookings"][0]
        self.assertEqual(booking["vendor_id"], "atlas_rigging_demo")
        self.assertEqual(booking["start"], booking["planned_start"])
        self.assertGreater(engine._dt(booking["end"]), engine._dt(booking["start"]))
        next(b for b in state["bookings"] if b["id"] == booking["id"])["status"] = "superseded"
        with self.assertRaisesRegex(engine.DomainError, "superseded"):
            operations.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]}, actor_id=booking["recipient_id"])

    def test_generic_correction_infers_installation_dependency_and_rejects_acceptance_cycle(self):
        state = self.fresh("riverbend_logistics")
        request = {"title": "Another correction", "why": "A field observation", "request": "Qualified electrical scope review", "vendor_capability": "electrical_ct", "affected_task_ids": ["t_verify"], "stakeholder_ids": ["electrician"], "duration_hours": 4}
        validated = operations._validate_request(state, request)
        self.assertIn("t_electrical", validated["predecessor_task_ids"])
        with self.assertRaisesRegex(engine.DomainError, "downstream"):
            operations._validate_request(state, dict(request, required_gates=["field_verified"]))


if __name__ == "__main__":
    unittest.main()
