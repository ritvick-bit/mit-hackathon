"""Post-signing phase view derived only from the project's observed records.

Grouping does not add serial dependencies or calculate a critical path. Historical
completion and current acceptance are separate: a later rejection can reopen a
review without pretending that delivered equipment was never installed.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone


VERSION = "post-signing-phases-1"

CATALOG = (
    {"id": "signed_scope", "title": "Signed scope · entry", "task_ids": ["t_contract"], "gate_ids": [],
     "description": "Begin with the signed scope, budget, customer contacts and decision authority.",
     "exit_criteria": ["Signed scope and project responsibility are recorded."], "source_ids": ["SRC_EQORE_PM"]},
    {"id": "site_design", "title": "Site survey & design", "task_ids": ["t_survey", "t_design"], "gate_ids": ["design"],
     "description": "Confirm site constraints and issue the responsible engineer's project design.",
     "exit_criteria": ["Survey constraints are recorded.", "The responsible engineer accepts the current issued design."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_PROCESS"]},
    {"id": "reviews", "title": "Permits & utility review", "task_ids": ["t_permit", "t_utility"], "gate_ids": ["permit", "fire_review", "utility_install"],
     "description": "Coordinate the applicable local, fire and utility installation reviews as separate authority tracks.",
     "exit_criteria": ["Applicable local and fire review conditions are accepted.", "The installation-stage utility conditions are accepted; operating permission remains separate."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_PROCESS", "SRC_NG_MA_1646"]},
    {"id": "procurement_site", "title": "Procurement & site preparation", "task_ids": ["t_procure", "t_site"], "gate_ids": [],
     "description": "Coordinate the ordered equipment and site readiness; each work package keeps its own prerequisites.",
     "exit_criteria": ["The ordered configuration and shipping record are confirmed.", "Qualified site personnel confirm pad, access and delivery-route readiness."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_PROCESS"]},
    {"id": "installation", "title": "Delivery & installation", "task_ids": ["t_unload", "t_electrical"], "gate_ids": ["delivery_receipt", "customer_window"],
     "description": "Confirm physical receipt, contractor bookings and customer interruption authority before placement and tie-in.",
     "exit_criteria": ["Physical receiving evidence and placement are recorded.", "Installation completion is evidenced against the issued design and authorized customer window."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_PROCESS"]},
    {"id": "verification", "title": "Verification & operating authorization", "task_ids": ["t_verify"], "gate_ids": ["corrective_work", "field_verified", "final_inspection", "utility_operate"],
     "description": "Close installation findings, obtain applicable inspection or utility witness results, and record written operating authority.",
     "exit_criteria": ["Qualified verification and applicable inspection findings are closed.", "Any required utility witness or acceptance conditions are satisfied before written operating authorization."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_PROCESS", "SRC_NG_MA_1646"]},
    {"id": "commissioning", "title": "Operational commissioning", "task_ids": ["t_commission"], "gate_ids": ["network", "commissioned"],
     "description": "Run the demo's operational controls tests after its required inspection and operating-authority gates.",
     "exit_criteria": ["Customer IT confirms the agreed network route.", "Controls accepts functional and metering results; network reachability alone is insufficient."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_FLEET", "SRC_ETB"]},
    {"id": "handoff", "title": "Documents, training & fleet handoff", "task_ids": ["t_closeout_documents", "t_customer_training", "t_handoff", "t_handoff_draft"], "gate_ids": ["fleet_ready"],
     "description": "Deliver current as-builts, customer instruction, telemetry acceptance and named operational support.",
     "exit_criteria": ["Required closeout documents and customer walkthrough are recorded.", "Fleet accepts telemetry, alert routing and support ownership."], "source_ids": ["SRC_EQORE_PM", "SRC_EQORE_FLEET", "SRC_EQORE_PROCESS"]},
)

_TASK_PHASE = {tid: phase["id"] for phase in CATALOG for tid in phase["task_ids"]}
_GATE_PHASE = {gid: phase["id"] for phase in CATALOG for gid in phase["gate_ids"]}
_PHASE_IDS = {phase["id"] for phase in CATALOG}
_OPEN_REQUESTS = {"pending", "acknowledged"}


def _date(value):
    try:
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _latest(values):
    dated = [(date, value) for value in values if (date := _date(value))]
    return max(dated)[1] if dated else None


def _earliest(values):
    dated = [(date, value) for value in values if (date := _date(value))]
    return min(dated)[1] if dated else None


def _finish(task):
    date = _date(task.get("planned_start"))
    try:
        return (date + timedelta(hours=float(task.get("duration_hours", 0)))).isoformat() if date else None
    except (ValueError, TypeError, OverflowError):
        return None


def _person(people, identity):
    person = people.get(identity, {})
    return {"id": identity, "name": person.get("name", identity), "role": person.get("role", "Responsible party not recorded")}


def _task_phase(task):
    explicit = task.get("phase_id")
    return explicit if explicit in _PHASE_IDS else _TASK_PHASE.get(task["id"], _TASK_PHASE.get(task.get("original_task_id")))


def summarize(state, analysis=None):
    """Return read-only phase progress, current acceptance and evidenced rework.

    ``analysis`` is optional engine analysis; its schedule impacts are displayed
    as recorded constraints, never used to invent timing or an action.
    """
    project = state.get("project", {})
    tasks = {t["id"]: t for t in state.get("tasks", [])}
    gates = state.get("gates", {})
    people = {p["id"]: p for p in state.get("stakeholders", [])}
    evidence = {e["id"]: e for e in state.get("evidence", [])}
    phase_of = {tid: _task_phase(task) for tid, task in tasks.items()}
    now = _date(project.get("now"))
    warnings = []

    def evidence_valid(item, current=False):
        if not item or not item.get("verified") or item.get("project_id") != project.get("id"):
            return False
        if item.get("status") in ("draft", "rejected", "superseded"):
            return False
        if current and item.get("design_revision") != project.get("design_revision"):
            return False
        observed = _date(item.get("effective_at") or item.get("received_at"))
        return not (now and observed and observed > now)

    def fresh_for(record, item):
        if item.get("id") in record.get("invalidated_evidence_ids", []):
            return False
        cutoff = _date(record.get("invalidated_at"))
        observed = _date(item.get("effective_at") or item.get("received_at"))
        return not cutoff or bool(observed and observed >= cutoff)

    def gate_result(identity, seen=()):
        gate = gates.get(identity)
        if not gate:
            return False, "Required gate is not present in the project record."
        if identity in seen:
            return False, "Gate dependency cycle requires review."
        if gate.get("status") != "approved":
            return False, "Recorded status: " + str(gate.get("status", "unknown")) + "."
        if any(r.get("status") == "correction_required" and identity in r.get("gate_ids", []) for r in state.get("rework", [])):
            return False, "The scoped correction must be evidenced before acceptance can be renewed."
        if gate.get("design_revision") and gate["design_revision"] != project.get("design_revision"):
            return False, "Acceptance belongs to a different design revision."
        actor = people.get(gate.get("issuer_id"), {})
        scope = gate.get("required_authority", identity)
        if scope not in actor.get("can_approve", []) and "*" not in actor.get("can_approve", []):
            return False, "The recorded issuer does not hold the required authority."
        if actor.get("project_ids") is not None and project.get("id") not in actor["project_ids"]:
            return False, "The recorded issuer is not scoped to this project."
        carry = gate.get("carry_forward", {})
        impact = evidence.get(carry.get("evidence_id"))
        reviewer = people.get(carry.get("issuer_id"), {})
        carry_valid = (carry.get("to_revision") == project.get("design_revision")
                       and evidence_valid(impact, current=True)
                       and impact.get("issuer_id") == carry.get("issuer_id")
                       and bool({"design", "design_revision", "*"}.intersection(reviewer.get("can_approve", [])))
                       and (reviewer.get("project_ids") is None or project.get("id") in reviewer["project_ids"]))
        valid = [evidence[eid] for eid in gate.get("evidence_ids", []) if eid in evidence
                 and evidence_valid(evidence[eid], gate.get("design_sensitive", True) and not (carry_valid and eid in carry.get("accepted_evidence_ids", [])))
                 and fresh_for(gate, evidence[eid])
                 and evidence[eid].get("issuer_id") == gate.get("issuer_id")
                 and evidence[eid].get("kind") not in ("receipt", "acknowledgement", "acknowledged", "correction_record", "request", "draft")]
        if not valid:
            return False, "A scoped, verified acceptance record from the authorized issuer is missing."
        for other in gate.get("required_gates", []):
            if not gate_result(other, seen + (identity,))[0]:
                return False, "Prerequisite acceptance is unresolved: " + other + "."
        return True, "Current scoped acceptance is recorded."

    gate_checks = {gid: gate_result(gid) for gid in gates}

    def completion(task):
        records = [evidence[eid] for eid in task.get("evidence_ids", []) if eid in evidence
                   and evidence_valid(evidence[eid]) and evidence[eid].get("issuer_id") == task.get("owner_id")
                   and fresh_for(task, evidence[eid])
                   and evidence[eid].get("kind") in ("task_completion", "completion", "contract")
                   and evidence[eid].get("task_id") in (None, task["id"])]
        completed = task.get("status") == "completed"
        actual = task.get("completed_at")
        if not _date(actual) or (now and _date(actual) > now):
            actual = _latest([e.get("effective_at") for e in records])
        # A task's timestamp alone is not a completion attestation.
        return {"task_id": task["id"], "title": task.get("title", task["id"]), "completed": completed,
                "evidenced": completed and bool(records), "actual_finish": actual if completed and records else None,
                "evidence_ids": [e["id"] for e in records], "previous_completions": deepcopy(task.get("completion_history", []))}

    task_records = {tid: completion(task) for tid, task in tasks.items()}

    def ancestors(identity, seen=()):
        if identity in seen:
            return set()
        found = set()
        for before in tasks.get(identity, {}).get("predecessors", []):
            found.add(before)
            found.update(ancestors(before, seen + (identity,)))
        return found

    def gate_closure(ids):
        result = set(ids)
        while True:
            extra = {other for gid in result for other in gates.get(gid, {}).get("required_gates", [])}
            if extra.issubset(result):
                return result
            result.update(extra)

    rework = deepcopy(state.get("rework", []))
    open_rework = [r for r in rework if r.get("status") not in ("resolved", "superseded")]
    alerts = [a for a in state.get("alerts", []) if not a.get("resolved")]
    requests = [r for r in state.get("requests", []) if r.get("status") in _OPEN_REQUESTS]
    impacts = (analysis or {}).get("impacts", [])
    rows = []
    edges = set()
    for meta in CATALOG:
        identity = meta["id"]
        task_ids = [tid for tid in tasks if phase_of[tid] == identity]
        own_gate_ids = [gid for gid in meta["gate_ids"] if gid in gates]
        if not task_ids and not own_gate_ids:
            continue
        row = deepcopy(meta)
        row["task_ids"], row["gate_ids"] = task_ids, own_gate_ids
        relevant_tasks = set(task_ids)
        for tid in task_ids:
            relevant_tasks.update(ancestors(tid))
        relevant_gates = gate_closure(set(own_gate_ids) | {gid for tid in relevant_tasks for gid in tasks.get(tid, {}).get("required_gates", [])})
        for tid in task_ids:
            for before in tasks[tid].get("predecessors", []):
                previous = phase_of.get(before)
                if previous and previous != identity:
                    edges.add((previous, identity, "task_dependency"))
        for gid in relevant_gates:
            previous = _GATE_PHASE.get(gid)
            if previous and previous != identity:
                edges.add((previous, identity, "acceptance_dependency"))
        own_invalid = [gid for gid in own_gate_ids if not gate_checks.get(gid, (False,))[0]]
        upstream_invalid = [gid for gid in sorted(relevant_gates) if gid not in own_gate_ids and not gate_checks.get(gid, (False,))[0]]
        related_rework = [r for r in open_rework
                          if (r.get("status") == "correction_required" and r.get("return_phase") == identity)
                          or any(tid in task_ids and not task_records[tid]["evidenced"] for tid in r.get("task_ids", []))
                          or any(gid in own_gate_ids and not gate_checks.get(gid, (False,))[0] for gid in r.get("gate_ids", []))]
        related_alerts = [a for a in alerts if a.get("gate_id") in own_gate_ids or set(a.get("task_ids", [])).intersection(task_ids)]
        related_requests = [r for r in requests if r.get("gate_id", r.get("subject_id")) in own_gate_ids or r.get("task_id", r.get("subject_id")) in task_ids]
        completed_ids = [tid for tid in task_ids if task_records[tid]["completed"]]
        missing_completion = [tid for tid in completed_ids if not task_records[tid]["evidenced"]]
        incomplete = [tid for tid in task_ids if tid not in completed_ids]
        external_before = {before for tid in task_ids for before in tasks[tid].get("predecessors", []) if before not in task_ids}
        entry_available = any(all(task_records.get(before, {}).get("evidenced") for before in tasks[tid].get("predecessors", [])) for tid in task_ids)
        ready_tasks = [tid for tid in incomplete if all(task_records.get(before, {}).get("evidenced") for before in tasks[tid].get("predecessors", []))
                       and all(gate_checks.get(gid, (False,))[0] for gid in tasks[tid].get("required_gates", []))
                       and all(gate_checks.get(gid, (False,))[0] for before in ancestors(tid) for gid in tasks.get(before, {}).get("required_gates", []))]
        ready_gates = [gid for gid in own_invalid if entry_available
                       and all(task_records.get(tid, {}).get("evidenced") for tid in gates[gid].get("required_tasks", []))
                       and all(gate_checks.get(other, (False,))[0] for other in gates[gid].get("required_gates", []))]
        prior_reopened = [gid for gid in own_invalid if gates[gid].get("status") == "blocked" or gates[gid].get("evidence_ids")
                          or any(tid in completed_ids and gid in tasks[tid].get("required_gates", []) for tid in task_ids)]
        blockers = []
        for gid in own_invalid + upstream_invalid:
            gate = gates.get(gid, {})
            blockers.append({"kind": "gate", "id": gid, "title": gate.get("label", gid), "reason": gate_checks.get(gid, (False, "Required gate is missing."))[1],
                             "owner": _person(people, gate.get("resolver_id")), "upstream": gid not in own_gate_ids,
                             "evidence_ids": deepcopy(gate.get("evidence_ids", []))})
        for before in sorted(external_before):
            if not task_records.get(before, {}).get("evidenced"):
                blockers.append({"kind": "task", "id": before, "title": tasks.get(before, {}).get("title", before), "reason": "Predecessor completion is not evidenced.", "upstream": True})
        for tid in missing_completion:
            blockers.append({"kind": "evidence", "id": tid, "title": tasks[tid].get("title", tid), "reason": "Marked complete, but scoped completion evidence is missing.", "upstream": False})
        for alert in related_alerts:
            blockers.append({"kind": "alert", "id": alert["id"], "title": alert.get("title", "Unresolved finding"), "reason": "This observed finding remains open.", "evidence_ids": deepcopy(alert.get("evidence_ids", [])), "upstream": False})
        for impact in impacts:
            if impact.get("task_id") in incomplete:
                blockers.append({"kind": "schedule", "id": impact.get("task_id"), "title": impact.get("message", "Schedule constraint"), "reason": impact.get("message", "Recorded schedule conflict."), "upstream": False})
        own_accepted = bool(task_ids) and not incomplete and not missing_completion and not own_invalid and not related_rework and not related_alerts
        acceptance_current = own_accepted and not upstream_invalid and all(task_records.get(before, {}).get("evidenced") for before in relevant_tasks)
        if acceptance_current:
            status = "completed"
        elif related_rework or prior_reopened:
            status = "rework"
        elif ready_tasks or any(not any(r.get("gate_id", r.get("subject_id")) == gid for r in related_requests) for gid in ready_gates):
            status = "current"
        elif completed_ids or entry_available or related_alerts or related_requests:
            status = "waiting"
        else:
            status = "upcoming"
        reasons = {"completed": "Required work and current acceptance are evidenced.", "current": "At least one task or acceptance request can advance under the recorded prerequisites.",
                   "waiting": "This phase is awaiting required work, evidence or an external response.", "upcoming": "Its entry prerequisites are not yet evidenced.",
                   "rework": "An observed rejection, changed acceptance or unresolved correction requires another review cycle."}
        owners = list(dict.fromkeys([tasks[tid].get("owner_id") for tid in task_ids] + [gates[gid].get("resolver_id") for gid in own_gate_ids]))
        records = [task_records[tid] for tid in task_ids]
        row.update(status=status, status_reason=reasons[status], acceptance_current=acceptance_current, historical_work_complete=bool(task_ids) and not incomplete,
                   completed_task_count=len(completed_ids), task_count=len(task_ids), owners=[_person(people, p) for p in owners if p],
                   ready_task_ids=ready_tasks, actionable_gate_ids=ready_gates, blockers=blockers, open_request_ids=[r["id"] for r in related_requests],
                   rework_ids=[r["id"] for r in related_rework], required_gate_ids=sorted(relevant_gates),
                   gates=[dict(deepcopy(gates[gid]), acceptance_current=gate_checks[gid][0], acceptance_reason=gate_checks[gid][1]) for gid in own_gate_ids],
                   milestones={"planned_start": _earliest([tasks[tid].get("planned_start") for tid in task_ids]),
                               "planned_finish": _latest([_finish(tasks[tid]) for tid in task_ids]), "recorded_completions": records,
                               "actual_finish": _latest([r["actual_finish"] for r in records]) if records and all(r["evidenced"] and r["actual_finish"] for r in records) else None},
                   timing_note="Planned dates are synthetic task windows, not phase lead-time estimates. Actual dates require recorded completion evidence. Parallel phase spans must not be added together.")
        row["source_ids"] = list(dict.fromkeys(row["source_ids"] + [sid for gid in own_gate_ids for sid in gates[gid].get("source_ids", [])]))
        rows.append(row)

    # Display explicit correction cycles first; legacy blocked gates get only a
    # scoped return to their responsible acceptance phase, never invented redesign.
    routes = []
    for record in rework:
        trigger = next((event for event in state.get("events", []) if event.get("id") == record.get("trigger_event_id")), {})
        trigger_gate = trigger.get("gate_id")
        phase_id = record.get("return_phase") or phase_of.get(record.get("return_task_id")) or _GATE_PHASE.get(trigger_gate)
        owner = record.get("correction_owner_id") or trigger.get("resolver_id") or gates.get(trigger_gate, {}).get("resolver_id")
        routes.append(dict(record, return_phase=phase_id, correction_owner_id=owner,
                           return_phase_basis="Recorded return phase" if record.get("return_phase") else "Phase owning the observed trigger gate",
                           source="recorded_rework", history_preserved=True))
    covered = {gid for record in open_rework for gid in record.get("gate_ids", [])}
    for row in rows:
        for gid in row["gate_ids"]:
            gate = gates[gid]
            if gid in covered or gate_checks[gid][0]:
                continue
            affected_done = [tid for tid in tasks if task_records[tid]["completed"] and gid in tasks[tid].get("required_gates", [])]
            if gate.get("status") != "blocked" and not (gate.get("evidence_ids") or affected_done):
                continue
            routes.append({"id": "acceptance-" + gid, "status": "awaiting_reapproval", "gate_ids": [gid],
                           "return_phase": row["id"], "correction_owner_id": gate.get("resolver_id"), "reason": gate_checks[gid][1],
                           "required_artifact": gate.get("required_artifact", gate.get("label", gid)), "evidence_ids": deepcopy(gate.get("evidence_ids", [])),
                           "task_ids": affected_done, "source": "observed_gate_state", "history_preserved": True,
                           "note": "Reassess the affected acceptance. A pending gate alone does not prove that design or physical work must be repeated."})
    unmapped = [tid for tid, phase in phase_of.items() if not phase]
    if unmapped:
        warnings.append("Tasks need a phase assignment: " + ", ".join(unmapped))
    active = [r for r in rows if r["status"] in ("current", "waiting", "rework")]
    all_accepted = bool(tasks) and bool(rows) and not unmapped and not open_rework and not alerts and all(r["acceptance_current"] for r in rows) and all(check[0] for check in gate_checks.values())
    if project.get("status") == "completed" and not all_accepted:
        warnings.append("The project retains a completed label, but current phase acceptance is not complete.")
    return {"version": VERSION, "scope": "Post-signing project management; signed scope is the entry record. Sales and pre-signing work are excluded.",
            "phases": rows, "active_phase_ids": [r["id"] for r in active], "active_phase_titles": [r["title"] for r in active],
            "rework_routes": routes, "open_rework_count": sum(r.get("status") not in ("resolved", "superseded") for r in routes),
            "resolved_rework_count": sum(r.get("status") == "resolved" for r in routes), "all_accepted": all_accepted,
            "superseded_rework_count": sum(r.get("status") == "superseded" for r in routes),
            "signed_at": project.get("signed_at"), "target_handoff": project.get("target_handoff", project.get("target_date")),
            "unmapped_task_ids": unmapped, "warnings": warnings,
            "edges": [{"from": before, "to": after, "kind": kind} for before, after, kind in sorted(edges)],
            "timing_note": "Phases can overlap. Dates come from this synthetic project plan and recorded completions; no critical path, forecast or sum of phase durations is implied.",
            "status_note": "Current means ready to advance, not that field work has started. Completed task history is retained when current acceptance is reopened."}
