"""Persistent PM decision cases and simulated vendor sourcing.

This is a deterministic domain boundary. Raw messages are evidence, never commands.
All operations return a copy, and no function sends email or contacts real vendors.
LLM reading summaries belong beside the immutable message fields, outside their hash.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
import re

import engine
import vendors

VERSION = "1.0.0"
DomainError = engine.DomainError


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _now(state):
    return state["project"]["now"]


def _find(rows, identity, kind="record"):
    return engine._find(rows, identity, kind)


def _next(ops, key):
    return "ops-" + key.rstrip("s") + "-%04d" % (len(ops[key]) + 1)


def _finite(value, label, minimum=0, maximum=None):
    if isinstance(value, bool):
        raise DomainError(label + " must be numeric.")
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise DomainError(label + " must be numeric.") from None
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        raise DomainError(label + " is outside the supported range.")
    return number


def _profiles(items):
    values = vendors.list_vendors() if items is None else deepcopy(items)
    if isinstance(values, dict):
        values = list(values.values())
    if len({v["id"] for v in values}) != len(values):
        raise DomainError("Vendor IDs must be unique.")
    return values


def _message_core(message):
    return {key: message.get(key) for key in ("id", "project_id", "issuer_id", "text", "subject", "received_at", "attachments")}


def _message(state, payload, case_id=None):
    ops = state["operations"]
    identity = str(payload.get("message_id") or payload.get("id") or _next(ops, "messages"))
    previous = next((m for m in ops["messages"] if m["id"] == identity), None)
    issuer = str(payload.get("issuer_id", ""))
    person = next((p for p in state["stakeholders"] if p["id"] == issuer), None)
    vendor = next((p for p in state.get("_operation_vendors", []) if p["id"] == issuer), None)
    if not person and not vendor:
        raise DomainError("Message issuer must be a recorded project stakeholder or queried vendor.")
    raw = payload.get("text")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 50000:
        raise DomainError("Message requires original text, at most 50,000 characters.")
    attachments = deepcopy(payload.get("attachments", []))
    if not isinstance(attachments, list) or len(attachments) > 12:
        raise DomainError("At most 12 attachment records are supported.")
    for attachment in attachments:
        if not isinstance(attachment, dict) or not attachment.get("name") or not re.fullmatch(r"[a-f0-9]{64}", attachment.get("sha256", "")):
            raise DomainError("Attachments require a name and SHA-256 content hash.")
        if not isinstance(attachment.get("url", ""), str) or (attachment.get("url") and not attachment["url"].startswith(("/assets/", "/attachments/", "/static/", "/api/attachments/"))):
            raise DomainError("Attachments must use the application's validated local attachment route.")
    at = payload.get("received_at") or (previous or {}).get("received_at") or _now(state)
    if engine._dt(at) > engine._dt(_now(state)):
        raise DomainError("A received message cannot be dated in the future.")
    message = {"id": identity, "project_id": state["project"]["id"], "issuer_id": issuer,
        "sender_name": (person or vendor)["name"], "text": raw, "subject": str(payload.get("subject") or "Project update")[:240],
        "received_at": at, "attachments": attachments, "case_id": case_id or payload.get("case_id"),
        "synthetic": True, "source_type": "stakeholder_message"}
    message["content_hash"] = _hash(_message_core(message))
    if previous:
        if previous["content_hash"] != message["content_hash"]:
            raise DomainError("Original message IDs and content are immutable; submit a new message ID for corrections.")
        if message.get("case_id"):
            previous["case_id"] = message["case_id"]
        return previous
    ops["messages"].append(message)
    state["evidence"].append({"id": identity, "title": message["subject"], "body": raw,
        "issuer_id": issuer, "project_id": state["project"]["id"], "design_revision": state["project"].get("design_revision"),
        "effective_at": at, "received_at": at, "kind": "stakeholder_message", "verified": True, "synthetic": True,
        "content_hash": message["content_hash"], "verification_scope": "Recorded provenance only; engineering claims and permission remain independently reviewable."})
    return message


def _validate_request(state, request):
    request = deepcopy(request)
    if not isinstance(request, dict) or request.get("vendor_capability") not in vendors.CAPABILITIES:
        raise DomainError("A reviewed request must name a supported vendor capability.")
    for key in ("title", "why", "request"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise DomainError("A reviewed request needs " + key + ".")
    task_ids = {t["id"] for t in state["tasks"]}
    actor_ids = {s["id"] for s in state["stakeholders"]}
    for key, allowed in (("affected_task_ids", task_ids), ("predecessor_task_ids", task_ids), ("stakeholder_ids", actor_ids), ("required_gates", set(state["gates"]))):
        values = request.setdefault(key, [])
        if not isinstance(values, list) or len(set(values)) != len(values) or not set(values).issubset(allowed):
            raise DomainError("Unknown or duplicate values in " + key + ".")
    if not request.get("predecessor_task_ids"):
        request["predecessor_task_ids"] = list(dict.fromkeys(p for tid in request["affected_task_ids"] for p in _find(state["tasks"], tid).get("predecessors", []) if p not in request["affected_task_ids"]))
    if set(request["predecessor_task_ids"]).intersection(request["affected_task_ids"]):
        raise DomainError("A corrective package cannot depend on the affected task it must enable.")
    acceptance = {"field_verified", "corrective_work", "final_inspection", "utility_operate", "commissioned"}
    if request["vendor_capability"] == "electrical_ct" and (acceptance.intersection(request["required_gates"]) or any(g.startswith("ops_scope_") for g in request["required_gates"])):
        raise DomainError("Corrective work cannot depend on the downstream verification or operating acceptance it is intended to enable.")
    if not request["affected_task_ids"]:
        raise DomainError("A reviewed request must identify an existing affected task.")
    if any(_find(state["tasks"], tid)["status"] == "completed" for tid in request["affected_task_ids"]):
        raise DomainError("Completed work cannot be silently rescheduled; open scoped rework first.")
    request["priority"] = int(_finite(request.get("priority", 70), "Priority", 0, 100))
    request["duration_hours"] = _finite(request.get("duration_hours", 4), "Package hours", .25, 80)
    qualification = vendors.CAPABILITIES[request["vendor_capability"]]["qualification"]
    request.setdefault("required_qualifications", [qualification])
    if not isinstance(request["required_qualifications"], list) or not set(request["required_qualifications"]).issubset({x["qualification"] for x in vendors.CAPABILITIES.values()}) or qualification not in request["required_qualifications"]:
        raise DomainError("Required qualification must match the trade scope.")
    minimum_gates = {"rigging": ["permit", "utility_install"], "electrical_ct": ["design", "permit", "utility_install", "customer_window"], "epc_interconnection": []}[request["vendor_capability"]]
    request["required_gates"] = list(dict.fromkeys(request["required_gates"] + [gid for gid in minimum_gates if gid in state["gates"]]))
    override = request.get("resource_override_task_id")
    if override and (request["vendor_capability"] != "rigging" or override not in request["affected_task_ids"]):
        raise DomainError("Resource replacement must name an affected rigging task.")
    request.setdefault("service_state", "MA")
    if request["service_state"] != "MA":
        raise DomainError("These demo projects currently support Massachusetts service scope.")
    if request.get("earliest_start"):
        engine._dt(request["earliest_start"])
    # Caller supplies a reviewed request, but cannot inject authority or ledger changes.
    allowed = {"title", "why", "request", "vendor_capability", "affected_task_ids", "predecessor_task_ids", "stakeholder_ids", "required_gates", "priority", "duration_hours", "required_qualifications", "service_state", "earliest_start", "scope_id", "kind", "resource_override_task_id", "additional_conditions"}
    return {key: value for key, value in request.items() if key in allowed}


def _new_case(state, request, message_id, identity=None):
    request = _validate_request(state, request)
    ops = state["operations"]
    scope_id = request.get("scope_id") or _hash({k: request[k] for k in ("vendor_capability", "affected_task_ids", "request")})[:16]
    old = next((c for c in ops["cases"] if c.get("scope_id") == scope_id and c["status"] != "resolved"), None)
    if old:
        if message_id not in old["source_message_ids"]:
            old["source_message_ids"].append(message_id)
        return old
    case = dict(request, id=identity or _next(ops, "cases"), scope_id=scope_id, status="sourcing", source_message_ids=[message_id],
        created_at=_now(state), project_id=state["project"]["id"], design_revision=state["project"].get("design_revision"), synthetic=True)
    ops["cases"].append(case)
    # A reported discrepancy creates an execution hold before procurement is approved.
    # Its missing planned work package keeps the gate closed until scoped work exists
    # and qualified completion evidence has been accepted by the responsible reviewer.
    hold_id = "ops_scope_" + case["id"]
    resolver = "engineer" if case["vendor_capability"] in ("electrical_ct", "epc_interconnection") else "epc"
    state["gates"][hold_id] = {"id": hold_id, "label": "Accept scoped additional work: " + case["title"],
        "status": "pending", "resolver_id": resolver, "issuer_id": None, "required_authority": hold_id,
        "evidence_ids": [], "design_revision": state["project"].get("design_revision"), "required_tasks": ["work-" + case["id"]],
        "required_artifact": "Qualified scoped completion evidence and responsible-party acceptance; inquiry or booking is insufficient.", "synthetic": True}
    _find(state["stakeholders"], resolver)["can_approve"].append(hold_id)
    case["scope_hold_gate_id"] = hold_id
    for tid in case["affected_task_ids"]:
        task = _find(state["tasks"], tid)
        task.setdefault("required_gates", []).append(hold_id)
    state["alerts"].append({"id": "alert-" + case["id"], "kind": "operations_case", "severity": "high" if case["priority"] >= 80 else "medium",
        "title": case["title"], "task_ids": case["affected_task_ids"], "evidence_ids": case["source_message_ids"], "gate_id": hold_id, "resolver_id": resolver, "resolved": False})
    return case


def _eligibility(profile, case, now, at=None):
    reasons = []
    if case["vendor_capability"] not in profile.get("capabilities", []):
        reasons.append("Does not cover the required trade scope.")
    if case.get("service_state", "MA") not in profile.get("service_states", []):
        reasons.append("Service geography does not cover this site.")
    for required in case["required_qualifications"]:
        records = [q for q in profile.get("qualifications", []) if q.get("code") == required and q.get("status") == "verified_demo"]
        if not any(q.get("expires_at") and engine._dt(q["expires_at"]) >= engine._dt(at or now) for q in records):
            reasons.append("Missing or expired scope qualification: " + required + ".")
    capacity = profile.get("capacity", {})
    if not capacity.get("battery_experience") or float(capacity.get("max_package_hours", 0)) < case["duration_hours"]:
        reasons.append("Recorded capacity does not cover this battery work package.")
    return reasons


def _profile_score(profile):
    perf = profile.get("performance", {})
    # Shrink small samples toward 80%, rather than reward a single perfect project.
    n = max(0, float(perf.get("completed_jobs", 0)))
    reliability = (float(perf.get("on_time_jobs", 0)) + 8) / (n + 10)
    rework = (float(perf.get("rework_jobs", 0)) + 1) / (n + 10)
    count = max(0, float(perf.get("rating_count", 0)))
    reputation = (float(perf.get("rating", 0)) * count + 4 * 5) / (count + 5) / 5
    return round(55 * reliability + 20 * (1 - rework) + 15 * reputation + 10 * min(n / 25, 1), 2)


def _inquire(state, case, profiles):
    ops = state["operations"]
    candidates = sorted((v for v in profiles if not _eligibility(v, case, _now(state))), key=lambda v: (-_profile_score(v), v["id"]))[:3]
    for vendor in candidates:
        existing = next((i for i in ops["inquiries"] if i["case_id"] == case["id"] and i["vendor_id"] == vendor["id"] and i.get("status") in ("pending", "replied") and i.get("design_revision") == state["project"].get("design_revision")), None)
        if existing:
            continue
        ops["inquiries"].append({"id": _next(ops, "inquiries"), "case_id": case["id"], "project_id": state["project"]["id"],
            "vendor_id": vendor["id"], "vendor_name": vendor["name"], "status": "pending", "sent_at": _now(state),
            "scope_id": case["scope_id"], "design_revision": state["project"].get("design_revision"), "delivery_mode": "simulated",
            "message": "Availability and scoped-price inquiry for " + state["project"]["name"] + ": " + case["request"] + " Confirm earliest start, duration, crew, exclusions and total incremental price. This is an inquiry, not a booking or authorization to perform work.",
            "simulated": True})
    case["status"] = "sourcing" if candidates else "clarification_required"


def _seed_request(state):
    pid = state["project"].get("demo_project_id")
    common = {"service_state": "MA"}
    if pid == "harbor_components":
        return dict(common, id="case-harbor-rigging", issuer_id="rigger", title="Find a rigging crew for the revised delivery", priority=92,
            subject="Nov 12 unload cannot meet the Nov 13 delivery estimate",
            text="Our original November 12 unloading crew cannot receive equipment arriving November 13. Please source a replacement mobilization for the current equipment schedule. The responsible rigger must review the equipment weight/centre of gravity, lift plan, ground support, access route and overhead/underground hazards with the EPC before accepting the job. The $4,800 baseline placement package stays contracted; please quote only the additional replacement mobilization and coordination. No crane is reserved by this message.",
            why="The November 13 equipment ETA is after the November 12 unloading slot. Placement must move; the later Saturday electrical window may also be needed.",
            request="Additional qualified rigging mobilization and site/lift-plan review, retaining the baseline placement scope. Quote all additional charges and credits; confirm equipment-specific lifting capability and site constraints.",
            vendor_capability="rigging", affected_task_ids=["t_unload"], predecessor_task_ids=["t_site", "t_procure"], stakeholder_ids=["rigger", "epc", "facilities", "vendor"],
            required_gates=["permit", "utility_install"], duration_hours=1, kind="rigging_recovery", resource_override_task_id="t_unload", earliest_start="2026-11-17T08:00:00-05:00",
            additional_conditions=["EPC and rigger must accept the equipment-specific lift plan, ground support and access/hazard survey.", "Physical receiving evidence remains required before unloading.", "Customer shutdown and electrician booking remain separate confirmations."])
    if pid == "millbrook_cold_storage":
        return dict(common, id="case-millbrook-utility", issuer_id="engineer", title="Resolve the utility application package discrepancy", priority=88,
            subject="EPC engineering support needed before utility submission",
            text="Our pre-submission check found that the draft equipment schedule and draft single-line use inconsistent inverter identifiers; the metering boundary is also unclear. Please obtain EPC/interconnection engineering support to reconcile the document register and prepare a controlled comment-response package for my review. The survey and issued design remain outstanding. This is preparation, not a utility rejection or accepted submission. The utility may later require study, witness testing or corrections; its turnaround is not promised by an engineering quote.",
            why="The application identifiers and metering boundary must agree before the responsible engineer issues the design and submits the utility package. Vendor availability cannot establish utility acceptance or operating permission.",
            request="Prepare a controlled equipment/application cross-check, resolve survey questions with the responsible engineer, and draft the utility submission comment register. Quote a two-engineer, eight-hour preparation package (16 person-hours) only; utility study fees and turnaround remain unknown.",
            vendor_capability="epc_interconnection", affected_task_ids=["t_design"], predecessor_task_ids=["t_survey"], stakeholder_ids=["epc", "engineer", "utility", "facilities"],
            required_gates=[], duration_hours=8, kind="utility_documents", earliest_start="2026-12-01T09:00:00-05:00",
            additional_conditions=["Responsible engineer must issue and accept the corrected design; the vendor draft is not design approval.", "Utility receipt, installation-stage requirements, witness testing and operating authorization stay separate.", "Utility review lead time and any study fees are unknown; no guaranteed authorization date is inferred."])
    if pid == "riverbend_logistics":
        return dict(common, id="case-riverbend-electrical", issuer_id="verifier", title="Approve qualified support for the CT discrepancy", priority=97,
            subject="Field verification hold: CT/metering identification differs from the issued drawing",
            text="The field CT/metering identification does not match the issued single-line. I cannot sign the field-verification record until the responsible engineer confirms the intended arrangement and a qualified electrical contractor supplies correction evidence. Please obtain two-person electrical support for the next customer-authorized access window and arrange independent reinspection. Do not infer wiring changes or settings from this report. The customer IT issue and utility operating acceptance also remain open.",
            why="The observed CT/metering discrepancy blocks qualified field verification and commissioning. A correction package and reinspection must precede downstream tests; network recovery alone cannot clear these gates.",
            request="Four-hour qualified electrical correction package under the responsible engineer's reviewed scope, followed by independent verifier reinspection. Include crew, mobilization and materials allowance in the incremental price; no engineering settings are prescribed by this system.",
            vendor_capability="electrical_ct", affected_task_ids=["t_verify"], predecessor_task_ids=["t_electrical"], stakeholder_ids=["electrician", "engineer", "verifier", "controls", "ops"],
            required_gates=["design", "permit", "utility_install", "customer_window"], duration_hours=4, kind="electrical_correction", earliest_start="2026-11-21T08:00:00-05:00",
            additional_conditions=["Responsible engineer must provide the scope; the assistant does not prescribe settings or field wiring.", "Qualified verifier separately records reinspection after corrected-work evidence.", "Network, utility operating permission and controls acceptance remain independent gates."])
    return None


def ensure(state):
    """Add the operations model once, retaining any existing world and its history."""
    result = engine._copy(state)
    ops = result.setdefault("operations", {"version": VERSION})
    for key in ("messages", "cases", "inquiries", "replies", "proposals", "decisions", "bookings", "audit"):
        ops.setdefault(key, [])
    if ops.get("initialized"):
        for booking in ops["bookings"]:
            generic = next((b for b in result["bookings"] if b["id"] == booking["id"]), None)
            if generic:
                booking.update(deepcopy(generic))
        for case in ops["cases"]:
            work = next((t for t in result["tasks"] if t["id"] == case.get("work_package_id")), None)
            if work and work["status"] == "completed" and all(_find(result["tasks"], tid)["status"] == "completed" for tid in case["affected_task_ids"]):
                case["status"] = "resolved"
                for alert in result["alerts"]:
                    if alert["id"] == "alert-" + case["id"]:
                        alert["resolved"] = True
            elif case.get("work_package_id"):
                relevant = [b for b in ops["bookings"] if b["case_id"] == case["id"]]
                if relevant and all(b["status"] == "confirmed" for b in relevant):
                    case["status"] = "awaiting_verification" if work and work["status"] == "completed" else "awaiting_work"
        return result
    ops["initialized"] = True
    request = _seed_request(result)
    if request and all(_find(result["tasks"], tid)["status"] != "completed" for tid in request["affected_task_ids"]):
        identity = request.pop("id")
        payload = {"message_id": "message-" + identity, "issuer_id": request.pop("issuer_id"), "subject": request.pop("subject"), "text": request.pop("text")}
        case = _new_case(result, request, payload["message_id"], identity)
        _message(result, payload, case["id"])
        _inquire(result, case, vendors.list_vendors())
    elif request:
        ops["seed_skipped_reason"] = "The relevant work has already completed in this saved project; no retrospective demo discrepancy or execution hold was added."
    return result


def _quote_for(ops, case, vendor_id):
    return next((r for r in reversed(ops["replies"]) if r["case_id"] == case["id"] and r["vendor_id"] == vendor_id), None)


def _reservation_conflicts(profile, start, end, project_id, case_id):
    if not start or not end:
        return []
    result = []
    for reservation in profile.get("reservations", []):
        if reservation.get("status") not in ("confirmed", "committed", "required", "pending"):
            continue
        if reservation.get("project_id") == project_id and reservation.get("case_id") == case_id:
            continue
        if reservation.get("start") and reservation.get("end") and engine._dt(start) < engine._dt(reservation["end"]) and engine._dt(reservation["start"]) < engine._dt(end):
            result.append("Vendor capacity conflicts with a reserved package in project " + str(reservation.get("project_id", "another project")) + ".")
    return result


def _option(state, case, vendor):
    quote = _quote_for(state["operations"], case, vendor["id"])
    reasons = _eligibility(vendor, case, _now(state), (quote or {}).get("available_until"))
    status = "not_contacted"
    inquiry = next((i for i in reversed(state["operations"]["inquiries"]) if i["case_id"] == case["id"] and i["vendor_id"] == vendor["id"]), None)
    if inquiry:
        status = "awaiting_reply"
    if quote:
        status = quote["availability"]
        reasons += _reservation_conflicts(vendor, quote.get("earliest_start"), quote.get("available_until"), state["project"]["id"], case["id"])
        if quote.get("project_id") != state["project"]["id"] or quote.get("scope_id") != case["scope_id"] or quote.get("design_revision") != state["project"].get("design_revision"):
            reasons.append("Reply does not cover the current project, scope and design revision.")
        if quote["availability"] != "available":
            reasons.append("Vendor has not confirmed available capacity for this scope.")
        if not quote.get("expires_at") or engine._dt(quote["expires_at"]) <= engine._dt(_now(state)):
            status = "expired"
            reasons.append("Availability and price quote expired; request a fresh reply.")
        if quote.get("total_price") is None or not quote.get("scope_complete"):
            reasons.append("A complete total incremental price and scope are not recorded.")
        if not quote.get("earliest_start") or engine._dt(quote["earliest_start"]) < engine._dt(_now(state)):
            reasons.append("Quoted work start has passed or is missing.")
        if not quote.get("capacity_confirmed"):
            reasons.append("Available crew capacity is not confirmed.")
    else:
        reasons.append("A scoped availability and price reply is required before proposing work.")
    if quote and not reasons and not case.get("work_package_id"):
        try:
            _build_plan(state, case, quote)
        except DomainError as error:
            reasons.append("Schedule is not currently feasible: " + str(error))
    score = _profile_score(vendor)
    ranking_reasons = ["Performance score is adjusted for the number of completed jobs and reference samples."]
    if quote and quote.get("total_price") is not None:
        # Deterministic, explainable tie-breaking; hard eligibility always wins first.
        price = float(quote["total_price"])
        days = max(0, (engine._dt(quote["earliest_start"]) - engine._dt(_now(state))).total_seconds() / 86400) if quote.get("earliest_start") else 90
        score = round(score * .7 + max(0, 15 - days * .3) + max(0, 15 - price / 500), 2)
        ranking_reasons += ["Earlier available start and lower total incremental quote increase the score."]
    return {"vendor_id": vendor["id"], "vendor_name": vendor["name"], "status": status, "eligible": not reasons,
        "exclusion_reasons": reasons, "ranking_score": score, "ranking_reasons": ranking_reasons,
        "earliest_start": (quote or {}).get("earliest_start"), "total_price": (quote or {}).get("total_price"),
        "duration_hours": (quote or {}).get("duration_hours"), "quote_id": (quote or {}).get("id"), "expires_at": (quote or {}).get("expires_at"),
        "performance": deepcopy(vendor.get("performance", {})), "qualifications": deepcopy(vendor.get("qualifications", [])),
        "capacity": deepcopy(vendor.get("capacity", {})), "scope": (quote or {}).get("scope"), "conditions": deepcopy((quote or {}).get("conditions", [])),
        "inquiry_id": (inquiry or {}).get("id"), "synthetic": True}


def _pending_conditions(state, case):
    conditions = list(case.get("additional_conditions", []))
    conditions.append("Downstream dates are conditional planning dates; each affected counterpart must separately confirm its appointment. Vendor availability cannot promise inspector or utility review timing.")
    for gid in case["required_gates"]:
        if not engine._gate_ready(state, gid):
            conditions.append("Execution hold: " + state["gates"][gid]["label"] + " is not yet accepted.")
    return conditions


def _next_window(state, task, earliest, resource_overrides=None):
    resources = list(resource_overrides if resource_overrides is not None else engine._resources(task))
    duration = timedelta(hours=float(task.get("duration_hours", 0)))
    if not resources:
        return earliest
    if any(not state["calendars"].get(resource) for resource in resources):
        raise DomainError("No known resource windows for " + task["title"] + "; obtain availability before proposing.")
    candidates = sorted({earliest} | {engine._dt(w["start"]) for resource in resources for w in state["calendars"][resource] if engine._dt(w["start"]) >= earliest})
    for candidate in candidates:
        if all(any(engine._dt(w["start"]) <= candidate and candidate + duration <= engine._dt(w["end"]) for w in state["calendars"][resource]) for resource in resources):
            return candidate
    raise DomainError("No confirmed available window fits " + task["title"] + "; request another option.")


def _build_plan(state, case, quote):
    """Insert a scoped package, then propagate only its dependent task dates."""
    plan = engine._copy(state)
    tasks = {t["id"]: t for t in plan["tasks"]}
    start = max(engine._dt(quote["earliest_start"]), engine._dt(_now(state)))
    for tid in case["predecessor_task_ids"]:
        parent = tasks[tid]
        start = max(start, engine._dt(parent["planned_start"]) + engine._duration(parent))
    if start != engine._dt(quote["earliest_start"]):
        raise DomainError("Quoted start precedes a prerequisite; obtain a revised scoped availability quote.")
    task_id = "work-" + case["id"]
    resource = "vendor:" + quote["vendor_id"]
    package = {"id": task_id, "title": case["request"].split(".")[0], "phase": "Design" if case["vendor_capability"] == "epc_interconnection" else "Construction",
        "phase_id": {"epc_interconnection": "site_design", "rigging": "installation", "electrical_ct": "verification"}[case["vendor_capability"]],
        "owner_id": quote["vendor_id"], "predecessors": list(case["predecessor_task_ids"]), "duration_hours": quote["duration_hours"],
        "planned_start": start.isoformat(), "resource": resource, "required_resources": ["customer_access"] if case["vendor_capability"] == "electrical_ct" else [],
        "required_gates": list(case["required_gates"]), "status": "planned", "evidence_ids": [], "external": True,
        "required_evidence_kind": "task_completion", "delivery_dependent": False, "operations_case_id": case["id"],
        "description": "Approved scoped additional work; requires qualified completion evidence and all independent execution gates. " + case["request"]}
    duration = timedelta(hours=quote["duration_hours"])
    slot_end = start + duration
    override_id = case.get("resource_override_task_id")
    if override_id:
        slot_end += engine._duration(tasks[override_id])
    if engine._dt(quote["available_until"]) < slot_end:
        raise DomainError("Vendor capacity window cannot cover the proposed work and placement scope.")
    plan["calendars"][resource] = [{"start": start.isoformat(), "end": engine._dt(quote["available_until"]).isoformat()}]
    if _next_window(plan, package, start) != start:
        raise DomainError("Vendor offer does not fit the recorded customer access window.")
    if task_id in tasks:
        raise DomainError("This case already has an authorized work package.")
    plan["tasks"].append(package)
    tasks[task_id] = package
    affected = {task_id}
    for tid in case["affected_task_ids"]:
        task = tasks[tid]
        if task.get("status") == "completed":
            raise DomainError("Affected work is now completed; obtain scoped rework review instead.")
        if task_id not in task["predecessors"]:
            task["predecessors"].append(task_id)
        if tid == override_id:
            task["resource"] = resource
            task["owner_id"] = quote["vendor_id"]
        affected.add(tid)
    for _ in range(len(tasks) + 1):
        previous = set(affected)
        affected.update(tid for tid, t in tasks.items() if set(t.get("predecessors", [])) & affected)
        if previous == affected:
            break
    # Topological iteration tolerates the original list order and detects cycles.
    pending = affected - {task_id}
    visited = {tid for tid in tasks if tid not in pending}
    for _ in range(len(tasks)):
        available = [tid for tid in pending if set(tasks[tid].get("predecessors", [])).issubset(visited)]
        if not available:
            break
        for tid in available:
            task = tasks[tid]
            if task.get("status") == "completed":
                raise DomainError("The new package affects completed downstream work; scoped rework is required first.")
            earliest = engine._dt(task["planned_start"])
            for parent_id in task.get("predecessors", []):
                parent = tasks[parent_id]
                earliest = max(earliest, engine._dt(parent["planned_start"]) + engine._duration(parent))
            if engine._delivery_task(task) and state["project"].get("delivery_eta"):
                earliest = max(earliest, engine._dt(state["project"]["delivery_eta"]))
            task["planned_start"] = _next_window(plan, task, earliest).isoformat()
            visited.add(tid)
            pending.remove(tid)
    if pending:
        raise DomainError("Dependency cycle or missing prerequisite in the proposed package.")
    errors = [e for e in engine._schedule_errors(plan) if e["task_id"] in affected]
    if errors:
        raise DomainError("Proposed package is infeasible: " + errors[0]["message"])
    changes = []
    for tid in affected - {task_id}:
        old, new = _find(state["tasks"], tid), tasks[tid]
        if old["planned_start"] != new["planned_start"] or old.get("resource") != new.get("resource") or old.get("predecessors") != new.get("predecessors"):
            changes.append({"task_id": tid, "title": new["title"], "before": old["planned_start"], "after": new["planned_start"],
                "before_resource": old.get("resource"), "after_resource": new.get("resource"), "predecessors": list(new["predecessors"]), "owner_id": new["owner_id"]})
    changes.sort(key=lambda c: (c["after"], c["task_id"]))
    return plan, package, changes


def _reply(state, inquiry, profile, raw):
    ops = state["operations"]
    identity = raw.get("reply_id") or "reply-" + inquiry["id"]
    old = next((r for r in ops["replies"] if r["id"] == identity), None)
    case = _find(ops["cases"], inquiry["case_id"], "case")
    if raw.get("project_id", state["project"]["id"]) != state["project"]["id"] or raw.get("scope_id", inquiry["scope_id"]) != inquiry["scope_id"] or raw.get("design_revision", inquiry["design_revision"]) != inquiry["design_revision"]:
        raise DomainError("Reply belongs to a different project, scope or design revision.")
    if raw.get("vendor_id", inquiry["vendor_id"]) != inquiry["vendor_id"] or raw.get("case_id", case["id"]) != case["id"]:
        raise DomainError("Reply vendor and case must match the inquiry.")
    if raw.get("currency", "USD") != "USD":
        raise DomainError("Quote currency must match the project USD ledger; currency conversion is not inferred.")
    for flag in ("capacity_confirmed", "scope_complete"):
        if flag in raw and not isinstance(raw[flag], bool):
            raise DomainError(flag + " must be an explicit boolean.")
    price = raw.get("total_price")
    if price is not None:
        price = _finite(price, "Total incremental price")
    availability = raw.get("availability", "unknown")
    if availability not in ("available", "unavailable", "needs_scope_review", "unknown"):
        raise DomainError("Unknown availability status.")
    duration = _finite(raw.get("duration_hours", case["duration_hours"]), "Quoted duration", case["duration_hours"], 160)
    for field in ("earliest_start", "available_until", "expires_at"):
        if raw.get(field):
            engine._dt(raw[field])
    if availability == "available" and (not raw.get("earliest_start") or not raw.get("available_until") or engine._dt(raw["available_until"]) <= engine._dt(raw["earliest_start"])):
        raise DomainError("An available reply needs a valid work window.")
    received = raw.get("received_at") or (old or {}).get("received_at") or _now(state)
    if engine._dt(received) > engine._dt(_now(state)):
        raise DomainError("A reply cannot be received in the future.")
    reply = {"id": identity, "case_id": case["id"], "project_id": state["project"]["id"], "inquiry_id": inquiry["id"], "vendor_id": inquiry["vendor_id"],
        "scope_id": inquiry["scope_id"], "design_revision": inquiry["design_revision"], "received_at": received, "availability": availability,
        "earliest_start": raw.get("earliest_start"), "available_until": raw.get("available_until"), "duration_hours": duration,
        "expires_at": raw.get("expires_at"), "total_price": price, "currency": "USD", "capacity_confirmed": bool(raw.get("capacity_confirmed")),
        "scope_complete": bool(raw.get("scope_complete")), "scope": raw.get("scope") or case["request"],
        "conditions": deepcopy(raw.get("conditions", case.get("additional_conditions", []))), "text": str(raw.get("text", "")), "synthetic": True}
    reply["content_hash"] = _hash(reply)
    if old:
        if old["content_hash"] != reply["content_hash"]:
            raise DomainError("Reply IDs are immutable; provide a new reply ID for changed availability or price.")
        return False
    if not reply["text"]:
        raise DomainError("Retain the original vendor reply text.")
    ops["replies"].append(reply)
    inquiry["status"] = "replied"
    inquiry["last_reply_id"] = reply["id"]
    _message(state, {"message_id": "message-" + reply["id"], "issuer_id": profile["id"], "subject": "Availability reply: " + case["title"], "text": reply["text"]}, case["id"])
    case["status"] = "options_ready" if availability == "available" else "sourcing"
    return True


def _simulate_replies(state, case, profiles):
    changed = False
    for inquiry in state["operations"]["inquiries"]:
        if inquiry["case_id"] != case["id"] or inquiry["status"] != "pending":
            continue
        profile = _find(profiles, inquiry["vendor_id"], "vendor")
        offer = profile.get("demo_response", {})
        offset = int(offer.get("offset", 0))
        start = engine._dt(case.get("earliest_start") or _now(state))
        if start <= engine._dt(_now(state)):
            start = engine._dt(_now(state)) + timedelta(days=2)
        if case["vendor_capability"] == "electrical_ct":
            windows = [w for w in state["calendars"].get("customer_access", []) if engine._dt(w["start"]) >= start]
            # Alternative 2 intentionally lacks customer access if no second offered window exists.
            start = engine._dt(windows[min(offset, len(windows)-1)]["start"]) if windows else start + timedelta(days=7 * offset)
        else:
            start += timedelta(days=2 * offset)
        duration = max(case["duration_hours"], offer.get("duration_hours", case["duration_hours"]))
        extra = 2 if case["vendor_capability"] == "rigging" else 0
        available_until = start + timedelta(hours=duration + extra)
        amount = offer.get("price")
        availability = offer.get("availability", "unknown")
        expires = min(start, engine._dt(_now(state)) + timedelta(days=3))
        text = ("Synthetic vendor response for %s. %s. Earliest offered start %s; package duration %s hours. " % (state["project"]["name"], "Crew available for the stated scope" if availability == "available" else "Need further scope review; capacity is not confirmed", start.isoformat(), duration))
        text += ("Total incremental fixed quote $%s USD, including crew, mobilization and stated allowance; no additional unpriced fees within this scope. " % amount if amount is not None else "Total price remains unknown; do not treat this as a zero-dollar offer. ")
        text += "Offer valid until %s. No booking, engineering acceptance or utility permission is established. %s" % (expires.isoformat(), " ".join(case.get("additional_conditions", [])))
        changed |= _reply(state, inquiry, profile, {"availability": availability, "earliest_start": start.isoformat(), "available_until": available_until.isoformat(),
            "duration_hours": duration, "expires_at": expires.isoformat(), "total_price": amount, "capacity_confirmed": availability == "available", "scope_complete": amount is not None, "text": text})
    return changed


def _proposal_hash(proposal):
    return _hash({k: v for k, v in proposal.items() if k not in ("content_hash", "status", "committed_at")})


def _assert_current(state, proposal, profiles):
    if _proposal_hash(proposal) != proposal["content_hash"]:
        raise DomainError("Proposal content changed; the exact approved package is immutable.")
    if proposal["based_on_revision"] != state["project"]["revision"] or proposal["design_revision"] != state["project"].get("design_revision"):
        raise DomainError("This proposal is stale; regenerate it against current project evidence and dates.")
    case = _find(state["operations"]["cases"], proposal["case_id"], "case")
    profile = _find(profiles, proposal["vendor_id"], "vendor")
    option = _option(state, case, profile)
    if not option["eligible"] or option["quote_id"] != proposal["quote_id"]:
        raise DomainError("Revalidate the vendor's current quote: " + "; ".join(option["exclusion_reasons"] or ["A newer reply supersedes the selected quote."]))
    quote = _find(state["operations"]["replies"], proposal["quote_id"], "quote")
    if quote["content_hash"] != _hash({k: v for k, v in quote.items() if k != "content_hash"}) or quote["total_price"] != proposal["cost_delta"]:
        raise DomainError("Quote content changed; request a new scoped reply and approval.")
    _, package, changes = _build_plan(state, case, quote)
    if _hash({"work_package": package, "schedule_changes": changes}) != proposal["plan_hash"]:
        raise DomainError("The proposed schedule or resource constraints changed; obtain a new exact approval.")
    approver, scope = engine._approver(state, proposal["cost_delta"])
    if (approver, scope) != (proposal["required_approver_id"], proposal["required_authority"]):
        raise DomainError("Delegated approval authority changed; obtain a fresh authorized decision.")
    return case, quote


def _commit(state, proposal, profiles):
    ops = state["operations"]
    if proposal["status"] == "committed":
        return
    if proposal["status"] != "approved":
        raise DomainError("Only an explicitly approved proposal can be committed.")
    case, quote = _assert_current(state, proposal, profiles)
    approval = next((d for d in reversed(ops["decisions"]) if d["proposal_id"] == proposal["id"] and d["status"] == "approved"), None)
    if not approval or approval["actor_id"] != proposal["required_approver_id"] or approval.get("proposal_hash") != proposal["content_hash"]:
        raise DomainError("No exact authorized approval record exists.")
    planned, package, changes = _build_plan(state, case, quote)
    state["tasks"] = planned["tasks"]
    state["calendars"] = planned["calendars"]
    profile = _find(profiles, quote["vendor_id"], "vendor")
    if not any(s["id"] == profile["id"] for s in state["stakeholders"]):
        state["stakeholders"].append({"id": profile["id"], "name": profile["name"], "role": vendors.CAPABILITIES[case["vendor_capability"]]["label"],
            "organization": profile["name"], "knows": [case["vendor_capability"]], "can_approve": ["booking", "task_completion"],
            "contact": profile["contact"], "project_ids": [state["project"]["id"]], "approval_limit": 0, "synthetic": True,
            "authority_source": "Authorized vendor scope only; no design, utility or customer-shutdown authority."})
    # Existing institutional and verification gates are not altered or marked approved.
    if case["vendor_capability"] == "electrical_ct" and "field_verified" in state["gates"]:
        gate = state["gates"]["field_verified"]
        gate.setdefault("required_tasks", [])
        if package["id"] not in gate["required_tasks"]:
            gate["required_tasks"].append(package["id"])
    budget = state["project"]["budget"]
    budget["committed"] = round(float(budget.get("committed", 0)) + proposal["cost_delta"], 2)
    ledger = state["project"].get("finance")
    if ledger is not None:
        ledger["lines"].append({"id": proposal["id"], "category": "Approved additional vendor work", "budget": 0, "baseline": 0,
            "committed": proposal["cost_delta"], "actual": 0, "forecast": proposal["cost_delta"], "task_ids": [package["id"]],
            "notes": "Authorized incremental scoped quote; no invoice or payment is inferred from approval."})
    booked_tasks = [package] + [_find(state["tasks"], c["task_id"]) for c in changes]
    for task in booked_tasks:
        for old in state["bookings"]:
            if old["task_id"] == task["id"] and old.get("status") != "superseded":
                old["status"] = "superseded"
                for operation_booking in ops["bookings"]:
                    if operation_booking["id"] == old["id"]:
                        operation_booking["status"] = "superseded"
        booking = {"id": _next(ops, "bookings"), "case_id": case["id"], "task_id": task["id"], "recipient_id": task["owner_id"],
            "planned_start": task["planned_start"], "start": task["planned_start"], "end": (engine._dt(task["planned_start"]) + engine._duration(task)).isoformat(),
            "vendor_id": task["owner_id"] if any(v["id"] == task["owner_id"] for v in profiles) else None,
            "status": "required", "proposal_id": proposal["id"], "simulated": True}
        ops["bookings"].append(booking)
        state["bookings"].append(deepcopy(booking))
    proposal["status"] = "committed"
    proposal["committed_at"] = _now(state)
    case["status"] = "awaiting_booking"
    case["work_package_id"] = package["id"]
    state["project"]["status"] = "active"
    engine._material(state)


def apply(state, payload, actor_id="pm", vendor_profiles=None):
    """Apply a validated PM operation. actor_id must come from the trusted route."""
    result = ensure(state)
    profiles = _profiles(vendor_profiles)
    result["_operation_vendors"] = profiles
    ops = result["operations"]
    payload = deepcopy(payload)
    kind = payload.get("type")
    case = _find(ops["cases"], payload.get("case_id"), "case") if payload.get("case_id") else None
    if kind == "ingest_message":
        request = payload.get("validated_request")
        if not case and request:
            case = _new_case(result, request, payload.get("message_id") or _next(ops, "messages"))
        before = len(ops["messages"])
        message = _message(result, payload, case["id"] if case else None)
        if case and message["id"] not in case["source_message_ids"]:
            case["source_message_ids"].append(message["id"])
        if case and not any(i["case_id"] == case["id"] for i in ops["inquiries"]):
            _inquire(result, case, profiles)
        if len(ops["messages"]) > before:
            engine._material(result)
    elif kind == "request_availability":
        if not case:
            raise DomainError("Select a decision case.")
        if case.get("work_package_id"):
            raise DomainError("This case already has an authorized package; use a separate change request.")
        for inquiry in ops["inquiries"]:
            quote = _quote_for(ops, case, inquiry["vendor_id"])
            if inquiry["case_id"] == case["id"] and (inquiry.get("design_revision") != result["project"].get("design_revision") or (quote and (not quote.get("expires_at") or engine._dt(quote["expires_at"]) <= engine._dt(_now(result))))):
                inquiry["status"] = "expired"
        _inquire(result, case, profiles)
    elif kind == "simulate_vendor_replies":
        changed = False
        for item in ([case] if case else ops["cases"]):
            changed |= _simulate_replies(result, item, profiles)
        if changed:
            engine._material(result)
    elif kind == "receive_vendor_reply":
        inquiry = _find(ops["inquiries"], payload.get("inquiry_id"), "inquiry")
        if actor_id != inquiry["vendor_id"]:
            raise DomainError("Only the queried vendor may supply its scoped reply.")
        profile = _find(profiles, inquiry["vendor_id"], "vendor")
        if _reply(result, inquiry, profile, payload):
            engine._material(result)
    elif kind == "propose_vendor":
        if not case or case.get("work_package_id"):
            raise DomainError("Choose an open case without an already committed package.")
        profile = _find(profiles, payload.get("vendor_id"), "vendor")
        option = _option(result, case, profile)
        if not option["eligible"]:
            raise DomainError("Vendor option is not eligible: " + "; ".join(option["exclusion_reasons"]))
        quote = _find(ops["replies"], option["quote_id"], "quote")
        _, package, changes = _build_plan(result, case, quote)
        approver, scope = engine._approver(result, quote["total_price"])
        if not approver:
            raise DomainError("No delegated approver covers this package cost.")
        existing = next((p for p in reversed(ops["proposals"]) if p["case_id"] == case["id"] and p["quote_id"] == quote["id"] and p["based_on_revision"] == result["project"]["revision"] and p["status"] in ("proposed", "pending", "approved")), None)
        if not existing:
            for old in ops["proposals"]:
                if old["case_id"] == case["id"] and old["status"] in ("proposed", "pending", "approved"):
                    old["status"] = "superseded"
            proposal = {"id": _next(ops, "proposals"), "case_id": case["id"], "vendor_id": profile["id"], "vendor_name": profile["name"], "quote_id": quote["id"],
                "project_id": result["project"]["id"], "design_revision": result["project"].get("design_revision"), "based_on_revision": result["project"]["revision"],
                "status": "proposed", "created_at": _now(result), "cost_delta": quote["total_price"], "budget_before": result["project"]["budget"]["committed"],
                "budget_after": round(result["project"]["budget"]["committed"] + quote["total_price"], 2), "work_package": package, "schedule_changes": changes,
                "required_approver_id": approver, "required_authority": scope, "conditions": _pending_conditions(result, case),
                "approval_meaning": "Authorize this exact scoped cost and conditional plan. Bookings, completion, inspections and utility permissions remain separate.",
                "evidence_ids": list(case["source_message_ids"]) + ["message-" + quote["id"]], "synthetic": True}
            proposal["plan_hash"] = _hash({"work_package": package, "schedule_changes": changes})
            proposal["content_hash"] = _proposal_hash(proposal)
            ops["proposals"].append(proposal)
        case["status"] = "decision_required"
    elif kind in ("request_approval", "approve_proposal", "approve_and_commit", "simulate_authority_response", "commit_proposal", "reject_proposal"):
        proposal = _find(ops["proposals"], payload.get("proposal_id"), "proposal")
        if case and proposal["case_id"] != case["id"]:
            raise DomainError("Proposal belongs to a different decision case.")
        case = _find(ops["cases"], proposal["case_id"], "case")
        if kind in ("commit_proposal", "approve_and_commit") and proposal["status"] == "committed":
            result.pop("_operation_vendors", None)
            return result
        _assert_current(result, proposal, profiles)
        if proposal["status"] in ("rejected", "committed", "superseded"):
            raise DomainError("This proposal is already closed.")
        if kind == "request_approval":
            proposal["status"] = "pending"
            case["status"] = "awaiting_approval"
            if not any(d["proposal_id"] == proposal["id"] and d["status"] == "requested" for d in ops["decisions"]):
                ops["decisions"].append({"id": _next(ops, "decisions"), "proposal_id": proposal["id"], "case_id": case["id"], "status": "requested",
                    "actor_id": actor_id, "recipient_id": proposal["required_approver_id"], "at": _now(result), "simulated": True})
        elif kind == "commit_proposal":
            _commit(result, proposal, profiles)
        else:
            if actor_id != proposal["required_approver_id"] or not engine._authorized(result, actor_id, proposal["required_authority"]):
                raise DomainError("This exact change requires approval by " + str(proposal["required_approver_id"]) + "; PM authority cannot be inferred or escalated by message text.")
            if kind == "simulate_authority_response" and payload.get("status", "approved") not in ("approved", "rejected"):
                raise DomainError("An authority response must explicitly approve or reject this proposal.")
            status = "rejected" if kind == "reject_proposal" or (kind == "simulate_authority_response" and payload.get("status") == "rejected") else "approved"
            if not any(d["proposal_id"] == proposal["id"] and d["status"] == status and d.get("proposal_hash") == proposal["content_hash"] for d in ops["decisions"]):
                ops["decisions"].append({"id": _next(ops, "decisions"), "proposal_id": proposal["id"], "case_id": case["id"], "status": status,
                    "actor_id": actor_id, "at": _now(result), "proposal_hash": proposal["content_hash"], "reason": str(payload.get("reason", "")), "simulated": True})
            proposal["status"] = status
            case["status"] = "clarification_required" if status == "rejected" else "approved_pending_commit"
            if kind == "approve_and_commit":
                _commit(result, proposal, profiles)
    elif kind == "request_clarification":
        if not case or not str(payload.get("text", "")).strip():
            raise DomainError("Choose a case and state the clarification needed.")
        case["status"] = "clarification_required"
        message = _message(result, {"message_id": payload.get("message_id"), "issuer_id": actor_id, "subject": "Clarification requested: " + case["title"], "text": payload["text"]}, case["id"])
        case.setdefault("clarification_message_ids", []).append(message["id"])
        for proposal in ops["proposals"]:
            if proposal["case_id"] == case["id"] and proposal["status"] in ("proposed", "pending", "approved"):
                proposal["status"] = "superseded"
    elif kind == "confirm_booking":
        booking = _find(ops["bookings"], payload.get("booking_id"), "booking")
        if case and booking["case_id"] != case["id"]:
            raise DomainError("Booking belongs to a different case.")
        if booking["status"] == "superseded":
            raise DomainError("This booking was superseded; confirm the current window instead.")
        if booking["status"] == "confirmed":
            result.pop("_operation_vendors", None)
            return result
        if actor_id != booking["recipient_id"]:
            raise DomainError("A booking must be explicitly confirmed by the named counterpart; PM approval is not a vendor confirmation.")
        task = _find(result["tasks"], booking["task_id"], "task")
        if task["planned_start"] != booking["planned_start"]:
            raise DomainError("The task moved; obtain a new booking confirmation.")
        profile = next((p for p in profiles if p["id"] == booking["recipient_id"]), None)
        if profile:
            finish = (engine._dt(task["planned_start"]) + engine._duration(task)).isoformat()
            case_for_booking = _find(ops["cases"], booking["case_id"], "case")
            errors = _eligibility(profile, case_for_booking, _now(result), finish) + _reservation_conflicts(profile, task["planned_start"], finish, result["project"]["id"], booking["case_id"])
            if errors:
                raise DomainError("Booking revalidation failed: " + "; ".join(errors))
        if engine._dt(task["planned_start"]) < engine._dt(_now(result)):
            raise DomainError("The booking start has passed; revise the work window.")
        booking.update(status="confirmed", confirmed_at=_now(result), confirmed_by=actor_id)
        for generic in result["bookings"]:
            if generic["id"] == booking["id"]:
                generic.update(deepcopy(booking))
        case = _find(ops["cases"], booking["case_id"], "case")
        if all(b["status"] == "confirmed" for b in ops["bookings"] if b["case_id"] == case["id"]):
            case["status"] = "awaiting_work"
    else:
        raise DomainError("Unknown operations action: " + str(kind))
    ops["audit"].append({"id": _next(ops, "audit"), "action": kind, "case_id": (case or {}).get("id"), "actor_id": actor_id, "at": _now(result), "simulated": True})
    result.pop("_operation_vendors", None)
    return result


def summarize(state, vendor_profiles=None):
    state = ensure(state)
    ops = state["operations"]
    profiles = _profiles(vendor_profiles)
    cases = []
    for raw in ops["cases"]:
        case = deepcopy(raw)
        options = [_option(state, case, p) for p in profiles if case["vendor_capability"] in p.get("capabilities", [])]
        options.sort(key=lambda x: (not x["eligible"], -x["ranking_score"], x["vendor_id"]))
        case["options"] = options
        case["inquiries"] = [deepcopy(i) for i in ops["inquiries"] if i["case_id"] == case["id"]]
        case["messages"] = [deepcopy(m) for m in ops["messages"] if m.get("case_id") == case["id"]]
        proposals = [deepcopy(p) for p in ops["proposals"] if p["case_id"] == case["id"]]
        for proposal in proposals:
            if proposal["status"] in ("proposed", "pending", "approved"):
                try:
                    _assert_current(state, proposal, profiles)
                except DomainError as error:
                    proposal["status"] = "stale"
                    proposal["stale_reason"] = str(error)
        case["current_proposal"] = proposals[-1] if proposals else None
        case["proposal_history"] = proposals
        case["bookings"] = [deepcopy(b) for b in ops["bookings"] if b["case_id"] == case["id"]]
        case["conditions"] = _pending_conditions(state, case)
        package = next((t for t in state["tasks"] if t["id"] == case.get("work_package_id")), None)
        if package and package["status"] == "completed":
            case["status"] = "awaiting_verification" if any(_find(state["tasks"], tid)["status"] != "completed" for tid in case["affected_task_ids"]) else "resolved"
        if not package and not case["current_proposal"] and any(o["eligible"] for o in options):
            case["status"] = "options_ready"
        if case["current_proposal"] and case["current_proposal"]["status"] == "stale":
            case["status"] = "refresh_required"
        cases.append(case)
    cases.sort(key=lambda c: (c["status"] == "resolved", -c["priority"], c["id"]))
    public_profiles = [{key: deepcopy(value) for key, value in p.items() if key != "demo_response"} for p in profiles]
    return {"version": VERSION, "messages": deepcopy(ops["messages"]), "cases": cases, "case_count": len(cases),
        "open_case_count": sum(c["status"] != "resolved" for c in cases), "vendors": public_profiles,
        "inquiries": deepcopy(ops["inquiries"]), "replies": deepcopy(ops["replies"]), "proposals": [p for c in cases for p in c["proposal_history"]],
        "bookings": deepcopy(ops["bookings"]), "decisions": deepcopy(ops["decisions"]), "simulated": True,
        "proposed_cost": sum(c["current_proposal"]["cost_delta"] for c in cases if c["current_proposal"] and c["current_proposal"]["status"] in ("proposed", "pending", "approved")),
        "notice": "All vendors, performance samples, messages and sends are fictional demo records. An availability reply is not a booking, engineering acceptance or utility operating permission."}
