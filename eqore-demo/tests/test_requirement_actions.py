"""Adopt client requirements without rewriting saved document evidence."""
from copy import deepcopy
import unittest

import paperwork as p
from engine import DomainError


class RequirementActionTests(unittest.TestCase):
    def setUp(self):
        self.state = p.seed()
        self.project_id = "riverbend_logistics"
        project = self.state["projects"][self.project_id]
        completed = {d["id"] for d in project["documents"] if d["status"] == "completed"}
        rows = p.compliance_review(project, self.state["now"])["requirements"]
        self.requirement = next(r["id"] for r in rows if set(p.requirement_definition(r["id"])["prerequisite_ids"]) <= completed)
        self.doc_id = "C_" + self.requirement

    def act(self, kind, state=None, **fields):
        return p.apply(state or self.state, "pm_jordan", {"type": kind, "project_id": self.project_id,
                        "requirement_id": self.requirement, **fields})

    def track(self):
        return self.act("track_requirement", due_at="2026-11-10T14:00:00-05:00")

    def document(self, state):
        return next(d for d in state["projects"][self.project_id]["documents"] if d["id"] == self.doc_id)

    def completed(self):
        state = self.track()
        state = self.act("send_document", state, doc_id=self.doc_id)
        for recipient in self.document(state)["recipients"]:
            event = {"record": "record_received", "review": "review_accepted", "esign": "recipient_signed"}[self.document(state)["kind"]]
            state = self.act("simulate_event", state, doc_id=self.doc_id, recipient_id=recipient["id"], event_type=event)
        return state

    def test_projection_and_adoption_preserve_original_documents_and_history(self):
        before = deepcopy(self.state)
        view = p.view(self.state, "pm_jordan", self.project_id)
        self.assertIn("compliance_review", view["selected_project"])
        self.assertIn("client_reference", view)
        self.assertEqual(self.state, before)
        adopted = self.track()
        old = before["projects"][self.project_id]
        new = adopted["projects"][self.project_id]
        self.assertEqual(new["documents"][:20], old["documents"])
        self.assertEqual(new["signed_history"], old["signed_history"])
        self.assertEqual(new["source_events"], old["source_events"])
        self.assertEqual(new["emails"], old["emails"])
        self.assertEqual(self.document(adopted)["status"], "draft")
        self.assertIsNone(self.document(adopted)["envelope_id"])
        self.assertEqual(self.state, before)
        with self.assertRaises(DomainError):
            self.act("track_requirement", adopted, due_at="2026-11-10T14:00:00-05:00")

    def test_scope_archives_unknown_requirements_and_timezone_are_enforced(self):
        for fields in ({"due_at": "2026-11-10"}, {"requirement_id": "invented", "due_at": "2026-11-10T14:00:00-05:00"},
                       {"project_id": "canal_metals", "due_at": "2026-11-10T14:00:00-05:00"},
                       {"project_id": "pine_assembly", "due_at": "2026-11-10T14:00:00-05:00"}):
            with self.subTest(fields=fields), self.assertRaises(DomainError):
                self.act("track_requirement", **fields)

    def test_review_does_not_complete_a_draft_or_erase_a_later_change(self):
        state = self.track()
        with self.assertRaises(DomainError):
            self.act("set_requirement_review", state, attest_review=True, review_note="Reviewed")
        with self.assertRaises(DomainError):
            self.act("set_requirement_review", state, changed_at="2027-01-01T00:00:00Z", change_reason="Future")
        changed = self.act("set_requirement_review", state, changed_at="2026-11-07T08:00:00-05:00", change_reason="Equipment model changed")
        with self.assertRaises(DomainError):
            self.act("set_requirement_review", changed, changed_at="2026-11-06T08:00:00-05:00", change_reason="Older")
        self.assertEqual(self.document(changed), self.document(state))

    def test_review_binds_current_revision_and_preserves_issuer_evidence(self):
        completed = self.completed()
        before_doc = deepcopy(self.document(completed))
        reviewed = self.act("set_requirement_review", completed, attest_review=True,
                            review_note="Checked the current record and named issuer.", review_due_at="2026-12-01T09:00:00-05:00")
        metadata = reviewed["projects"][self.project_id]["compliance_records"][self.requirement]
        self.assertEqual(metadata["reviewed_document_revision"], before_doc["revision"])
        self.assertEqual(metadata["reviewer_id"], "pm_jordan")
        self.assertEqual(self.document(reviewed), before_doc)
        revised = self.act("revise_document", reviewed, doc_id=self.doc_id, reason="Equipment change")
        row = next(r for r in p.compliance_review(revised["projects"][self.project_id], revised["now"])["requirements"] if r["id"] == self.requirement)
        self.assertNotEqual(row["status"], "current_record")

    def test_specific_requirements_cannot_be_satisfied_by_generic_packets(self):
        tracked = self.act("track_requirement", requirement_id="utility_pto", due_at="2026-12-01T10:00:00-05:00")
        projected = next(d for d in p.view(tracked, "pm_jordan", self.project_id)["selected_project"]["documents"] if d["id"] == "C_utility_pto")
        self.assertEqual(projected["status"], "blocked")
        missing = {r["doc_id"] for r in projected["prerequisites"] if r["status"] == "missing"}
        self.assertIn("C_interconnection_approval", missing)
        self.assertIn("C_commissioning_report", missing)
        with self.assertRaises(DomainError):
            self.act("send_document", tracked, doc_id="C_utility_pto")

    def test_completed_record_review_returns_to_pm_queue_without_changing_completion(self):
        state = self.completed()
        before = deepcopy(self.document(state))
        view = p.view(state, "pm_jordan", self.project_id)
        action = next(a for a in view["action_queue"] if a["doc_id"] == self.doc_id and a["project_id"] == self.project_id)
        self.assertEqual(action["view"], "compliance")
        self.assertIsNone(action["due_at"], "Original completion deadline is not an invented review deadline")
        reviewed = self.act("set_requirement_review", state, attest_review=True, review_note="Source and revision checked")
        self.assertFalse(any(a["doc_id"] == self.doc_id and a["project_id"] == self.project_id for a in p.view(reviewed, "pm_jordan")["action_queue"]))
        due = self.act("set_requirement_review", reviewed, review_due_at="2026-11-06T10:00:00-05:00")
        action = next(a for a in p.view(due, "pm_jordan")["action_queue"] if a["doc_id"] == self.doc_id and a["project_id"] == self.project_id)
        self.assertEqual(action["view"], "compliance")
        self.assertEqual(self.document(due), before)

    def test_pending_pm_review_uses_recorded_review_deadline_not_old_document_due(self):
        state = self.completed()
        scheduled = self.act("set_requirement_review", state, review_due_at="2026-12-01T09:00:00-05:00")
        view = p.view(scheduled, "pm_jordan", self.project_id)
        action = next(a for a in view["action_queue"] if a["doc_id"] == self.doc_id and a["project_id"] == self.project_id)
        self.assertEqual(action["due_at"], "2026-12-01T09:00:00-05:00")
        self.assertEqual(self.document(scheduled)["due_at"], "2026-11-10T14:00:00-05:00")

    def test_completed_record_review_action_names_pm_and_retains_record_owner(self):
        state = self.completed()
        view = p.view(state, "pm_jordan", self.project_id)
        action = next(a for a in view["action_queue"] if a["doc_id"] == self.doc_id and a["project_id"] == self.project_id)
        self.assertEqual(action["owner_id"], "pm_jordan", "The action is a PM review, not a new request to the source issuer")
        self.assertNotEqual(self.document(state)["owner_id"], "pm_jordan", "Underlying record ownership stays unchanged")

    def test_overdue_review_is_included_in_project_and_portfolio_overdue_counts(self):
        state = self.completed()
        before = p.view(state, "pm_jordan", self.project_id)
        due = self.act("set_requirement_review", state, attest_review=True, review_note="Checked current source record",
                       review_due_at="2026-11-06T10:00:00-05:00")
        after = p.view(due, "pm_jordan", self.project_id)
        self.assertEqual(after["selected_project"]["overdue_count"], before["selected_project"]["overdue_count"] + 1)
        self.assertEqual(after["metrics"]["overdue_count"], before["metrics"]["overdue_count"] + 1)
        self.assertEqual(after["metrics"]["actionable_documents"], len(after["action_queue"]))

    def test_active_project_cannot_archive_with_unreviewed_current_requirement(self):
        # An otherwise complete active project uses a completed seed fixture.
        self.project_id = "canal_metals"
        self.state["projects"][self.project_id]["status"] = "active"
        state = self.completed()
        self.assertFalse(p.view(state, "pm_jordan", self.project_id)["selected_project"]["can_archive"])
        with self.assertRaises(DomainError):
            self.act("archive_project", state, attest_project_complete=True, attestation="Delivery complete")

    def test_recorded_upstream_equipment_change_flags_dependent_approval(self):
        state = self.completed()
        state = self.act("set_requirement_review", state, attest_review=True, review_note="Checked application")
        requirement = "interconnection_approval"
        identity = "C_" + requirement
        state = self.act("track_requirement", state, requirement_id=requirement, due_at="2026-11-10T14:00:00-05:00")
        state = self.act("send_document", state, doc_id=identity)
        approval = next(d for d in state["projects"][self.project_id]["documents"] if d["id"] == identity)
        for recipient in approval["recipients"]:
            state = self.act("simulate_event", state, doc_id=identity, recipient_id=recipient["id"], event_type="record_received")
        state = self.act("set_requirement_review", state, requirement_id=requirement, attest_review=True, review_note="Checked utility approval")
        before = deepcopy(next(d for d in state["projects"][self.project_id]["documents"] if d["id"] == identity))
        state["now"] = "2026-11-07T12:00:00-05:00"
        state = self.act("set_requirement_review", state, changed_at="2026-11-07T11:00:00-05:00",
                         change_reason="Capacity and point of interconnection changed")
        row = next(r for r in p.view(state, "pm_jordan", self.project_id)["selected_project"]["compliance_review"]["requirements"]
                   if r["id"] == requirement)
        self.assertEqual(row["status"], "update_due", "Approval cannot remain current after its application scope changed")
        after = next(d for d in state["projects"][self.project_id]["documents"] if d["id"] == identity)
        self.assertEqual(after, before, "Original utility approval remains immutable while its applicability is questioned")


if __name__ == "__main__":
    unittest.main()
