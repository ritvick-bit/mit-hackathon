"""Client checklist coverage must preserve records and avoid inferred approval."""
from copy import deepcopy
import json
import unittest

import compliance


NOW = "2026-11-07T12:00:00-05:00"


class ComplianceTests(unittest.TestCase):
    def project(self):
        return {"id": "site", "status": "active", "pm_id": "pm", "stakeholders": [{"id": "pm", "name": "PM"}],
                "documents": [{"id": "D07", "title": "Issued permit and fire-review records", "status": "completed", "revision": 1}]}

    def tagged(self, requirement="emergency_plan", **changes):
        document = {"id": "C01", "title": "Emergency operations plan", "requirement_id": requirement,
                    "status": "completed", "revision": 1, "source_mode": "sample",
                    "completed_at": "2026-11-01T10:00:00-05:00",
                    "completion_record": {"revision": 1, "at": "2026-11-01T10:00:00-05:00", "source_event_ids": ["e1"]}}
        document.update(changes)
        return document

    def review_metadata(self):
        return {"reviewed_at": "2026-11-02T10:00:00-05:00", "reviewer_id": "pm", "reviewed_document_revision": 1}

    def row(self, project, identity="emergency_plan", **kwargs):
        return next(r for r in compliance.review(project, NOW, **kwargs)["requirements"] if r["id"] == identity)

    def test_review_preserves_history_and_returns_detached_json(self):
        project = self.project()
        project["history"] = [{"signed": "unchanged"}]
        before = deepcopy(project)
        result = compliance.review(project, NOW)
        json.dumps(result)
        result["source"]["title"] = "changed"
        result["requirements"][0]["source_refs"][0]["title"] = "changed"
        self.assertEqual(project, before)
        self.assertNotEqual(compliance.SOURCE["title"], "changed")

    def test_generic_completed_permit_does_not_satisfy_three_approvals(self):
        project = self.project()
        for identity in ("building_permit", "electrical_permit", "fire_permit"):
            row = self.row(project, identity)
            self.assertEqual(row["status"], "missing_record")
            self.assertEqual(row["related_document_ids"], ["D07"])
            self.assertEqual(row["tracked_document_ids"], [])

    def test_current_record_needs_tag_revision_and_completion_sources(self):
        project = self.project()
        project["documents"].append(self.tagged())
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        self.assertEqual(self.row(project)["status"], "current_record")
        project["documents"][-1]["completion_record"]["revision"] = 0
        self.assertEqual(self.row(project)["status"], "needs_review")
        project["documents"][-1]["completion_record"] = {"revision": 1, "source_event_ids": []}
        self.assertEqual(self.row(project)["status"], "needs_review")

    def test_projected_dependency_block_overrides_raw_completed_record(self):
        project = self.project()
        project["documents"].append(self.tagged())
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        projected = deepcopy(project["documents"])
        projected[-1]["status"] = "blocked"
        self.assertEqual(self.row(project, document_views=projected)["status"], "update_due")

    def test_operations_and_decommissioning_not_immediate_missing_tasks(self):
        project = self.project()
        self.assertEqual(self.row(project, "maintenance_log")["status"], "not_yet_due")
        self.assertEqual(self.row(project, "decommissioning_plan")["status"], "not_yet_due")
        project["lifecycle"] = "operations"
        self.assertEqual(self.row(project, "maintenance_log")["status"], "missing_record")
        self.assertEqual(self.row(project, "decommissioning_plan")["status"], "not_yet_due")
        project["lifecycle"] = "decommissioning"
        self.assertEqual(self.row(project, "decommissioning_plan")["status"], "missing_record")

    def test_no_arbitrary_deadline_or_overdue_from_absent_review_schedule(self):
        project = self.project()
        project["documents"].append(self.tagged())
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        row = self.row(project)
        self.assertEqual(row["status"], "current_record")
        self.assertIsNone(row["due_at"])

    def test_recorded_review_due_and_post_review_site_change(self):
        project = self.project()
        project["documents"].append(self.tagged())
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        project["compliance_records"] = {"emergency_plan": dict(self.review_metadata(), review_due_at="2026-11-21T10:00:00-05:00")}
        self.assertEqual(self.row(project)["status"], "upcoming")
        project["compliance_records"]["emergency_plan"]["review_due_at"] = "2026-11-06T10:00:00-05:00"
        self.assertEqual(self.row(project)["status"], "update_due")
        project["compliance_records"]["emergency_plan"] = dict(self.review_metadata(), changed_at="2026-11-05T10:00:00-05:00")
        self.assertEqual(self.row(project)["status"], "update_due")
        project["compliance_records"]["emergency_plan"]["reviewed_at"] = "2026-11-06T10:00:00-05:00"
        self.assertEqual(self.row(project)["status"], "current_record")

    def test_timezone_missing_metadata_requires_review(self):
        project = self.project()
        project["documents"].append(self.tagged())
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        project["compliance_records"] = {"emergency_plan": {"review_due_at": "2026-11-06"}}
        self.assertEqual(self.row(project)["status"], "needs_review")

    def test_duplicate_tagged_records_are_not_silently_current(self):
        project = self.project()
        project["documents"] += [self.tagged(), self.tagged(id="C02")]
        self.assertEqual(self.row(project)["status"], "needs_review")

    def test_future_and_past_tracked_deadlines_only(self):
        project = self.project()
        project["documents"].append(self.tagged(status="draft", completion_record=None, due_at="2026-11-20T10:00:00-05:00"))
        self.assertEqual(self.row(project)["status"], "upcoming")
        project["documents"][-1]["due_at"] = "2026-11-06T10:00:00-05:00"
        self.assertEqual(self.row(project)["status"], "update_due")

    def test_archives_are_retrospective_without_new_actions(self):
        project = self.project()
        project["status"] = "archived"
        result = compliance.review(project, NOW)
        self.assertEqual(result["scope"], "retrospective")
        self.assertEqual(result["actions"], [])
        self.assertTrue(all(r["read_only"] for r in result["requirements"]))
        self.assertEqual(project["status"], "archived")

    def test_definitions_have_source_roles_and_separate_authority(self):
        definitions = [compliance.requirement_definition(r["id"]) for r in compliance.REQUIREMENTS]
        self.assertTrue(all(r["kind"] == "record" and r["source_refs"] and r["audiences"] for r in definitions))
        report = compliance.requirement_definition("commissioning_report")
        self.assertNotIn("D17", report["prerequisite_ids"])
        self.assertIn("before final inspection", report["when"])
        definitions[0]["title"] = "changed"
        self.assertNotEqual(compliance.REQUIREMENTS[0]["title"], "changed")
        with self.assertRaises(ValueError):
            compliance.requirement_definition("unknown")

    def test_catalog_matches_reviewed_client_reference(self):
        from client_reference import DOCUMENT_REQUIREMENTS
        self.assertEqual({(r["id"], r["title"]) for r in compliance.REQUIREMENTS},
                         {(r["id"], r["title"]) for r in DOCUMENT_REQUIREMENTS})
        self.assertEqual(len(compliance.REQUIREMENTS), 20)
        self.assertTrue(all(isinstance(r["evidence_required"], list) and r["evidence_required"] for r in compliance.REQUIREMENTS))

    def test_pm_review_is_required_and_bound_to_current_revision(self):
        project = self.project()
        project["documents"].append(self.tagged())
        self.assertEqual(self.row(project)["status"], "needs_review")
        project["compliance_records"] = {"emergency_plan": self.review_metadata()}
        self.assertEqual(self.row(project)["status"], "current_record")
        project["documents"][-1]["revision"] = 2
        project["documents"][-1]["completion_record"]["revision"] = 2
        self.assertEqual(self.row(project)["status"], "update_due")
        project["compliance_records"]["emergency_plan"]["reviewed_document_revision"] = 2
        project["compliance_records"]["emergency_plan"]["reviewed_at"] = "2026-12-01T10:00:00-05:00"
        self.assertEqual(self.row(project)["status"], "needs_review")
        self.assertEqual(self.row(project)["review"]["reviewed_document_revision"], 2)


if __name__ == "__main__":
    unittest.main()
