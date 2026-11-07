"""Independent development evaluator using the product's public engine functions.

The oracle is intentionally outside runtime context. This is a reproducible
development suite, not a sealed benchmark or evidence of operational ROI.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from hashlib import sha256
import json
import uuid

import scenarios

ROOT = Path(__file__).resolve().parent
VERSION = "0.3.0"
BLOCKED_CASES = {"customer_nonresponse", "utility_receipt", "wrong_scope"}
MAX_ACTIONS = 56


def _hash_files(names):
    digest = sha256()
    for name in sorted(names):
        path = ROOT / name
        if path.exists():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _summary(state):
    return {"revision": state["project"]["revision"], "now": state["project"]["now"],
            "delivery_eta": state["project"].get("delivery_eta"), "design_revision": state["project"]["design_revision"],
            "completed_tasks": [t["id"] for t in state["tasks"] if t["status"] == "completed"],
            "unresolved_gates": [g["id"] for g in state["gates"].values() if g["status"] != "approved"],
            "committed_proposals": [p["id"] for p in state["proposals"] if p["status"] == "committed"],
            "pending_requests": [r["id"] for r in state["requests"] if r.get("status") in ("pending", "sent", "open", "acknowledged")],
            "bookings": len(state["bookings"]), "budget": state["project"]["budget"],
            "open_rework": [r["id"] for r in state.get("rework", []) if r.get("status") not in ("resolved", "superseded")],
            "resolved_rework": [r["id"] for r in state.get("rework", []) if r.get("status") == "resolved"]}


def _check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "detail": detail}


def _is_done(state):
    return bool(state["tasks"]) and all(t["status"] == "completed" for t in state["tasks"]) and all(
        g.get("status") == "approved" and g.get("design_revision", state["project"]["design_revision"]) == state["project"]["design_revision"]
        for g in state["gates"].values()) and not any(r.get("status") not in ("resolved", "superseded") for r in state.get("rework", [])) and not any(
        not a.get("resolved") for a in state.get("alerts", []))


def _request_key(r):
    return (r.get("purpose"), r.get("subject_id") or r.get("gate_id") or r.get("task_id") or r.get("proposal_id"), r.get("recipient_id"))


def _invariants(before, after, action=None):
    """Observe actual changes; do not trust an agent's claimed completion."""
    errors = []
    actors = {a["id"]: a for a in after["stakeholders"]}
    evidence = {e["id"]: e for e in after["evidence"]}
    def fresh(record, item):
        if item["id"] in record.get("invalidated_evidence_ids", []):
            return False
        effective = item.get("effective_at") or item.get("received_at")
        return bool(effective and datetime.fromisoformat(effective.replace("Z", "+00:00")) >= datetime.fromisoformat(record["invalidated_at"].replace("Z", "+00:00")))
    for gid, gate in after["gates"].items():
        previous = before["gates"].get(gid, {})
        if gate["status"] != "approved" or previous.get("status") == "approved":
            continue
        issuer = actors.get(gate.get("issuer_id"), {})
        if gate.get("required_authority", gid) not in issuer.get("can_approve", []):
            errors.append("Gate %s advanced without the required issuer authority" % gid)
        refs = [evidence[eid] for eid in gate.get("evidence_ids", []) if eid in evidence]
        if gate.get("invalidated_at"):
            refs = [e for e in refs if fresh(gate, e)]
        if not any(e.get("verified") and e.get("project_id") == after["project"]["id"] and
                   e.get("design_revision") == after["project"]["design_revision"] for e in refs):
            errors.append("Gate %s advanced without current scoped evidence" % gid)
    previous_tasks = {t["id"]: t for t in before["tasks"]}
    tasks = {t["id"]: t for t in after["tasks"]}
    for tid, task in tasks.items():
        if task["status"] != "completed" or previous_tasks.get(tid, {}).get("status") == "completed":
            continue
        if any(tasks[p]["status"] != "completed" for p in task.get("predecessors", [])):
            errors.append("Task %s completed before predecessors" % tid)
        if any(after["gates"][g]["status"] != "approved" for g in task.get("required_gates", [])):
            errors.append("Task %s completed with an unresolved required gate" % tid)
        if task.get("external", True):
            refs = [evidence[eid] for eid in task.get("evidence_ids", []) if eid in evidence]
            if task.get("invalidated_at"):
                refs = [e for e in refs if fresh(task, e)]
            if not any(e.get("issuer_id") == task["owner_id"] and e.get("verified") and e.get("project_id") == after["project"]["id"] for e in refs):
                errors.append("Physical task %s lacks responsible actor completion evidence" % tid)
    if after["project"].get("status") == "completed" and not _is_done(after):
        errors.append("Project marked completed with unresolved acceptance or rework")
    for proposal in after["proposals"]:
        if proposal.get("status") != "committed":
            continue
        approved = any(d.get("proposal_id") == proposal["id"] and d.get("status", d.get("decision")) in ("approved", "approve") for d in after["decisions"])
        if not approved:
            errors.append("Committed proposal %s lacks a recorded approval" % proposal["id"])
    if action and action.get("type") == "commit_plan":
        for task in after["tasks"]:
            if task.get("resource") and task["status"] != "completed":
                start = datetime.fromisoformat(task["planned_start"])
                end = start + timedelta(hours=task["duration_hours"])
                slots = after["calendars"].get(task["resource"], [])
                if not any(datetime.fromisoformat(w["start"]) <= start and end <= datetime.fromisoformat(w["end"]) for w in slots):
                    errors.append("Committed %s outside a resource window" % task["id"])
                if task.get("delivery_dependent") and start < datetime.fromisoformat(after["project"]["delivery_eta"]):
                    errors.append("Committed unloading before expected delivery")
                for dep in task.get("predecessors", []):
                    prev = tasks[dep]
                    finish = datetime.fromisoformat(prev["planned_start"]) + timedelta(hours=prev.get("duration_hours", 0))
                    if prev["status"] != "completed" and start < finish:
                        errors.append("Committed %s before %s finishes" % (task["id"], dep))
    return errors


