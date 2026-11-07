"""Project-scoped subcontract, logistics and readiness projections.

The command-center's useful resource and readiness views are derived here from
the PM engine's actual records. No separate crew pool, scheduler or seed catalog
is introduced. This module never mutates a snapshot or creates authority.
"""
from copy import deepcopy
from datetime import timedelta

import dashboard
import engine
import workspace


CITY_COORDINATES = {
    "harbor_components": ("Beverly", "MA", 42.5584, -70.8800),
    "millbrook_cold_storage": ("Lowell", "MA", 42.6334, -71.3162),
    "riverbend_logistics": ("Worcester", "MA", 42.2626, -71.8023),
}
SERVICE_OWNERS = {"engineer", "epc", "rigger", "electrician", "vendor", "verifier", "controls"}


def geography(state):
    """City-level map anchors, never a surveyed site location."""
    row = CITY_COORDINATES.get(state["project"].get("demo_project_id"))
    if not row:
        return {"city": None, "state": None, "lat": None, "lng": None,
                "approximate": True, "source": "Site coordinates not recorded."}
    city, region, lat, lng = row
    return {"city": city, "state": region, "lat": lat, "lng": lng,
            "approximate": True, "source": "Approximate city-centre map anchor; not a surveyed site address."}


def _end(start, hours):
    value = engine._dt(start)
    return (value + timedelta(hours=float(hours or 0))).isoformat() if value else None


def _bookings(state, task):
    return [b for b in state.get("bookings", []) if b.get("task_id") == task["id"] and
            b.get("status") != "superseded"]


def _booking_confirmed(state, task):
    rows = _bookings(state, task)
    # A leftover confirmation for an old date or counterpart is not a reservation.
    return bool(rows) and all(b.get("status") == "confirmed" and
                             b.get("planned_start", b.get("start")) == task.get("planned_start") and
                             b.get("recipient_id") == task.get("owner_id") for b in rows)


def _task_view(state, task):
    completed = task.get("status") == "completed"
    confirmed = _booking_confirmed(state, task)
    status = "completed" if completed else "booking_confirmed" if confirmed else "planned"
    resources = engine._resources(task)
    windows = [{"resource_id": resource, "windows": deepcopy(state.get("calendars", {}).get(resource, [])),
                "meaning": "Recorded availability; separate counterpart booking required."} for resource in resources]
    return {"id": task["id"], "title": task["title"], "start": task.get("planned_start"),
            "end": _end(task.get("planned_start"), task.get("duration_hours")),
            "duration_hours": task.get("duration_hours"), "completed_at": task.get("completed_at"),
            "status": status, "owner_id": task.get("owner_id"),
            "required_gates": [{"id": key, "label": state.get("gates", {}).get(key, {}).get("label", key),
                                "status": "accepted" if engine._gate_ready(state, key) else "waiting"}
                               for key in task.get("required_gates", [])],
            "resources": resources, "resource_windows": windows,
            "booking_ids": [b["id"] for b in _bookings(state, task)],
            "evidence_ids": list(task.get("evidence_ids", [])),
            "confirmation": "Recorded completion; current acceptance is checked separately." if completed else
                            "Named counterpart confirmed this work window." if confirmed else
                            "Planned work; no current counterpart booking is established."}


def _qualifications(profile, at):
    result = []
    for item in profile.get("qualifications", []):
        expiry = engine._dt(item.get("expires_at"))
        reference_time = engine._dt(at)
        valid = bool(expiry and reference_time and expiry >= reference_time and
                     item.get("status") in {"verified", "verified_demo"})
        result.append(dict(deepcopy(item), validity="current_record" if valid else "expired_or_unverified",
                           checked_at=at))
    return result


