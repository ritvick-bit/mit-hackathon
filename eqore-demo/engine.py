"""Deterministic, auditable project tools. No network or model calls live here.

Actor events enter through a trusted simulator path; model output may only invoke
apply_action. All public operations copy their input so failed changes are atomic.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from reasoning import build_reasoning, design_acceptance_recorded


class DomainError(Exception):
    pass


ARRAYS = ("tasks", "stakeholders", "evidence", "events", "proposals", "decisions", "requests", "bookings", "alerts", "audit", "rework")
OPEN_REQUEST_STATUSES = ("pending", "sent", "acknowledged")
ACCEPTANCE_TASKS = {"t_design", "t_permit", "t_utility", "t_verify", "t_commission", "t_closeout_documents", "t_customer_training", "t_handoff"}


def project_complete(state):
    """Current acceptance, not historical task completion alone, closes a project."""
    return bool(state.get("tasks")) and all(t.get("status") == "completed" for t in state["tasks"]) and all(
        _gate_ready(state, gid) for gid in state.get("gates", {})) and not any(
        r.get("status") not in ("resolved", "superseded") for r in state.get("rework", [])) and not any(
        not a.get("resolved") for a in state.get("alerts", []))


def _fresh_for(record, item):
    if not item or item.get("id") in record.get("invalidated_evidence_ids", []):
        return False
    cutoff = _dt(record.get("invalidated_at"))
    effective = _dt(item.get("effective_at") or item.get("received_at"))
    return not cutoff or bool(effective and effective >= cutoff)


def _correction_pending(state, gate_id):
    return any(r.get("status") == "correction_required" and gate_id in r.get("gate_ids", []) for r in state.get("rework", []))


def _refresh_rework(state):
    tasks = {t["id"]: t for t in state["tasks"]}
    for record in state.get("rework", []):
        if record.get("status") != "awaiting_reapproval":
            continue
        if all(_gate_ready(state, g) for g in record["gate_ids"]) and all(tasks[t].get("status") == "completed" for t in record["task_ids"]):
            record.update(status="resolved", resolved_at=state["project"].get("now"))
            record["resolution_evidence_ids"] = list(dict.fromkeys(
                [e for g in record["gate_ids"] for e in state["gates"][g].get("evidence_ids", []) if e not in record["invalidated_evidence_ids"]] +
                [e for t in record["task_ids"] for e in tasks[t].get("evidence_ids", []) if e not in record["invalidated_evidence_ids"]]))
    state["project"]["status"] = "completed" if project_complete(state) else "active"


def _open_rework(state, event, gate_ids, evidence_ids, correction_owner=None):
    """Invalidate scoped acceptance; physical installation and its history remain intact."""
    tasks = {t["id"]: t for t in state["tasks"]}
    gates = set(gate_ids)
    affected = set(event.get("affected_task_ids", []))
    for gid in gates:
        if gid not in state["gates"]:
            raise DomainError("Unknown rework gate: %s" % gid)
    if not affected.issubset(tasks):
        raise DomainError("Unknown rework task.")
    changed = True
    while changed:
        previous = (set(gates), set(affected))
        affected.update(tid for tid, task in tasks.items() if gates.intersection(_task_gates(task)) or affected.intersection(task.get("predecessors", [])))
        # A renewed acceptance requires dependent acceptance to be re-evidenced.
        reopened = {tid for tid in affected if tid in ACCEPTANCE_TASKS or tasks[tid].get("acceptance_task")}
        gates.update(gid for gid, gate in state["gates"].items() if gates.intersection(gate.get("required_gates", [])) or reopened.intersection(gate.get("required_tasks", [])))
        changed = previous != (gates, affected)
    task_ids = [tid for tid in tasks if tid in affected and (tid in ACCEPTANCE_TASKS or tasks[tid].get("acceptance_task"))]
    identity = _id(state, "rework")
    now = state["project"].get("now")
    old_evidence = [e["id"] for e in state["evidence"]]
    record = {"id": identity, "status": "correction_required" if correction_owner else "awaiting_reapproval",
              "trigger_event_id": event["id"], "reason": event.get("reason") or event.get("summary", "Scoped acceptance requires review"),
              "return_phase": event.get("return_phase"), "return_task_id": event.get("return_task_id"),
              "correction_owner_id": correction_owner, "gate_ids": [g for g in state["gates"] if g in gates],
              "task_ids": task_ids, "required_artifact": event.get("required_artifact", "Current scoped correction and renewed acceptance records"),
              "required_actions": ["Obtain correction evidence from the named owner", "Resubmit to the original authorized reviewer", "Re-evidence affected acceptance tasks"] if correction_owner else ["Resolve the recorded discrepancy", "Re-evidence affected acceptance and handoff"],
              "evidence_ids": evidence_ids, "correction_evidence_ids": [], "resolution_evidence_ids": [],
              "created_at": now, "generation": 1, "invalidated_at": now, "invalidated_evidence_ids": old_evidence}
    for older in state["rework"]:
        if older.get("status") not in ("resolved", "superseded") and set(older.get("gate_ids", [])).issubset(gates):
            older.update(status="superseded", superseded_by=identity)
    state["rework"].append(record)
    for gid in gates:
        gate = state["gates"][gid]
        gate.setdefault("acceptance_history", []).append({"status": gate.get("status"), "evidence_ids": list(gate.get("evidence_ids", [])), "design_revision": gate.get("design_revision"), "invalidated_at": now, "rework_id": identity})
        gate.update(status="blocked" if gid in gate_ids else "pending", invalidated_at=now, invalidated_evidence_ids=old_evidence,
                    rework_generation=gate.get("rework_generation", 0) + 1, rework_id=identity)
    for tid in task_ids:
        task = tasks[tid]
        if task.get("status") == "completed":
            previous_revision = task.get("completed_design_revision") or next((e.get("design_revision") for eid in reversed(task.get("evidence_ids", [])) for e in state["evidence"] if e["id"] == eid and e.get("kind") in ("task_completion", "completion")), state["project"].get("design_revision"))
            task.setdefault("completion_history", []).append({"completed_at": task.get("completed_at"), "evidence_ids": list(task.get("evidence_ids", [])), "design_revision": previous_revision, "invalidated_at": now, "rework_id": identity})
            task["status"] = "planned"
            task.pop("completed_at", None)
            task.pop("completed_design_revision", None)
        task.update(invalidated_at=now, invalidated_evidence_ids=old_evidence, rework_generation=task.get("rework_generation", 0) + 1, rework_id=identity)
    for request in state["requests"]:
        if request.get("status") in OPEN_REQUEST_STATUSES and (request.get("gate_id") in gates or request.get("task_id") in task_ids or request.get("subject_id") in gates.union(task_ids)):
            request.update(status="superseded", superseded_by=identity)
    state["project"]["status"] = "active"
    return record


def _dt(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError) as error:
        raise DomainError("Invalid timestamp: %s" % value) from error


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _copy(state):
    result = deepcopy(state)
    for key in ARRAYS:
        result.setdefault(key, [])
    result.setdefault("gates", {})
    result.setdefault("calendars", {})
    result.setdefault("project", {}).setdefault("revision", 1)
    result["project"].setdefault("budget", {"baseline": 0, "committed": 0, "proposed": 0})
    return result


def _find(items, identity, kind="record"):
    for item in items:
        if item.get("id") == identity:
            return item
    raise DomainError("Unknown %s: %s" % (kind, identity))


def _id(state, kind):
    return "%s-%04d" % (kind.rstrip("s"), len(state[kind]) + 1)


def _audit(state, action, detail, actor="coordinator"):
    state["audit"].append({"id": _id(state, "audit"), "at": state["project"].get("now"),
                           "action": action, "actor_id": actor, "detail": detail,
                           "revision": state["project"]["revision"], "simulated": True})


def _material(state):
    state["project"]["revision"] += 1
    for proposal in state["proposals"]:
        if proposal.get("status") in ("proposed", "pending", "approved"):
            proposal["status"] = "stale"


def _authorized(state, actor, scope):
    person = next((p for p in state["stakeholders"] if p.get("id") == actor), {})
    permissions = person.get("can_approve", [])
    return scope in permissions or "*" in permissions


def _gate_authorized(state, gate, actor):
    scope = gate.get("required_authority", gate.get("id"))
    return bool(scope and _authorized(state, actor, scope))


def _evidence(state, raw, issuer=None):
    if not raw:
        return None
    if isinstance(raw, str):
        return _find(state["evidence"], raw, "evidence")
    record = deepcopy(raw)
    record.setdefault("id", _id(state, "evidence"))
    previous = next((e for e in state["evidence"] if e["id"] == record["id"]), None)
    if previous:
        if any(previous.get(key) != value for key, value in record.items()):
            raise DomainError("Evidence identity is immutable; use a new record for changed content.")
        return previous
    record.setdefault("issuer_id", issuer)
    record.setdefault("project_id", state["project"]["id"])
    record.setdefault("design_revision", state["project"].get("design_revision"))
    record.setdefault("received_at", state["project"].get("now"))
    record.setdefault("effective_at", record["received_at"])
    record.setdefault("verified", False)
    state["evidence"].append(record)
    return record


def _valid_evidence(state, item, design_sensitive=True):
    if not item or not item.get("verified") or item.get("project_id") != state["project"].get("id"):
        return False
    if design_sensitive and item.get("design_revision") != state["project"].get("design_revision"):
        return False
    if item.get("status") in ("draft", "superseded", "rejected"):
        return False
    return True


def _gate_ready(state, gate_id, seen=()):
    gate = state["gates"].get(gate_id, {})
    if gate_id in seen or gate.get("status") != "approved" or _correction_pending(state, gate_id):
        return False
    if gate.get("design_revision") and gate["design_revision"] != state["project"].get("design_revision"):
        return False
    issuer = next((p for p in state.get("stakeholders", []) if p.get("id") == gate.get("issuer_id")), {})
    if not _gate_authorized(state, gate, issuer.get("id")) or (issuer.get("project_ids") is not None and state["project"]["id"] not in issuer["project_ids"]):
        return False
    carry = gate.get("carry_forward", {})
    impact = next((e for e in state.get("evidence", []) if e["id"] == carry.get("evidence_id")), None)
    carry_valid = (carry.get("to_revision") == state["project"].get("design_revision") and _valid_evidence(state, impact) and
                   impact.get("issuer_id") == carry.get("issuer_id") and (_authorized(state, carry.get("issuer_id"), "design_revision") or _authorized(state, carry.get("issuer_id"), "design")))
    valid = False
    for item in state.get("evidence", []):
        if item["id"] not in gate.get("evidence_ids", []) or item.get("issuer_id") != issuer.get("id") or item.get("kind") in ("receipt", "acknowledgement", "acknowledged", "draft", "request", "correction_record"):
            continue
        carried = bool(carry_valid and item["id"] in carry.get("accepted_evidence_ids", []))
        if not _valid_evidence(state, item, gate.get("design_sensitive", True) and not carried) or not _fresh_for(gate, item):
            continue
        now, effective = _dt(state["project"].get("now")), _dt(item.get("effective_at") or item.get("received_at"))
        if now and effective and effective > now:
            continue
        valid = True
        break
    return valid and all(_gate_ready(state, other, seen + (gate_id,)) for other in gate.get("required_gates", []))


def _task_gates(task):
    return task.get("required_gates", [])


def _resources(task):
    value = task.get("resources", task.get("resource"))
    result = [value] if isinstance(value, str) else list(value or [])
    for extra in task.get("required_resources", []):
        if extra not in result:
            result.append(extra)
    return result


def _duration(task):
    return timedelta(hours=float(task.get("duration_hours", 0)))


def _delivery_task(task):
    return task.get("delivery_dependent") or task.get("id") in ("t_unload", "unload", "unloading")


def _schedule_errors(state, overrides=None, check_gates=False):
    starts = {t["id"]: _dt((overrides or {}).get(t["id"], t.get("planned_start"))) for t in state["tasks"]}
    tasks = {t["id"]: t for t in state["tasks"]}
    errors = []
    eta = _dt(state["project"].get("delivery_eta"))
    for task in state["tasks"]:
        if task.get("status") == "completed":
            continue
        start = starts[task["id"]]
        if start is None:
            continue
        end = start + _duration(task)
        if _delivery_task(task) and eta and start < eta:
            errors.append({"task_id": task["id"], "kind": "delivery", "message": "Equipment ETA is after the planned unloading start."})
        for dependency in task.get("predecessors", []):
            parent = tasks.get(dependency)
            if not parent:
                errors.append({"task_id": task["id"], "kind": "missing_dependency", "message": "Missing prerequisite %s" % dependency})
            elif starts.get(dependency) and starts[dependency] + _duration(parent) > start:
                errors.append({"task_id": task["id"], "kind": "dependency", "message": "Starts before prerequisite %s finishes." % dependency})
        for resource in _resources(task):
            if resource not in state["calendars"]:
                errors.append({"task_id": task["id"], "kind": "resource_unknown", "message": "Availability is unknown for %s." % resource})
                continue
            if not any(_dt(w["start"]) <= start and end <= _dt(w["end"]) for w in state["calendars"][resource]):
                errors.append({"task_id": task["id"], "kind": "resource", "message": "%s is unavailable for the full task window." % resource})
        if check_gates and task["id"] in (overrides or {}):
            for gate in _task_gates(task):
                # Receipt can only be evidenced at physical arrival. It blocks
                # execution, while a future plan may be committed against ETA.
                if state["gates"].get(gate, {}).get("execution_only"):
                    continue
                if not _gate_ready(state, gate):
                    errors.append({"task_id": task["id"], "kind": "gate", "message": "Required approval or readiness gate is unresolved: %s." % gate})
    # Same-project resource contention is checked in addition to external calendars.
    remaining = [t for t in state["tasks"] if t.get("status") != "completed" and starts[t["id"]]]
    for index, left in enumerate(remaining):
        for right in remaining[index + 1:]:
            if set(_resources(left)) & set(_resources(right)):
                a, b = starts[left["id"]], starts[right["id"]]
                if a < b + _duration(right) and b < a + _duration(left):
                    errors.append({"task_id": right["id"], "kind": "resource_conflict", "message": "Resource overlaps task %s." % left["id"]})
    return errors


def _schedule_options(state, errors):
    if not errors:
        return []
    tasks = {t["id"]: t for t in state["tasks"]}
    starts = {key: _dt(task.get("planned_start")) for key, task in tasks.items()}
    pending = list(tasks)
    ordered = []
    while pending:
        eligible = [key for key in pending if all(p in ordered or p not in tasks for p in tasks[key].get("predecessors", []))]
        if not eligible:
            return []
        ordered.extend(eligible)
        pending = [key for key in pending if key not in eligible]
    affected = {e["task_id"] for e in errors}
    eta = _dt(state["project"].get("delivery_eta"))
    for key in ordered:
        task = tasks[key]
        if task.get("status") == "completed":
            continue
        parents = task.get("predecessors", [])
        if any(p in affected for p in parents):
            affected.add(key)
        if key not in affected:
            continue
        earliest = starts[key] or _dt(state["project"].get("now"))
        if earliest is None:
            return []
        for parent in parents:
            if starts.get(parent):
                earliest = max(earliest, starts[parent] + _duration(tasks[parent]))
        if _delivery_task(task) and eta:
            earliest = max(earliest, eta)
        resources = _resources(task)
        choices = {earliest}
        for resource in resources:
            for window in state["calendars"].get(resource, []):
                choices.add(max(earliest, _dt(window["start"])))
        # Resource release times can be feasible candidates inside broad windows.
        for other in ordered:
            if other == key or not starts.get(other):
                continue
            if set(resources) & set(_resources(tasks[other])):
                choices.add(max(earliest, starts[other] + _duration(tasks[other])))
        selected = None
        for candidate in sorted(choices):
            end = candidate + _duration(task)
            if not all(any(_dt(w["start"]) <= candidate and end <= _dt(w["end"]) for w in state["calendars"].get(resource, [])) for resource in resources):
                continue
            conflict = False
            for other in ordered:
                if other == key or tasks[other].get("status") == "completed" or not starts.get(other):
                    continue
                if other in affected and ordered.index(other) > ordered.index(key):
                    continue
                if set(resources) & set(_resources(tasks[other])):
                    a = starts[other]
                    if candidate < a + _duration(tasks[other]) and a < end:
                        conflict = True
            if not conflict:
                selected = candidate
                break
        if selected is None:
            return []
        starts[key] = selected
    changes = [{"task_id": key, "planned_start": _iso(starts[key])} for key in ordered
               if starts[key] and starts[key] != _dt(tasks[key].get("planned_start"))]
    if not changes or _schedule_errors(state, {c["task_id"]: c["planned_start"] for c in changes}):
        return []
    cost = float(state["project"].get("recovery_cost_delta", state["project"].get("recovery_cost", sum(float(tasks[c["task_id"]].get("reschedule_cost", 0)) for c in changes))))
    return [{"id": "earliest-feasible", "label": "Earliest feasible option within recorded resource windows", "changes": changes,
             "cost_delta": cost, "assumptions": ["External reservations require separate confirmation."]}]


def _unresolved_request(state, subject, purpose=None):
    return next((r for r in state["requests"] if r.get("subject_id") == subject and r.get("status") in OPEN_REQUEST_STATUSES and (not purpose or r.get("purpose") == purpose)), None)


def _response_times(state, request):
    policy = state["project"].get("response_policy", {})
    created = _dt(request.get("created_at"))
    if not created:
        return None, None
    return (created + timedelta(hours=float(policy.get("follow_up_after_hours", 24))),
            created + timedelta(hours=float(policy.get("escalate_after_hours", 48))))


def _approval_current(state, proposal):
    """An historical approval never inherits a new person's delegation."""
    actor = proposal.get("required_approver_id")
    if not _authorized(state, actor, proposal.get("required_authority")):
        return False
    current_actor, current_scope = _approver(state, proposal.get("cost_delta", 0))
    return actor == current_actor and proposal.get("required_authority") == current_scope


