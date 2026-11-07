"""Independent challenge artifact integrity and executable behavior checks."""
import hashlib
import json
from pathlib import Path
import unittest

import challenges


class IndependentChallengeTests(unittest.TestCase):
    def test_fresh_model_design_has_trace_and_frozen_inputs(self):
        artifact = challenges._artifact()
        self.assertEqual(12, len(artifact["designs"]))
        self.assertEqual("Independent challenge designer", artifact["designer_result"]["role"])
        self.assertTrue(artifact["designer_result"]["thread_id"])
        self.assertGreater(artifact["designer_result"]["usage"]["input_tokens"], 0)
        self.assertEqual(0, artifact["raw_invocation"]["returncode"])
        self.assertIn("OBSERVATIONS:", artifact["raw_invocation"]["exact_prompt"])
        self.assertNotIn("baseline_engine_source", artifact["raw_invocation"]["exact_prompt"])
        self.assertNotIn("permitted_candidates", artifact["raw_invocation"]["exact_prompt"])
        self.assertEqual(artifact["product_hashes_at_freeze"]["engine.py"], hashlib.sha256(artifact["baseline_engine_source"].encode()).hexdigest())
        self.assertEqual({d["id"] for d in artifact["designs"]}, set(challenges.PROBES))

    def test_browser_design_omits_private_replay_material(self):
        design = challenges.load_design()
        self.assertTrue(design["available"])
        for key in ("raw_invocation", "frozen_states", "baseline_engine_source", "designer_context"):
            self.assertNotIn(key, design)

    def test_before_results_keep_observed_failures(self):
        report = json.loads((challenges.ROOT / "data/challenge-results-before-v03.json").read_text())
        failures = {c["id"] for c in report["cases"] if c["status"] == "failed"}
        self.assertEqual({"CH03", "CH09"}, failures)
        self.assertEqual(hashlib.sha256(challenges.DESIGN_PATH.read_bytes()).hexdigest(), report["design_sha256"])

    def test_independent_claim_check_reproduces_recorded_live_defect(self):
        report = json.loads((challenges.ROOT / "data/challenge-live-before-v03.json").read_text())
        artifact = challenges._artifact()
        for case_id in ("CH08", "CH11"):
            case = next(c for c in report["cases"] if c["id"] == case_id)
            design = next(d for d in artifact["designs"] if d["id"] == case_id)
            decision = next(t["decision"] for t in case["trace"] if t["operation"] == "live_decision")
            probe = challenges.Probe(None, artifact, design)
            challenges.check_design_claims(probe, probe.state(), decision)
            self.assertFalse(probe.checks[0]["passed"])
            self.assertEqual("explanation", probe.checks[0]["category"])
        self.assertEqual({"safety": 0, "progress": 0, "explanation": 2}, report["failure_counts_by_kind"])

    def test_current_product_satisfies_frozen_executable_checks(self):
        report = challenges.run_suite(phase="after")
        failures = [(c["id"], [x["name"] for x in c["checks"] if not x["passed"]])
                    for c in report["cases"] if c["status"] == "failed"]
        self.assertEqual([], failures)
        self.assertEqual(12, report["summary"]["total"])
        self.assertEqual(0, report["summary"]["live_decisions"])


if __name__ == "__main__":
    unittest.main()
