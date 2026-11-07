"""Project switching is persistence, never an implicit reset or cross-project write."""
import tempfile
import copy
import threading
import time
import unittest
from unittest.mock import patch

import engine
import projects
from server import Application
from storage import Conflict


class PortfolioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = patch("llm.runtime_status", return_value={"available": True, "authenticated": True, "detail": "test"})
        self.auth.start()
        self.app = Application(self.tmp.name + "/projects.sqlite3")
        self.ids = [p["id"] for p in projects.list_projects()]

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.auth.stop()
        self.tmp.cleanup()

    def switch(self, project_id):
        return self.app.mutate("/api/projects/select", {"project_id": project_id, "expected_version": self.app.store.read()["version"]})

    def test_project_changes_survive_switch_and_restart(self):
        before = self.app.bootstrap()
        modified = self.app.mutate("/api/action", {"action": before["recommendation"]["action"], "expected_version": before["session_version"]})
        self.switch(self.ids[1])
        restored = self.switch(self.ids[0])
        self.assertEqual(restored["state"], modified["state"])
        self.assertGreater(restored["session_version"], modified["session_version"])
        reopened = Application(self.app.store.path)
        try:
            self.assertEqual(reopened.bootstrap()["state"], modified["state"])
        finally:
            reopened.pool.shutdown(wait=True)

    def test_stale_project_action_rejected_after_switch(self):
        first = self.app.bootstrap()
        second = self.switch(self.ids[1])
        with self.assertRaises(Conflict):
            self.app.mutate("/api/action", {"action": first["recommendation"]["action"], "expected_version": first["session_version"]})
        self.assertEqual(self.app.bootstrap()["state"], second["state"])

    def test_reset_only_changes_selected_project(self):
        initial = self.app.bootstrap()
        modified = self.app.mutate("/api/action", {"action": initial["recommendation"]["action"], "expected_version": initial["session_version"]})
        self.switch(self.ids[1])
        self.app.mutate("/api/projects/reset", {"project_id": self.ids[1], "expected_version": self.app.store.read()["version"]})
        self.assertEqual(self.switch(self.ids[0])["state"], modified["state"])

    def test_test_case_does_not_replace_saved_project(self):
        initial = self.app.bootstrap()
        modified = self.app.mutate("/api/action", {"action": initial["recommendation"]["action"], "expected_version": initial["session_version"]})
        case = self.app.mutate("/api/reset", {"scenario_id": "delivery_delay", "expected_version": modified["session_version"]})
        self.assertEqual(case["mode"], "scenario")
        restored = self.switch(self.ids[0])
        self.assertEqual(restored["mode"], "project")
        self.assertEqual(restored["state"], modified["state"])

    def test_recommendations_and_history_are_scoped_to_project(self):
        first = self.app.bootstrap()
        decision = dict(first["recommendation"], title="First project saved rationale")
        self.app.store.save_recommendation(decision, first["session_version"])
        second = self.switch(self.ids[1])
        self.assertEqual(second["reasoning_history"], [])
        self.assertNotEqual(second["recommendation"]["title"], decision["title"])
        restored = self.switch(self.ids[0])
        self.assertEqual(restored["recommendation"], decision)
        self.assertEqual(restored["reasoning_history"][0]["project_id"], first["state"]["project"]["id"])

    def test_inflight_reasoning_cannot_follow_user_to_another_project(self):
        started, finish = threading.Event(), threading.Event()

        def decide(state):
            started.set()
            finish.wait(5)
            return dict(engine.recommend(state), mode="live")

        with patch("llm.decide", side_effect=decide):
            job_id = self.app.submit("decide", {"mode": "live"})["job_id"]
            self.assertTrue(started.wait(2))
            second = self.switch(self.ids[1])
            finish.set()
            for _ in range(200):
                if self.app.jobs[job_id]["status"] != "running":
                    break
                time.sleep(.01)
        self.assertEqual(self.app.jobs[job_id]["status"], "failed")
        self.assertEqual(self.app.bootstrap()["state"], second["state"])
        self.assertEqual(self.app.bootstrap()["reasoning_history"], [])

    def test_catalog_reports_independent_project_metrics(self):
        envelope = self.app.bootstrap()
        self.assertEqual(len(envelope["projects"]), 3)
        self.assertEqual(sum(bool(p["selected"]) for p in envelope["projects"]), 1)
        self.assertTrue(all(p["metrics"] for p in envelope["projects"]))
        self.assertGreater(len(envelope["dashboard"]["bottlenecks"]), 1)
        for key in ("private_events", "expected_outcome", "actor_policy"):
            self.assertNotIn(key, envelope)

    def test_world_upgrade_archives_pristine_but_preserves_active_progress(self):
        initial = self.app.store.read()
        upgraded = copy.deepcopy(initial["state"])
        upgraded["project"]["world_version"] = "next-test-world"
        self.assertEqual(self.app.store.refresh_pristine_projects([upgraded]), [self.ids[0]])
        self.assertEqual(self.app.store.archives(self.ids[0])[0]["state"], initial["state"])
        current = self.app.store.read()
        self.assertGreater(current["version"], initial["version"])
        changed = engine.apply_action(current["state"], engine.recommend(current["state"])["action"])
        self.app.store.write(changed, expected=current["version"])
        next_template = copy.deepcopy(upgraded)
        next_template["project"]["world_version"] = "later-test-world"
        self.assertEqual(self.app.store.refresh_pristine_projects([next_template]), [])
        self.assertEqual(self.app.store.read()["state"], changed)

    def test_review_clock_exposes_followup_without_granting_approval(self):
        initial = self.app.bootstrap()
        action = next(c["action"] for c in initial["analysis"]["candidates"]
                      if c["action"].get("gate_id") == "permit")
        requested = self.app.mutate("/api/action", {"action": action, "expected_version": initial["session_version"]})
        request = requested["state"]["requests"][-1]
        acknowledged = self.app.mutate("/api/respond", {"request_id": request["id"], "expected_version": requested["session_version"]})
        self.assertEqual("acknowledged", acknowledged["state"]["requests"][-1]["status"])
        gates = copy.deepcopy(acknowledged["state"]["gates"])
        advanced = self.app.mutate("/api/clock", {"expected_version": acknowledged["session_version"]})
        self.assertEqual(acknowledged["simulation"]["next_response_at"], advanced["state"]["project"]["now"])
        self.assertEqual(gates, advanced["state"]["gates"])
        self.assertTrue(any(c["action"].get("purpose") == "follow_up" for c in advanced["analysis"]["candidates"]))


if __name__ == "__main__":
    unittest.main()
