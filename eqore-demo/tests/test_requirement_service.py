"""Requirement adoption/review inherits durable PM scope and version guards."""
import tempfile
import unittest

from engine import DomainError
from paperwork_api import PaperworkService
from storage import Conflict, Store


class RequirementServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(self.directory.name + "/requirements.sqlite3")
        self.service = PaperworkService(self.store, None, {"authenticated": False, "detail": "Isolated test"})
        self.jordan = self.service.login("pm_jordan")["token"]
        self.casey = self.service.login("pm_casey")["token"]

    def tearDown(self):
        self.directory.cleanup()

    def record(self):
        return self.store.read_workspace("paperwork")

    def payload(self, version, kind="track_requirement", **changes):
        action = {"type": kind, "project_id": "riverbend_logistics", "requirement_id": "emergency_plan",
                  "due_at": "2026-12-01T09:00:00-05:00"}
        action.update(changes)
        return {"expected_version": version, "action": action}

    def test_stale_adoption_and_review_cannot_overwrite_newer_changes(self):
        initial = self.record()
        self.service.action(self.jordan, self.payload(initial["version"]))
        adopted = self.record()
        with self.assertRaises(Conflict):
            self.service.action(self.jordan, self.payload(initial["version"], requirement_id="om_manual"))
        self.assertEqual(self.record(), adopted)
        self.service.action(self.jordan, self.payload(adopted["version"], "set_requirement_review",
                                                    review_due_at="2026-12-02T09:00:00-05:00"))
        scheduled = self.record()
        with self.assertRaises(Conflict):
            self.service.action(self.jordan, self.payload(adopted["version"], "set_requirement_review",
                                                        review_due_at="2026-12-03T09:00:00-05:00"))
        self.assertEqual(self.record(), scheduled)

    def test_other_pm_and_archived_projects_reject_tracking_and_review(self):
        initial = self.record()
        with self.assertRaises(DomainError):
            self.service.action(self.casey, self.payload(initial["version"]))
        with self.assertRaises(DomainError):
            self.service.action(self.jordan, self.payload(initial["version"], project_id="canal_metals"))
        self.assertEqual(self.record(), initial)
        self.service.action(self.jordan, self.payload(initial["version"]))
        adopted = self.record()
        with self.assertRaises(DomainError):
            self.service.action(self.casey, self.payload(adopted["version"], "set_requirement_review",
                                                       review_due_at="2026-12-03T09:00:00-05:00"))
        self.assertEqual(self.record(), adopted)


if __name__ == "__main__":
    unittest.main()
