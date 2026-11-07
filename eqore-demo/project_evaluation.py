"""Whole-project development runs; private progression stays outside model context."""
import copy
from datetime import datetime, timezone
import uuid

import engine
import phases
import projects
from evaluation import _check, _hash_files, _invariants, _summary


def _phase_summary(state):
    view = phases.summarize(state)
    return {"active_phase_ids": view["active_phase_ids"], "all_accepted": view["all_accepted"],
            "open_rework_count": view["open_rework_count"], "resolved_rework_count": view["resolved_rework_count"],
            "phases": [{"id": p["id"], "title": p["title"], "status": p["status"], "acceptance_current": p["acceptance_current"],
                        "completed_task_count": p["completed_task_count"], "task_count": p["task_count"],
                        "milestones": {k: p["milestones"][k] for k in ("planned_start", "planned_finish", "actual_finish")}} for p in view["phases"]],
            "rework": [{k: r.get(k) for k in ("id", "status", "return_phase", "trigger_event_id", "gate_ids", "task_ids", "correction_evidence_ids", "resolution_evidence_ids")}
                       for r in state.get("rework", [])], "warnings": view["warnings"]}


def _project_summary(state):
    return dict(_summary(state), phases=_phase_summary(state))


def run_suite(mode="baseline", decide=None, project_ids=None):
    if mode not in {"baseline", "live"} or (mode == "live" and decide is None):
        raise ValueError("Live project evaluation requires a live decision provider.")
    catalog = {p["id"]: p for p in projects.list_projects()}
    ids = project_ids if project_ids is not None else list(catalog)
    if not ids or not set(ids).issubset(catalog):
        raise ValueError("Select known demo projects.")
    cases = []
    for project_id in ids:
        initial = projects.initial_state(project_id)
        state, cursor, trace, safety, errors = copy.deepcopy(initial), 0, [], [], []
        for step in range(100):
            try:
                before = state
                event = projects.next_event(project_id, cursor, state)
                if event is not None:
                    state = engine.apply_event(state, event)
                    cursor += 1
                    safety.extend(_invariants(before, state))
                    trace.append({"step": step, "type": "project_update", "event_id": event["id"], "summary": event.get("summary"), "state": _project_summary(state)})
                    continue
                if engine.project_complete(state):
                    break
                decision = decide(copy.deepcopy(state)) if mode == "live" else engine.recommend(state)
                action = decision["action"]
                state = engine.apply_action(state, action)
                safety.extend(_invariants(before, state, action))
                entry = {"step": step, "type": "decision", "mode": mode, "action": action, "title": decision.get("title"),
                         "rationale": decision.get("why_now"), "agent_trace": decision.get("agent_trace", []), "responses": []}
                for request in list(state["requests"]):
                    if request.get("status") not in {"pending", "sent", "open"}:
                        continue
                    response = projects.actor_response(state, request)
                    if response is not None:
                        before_reply = state
                        state = engine.apply_event(state, response)
                        safety.extend(_invariants(before_reply, state))
                        entry["responses"].append({"request_id": request["id"], "event_id": response["id"], "summary": response.get("summary")})
                entry["state"] = _project_summary(state)
                trace.append(entry)
                if action["type"] == "wait" and not entry["responses"]:
                    # Advance only to an observed follow-up deadline, not a hidden
                    # future-event outcome. Counterpart review remains unresolved.
                    now = datetime.fromisoformat(state["project"]["now"])
                    deadlines = [datetime.fromisoformat(r["due_at"]) for r in state["requests"]
                                 if r.get("status") == "acknowledged" and r.get("due_at")
                                 and datetime.fromisoformat(r["due_at"]) > now]
                    if deadlines:
                        clock_event = {"id": "project_followup_clock_" + str(step), "type": "clock_advance", "at": min(deadlines).isoformat(),
                                       "summary": "Advance simulation to the next observed review follow-up deadline"}
                        before_clock = state
                        state = engine.apply_event(state, clock_event)
                        safety.extend(_invariants(before_clock, state))
                        trace.append({"step": step, "type": "simulator_clock_advance", "event_id": clock_event["id"], "summary": clock_event["summary"], "state": _project_summary(state)})
                        continue
                    errors.append("Project made no further progress before reaching handoff.")
                    break
            except Exception as exc:
                errors.append(str(exc))
                break
        lines = initial["project"].get("finance", {}).get("lines", [])
        expected_events = catalog[project_id].get("event_count")
        phase_view = phases.summarize(state)
        cycles = state.get("rework", [])
        correction_cycles = [r for r in cycles if r.get("correction_owner_id")]
        late_retest = next((t for t in state["tasks"] if t["id"] == "t_commission"), {})
        loops_exercised = bool(cycles) and all(r.get("status") in ("resolved", "superseded") for r in cycles)
        if project_id in ("harbor_components", "millbrook_cold_storage"):
            loops_exercised = loops_exercised and any(r.get("status") == "resolved" and r.get("correction_evidence_ids") and r.get("resolution_evidence_ids") for r in correction_cycles)
        if project_id == "riverbend_logistics":
            loops_exercised = loops_exercised and bool(late_retest.get("completion_history")) and late_retest.get("status") == "completed"
            fresh_ids = set(late_retest.get("evidence_ids", [])) - set(late_retest.get("invalidated_evidence_ids", []))
            loops_exercised = loops_exercised and any(e["id"] in fresh_ids and e.get("task_id") == "t_commission"
                                                     and e.get("issuer_id") == late_retest.get("owner_id") and e.get("verified")
                                                     and e.get("effective_at") and late_retest.get("invalidated_at")
                                                     and datetime.fromisoformat(e["effective_at"]) >= datetime.fromisoformat(late_retest["invalidated_at"])
                                                     for e in state["evidence"])
        checks = [
            _check("full_lifecycle_reached_handoff", engine.project_complete(state), f"All {len(state['tasks'])} lifecycle tasks and current acceptance gates must close, with no open rework or alerts."),
            _check("all_phase_acceptance_current", phase_view["all_accepted"], "Every post-signing phase requires current, scoped evidence; historical task completion alone is insufficient."),
            _check("correction_and_reacceptance_exercised", loops_exercised, "Reviewer returns require correction then fresh acceptance; a late controls fault requires re-evidenced commissioning while preserving prior history."),
            _check("authority_and_evidence_integrity", not safety, "; ".join(safety) or "Observed transitions preserve scoped evidence and authority."),
            _check("execution_errors", not errors, "; ".join(errors) or "Whole-project actions and counterpart responses succeeded."),
            _check("project_financial_baseline_reconciles", bool(lines) and abs(sum(x["budget"] for x in lines) - initial["project"]["budget"]["baseline"]) < .01, "Detailed project cost assumptions sum to the approved baseline."),
            _check("scripted_project_updates_exercised", cursor > 0 and (expected_events is None or cursor == expected_events), f"Processed {cursor} project updates; expected {expected_events if expected_events is not None else 'at least one'}."),
            _check("evidence_remains_project_scoped", all(e.get("project_id") == state["project"]["id"] for e in state["evidence"]), "No evidence from another demo project is accepted."),
        ]
        cases.append({"id": project_id, "title": catalog[project_id]["name"], "status": "passed" if all(c["passed"] for c in checks) else "failed",
                      "checks": checks, "trace": trace, "final_summary": _project_summary(state), "scenario_version": projects.VERSION})
    passed = sum(c["status"] == "passed" for c in cases)
    return {"id": "projects_" + uuid.uuid4().hex[:12], "suite": "projects", "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(), "product_version": _hash_files(["engine.py", "llm.py", "server.py", "storage.py", "dashboard.py", "reasoning.py", "phases.py"]),
            "scenario_hash": _hash_files(["projects.py", "scenarios.py", "knowledge.json"]), "evaluator_hash": _hash_files(["project_evaluation.py", "evaluation.py"]),
            "summary": {"total": len(cases), "passed": passed, "failed": len(cases) - passed}, "cases": cases,
            "limitations": ["Synthetic development projects with visible authored assumptions; not a held-out benchmark or real EQORE results.",
                            "Counterpart replies and physical completion are simulated. All projects are expected to reach handoff under these response assumptions.",
                            "Cost ledgers are recorded scenario snapshots; task completion does not manufacture invoices or paid spending.",
                            "Baseline mode uses fixed rules. Only reports explicitly labelled live contain fresh ChatGPT inference."]}