def _decision(state, action, title, blocker, why, unlocks=None, evidence_ids=None, recipient=None, priority=50):
    person = next((p for p in state["stakeholders"] if p["id"] == (recipient or action.get("recipient_id"))), {})
    return {"action_type": action["type"], "title": title, "recipient_id": recipient or action.get("recipient_id"),
            "request": action.get("request", title), "why_now": why, "blocker": blocker,
            "unlocks": unlocks or [], "evidence_ids": evidence_ids or [],
            "authority": person.get("authority_source", "Recorded project policy; external approvals remain separate."),
            "alternatives": [], "while_waiting": [], "action": action, "confidence": "supported by current project records",
            "priority": priority}


def _approver(state, cost):
    policy = state["project"].get("policy", {})
    limit = float(policy.get("pm_cost_limit", state["project"].get("pm_approval_limit", state["project"].get("pm_cost_limit", 5000))))
    if cost > limit:
        scope = "commercial_change"
    else:
        scope = "schedule_change"
    approver = next((p["id"] for p in state["stakeholders"] if scope in p.get("can_approve", [])), None)
    if not approver and scope == "schedule_change":
        approver = next((p["id"] for p in state["stakeholders"] if "plan" in p.get("can_approve", [])), None)
    if not approver:
        eligible = [p for p in state["stakeholders"] if "plan_change" in p.get("can_approve", []) and float(p.get("approval_limit", 0)) >= cost]
        eligible.sort(key=lambda p: float(p.get("approval_limit", 0)))
        if eligible:
            return eligible[0]["id"], "plan_change"
    return approver, scope