def _subcontracts(state, operation_view, profiles):
    people = {p["id"]: p for p in state.get("stakeholders", [])}
    vendors = {p["id"]: p for p in profiles}
    owners = SERVICE_OWNERS | set(vendors)
    groups = {}

    def group(owner):
        if owner not in groups:
            person, profile = people.get(owner, {}), vendors.get(owner, {})
            groups[owner] = {"id": "counterpart:" + owner, "owner_id": owner,
                "name": profile.get("name", person.get("name", owner)),
                "organization": profile.get("name", person.get("organization", "Not recorded")),
                "role": person.get("role", ", ".join(profile.get("specialties", [])) or "Project vendor"),
                "contact": profile.get("contact", person.get("contact")),
                "engagement": "Project-scoped external work", "tasks": [], "offers": [], "cost_lines": [],
                "performance": deepcopy(profile.get("performance", {})),
                "qualifications": [], "qualification_note": "No reviewed vendor credential profile is attached." if not profile else
                    "Directory records; project scope, expiry and availability are checked separately."}
        return groups[owner]

    for task in state["tasks"]:
        if task.get("owner_id") in owners:
            group(task["owner_id"])["tasks"].append(_task_view(state, task))
    for case in operation_view.get("cases", []):
        if case.get("work_package_id") or case.get("status") in {"closed", "completed", "resolved"}:
            continue
        for option in case.get("options", []):
            # Unknown directory vendors do not become engaged subcontractors.
            if option.get("quote_id"):
                group(option["vendor_id"])["offers"].append(dict(workspace.public(deepcopy(option)),
                                                                 case_id=case["id"], case_title=case["title"]))
    tasks_by_id = {t["id"]: t for t in state["tasks"]}
    # A takeover changes who executes a task, not the commercial recipient of
    # its original ledger allocation. Keep retained baseline scope unassigned
    # until a separate commercial record explicitly transfers that commitment.
    reassigned_tasks = {case["resource_override_task_id"] for case in state.get("operations", {}).get("cases", [])
                        if case.get("resource_override_task_id") and case.get("work_package_id")}
    for line in state["project"].get("finance", {}).get("lines", []):
        line_owners = {tasks_by_id.get(task_id, {}).get("owner_id") for task_id in line.get("task_ids", [])}
        commercial_owner_unknown = bool(reassigned_tasks.intersection(line.get("task_ids", [])))
        for owner in line_owners & set(groups):
            exclusive = line_owners == {owner} and not commercial_owner_unknown
            groups[owner]["cost_lines"].append(dict(deepcopy(line), allocation="exclusive" if exclusive else "shared",
                commercial_owner_status="unconfirmed_after_takeover" if commercial_owner_unknown else "task_allocation",
                allocation_note="Execution ownership changed; this retained project allocation has no recorded commercial transfer to the replacement vendor." if commercial_owner_unknown else
                                "Entire ledger line belongs to this counterpart's tasks." if exclusive else
                                "Shared project allocation; not a separate payable amount for each counterpart."))
    for owner, row in groups.items():
        tasks, offers = row["tasks"], row["offers"]
        row["task_count"] = len(tasks)
        row["completed_count"] = sum(t["status"] == "completed" for t in tasks)
        row["confirmed_count"] = sum(t["status"] == "booking_confirmed" for t in tasks)
        pending = [t for t in tasks if t["status"] != "completed"]
        row["status"] = ("completed" if tasks and not pending else
                         "booking_confirmed" if pending and all(t["status"] == "booking_confirmed" for t in pending) else
                         "planned" if tasks else "offered")
        current_ends = [t["end"] for t in pending if t.get("end")]
        service_at = max(current_ends + [state["project"]["now"]], key=engine._dt)
        row["qualifications"] = _qualifications(vendors.get(owner, {}), service_at)
        exclusive = [line for line in row["cost_lines"] if line["allocation"] == "exclusive"]
        row["committed_total"] = round(sum(float(line.get("committed", 0)) for line in exclusive), 2) if exclusive else None
        row["actual_total"] = round(sum(float(line["actual"]) for line in exclusive), 2) if exclusive and all(line.get("actual") is not None for line in exclusive) else None
        row["cost_note"] = "Totals include exclusively attributed ledger lines only; shared lines are shown separately. Offers are not commitments."
    return sorted(groups.values(), key=lambda row: (row["status"] == "completed", row["name"], row["owner_id"]))


