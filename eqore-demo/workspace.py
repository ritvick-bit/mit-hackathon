"""Read-only PM views: shared sources for portfolio, agenda and cost presentation."""
from copy import deepcopy
from datetime import datetime, timedelta


def public(value):
    """Keep simulated future counterpart behavior out of product observations."""
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if k not in {"demo_response", "private_response"}}
    if isinstance(value, list):
        return [public(x) for x in value]
    return value


def operation_summary(view):
    cases = [{k: deepcopy(c.get(k)) for k in ("id", "title", "status", "priority", "why", "needs_pm_decision")}
             for c in view.get("cases", []) if c.get("status") not in ("closed", "completed", "resolved")]
    cases.sort(key=lambda c: float(c.get("priority") or 0), reverse=True)
    return {"cases": cases, "open_count": len(cases),
            "top_priority": cases[0]["priority"] if cases else 0,
            "top_title": cases[0]["title"] if cases else "No open vendor cases",
            "pending_inquiry_count": sum(i.get("status") in ("sent", "pending", "awaiting_reply")
                                          for i in view.get("inquiries", []))}


def finance(overview, state, operation_view=None):
    """Add independently scoped pending vendor packages once per current case."""
    result = deepcopy(overview)
    if operation_view is None:
        import operations
        operation_view = operations.summarize(state)
    # The domain view revalidates scope, expiry, qualifications, capacity and authority.
    pending = round(float(operation_view.get("proposed_cost", 0)), 2)
    value = result["finance"]
    value["vendor_proposed_change"] = pending
    value["proposed_change"] = round((value.get("proposed_change") or 0) + pending, 2)
    if value.get("committed_total") is not None:
        value["estimated_total"] = round(value["committed_total"] + value["proposed_change"], 2)
        if value.get("baseline_total") is not None:
            value["variance_to_baseline"] = round(value["estimated_total"] - value["baseline_total"], 2)
    value["note"] += " Independently scoped vendor proposals are included once per case; offered prices remain pending until approval."
    return result


def calendar(state, view):
    result = []
    people = {p["id"]: p.get("name", p["id"]) for p in state["stakeholders"]}
    bookings = state.get("bookings", [])
    operation_bookings = {b["id"]: b for b in view.get("bookings", [])}
    for task in state["tasks"]:
        start = task.get("planned_start")
        if not start:
            continue
        booking = next((b for b in reversed(bookings) if b.get("task_id") == task["id"] and b.get("status") != "superseded"), None)
        completed = task.get("status") == "completed"
        status = "completed" if completed else "confirmed" if booking and booking.get("status") == "confirmed" else "planned"
        try:
            end = (datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(hours=float(task.get("duration_hours", 0)))).isoformat()
        except (ValueError, TypeError):
            end = None
        operation_booking = operation_bookings.get((booking or {}).get("id"), {})
        result.append({"id": "task:" + task["id"], "title": task["title"], "start": start, "end": end,
                       "kind": "work_checkpoint", "status": status, "task_id": task["id"],
                       "case_id": operation_booking.get("case_id"), "booking_id": (booking or {}).get("id"),
                       "owner": people.get(task.get("owner_id"), task.get("owner_id")),
                       "confirmation": "Accepted completion evidence" if completed else "Counterpart booking confirmed" if status == "confirmed" else "Internal plan; not a confirmed site appointment"})
    for request in state.get("requests", []):
        if request.get("status") in {"pending", "sent", "open", "acknowledged"} and request.get("due_at"):
            result.append({"id": "request:" + request["id"], "title": request.get("request", request.get("purpose", "Response due")),
                           "start": request["due_at"], "kind": "response_deadline", "status": "due",
                           "owner": people.get(request.get("recipient_id"), request.get("recipient_id")),
                           "confirmation": "Response deadline; not an appointment"})
    for inquiry in view.get("inquiries", []):
        if inquiry.get("status") in {"sent", "pending", "awaiting_reply"} and inquiry.get("due_at"):
            result.append({"id": "inquiry:" + inquiry["id"], "title": "Vendor availability response due",
                           "start": inquiry["due_at"], "kind": "response_deadline", "status": "due",
                           "case_id": inquiry.get("case_id"), "owner": inquiry.get("vendor_id"),
                           "confirmation": "Simulated inquiry deadline"})
    for case in view.get("cases", []):
        if case.get("work_package_id") or case.get("status") in {"resolved", "closed"}:
            continue
        for option in case.get("options", []):
            if option.get("quote_id") and option.get("earliest_start"):
                start = option["earliest_start"]
                end = (datetime.fromisoformat(start) + timedelta(hours=float(option.get("duration_hours") or 0))).isoformat()
                result.append({"id": "offer:" + option["quote_id"], "title": "Offered: " + case["title"],
                               "start": start, "end": end, "kind": "vendor_offer",
                               "status": "offered" if option.get("eligible") else option.get("status", "unavailable"),
                               "case_id": case["id"], "owner": option.get("vendor_name"),
                               "confirmation": "Vendor offer only; not approved or booked. " + "; ".join(option.get("exclusion_reasons", []))})
    for appointment in state.get("appointments", []):
        result.append(dict(appointment, kind="appointment"))
    return sorted(result, key=lambda e: (e.get("start", ""), e["id"]))