def analyze(state):
    state = _copy(state)
    tasks = {t["id"]: t for t in state["tasks"]}
    impacts = _schedule_errors(state)
    options = _schedule_options(state, impacts)
    ready, blocked, constraints, candidates = [], [], [], []
    for task in state["tasks"]:
        if task.get("status") == "completed":
            continue
        reasons = ["Prerequisite %s is incomplete" % p for p in task.get("predecessors", []) if tasks.get(p, {}).get("status") != "completed"]
        reasons += ["Gate %s is unresolved" % g for g in _task_gates(task) if not _gate_ready(state, g)]
        reasons += [e["message"] for e in impacts if e["task_id"] == task["id"]]
        if reasons:
            blocked.append({"task_id": task["id"], "title": task["title"], "reasons": reasons})
        else:
            ready.append(task["id"])
    for record in state["rework"]:
        if record.get("status") == "correction_required" and not _unresolved_request(state, record["id"]):
            action = {"type": "request_review", "purpose": "rework_correction", "subject_id": record["id"], "rework_id": record["id"],
                      "recipient_id": record["correction_owner_id"], "request": record["required_artifact"]}
            candidates.append(_decision(state, action, "Correct the returned review package", record["reason"],
                                        "A scoped correction must precede renewed reviewer acceptance.", record["task_ids"], record["evidence_ids"], priority=102))
    for alert in state["alerts"]:
        if alert.get("resolved"):
            continue
        # An alert can describe a future prerequisite. Its resolution still
        # requires the same work and gate prerequisites as the ordinary path.
        alert_gate = state["gates"].get(alert.get("gate_id"), {})
        if _correction_pending(state, alert.get("gate_id")):
            continue
        if any(tasks.get(key, {}).get("status") != "completed" for key in alert_gate.get("required_tasks", [])):
            continue
        if any(not _gate_ready(state, key) for key in alert_gate.get("required_gates", [])):
            continue
        subject = alert.get("gate_id", alert["id"])
        if _unresolved_request(state, subject):
            continue
        resolver = alert.get("resolver_id")
        if resolver:
            action = {"type": "request_review", "recipient_id": resolver, "subject_id": subject,
                      "purpose": "gate_resolution" if alert.get("gate_id") else "issue_resolution", "request": alert["title"]}
            if alert.get("gate_id"):
                action["gate_id"] = alert["gate_id"]
            candidates.append(_decision(state, action, "Resolve: " + alert["title"], alert["title"],
                                        "An unresolved discrepancy blocks evidenced completion.", alert.get("task_ids", []), alert.get("evidence_ids", []), priority=100))
    for gate_id, gate in state["gates"].items():
        if _gate_ready(state, gate_id):
            continue
        constraints.append({"gate_id": gate_id, "status": gate.get("status"), "label": gate.get("label", gate_id), "resolver_id": gate.get("resolver_id")})
        if _correction_pending(state, gate_id):
            continue
        dependent = [t for t in state["tasks"] if t.get("status") != "completed" and gate_id in _task_gates(t)]
        immediately_needed = [t for t in dependent if all(tasks.get(p, {}).get("status") == "completed" for p in t.get("predecessors", []))]
        prerequisites_ready = all(tasks.get(key, {}).get("status") == "completed" for key in gate.get("required_tasks", []))
        prerequisites_ready = prerequisites_ready and all(_gate_ready(state, key) for key in gate.get("required_gates", []))
        if not immediately_needed or not gate.get("resolver_id") or not prerequisites_ready:
            continue
        request = _unresolved_request(state, gate_id)
        if request:
            # Follow-up and escalation are timed from the original request.
            # Acknowledgement never resets these clocks or authorizes work.
            request = next((r for r in state["requests"] if r.get("id") == request.get("parent_request_id")), request)
            follow_at, escalate_at = _response_times(state, request)
            now = _dt(state["project"].get("now"))
            recipient = next((p for p in state["stakeholders"] if p["id"] == request["recipient_id"]), {})
            escalation = gate.get("escalation_id") or recipient.get("escalation_id")
            responses = [r for r in state["requests"] if r.get("parent_request_id") == request["id"]]
            if escalate_at and now and now >= escalate_at and escalation and not any(r.get("purpose") == "escalation" for r in responses):
                action = {"type": "request_information", "purpose": "escalation", "subject_id": gate_id, "gate_id": gate_id,
                          "recipient_id": escalation, "request": "Escalate overdue request for " + gate.get("label", gate_id), "parent_request_id": request["id"]}
                candidates.append(_decision(state, action, action["request"], "Required response is overdue", "The recorded response deadline has passed.", [t["id"] for t in dependent], gate.get("evidence_ids", []), priority=96))
            elif follow_at and now and now >= follow_at and not any(r.get("purpose") == "follow_up" for r in responses) and int(state["project"].get("response_policy", {}).get("max_requests_per_subject", 2)) > 1:
                action = {"type": "request_information", "purpose": "follow_up", "subject_id": gate_id, "gate_id": gate_id,
                          "recipient_id": request["recipient_id"], "request": "Follow up for the scoped outcome of " + gate.get("label", gate_id), "parent_request_id": request["id"]}
                candidates.append(_decision(state, action, action["request"], "Required outcome remains unresolved", "The follow-up interval has elapsed without the required outcome.", [t["id"] for t in dependent], gate.get("evidence_ids", []), priority=96))
            continue
        action = {"type": "request_information", "purpose": "gate_resolution", "subject_id": gate_id, "gate_id": gate_id,
                  "recipient_id": gate["resolver_id"], "request": "Obtain %s with current-revision evidence and authorized confirmation." % gate.get("label", gate_id)}
        candidates.append(_decision(state, action, "Ask for " + gate.get("label", gate_id), gate.get("label", gate_id) + " remains unresolved",
                                    "This prerequisite must be evidenced before dependent work can proceed.", [t["id"] for t in dependent], gate.get("evidence_ids", []), priority=99))
    for proposal in state["proposals"]:
        if proposal.get("based_on_revision") != state["project"]["revision"] or proposal.get("status") not in ("proposed", "pending", "approved"):
            continue
        if proposal["status"] == "approved":
            if _approval_current(state, proposal):
                proposed_starts = {c["task_id"]: c["planned_start"] for c in proposal["changes"]}
                if not _schedule_errors(state, proposed_starts, check_gates=True):
                    action = {"type": "commit_plan", "proposal_id": proposal["id"]}
                    candidates.append(_decision(state, action, "Commit the authorized recovery plan", "Approved proposal has not been applied", "Approval is valid for the unchanged proposal; feasibility is rechecked atomically.", [c["task_id"] for c in proposal["changes"]], proposal.get("evidence_ids", []), priority=95))
            elif not _unresolved_request(state, "authority:" + proposal["id"]):
                reviewer, _ = _approver(state, proposal.get("cost_delta", 0))
                reviewer = reviewer or proposal["required_approver_id"]
                action = {"type": "request_review", "purpose": "authority_revalidation", "subject_id": "authority:" + proposal["id"],
                          "recipient_id": reviewer, "request": "Review changed delegation for " + proposal["id"] + "; obtain a new authorized decision before commitment. The previous approval cannot be transferred."}
                candidates.append(_decision(state, action, "Revalidate changed approval authority", "Recorded approval no longer satisfies current delegation", "The prior approval cannot authorize commitment under the current authority record.", [], proposal.get("evidence_ids", []), priority=98))
        elif not _unresolved_request(state, proposal["id"]):
            action = {"type": "request_approval", "proposal_id": proposal["id"], "recipient_id": proposal["required_approver_id"]}
            candidates.append(_decision(state, action, "Request authorization for the recovery plan", "Schedule or cost change needs an authorized decision", "A feasible proposal is ready for the designated decision-maker.", [c["task_id"] for c in proposal["changes"]], proposal.get("evidence_ids", []), priority=94))
    active = any(p.get("status") in ("proposed", "pending", "approved") and p.get("based_on_revision") == state["project"]["revision"] for p in state["proposals"])
    if impacts and not active:
        if options:
            option = options[0]
            approver, scope = _approver(state, option["cost_delta"])
            rejected = next((p for p in reversed(state["proposals"]) if p.get("status") == "rejected" and p.get("based_on_revision") == state["project"]["revision"] and p.get("changes") == option["changes"] and p.get("cost_delta") == option["cost_delta"]), None)
            if rejected:
                subject = "rejected_plan:" + rejected["id"]
                if not _unresolved_request(state, subject):
                    action = {"type": "request_review", "purpose": "rejected_plan", "subject_id": subject, "recipient_id": rejected["required_approver_id"],
                              "request": "Clarify the rejected recovery option and acceptable alternatives before proposing the same dates or cost again."}
                    candidates.append(_decision(state, action, "Clarify the rejected recovery option", "The feasible option was rejected by its authorized approver", "Repeating the same unchanged proposal cannot resolve the decision.", [], rejected.get("evidence_ids", []), priority=93))
            elif approver:
                action = {"type": "propose_plan", "changes": option["changes"], "cost_delta": option["cost_delta"], "required_approver_id": approver,
                          "evidence_ids": [e["id"] for e in state["evidence"] if _valid_evidence(state, e, False)][-8:]}
                candidates.append(_decision(state, action, "Prepare a feasible recovery schedule", impacts[0]["message"], "Recorded dates conflict with current delivery or resource constraints.", [c["task_id"] for c in option["changes"]], action["evidence_ids"], priority=93))
        else:
            pm = next((p["id"] for p in state["stakeholders"] if p["id"] == "pm"), state["stakeholders"][0]["id"] if state["stakeholders"] else None)
            if pm and not _unresolved_request(state, "schedule_recovery"):
                action = {"type": "request_review", "purpose": "schedule_recovery", "subject_id": "schedule_recovery", "recipient_id": pm,
                          "request": "No feasible recovery exists in the recorded resource windows. Obtain additional windows or authorize scope changes."}
                candidates.append(_decision(state, action, "Escalate unavailable recovery windows", "No feasible schedule within known constraints", "A commitment would violate resource or dependency constraints.", [], priority=92))
    for booking in state["bookings"]:
        if booking.get("status") == "required" and not _unresolved_request(state, booking["task_id"], "booking"):
            action = {"type": "confirm_booking", "task_id": booking["task_id"], "booking_id": booking["id"], "recipient_id": booking["recipient_id"]}
            candidates.append(_decision(state, action, "Confirm external resource booking", "The internal plan is committed; external booking remains unconfirmed", "Internal approval does not reserve a contractor or customer window.", [booking["task_id"]], priority=89))
    for task_id in ready:
        task = tasks[task_id]
        if any(b["task_id"] == task_id and b.get("status") not in ("confirmed", "superseded") for b in state["bookings"]):
            continue
        if _unresolved_request(state, task_id):
            continue
        digital = task.get("completion_mode") == "digital" or task.get("external") is False
        evidence = [e["id"] for e in state["evidence"] if _valid_evidence(state, e) and _fresh_for(task, e) and (e.get("task_id") == task_id) and e.get("kind") in (task.get("required_evidence_kind"), "completion", "task_completion")]
        if digital or evidence:
            action = {"type": "complete_task", "task_id": task_id, "evidence_ids": evidence}
            candidates.append(_decision(state, action, "Complete " + task["title"], "Ready work remains open", "Prerequisites are satisfied and required completion evidence is available.", [task_id], evidence, priority=45))
        elif task.get("owner_id"):
            revision = state["project"].get("design_revision", "unrecorded")
            accepted_design = design_acceptance_recorded(state)
            design_context = ("Design acceptance for this revision is recorded; other required approvals remain separate." if accepted_design else
                              "Design acceptance for this revision is not yet recorded; keep any acceptance decision separate from this task record.")
            action = {"type": "request_information", "purpose": "task_completion", "subject_id": task_id, "task_id": task_id,
                      "recipient_id": task["owner_id"], "request": "Provide verified completion evidence for %s scoped to recorded revision %s. %s" % (task["title"], revision, design_context)}
            candidates.append(_decision(state, action, "Coordinate " + task["title"], "External work or its completion evidence remains outstanding", "Recorded prerequisites are satisfied; the responsible actor can perform or evidence the next step.", [task_id], priority=40))
    if not candidates:
        pending = [r for r in state["requests"] if r.get("status") in OPEN_REQUEST_STATUSES]
        done = project_complete(state)
        title = "Deployment handoff is complete" if done else ("Await recorded counterpart responses" if pending else "Review unresolved project prerequisites")
        action = {"type": "wait", "reason": title}
        candidates.append(_decision(state, action, title, "No outstanding work" if done else "Required evidence or authorized response is unavailable",
                                    "Completion is evidenced." if done else "Waiting is intermediate; unresolved requests and gates remain visible.", priority=0))
    candidates.sort(key=lambda c: -c["priority"])
    independent = [tasks[key]["title"] for key in ready][:4]
    for decision in candidates:
        decision["while_waiting"] = independent
        decision["alternatives"] = [other["title"] for other in candidates if other is not decision][:3]
        decision["reasoning"] = build_reasoning(state, decision, impacts)
        decision["why_now"] = decision["reasoning"]["summary"]
        decision["unlocks"] = decision["reasoning"]["expected_unlocks"]
        decision["request"] = decision["reasoning"]["authorized_action"]["description"]
        if decision["action_type"] in ("request_information", "request_review", "request_approval"):
            decision["action"]["request"] = decision["request"]
    return {"schedule_options": options, "impacts": impacts, "constraints": constraints,
            "ready_tasks": ready, "blocked_tasks": blocked, "candidates": candidates}


