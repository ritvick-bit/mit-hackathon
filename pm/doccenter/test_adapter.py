"""Run: python -m unittest discover -s pm/doccenter -v

Covers the PM platform's adapter around Yichang's document center: seeding projects from a plan, PM scoping,
the compact feed, his own actions still working, and the two platform additions (add document, edit details).
"""
import copy
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import adapter  # noqa: E402
import paperwork  # noqa: E402
from engine import DomainError  # noqa: E402
from storage import Conflict  # noqa: E402

DAY = lambda n: (datetime.now(timezone.utc) + timedelta(days=n)).date().isoformat()
PMS = [{"id": "PM-JORDAN", "name": "Jordan Lee", "email": "jordan@demo.example"}, {"id": "PM-SAM", "name": "Sam Ortiz", "email": "sam@demo.example"}]


def plan(pid="JOB-001", pm="PM-JORDAN", done=8):
    docs = []
    for i, row in enumerate(paperwork.TEMPLATE):
        docs.append({"id": row[0], "step": "contract", "due_at": DAY(i - done), "completed_at": DAY(i - done - 1) if i < done else None,
                     "opening": "returned" if i == done else None, "opening_text": "Please correct the one-line diagram."})
    docs.append({"id": "P-cabinets-po", "title": "Purchase order: Battery cabinets", "kind": "esign", "phase": "Procurement", "owner_role": "pm",
                 "recipient_roles": ["commercial"], "recipients": [{"company_id": "SU-QPACK", "name": "Elena Marsh", "organization": "QorePack", "email": "elena@q.demo.example"}],
                 "step": "procurement", "product_id": pid + ":p:cabinets", "due_at": DAY(5)})
    return {"id": pid, "pm_id": pm, "name": "Harbor Point", "site": "Boston, MA", "profile": {"system_power_kw": 500},
            "stakeholders": {"supplier": {"name": "Elena Marsh", "organization": "QorePack", "email": "elena@q.demo.example", "company_id": "SU-QPACK"}},
            "documents": docs}


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.sessions = {"jordan": {"pm_id": "PM-JORDAN", "mode": "demo"}, "sam": {"pm_id": "PM-SAM", "mode": "demo"}}
        self.dc = adapter.DocCenter(self.folder.name, 8790, self.sessions, threading.Lock(), PMS)
        self.dc.ensure("jordan", {"projects": [plan()]})

    def tearDown(self):
        self.dc.pool.shutdown(wait=False)
        self.folder.cleanup()

    def docs(self, token="jordan", pid="JOB-001"):
        return {d["id"]: d for d in self.dc.feed(token)["projects"][pid]["documents"]}

    def test_seed_replays_completed_documents_and_openings(self):
        docs = self.docs()
        self.assertEqual(len(docs), 21)
        self.assertTrue(all(docs["D%02d" % i]["status"] == "completed" for i in range(1, 9)))
        self.assertIn(docs["D09"]["status"], ("returned", "declined"))
        self.assertEqual(docs["D10"]["status"], "blocked", "a returned prerequisite blocks what follows")
        self.assertEqual(docs["P-cabinets-po"]["product_id"], "JOB-001:p:cabinets")
        people = {p["id"]: p for p in self.dc.feed("jordan")["projects"]["JOB-001"]["stakeholders"]}
        self.assertEqual(people["JOB-001__supplier"]["company_id"], "SU-QPACK")
        view = self.dc.bootstrap("jordan", "JOB-001")["selected_project"]
        self.assertTrue(any(e["doc_id"] == "D09" for e in view["emails"]), "the returned document keeps its original email")

    def test_ensure_is_idempotent_and_scoped_to_the_pm(self):
        before = self.dc.store.read_workspace("paperwork")["version"]
        self.assertEqual(self.dc.ensure("jordan", {"projects": [plan()]})["created"], [])
        self.assertEqual(self.dc.store.read_workspace("paperwork")["version"], before)
        with self.assertRaises(PermissionError):
            self.dc.ensure("sam", {"projects": [plan("JOB-002", pm="PM-JORDAN")]})
        self.assertEqual(self.dc.feed("sam")["projects"], {}, "Sam cannot see Jordan's projects")
        with self.assertRaises(DomainError):
            paperwork.view(self.dc.store.read_workspace("paperwork")["state"], "PM-SAM", "JOB-001")
        with self.assertRaises(PermissionError):
            self.dc.actor("nobody")

    def test_his_actions_still_work(self):
        version = self.dc.store.read_workspace("paperwork")["version"]
        result = self.dc.action("jordan", {"expected_version": version, "action": {"type": "send_document", "project_id": "JOB-001", "doc_id": "P-cabinets-po"}})
        self.assertEqual(self.docs()["P-cabinets-po"]["status"], "sent")
        result = self.dc.action("jordan", {"expected_version": result["version"], "action": {"type": "simulate_event", "project_id": "JOB-001", "doc_id": "P-cabinets-po",
                                                                                           "event_type": "recipient_signed", "recipient_id": "JOB-001__commercial"}})
        self.assertEqual(self.docs()["P-cabinets-po"]["status"], "partially_signed")
        with self.assertRaises(Conflict):
            self.dc.action("jordan", {"expected_version": version, "action": {"type": "draft_email", "project_id": "JOB-001", "doc_id": "D12"}})

    def test_add_document_and_edit_details(self):
        version = self.dc.store.read_workspace("paperwork")["version"]
        result = self.dc.action("jordan", {"expected_version": version, "action": {
            "type": "add_document", "project_id": "JOB-001", "title": "Lien waiver", "kind": "esign", "due_at": DAY(10), "step": "civil",
            "recipients": [{"company_id": "CV-COMMON", "name": "Kevin Brennan", "organization": "Commonwealth Civil", "email": "kevin@c.demo.example"}]}})
        added = self.docs()["X01"]
        self.assertEqual((added["title"], added["status"], added["step"]), ("Lien waiver", "ready", "civil"))
        people = {p["id"]: p for p in self.dc.feed("jordan")["projects"]["JOB-001"]["stakeholders"]}
        self.assertEqual(people["JOB-001__c_CV-COMMON"]["organization"], "Commonwealth Civil", "a new company becomes a project stakeholder")
        self.dc.action("jordan", {"expected_version": result["version"], "action": {"type": "edit_document_details", "project_id": "JOB-001", "doc_id": "X01",
                                                                                   "title": "Lien waiver (final)", "due_at": DAY(12), "notes": "Progress payment 2"}})
        edited = self.docs()["X01"]
        self.assertEqual((edited["title"], edited["notes"], edited["due_at"][:10]), ("Lien waiver (final)", "Progress payment 2", DAY(12)))
        with self.assertRaises(DomainError):
            self.dc.action("jordan", {"expected_version": self.dc.store.read_workspace("paperwork")["version"],
                                      "action": {"type": "add_document", "project_id": "JOB-001", "title": "x", "due_at": DAY(1), "recipients": []}})


if __name__ == "__main__":
    unittest.main()