def _readiness(state, subcontracts):
    tasks = {t["id"]: t for t in state["tasks"]}
    checks = []

    def gate_check(identity, label, gate_ids, task_ids, criteria, stage):
        exists = [g for g in gate_ids if g in state.get("gates", {})]
        accepted = bool(exists) and len(exists) == len(gate_ids) and all(engine._gate_ready(state, g) for g in gate_ids)
        outstanding = [state["gates"][g].get("label", g) for g in exists if not engine._gate_ready(state, g)]
        checks.append({"id": identity, "label": label, "status": "accepted" if accepted else "waiting",
            "criteria": criteria, "detail": "Current scoped acceptance is recorded." if accepted else
                "Awaiting: " + ("; ".join(outstanding) or "required project evidence"),
            "stage": stage, "gate_ids": list(gate_ids), "task_ids": [t for t in task_ids if t in tasks],
            "owner_id": state["gates"].get(gate_ids[0], {}).get("resolver_id"),
            "evidence_ids": list(dict.fromkeys(e for g in exists for e in state["gates"][g].get("evidence_ids", [])))})

    def task_check(identity, label, task_id, criteria, stage):
        task = tasks.get(task_id, {})
        done = task.get("status") == "completed"
        checks.append({"id": identity, "label": label, "status": "accepted" if done else "waiting",
            "criteria": criteria, "detail": "Completion is recorded by the responsible owner." if done else "Responsible-owner completion is still required.",
            "stage": stage, "gate_ids": [], "task_ids": [task_id], "owner_id": task.get("owner_id"),
            "evidence_ids": list(task.get("evidence_ids", []))})

    gate_check("design", "Issued design", ["design"], ["t_design"], "Current design revision accepted by its designated engineering authority.", "design")
    task_check("site", "Pad and access readiness", "t_site", "EPC completion record covers the modeled pad, route and site-readiness work.", "installation")
    task_check("equipment_order", "Equipment order and shipping record", "t_procure", "Supplier completion record covers the ordered configuration and shipping record; receipt is separate.", "procurement")
    gate_check("receipt", "Physical equipment receipt", ["delivery_receipt"], ["t_unload"], "Facilities accepts the actual delivered equipment; an ETA cannot satisfy receipt.", "installation")
    gate_check("permits", "Permit and fire acceptance", ["permit", "fire_review"], ["t_permit"], "Separate current permit and fire-review authority records are both accepted.", "installation")
    gate_check("utility_install", "Utility installation-stage review", ["utility_install"], ["t_utility"], "Current installation-stage utility acceptance; it does not grant operating authorization.", "installation")
    relevant = [task for task in state["tasks"] if task.get("status") != "completed" and
                (engine._resources(task) or _bookings(state, task))]
    waiting = [t for t in relevant if not _booking_confirmed(state, t)]
    resource_errors = [e for e in engine._schedule_errors(state) if e["kind"] in {"resource", "resource_unknown", "resource_conflict"}]
    expired = [row["name"] for row in subcontracts if any(t["status"] != "completed" for t in row["tasks"]) and
               any(q["validity"] != "current_record" for q in row["qualifications"])]
    checks.append({"id": "subcontracts", "label": "Subcontractor windows and bookings",
        "status": "accepted" if not waiting and not resource_errors and not expired else "waiting",
        "criteria": "Each outstanding resource-backed task has its own counterpart confirmation, full-window calendar fit, and any attached current credential records.",
        "detail": "; ".join(([str(len(waiting)) + " task booking(s) unconfirmed"] if waiting else []) +
                            [e["message"] for e in resource_errors] + (["Review qualifications: " + ", ".join(expired)] if expired else [])) or
                  "No outstanding booking or recorded resource conflict for this project's modeled work.",
        "stage": "installation", "gate_ids": [], "task_ids": [t["id"] for t in relevant], "owner_id": "pm", "evidence_ids": []})
    gate_check("shutdown", "Customer shutdown authorization", ["customer_window"], ["t_electrical"], "Customer operations authorizes the interruption; an available access window is insufficient.", "installation")
    gate_check("field", "Field correction and verification", ["corrective_work", "field_verified"], ["t_verify"], "Current correction acceptance and independent field verification are both accepted.", "verification")
    gate_check("final_inspection", "Final local inspection", ["final_inspection"], ["t_commission"], "Assigned local reviewer accepts the installed revision and required inspection scope.", "verification")
    gate_check("utility_operate", "Utility operating authorization", ["utility_operate"], ["t_commission"], "Current written operating acceptance from the utility authority; installer approval is insufficient.", "commissioning")
    gate_check("network", "Customer network readiness", ["network"], ["t_commission"], "Customer IT accepts the required project network route; functional testing remains separate.", "commissioning")
    gate_check("commissioned", "Operational commissioning acceptance", ["commissioned"], ["t_commission"], "Current scoped functional-test evidence is accepted by the controls owner.", "commissioning")
    gate_check("fleet", "Fleet and support acceptance", ["fleet_ready"], ["t_handoff"], "Current telemetry, documentation and support acceptance from the fleet owner.", "handoff")
    accepted = sum(check["status"] == "accepted" for check in checks)
    next_tasks = sorted((t for t in state["tasks"] if t.get("status") != "completed" and t.get("planned_start")),
                        key=lambda task: (engine._dt(task["planned_start"]), task["id"]))
    next_task = next_tasks[0] if next_tasks else {}
    return {"accepted_count": accepted, "total_count": len(checks), "waiting_count": len(checks) - accepted,
            "next_milestone": {"task_id": next_task.get("id"), "label": next_task.get("title"), "planned_start": next_task.get("planned_start")},
            "checks": checks, "meaning": "Accepted criteria across project stages, not a critical-path score or dispatch authorization. Later-stage requirements may properly remain waiting."}