def recommend(state):
    decision = deepcopy(analyze(state)["candidates"][0])
    decision["mode"] = "baseline"
    return decision


def _request(state, action, purpose=None, subject=None):
    recipient = action.get("recipient_id")
    _find(state["stakeholders"], recipient, "stakeholder")
    purpose = purpose or action.get("purpose", "information")
    subject = subject or action.get("subject_id") or action.get("gate_id") or action.get("task_id")
    if not subject:
        raise DomainError("Requests must identify their subject.")
    existing = next((r for r in state["requests"] if r.get("subject_id") == subject and r.get("purpose") == purpose and r.get("recipient_id") == recipient and r.get("status") in OPEN_REQUEST_STATUSES), None)
    if existing:
        return existing
    now = _dt(state["project"].get("now"))
    if purpose == "rework_correction":
        record = _find(state["rework"], action.get("rework_id") or subject, "rework")
        if record["status"] != "correction_required" or recipient != record["correction_owner_id"] or subject != record["id"]:
            raise DomainError("Correction must be requested from the current scoped rework owner.")
    if purpose in ("follow_up", "escalation"):
        parent = _find(state["requests"], action.get("parent_request_id"), "original request")
        if parent.get("parent_request_id") or parent.get("subject_id") != subject or parent.get("status") not in OPEN_REQUEST_STATUSES:
            raise DomainError("Follow-up requires the original unresolved request for this subject.")
        follow_at, escalate_at = _response_times(state, parent)
        threshold = follow_at if purpose == "follow_up" else escalate_at
        if not now or not threshold or now < threshold:
            raise DomainError("The recorded %s interval has not elapsed." % purpose)
        prior = [r for r in state["requests"] if r.get("parent_request_id") == parent["id"] and r.get("purpose") == purpose]
        if prior:
            return prior[0]
        original_actor = _find(state["stakeholders"], parent["recipient_id"], "stakeholder")
        gate = state["gates"].get(parent.get("gate_id") or subject, {})
        expected = parent["recipient_id"] if purpose == "follow_up" else gate.get("escalation_id") or original_actor.get("escalation_id")
        if recipient != expected:
            raise DomainError("Response follow-up must use the recorded responsible recipient.")
        if purpose == "follow_up" and int(state["project"].get("response_policy", {}).get("max_requests_per_subject", 2)) <= 1:
            raise DomainError("Direct request limit reached; await the escalation interval.")
    follow_hours = float(state["project"].get("response_policy", {}).get("follow_up_after_hours", 24))
    request = {"id": _id(state, "requests"), "purpose": purpose, "subject_id": subject, "recipient_id": recipient,
               "request": action.get("request", "Provide an authorized decision for " + str(subject)), "status": "pending",
               "created_at": state["project"].get("now"), "due_at": action.get("due_at") or (_iso(now + timedelta(hours=follow_hours)) if now else None),
               "based_on_revision": state["project"]["revision"], "simulated": True}
    for key in ("gate_id", "task_id", "proposal_id", "booking_id", "parent_request_id", "rework_id"):
        if action.get(key):
            request[key] = action[key]
    record = next((r for r in state["rework"] if r["id"] == request.get("rework_id")), None)
    target = record or state["gates"].get(request.get("gate_id")) or next((t for t in state["tasks"] if t["id"] == request.get("task_id")), {})
    request["rework_generation"] = target.get("generation", target.get("rework_generation", 0))
    state["requests"].append(request)
    return request


