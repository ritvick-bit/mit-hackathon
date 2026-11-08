"""Run: python -m unittest discover -s pm/doccenter -v

In-platform signing, DocuSign embedded signing (against a fake DocuSign), signed PDFs and earlier revisions.
"""
import copy
import json
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
from paperwork_connectors import PaperworkConnectors  # noqa: E402
from test_adapter import PMS, plan  # noqa: E402

STROKES = [[[0.1, 0.5], [0.2, 0.3], [0.3, 0.6], [0.4, 0.4], [0.5, 0.5]], [[0.6, 0.5], [0.7, 0.4], [0.8, 0.6], [0.9, 0.5]]]


class SigningTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.sessions = {"jordan": {"pm_id": "PM-JORDAN", "mode": "demo", "name": "Jordan Lee", "email": "jordan@company.com"}}
        self.dc = adapter.DocCenter(self.folder.name, 8790, self.sessions, threading.Lock(), PMS)
        ready = plan(done=4)
        ready["documents"][4]["opening"] = None  # D05, an e-signature document the PM owns, is ready to sign
        self.dc.ensure("jordan", {"projects": [ready]})
        self.calls = []

    def tearDown(self):
        self.dc.pool.shutdown(wait=False)
        self.folder.cleanup()

    def version(self):
        return self.dc.store.read_workspace("paperwork")["version"]

    def raw(self, doc_id):
        return paperwork._doc(self.dc.store.read_workspace("paperwork")["state"]["projects"]["JOB-001"], doc_id)

    def sign(self, **extra):
        act = {"type": "sign_locally", "project_id": "JOB-001", "doc_id": "D05", "consent": True, "signature": {"method": "draw", "strokes": STROKES}}
        act.update(extra)
        return self.dc.action("jordan", {"expected_version": self.version(), "action": act})

    def test_sign_in_platform_then_it_goes_to_the_recipients(self):
        with self.assertRaises(DomainError):
            self.sign(consent=False)
        with self.assertRaises(ValueError):
            self.sign(signature={"method": "draw", "strokes": [[[0.1, 0.1]]]})
        self.sign()
        doc = self.raw("D05")
        self.assertEqual(doc["status"], "sent")
        sig = doc["pm_signatures"][0]
        self.assertEqual((sig["revision"], sig["name"], sig["method"], len(sig["body_hash"])), (1, "Jordan Lee", "draw", 64))
        with self.assertRaises(DomainError):
            self.sign()  # already sent: a new revision is needed to sign again
        self.dc.action("jordan", {"expected_version": self.version(), "action": {"type": "sign_locally", "project_id": "JOB-001", "doc_id": "D12",
                                                                                "consent": True, "signature": {"method": "type", "typed": "Jordan Lee"}}}) \
            if False else None

    def test_only_the_pms_own_signature_documents(self):
        with self.assertRaises(DomainError):  # D06 is a record, not a signature document
            self.dc.action("jordan", {"expected_version": self.version(), "action": {"type": "sign_locally", "project_id": "JOB-001", "doc_id": "D06",
                                                                                    "consent": True, "signature": {"method": "type", "typed": "Jordan Lee"}}})

    def test_signed_pdf_and_earlier_revisions(self):
        self.sign()
        data, name = self.dc.pdf("jordan", "JOB-001", "D05")
        self.assertTrue(data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b" l S", data, "the drawn signature is drawn as a path")
        self.assertEqual(name, "JOB-001-D05-r1.pdf")
        self.dc.action("jordan", {"expected_version": self.version(), "action": {"type": "revise_document", "project_id": "JOB-001", "doc_id": "D05",
                                                                                "reason": "Customer asked for a new start date.", "body": "Revised text."}})
        doc = self.raw("D05")
        self.assertEqual((doc["revision"], doc["body"], doc["revisions"][0]["revision"]), (2, "Revised text.", 1))
        old, _ = self.dc.pdf("jordan", "JOB-001", "D05", 1)
        new, _ = self.dc.pdf("jordan", "JOB-001", "D05", 2)
        self.assertIn(b" l S", old, "revision 1 keeps its signature")
        self.assertNotIn(b" l S", new, "revision 2 is not signed yet")
        with self.assertRaises(ValueError):
            self.dc.pdf("jordan", "JOB-001", "D05", 7)

    def fake_docusign(self, method, url, headers, body, timeout):
        payload = json.loads(body) if body else None
        self.calls.append((method, url, payload))
        if url.endswith("/envelopes") and method == "POST":
            # As in the live sandbox: the create response's time differs slightly from the envelope's sentDateTime.
            self.sent_at = datetime.now(timezone.utc).isoformat()
            return {"envelopeId": "env-123", "status": "sent", "statusDateTime": (datetime.now(timezone.utc) - timedelta(milliseconds=300)).isoformat()}
        if url.endswith("/views/recipient"):
            return {"url": "https://demo.docusign.net/Signing/StartInSession.aspx?t=abc"}
        if "/envelopes/env-123" in url and method == "GET":
            signed = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            return {"envelopeId": "env-123", "status": "sent", "sentDateTime": self.sent_at, "recipients": {"signers": [
                {"recipientId": "1", "name": "Jordan Lee", "email": "jordan@company.com", "status": "completed", "signedDateTime": signed},
                {"recipientId": "2", "name": "Avery Brooks", "email": "avery@customer.com", "status": "sent"},
                {"recipientId": "3", "name": "Taylor Reed", "email": "taylor@customer.com", "status": "sent"}]}}
        raise AssertionError("unexpected call " + url)

    def test_docusign_sign_in_platform_and_email_the_rest(self):
        env = {"EQORE_DOCUSIGN_ACCESS_TOKEN": "t", "EQORE_DOCUSIGN_ACCOUNT_ID": "acct1"}
        self.dc.session_connectors["jordan"] = PaperworkConnectors(env, transport=self.fake_docusign)
        with self.assertRaises(DomainError):
            self.dc.docusign_sign("jordan", {"project_id": "JOB-001", "doc_id": "D05"})  # signers still have placeholder emails
        state = copy.deepcopy(self.dc.store.read_workspace("paperwork")["state"])
        names = {"JOB-001__customer": ("Avery Brooks", "avery@customer.com"), "JOB-001__facilities": ("Taylor Reed", "taylor@customer.com")}
        for p in state["projects"]["JOB-001"]["stakeholders"]:
            if p["id"] in names:
                p["name"], p["email"] = names[p["id"]]
        for r in paperwork._doc(state["projects"]["JOB-001"], "D05")["recipients"]:
            r["name"] = names[r["id"]][0]
        self.dc.store.write_workspace("paperwork", state, self.version())

        result = self.dc.docusign_sign("jordan", {"project_id": "JOB-001", "doc_id": "D05"})
        self.assertTrue(result["signing_url"].startswith("https://demo.docusign.net/"))
        envelope = self.calls[0][2]
        signers = envelope["recipients"]["signers"]
        self.assertEqual(envelope["status"], "sent")
        self.assertEqual((signers[0]["clientUserId"], signers[0]["routingOrder"], signers[0]["email"]), ("PM-JORDAN", "1", "jordan@company.com"))
        self.assertTrue(all(s["routingOrder"] == "2" and "clientUserId" not in s for s in signers[1:]), "DocuSign emails the other signers")
        view = next(c[2] for c in self.calls if c[1].endswith("/views/recipient"))
        self.assertEqual((view["clientUserId"], view["recipientId"]), ("PM-JORDAN", "1"))
        self.assertTrue(view["returnUrl"].startswith("http://localhost:8790/api/paperwork/signing/return?"))
        doc = self.raw("D05")
        self.assertEqual((doc["status"], doc["provider"], doc["envelope_id"]), ("sent", "docusign", "env-123"))
        self.assertEqual(doc["sent_at"], self.sent_at, "the envelope's own sentDateTime, so reconciliation matches")
        self.assertEqual(doc["provider_recipient_map"], {"2": "JOB-001__customer", "3": "JOB-001__facilities"})

        self.dc.signing_return("jordan", {"project_id": "JOB-001", "doc_id": "D05", "event": "signing_complete"})
        doc = self.raw("D05")
        self.assertTrue(doc["platform_signing"]["pm_signed_at"])
        self.assertEqual(doc["status"], "sent", "the other signers have not signed yet; nothing is inferred")
        self.assertTrue(sum(c[0] == "GET" for c in self.calls) >= 2, "returning from DocuSign reconciles the envelope")
        self.assertTrue(doc["provider_observations"], "the reconciliation was recorded (no timestamp conflict)")
        # An envelope recorded with the create-response time (before the fix) is aligned on the next sync.
        state = copy.deepcopy(self.dc.store.read_workspace("paperwork")["state"])
        paperwork._doc(state["projects"]["JOB-001"], "D05")["sent_at"] = (datetime.fromisoformat(self.sent_at) - timedelta(milliseconds=300)).isoformat()
        self.dc.store.write_workspace("paperwork", state, self.version())
        result = self.dc.connector_action("jordan", {"operation": "sync_envelope", "provider": "docusign", "expected_version": self.version(),
                                                     "project_id": "JOB-001", "doc_id": "D05"})
        self.assertFalse(result["connector_result"].get("errors"))
        with self.assertRaises(DomainError):
            self.dc.docusign_sign("jordan", {"project_id": "JOB-001", "doc_id": "D05"})  # nothing left for the PM to sign


if __name__ == "__main__":
    unittest.main()
