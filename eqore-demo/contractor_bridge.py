"""Contractor projections and scoped mutations over the canonical PM project state.

No second scheduler, project catalog or authority engine is introduced. The HTTP
boundary supplies actor identity and checks the project snapshot version.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import re

import engine
import messages
import operations
import workspace

EXCLUDED_ACTORS = {"pm", "commercial", "process"}
URGENCY_PRIORITY = {1: 100, 2: 85, 3: 70, 4: 55, 5: 40}
SUPPORTED = {"rigging", "electrical_ct", "epc_interconnection"}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _states(values):
    if isinstance(values, dict):
        values = values.values()
    return [item.get("state", item) for item in values]


def _selector(state):
    return state["project"].get("demo_project_id", state["project"]["id"])


def _actor(state, actor_id, profiles=None):
    if actor_id in EXCLUDED_ACTORS:
        raise engine.DomainError("This account does not have contractor access.")
    person = next((p for p in state.get("stakeholders", []) if p["id"] == actor_id), None)
    assigned = (any(t.get("owner_id") == actor_id for t in state.get("tasks", [])) or
                any(g.get("resolver_id") == actor_id for g in state.get("gates", {}).values()) or
                any(b.get("recipient_id") == actor_id for b in state.get("bookings", [])) or
                any(r.get("actor_id") == actor_id for r in state.get("contractor_reports", [])) or
                any(actor_id in c.get("stakeholder_ids", []) for c in state.get("operations", {}).get("cases", [])))
    inquiries = [i for i in state.get("operations", {}).get("inquiries", []) if i.get("vendor_id") == actor_id]
    if person and assigned:
        if person.get("project_ids") is not None and state["project"]["id"] not in person["project_ids"]:
            raise engine.DomainError("Contractor is not assigned to this project.")
        return {k: person.get(k) for k in ("id", "name", "role", "organization")}
    if inquiries:
        profile = next((p for p in (profiles or []) if p["id"] == actor_id), {})
        name = profile.get("name") or inquiries[0].get("vendor_name", actor_id)
        return {"id": actor_id, "name": name, "organization": name, "role": "Vendor contact"}
    raise engine.DomainError("Contractor is not assigned to this project.")


def accounts(states):
    """Observed assigned parties only, including vendors with real pending inquiries."""
    found = {}
    for state in _states(states):
        identities = {p["id"] for p in state.get("stakeholders", [])} | {i["vendor_id"] for i in state.get("operations", {}).get("inquiries", [])}
        for identity in identities - EXCLUDED_ACTORS:
            try:
                person = _actor(state, identity)
            except engine.DomainError:
                continue
            account = found.setdefault(identity, dict(person, project_ids=[]))
            if _selector(state) not in account["project_ids"]:
                account["project_ids"].append(_selector(state))
    return sorted(found.values(), key=lambda p: (p.get("organization") or "", p["name"], p["id"]))


def _owned_task(state, task_id, actor_id):
    task = engine._find(state["tasks"], task_id, "task")
    if task.get("owner_id") != actor_id:
        raise engine.DomainError("Only the recorded task owner may report or complete this task.")
    return task


def _readiness(state, task):
    reasons = []
    if task.get("status") == "completed":
        return ["Completion is already recorded."]
    tasks = {t["id"]: t for t in state["tasks"]}
    reasons.extend("Awaiting " + tasks.get(tid, {}).get("title", tid) for tid in task.get("predecessors", []) if tasks.get(tid, {}).get("status") != "completed")
    reasons.extend("Acceptance needed: " + state["gates"].get(gid, {}).get("label", gid) for gid in task.get("required_gates", []) if not engine._gate_ready(state, gid))
    reasons.extend("Counterpart booking is not confirmed." for b in state.get("bookings", []) if b.get("task_id") == task["id"] and b.get("status") not in ("confirmed", "superseded"))
    reasons.extend(e["message"] for e in engine._schedule_errors(state) if e["task_id"] == task["id"])
    if task.get("planned_start") and engine._dt(state["project"]["now"]) < engine._dt(task["planned_start"]) + engine._duration(task):
        reasons.append("The recorded work window has not finished.")
    return list(dict.fromkeys(reasons))


def _task_view(state, task, actor_id):
    tasks = {t["id"]: t for t in state["tasks"]}
    people = {p["id"]: p for p in state["stakeholders"]}
    start = task.get("planned_start")
    booking = next((b for b in reversed(state.get("bookings", [])) if b.get("task_id") == task["id"] and b.get("status") != "superseded"), None)
    reasons = _readiness(state, task)
    return {"id": task["id"], "title": task["title"], "description": task.get("description", ""),
            "owner_id": task.get("owner_id"), "owner_name": people.get(task.get("owner_id"), {}).get("name", task.get("owner_id")),
            "is_owned": task.get("owner_id") == actor_id, "status": task["status"], "phase": task.get("phase_id", task.get("phase")),
            "planned_start": start, "planned_end": (engine._dt(start) + engine._duration(task)).isoformat() if start else None,
            "duration_hours": task.get("duration_hours"), "completed_at": task.get("completed_at"),
            "predecessors": [{"id": tid, "title": tasks.get(tid, {}).get("title", tid), "status": tasks.get(tid, {}).get("status", "unknown")} for tid in task.get("predecessors", [])],
            "gates": [{"id": gid, "label": state["gates"].get(gid, {}).get("label", gid), "status": state["gates"].get(gid, {}).get("status", "pending"), "ready": engine._gate_ready(state, gid)} for gid in task.get("required_gates", [])],
            "blocked_reasons": reasons, "can_complete": task.get("owner_id") == actor_id and not reasons,
            "booking_status": (booking or {}).get("status"), "booking_id": (booking or {}).get("id"), "evidence_ids": list(task.get("evidence_ids", []))}


def view(state, actor_id, project_version, vendor_profiles=None):
    """Project-scoped contractor view. No private response policy or whole-world writes."""
    actor = _actor(state, actor_id, vendor_profiles)
    state = operations.ensure(state)
    operation_view = operations.summarize(state, vendor_profiles)
    owned = {t["id"] for t in state["tasks"] if t.get("owner_id") == actor_id}
    my_reports = [r for r in state.get("contractor_reports", []) if r["actor_id"] == actor_id]
    source_ids = {r["message_id"] for r in my_reports}
    affected_owned = owned | {r["task_id"] for r in my_reports}
    cases = [c for c in operation_view["cases"] if actor_id in c.get("stakeholder_ids", []) or owned.intersection(c.get("affected_task_ids", [])) or source_ids.intersection(c.get("source_message_ids", [])) or any(b.get("recipient_id") == actor_id for b in c.get("bookings", []))]
    relevant_case_ids = {c["id"] for c in cases}
    cases_by_id = {c["id"]: c for c in cases}
    messages_by_id = {m["id"]: m for m in operation_view["messages"]}
    reports = []
    for report in my_reports:
        original = messages_by_id.get(report["message_id"], {})
        displayed = dict(deepcopy(report), message=deepcopy(original), intake_status=report["status"])
        linked = cases_by_id.get(report.get("case_id")) or next((c for c in cases if report["message_id"] in c.get("source_message_ids", [])), None)
        if linked:
            displayed["case_id"] = linked["id"]
        if linked:
            proposal = linked.get("current_proposal") or {}
            if linked["status"] == "resolved":
                displayed["status"] = "resolved"
            elif proposal.get("status") == "committed":
                displayed["status"] = "plan_committed"
            elif proposal.get("status") == "approved":
                displayed["status"] = "approved_pending_commit"
            elif proposal.get("status") in ("proposed", "pending"):
                displayed["status"] = "awaiting_pm_decision"
            elif proposal.get("status") in ("rejected", "stale"):
                displayed["status"] = "needs_scope_review"
        reports.append(displayed)
    updates = []
    for case in cases:
        proposal = case.get("current_proposal")
        if proposal:
            changes = [c for c in proposal.get("schedule_changes", []) if c["task_id"] in affected_owned]
            updates.append({"id": "proposal:" + proposal["id"], "at": proposal.get("committed_at", proposal.get("created_at")),
                "type": "approval", "title": case["title"], "status": proposal["status"], "case_id": case["id"],
                "detail": "Plan committed; confirm assigned bookings before work." if proposal["status"] == "committed" else "Decision status: " + proposal["status"].replace("_", " "),
                "task_ids": [c["task_id"] for c in changes], "schedule_changes": changes})
        for identity in case.get("clarification_message_ids", []):
            original = messages_by_id.get(identity, {})
            updates.append({"id": "clarification:" + identity, "at": original.get("received_at"), "type": "clarification", "case_id": case["id"], "title": "PM clarification requested", "detail": original.get("text", ""), "task_ids": case.get("affected_task_ids", [])})
    for proposal in state.get("proposals", []):
        relevant = [c for c in proposal.get("changes", []) if c.get("task_id") in affected_owned]
        if relevant:
            updates.append({"id": "engine-proposal:" + proposal["id"], "at": proposal.get("created_at"), "type": "schedule", "title": "Project schedule update", "status": proposal.get("status"), "detail": "Schedule change is " + str(proposal.get("status", "pending")) + ".", "task_ids": [c["task_id"] for c in relevant], "schedule_changes": deepcopy(relevant)})
    bookings = [deepcopy(b) for b in state.get("bookings", []) if b.get("recipient_id") == actor_id and b.get("status") != "superseded"]
    for booking in bookings:
        booking["task_title"] = next((t["title"] for t in state["tasks"] if t["id"] == booking["task_id"]), booking["task_id"])
        booking["can_confirm"] = booking["status"] != "confirmed" and engine._dt(booking["planned_start"]) >= engine._dt(state["project"]["now"])
    timeline = [_task_view(state, t, actor_id) for t in state["tasks"]]
    timeline.sort(key=lambda t: (t.get("planned_start") or "", t["id"]))
    project = state["project"]
    public_cases = []
    for case in cases:
        projected = {key: deepcopy(case.get(key)) for key in ("id", "title", "why", "request", "priority", "status", "affected_task_ids", "conditions")}
        proposal = case.get("current_proposal")
        projected["current_proposal"] = None
        if proposal:
            projected["current_proposal"] = {key: deepcopy(proposal.get(key)) for key in ("id", "case_id", "status", "vendor_id", "vendor_name", "created_at", "committed_at", "work_package", "schedule_changes", "conditions", "approval_meaning", "required_approver_id")}
            if proposal.get("vendor_id") == actor_id:
                projected["current_proposal"]["cost_delta"] = proposal.get("cost_delta")
        projected["bookings"] = [deepcopy(b) for b in case.get("bookings", []) if b.get("recipient_id") == actor_id]
        public_cases.append(projected)
    clarifications = {identity for case in cases for identity in case.get("clarification_message_ids", [])}
    allowed_messages = [deepcopy(m) for m in operation_view["messages"] if m.get("issuer_id") == actor_id or (m["id"] in clarifications and m.get("issuer_id") == "pm")]

    return workspace.public({"project": {"id": _selector(state), "canonical_id": project["id"], "name": project["name"], "site": project.get("site", project.get("location")), "now": project["now"], "timezone": "America/New_York", "target_handoff": project.get("target_handoff", project.get("target_date")), "revision": project["revision"]},
        "project_version": project_version, "actor": actor, "tasks": [t for t in timeline if t["is_owned"]], "timeline": timeline,
        "reports": sorted(reports, key=lambda r: r["created_at"], reverse=True), "cases": public_cases, "updates": sorted(updates, key=lambda u: u.get("at") or "", reverse=True),
        "bookings": bookings, "inquiries": [dict(deepcopy(i), accepting_replies=not next((c for c in operation_view["cases"] if c["id"] == i["case_id"]), {}).get("work_package_id")) for i in operation_view["inquiries"] if i["vendor_id"] == actor_id],
        "replies": [deepcopy(r) for r in operation_view["replies"] if r["vendor_id"] == actor_id],
        "linked_messages": allowed_messages,
        "metrics": {"open_tasks": sum(t["is_owned"] and t["status"] != "completed" for t in timeline), "reports_waiting": sum(r["status"] in ("reported", "needs_scope_review", "sourcing", "awaiting_pm_decision", "approved_pending_commit") for r in reports), "bookings_waiting": sum(b["status"] != "confirmed" for b in bookings)}})


def _support_request(state, task, actor_id, report, support):
    capability = support.get("capability")
    if capability not in SUPPORTED:
        return None, "The requested trade needs PM scope review; no vendor type was guessed."
    mode = support.get("mode", "before")
    if mode not in ("before", "takeover"):
        return None, "Select whether support precedes the task or takes over its execution."
    if task["status"] == "completed":
        return None, "Completed work requires a scoped rework decision before adding a new package."
    if mode == "takeover" and not (capability == "rigging" and task["id"] == "t_unload"):
        return None, "Task takeover requires PM review of scope and ownership; this trade is not automatically reassigned."
    if mode == "before" and task["id"].startswith("work-"):
        return None, "A change to an already authorized work package requires PM review."
    duration = support.get("duration_hours", {"rigging": 1, "electrical_ct": 4, "epc_interconnection": 8}[capability])
    duration = operations._finite(duration, "Support duration", .25, 80)
    predecessors = list(task.get("predecessors", []))
    earliest = engine._dt(state["project"]["now"])
    for tid in predecessors:
        predecessor = engine._find(state["tasks"], tid, "task")
        earliest = max(earliest, engine._dt(predecessor["planned_start"]) + engine._duration(predecessor))
    if support.get("earliest_start"):
        earliest = max(earliest, engine._dt(support["earliest_start"]))
    request = {"title": report["subject"][:180], "why": "The assigned contractor reported a problem requiring PM coordination: " + report["raw_text"][:350],
        "request": report["raw_text"], "vendor_capability": capability, "affected_task_ids": [task["id"]], "predecessor_task_ids": predecessors,
        "stakeholder_ids": list(dict.fromkeys([actor_id, "engineer", "pm"])), "required_gates": [], "priority": URGENCY_PRIORITY[report["urgency"]],
        "duration_hours": duration, "earliest_start": earliest.isoformat(), "scope_id": "contractor-" + task["id"] + "-" + capability + "-" + mode,
        "kind": "contractor_support", "additional_conditions": ["Contractor request is a reported need; qualified scope, quotation and PM approval remain required.", "Vendor selection does not provide customer access, engineering acceptance or utility operating permission."]}
    if mode == "takeover":
        request["resource_override_task_id"] = task["id"]
    return request, None


def _finish_report(state, action, actor_id, profiles):
    task = _owned_task(state, action.get("task_id"), actor_id)
    kind = "completion" if action["type"] == "completion_report" else "problem"
    identity = action.get("client_report_id")
    if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", identity):
        raise engine.DomainError("Provide a stable client_report_id of 8–100 letters, digits, hyphens or underscores.")
    raw_text = action.get("raw_text", "")
    subject = action.get("subject") or ("Completion: " if kind == "completion" else "Problem: ") + task["title"]
    urgency = action.get("urgency", 3)
    if isinstance(urgency, bool) or urgency not in URGENCY_PRIORITY:
        raise engine.DomainError("Urgency must be a whole number from 1 (highest) to 5.")
    attachments = deepcopy(action.get("attachments", []))
    support = deepcopy(action.get("support") or {})
    if not isinstance(support, dict):
        raise engine.DomainError("Support request must be a structured object.")
    content = {"type": kind, "actor_id": actor_id, "task_id": task["id"], "raw_text": raw_text, "subject": subject, "urgency": urgency,
        "attachments": attachments, "support": support, "attest_complete": action.get("attest_complete", False)}
    digest = _hash(content)
    old = next((r for r in state.get("contractor_reports", []) if r["client_report_id"] == identity), None)
    if old:
        if old["request_hash"] != digest:
            raise engine.DomainError("This report ID was already used with different content. Submit a new report ID.")
        return deepcopy(state), []
    if kind == "completion":
        if action.get("attest_complete") is not True:
            raise engine.DomainError("The task owner must explicitly attest that this scoped work is complete.")
        reasons = _readiness(state, task)
        if reasons:
            raise engine.DomainError("Completion cannot be recorded: " + "; ".join(reasons))
    result, blobs, message_id = messages.prepare(state, {"sender_id": actor_id, "raw_text": raw_text, "subject": subject, "attachments": attachments}, profiles)
    message = messages.find(result, message_id)
    record = {"id": identity, "client_report_id": identity, "message_id": message_id, "actor_id": actor_id, "task_id": task["id"],
        "type": kind, "urgency": urgency, "priority": URGENCY_PRIORITY[urgency], "status": "reported", "support": support,
        "case_id": None, "created_at": result["project"]["now"], "request_hash": digest}
    message.update(task_id=task["id"], urgency=urgency, priority=record["priority"], contractor_report_id=identity)
    if kind == "completion":
        evidence = {"id": "completion-" + identity, "title": subject, "body": raw_text, "issuer_id": actor_id,
            "project_id": result["project"]["id"], "design_revision": result["project"].get("design_revision"), "task_id": task["id"],
            "kind": task.get("required_evidence_kind", "task_completion"), "effective_at": result["project"]["now"], "received_at": result["project"]["now"],
            "verified": True, "source_message_id": message_id, "source_hash": message["content_hash"], "attestation": "Task owner explicitly reports completion through the scoped contractor session."}
        result = engine.apply_event(result, {"id": "contractor-completed-" + identity, "type": "task_completed", "at": result["project"]["now"], "task_id": task["id"], "issuer_id": actor_id, "evidence": evidence, "summary": subject})
        record["status"] = "completion_recorded"
    elif support:
        request, review = _support_request(result, task, actor_id, {"subject": subject, "raw_text": raw_text, "urgency": urgency}, support)
        if request:
            # Link a matching outstanding case instead of opening duplicate holds.
            existing = next((c for c in result["operations"]["cases"] if c.get("vendor_capability") == request["vendor_capability"] and task["id"] in c.get("affected_task_ids", []) and c.get("status") != "resolved" and not c.get("work_package_id")
                and c.get("resource_override_task_id") == request.get("resource_override_task_id")
                and set(c.get("predecessor_task_ids", [])) == set(request["predecessor_task_ids"])
                and float(c.get("duration_hours", 0)) == float(request["duration_hours"])), None)
            payload = {"type": "ingest_message", "message_id": message_id, "issuer_id": actor_id, "text": raw_text, "subject": message["subject"], "attachments": message["attachments"]}
            payload.update(case_id=existing["id"]) if existing else payload.update(validated_request=request)
            result = operations.apply(result, payload, actor_id=actor_id, vendor_profiles=profiles)
            linked = next(c for c in result["operations"]["cases"] if message_id in c.get("source_message_ids", []))
            linked["priority"] = max(linked["priority"], record["priority"])
            record.update(case_id=linked["id"], status="sourcing")
        else:
            record.update(status="needs_scope_review", review_reason=review)
    result.setdefault("contractor_reports", []).append(record)
    result = operations.ensure(result)
    return result, blobs


def apply(state, payload, actor_id, profiles=None):
    """Only task-owner reports, scoped completion and named-counterpart replies."""
    profiles = operations._profiles(profiles)
    _actor(state, actor_id, profiles)
    payload = deepcopy(payload)
    kind = payload.get("type")
    if kind in ("report_problem", "message", "completion_report"):
        return _finish_report(state, payload, actor_id, profiles)
    if kind == "confirm_booking":
        booking = engine._find(state.get("bookings", []), payload.get("booking_id"), "booking")
        if booking.get("recipient_id") != actor_id:
            raise engine.DomainError("Only the named counterpart may confirm this booking.")
        if booking.get("status") == "superseded":
            raise engine.DomainError("This booking was superseded; review the current appointment.")
        if booking.get("status") == "confirmed":
            return deepcopy(state), []
        if engine._dt(booking["planned_start"]) < engine._dt(state["project"]["now"]):
            raise engine.DomainError("The booking start has passed. Ask the PM for a current work window.")
        if any(b["id"] == booking["id"] for b in state.get("operations", {}).get("bookings", [])):
            return operations.apply(state, {"type": "confirm_booking", "booking_id": booking["id"]}, actor_id=actor_id, vendor_profiles=profiles), []
        result = engine.apply_action(state, {"type": "confirm_booking", "task_id": booking["task_id"], "recipient_id": actor_id}, actor_id=actor_id)
        request = next(r for r in reversed(result["requests"]) if r.get("booking_id") == booking["id"])
        evidence = {"id": "contractor-booking-" + booking["id"], "title": "Counterpart confirms the exact work window", "body": "Confirmed " + booking["planned_start"],
            "issuer_id": actor_id, "project_id": state["project"]["id"], "design_revision": state["project"].get("design_revision"), "kind": "booking", "verified": True,
            "effective_at": state["project"]["now"], "received_at": state["project"]["now"]}
        return engine.apply_event(result, {"id": "contractor-booking-event-" + booking["id"], "type": "request_response", "at": state["project"]["now"], "request_id": request["id"], "booking_id": booking["id"], "issuer_id": actor_id, "status": "confirmed", "evidence": evidence}), []
    if kind == "receive_vendor_reply":
        inquiry = engine._find(state.get("operations", {}).get("inquiries", []), payload.get("inquiry_id"), "inquiry")
        if inquiry["vendor_id"] != actor_id:
            raise engine.DomainError("Only the queried vendor may answer this availability inquiry.")
        case = engine._find(state["operations"]["cases"], inquiry["case_id"], "case")
        if case.get("work_package_id"):
            raise engine.DomainError("This scope is already committed. Report a problem on the assigned task so the PM can review a new change.")
        allowed = {"type", "inquiry_id", "reply_id", "availability", "earliest_start", "available_until", "expires_at", "duration_hours", "total_price", "currency", "capacity_confirmed", "scope_complete", "text"}
        return operations.apply(state, {k: v for k, v in payload.items() if k in allowed}, actor_id=actor_id, vendor_profiles=profiles), []
    raise engine.DomainError("Contractor action is not permitted: " + str(kind))