def _resolve(state, proposal_id, status, actor):
    proposal = _find(state["proposals"], proposal_id, "proposal")
    if status not in ("approved", "rejected"):
        raise DomainError("Decision must be approved or rejected.")
    if proposal.get("based_on_revision") != state["project"]["revision"] or proposal.get("status") == "stale":
        raise DomainError("Proposal is stale; replan against current evidence before deciding.")
    if actor != proposal["required_approver_id"] or not _authorized(state, actor, proposal["required_authority"]):
        raise DomainError("Actor lacks the recorded authority for this proposal.")
    if proposal["status"] in ("committed", "rejected"):
        raise DomainError("Proposal is already closed.")
    previous = next((d for d in state["decisions"] if d.get("proposal_id") == proposal_id and d.get("status") == status), None)
    if not previous:
        state["decisions"].append({"id": _id(state, "decisions"), "proposal_id": proposal_id, "actor_id": actor,
                                   "status": status, "at": state["project"].get("now"), "proposal_revision": proposal["based_on_revision"]})
    proposal["status"] = status
    for request in state["requests"]:
        if request.get("proposal_id") == proposal_id:
            request["status"] = status


def apply_action(state, action, actor_id="coordinator"):
    state = _copy(state)
    action = deepcopy(action)
    kind = action.get("type")
    if kind == "propose_plan":
        changes = action.get("changes", [])
        if not changes or len({c["task_id"] for c in changes}) != len(changes):
            raise DomainError("A proposal needs unique task changes.")
        for change in changes:
            task = _find(state["tasks"], change["task_id"], "task")
            if task.get("status") == "completed":
                raise DomainError("Completed work cannot be rescheduled.")
            if _dt(change.get("planned_start")) is None:
                raise DomainError("Each task change needs a planned start.")
        errors = _schedule_errors(state, {c["task_id"]: c["planned_start"] for c in changes})
        if errors:
            raise DomainError("Infeasible proposal: " + errors[0]["message"])
        cost = float(action.get("cost_delta", 0))
        if not math.isfinite(cost) or cost < 0:
            raise DomainError("Negative cost changes require an explicitly supported credit workflow.")
        minimum_cost = float(state["project"].get("recovery_cost_delta", state["project"].get("recovery_cost", 0)))
        if cost < minimum_cost:
            raise DomainError("Proposal understates the recorded recovery cost.")
        approver, scope = _approver(state, cost)
        if action.get("required_approver_id") and action["required_approver_id"] != approver:
            raise DomainError("Proposal approver must match recorded cost and schedule authority.")
        if not approver:
            raise DomainError("No authorized approver is configured for this change.")
        evidence_ids = action.get("evidence_ids", [])
        for identity in evidence_ids:
            if not _valid_evidence(state, _find(state["evidence"], identity, "evidence"), False):
                raise DomainError("Proposal references unverified or differently scoped evidence.")
        fingerprint = hashlib.sha256(json.dumps({"revision": state["project"]["revision"], "changes": changes, "cost": cost}, sort_keys=True).encode()).hexdigest()
        if any(p.get("fingerprint") == fingerprint and p.get("status") in ("proposed", "pending", "approved", "committed") for p in state["proposals"]):
            return state
        if any(p.get("fingerprint") == fingerprint and p.get("status") == "rejected" for p in state["proposals"]):
            raise DomainError("This unchanged proposal was rejected; obtain new information or propose a different option.")
        proposal = {"id": _id(state, "proposals"), "based_on_revision": state["project"]["revision"], "design_revision": state["project"].get("design_revision"),
                    "changes": changes, "cost_delta": cost, "required_approver_id": approver, "required_authority": scope, "evidence_ids": evidence_ids,
                    "status": "proposed", "fingerprint": fingerprint, "created_at": state["project"].get("now")}
        state["proposals"].append(proposal)
        state["project"]["budget"]["proposed"] = cost
    elif kind in ("request_information", "request_review"):
        _request(state, action)
    elif kind == "request_approval":
        proposal = _find(state["proposals"], action.get("proposal_id"), "proposal")
        if proposal["based_on_revision"] != state["project"]["revision"] or proposal["status"] not in ("proposed", "pending"):
            raise DomainError("Only a current, undecided proposal can request approval.")
        if action.get("recipient_id", proposal["required_approver_id"]) != proposal["required_approver_id"]:
            raise DomainError("Approval must be requested from the designated approver.")
        action["recipient_id"] = proposal["required_approver_id"]
        _request(state, action, "plan_approval", proposal["id"])
        proposal["status"] = "pending"
    elif kind == "resolve_decision":
        # The actor identity is provided by the trusted boundary, never action text.
        _resolve(state, action.get("proposal_id"), action.get("status"), actor_id)
    elif kind == "commit_plan":
        proposal = _find(state["proposals"], action.get("proposal_id"), "proposal")
        if proposal["status"] == "committed":
            return state
        if proposal["based_on_revision"] != state["project"]["revision"] or proposal["status"] != "approved":
            raise DomainError("Commit requires a current approved proposal.")
        if not _approval_current(state, proposal):
            raise DomainError("Commit requires current approval authority and delegation for this exact proposal; the historical approval cannot be rerouted.")
        if not any(d.get("proposal_id") == proposal["id"] and d.get("status") == "approved" and d.get("actor_id") == proposal["required_approver_id"] for d in state["decisions"]):
            raise DomainError("No recorded authorized approval exists.")
        errors = _schedule_errors(state, {c["task_id"]: c["planned_start"] for c in proposal["changes"]}, check_gates=True)
        if errors:
            raise DomainError("Commit revalidation failed: " + errors[0]["message"])
        for change in proposal["changes"]:
            task = _find(state["tasks"], change["task_id"], "task")
            task["planned_start"] = change["planned_start"]
            task["status"] = "planned"
            for booking in state["bookings"]:
                if booking["task_id"] == task["id"] and booking.get("status") != "superseded":
                    booking["status"] = "superseded"
            if _resources(task):
                state["bookings"].append({"id": _id(state, "bookings"), "task_id": task["id"], "recipient_id": task.get("owner_id"),
                                           "planned_start": task["planned_start"], "status": "required", "proposal_id": proposal["id"], "simulated": True})
        proposal["status"] = "committed"
        budget = state["project"]["budget"]
        budget["committed"] = float(budget.get("committed", 0)) + proposal["cost_delta"]
        budget["proposed"] = 0
        _material(state)
    elif kind == "confirm_booking":
        task = _find(state["tasks"], action.get("task_id"), "task")
        booking = next((b for b in reversed(state["bookings"]) if b["task_id"] == task["id"] and b.get("status") != "superseded"), None)
        if not booking:
            raise DomainError("No committed plan booking exists for this task.")
        if booking["status"] == "confirmed":
            return state
        if action.get("recipient_id", booking["recipient_id"]) != booking["recipient_id"]:
            raise DomainError("Booking must be confirmed by the responsible counterpart.")
        action.update({"recipient_id": booking["recipient_id"], "booking_id": booking["id"]})
        _request(state, action, "booking", task["id"])
        booking["status"] = "pending"
    elif kind == "complete_task":
        _complete(state, action.get("task_id"), action.get("evidence_ids", []), actor_id)
    elif kind == "wait":
        pass
    else:
        raise DomainError("Unsupported product action: %s" % kind)
    _audit(state, kind, action, actor_id)
    _refresh_rework(state)
    return state


