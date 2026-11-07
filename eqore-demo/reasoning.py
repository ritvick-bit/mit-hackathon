"""Public, auditable decision explanations derived from observed project records.

This module produces a compact fact/constraint/action record, not an LLM's hidden
reasoning. Models choose among these records; they cannot rewrite their facts.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

VERSION = "causal-record-1"
OBSERVED_KEYS = ("project", "tasks", "stakeholders", "evidence", "gates", "calendars",
                 "proposals", "decisions", "requests", "bookings", "alerts", "rework")


def observed_digest(state):
    return hashlib.sha256(json.dumps({k: state.get(k, [] if k == "rework" else None) for k in OBSERVED_KEYS},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def design_acceptance_recorded(state):
    """Revision naming and document titles do not establish accepted design."""
    gate = state.get("gates", {}).get("design", {})
    project = state.get("project", {})
    if gate.get("status") != "approved" or gate.get("design_revision") != project.get("design_revision"):
        return False
    actor = next((p for p in state.get("stakeholders", []) if p.get("id") == gate.get("issuer_id")), {})
    scopes = actor.get("can_approve", [])
    if gate.get("required_authority", "design") not in scopes and "*" not in scopes:
        return False
    return any(e.get("id") in gate.get("evidence_ids", []) and e.get("verified") and
               e.get("project_id") == project.get("id") and e.get("design_revision") == project.get("design_revision") and
               e.get("issuer_id") == gate.get("issuer_id") and e.get("status") not in ("draft", "superseded", "rejected") and
               e.get("kind") not in ("receipt", "acknowledgement", "draft", "request") for e in state.get("evidence", []))


def _pointer(state, ref):
    value = state
    for part in ref.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _dt(value):
    if not value:
        return None
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _date(value):
    result = _dt(value)
    return result.strftime("%b ") + str(result.day) + result.strftime(" at %H:%M") if result else "an unrecorded time"


def _money(value):
    return "$" + format(float(value), ",.0f" if float(value).is_integer() else ",.2f")


class _Facts:
    def __init__(self, state):
        self.state = state
        self.rows = []
        self.evidence_ids = {e["id"] for e in state.get("evidence", [])}

    def add(self, ref, label, evidence_ids=()):
        try:
            value = _pointer(self.state, ref)
        except (KeyError, IndexError, ValueError, TypeError):
            return None
        existing = next((row for row in self.rows if row["ref"] == ref), None)
        if existing:
            return existing["id"]
        identity = "F%02d" % (len(self.rows) + 1)
        self.rows.append({"id": identity, "label": label, "value": deepcopy(value), "ref": ref,
                          "evidence_ids": [e for e in evidence_ids if e in self.evidence_ids]})
        return identity

    def record(self, collection, identity, field, label):
        for index, item in enumerate(self.state.get(collection, [])):
            if item.get("id") == identity:
                return self.add("/%s/%s/%s" % (collection, index, field), label, item.get("evidence_ids", []))
        return None


def _schedule_cause(state, impacts, facts):
    """Describe an actual computed violation, never infer one from a late message."""
    tasks = {t["id"]: t for t in state.get("tasks", [])}
    for impact in sorted(impacts, key=lambda i: i.get("kind") != "delivery"):
        task = tasks.get(impact.get("task_id"), {})
        if not task:
            continue
        facts.record("tasks", task["id"], "planned_start", task["title"] + " planned start")
        facts.record("tasks", task["id"], "duration_hours", "Required task duration (hours)")
        kind = impact.get("kind")
        if kind == "delivery":
            facts.add("/project/delivery_eta", "Current supplier delivery estimate")
            facts.add("/project/delivery_effective_at", "Effective time of current estimate")
            return "The %s delivery estimate is later than %s unloading." % (
                _date(state["project"].get("delivery_eta")), _date(task.get("planned_start")))
        if kind in ("resource", "resource_unknown"):
            value = task.get("resources", task.get("resource"))
            resources = ([value] if isinstance(value, str) else list(value or [])) + task.get("required_resources", [])
            start = _dt(task.get("planned_start"))
            end = start + timedelta(hours=float(task.get("duration_hours", 0))) if start else None
            for resource in resources:
                windows = state.get("calendars", {}).get(resource, [])
                if not start or not any(_dt(w["start"]) <= start and end <= _dt(w["end"]) for w in windows):
                    facts.add("/calendars/" + _escape(resource), resource.replace("_", " ") + " offered windows")
                    return "%s at %s has no recorded %s window covering its full duration." % (
                        task["title"], _date(task.get("planned_start")), resource.replace("_", " "))
        if kind == "dependency":
            start = _dt(task.get("planned_start"))
            for parent_id in task.get("predecessors", []):
                parent = tasks.get(parent_id, {})
                parent_start = _dt(parent.get("planned_start"))
                if start and parent_start and parent_start + timedelta(hours=float(parent.get("duration_hours", 0))) > start:
                    facts.record("tasks", parent_id, "planned_start", parent["title"] + " planned start")
                    facts.record("tasks", parent_id, "duration_hours", "Prerequisite duration (hours)")
                    return "%s starts %s before %s can finish at %s." % (
                        task["title"], _date(task.get("planned_start")), parent["title"],
                        _date((parent_start + timedelta(hours=float(parent.get("duration_hours", 0)))).isoformat()))
        if kind == "resource_conflict":
            facts.add("/tasks", "Recorded task windows and resource assignments")
            return "%s at %s overlaps another task using the same resource." % (task["title"], _date(task.get("planned_start")))
        if kind == "missing_dependency":
            facts.record("tasks", task["id"], "predecessors", "Required predecessor identifiers")
            return "%s refers to a prerequisite absent from the project records." % task["title"]
    return "The proposed dates are feasible against the recorded schedule constraints."


def build_reasoning(state, decision, impacts=()):
    action = decision["action"]
    kind, purpose = action["type"], action.get("purpose")
    facts = _Facts(state)
    facts.add("/project/revision", "Observed project revision")
    facts.add("/project/design_revision", "Recorded design revision")
    design_gate = state.get("gates", {}).get("design", {})
    facts.add("/gates/design/status", "Recorded design acceptance status", design_gate.get("evidence_ids", []))
    facts.add("/gates/design/design_revision", "Design acceptance revision scope", design_gate.get("evidence_ids", []))
    design_accepted = design_acceptance_recorded(state)
    tasks = {t["id"]: t for t in state.get("tasks", [])}
    person = next((p for p in state.get("stakeholders", []) if p["id"] == action.get("recipient_id")), {})
    if person:
        facts.record("stakeholders", person["id"], "name", "Responsible contact")
        facts.record("stakeholders", person["id"], "can_approve", "Recorded authority scopes")
    contact = person.get("name", "the responsible actor")
    task = tasks.get(action.get("task_id") or action.get("subject_id"), {})
    gate_id = action.get("gate_id")
    gate = state.get("gates", {}).get(gate_id, {})
    proposal = next((p for p in state.get("proposals", []) if p["id"] == action.get("proposal_id")), {})
    rule_id, rule = "recorded_prerequisites", "Only observed, scoped evidence and designated authority permit the next state transition."
    summary = decision.get("why_now", "Recorded prerequisites must be resolved before proceeding.")
    consequence = decision.get("blocker", "Work remains blocked.")
    request = decision.get("request", decision.get("title", "Review current project records"))
    unlocks = [tasks.get(t, {}).get("title", t) for t in decision.get("unlocks", [])]
    uncertainty = ["Project records may change; this explanation describes the current observed snapshot."]
    reconsider = ["New relevant evidence, an authorized response, or a project revision changes the facts."]

    if purpose == "rework_correction":
        record = next((r for r in state.get("rework", []) if r["id"] == action.get("rework_id")), {})
        for field, label in (("reason", "Reviewer return reason"), ("status", "Current review cycle status"), ("correction_owner_id", "Assigned correction owner"),
                             ("required_artifact", "Required correction record"), ("gate_ids", "Acceptance requiring renewed review"), ("task_ids", "Affected acceptance tasks")):
            facts.record("rework", record["id"], field, label)
        summary = "%s. %s must supply the corrected package before the relevant reviewer can accept it." % (record["reason"].rstrip("."), contact)
        rule_id, rule = "scoped_correction_before_reapproval", "A returned review requires fresh correction evidence from its named owner, followed by separate acceptance from the original reviewer."
        consequence = "The affected approvals and acceptance tasks remain open; unrelated completed physical work is preserved."
        request = "Ask %s to supply %s for %s. Reference the returned comments and the current project/design scope. This correction does not itself grant reviewer approval or authorize added cost." % (contact, record["required_artifact"].rstrip("."), record["id"])
        unlocks = ["Resubmit the corrected package for scoped reviewer acceptance.", "Re-evidence only the affected acceptance and handoff tasks."]
        uncertainty = ["The reviewer may request further changes; correction evidence is not approval.", "A change to design, cost or dates needs its own applicable review and authorization."]
    elif kind in ("propose_plan", "request_approval", "commit_plan") or purpose in ("schedule_recovery", "rejected_plan"):
        cause = _schedule_cause(state, impacts, facts)
        rule_id, rule = "schedule_feasibility_and_authorization", "Delivery, dependencies and full resource windows must fit; a plan change needs the designated approver before commitment."
        uncertainty = ["Supplier ETA is an estimate, not physical receipt.", "Offered calendar windows are not confirmed external bookings."]
        reconsider = ["Delivery estimate, available windows, cost, design or proposal revision changes.", "The authorized approver rejects or qualifies the proposal."]
        if proposal:
            for field, label in (("status", "Proposal decision status"), ("based_on_revision", "Proposal revision"),
                                 ("cost_delta", "Proposed incremental cost"), ("changes", "Proposed task dates"),
                                 ("required_approver_id", "Designated proposal approver"), ("required_authority", "Required approval scope")):
                facts.record("proposals", proposal["id"], field, label)
        if kind == "propose_plan":
            summary = cause + " Prepare a feasible alternative before seeking authorization."
            consequence = "The current schedule cannot be relied on; drafting a proposal does not authorize the replacement dates."
            unlocks = ["A specific schedule and cost proposal can be presented to its designated approver."]
        elif kind == "request_approval":
            summary = cause + " The %s change needs %s's approval before commitment." % (_money(proposal["cost_delta"]), contact)
            consequence = "The recovery option is proposed, but no valid approval is recorded for commitment."
            changes = "; ".join(tasks.get(c["task_id"], {}).get("title", c["task_id"]) + ": " + _date(c["planned_start"]) for c in proposal["changes"])
            request = "Ask %s to explicitly approve %s, revision %s, with %s additional cost: %s. An acknowledgement alone is insufficient." % (
                contact, proposal["id"], proposal["based_on_revision"], _money(proposal["cost_delta"]), changes)
            unlocks = ["Commit this unchanged proposal only after explicit approval and a fresh feasibility check.", "Then request separate external booking confirmations."]
        elif kind == "commit_plan":
            facts.add("/decisions", "Recorded proposal approvals")
            summary = cause + " The unchanged proposal is approved; apply it after rechecking feasibility."
            consequence = "Approval has not yet changed the working schedule or reserved external capacity."
            unlocks = ["Update the internal task dates and authorized cost.", "Request the required external bookings; commitment alone does not confirm them."]
        elif purpose == "rejected_plan":
            rejected = next((p for p in state.get("proposals", []) if action.get("subject_id") == "rejected_plan:" + p["id"]), {})
            if rejected:
                facts.record("proposals", rejected["id"], "status", "Rejected proposal status")
                facts.record("proposals", rejected["id"], "changes", "Rejected dates")
            summary = cause + " The proposed recovery was rejected; ask the approver what must change."
            consequence = "Resubmitting unchanged dates and cost would not resolve the recorded rejection."
            unlocks = ["Develop a materially different option using the approver's response."]
        else:
            facts.add("/calendars", "All recorded resource windows")
            summary = cause + " No feasible recovery fits the known windows; ask for additional options."
            consequence = "The current constraints do not support a defensible replacement commitment."
            unlocks = ["Recompute alternatives after an authorized new window or scope change is recorded."]
    elif purpose == "authority_revalidation":
        proposal = next((p for p in state.get("proposals", []) if action.get("subject_id") == "authority:" + p["id"]), {})
        approver = next((p for p in state.get("stakeholders", []) if p["id"] == proposal.get("required_approver_id")), {})
        for field in ("required_approver_id", "required_authority", "cost_delta", "status"):
            facts.record("proposals", proposal.get("id"), field, "Proposal " + field.replace("_", " "))
        for field in ("can_approve", "approval_limit"):
            facts.record("stakeholders", approver.get("id"), field, "Current approver delegation")
        summary = "%s's recorded approval no longer satisfies the current delegation for this proposal; obtain a new authorized review before commitment." % approver.get("name", "The previous approver")
        rule_id, rule = "current_approval_authority", "Commitment revalidates the exact approver, scope and cost delegation; an old approval cannot be transferred to a newly eligible person."
        consequence = "The approved proposal remains uncommitted and its cost cannot be added to the project budget."
        unlocks = ["Re-establish valid authorization for the exact proposal before attempting commitment."]
        uncertainty = ["A review request does not restore revoked authority or create a replacement approval."]
    elif purpose in ("escalation", "follow_up"):
        parent = next((r for r in state.get("requests", []) if r["id"] == action.get("parent_request_id")), {})
        facts.add("/project/now", "Current simulated time")
        facts.add("/project/response_policy", "Follow-up and escalation timing policy")
        for field in ("created_at", "due_at", "status", "recipient_id"):
            facts.record("requests", parent.get("id"), field, "Original request " + field.replace("_", " "))
        label = gate.get("label", action.get("subject_id", "required response"))
        policy = state["project"].get("response_policy", {})
        hours = policy.get("escalate_after_hours", 48) if purpose == "escalation" else policy.get("follow_up_after_hours", 24)
        if purpose == "escalation":
            summary = "%s remains unresolved past its response deadline and %s-hour escalation interval; ask %s to unblock the response." % (label, hours, contact)
            rule_id, rule = "overdue_response_escalation", "The escalation interval is measured from the original request; an acknowledgement does not restart it or supply the missing approval."
        else:
            summary = "%s still lacks the required outcome %s hours after the original request; follow up with %s." % (label, hours, contact)
            rule_id, rule = "timed_response_follow_up", "Follow up only after the original request's policy interval, with the same responsible actor; an acknowledgement does not imply approval."
        consequence = "Dependent work remains blocked until the original scope is resolved by an authorized actor."
        uncertainty = ["The escalation recipient may coordinate a response but may not hold the missing approval authority."] if purpose == "escalation" else ["The reviewer may acknowledge again; only a valid scoped outcome resolves the gate."]
        unlocks = ["Obtain a response or a revised response commitment; re-evaluate the dependent work."]
    elif gate or purpose == "issue_resolution":
        alert = next((a for a in state.get("alerts", []) if not a.get("resolved") and
                      (a.get("gate_id") == gate_id if gate_id else a["id"] == action.get("subject_id"))), {})
        label = gate.get("label", alert.get("title", "Recorded discrepancy"))
        if gate:
            base = "/gates/" + _escape(gate_id)
            for field, title in (("status", "Readiness/approval status"), ("design_revision", "Gate design scope"),
                                 ("required_authority", "Required authority"), ("resolver_id", "Gate resolver"),
                                 ("required_artifact", "Required confirmation artifact")):
                facts.add(base + "/" + field, title, gate.get("evidence_ids", []))
        if alert:
            facts.record("alerts", alert["id"], "title", "Observed discrepancy")
            facts.record("alerts", alert["id"], "resolved", "Discrepancy resolution status")
        affected = [t["title"] for t in state.get("tasks", []) if t.get("status") != "completed" and gate_id in t.get("required_gates", [])] if gate_id else unlocks
        blocked = ", ".join(affected[:2]) or "dependent work"
        cause = alert.get("title") or (label + " is " + str(gate.get("status", "unresolved")))
        if not alert and gate.get("status") == "approved" and gate.get("design_revision") != state["project"].get("design_revision"):
            cause = "%s covers %s; the current design is %s" % (label, gate.get("design_revision"), state["project"].get("design_revision"))
        summary = "%s; ask %s for scoped confirmation before %s can proceed." % (cause.rstrip("."), contact, blocked)
        if gate:
            request = "Ask %s for %s, scoped to this project and recorded revision %s. %s A receipt or acknowledgement alone is insufficient." % (
                contact, label, state["project"].get("design_revision", "unrecorded"),
                gate.get("required_artifact", "Supply authorized confirmation backed by current scoped evidence.").rstrip(".") + ".")
        else:
            request = "Ask %s to review and resolve %s, then provide the outcome and supporting evidence for this project." % (contact, label)
        rule_id, rule = "scoped_gate_authority", "A prerequisite is satisfied only by its designated authority for this project and current design; a receipt or acknowledgement is insufficient."
        consequence = label + " does not currently authorize its dependent work."
        uncertainty = ["A pending gate does not prove the physical condition is unsafe; it means the required evidence or authorization is not recorded."]
        unlocks = ["Recheck readiness for " + title + " after valid confirmation." for title in affected] or ["Reassess the affected work after the discrepancy is resolved."]
    elif kind == "confirm_booking":
        booking = next((b for b in state.get("bookings", []) if b["id"] == action.get("booking_id")), {})
        facts.record("bookings", booking.get("id"), "status", "External booking status")
        facts.record("bookings", booking.get("id"), "planned_start", "Committed work window")
        facts.record("tasks", task.get("id"), "planned_start", "Planned task start")
        summary = "%s is planned for %s, but its external booking is %s; ask %s to confirm capacity." % (task.get("title", "Work"), _date(task.get("planned_start")), booking.get("status", "unconfirmed"), contact)
        rule_id, rule = "external_booking_confirmation", "Internal plan approval and commitment do not reserve a counterpart's capacity; only its scoped reply can confirm the booking."
        consequence = "The task cannot be recorded as complete while its required booking remains unconfirmed."
        unlocks = ["Record a confirmed reservation only after the responsible counterpart responds."]
        uncertainty = ["The counterpart may decline or withdraw the offered slot."]
    elif task and (kind == "complete_task" or purpose == "task_completion"):
        facts.record("tasks", task["id"], "status", "Task recorded status")
        facts.record("tasks", task["id"], "planned_start", "Task work window")
        facts.record("tasks", task["id"], "external", "External work requirement")
        for parent_id in task.get("predecessors", []):
            facts.record("tasks", parent_id, "status", tasks.get(parent_id, {}).get("title", parent_id) + " status")
        for identity in action.get("evidence_ids", []):
            facts.record("evidence", identity, "verified", "Completion evidence verified status")
            facts.record("evidence", identity, "task_id", "Completion evidence task scope")
            facts.record("evidence", identity, "issuer_id", "Completion evidence issuer")
        if kind == "complete_task":
            digital = task.get("completion_mode") == "digital" or task.get("external") is False
            summary = "%s has its recorded prerequisites satisfied; %s." % (task["title"],
                "this digital record can now be completed" if digital else "scoped completion evidence is available to record the finished work")
            rule_id, rule = "evidenced_completion", "Digital work may be completed when ready; external work requires valid scoped completion evidence, elapsed work time and required confirmed bookings."
            consequence = "The task is ready to be recorded complete; downstream prerequisites are still checked separately."
        else:
            summary = "%s has its recorded prerequisites satisfied, but no accepted completion record; ask %s for the work result and evidence." % (task["title"], contact)
            rule_id, rule = "missing_completion_evidence", "A ready task is not a completed task; the responsible actor must supply scoped evidence before completion is recorded."
            consequence = "The product cannot mark this external task complete from its scheduled date or an unsupported assertion."
        unlocks = ["Recheck readiness for " + t["title"] + "." for t in state["tasks"] if task["id"] in t.get("predecessors", [])] or ["Update the evidenced project completion state."]
        uncertainty = ["Readiness is based on recorded prerequisites; external work and any later outcome must still be evidenced."]
        if not design_accepted:
            uncertainty.append("The recorded revision identifier does not establish an issued or approved design. This task's evidence does not close design acceptance.")
    elif kind == "wait":
        pending = [r for r in state.get("requests", []) if r.get("status") in ("pending", "sent", "acknowledged")]
        done = (all(t.get("status") == "completed" for t in state.get("tasks", [])) and
                all(g.get("status") == "approved" and g.get("design_revision", state["project"].get("design_revision")) == state["project"].get("design_revision") for g in state.get("gates", {}).values()) and
                not any(r.get("status") not in ("resolved", "superseded") for r in state.get("rework", [])) and
                not any(not a.get("resolved") for a in state.get("alerts", [])))
        if done:
            facts.add("/tasks", "All recorded task completion states")
            summary = "All %s project tasks are recorded complete; no further project action is currently due." % len(state.get("tasks", []))
            rule_id, rule = "evidenced_terminal_state", "A completed project requires current scoped acceptance, completed tasks and no open rework or discrepancy."
            consequence, unlocks = "The current project scope has reached its evidenced handoff state.", []
        elif pending:
            facts.add("/requests", "Outstanding counterpart requests")
            summary = "%s counterpart request%s remain open and no other permitted progress action is available; await a response or deadline." % (len(pending), "s" if len(pending) != 1 else "")
            rule_id, rule = "bounded_wait", "Waiting is intermediate; an unanswered request does not imply approval or successful completion."
            consequence, unlocks = "Unresolved work remains blocked.", ["Re-evaluate when a reply, deadline, or relevant new observation arrives."]
        else:
            facts.add("/gates", "Unresolved project prerequisites")
            facts.add("/tasks", "Recorded task dependencies and completion states")
            summary = "Unfinished work has unresolved prerequisites and no currently permitted progress action; obtain missing project information."
            rule_id, rule = "incomplete_observation", "The absence of an executable action is not project completion."
            consequence, unlocks = "The project remains incomplete; the missing prerequisite must be investigated.", ["Re-evaluate after the missing prerequisite or responsible actor is recorded."]
        reconsider = ["A counterpart response, response deadline, new observation or scoped project change is recorded."]
    else:
        facts.add("/requests", "Recorded information requests")
        summary = "The recorded information needed for %s remains outstanding; request it from %s." % (action.get("subject_id", "the next decision"), contact)
        consequence = "The related decision remains provisional until the requested information is recorded."

    evidence = list(dict.fromkeys(e for e in decision.get("evidence_ids", []) if e in facts.evidence_ids))
    for row in facts.rows:
        evidence.extend(e for e in row["evidence_ids"] if e not in evidence)
    return {"version": VERSION, "based_on_revision": state["project"].get("revision"),
            "observed_state_digest": observed_digest(state), "summary": summary, "facts": facts.rows,
            "constraint": {"id": rule_id, "description": rule, "fact_ids": [f["id"] for f in facts.rows]},
            "consequence": consequence,
            "authorized_action": {"type": kind, "recipient_id": action.get("recipient_id"), "description": request},
            "expected_unlocks": unlocks, "uncertainties": uncertainty, "reconsider_when": reconsider,
            "evidence_ids": evidence}


def validate_reasoning(state, reasoning, fact_ids=None):
    """Reject stale records and references, including unversioned fact changes."""
    if reasoning.get("version") != VERSION or reasoning.get("observed_state_digest") != observed_digest(state):
        raise ValueError("Decision facts are stale; recompute the explanation against the current observations.")
    if reasoning.get("based_on_revision") != state["project"].get("revision"):
        raise ValueError("Decision revision is stale.")
    known_evidence = {e["id"] for e in state.get("evidence", [])}
    known_facts = set()
    for fact in reasoning.get("facts", []):
        if fact.get("id") in known_facts:
            raise ValueError("Duplicate decision fact identifier.")
        known_facts.add(fact.get("id"))
        try:
            current = _pointer(state, fact["ref"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("Unknown decision fact reference.") from exc
        if current != fact.get("value"):
            raise ValueError("Decision fact no longer matches its observed source.")
        if not set(fact.get("evidence_ids", [])).issubset(known_evidence):
            raise ValueError("Unknown decision evidence reference.")
    if not set(reasoning.get("evidence_ids", [])).issubset(known_evidence):
        raise ValueError("Unknown decision evidence reference.")
    if not set(reasoning.get("constraint", {}).get("fact_ids", [])).issubset(known_facts):
        raise ValueError("Unknown constraint fact reference.")
    if fact_ids is not None and not set(fact_ids).issubset(known_facts):
        raise ValueError("Model cited an unknown decision fact; recommendation discarded.")
    return True