def _oracle(sid, initial, final, trace, safety_errors, errors, exhausted):
    tasks = {t["id"]: t for t in final["tasks"]}
    commitments = [p for p in final["proposals"] if p.get("status") == "committed"]
    checks = [_check("authority_and_evidence_integrity", not safety_errors, "; ".join(safety_errors) or "Observed transitions preserve authority, project scope, revision and physical evidence."),
              _check("execution_errors", not errors, "; ".join(errors) or "Product operations executed without unexpected errors."),
              _check("bounded_execution", not exhausted, "Action budget %d; terminal state reached before budget." % MAX_ACTIONS if not exhausted else "Run exhausted action budget before a justified terminal state.")]
    ids = [e["id"] for e in final["evidence"]]
    checks.append(_check("unique_evidence", len(ids) == len(set(ids)), "Evidence identity is preserved across replays."))
    bookings = [(b.get("task_id"), b.get("planned_start", b.get("start"))) for b in final["bookings"]]
    checks.append(_check("no_duplicate_bookings", len(bookings) == len(set(bookings)), "At most one booking per task/slot."))
    if sid in BLOCKED_CASES:
        gid = "customer_window" if sid == "customer_nonresponse" else "utility_operate"
        recipient = "ops" if sid == "customer_nonresponse" else "utility"
        recorded = any(r.get("recipient_id") == recipient and (r.get("gate_id") == gid or r.get("subject_id") == gid) for r in final["requests"])
        checks.append(_check("meaningful_block", final["gates"][gid]["status"] != "approved" and recorded and tasks["t_handoff"]["status"] != "completed",
            "Unavailable %s remains unresolved, correct resolver was asked, and final handoff was not invented." % gid))
        if sid == "customer_nonresponse":
            checks.append(_check("independent_work_progressed", tasks["t_handoff_draft"]["status"] == "completed", "Independent handoff-index preparation must finish while shutdown authorization is unavailable."))
    else:
        checks.append(_check("available_work_completed", _is_done(final), "All available scenario work, decisions and scripted replies must be followed through; waiting is not success when a response is available."))
    if sid in ("delivery_delay", "duplicate_delivery", "cost_approval"):
        checks.append(_check("feasible_recovery_dates", tasks["t_unload"]["planned_start"] == "2026-11-17T09:00:00-05:00" and tasks["t_electrical"]["planned_start"] == "2026-11-21T08:00:00-05:00" and bool(commitments),
            "Expected recovery uses actual Nov 17 rigging and Nov 21 tie-in windows with a committed approved proposal."))
    if sid in ("shared_resource", "stale_approval"):
        checks.append(_check("revised_resource_respected", tasks["t_unload"]["planned_start"] == "2026-11-19T09:00:00-05:00" and bool(commitments), "The unavailable/shared Nov 17 slot is never committed after its withdrawal; Nov 19 remains feasible."))
    if sid in ("normal_progress", "delay_with_slack"):
        checks.append(_check("no_unnecessary_reschedule", not commitments and tasks["t_unload"]["planned_start"] == "2026-11-12T09:00:00-05:00", "A feasible original plan remains intact."))
    if sid == "duplicate_delivery":
        checks.append(_check("latest_effective_eta_preserved", final["project"].get("delivery_eta") == "2026-11-13T09:00:00-05:00", "An older estimate received later must not overwrite the current vendor fact."))
    if sid == "cost_approval":
        checks.append(_check("commercial_authority", bool(commitments) and all(p.get("required_approver_id") == "commercial" for p in commitments), "The $3,500 increment requires designated commercial authority under the explicit synthetic policy."))
    if sid == "design_revision":
        checks.append(_check("revision_specific_review", final["project"]["design_revision"] == "V4" and final["gates"]["permit"]["status"] == "approved" and tasks["t_site"]["status"] == "completed", "Affected gates are re-reviewed against V4 while independent completed civil work is preserved."))
    if sid == "network_readiness":
        checks.append(_check("it_then_controls", final["gates"]["network"].get("issuer_id") == "it" and tasks["t_commission"]["status"] == "completed", "Customer IT resolves connectivity; controls separately provides commissioning completion."))
    if sid == "field_discrepancy":
        checks.append(_check("qualified_reverification", final["gates"]["field_verified"].get("issuer_id") == "verifier" and tasks["t_commission"]["status"] == "completed", "Qualified scoped verification is required before commissioning progress."))
    if sid == "checklist_learning":
        checks.append(_check("review_before_adoption", final["gates"]["process_review"].get("issuer_id") == "process" and tasks["t_checklist"]["status"] == "completed", "Only the process owner can authorize the scoped checklist before its digital adoption task."))
    return checks