def _complete(state, task_id, evidence_ids, actor):
    task = _find(state["tasks"], task_id, "task")
    if task.get("status") == "completed":
        return
    if any(_find(state["tasks"], p, "task").get("status") != "completed" for p in task.get("predecessors", [])):
        raise DomainError("Task prerequisites are incomplete.")
    if any(not _gate_ready(state, g) for g in _task_gates(task)):
        raise DomainError("Task readiness or approval gates are unresolved.")
    if any(b["task_id"] == task_id and b.get("status") not in ("confirmed", "superseded") for b in state["bookings"]):
        raise DomainError("External booking is not confirmed.")
    if any(e["task_id"] == task_id for e in _schedule_errors(state)):
        raise DomainError("Task schedule violates current constraints.")
    digital = task.get("completion_mode") == "digital" or task.get("external") is False
    if not digital:
        valid = []
        for identity in evidence_ids:
            item = _find(state["evidence"], identity, "evidence")
            if _valid_evidence(state, item) and _fresh_for(task, item) and item.get("task_id") == task_id and item.get("kind") in (task.get("required_evidence_kind"), "task_completion", "completion") and item.get("issuer_id") == task.get("owner_id"):
                valid.append(identity)
        if not valid:
            raise DomainError("External work requires fresh scoped verified completion evidence from its responsible actor.")
        planned = _dt(task.get("planned_start"))
        now = _dt(state["project"].get("now"))
        if planned and now and now < planned + _duration(task):
            raise DomainError("Physical work cannot be completed before its recorded work window finishes.")
    task["status"] = "completed"
    task["evidence_ids"] = list(dict.fromkeys(task.get("evidence_ids", []) + evidence_ids))
    task["completed_at"] = state["project"].get("now")
    task["completed_design_revision"] = state["project"].get("design_revision")
    _material(state)
    _refresh_rework(state)


