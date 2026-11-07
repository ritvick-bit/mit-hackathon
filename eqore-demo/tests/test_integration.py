import copy
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import engine
import llm
import scenarios
from server import Application, Handler
from storage import Conflict, Store


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = self.tmp.name + "/state.sqlite3"
        self.auth_patch = patch("llm.runtime_status", return_value={"available": True, "authenticated": True, "detail": "test"})
        self.auth_patch.start()
        self.app = Application(self.db)

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.auth_patch.stop()
        self.tmp.cleanup()

    def test_persistence_and_stale_browser_rejection(self):
        first = self.app.bootstrap()
        action = first["recommendation"]["action"]
        updated = self.app.mutate("/api/action", {"action": action, "expected_version": first["session_version"]})
        self.assertGreater(updated["session_version"], first["session_version"])
        self.assertEqual(Store(self.db).read()["state"], updated["state"])
        with self.assertRaises(Conflict):
            self.app.mutate("/api/action", {"action": action, "expected_version": first["session_version"]})

    def test_browser_action_without_snapshot_version_is_rejected(self):
        initial = self.app.store.read()
        with self.assertRaises(Conflict):
            self.app.mutate("/api/action", {"action": engine.recommend(initial["state"])["action"]})
        self.assertEqual(self.app.store.read(), initial)

    def test_reasoning_trace_survives_action_and_restart(self):
        initial = self.app.store.read()
        recommendation = dict(engine.recommend(initial["state"]), mode="baseline", agent_trace=[{"role": "test", "output": "decision explanation"}])
        self.app.store.save_recommendation(recommendation, initial["version"])
        self.app.mutate("/api/action", {"action": recommendation["action"], "expected_version": initial["version"]})
        records = Store(self.db).reasoning(include_context=True)
        self.assertEqual(records[0]["recommendation"], recommendation)
        self.assertEqual(records[0]["observed_state"], initial["state"])

    def test_inflight_decision_discarded_after_project_change(self):
        started, finish = threading.Event(), threading.Event()

        def slow_decide(state):
            started.set()
            finish.wait(5)
            return dict(engine.recommend(state), mode="live")
        with patch("llm.decide", side_effect=slow_decide):
            job = self.app.submit("decide", {"mode": "live"})["job_id"]
            self.assertTrue(started.wait(2))
            self.app.mutate("/api/reset", {"scenario_id": "delivery_delay"})
            finish.set()
            for _ in range(100):
                if self.app.jobs[job]["status"] != "running":
                    break
                time.sleep(.01)
        self.assertEqual(self.app.jobs[job]["status"], "failed")
        self.assertIsNone(self.app.store.read()["recommendation"])

    def test_failed_live_call_has_no_silent_baseline_substitution(self):
        with patch("llm.decide", side_effect=llm.ModelError("test inference failure")):
            job = self.app.submit("decide", {"mode": "live"})["job_id"]
            for _ in range(100):
                if self.app.jobs[job]["status"] != "running":
                    break
                time.sleep(.01)
        self.assertEqual(self.app.jobs[job]["status"], "failed")
        self.assertIn("test inference failure", self.app.jobs[job]["error"])
        self.assertIsNone(self.app.store.read()["recommendation"])

    def test_http_blocks_cross_origin_and_private_files(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%s" % server.server_address[1]
        try:
            with urlopen(base + "/api/health") as response:
                self.assertTrue(json.load(response)["ok"])
            for path in ("/scenarios.py", "/evaluation.py", "/data/eqore.sqlite3", "/../knowledge.json"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            request = Request(base + "/api/reset", data=b'{"scenario_id":"delivery_delay"}',
                              headers={"Content-Type": "application/json", "Origin": "https://unrelated.example"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()


class ModelBoundaryTests(unittest.TestCase):
    def test_electrician_availability_does_not_grant_customer_access(self):
        state = scenarios.initial_state("delivery_delay")
        state = engine.apply_event(state, scenarios.next_event("delivery_delay", 0, state))
        # Both tasks fit contractor calendars, but the customer never offered Nov 28.
        with self.assertRaisesRegex(engine.DomainError, "customer_access"):
            engine.apply_action(state, {"type": "propose_plan", "cost_delta": 1200,
                "changes": [{"task_id": "t_unload", "planned_start": "2026-11-17T09:00:00-05:00"},
                            {"task_id": "t_electrical", "planned_start": "2026-11-28T08:00:00-05:00"},
                            {"task_id": "t_verify", "planned_start": "2026-11-29T09:00:00-05:00"},
                            {"task_id": "t_commission", "planned_start": "2026-11-30T09:00:00-05:00"},
                            {"task_id": "t_handoff", "planned_start": "2026-12-01T09:00:00-05:00"}]})

    def test_curated_context_and_candidate_action_validation(self):
        state = scenarios.initial_state("delivery_delay")
        state = engine.apply_event(state, scenarios.next_event("delivery_delay", 0, state))
        seen = []

        def fake_call(role, instruction, context, schema):
            seen.append(copy.deepcopy(context))
            result = {key: [] if definition["type"] == "array" else "Test explanation" for key, definition in schema["properties"].items()}
            if "candidate_id" in result:
                result["candidate_id"] = context["permitted_candidates"][0]["candidate_id"]
            return {"role": role, "output": result, "mode": "test"}
        with patch("llm._call", side_effect=fake_call):
            decision = llm.decide(state)
        self.assertEqual(len(seen), 3)
        for context in seen:
            self.assertNotIn("scenario_id", context["project"])
            self.assertNotIn("capabilities", context["reference_knowledge"])
            self.assertNotIn("trace", context)
        self.assertEqual(decision["action"]["type"], engine.analyze(state)["candidates"][0]["action"]["type"])
        engine.apply_action(state, decision["action"])

    def test_unknown_model_candidate_is_rejected(self):
        def fake_call(role, instruction, context, schema):
            result = {key: [] if definition["type"] == "array" else "unknown" for key, definition in schema["properties"].items()}
            return {"role": role, "output": result}
        with patch("llm._call", side_effect=fake_call), self.assertRaises(llm.ModelError):
            llm.decide(scenarios.initial_state("delivery_delay"))


if __name__ == "__main__":
    unittest.main()