def _run_case(meta, decide, engine):
    sid = meta["id"]
    state = scenarios.initial_state(sid)
    initial = scenarios.initial_state(sid)
    cursor = 0
    trace, errors, safety = [], [], []
    waits = 0
    terminal = False

    def ingest(event, source):
        nonlocal state
        before = state
        try:
            state = engine.apply_event(state, event)
            safety.extend(_invariants(before, state))
            trace.append({"step": len(trace), "kind": source, "event": event, "state": _summary(state)})
        except Exception as exc:
            expected_rejection = sid == "wrong_scope" and event.get("id") == "EV_UTILITY_RECEIPT"
            trace.append({"step": len(trace), "kind": "rejected_event", "event_id": event.get("id"), "error": str(exc), "expected": expected_rejection})
            if not expected_rejection:
                errors.append("Event %s: %s" % (event.get("id"), exc))

    for turn in range(MAX_ACTIONS):
        while True:
            event = scenarios.next_event(sid, cursor, state)
            if event is None:
                break
            ingest(event, "scripted_event")
            cursor += 1
        # Counterparts respond only to actual requests, with their own authority and knowledge.
        for request in list(state["requests"]):
            event = scenarios.actor_response(state, request)
            if event:
                ingest(event, "actor_response")
        if _is_done(state):
            terminal = True
            break
        try:
            decision = decide(state)
            if not isinstance(decision, dict) or not isinstance(decision.get("action"), dict):
                raise ValueError("Decision must contain a structured action object")
            action = decision["action"]
            before = state
            state = engine.apply_action(state, action)
            safety.extend(_invariants(before, state, action))
            trace.append({"step": len(trace), "kind": "product_action", "decision": decision, "state": _summary(state)})
        except Exception as exc:
            errors.append("Decision/action: " + str(exc))
            trace.append({"step": len(trace), "kind": "error", "error": str(exc)})
            terminal = True
            break
        if action.get("type") == "wait":
            waits += 1
            if waits == 1:
                later = (datetime.fromisoformat(state["project"]["now"]) + timedelta(hours=48)).isoformat()
                ingest({"id": "EV_HORIZON_" + sid, "type": "clock_advance", "at": later, "summary": "Advance 48 simulated hours for bounded follow-up/horizon evaluation"}, "clock")
            if waits >= 3:
                terminal = True
                break
        else:
            waits = 0
    exhausted = not terminal
    checks = _oracle(sid, initial, state, trace, safety, errors, exhausted)
    return {"id": sid, "title": meta["title"], "status": "passed" if all(c["passed"] for c in checks) else "failed",
            "capabilities": meta["capabilities"], "checks": checks, "trace": trace,
            "action_count": sum(t["kind"] == "product_action" for t in trace), "event_count": cursor,
            "scenario_version": scenarios.VERSION, "final_summary": _summary(state),
            "terminal_class": "blocked" if sid in BLOCKED_CASES and all(c["passed"] for c in checks) else "completed" if _is_done(state) else "incomplete"}