def apply_event(state, event):
    state = _copy(state)
    event = deepcopy(event)
    if not event.get("id"):
        event["id"] = "event-" + hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()[:16]
    if any(e["id"] == event["id"] for e in state["events"]):
        return state
    if event.get("at"):
        old, new = _dt(state["project"].get("now")), _dt(event["at"])
        if not old or new > old:
            state["project"]["now"] = event["at"]
    kind = event.get("type")
    issuer = event.get("issuer_id") or (event.get("evidence") or {}).get("issuer_id") if isinstance(event.get("evidence", {}), dict) else event.get("issuer_id")
    item = _evidence(state, event.get("evidence"), issuer)
    evidence_ids = [item["id"]] if item else event.get("evidence_ids", [])
    if kind in ("delivery_update", "delivery_eta"):
        if not _valid_evidence(state, item, False):
            raise DomainError("Delivery updates require verified project evidence.")
        eta = event.get("eta", event.get("delivery_eta"))
        _dt(eta)
        effective = _dt(item.get("effective_at"))
        previous_effective = _dt(state["project"].get("delivery_effective_at"))
        if previous_effective and effective and effective < previous_effective:
            _audit(state, "older_evidence_retained", "Historical shipping estimate retained without replacing the current ETA.", issuer)
        elif eta != state["project"].get("delivery_eta"):
            state["project"]["delivery_eta"] = eta
            state["project"]["delivery_effective_at"] = item.get("effective_at")
            _material(state)
    elif kind in ("gate_update", "gate_approval"):
        _update_gate(state, event.get("gate_id"), event.get("status", "approved"), issuer, item)
        if event.get("status", "approved") != "approved":
            _open_rework(state, event, [event["gate_id"]], evidence_ids)
    elif kind == "review_returned":
        _return_review(state, event, issuer, item)
    elif kind == "design_revision":
        revision = event.get("design_revision", event.get("revision"))
        if not item or not item.get("verified") or item.get("project_id") != state["project"].get("id"):
            raise DomainError("Design revision requires verified scoped evidence.")
        if item.get("status") == "draft" or event.get("status") == "draft":
            _audit(state, "draft_design_received", "Draft retained; recorded design revision remains unchanged.", issuer)
        else:
            if not _authorized(state, issuer, "design_revision") and not _authorized(state, issuer, "design"):
                raise DomainError("Design issuer lacks recorded design authority.")
            prior_ready = {gid: _gate_ready(state, gid) for gid in state["gates"]}
            old_revision = state["project"].get("design_revision")
            state["project"]["design_revision"] = revision
            affected = event.get("affected_gates")
            for gate_id, gate in state["gates"].items():
                if affected is not None and not (gate.get("design_sensitive", True) and gate_id in affected):
                    # Explicit engineering impact scope carries unaffected permissions forward.
                    gate["design_revision"] = revision
                    if prior_ready[gate_id]:
                        gate["carry_forward"] = {"from_revision": old_revision, "to_revision": revision, "evidence_id": item["id"], "issuer_id": issuer,
                                                 "accepted_evidence_ids": list(gate.get("evidence_ids", []))}
            invalidated = [gid for gid, gate in state["gates"].items() if gate.get("design_sensitive", True) and (affected is None or gid in affected)]
            if invalidated:
                _open_rework(state, event, invalidated, evidence_ids)
                for gid in invalidated:
                    state["gates"][gid]["status"] = "pending"
            _material(state)
    elif kind in ("resource_update", "resource_conflict"):
        state["calendars"][event["resource"]] = deepcopy(event.get("windows", []))
        _material(state)
    elif kind in ("field_defect", "commissioning_fault"):
        gate_id = event.get("gate_id", "field_verified" if kind == "field_defect" else "network")
        gate = state["gates"].get(gate_id)
        if not _valid_evidence(state, item) or item.get("issuer_id") != issuer or not any(p["id"] == issuer for p in state["stakeholders"]):
            raise DomainError("A discrepancy requires verified current project evidence from a recorded actor.")
        if gate:
            _open_rework(state, event, [gate_id], evidence_ids)
            gate["evidence_ids"] = list(dict.fromkeys(gate.get("evidence_ids", []) + evidence_ids))
        state["alerts"].append({"id": _id(state, "alerts"), "kind": kind, "severity": "high", "title": event.get("summary", kind.replace("_", " ")),
                               "task_ids": event.get("task_ids", [event.get("task_id")] if event.get("task_id") else []), "gate_id": gate_id,
                               "resolver_id": event.get("resolver_id") or (gate or {}).get("resolver_id"), "evidence_ids": evidence_ids, "resolved": False})
        _material(state)
    elif kind == "request_response":
        request = _find(state["requests"], event.get("request_id"), "request")
        _current_request(state, request)
        if issuer != request["recipient_id"]:
            raise DomainError("Response actor does not match the recorded recipient.")
        status = event.get("status", "answered")
        proposal_id = event.get("proposal_id") or request.get("proposal_id")
        gate_id = event.get("gate_id") or request.get("gate_id")
        if request.get("purpose") == "rework_correction" and status == "corrected":
            record = _find(state["rework"], request.get("rework_id"), "rework")
            if record["status"] != "correction_required" or issuer != record["correction_owner_id"]:
                raise DomainError("Correction actor or current rework scope does not match.")
            if not _valid_evidence(state, item) or not _fresh_for(record, item) or item.get("issuer_id") != issuer or item.get("kind") != "correction_record" or item.get("rework_id") != record["id"]:
                raise DomainError("Correction requires fresh scoped correction evidence from its recorded owner.")
            record.update(status="awaiting_reapproval", correction_evidence_ids=evidence_ids, corrected_at=state["project"].get("now"))
            for gid in record["gate_ids"]:
                state["gates"][gid]["status"] = "pending"
            _material(state)
        elif proposal_id and status in ("approved", "rejected"):
            _resolve(state, proposal_id, status, issuer)
        elif gate_id and status in ("rejected", "returned"):
            review = dict(event, gate_id=gate_id)
            _return_review(state, review, issuer, item)
        elif gate_id and status == "approved":
            _update_gate(state, gate_id, "approved", issuer, item)
        elif request.get("purpose") == "booking" and status in ("confirmed", "approved"):
            booking = _find(state["bookings"], event.get("booking_id") or request.get("booking_id"), "booking")
            if booking["status"] == "superseded" or booking["planned_start"] != _find(state["tasks"], booking["task_id"], "task")["planned_start"]:
                raise DomainError("Booking response refers to a superseded window.")
            if not _valid_evidence(state, item, False):
                raise DomainError("Booking confirmation requires verified project evidence.")
            booking["status"] = "confirmed"
            booking["evidence_ids"] = evidence_ids
        acknowledgement = status in ("acknowledged", "acknowledgement", "received") or (
            status == "answered" and item and item.get("kind") in ("receipt", "acknowledgement"))
        request["status"] = "acknowledged" if acknowledgement else status
        request["response_status"] = status
        request["response_evidence_ids"] = evidence_ids
        request["responded_at"] = state["project"].get("now")
    elif kind == "task_completed":
        task = _find(state["tasks"], event.get("task_id"), "task")
        if event.get("request_id"):
            _current_request(state, _find(state["requests"], event["request_id"], "request"))
        if issuer != task.get("owner_id"):
            raise DomainError("Task completion must be supplied by its recorded responsible actor.")
        if item:
            item.setdefault("task_id", task["id"])
        _complete(state, task["id"], evidence_ids, issuer)
        for request in state["requests"]:
            if request.get("id") == event.get("request_id") or (request.get("task_id") == task["id"] and request.get("purpose") == "task_completion"):
                request["status"] = "answered"
    elif kind in ("evidence", "evidence_received", "clock_advance", "noop"):
        pass
    else:
        raise DomainError("Unsupported simulator event: %s" % kind)
    public_event = {key: value for key, value in event.items() if key != "evidence"}
    if item:
        public_event["evidence_id"] = item["id"]
    state["events"].append(public_event)
    _audit(state, "event:" + str(kind), event.get("summary", event["id"]), issuer or "simulator")
    _refresh_rework(state)
    return state