def _procurement(state, finance):
    tasks = {t["id"]: t for t in state["tasks"]}
    project = state["project"]
    order, unload, electrical = (tasks.get(key, {}) for key in ("t_procure", "t_unload", "t_electrical"))
    eta = project.get("delivery_eta")
    conflict = bool(eta and unload.get("planned_start") and unload.get("status") != "completed" and
                    engine._dt(eta) > engine._dt(unload["planned_start"]))
    received = engine._gate_ready(state, "delivery_receipt")
    receipt = state.get("gates", {}).get("delivery_receipt", {})
    shutdown = state.get("gates", {}).get("customer_window", {})
    sources = [e["id"] for e in state.get("evidence", []) if e.get("kind") == "delivery" and engine._valid_evidence(state, e, False)]
    return {"system": deepcopy(project.get("system", {})), "supplier_id": order.get("owner_id"),
        "order": {"task_id": order.get("id"), "status": "completed" if order.get("status") == "completed" else "planned",
                  "planned_start": order.get("planned_start"), "completed_at": order.get("completed_at"),
                  "evidence_ids": list(order.get("evidence_ids", [])), "purchase_order_id": None, "verified_lead_time_days": None},
        "delivery": {"eta": eta, "eta_effective_at": project.get("delivery_effective_at"), "eta_evidence_ids": sources,
            "receipt_status": "accepted" if received else "waiting", "receipt_evidence_ids": list(receipt.get("evidence_ids", [])),
            "unload_start": unload.get("planned_start"), "conflict": conflict,
            "detail": "Delivery estimate is after the planned unloading start; revise the schedule and counterpart bookings." if conflict else
                      "Physical receipt is accepted; placement remains its own task." if received else
                      "Delivery estimate supports planning. Physical receiving acceptance is still required."},
        "shutdown": {"status": "accepted" if engine._gate_ready(state, "customer_window") else "waiting",
            "planned_start": electrical.get("planned_start"), "end": _end(electrical.get("planned_start"), electrical.get("duration_hours")),
            "windows": deepcopy(state.get("calendars", {}).get("customer_access", [])),
            "evidence_ids": list(shutdown.get("evidence_ids", [])), "owner_id": shutdown.get("resolver_id"),
            "detail": "Recorded customer access windows do not themselves authorize a shutdown or confirm contractor attendance."},
        "cost_lines": [deepcopy(line) for line in finance["lines"] if "t_procure" in line.get("task_ids", [])],
        "unknowns": ["Purchase order number is not recorded.", "Verified manufacturer lead time is not recorded.",
                     "System size is the project equipment assumption; no serial-number inventory is recorded."]}


def view(state, operation_view, profiles):
    """Return a deterministic projection without modifying any input."""
    subcontracts = _subcontracts(state, operation_view, profiles)
    finance = workspace.finance({"finance": dashboard._finance(state)}, state, operation_view)["finance"]
    people = {p["id"]: p for p in state.get("stakeholders", [])}
    calendar = []
    for task in state["tasks"]:
        row = _task_view(state, task)
        if not row["start"]:
            continue
        case_id = task.get("operations_case_id") or next((booking.get("case_id") for booking in
            reversed(_bookings(state, task)) if booking.get("case_id")), None)
        calendar.append(dict(row, id="task:" + task["id"], task_id=task["id"], kind="work_checkpoint",
                             owner=people.get(task.get("owner_id"), {}).get("name", task.get("owner_id")), case_id=case_id))
    for counterpart in subcontracts:
        for offer in counterpart["offers"]:
            if offer.get("earliest_start"):
                calendar.append({"id": "offer:" + offer["quote_id"], "owner_id": counterpart["owner_id"], "owner": counterpart["name"],
                    "task_id": None, "case_id": offer["case_id"], "title": offer["case_title"], "start": offer["earliest_start"],
                    "end": _end(offer["earliest_start"], offer.get("duration_hours")), "status": "offered", "kind": "vendor_offer",
                    "eligible": offer.get("eligible", False), "resources": [], "confirmation": "Scoped offer only; no work is booked.",
                    "exclusion_reasons": deepcopy(offer.get("exclusion_reasons", []))})
    assigned = [t for row in subcontracts for t in row["tasks"]]
    metrics = {"subcontractor_count": sum(bool(row["tasks"]) for row in subcontracts),
               "open_work_packages": sum(t["status"] != "completed" for t in assigned),
               "confirmed_work_packages": sum(t["status"] == "booking_confirmed" for t in assigned),
               "offered_packages": sum(len(row["offers"]) for row in subcontracts),
               **{key: finance[key] for key in ("committed_total", "actual_total", "baseline_total", "proposed_change")}}
    return {"project_id": state["project"]["id"], "geography": geography(state), "subcontracts": subcontracts,
            "calendar": sorted(calendar, key=lambda row: (engine._dt(row["start"]), row["id"])),
            "procurement": _procurement(state, finance), "readiness": _readiness(state, subcontracts),
            "metrics": metrics, "note": "Each subcontractor is attached to this project's work. Availability calendars do not represent an in-house EQORE crew pool."}
