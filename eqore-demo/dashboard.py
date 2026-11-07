"""Project-wide, rule-based management view over the observed engine state.

This view never invents actions, actual spending, completion forecasts or critical
paths. Future routine prerequisites remain visible, separately from current
bottlenecks. All actions exposed here have passed the engine's own dry run.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import engine


RANKING_METHOD = (
    "Rule-based priority: unresolved safety/quality issues and required authority "
    "first, then schedule, booking and evidence constraints; response deadlines "
    "and the number of affected unfinished tasks adjust priority. Future "
    "prerequisites rank last. This is a transparent coordination queue, not a "
    "mathematically calculated critical path or an LLM judgment."
)


def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _amount(value):
    try:
        return round(float(value), 2) if value is not None else None
    except (TypeError, ValueError):
        return None


def _gate_ready(state, gate_id):
    return engine._gate_ready(state, gate_id)


def _finish(task):
    start = _date(task.get("planned_start"))
    return (start + timedelta(hours=float(task.get("duration_hours", 0)))).isoformat() if start else None


def _resources(task):
    value = task.get("resources", task.get("resource"))
    return list(dict.fromkeys(([value] if isinstance(value, str) else list(value or [])) + task.get("required_resources", [])))


def _alert_priority(alerts):
    """Use recorded issue type; an alert alone does not imply a safety defect."""
    priorities = []
    for alert in alerts:
        kind = alert.get("kind", "")
        if kind in ("safety", "safety_defect", "hazard") or alert.get("severity") == "critical":
            priorities.append((1000, "Safety / critical issue"))
        elif kind == "field_defect":
            priorities.append((950, "Field quality"))
        elif kind in ("commissioning_fault", "network_fault", "technical_readiness"):
            priorities.append((900, "Technical readiness"))
        elif kind in ("authority", "approval", "permit", "utility"):
            priorities.append((850, "Required authority"))
        else:
            priorities.append((800 if alert.get("severity") == "high" else 600, "Reported issue"))
    return max(priorities, default=(850, "Required authority"))


def _finance(state):
    project = state["project"]
    budget = project.get("budget", {})
    ledger = project.get("finance", {})
    lines = []
    for index, line in enumerate(ledger.get("lines", [])):
        lines.append({"id": line.get("id", "line-%s" % index),
                      "label": line.get("label", line.get("category", "Cost allocation")),
                      "category": line.get("category", "Other"),
                      "baseline": _amount(line.get("baseline", line.get("budget"))),
                      "committed": _amount(line.get("committed")),
                      "actual": _amount(line.get("actual")),
                      "task_ids": line.get("task_ids", []),
                      "notes": line.get("notes", "Synthetic cost allocation")})
    baseline = _amount(budget.get("baseline", project.get("budget_baseline")))
    if baseline is None and lines and all(l["baseline"] is not None for l in lines):
        baseline = round(sum(l["baseline"] for l in lines), 2)
    committed = _amount(budget.get("committed"))
    if committed is None and lines and all(l["committed"] is not None for l in lines):
        committed = round(sum(l["committed"] for l in lines), 2)
    # In the engine, budget.committed is the TOTAL, already including baseline.
    # Preserve original cost allocations and reconcile only the incremental delta.
    if lines and committed is not None and all(l["committed"] is not None for l in lines):
        change = round(committed - sum(l["committed"] for l in lines), 2)
        if change:
            lines.append({"id": "committed-plan-changes", "label": "Committed plan changes",
                          "category": "Authorized changes", "baseline": 0, "committed": change,
                          "actual": None, "task_ids": [],
                          "notes": "Authorized incremental commitment, not evidence of payment."})
    active_proposals = [p for p in state.get("proposals", [])
                        if p.get("based_on_revision") == project.get("revision") and
                        p.get("status") in ("proposed", "pending", "approved")]
    # Multiple proposals may be alternative versions of the same recovery; do
    # not imply they will all be purchased. Report the maximum pending exposure.
    proposed = max([_amount(p.get("cost_delta")) or 0 for p in active_proposals] or [0])
    original = ledger.get("lines", [])
    actual = round(sum(float(l["actual"]) for l in original), 2) if original and all(_amount(l.get("actual")) is not None for l in original) else None
    return {"currency": ledger.get("currency", "USD"), "baseline_total": baseline,
            "committed_total": committed,
            "committed_change": round(committed - baseline, 2) if committed is not None and baseline is not None else None,
            "proposed_change": proposed,
            "estimated_total": round(committed + proposed, 2) if committed is not None else None,
            "actual_total": actual, "actual_as_of": ledger.get("as_of"),
            "variance_to_baseline": round(committed + proposed - baseline, 2) if committed is not None and baseline is not None else None,
            "lines": lines, "labor": deepcopy(project.get("labor", ledger.get("labor", []))),
            "note": " ".join(filter(None, [ledger.get("note"), "Committed total already includes baseline. Estimated total is known commitment plus the largest active proposal, not an expenditure forecast. Stale/rejected proposals are excluded."])),
            "ledger_note": ledger.get("note", ""),
            "actual_note": "Posted-to-date synthetic ledger snapshot; task completion does not automatically accrue or pay costs." if actual is not None else "Actual expenditure has not been supplied."}


def summarize(state, analysis=None):
    """Return all current independent constraints plus tagged future prerequisites."""
    analysis = analysis if analysis is not None else engine.analyze(state)
    project = state["project"]
    tasks = {t["id"]: t for t in state.get("tasks", [])}
    people = {p["id"]: p for p in state.get("stakeholders", [])}
    now = _date(project.get("now"))
    pending = [r for r in state.get("requests", []) if r.get("status") in engine.OPEN_REQUEST_STATUSES]
    consumed_requests = set()
    rows = []
    valid_candidates = []
    for candidate in analysis.get("candidates", []):
        action = candidate.get("action", {})
        if action.get("type") in ("wait", "resolve_decision"):
            continue
        try:
            engine.apply_action(state, action)
        except (engine.DomainError, KeyError, TypeError, ValueError):
            continue
        valid_candidates.append(candidate)

    def candidate_for(predicate):
        return next((c for c in valid_candidates if predicate(c["action"])), None)

    def descendants(ids):
        found = set(ids)
        while True:
            extra = {tid for tid, task in tasks.items() if any(p in found for p in task.get("predecessors", []))}
            if extra.issubset(found):
                break
            found |= extra
        return [tid for tid in tasks if tid in found and tasks[tid].get("status") != "completed"]

    def add(identity, title, category, base, ids, resolver=None, evidence=None,
            status="actionable", next_step=None, candidate=None, requests=None, detail=None):
        ids = list(dict.fromkeys(tid for tid in ids if tid in tasks))
        affected = descendants(ids)
        requests = requests or []
        consumed_requests.update(r["id"] for r in requests)
        due = min((_date(r.get("due_at")) for r in requests if _date(r.get("due_at"))), default=None)
        overdue = bool(due and now and due <= now)
        if requests and not candidate and status != "upcoming":
            status = "waiting"
        impact_score = min(len(affected) * 5, 40)
        if overdue:
            urgency, urgency_text = 80, "response deadline has passed (+80)"
        else:
            starts = [_date(tasks[tid].get("planned_start")) for tid in ids]
            days = min(((dt - now).total_seconds() / 86400 for dt in starts if dt and now), default=None)
            urgency = 30 if days is not None and days <= 2 else 15 if days is not None and days <= 7 else 0
            urgency_text = "work is due within two days or overdue (+30)" if urgency == 30 else "work is due within seven days (+15)" if urgency else "no immediate date pressure recorded (+0)"
        score = base + urgency + impact_score if status != "upcoming" else min(base // 20, 60) + impact_score
        label = "Upcoming" if status == "upcoming" else "Urgent" if overdue or base >= 950 else "High" if score >= 750 else "Medium" if score >= 500 else "Normal"
        if candidate:
            next_step = candidate.get("request", candidate.get("title", next_step))
            resolver = candidate.get("recipient_id") or resolver
        if not next_step:
            next_step = "Await the responsible counterpart's scoped response." if requests else "Review the recorded prerequisite with its responsible owner."
        row = {"id": identity, "rank": 0, "title": title, "category": category,
               "priority_label": label, "score": score,
               "ranking_reason": ("Future prerequisite; supporting work must finish first. " if status == "upcoming" else "%s priority base %s; %s; " % (category, base, urgency_text)) + "%s unfinished tasks affected (+%s impact points)." % (len(affected), impact_score),
               "resolver_id": resolver, "task_ids": ids, "blocked_task_ids": affected,
               "evidence_ids": list(dict.fromkeys(evidence or [])), "status": status,
               "next_step": next_step, "unlocks": [tasks[tid]["title"] for tid in affected],
               "authority": people.get(resolver, {}).get("authority_source", "Authority must be confirmed from current project records."),
               "request_ids": [r["id"] for r in requests],
               "due_at": due.isoformat() if due else None, "overdue": overdue,
               "detail": detail or "", "ranking_mode": "rule_based"}
        if candidate:
            row["action"] = deepcopy(candidate["action"])
        rows.append(row)
        return row

    # A gate plus its issue alert and follow-up requests is one underlying block.
    gate_alerts = {}
    for alert in state.get("alerts", []):
        if not alert.get("resolved") and alert.get("gate_id"):
            gate_alerts.setdefault(alert["gate_id"], []).append(alert)
    correction_gates = set()
    for record in state.get("rework", []):
        if record.get("status") != "correction_required":
            continue
        rid = record["id"]
        correction_gates.update(record.get("gate_ids", []))
        requests = [r for r in pending if r.get("rework_id") == rid or r.get("subject_id") == rid]
        candidate = candidate_for(lambda a: a.get("rework_id") == rid or a.get("subject_id") == rid)
        affected_alerts = [a for gid in record.get("gate_ids", []) for a in gate_alerts.get(gid, [])]
        evidence = record.get("evidence_ids", []) + [eid for alert in affected_alerts for eid in alert.get("evidence_ids", [])]
        row = add("rework:" + rid, record.get("reason", "Returned review requires correction"), "Review correction", 960,
                  record.get("task_ids", []), record.get("correction_owner_id"), evidence,
                  candidate=candidate, requests=requests,
                  next_step="Await the named correction owner's scoped package; reviewer acceptance remains a separate subsequent step." if requests else None,
                  detail="%s Correction evidence must be supplied before the affected gates can be resubmitted. Unrelated completed physical work is preserved." % record.get("required_artifact", ""))
        row.update(rework_id=rid, gate_ids=list(record.get("gate_ids", [])), return_phase=record.get("return_phase"))
    for gid, gate in state.get("gates", {}).items():
        if gid in correction_gates:
            continue
        alerts = gate_alerts.get(gid, [])
        if _gate_ready(state, gid) and not alerts:
            continue
        dependent = [tid for tid, task in tasks.items() if task.get("status") != "completed" and gid in task.get("required_gates", [])]
        dependent += [tid for a in alerts for tid in a.get("task_ids", [])]
        if not dependent and not alerts:
            continue
        requests = [r for r in pending if r.get("subject_id") == gid or r.get("gate_id") == gid]
        candidate = candidate_for(lambda a: a.get("gate_id") == gid or a.get("subject_id") == gid)
        prereqs = all(tasks.get(tid, {}).get("status") == "completed" for tid in gate.get("required_tasks", [])) and all(_gate_ready(state, key) for key in gate.get("required_gates", []))
        immediate = any(all(tasks.get(p, {}).get("status") == "completed" for p in tasks[tid].get("predecessors", [])) for tid in dependent if tid in tasks)
        current = bool(alerts or requests or candidate or (prereqs and immediate))
        evidence = gate.get("evidence_ids", []) + [eid for a in alerts for eid in a.get("evidence_ids", [])]
        base, category = _alert_priority(alerts)
        row = add("gate:" + gid, alerts[0]["title"] if alerts else gate.get("label", gid),
                  category, base,
                  dependent, gate.get("resolver_id"), evidence,
                  "actionable" if current else "upcoming", candidate=candidate, requests=requests,
                  next_step="Complete the preceding work, then obtain scoped %s." % gate.get("label", gid) if not current else None,
                  detail="Gate status: %s. %s" % (gate.get("status", "unknown"), gate.get("scope", "")))
        row["gate_id"] = gid
    for alert in state.get("alerts", []):
        if alert.get("resolved") or alert.get("gate_id"):
            continue
        requests = [r for r in pending if r.get("subject_id") == alert["id"]]
        base, category = _alert_priority([alert])
        add("alert:" + alert["id"], alert["title"], category, base,
            alert.get("task_ids", []), alert.get("resolver_id"), alert.get("evidence_ids", []),
            candidate=candidate_for(lambda a: a.get("subject_id") == alert["id"]), requests=requests)

    # Group all delivery effects and each resource conflict at its root cause.
    # A dependency date conflict inherited from an earlier root is not another block.
    impacts = analysis.get("impacts", [])
    roots = {}
    non_dependency = [e for e in impacts if e.get("kind") != "dependency"]
    for impact in non_dependency:
        task = tasks.get(impact.get("task_id"), {})
        kind = impact.get("kind", "schedule")
        resource = next((r for r in _resources(task) if r in impact.get("message", "")), None)
        if kind == "resource_conflict" and not resource:
            other = next((other for tid, other in tasks.items() if ("task %s." % tid) in impact.get("message", "")), {})
            resource = next(iter(sorted(set(_resources(task)) & set(_resources(other)))), None)
        key = "delivery" if kind == "delivery" else "resource:" + resource if resource else kind + ":" + str(impact.get("task_id"))
        roots.setdefault(key, []).append(impact)
    rooted = set(tid for effects in roots.values() for tid in descendants([e["task_id"] for e in effects]))
    # Upstream conflicts have more descendants, so resolve them before their
    # dependent effects even if the task list was provided out of order.
    dependency_impacts = sorted((e for e in impacts if e.get("kind") == "dependency"),
                                key=lambda e: -len(descendants([e["task_id"]])))
    for impact in dependency_impacts:
        if impact.get("task_id") not in rooted:
            roots.setdefault("dependency:" + impact["task_id"], []).append(impact)
            rooted.update(descendants([impact["task_id"]]))
    schedule_candidate = candidate_for(lambda a: a.get("type") in ("propose_plan", "commit_plan") or a.get("purpose") in ("schedule_recovery", "rejected_plan"))
    for key, effects in roots.items():
        evidence = [e["id"] for e in state.get("evidence", []) if e.get("project_id") == project.get("id") and e.get("verified") and e.get("kind") in (("delivery",) if key == "delivery" else ("resource", "customer_window"))]
        requests = [r for r in pending if r.get("subject_id") == "schedule_recovery" or r.get("purpose") == "rejected_plan"]
        title = "Shipment misses the planned unloading window" if key == "delivery" else effects[0]["message"]
        add("schedule:" + key, title, "Schedule / resources", 720,
            [e["task_id"] for e in effects], "vendor" if key == "delivery" else "pm", evidence,
            candidate=schedule_candidate, requests=requests, detail=" ".join(dict.fromkeys(e["message"] for e in effects)))

    for proposal in state.get("proposals", []):
        if proposal.get("based_on_revision") != project.get("revision") or proposal.get("status") not in ("proposed", "pending", "approved"):
            continue
        pid = proposal["id"]
        requests = [r for r in pending if r.get("proposal_id") == pid or r.get("subject_id") == pid]
        candidate = candidate_for(lambda a: a.get("proposal_id") == pid)
        add("proposal:" + pid, "Apply the authorized plan" if proposal["status"] == "approved" else "Recovery plan awaits authorized decision",
            "Plan authority", 810, [c["task_id"] for c in proposal.get("changes", [])],
            proposal.get("required_approver_id"), proposal.get("evidence_ids", []),
            candidate=candidate, requests=requests, detail="Proposal %s; incremental cost $%s." % (pid, proposal.get("cost_delta", 0)))

    bookings_by_task = {}
    for booking in state.get("bookings", []):
        if booking.get("status") not in ("confirmed", "superseded"):
            bookings_by_task.setdefault(booking["task_id"], []).append(booking)
    for tid, bookings in bookings_by_task.items():
        requests = [r for r in pending if r.get("subject_id") == tid and r.get("purpose") == "booking"]
        candidate = candidate_for(lambda a: a.get("type") == "confirm_booking" and a.get("task_id") == tid)
        add("booking:" + tid, "External booking unconfirmed: " + tasks.get(tid, {}).get("title", tid),
            "External reservation", 650, [tid], bookings[-1].get("recipient_id"),
            candidate=candidate, requests=requests,
            detail="An internal plan does not reserve a contractor or customer window.")

    # Only the currently ready physical work gets an evidence row. Downstream
    # tasks inherit its block and are not repeated as one card per task.
    for tid in analysis.get("ready_tasks", []):
        task = tasks[tid]
        if task.get("completion_mode") == "digital" or task.get("external") is False or tid in bookings_by_task:
            continue
        evidence = [e for e in state.get("evidence", []) if e.get("verified") and engine._fresh_for(task, e) and e.get("project_id") == project.get("id") and e.get("design_revision") == project.get("design_revision") and e.get("task_id") == tid and e.get("issuer_id") == task.get("owner_id") and e.get("kind") in (task.get("required_evidence_kind"), "completion", "task_completion") and e.get("status") not in ("draft", "superseded", "rejected")]
        if evidence:
            continue
        requests = [r for r in pending if r.get("subject_id") == tid and r.get("purpose") != "booking"]
        candidate = candidate_for(lambda a: a.get("task_id") == tid or a.get("subject_id") == tid)
        add("evidence:" + tid, "Work or completion evidence outstanding: " + task["title"],
            "Scoped completion evidence", 450, [tid], task.get("owner_id"),
            candidate=candidate, requests=requests,
            detail="This task is ready for coordination. Only its responsible actor's verified current-project/current-design record can evidence completion.")

    # Preserve other unanswered inquiries (including escalation) without losing
    # them merely because they are no longer the single recommended next action.
    grouped_requests = {}
    for request in pending:
        if request["id"] not in consumed_requests:
            proposal = next((p for p in state.get("proposals", []) if p["id"] == request.get("proposal_id")), None)
            if proposal and (proposal.get("status") in ("stale", "rejected", "committed") or proposal.get("based_on_revision") != project.get("revision")):
                continue
            grouped_requests.setdefault(request.get("subject_id", request["id"]), []).append(request)
    for subject, requests in grouped_requests.items():
        last = requests[-1]
        candidate = candidate_for(lambda a: a.get("subject_id") == subject)
        add("request:" + subject, "Await response: " + last.get("request", subject), "Counterpart response", 500,
            [last.get("task_id") or subject], last.get("recipient_id"), status="actionable" if candidate else "waiting", candidate=candidate, requests=requests,
            next_step="Await the scoped response or recorded response deadline; retain the unresolved dependency until evidence arrives.")

    rows.sort(key=lambda row: (row["status"] == "upcoming", -row["score"], row["id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    completed = sum(t.get("status") == "completed" for t in tasks.values())
    blocked = {b["task_id"] for b in analysis.get("blocked_tasks", [])}
    blocked |= {tid for tid in bookings_by_task if tid in tasks and tasks[tid].get("status") != "completed"}
    ends = [(t, _date(_finish(t))) for t in tasks.values()]
    latest = max((end for _, end in ends if end), default=None)
    planned_finish = latest.isoformat() if latest else None
    target = project.get("target_handoff", project.get("target_date"))
    target_dt = _date(target)
    metrics = {"total_tasks": len(tasks), "completed_tasks": completed,
               "completion_percent": round(100 * completed / len(tasks)) if tasks else 0,
               "blocked_tasks": len(blocked), "ready_tasks": len(set(analysis.get("ready_tasks", [])) - blocked),
               "active_bottlenecks": sum(r["status"] != "upcoming" for r in rows),
               "waiting_bottlenecks": sum(r["status"] == "waiting" for r in rows),
               "upcoming_prerequisites": sum(r["status"] == "upcoming" for r in rows),
               "overdue_requests": sum(bool(_date(r.get("due_at")) and now and _date(r["due_at"]) <= now) for r in pending),
               "target_date": target, "planned_finish": planned_finish, "forecast_finish": None,
               "planned_variance_days": (latest.date() - target_dt.date()).days if latest and target_dt else None,
               "forecast_note": "Planned dates describe the recorded plan, not a completion forecast or confirmed external reservations. Unresolved gates, resource constraints and response times may change them."}
    milestones = []
    for tid, task in tasks.items():
        related = [r["id"] for r in rows if tid in r["blocked_task_ids"] and r["status"] != "upcoming"]
        status = "completed" if task.get("status") == "completed" else "blocked" if tid in blocked else "waiting" if related else "ready"
        milestones.append({"id": tid, "title": task["title"], "task_id": tid,
                           "planned_start": task.get("planned_start"), "planned_finish": _finish(task),
                           "completed_at": task.get("completed_at"), "status": status,
                           "owner_id": task.get("owner_id"), "phase": task.get("phase"), "blocker_ids": related})
    resource_ids = sorted(set(state.get("calendars", {})) | {r for t in tasks.values() for r in _resources(t)})
    resource_rows = []
    for rid in resource_ids:
        ids = [tid for tid, t in tasks.items() if rid in _resources(t)]
        bookings = [deepcopy(b) for b in state.get("bookings", []) if b.get("task_id") in ids and b.get("status") != "superseded"]
        owner_ids = project.get("resource_owners", {}).get(rid)
        if owner_ids is None:
            if rid == "customer_access":
                owner_ids = [state.get("gates", {}).get("customer_window", {}).get("resolver_id") or
                             ("ops" if "ops" in people else "facilities" if "facilities" in people else None)]
            elif rid in ("electrical_crew", "rigging_crew"):
                owner_ids = [{"electrical_crew": "electrician", "rigging_crew": "rigger"}[rid]]
            else:
                owner_ids = [tasks[tid].get("owner_id") for tid in ids]
        owner_ids = [owner_ids] if isinstance(owner_ids, str) else owner_ids
        owner_ids = list(dict.fromkeys(owner for owner in owner_ids if owner))
        resource_rows.append({"id": rid, "label": rid.replace("_", " ").capitalize(), "task_ids": ids,
                              "owner_ids": owner_ids,
                              "windows": deepcopy(state.get("calendars", {}).get(rid, [])),
                              "bookings": bookings,
                              "status": "conflict" if any(e.get("task_id") in ids and e.get("kind") in ("resource", "resource_unknown", "resource_conflict") for e in impacts) else "awaiting confirmation" if any(b.get("status") != "confirmed" for b in bookings) else "recorded windows" if rid in state.get("calendars", {}) else "availability unknown"})
    return {"bottlenecks": rows, "metrics": metrics, "finance": _finance(state),
            "milestones": milestones, "resources": resource_rows,
            "ranking_method": RANKING_METHOD, "ranking_mode": "rule_based"}
