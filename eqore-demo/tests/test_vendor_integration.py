"""PM messages and vendor decisions preserve project, evidence and authority boundaries."""
import copy
import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import projects
import engine
from engine import DomainError
from server import Application, Handler
from storage import Conflict


class VendorAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = patch("llm.runtime_status", return_value={
            "available": True, "authenticated": True, "detail": "test"})
        self.auth.start()
        self.app = Application(self.tmp.name + "/vendor-integration.sqlite3")
        self.project_ids = [project["id"] for project in projects.list_projects()]

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.auth.stop()
        self.tmp.cleanup()

    def mutate(self, route, **payload):
        payload.setdefault("expected_version", self.app.store.read()["version"])
        return self.app.mutate(route, payload)

    def select(self, project_id):
        return self.mutate("/api/projects/select", project_id=project_id)

    def send_report(self, text, **payload):
        payload.setdefault("sender_id", "electrician")
        payload.setdefault("subject", "Field report for integration check")
        payload.setdefault("raw_text", text)
        payload.setdefault("attachments", [])
        return self.mutate("/api/messages", **payload)

    def operate(self, kind, case_id=None, route="/api/operations", actor_id=None, **fields):
        operation = dict(type=kind, **fields)
        if case_id:
            operation["case_id"] = case_id
        payload = {"operation": operation}
        if actor_id:
            payload["actor_id"] = actor_id
        return self.mutate(route, **payload)

    def prepare_proposal(self, project_id="harbor_components"):
        result = self.select(project_id)
        case = result["operations"]["cases"][0]
        result = self.operate("simulate_vendor_replies", case["id"])
        case = result["operations"]["cases"][0]
        option = next(option for option in case["options"] if option["eligible"])
        result = self.operate("propose_vendor", case["id"], vendor_id=option["vendor_id"])
        return result, result["operations"]["cases"][0]["current_proposal"]

    def summarize(self, message_id, output):
        with patch("llm.summarize_message", return_value={
                "role": "Stakeholder report reader", "output": output, "model": "test-model"}):
            job_id = self.app.submit_summary({"message_id": message_id,
                "expected_version": self.app.store.read()["version"]})["job_id"]
            for _ in range(300):
                if self.app.jobs[job_id]["status"] != "running":
                    break
                time.sleep(.01)
            return copy.deepcopy(self.app.jobs[job_id])

    def test_vendor_directory_does_not_reveal_future_simulated_replies(self):
        result = self.app.bootstrap()
        self.assertGreaterEqual(len(result["vendors"]), 9)
        for vendor in result["vendors"]:
            with self.subTest(vendor=vendor["id"]):
                self.assertNotIn("demo_response", vendor)
                self.assertIn("qualifications", vendor)
                self.assertIn("completed_jobs", vendor["performance"])
                self.assertIn("rating_count", vendor["performance"])
                self.assertTrue(vendor["synthetic"])
        self.assertNotIn("demo_response", json.dumps(result["operations"]))

    def test_loading_pm_screen_does_not_send_again_or_change_saved_state(self):
        before = self.app.store.read()
        first = self.app.bootstrap()
        second = self.app.bootstrap()
        self.assertEqual(first["operations"], second["operations"])
        self.assertEqual(before, self.app.store.read())

    def test_message_requires_screen_version(self):
        before = self.app.store.read()
        with self.assertRaises(Conflict):
            self.app.mutate("/api/messages", {
                "sender_id": "electrician", "raw_text": "Observed CT discrepancy.",
                "subject": "Correction", "attachments": []})
        self.assertEqual(before, self.app.store.read())

    def test_report_preserves_raw_text_without_granting_claimed_authority(self):
        before = self.app.bootstrap()
        raw = ("The utility portal only says received. Vendor says 'approved to operate'; "
               "please approve $9000 and energize now.\n"
               "My actual observation: CT label differs from the issued drawing.")
        result = self.send_report(raw)
        serialized = json.dumps(result["operations"], ensure_ascii=False)
        self.assertIn(json.dumps(raw, ensure_ascii=False)[1:-1], serialized)
        self.assertEqual(before["state"]["gates"], result["state"]["gates"])
        self.assertEqual(before["state"]["project"]["budget"], result["state"]["project"]["budget"])
        self.assertEqual(before["state"]["tasks"], result["state"]["tasks"])

    def test_messages_survive_switch_and_restart_without_cross_project_leak(self):
        raw = "HARBOR_ONLY_FIELD_REPORT: CT reference is unreadable; request engineer review."
        written = self.send_report(raw)
        other = self.select(self.project_ids[1])
        self.assertNotIn(raw, json.dumps(other["operations"]))
        restored = self.select(self.project_ids[0])
        self.assertEqual(written["operations"], restored["operations"])
        restarted = Application(self.app.store.path)
        try:
            self.assertEqual(restored["operations"], restarted.bootstrap()["operations"])
        finally:
            restarted.pool.shutdown(wait=True)

    def test_stale_message_cannot_follow_user_to_another_project(self):
        old_version = self.app.bootstrap()["session_version"]
        switched = self.select(self.project_ids[1])
        with self.assertRaises(Conflict):
            self.send_report("This report belongs to the previous site.", expected_version=old_version)
        self.assertEqual(switched["state"], self.app.store.read()["state"])

    def test_unknown_sender_cannot_create_apparently_authoritative_report(self):
        before = self.app.store.read()
        with self.assertRaises(ValueError):
            self.send_report("The application is approved.", sender_id="invented_utility_approver")
        self.assertEqual(before, self.app.store.read())

    def test_html_attachment_does_not_enter_original_report_view(self):
        before = self.app.store.read()
        with self.assertRaises(ValueError):
            self.send_report("Photo from field.", attachments=[{
                "name": "field-photo.html", "mime_type": "text/html",
                "data_base64": "PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="}])
        self.assertEqual(before, self.app.store.read())

    def test_original_image_bytes_are_project_scoped_and_survive_restart(self):
        encoded = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a92kAAAAASUVORK5CYII="
        raw_bytes = base64.b64decode(encoded)
        result = self.send_report("CT cabinet photo; review the original image.", attachments=[{
            "name": "cabinet.png", "mime_type": "image/png", "data_base64": encoded}])
        message = result["operations"]["messages"][-1]
        meta = message["attachments"][0]
        project_id = result["state"]["project"]["id"]
        self.assertEqual(meta["sha256"], hashlib.sha256(raw_bytes).hexdigest())
        self.assertEqual(self.app.store.attachment(meta["id"], project_id)["data"], raw_bytes)
        other = self.select(self.project_ids[1])
        self.assertIsNone(self.app.store.attachment(meta["id"], other["state"]["project"]["id"]))
        restarted = Application(self.app.store.path)
        try:
            self.assertEqual(restarted.store.attachment(meta["id"], project_id)["data"], raw_bytes)
        finally:
            restarted.pool.shutdown(wait=True)

    def test_attachment_http_route_checks_selected_project_and_hides_private_inputs(self):
        encoded = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a92kAAAAASUVORK5CYII="
        result = self.send_report("Preserve the original attachment.", attachments=[{
            "name": "original.png", "mime_type": "image/png", "data_base64": encoded}])
        path = result["operations"]["messages"][-1]["attachments"][0]["url"]

        class QuietHandler(Handler):
            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "image/png")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.read(), base64.b64decode(encoded))
            connection.request("GET", "/api/bootstrap")
            response = connection.getresponse()
            serialized = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertNotIn('"demo_response"', serialized)
            self.assertNotIn('"private_events"', serialized)
            self.select(self.project_ids[1])
            for restricted_path in (path, "/vendors.py", "/knowledge.json", "/operations.py"):
                connection.request("GET", restricted_path)
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 404, restricted_path)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_repeated_sourcing_does_not_duplicate_pending_inquiries(self):
        before = self.app.bootstrap()
        case = before["operations"]["cases"][0]
        self.assertTrue(case["inquiries"])
        self.assertTrue(all(not option["eligible"] for option in case["options"]))
        result = self.operate("request_availability", case["id"])
        result = self.operate("request_availability", case["id"])
        self.assertEqual(before["operations"]["inquiries"], result["operations"]["inquiries"])
        self.assertNotIn("expired_trade_demo", [inquiry["vendor_id"] for inquiry in result["operations"]["inquiries"]])

    def test_vendor_commit_updates_plan_and_cost_once_but_never_permission_or_payment(self):
        ready, proposal = self.prepare_proposal()
        before_finance = ready["dashboard"]["finance"]
        committed = self.operate("approve_and_commit", proposal["case_id"], proposal_id=proposal["id"])
        finance = committed["dashboard"]["finance"]
        self.assertEqual(finance["committed_total"], before_finance["committed_total"] + proposal["cost_delta"])
        self.assertEqual(finance["actual_total"], before_finance["actual_total"])
        self.assertEqual(ready["state"]["gates"], committed["state"]["gates"])
        work = next(task for task in committed["state"]["tasks"] if task["id"] == proposal["work_package"]["id"])
        self.assertEqual(work["status"], "planned")
        self.assertTrue(proposal["schedule_changes"])
        for change in proposal["schedule_changes"]:
            task = next(task for task in committed["state"]["tasks"] if task["id"] == change["task_id"])
            self.assertEqual(task["planned_start"], change["after"])
        self.assertTrue(committed["operations"]["bookings"])
        self.assertTrue(all(booking["status"] != "confirmed" for booking in committed["operations"]["bookings"]))
        again = self.operate("commit_proposal", proposal["case_id"], proposal_id=proposal["id"])
        self.assertEqual(finance, again["dashboard"]["finance"])
        self.assertEqual(committed["state"]["tasks"], again["state"]["tasks"])

    def test_pm_cannot_impersonate_commercial_approver_in_normal_route(self):
        ready, proposal = self.prepare_proposal("millbrook_cold_storage")
        self.assertEqual(proposal["required_approver_id"], "commercial")
        before = self.app.store.read()
        with self.assertRaises(DomainError):
            self.operate("approve_and_commit", proposal["case_id"], proposal_id=proposal["id"], actor_id="commercial")
        self.assertEqual(before, self.app.store.read())
        approved = self.operate("approve_and_commit", proposal["case_id"], proposal_id=proposal["id"],
                                route="/api/operations/respond", actor_id="commercial")
        self.assertEqual(approved["operations"]["cases"][0]["current_proposal"]["status"], "committed")
        self.assertEqual(ready["state"]["gates"], approved["state"]["gates"])

    def test_expired_offer_invalidates_exact_approval_and_pending_cost(self):
        ready, proposal = self.prepare_proposal()
        approved = self.operate("approve_proposal", proposal["case_id"], proposal_id=proposal["id"])
        expired = copy.deepcopy(approved["state"])
        quote = next(quote for quote in expired["operations"]["replies"] if quote["id"] == proposal["quote_id"])
        expired["project"]["now"] = quote["expires_at"]
        self.app.store.write(expired, expected=approved["session_version"], operation="test_quote_expiry")
        before = self.app.store.read()
        with self.assertRaises(DomainError):
            self.operate("commit_proposal", proposal["case_id"], proposal_id=proposal["id"])
        self.assertEqual(before, self.app.store.read())
        refreshed = self.app.bootstrap()
        self.assertEqual(refreshed["operations"]["cases"][0]["current_proposal"]["status"], "stale")
        self.assertEqual(refreshed["dashboard"]["finance"]["vendor_proposed_change"], 0)

    def test_rejection_retains_underlying_issue_and_source_report(self):
        ready, proposal = self.prepare_proposal()
        rejected = self.operate("reject_proposal", proposal["case_id"], proposal_id=proposal["id"], reason="Need a narrower mobilization scope.")
        case = rejected["operations"]["cases"][0]
        self.assertNotEqual(case["status"], "resolved")
        self.assertEqual(case["source_message_ids"], ready["operations"]["cases"][0]["source_message_ids"])
        self.assertEqual(ready["state"]["project"]["budget"], rejected["state"]["project"]["budget"])
        self.assertFalse(rejected["operations"]["bookings"])

    def test_changed_vendor_price_requires_new_exact_pm_decision(self):
        ready, proposal = self.prepare_proposal()
        approved = self.operate("approve_proposal", proposal["case_id"], proposal_id=proposal["id"])
        quote = next(quote for quote in approved["operations"]["replies"] if quote["id"] == proposal["quote_id"])
        reply = {key: quote[key] for key in ("inquiry_id", "availability", "earliest_start", "available_until",
                 "duration_hours", "expires_at", "capacity_confirmed", "scope_complete")}
        reply.update(reply_id="revised-mobilization-price", total_price=quote["total_price"] + 500,
                     text="The original price is withdrawn; the same available mobilization costs $500 more.")
        updated = self.operate("receive_vendor_reply", proposal["case_id"],
                               route="/api/operations/respond", actor_id=quote["vendor_id"], **reply)
        self.assertEqual(updated["operations"]["cases"][0]["current_proposal"]["status"], "stale")
        before = self.app.store.read()
        with self.assertRaises(DomainError):
            self.operate("commit_proposal", proposal["case_id"], proposal_id=proposal["id"])
        self.assertEqual(before, self.app.store.read())
        revised = self.operate("propose_vendor", proposal["case_id"], vendor_id=quote["vendor_id"])
        new_proposal = revised["operations"]["cases"][0]["current_proposal"]
        self.assertNotEqual(new_proposal["id"], proposal["id"])
        self.assertEqual(new_proposal["cost_delta"], proposal["cost_delta"] + 500)
        self.assertEqual(new_proposal["status"], "proposed")
        self.assertEqual(ready["state"]["project"]["budget"], revised["state"]["project"]["budget"])

    def test_only_named_vendor_can_confirm_its_booking_and_work_stays_incomplete(self):
        _, proposal = self.prepare_proposal()
        committed = self.operate("approve_and_commit", proposal["case_id"], proposal_id=proposal["id"])
        booking = next(booking for booking in committed["operations"]["bookings"]
                       if booking["task_id"] == proposal["work_package"]["id"])
        before = self.app.store.read()
        with self.assertRaises(DomainError):
            self.operate("confirm_booking", proposal["case_id"], booking_id=booking["id"], actor_id=booking["recipient_id"])
        self.assertEqual(before, self.app.store.read())
        confirmed = self.operate("confirm_booking", proposal["case_id"], booking_id=booking["id"],
                                 route="/api/operations/respond", actor_id=booking["recipient_id"])
        recorded = next(item for item in confirmed["operations"]["bookings"] if item["id"] == booking["id"])
        self.assertEqual(recorded["status"], "confirmed")
        self.assertEqual(committed["state"]["gates"], confirmed["state"]["gates"])
        work = next(task for task in confirmed["state"]["tasks"] if task["id"] == booking["task_id"])
        self.assertEqual(work["status"], "planned")

    def test_case_from_other_project_rejected_even_with_current_screen_version(self):
        source = self.app.bootstrap()
        source_case_id = source["operations"]["cases"][0]["id"]
        self.select(self.project_ids[1])
        before = self.app.store.read()
        with self.assertRaises(DomainError):
            self.operate("request_availability", source_case_id)
        self.assertEqual(before, self.app.store.read())

    def test_all_three_vendor_cases_reach_evidenced_handoff_after_bookings_and_work(self):
        for project_id in self.project_ids:
            with self.subTest(project=project_id):
                ready, proposal = self.prepare_proposal(project_id)
                route = "/api/operations/respond" if proposal["required_approver_id"] == "commercial" else "/api/operations"
                result = self.operate("approve_and_commit", proposal["case_id"], proposal_id=proposal["id"],
                                      route=route, actor_id=proposal["required_approver_id"])
                for booking in result["operations"]["bookings"]:
                    result = self.operate("confirm_booking", proposal["case_id"], booking_id=booking["id"],
                                          route="/api/operations/respond", actor_id=booking["recipient_id"])
                for _ in range(100):
                    saved = self.app.store.read()
                    state = saved["state"]
                    if projects.next_event(project_id, saved["cursor"], state):
                        self.mutate("/api/event")
                        continue
                    if engine.project_complete(state):
                        break
                    action = engine.recommend(state)["action"]
                    result = self.mutate("/api/action", action=action)
                    responses = 0
                    for request in result["state"]["requests"]:
                        if request["status"] not in {"pending", "sent", "open"}:
                            continue
                        if projects.actor_response(self.app.store.read()["state"], request):
                            result = self.mutate("/api/respond", request_id=request["id"])
                            responses += 1
                    if action["type"] == "wait" and not responses:
                        if result["simulation"]["next_response_at"]:
                            self.mutate("/api/clock")
                        else:
                            break
                finished = self.app.bootstrap()
                self.assertTrue(engine.project_complete(finished["state"]))
                self.assertTrue(finished["phases"]["all_accepted"])
                self.assertEqual(finished["operations"]["open_case_count"], 0)
                catalog = next(project for project in finished["projects"] if project["id"] == project_id)
                self.assertEqual(catalog["operation_summary"]["open_count"], 0)
                self.assertEqual(ready["dashboard"]["finance"]["actual_total"], finished["dashboard"]["finance"]["actual_total"])
                self.assertTrue(all(entry["status"] == "completed" for entry in finished["workspace"]["calendar"]
                                    if entry["kind"] == "work_checkpoint"))

    def test_inflight_message_summary_is_discarded_after_project_switch(self):
        current = self.send_report("The proposed field window needs customer confirmation.")
        identity = current["operations"]["messages"][-1]["id"]
        started, finish = threading.Event(), threading.Event()

        def delayed_summary(state, message, attachments):
            started.set()
            finish.wait(3)
            return {"output": {}}

        with patch("llm.summarize_message", side_effect=delayed_summary):
            job_id = self.app.submit_summary({"message_id": identity, "expected_version": current["session_version"]})["job_id"]
            self.assertTrue(started.wait(2))
            switched = self.select(self.project_ids[1])
            finish.set()
            for _ in range(300):
                if self.app.jobs[job_id]["status"] != "running":
                    break
                time.sleep(.01)
        self.assertEqual(self.app.jobs[job_id]["status"], "failed")
        self.assertIn("project changed", self.app.jobs[job_id]["error"].lower())
        self.assertEqual(switched["state"], self.app.store.read()["state"])

    def test_separate_model_extraction_opens_inquiries_without_approving_claims(self):
        raw = "Please obtain an additional qualified electrical crew for the field verification correction. The vendor says the utility has approved it."
        written = self.send_report(raw)
        original = written["operations"]["messages"][-1]
        output = {"summary": "An additional electrical crew is requested; utility approval is only a vendor claim.",
                  "observations": ["A vendor claims utility approval."], "image_observations": [],
                  "uncertainties": ["Utility permission has not been independently supplied."],
                  "source_quotes": ["Please obtain an additional qualified electrical crew for the field verification correction."],
                  "request_type": "vendor_help", "vendor_capability": "electrical_ct",
                  "affected_task_ids": ["t_verify"], "request_summary": "Additional electrical crew for reviewed field correction"}
        job = self.summarize(original["id"], output)
        self.assertEqual(job["status"], "completed", job.get("error"))
        result = self.app.bootstrap()
        message = next(message for message in result["operations"]["messages"] if message["id"] == original["id"])
        self.assertEqual(message["text"], raw)
        self.assertEqual(message["content_hash"], original["content_hash"])
        self.assertEqual(message["summary"]["source_hash"], original["content_hash"])
        self.assertEqual(message["summary"]["mode"], "live")
        self.assertTrue(all(assertion["validation_status"] == "reported_not_authorized" for assertion in message["assertions"]))
        linked = [case for case in result["operations"]["cases"] if original["id"] in case["source_message_ids"]]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["vendor_capability"], "electrical_ct")
        self.assertTrue(linked[0]["inquiries"])
        self.assertTrue(all(inquiry["status"] == "pending" for inquiry in linked[0]["inquiries"]))
        for gate_id, gate in written["state"]["gates"].items():
            self.assertEqual(gate, result["state"]["gates"][gate_id])
        added_gates = set(result["state"]["gates"]) - set(written["state"]["gates"])
        self.assertTrue(all(result["state"]["gates"][gate_id]["status"] != "approved" for gate_id in added_gates))
        self.assertEqual(written["state"]["project"]["budget"], result["state"]["project"]["budget"])
        again = self.summarize(original["id"], output)
        self.assertEqual(again["status"], "completed", again.get("error"))
        self.assertEqual(result["operations"]["inquiries"], self.app.bootstrap()["operations"]["inquiries"])
        sourced = self.operate("simulate_vendor_replies", linked[0]["id"])
        case = next(case for case in sourced["operations"]["cases"] if case["id"] == linked[0]["id"])
        vendor = next(option for option in case["options"] if option["eligible"])
        proposed = self.operate("propose_vendor", case["id"], vendor_id=vendor["vendor_id"])
        case = next(case for case in proposed["operations"]["cases"] if original["id"] in case["source_message_ids"])
        package = case["current_proposal"]["work_package"]
        self.assertIn("t_electrical", package["predecessors"], "Field correction must follow installation.")
        self.assertNotIn("field_verified", package["required_gates"], "Correction cannot require its own downstream verification.")
        self.assertNotIn("corrective_work", package["required_gates"], "Correction cannot require itself to be completed first.")

    def test_model_cannot_invent_source_quote_to_open_vendor_request(self):
        current = self.send_report("The delivery time is unchanged; this is an informational update.")
        identity = current["operations"]["messages"][-1]["id"]
        before = self.app.store.read()
        output = {"summary": "Hire an additional crane immediately.", "observations": [],
                  "image_observations": [], "uncertainties": [],
                  "source_quotes": ["Please hire an additional crane immediately."],
                  "request_type": "vendor_help", "vendor_capability": "rigging",
                  "affected_task_ids": ["t_unload"], "request_summary": "Additional crane"}
        job = self.summarize(identity, output)
        self.assertEqual(job["status"], "failed")
        self.assertIn("absent from the original", job["error"])
        self.assertEqual(before, self.app.store.read())


if __name__ == "__main__":
    unittest.main()