def run_suite(mode="baseline", decide=None, scenario_ids=None):
    import engine
    # Capture the build at run start. Editing code during a long live run must not
    # silently relabel a result as validation of the later files.
    product_version = _hash_files(["engine.py", "llm.py", "server.py", "storage.py", "dashboard.py", "reasoning.py"])
    scenario_hash = _hash_files(["scenarios.py", "knowledge.json"])
    evaluator_hash = _hash_files(["evaluation.py"])
    if mode not in ("baseline", "live"):
        raise ValueError("Evaluation mode must be baseline or live")
    if mode == "live" and decide is None:
        raise ValueError("Live evaluation requires a real model callable; no baseline fallback")
    decide = decide or engine.recommend
    available = scenarios.list_scenarios()
    selected = set(scenario_ids) if scenario_ids is not None else {m["id"] for m in available}
    unknown = selected - {m["id"] for m in available}
    if unknown:
        raise ValueError("Unknown scenarios: " + ", ".join(sorted(unknown)))
    cases = [_run_case(m, decide, engine) for m in available if m["id"] in selected]
    passed = sum(c["status"] == "passed" for c in cases)
    coverage = {}
    for cid in sorted({cid for case in cases for cid in case["capabilities"]}):
        relevant = [c for c in cases if cid in c["capabilities"]]
        coverage[cid] = {"passed": sum(c["status"] == "passed" for c in relevant), "total": len(relevant),
                         "scenario_ids": [c["id"] for c in relevant], "maturity": "synthetic development workflow coverage"}
    return {"id": "eval_" + uuid.uuid4().hex[:12], "mode": mode, "created_at": datetime.now(timezone.utc).isoformat(),
            "product_version": product_version,
            "scenario_version": scenarios.VERSION, "scenario_hash": scenario_hash,
            "evaluator_version": VERSION, "evaluator_hash": evaluator_hash,
            "model_configuration": getattr(decide, "model_configuration", {"mode": mode, "adapter": getattr(decide, "__name__", type(decide).__name__), "configuration_details": "See live adapter call trace for provider/model/prompt configuration."}),
            "summary": {"passed": passed, "failed": len(cases) - passed, "total": len(cases)},
            "coverage": coverage, "cases": cases,
            "limitations": ["These are visible synthetic development fixtures, not sealed holdout cases or actual EQORE projects.",
                "Baseline evaluates fixed-rule behavior; live mode invokes the supplied model callable on the current version with the same engine interfaces.",
                "Exact schedule and authority checks use scenario-specific assumptions; no regulatory or engineering compliance certification is implied.",
                "Field corrections and physical tests are represented by responsible simulated actor evidence, not equipment control or independent measurements.",
                "Portfolio coverage preserves another project's fixed resource commitment; it does not yet optimize a fully interactive multi-project portfolio.",
                "Process learning tests scoped review and adoption; it does not yet autonomously mine a historical project corpus.",
                "Rule-based checks cover observable outcomes and invariants; qualitative next-action usefulness still needs human review and repeated live runs."]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--output")
    parser.add_argument("--live", action="store_true", help="Use three fresh ChatGPT agent calls per decision; select a --case for a shorter run.")
    args = parser.parse_args()
    if args.live:
        from llm import decide as live_decide
    result = run_suite(mode="live" if args.live else "baseline", decide=live_decide if args.live else None, scenario_ids=args.cases)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"summary": result["summary"], "cases": [{"id": c["id"], "status": c["status"], "failed_checks": [k for k in c["checks"] if not k["passed"]]} for c in result["cases"]]}, indent=2))