def _current_request(state, request):
    record = next((r for r in state["rework"] if r["id"] == request.get("rework_id")), None)
    target = record or state["gates"].get(request.get("gate_id")) or next((t for t in state["tasks"] if t["id"] == request.get("task_id")), {})
    if request.get("status") == "superseded" or (record and record.get("status") == "superseded") or request.get("rework_generation", 0) != target.get("generation", target.get("rework_generation", 0)):
        raise DomainError("Response belongs to a superseded review cycle; obtain a current scoped response.")


def _return_review(state, event, issuer, item):
    gate = state["gates"].get(event.get("gate_id"), {})
    if not gate or not _gate_authorized(state, gate, issuer):
        raise DomainError("Only the recorded reviewer may return this review.")
    if not _valid_evidence(state, item) or item.get("issuer_id") != issuer:
        raise DomainError("Returned review requires current scoped reviewer evidence.")
    correction_owner = event.get("correction_owner_id") or gate.get("correction_owner_id")
    if not correction_owner or not event.get("required_artifact") or not (event.get("reason") or event.get("summary")):
        raise DomainError("Returned review must identify a correction owner, reason and required artifact.")
    _find(state["stakeholders"], correction_owner, "correction owner")
    gate_ids = list(dict.fromkeys([gate["id"]] + event.get("affected_gate_ids", [])))
    _open_rework(state, event, gate_ids, [item["id"]], correction_owner)
    _material(state)


def _update_gate(state, gate_id, status, issuer, item):
    gate = state["gates"].get(gate_id)
    if not gate:
        raise DomainError("Unknown gate: %s" % gate_id)
    if status not in ("pending", "approved", "blocked"):
        raise DomainError("Receipt or acknowledgement does not constitute gate approval.")
    if status == "approved":
        if _correction_pending(state, gate_id):
            raise DomainError("The returned review requires correction evidence before reapproval.")
        if not _gate_authorized(state, gate, issuer):
            raise DomainError("Actor lacks authority for gate %s." % gate_id)
        if not _valid_evidence(state, item, gate.get("design_sensitive", True)):
            raise DomainError("Gate approval requires verified evidence for the applicable project and design.")
        if item.get("issuer_id") != issuer:
            raise DomainError("Approval evidence issuer does not match the authorized actor.")
        if not _fresh_for(gate, item):
            raise DomainError("Gate reapproval requires fresh evidence after its invalidation.")
        tasks = {t["id"]: t for t in state["tasks"]}
        if any(tasks.get(key, {}).get("status") != "completed" for key in gate.get("required_tasks", [])) or any(not _gate_ready(state, key) for key in gate.get("required_gates", [])):
            raise DomainError("Approval prerequisites are not yet evidenced.")
        if item.get("kind") in ("receipt", "acknowledgement", "draft", "request", "correction_record"):
            raise DomainError("Receipt, draft, request, or correction evidence cannot establish separate approval.")
    elif not _gate_authorized(state, gate, issuer) or not _valid_evidence(state, item) or item.get("issuer_id") != issuer:
        raise DomainError("Gate withdrawal requires current scoped evidence from its authorized reviewer.")
    changed = gate.get("status") != status
    gate.update({"status": status, "issuer_id": issuer, "design_revision": state["project"].get("design_revision")})
    if item:
        gate["evidence_ids"] = list(dict.fromkeys(gate.get("evidence_ids", []) + [item["id"]]))
    if status == "approved":
        for request in state["requests"]:
            if (request.get("gate_id") == gate_id or request.get("subject_id") == gate_id) and request.get("status") in OPEN_REQUEST_STATUSES:
                request["status"] = "resolved"
        for alert in state["alerts"]:
            if alert.get("gate_id") == gate_id:
                alert["resolved"] = True
    if changed:
        _material(state)
