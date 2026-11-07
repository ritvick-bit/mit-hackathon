"""Post-signing paperwork coordination, independent of the physical-work engine.

The twenty-document template and all seed records are illustrative. A completed
document is a coordination record, never permission to construct or operate.
No function makes an external request. Real provider adapters must verify events
before calling apply(..., trusted_provider=True); that flag is not an action field.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from email.utils import parseaddr
import hashlib
import json

from engine import DomainError
from projects import list_projects as delivery_project_catalog
from compliance import review as compliance_review, requirement_definition
from client_reference import calibration_reference


NOW = "2026-11-07T10:00:00-05:00"
SCHEMA_VERSION = 1
PMS = [{"id": "pm_jordan", "name": "Jordan Lee"}, {"id": "pm_casey", "name": "Casey Morgan"}]

# Id, title, kind, phase, owner role, required source/signer roles, prerequisites.
TEMPLATE = [
    ("D01", "Executed customer agreement", "record", "Kickoff", "pm", ["commercial"], []),
    ("D02", "Kickoff and responsibility review", "review", "Kickoff", "pm", ["epc", "facilities"], ["D01"]),
    ("D03", "Site-survey record", "record", "Engineering", "epc", ["engineer"], ["D02"]),
    ("D04", "Issued-design review", "review", "Engineering", "engineer", ["epc"], ["D03"]),
    ("D05", "Customer implementation acknowledgement", "esign", "Engineering", "pm", ["customer", "facilities"], ["D04"]),
    ("D06", "Permit submission record", "record", "Reviews and procurement", "engineer", ["engineer"], ["D04"]),
    ("D07", "Issued permit and fire-review records", "record", "Reviews and procurement", "pm", ["ahj", "fire"], ["D06"]),
    ("D08", "Utility application record", "record", "Reviews and procurement", "engineer", ["engineer"], ["D04"]),
    ("D09", "Utility comments disposition", "review", "Reviews and procurement", "engineer", ["utility"], ["D08"]),
    ("D10", "Installation-stage utility review record", "record", "Reviews and procurement", "pm", ["utility"], ["D09"]),
    ("D11", "Supplier order acceptance", "esign", "Reviews and procurement", "commercial", ["commercial", "supplier"], ["D04"]),
    ("D12", "EPC and electrical scope agreement", "esign", "Reviews and procurement", "pm", ["commercial", "epc", "electrician"], ["D04"]),
    ("D13", "Installation and lift-method review", "review", "Installation readiness", "epc", ["engineer", "rigger", "electrician"], ["D11", "D12"]),
    ("D14", "Change-control disposition", "review", "Installation readiness", "pm", ["commercial", "epc"], ["D12"]),
    ("D15", "Site-readiness and receiving packet", "record", "Installation readiness", "epc", ["facilities", "epc"], ["D07", "D10", "D13", "D14"]),
    ("D16", "Customer shutdown authorization", "esign", "Installation readiness", "pm", ["facilities", "customer"], ["D05", "D12"]),
    ("D17", "Field verification and correction record", "record", "Verification", "engineer", ["engineer", "electrician"], ["D15", "D16"]),
    ("D18", "Test and witness results review", "review", "Verification", "controls", ["engineer", "utility"], ["D17"]),
    ("D19", "Utility operating-acceptance record", "record", "Handoff", "pm", ["utility"], ["D18"]),
    ("D20", "Customer and fleet handoff acceptance", "esign", "Handoff", "pm", ["customer", "fleet"], ["D19"]),
]
ROLE_PROFILES = {
    "commercial": ("Morgan Chen", "Commercial approver", "EQORE"),
    "customer": ("Avery Brooks", "Customer signatory", "Customer"),
    "facilities": ("Taylor Reed", "Facilities and operations lead", "Customer"),
    "epc": ("Alex Rivera", "EPC project lead", "EPC partner"),
    "engineer": ("Sam Patel", "Responsible design engineer", "Engineering partner"),
    "electrician": ("Jamie Torres", "Electrical contractor", "Electrical partner"),
    "rigger": ("Drew Ellis", "Rigging supervisor", "Rigging partner"),
    "supplier": ("Cameron Park", "Equipment supplier", "Equipment supplier"),
    "ahj": ("Local permit records office", "AHJ record issuer", "Local authority"),
    "fire": ("Fire review records office", "Fire record issuer", "Fire authority"),
    "utility": ("Utility interconnection desk", "Utility record issuer", "Utility"),
    "controls": ("Robin Shaw", "Controls and commissioning lead", "EQORE"),
    "fleet": ("Quinn Carter", "Fleet operations lead", "EQORE"),
}
PROJECTS = [
    ("harbor_components", "Harbor Components", "Beverly, MA", "pm_jordan", 6, "returned"),
    ("millbrook_cold_storage", "Millbrook Cold Storage", "Lowell, MA", "pm_jordan", 3, "sent"),
    ("riverbend_logistics", "Riverbend Logistics", "Worcester, MA", "pm_jordan", 16, "sent"),
    ("cedar_foods", "Cedar Foods", "Nashua, NH", "pm_jordan", 4, "partial"),
    ("summit_precision", "Summit Precision", "Springfield, MA", "pm_jordan", 8, "returned"),
    ("maple_textiles", "Maple Textiles", "Fitchburg, MA", "pm_jordan", 10, "partial"),
    ("bayview_packaging", "Bayview Packaging", "Oakland, CA", "pm_jordan", 11, "draft"),
    ("granite_manufacturing", "Granite Manufacturing", "Manchester, NH", "pm_jordan", 1, "sent"),
    ("orchard_cold_chain", "Orchard Cold Chain", "Stockton, CA", "pm_casey", 12, "sent"),
    ("pine_assembly", "Pine Assembly", "Concord, NH", "pm_casey", 4, "declined"),
    ("canal_metals", "Canal Metals", "Lawrence, MA", "pm_jordan", 20, "archive"),
    ("sequoia_fabrication", "Sequoia Fabrication", "Fremont, CA", "pm_casey", 20, "archive"),
]
# Approximate city centres for map navigation, never surveyed deployment addresses.
CITY_ANCHORS = {
    "harbor_components": ("Beverly", "MA", 42.5584, -70.8800),
    "millbrook_cold_storage": ("Lowell", "MA", 42.6334, -71.3162),
    "riverbend_logistics": ("Worcester", "MA", 42.2626, -71.8023),
    "cedar_foods": ("Nashua", "NH", 42.7654, -71.4676),
    "summit_precision": ("Springfield", "MA", 42.1015, -72.5898),
    "maple_textiles": ("Fitchburg", "MA", 42.5834, -71.8023),
    "bayview_packaging": ("Oakland", "CA", 37.8044, -122.2712),
    "granite_manufacturing": ("Manchester", "NH", 42.9956, -71.4548),
    "orchard_cold_chain": ("Stockton", "CA", 37.9577, -121.2908),
    "pine_assembly": ("Concord", "NH", 43.2081, -71.5376),
    "canal_metals": ("Lawrence", "MA", 42.7070, -71.1631),
    "sequoia_fabrication": ("Fremont", "CA", 37.5485, -121.9886),
}

# Authored commercial briefs, not real customer records or engineering designs.
# Size, baseline and handoff for the three delivery cases are overlaid from their
# public catalog below, so paperwork cannot silently diverge from those fixtures.
_CASE_BRIEFS = {
    "harbor_components": {
        "industry": "Industrial component manufacturing", "system_power_kw": 250, "system_energy_kwh": 500,
        "scope": "Behind-the-meter battery, outdoor placement, electrical tie-in and operating handoff for a manufacturing site.",
        "contract_date": "2026-08-17", "target_handover_date": "2026-11-25", "project_budget_usd": 240000,
        "site_constraints": ["Production shutdown requires customer operations approval for Saturday 08:00–12:00.",
                             "Freight arrival and the rigging slot must be reconciled before equipment placement.",
                             "Permit acceptance and utility operating authorization remain separate records."]},
    "millbrook_cold_storage": {
        "industry": "Refrigerated warehousing and distribution", "system_power_kw": 500, "system_energy_kwh": 1000,
        "scope": "Battery and controls deployment for a refrigerated facility, including survey, design, protected tie-in and handoff.",
        "contract_date": "2026-10-26", "target_handover_date": "2027-02-12", "project_budget_usd": 395000,
        "site_constraints": ["Refrigeration continuity must be addressed in the customer-approved interruption plan.",
                             "Survey and issued-design questions must be resolved before institutional reviews.",
                             "Rigging availability and the Saturday electrical window require separate confirmations."]},
    "riverbend_logistics": {
        "industry": "Warehousing and logistics", "system_power_kw": 300, "system_energy_kwh": 600,
        "scope": "Installed battery project proceeding through independent field verification, controls testing and fleet handoff.",
        "contract_date": "2026-08-17", "target_handover_date": "2026-11-23", "project_budget_usd": 310000,
        "site_constraints": ["Customer IT owns the firewall and communications correction.",
                             "A network connection does not establish successful controls or meter testing.",
                             "Field verification, utility operating acceptance and customer training are separate handoff inputs."]},
    "cedar_foods": {
        "industry": "Food processing and packing", "system_power_kw": 200, "system_energy_kwh": 400,
        "scope": "Outdoor battery and site-metering integration to manage production and refrigeration demand peaks.",
        "contract_date": "2026-10-19", "target_handover_date": "2027-01-29", "project_budget_usd": 210000,
        "site_constraints": ["Customer and facilities leads must agree on the implementation scope.",
                             "Electrical interruption must fit a planned sanitation window.",
                             "Equipment delivery must preserve food-loading access and segregation from work areas."]},
    "summit_precision": {
        "industry": "Precision machining and metal components", "system_power_kw": 400, "system_energy_kwh": 800,
        "scope": "Battery installation with service tie-in, site metering, controls and demand-peak management for a machining plant.",
        "contract_date": "2026-09-14", "target_handover_date": "2027-01-15", "project_budget_usd": 355000,
        "site_constraints": ["The engineer must reconcile utility comments with the current issued drawing package.",
                             "Weekday machining production constrains tie-in and outage scheduling.",
                             "Service and CT locations require field confirmation before the electrical scope is finalized."]},
    "maple_textiles": {
        "industry": "Textile finishing and manufacturing", "system_power_kw": 300, "system_energy_kwh": 600,
        "scope": "Battery, electrical works and monitoring integration for production-line and process-load demand management.",
        "contract_date": "2026-09-01", "target_handover_date": "2027-01-08", "project_budget_usd": 280000,
        "site_constraints": ["Supplier acceptance must match the current equipment schedule and commercial terms.",
                             "Process-line cooldown and restart require a customer-controlled outage plan.",
                             "The installation route must preserve finished-goods loading access."]},
    "bayview_packaging": {
        "industry": "Packaging conversion and printing", "system_power_kw": 600, "system_energy_kwh": 1200,
        "scope": "Battery system, electrical distribution tie-in and controls integration for multiple packaging production lines.",
        "contract_date": "2026-08-31", "target_handover_date": "2027-01-22", "project_budget_usd": 515000,
        "site_constraints": ["EPC and electrical scope boundaries must be agreed before subcontract dispatch.",
                             "Rigging and truck access share a loading yard with daily shipments.",
                             "Weekend interruption must be coordinated across the affected production lines."]},
    "granite_manufacturing": {
        "industry": "General industrial manufacturing", "system_power_kw": 250, "system_energy_kwh": 500,
        "scope": "Post-signing battery deployment from site survey through design, procurement, installation and operating handoff.",
        "contract_date": "2026-11-02", "target_handover_date": "2027-03-05", "project_budget_usd": 245000,
        "site_constraints": ["Kickoff must confirm the facilities contact and responsibility split with the EPC.",
                             "The proposed outdoor equipment area requires a documented site survey.",
                             "Service data and operating hours are inputs to the design and interruption plan."]},
    "orchard_cold_chain": {
        "industry": "Cold-chain storage and distribution", "system_power_kw": 750, "system_energy_kwh": 1500,
        "scope": "Battery and controls deployment supporting a larger refrigerated distribution site's demand management.",
        "contract_date": "2026-08-24", "target_handover_date": "2027-01-15", "project_budget_usd": 595000,
        "site_constraints": ["The lift and installation method must be reviewed by the responsible trades.",
                             "Refrigeration continuity and product-temperature requirements constrain shutdowns.",
                             "Vehicle movements and rigging exclusion areas must be coordinated with dispatch operations."]},
    "pine_assembly": {
        "industry": "Electromechanical product assembly", "system_power_kw": 200, "system_energy_kwh": 400,
        "scope": "Battery, site-metering and controls installation for an assembly facility's production and test loads.",
        "contract_date": "2026-10-19", "target_handover_date": "2027-02-19", "project_budget_usd": 215000,
        "site_constraints": ["Implementation scope must be agreed with the customer before an acknowledgement is reissued.",
                             "Product test stations require an agreed shutdown and restart sequence.",
                             "Facilities access and contractor work areas must be confirmed before scheduling."]},
    "canal_metals": {
        "industry": "Metal finishing and fabrication", "system_power_kw": 400, "system_energy_kwh": 800,
        "scope": "Completed battery installation and customer/fleet handoff for a metal-processing facility.",
        "contract_date": "2026-06-15", "target_handover_date": "2026-11-06", "project_budget_usd": 365000,
        "site_constraints": ["The closeout packet retains the issued design and final verification records.",
                             "Customer operations owns future interruption and access planning.",
                             "Operating-acceptance and handoff records remain separately traceable in the archive."]},
    "sequoia_fabrication": {
        "industry": "Precision fabrication and assembly", "system_power_kw": 300, "system_energy_kwh": 600,
        "scope": "Completed behind-the-meter battery, metering and monitoring deployment with documented handoff.",
        "contract_date": "2026-06-29", "target_handover_date": "2026-11-06", "project_budget_usd": 285000,
        "site_constraints": ["The archive retains signed customer acceptance and fleet handoff records.",
                             "The delivered design and correction history remain available for maintenance planning.",
                             "Future changes require a new controlled scope and applicable authority review."]},
}


def project_profile(project):
    """Read-only enrichment for old snapshots; explicit saved fields always win."""
    result = {"industry": None, "system_power_kw": None, "system_energy_kwh": None,
              "scope": None, "contract_date": None, "target_handover_date": None,
              "delivery_model": "EQORE project management with EPC and trade subcontractors",
              "site_constraints": [], "utility": None, "project_budget_usd": None,
              "budget_basis": "Contract baseline; excludes later approved changes and is not spend to date."}
    result.update(deepcopy(_CASE_BRIEFS.get(project["id"], {})))
    refs = ["paperwork.py:_CASE_BRIEFS"]
    delivery = next((p for p in delivery_project_catalog() if p["id"] == project["id"]), None)
    if delivery:
        result.update(system_power_kw=delivery["system"]["power_kw"], system_energy_kwh=delivery["system"]["capacity_kwh"],
                      target_handover_date=delivery["target_handoff"], project_budget_usd=delivery["budget_baseline"])
        refs.append("projects.py:list_projects:" + project["id"])
    result["provenance"] = {"source_kind": "authored_case_brief", "source_refs": refs,
                            "note": "Authored project assumptions, not real client data. Delivery-case size, baseline and target dates are reused where available; utility service territories are unverified."}
    saved = project.get("profile")
    if isinstance(saved, dict):
        result["provenance"] = {"source_kind": "saved_profile_with_case_defaults",
                                "source_refs": ["saved_project.profile"] + refs,
                                "note": "Saved profile fields are preserved; missing fields use authored case assumptions."}
        result.update(deepcopy(saved))
    return result


def geography(project):
    row = CITY_ANCHORS.get(project["id"])
    if not row:
        return {"city": None, "state": None, "lat": None, "lng": None,
                "approximate": True, "source": "Location not recorded."}
    city, region, lat, lng = row
    return {"city": city, "state": region, "lat": lat, "lng": lng,
            "approximate": True, "source": "Illustrative city-centre map anchor; not a surveyed site address."}


EVENT_TYPES = {"recipient_signed", "recipient_declined", "envelope_completed", "review_accepted", "review_returned", "record_received", "record_returned"}
TERMINAL = {"completed", "returned", "declined", "voided"}


def _dt(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise DomainError("A valid timestamp with timezone is required.") from None
    if result.tzinfo is None:
        raise DomainError("A timestamp must include its timezone.")
    return result


def _text(value, label, maximum=40000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DomainError("%s must contain 1–%s characters." % (label, maximum))
    return value.strip()


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _pm(state, pm_id):
    pm = next((p for p in state["pms"] if p["id"] == pm_id), None)
    if not pm:
        raise DomainError("Select a recorded PM profile.")
    return pm


def _project(state, pm_id, project_id, writable=False):
    _pm(state, pm_id)
    project = state["projects"].get(project_id)
    if not project or project["pm_id"] != pm_id:
        raise DomainError("This project is not assigned to the selected PM.")
    if writable and project["status"] == "archived":
        raise DomainError("Archived projects are read-only.")
    return project


def _doc(project, doc_id):
    doc = next((d for d in project["documents"] if d["id"] == doc_id), None)
    if not doc:
        raise DomainError("Unknown document in this project.")
    return doc


def _stakeholder(project, actor_id):
    person = next((p for p in project["stakeholders"] if p["id"] == actor_id), None)
    if not person:
        raise DomainError("Unknown project stakeholder.")
    return person


def _audit(state, project, action, actor_id, text, doc=None, source_event_id=None, **extra):
    row = {"id": "%s-H%04d" % (project["id"], len(project["history"]) + 1),
           "at": state["now"], "type": action, "actor_id": actor_id, "text": text,
           "doc_id": doc["id"] if doc else None, "revision": doc["revision"] if doc else None,
           "source_event_id": source_event_id}
    row.update(extra)
    project["history"].append(row)
    project["last_activity"] = state["now"]
    project["version"] += 1
    return row


def _dependency_rows(project, doc, now=None, visiting=None):
    rows = []
    for identity in doc["prerequisite_ids"]:
        predecessor = _doc(project, identity)
        rows.append({"doc_id": identity, "title": predecessor["title"],
                     "required_revision": doc["dependency_revisions"].get(identity),
                     "current_revision": predecessor["revision"], "status": _status(project, predecessor, now, visiting)})
    for requirement_id in doc.get("prerequisite_requirement_ids", []):
        matches = [d for d in project["documents"] if d.get("requirement_id") == requirement_id]
        if len(matches) != 1:
            rows.append({"doc_id": "C_" + requirement_id, "title": requirement_definition(requirement_id)["title"],
                         "required_revision": None, "current_revision": None,
                         "status": "missing" if not matches else "ambiguous"})
        else:
            predecessor = matches[0]
            status = _status(project, predecessor, now, visiting)
            metadata = project.get("compliance_records", {}).get(requirement_id, {})
            if status == "completed":
                try:
                    reviewed_at = _dt(metadata.get("reviewed_at"))
                    completed_at = _dt((predecessor.get("completion_record") or {}).get("at"))
                    reviewed = (metadata.get("reviewed_document_revision") == predecessor["revision"]
                                and bool(metadata.get("reviewer_id")) and reviewed_at >= completed_at
                                and (not now or reviewed_at <= _dt(now))
                                and all(not metadata.get(key) or (now and _dt(metadata[key]) > _dt(now))
                                        for key in ("review_due_at", "expires_at"))
                                and (not metadata.get("changed_at") or _dt(metadata["changed_at"]) <= reviewed_at))
                except DomainError:
                    reviewed = False
                if not reviewed:
                    status = "review_due"
            rows.append({"doc_id": predecessor["id"], "title": predecessor["title"],
                         "required_revision": doc["dependency_revisions"].get(predecessor["id"]),
                         "current_revision": predecessor["revision"], "status": status})
    return rows


def _blockers(project, doc, now=None, visiting=None):
    blocked = []
    for row in _dependency_rows(project, doc, now, visiting):
        if row["status"] == "review_due":
            blocked.append("%s needs review of its current revision, review deadline and recorded site changes." % row["title"])
        elif row["status"] != "completed":
            blocked.append("%s must be completed for its current revision." % row["title"])
        required = row["required_revision"]
        if required is not None and required != row["current_revision"]:
            blocked.append("%s changed from revision %s to %s; revise and revalidate this document." % (
                row["title"], required, row["current_revision"]))
    return blocked


def _status(project, doc, now=None, visiting=None):
    visiting = frozenset(visiting or ())
    if doc["id"] in visiting:
        return "blocked"
    visiting = visiting | {doc["id"]}
    # Historical signatures are retained but cannot satisfy a changed dependency.
    if _blockers(project, doc, now, visiting):
        return "blocked"
    return doc["status"]


def _bind_dependencies(project, doc, now=None):
    visiting = None
    if _blockers(project, doc, now, visiting):
        raise DomainError("Complete current prerequisites and revise stale dependency bindings before sending.")
    doc["dependency_revisions"] = {row["doc_id"]: row["current_revision"] for row in _dependency_rows(project, doc, now, visiting)}


def _priority(state, project, doc):
    now = state["now"]
    status = _status(project, doc, now)
    if status == "completed":
        return 0
    overdue = max(0, (_dt(state["now"]) - _dt(doc["due_at"])).days)
    dependents = sum(doc["id"] in row["prerequisite_ids"] for row in project["documents"])
    base = {"declined": 85, "returned": 85, "partially_signed": 70, "sent": 55,
            "ready": 60, "draft": 60, "voided": 65, "blocked": 25}[status]
    return min(100, base + min(overdue, 8) * 3 + min(dependents, 4) * 3)


def _next_action(project, doc, now=None):
    status = _status(project, doc, now)
    if status == "blocked":
        return "Resolve prerequisites", "; ".join(_blockers(project, doc, now))
    if status in ("returned", "declined", "voided"):
        return "Revise %s" % doc["title"], "The current revision cannot complete; review the source response and issue a new revision."
    if status in ("sent", "partially_signed"):
        waiting = ", ".join(r["name"] for r in doc["recipients"] if r["status"] == "pending")
        return "Follow up on %s" % doc["title"], "Waiting for %s on revision %s." % (waiting or "verified provider envelope completion", doc["revision"])
    return "Prepare %s" % doc["title"], "Its current prerequisite records are complete; review the draft and recipient list."


def _allowed(project, doc, now=None):
    if project["status"] == "archived":
        return []
    status = _status(project, doc, now)
    actions = ["record_email", "draft_email"]
    if doc["status"] in ("ready", "draft") and doc["provider"] == "local_sample":
        actions.append("draft_document")
        if status != "blocked":
            actions.append("send_document")
    if doc["status"] not in ("ready", "draft") or status == "blocked" or doc["provider"] != "local_sample":
        if doc["provider"] == "local_sample" or doc["status"] in TERMINAL or doc["envelope_status"] == "created":
            actions.append("revise_document")
    if doc["status"] != "voided" and doc["provider"] == "local_sample":
        actions.append("void_document")
    if status in ("sent", "partially_signed") and doc["source_mode"] == "sample":
        actions.append("simulate_event")
    return actions


def _document_view(state, project, doc):
    now = state["now"]
    result = deepcopy(doc)
    result.update(status=_status(project, doc, now), lifecycle_status=doc["status"],
                  owner_name=_stakeholder(project, doc["owner_id"])["name"],
                  priority=_priority(state, project, doc), prerequisites=_dependency_rows(project, doc, now),
                  blockers=_blockers(project, doc, now), allowed_actions=_allowed(project, doc, now))
    title, reason = _next_action(project, doc, now)
    result["next_action"] = {"title": title, "reason": reason}
    result["draft_url"] = "/paperwork.html?project_id=%s&doc_id=%s&draft=1" % (project["id"], doc["id"])
    result["source_events"] = [deepcopy(e) for e in project["source_events"] if e.get("doc_id") == doc["id"]]
    result["signed_history"] = [deepcopy(e) for e in project["signed_history"] if e["doc_id"] == doc["id"]]
    result["sample_event_types"] = {"esign": ["recipient_signed", "recipient_declined"],
                                    "review": ["review_accepted", "review_returned"],
                                    "record": ["record_received", "record_returned"]}[doc["kind"]]
    return result


def _summary(state, project):
    documents = [_document_view(state, project, doc) for doc in project["documents"]]
    coverage = compliance_review(project, state["now"], documents)
    review_actions = _compliance_actions(project, documents, coverage)
    open_docs = [d for d in documents if d["status"] != "completed"]
    actionable = sorted([d for d in open_docs if d["status"] != "blocked"], key=lambda d: (-d["priority"], d["due_at"], d["id"]))
    next_doc = (actionable or sorted(open_docs, key=lambda d: (-d["priority"], d["id"])) or [None])[0]
    next_action = None
    if next_doc:
        next_action = dict(next_doc["next_action"], doc_id=next_doc["id"], owner_id=next_doc["owner_id"],
                           owner_name=next_doc["owner_name"], priority=next_doc["priority"], due_at=next_doc["due_at"],
                           status=next_doc["status"], kind=next_doc["kind"])
    if review_actions and (not next_action or review_actions[0]["priority"] > next_action["priority"]):
        next_action = deepcopy(review_actions[0])
    return {"id": project["id"], "name": project["name"], "pm_id": project["pm_id"], "status": project["status"],
            "site": project["site"], "geography": geography(project), "profile": project_profile(project),
            "compliance_counts": coverage["counts"], "compliance_followup_count": len(review_actions),
            "phase": next_doc["phase"] if next_doc else "Closeout complete",
            "completed_count": len(documents) - len(open_docs), "document_count": len(documents),
            "open_count": len(open_docs), "action_count": len(actionable) + len(review_actions),
            "overdue_count": sum(_dt(d["due_at"]) < _dt(state["now"]) for d in open_docs)
                             + sum(bool(a["due_at"]) and _dt(a["due_at"]) < _dt(state["now"]) for a in review_actions),
            "actionable_overdue_count": sum(_dt(d["due_at"]) < _dt(state["now"]) for d in actionable)
                                        + sum(bool(a["due_at"]) and _dt(a["due_at"]) < _dt(state["now"]) for a in review_actions),
            "blocked_overdue_count": sum(d["status"] == "blocked" and _dt(d["due_at"]) < _dt(state["now"]) for d in open_docs),
            "priority": next_action["priority"] if next_action else 0, "next_action": next_action,
            "last_activity": project["last_activity"], "version": project["version"],
            "paperwork_only": project["paperwork_only"], "archived_at": project.get("archived_at")}


def _compliance_actions(project, documents, coverage):
    """Keep a completed document's later review visible without undoing evidence."""
    completed = {d["id"]: d for d in documents if d["status"] == "completed"}
    actions = []
    for requirement in coverage["actions"]:
        identities = requirement["tracked_document_ids"]
        if len(identities) != 1 or identities[0] not in completed:
            continue
        doc = completed[identities[0]]
        review_dates = requirement.get("review", {})
        dates = []
        for key in ("review_due_at", "expires_at"):
            if review_dates.get(key):
                try:
                    dates.append(_dt(review_dates[key]))
                except DomainError:
                    pass
        review_due = min(dates).isoformat() if dates else None
        reviewer = _stakeholder(project, project["pm_id"])
        actions.append({"title": requirement["action_title"], "reason": requirement["reason"],
                        "doc_id": doc["id"], "doc_title": doc["title"], "requirement_id": requirement["id"],
                        "project_id": project["id"], "project_name": project["name"],
                        "owner_id": reviewer["id"], "owner_name": reviewer["name"],
                        "priority": requirement["priority"], "due_at": review_due,
                        "status": "review_due", "kind": doc["kind"], "view": "compliance"})
    return sorted(actions, key=lambda a: (-a["priority"], a["doc_id"]))


def _coverage_blocks_archive(coverage):
    return any(r["tracked_document_ids"] and r["status"] not in ("current_record", "upcoming")
               for r in coverage["requirements"])


def view(state, pm_id, project_id=None):
    """A PM can see only their own active projects, archive, originals and audit."""
    pm = deepcopy(_pm(state, pm_id))
    owned = [p for p in state["projects"].values() if p["pm_id"] == pm_id]
    summaries = [_summary(state, p) for p in owned]
    active = sorted([p for p in summaries if p["status"] == "active"], key=lambda p: (-p["priority"], p["name"]))
    archives = sorted([p for p in summaries if p["status"] == "archived"], key=lambda p: p["name"])
    selected = None
    if project_id is not None:
        project = _project(state, pm_id, project_id)
        selected = _summary(state, project)
        selected.update(documents=[_document_view(state, project, d) for d in project["documents"]],
                        stakeholders=deepcopy(project["stakeholders"]), history=deepcopy(project["history"]),
                        emails=deepcopy(project["emails"]), signed_history=deepcopy(project["signed_history"]),
                        closeout_attestation=deepcopy(project.get("closeout_attestation")),
                        can_archive=not selected["open_count"] and project["status"] != "archived",
                        source_events=deepcopy(project["source_events"]),
                        quarantine=[deepcopy(q) for q in state["quarantine"] if q["project_id"] == project_id])
        selected["action_summary"] = sorted(
            [dict(d["next_action"], doc_id=d["id"], priority=d["priority"], status=d["status"], kind=d["kind"],
                  due_at=d["due_at"], owner_id=d["owner_id"], owner_name=d["owner_name"])
             for d in selected["documents"] if d["status"] != "completed"], key=lambda a: (-a["priority"], a["doc_id"]))
        selected["compliance_review"] = compliance_review(project, state["now"], selected["documents"])
        selected["can_archive"] = selected["can_archive"] and not _coverage_blocks_archive(selected["compliance_review"])
        selected["action_summary"].extend(_compliance_actions(project, selected["documents"], selected["compliance_review"]))
        selected["action_summary"].sort(key=lambda a: (-a["priority"], a["doc_id"]))
    active_docs = [d for p in owned if p["status"] == "active" for d in p["documents"]]
    statuses = [_status(p, d, state["now"]) for p in owned if p["status"] == "active" for d in p["documents"]]
    action_queue = []
    for project in owned:
        if project["status"] != "active":
            continue
        projected_docs = []
        for doc in project["documents"]:
            projected = _document_view(state, project, doc)
            projected_docs.append(projected)
            if projected["status"] in ("completed", "blocked"):
                continue
            action_queue.append(dict(projected["next_action"], project_id=project["id"], project_name=project["name"],
                                     doc_id=doc["id"], doc_title=doc["title"], kind=doc["kind"], status=projected["status"],
                                     due_at=doc["due_at"], owner_id=doc["owner_id"], owner_name=projected["owner_name"],
                                     priority=projected["priority"]))
        action_queue.extend(_compliance_actions(project, projected_docs, compliance_review(project, state["now"], projected_docs)))
    action_queue.sort(key=lambda a: (-a["priority"], a["due_at"] or "9999", a["project_id"], a["doc_id"]))
    return {"schema_version": SCHEMA_VERSION, "pm": pm, "pms": deepcopy(state["pms"]), "now": state["now"],
            "projects": active, "archives": archives, "selected_project": selected, "action_queue": action_queue,
            "client_reference": calibration_reference(),
            "metrics": {"active_projects": len(active), "archived_projects": len(archives),
                        "open_documents": sum(p["open_count"] for p in active),
                        "actionable_documents": sum(p["action_count"] for p in active),
                        "overdue_documents": sum(p["overdue_count"] for p in active),
                        "ready_count": sum(s in ("ready", "draft") for s in statuses),
                        "awaiting_count": sum(s in ("sent", "partially_signed") for s in statuses),
                        "returned_count": sum(s in ("returned", "declined", "voided") for s in statuses),
                        "completed_count": statuses.count("completed"), "document_count": len(active_docs),
                        "project_count": len(active), "overdue_count": sum(p["overdue_count"] for p in active),
                        "actionable_overdue_count": sum(p["actionable_overdue_count"] for p in active),
                        "blocked_overdue_count": sum(p["blocked_overdue_count"] for p in active)},
            "provenance": "Illustrative post-signing coordination template and authored project records; not a verified EQORE SOP. Local sample events are distinct from provider-verified events.",
            "authority_boundary": "Document status does not grant engineering, construction or operating permission."}


def _quarantine(state, project, event, reason):
    fingerprint = _hash({"project_id": project["id"], "event": event, "reason": reason})
    if not any(q["fingerprint"] == fingerprint for q in state["quarantine"]):
        state["quarantine"].append({"id": "Q%05d" % (len(state["quarantine"]) + 1), "project_id": project["id"],
                                    "received_at": state["now"], "reason": reason, "event": deepcopy(event), "fingerprint": fingerprint})
        _audit(state, project, "event_quarantined", project["pm_id"], reason, source_event_id=event.get("id"))


def _receive(state, project, event):
    """Internal after transport trust check. Invalid external events are retained."""
    if not isinstance(event, dict):
        raise DomainError("A structured event is required.")
    event = deepcopy(event)
    identity = _text(event.get("id"), "Event ID", 160)
    fingerprint = _hash(event)
    previous = state["event_receipts"].get(identity)
    if previous:
        if previous["fingerprint"] != fingerprint:
            _quarantine(state, project, event, "Event ID was reused with different content.")
            return
        if previous["outcome"] == "applied":
            return
        # A fresh verified poll may resolve an out-of-order receipt. Revalidate
        # the identical event; never accept different content under its ID.
    reason = None
    doc = next((d for d in project["documents"] if d["id"] == event.get("doc_id")), None)
    if event.get("project_id") != project["id"]:
        reason = "Event project does not match the selected project."
    elif not doc:
        reason = "Event references an unknown document."
    elif type(event.get("revision")) is not int or event["revision"] != doc["revision"]:
        reason = "Event does not match the current document revision."
    elif event.get("type") not in EVENT_TYPES:
        reason = "Unknown completion event type."
    elif event.get("source_mode") != doc["source_mode"]:
        reason = "Sample and provider evidence cannot be mixed for this revision."
    elif event.get("envelope_id") != doc["envelope_id"] or not doc["envelope_id"]:
        reason = "Event does not match the current dispatch or envelope."
    elif _status(project, doc, state["now"]) == "blocked":
        reason = "The document has incomplete or stale prerequisite revisions."
    else:
        try:
            occurred = _dt(event.get("occurred_at"))
            if occurred > _dt(state["now"]):
                reason = "Future-dated event requires review."
            elif not doc.get("sent_at") or occurred < _dt(doc["sent_at"]):
                reason = "Event predates dispatch of this revision."
        except DomainError as error:
            reason = str(error)
    envelope_event = event.get("type") == "envelope_completed"
    recipient = next((r for r in (doc or {}).get("recipients", []) if r["id"] == event.get("actor_id")), None)
    if not reason and not recipient and not (envelope_event and event.get("actor_id") == doc["owner_id"]):
        reason = "Event actor is not a required recipient or recorded source for this document."
    if not reason and event["source_mode"] == "provider" and doc["kind"] == "esign":
        mapped_actor = doc["provider_recipient_map"].get(str(event.get("provider_recipient_id", "")))
        if (not envelope_event and mapped_actor != event.get("actor_id")) or event.get("source_kind") != "esign_webhook":
            reason = "Provider recipient mapping or verified event kind does not match."
    if not reason and doc["status"] in TERMINAL:
        # Repeated current success receipts are harmless; terminal contradictions are retained for review.
        successful = {"esign": "recipient_signed", "review": "review_accepted", "record": "record_received"}[doc["kind"]]
        if doc["status"] == "completed" and event["type"] in (successful, "envelope_completed"):
            if not envelope_event and recipient["status"] not in ("signed", "accepted", "received"):
                reason = "Completed document has an inconsistent recipient record."
        else:
            reason = "Event conflicts with a terminal revision; issue a new revision for rework."
    if not reason:
        allowed = {"esign": {"recipient_signed", "recipient_declined", "envelope_completed"},
                   "review": {"review_accepted", "review_returned"},
                   "record": {"record_received", "record_returned"}}[doc["kind"]]
        if event["type"] not in allowed:
            reason = "Event type is incompatible with this document kind."
        elif doc["status"] not in ("sent", "partially_signed", "completed"):
            reason = "This revision has not been dispatched."
        elif event["type"] in ("review_accepted", "record_received") and (
                event.get("source_kind") not in ("official_record", "sample_record") or not str(event.get("reference", "")).strip()):
            reason = "Review or record completion needs a source record reference; an email cue is insufficient."
        elif recipient and recipient.get("responded_at") and _dt(event["occurred_at"]) < _dt(recipient["responded_at"]):
            reason = "Event is older than the recipient's recorded response."
        elif event["type"] == "envelope_completed" and not all(r["status"] == "signed" for r in doc["recipients"]):
            reason = "Envelope completion cannot replace missing individual recipient signatures."
        elif event["type"] == "envelope_completed" and any(_dt(r["responded_at"]) > _dt(event["occurred_at"]) for r in doc["recipients"]):
            reason = "Envelope completion predates a required recipient signature."
    state["event_receipts"][identity] = {"fingerprint": fingerprint, "project_id": project["id"],
                                          "outcome": "quarantined" if reason else "applied"}
    if reason:
        _quarantine(state, project, event, reason)
        return
    for quarantined in state["quarantine"]:
        if (quarantined["project_id"] == project["id"] and _hash(quarantined["event"]) == fingerprint
                and not quarantined.get("resolved_at")):
            quarantined.update(resolved_at=state["now"], resolution="Validated on a fresh verified observation after prerequisites became available.")
    event["received_at"] = state["now"]
    project["source_events"].append(event)
    doc["source_event_ids"].append(identity)
    if doc["status"] == "completed":
        _audit(state, project, "duplicate_completion_observed", event["actor_id"],
               "Repeated successful receipt retained; original completion is unchanged.", doc, identity,
               source_mode=event["source_mode"])
        return
    old_status = doc["status"]
    kind = event["type"]
    if kind in ("recipient_declined", "review_returned", "record_returned"):
        recipient.update(status="declined" if kind == "recipient_declined" else "returned", responded_at=event["occurred_at"])
        doc["status"] = "declined" if kind == "recipient_declined" else "returned"
        doc["envelope_status"] = "declined" if doc["kind"] == "esign" else "returned"
        doc["return_reason"] = event.get("text", "Review source response before issuing a new revision.")
    elif kind != "envelope_completed":
        recipient_status = {"recipient_signed": "signed", "review_accepted": "accepted", "record_received": "received"}[kind]
        first_response = recipient["status"] != recipient_status
        if first_response:
            recipient.update(status=recipient_status, responded_at=event["occurred_at"], source_event_id=identity)
        if kind == "recipient_signed":
            if first_response:
                recipient["signed_at"] = event["occurred_at"]
                project["signed_history"].append({"project_id": project["id"], "doc_id": doc["id"], "title": doc["title"],
                                                   "revision": doc["revision"], "envelope_id": doc["envelope_id"],
                                                   "recipient_id": recipient["id"], "recipient_name": recipient["name"],
                                                   "recipient_email": recipient.get("email"),
                                                   "signed_at": event["occurred_at"], "source_event_id": identity,
                                                   "source_mode": event["source_mode"]})
        if all(r["status"] == recipient_status for r in doc["recipients"]) and not (doc["kind"] == "esign" and doc["source_mode"] == "provider"):
            doc.update(status="completed", completed_at=max((r["responded_at"] for r in doc["recipients"]), key=_dt), envelope_status="completed")
        elif doc["kind"] == "esign":
            doc.update(status="partially_signed", envelope_status="sent")
    else:
        doc.update(status="completed", completed_at=event["occurred_at"], envelope_status="completed")
    if old_status != "completed" and doc["status"] == "completed":
        doc["completion_record"] = {"revision": doc["revision"], "at": doc["completed_at"],
                                     "dependency_revisions": deepcopy(doc["dependency_revisions"]),
                                     "source_event_ids": list(doc["source_event_ids"]), "source_mode": doc["source_mode"]}
    _audit(state, project, kind, event["actor_id"], event.get("text", kind.replace("_", " ")),
           doc, identity, source_mode=event["source_mode"])


def _dispatch(state, project, doc, pm_id, provider="local_sample", envelope_id=None, recipient_map=None, sent_at=None):
    if doc["status"] not in ("ready", "draft"):
        raise DomainError("Only a ready or draft revision can be dispatched.")
    _bind_dependencies(project, doc, state["now"])
    if not doc["body"].strip():
        raise DomainError("Review a nonempty draft before dispatching.")
    previous_provider = doc["provider"]
    dispatch_time = sent_at or state["now"]
    if _dt(dispatch_time) > _dt(state["now"]):
        raise DomainError("Dispatch time cannot be in the future.")
    if provider != "local_sample" and _dt(dispatch_time) < _dt(doc["created_at"]):
        raise DomainError("Provider dispatch predates creation of this document revision.")
    doc.update(status="sent", sent_at=dispatch_time, envelope_status="sent", provider=provider,
               source_mode="sample" if provider == "local_sample" else "provider",
               envelope_id=envelope_id or "local:%s:%s:r%s" % (project["id"], doc["id"], doc["revision"]),
               provider_recipient_map=deepcopy(recipient_map or {}))
    if previous_provider == "local_sample":
        for recipient in doc["recipients"]:
            recipient["email"] = _stakeholder(project, recipient["id"])["email"]
    _audit(state, project, "document_dispatched", pm_id,
           "Local sample dispatch recorded; no external message sent." if provider == "local_sample" else "Verified provider envelope bound to this revision.", doc,
           source_mode=doc["source_mode"], envelope_id=doc["envelope_id"])


def _revise(state, project, doc, pm_id, action):
    if doc["provider"] != "local_sample" and doc["status"] not in TERMINAL and doc["envelope_status"] != "created":
        raise DomainError("Resolve or void the active provider envelope before issuing a new revision.")
    reason = _text(action.get("reason"), "Revision reason", 2000)
    snapshot = {key: deepcopy(value) for key, value in doc.items() if key != "revisions"}
    snapshot.update(superseded_at=state["now"], superseded_reason=reason)
    doc["revisions"].append(snapshot)
    doc["revision"] += 1
    body = action.get("body", doc["body"])
    if not isinstance(body, str) or len(body) > 40000:
        raise DomainError("Draft body must be text of at most 40,000 characters.")
    doc.update(body=body, status="draft" if body.strip() else "ready", envelope_id=None,
               envelope_status="created", provider="local_sample", source_mode="sample", provider_recipient_map={},
               dependency_revisions={}, source_event_ids=[], sent_at=None, completed_at=None, completion_record=None,
               return_reason=None, created_at=state["now"], email_draft=None, summary=None, provider_observations=[])
    for recipient in doc["recipients"]:
        recipient.update(status="pending", signed_at=None, responded_at=None, source_event_id=None)
    _audit(state, project, "document_revised", pm_id, reason, doc)


def apply(state, pm_id, action, *, trusted_provider=False, trusted_assist=False):
    """Copy-on-write actions; transport trust is an internal keyword, never JSON.

    Provider record_event and bind_provider_envelope calls are reserved for a
    verified server adapter. simulate_event creates conspicuously sample evidence.
    Archive additionally needs attest_project_complete=True and a closeout statement.
    """
    if not isinstance(action, dict):
        raise DomainError("A structured paperwork action is required.")
    result = deepcopy(state)
    project = _project(result, pm_id, action.get("project_id"), writable=True)
    kind = action.get("type")
    if kind in ("track_requirement", "set_requirement_review"):
        try:
            requirement = requirement_definition(action.get("requirement_id"))
        except (ValueError, KeyError, TypeError):
            raise DomainError("Choose a requirement from the EQORE document catalog.") from None
        requirement_id = requirement["id"]
        tracked = [d for d in project["documents"] if d.get("requirement_id") == requirement_id]
        if kind == "track_requirement":
            if tracked:
                raise DomainError("This requirement already has a tracked document. Open its current record.")
            due_at = action.get("due_at")
            _dt(due_at)
            def role_person(role):
                return _stakeholder(project, pm_id if role == "pm" else project["id"] + "__" + role)
            owner = role_person(requirement["owner_role"])
            recipients = []
            for role in requirement["recipient_roles"]:
                person = role_person(role)
                recipients.append({"id": person["id"], "name": person["name"], "role": person["role"],
                                   "status": "pending", "signed_at": None, "responded_at": None, "source_event_id": None})
            dependencies = list(requirement.get("prerequisite_ids", []))
            for identity in dependencies:
                _doc(project, identity)
            identity = "C_" + requirement_id
            if any(d["id"] == identity for d in project["documents"]):
                raise DomainError("A document already uses this requirement ID.")
            evidence = requirement.get("evidence_required", [])
            evidence_text = "\n".join("- " + str(item) for item in evidence) if isinstance(evidence, list) else str(evidence)
            body = ("%s — %s\n\nRequired record contents:\n%s\n\nTiming: %s\n\nUpdate trigger: %s\n\n"
                    "Confirm the site-specific scope and responsible issuer. This draft is not an issued approval or signed record.") % (
                        project["name"], requirement["title"], evidence_text, requirement.get("when", "Confirm with owner"),
                        requirement.get("update_trigger", "Confirm with owner"))
            document = {"id": identity, "requirement_id": requirement_id, "title": requirement["title"],
                        "kind": requirement["kind"], "phase": requirement["phase"], "owner_id": owner["id"],
                        "recipient_ids": [r["id"] for r in recipients], "recipients": recipients,
                        "prerequisite_ids": dependencies, "dependency_revisions": {}, "due_at": due_at,
                        "prerequisite_requirement_ids": deepcopy(requirement.get("prerequisite_requirement_ids", [])),
                        "status": "draft", "revision": 1, "revisions": [], "source_event_ids": [], "body": body,
                        "envelope_id": None, "envelope_status": "created", "provider": "local_sample", "source_mode": "sample",
                        "provider_recipient_map": {}, "created_at": result["now"], "sent_at": None, "completed_at": None,
                        "completion_record": None, "return_reason": None, "email_draft": None, "summary": None,
                        "provider_observations": [], "requirement_source_refs": deepcopy(requirement.get("source_refs", [])),
                        "authority_effect": "Tracks the requested evidence only; an actual issuer record and review are required.",
                        "template_note": "Based on EQORE's supplied documentation brief. Site applicability and adopted code edition require responsible review."}
            project["documents"].append(document)
            _audit(result, project, kind, pm_id, "Added requirement to the document register with a PM-selected due date; no request sent.", document,
                   requirement_id=requirement_id)
            return result
        if not tracked:
            raise DomainError("Track this requirement before scheduling its review or recording a change.")
        if len(tracked) != 1:
            raise DomainError("Resolve multiple current records before reviewing this requirement.")
        document = tracked[0]
        metadata = deepcopy(project.get("compliance_records", {}).get(requirement_id, {}))
        if "review_due_at" in action:
            if action["review_due_at"] is not None:
                _dt(action["review_due_at"])
            metadata["review_due_at"] = action["review_due_at"]
        if "changed_at" in action:
            changed_at = _dt(action["changed_at"])
            if changed_at > _dt(result["now"]):
                raise DomainError("A recorded site change cannot be in the future.")
            if metadata.get("changed_at") and changed_at < _dt(metadata["changed_at"]):
                raise DomainError("A new change cannot replace a later recorded change.")
            metadata.update(changed_at=action["changed_at"], change_reason=_text(action.get("change_reason"), "Change reason", 2000))
        if action.get("attest_review") is True:
            if _status(project, document, result["now"]) != "completed" or not document.get("completion_record"):
                raise DomainError("Review requires a completed current record with its source evidence.")
            metadata.update(reviewed_at=result["now"], reviewer_id=pm_id, reviewed_document_revision=document["revision"],
                            review_note=_text(action.get("review_note"), "Review note", 2000))
        if metadata == project.get("compliance_records", {}).get(requirement_id, {}):
            raise DomainError("Enter a review date, a site change, or an explicit completed-record review.")
        project.setdefault("compliance_records", {})[requirement_id] = metadata
        _audit(result, project, kind, pm_id, "Document review metadata updated; signatures and issuer approvals are unchanged.", document,
               requirement_id=requirement_id, review_metadata=deepcopy(metadata))
        return result
    if kind == "configure_contact":
        person = _stakeholder(project, action.get("stakeholder_id"))
        address = _text(action.get("email"), "Contact email", 254)
        if address.count("@") != 1 or not all(address.split("@")) or any(c.isspace() or c in "<>,;\r\n" for c in address):
            raise DomainError("Enter a single valid contact email address.")
        old = person["email"]
        person["email"] = address
        _audit(result, project, kind, pm_id, "Contact address changed from %s to %s; historical originals and signatures are unchanged." % (old, address))
        return result
    if kind == "import_provider_email":
        if not trusted_provider:
            raise DomainError("Only an authenticated mailbox adapter may import provider email.")
        doc = _doc(project, action.get("doc_id"))
        provider = action.get("provider")
        if provider not in ("gmail", "outlook", "graph"):
            raise DomainError("Unknown email provider.")
        message_id = _text(action.get("provider_message_id"), "Provider message ID", 500)
        original_from = _text(action.get("from"), "Original sender", 1000)
        address = parseaddr(original_from)[1].casefold()
        matches = [person for person in project["stakeholders"] if person["email"].casefold() == address]
        matched_id = matches[0]["id"] if address and len(matches) == 1 else None
        body = action.get("text")
        if not isinstance(body, str) or len(body) > 200000:
            raise DomainError("Original email body must be text of at most 200,000 characters.")
        occurred_at = action.get("occurred_at", result["now"])
        _dt(occurred_at)
        email = {"id": "mail-" + _hash({"provider": provider, "message_id": message_id})[:24],
                 "project_id": project["id"], "doc_id": doc["id"], "document_revision": action.get("document_revision", doc["revision"]),
                 "sender_id": matched_id, "matched_stakeholder_id": matched_id, "original_from": original_from,
                 "sender_email": address, "sender_verified": False, "mailbox_retrieval_verified": True,
                 "subject": _text(action.get("subject"), "Original subject", 2000), "text": body,
                 "occurred_at": occurred_at, "source_mode": "provider", "provider": provider,
                 "provider_message_id": message_id, "needs_review": True,
                 "sender_match": "unique_configured_address" if matched_id else "ambiguous" if len(matches) > 1 else "unknown"}
        fingerprint = _hash(email)
        existing = next((e for e in project["emails"] if e["id"] == email["id"]), None)
        if existing:
            if existing["content_hash"] != fingerprint:
                raise DomainError("Provider message ID already records different original content or document linkage.")
            return result
        email["content_hash"] = fingerprint
        project["emails"].append(email)
        _audit(result, project, "provider_email_imported", matched_id or pm_id,
               "Original mailbox message retained for review; sender identity and completion are not inferred.", doc, email["id"])
        return result
    if kind == "archive_project":
        if any(_status(project, d, result["now"]) != "completed" for d in project["documents"]):
            raise DomainError("Complete all current paperwork and resolve stale dependencies before archiving.")
        projected = [_document_view(result, project, d) for d in project["documents"]]
        if _coverage_blocks_archive(compliance_review(project, result["now"], projected)):
            raise DomainError("Review current tracked requirement records and resolve overdue or changed records before archiving.")
        if action.get("attest_project_complete") is not True:
            raise DomainError("Explicit project-completion and closeout attestation is required.")
        statement = _text(action.get("attestation"), "Closeout attestation", 4000)
        project.update(status="archived", completed_at=result["now"], archived_at=result["now"],
                       closeout_attestation={"actor_id": pm_id, "at": result["now"], "text": statement, "project_complete": True})
        _audit(result, project, kind, pm_id, statement)
        return result
    if kind == "record_email":
        identity = _text(action.get("event_id"), "Email event ID", 160)
        _stakeholder(project, action.get("sender_id"))
        if action.get("doc_id"):
            _doc(project, action["doc_id"])
        email = {"id": identity, "project_id": project["id"], "doc_id": action.get("doc_id"),
                 "sender_id": action["sender_id"], "subject": _text(action.get("subject"), "Subject", 250),
                 "text": _text(action.get("text"), "Original email"),
                 "occurred_at": action.get("occurred_at", result["now"]), "source_mode": "provider" if trusted_provider else "local_entry",
                 "sender_verified": False, "provider_message_id": action.get("provider_message_id") if trusted_provider else None}
        _dt(email["occurred_at"])
        existing = next((e for e in project["emails"] if e["id"] == identity), None)
        if existing:
            if existing["content_hash"] != _hash(email):
                raise DomainError("Email ID already records different original content.")
            return result
        email["content_hash"] = _hash(email)
        project["emails"].append(email)
        _audit(result, project, kind, email["sender_id"], "Original email recorded; document status is unchanged.",
               _doc(project, action["doc_id"]) if action.get("doc_id") else None, identity)
        return result
    if kind == "record_event":
        if not trusted_provider or (action.get("event") or {}).get("source_mode") != "provider":
            raise DomainError("Only a verified provider adapter may import provider completion events.")
        _receive(result, project, action.get("event"))
        return result
    doc = _doc(project, action.get("doc_id"))
    if kind == "save_summary":
        if not trusted_assist:
            raise DomainError("Only the server's reviewed model-result path may save a live summary.")
        known_sources = {e["id"] for e in project["source_events"] if e.get("doc_id") == doc["id"]}
        known_sources.update(e["id"] for e in project["emails"] if e.get("doc_id") == doc["id"])
        source_ids = action.get("source_ids", [])
        uncertainties = action.get("uncertainties", [])
        if not isinstance(source_ids, list) or not all(isinstance(i, str) and i in known_sources for i in source_ids):
            raise DomainError("Summary references must identify originals for this document.")
        if not isinstance(uncertainties, list) or not all(isinstance(i, str) and len(i) <= 2000 for i in uncertainties):
            raise DomainError("Summary uncertainties must be short text statements.")
        doc["summary"] = {"text": _text(action.get("summary"), "Summary", 8000), "source_ids": list(dict.fromkeys(source_ids)),
                          "uncertainties": deepcopy(uncertainties), "mode": "live", "at": result["now"], "revision": doc["revision"]}
        _audit(result, project, kind, pm_id, "Live summary saved separately from original records; no document status changed.", doc)
    elif kind == "draft_email":
        recipients = [r for r in doc["recipients"] if r["status"] == "pending"] or doc["recipients"]
        token = "EQORE-%s-%s-r%s" % (project["id"], doc["id"], doc["revision"])
        subject = action.get("subject") or "[%s] %s — %s" % (token, project["name"], doc["title"])
        if token not in subject:
            subject = "[" + token + "] " + subject
        body = action.get("body") or ("Hello %s,\n\nPlease review %s for %s, revision %s. The requested response is due %s. "
                                       "Please send the required %s or identify the exact correction needed. "
                                       "A reply acknowledging receipt does not complete the document.\n\nThank you,\n%s" % (
                                           ", ".join(r["name"] for r in recipients), doc["title"], project["name"], doc["revision"],
                                           doc["due_at"], "signature" if doc["kind"] == "esign" else "source record and reference",
                                           _pm(result, pm_id)["name"]))
        doc["email_draft"] = {"to": [_stakeholder(project, r["id"])["email"] for r in recipients], "cc": [],
                              "subject": _text(subject, "Draft email subject", 500), "body": _text(body, "Draft email body"),
                              "mode": "prepared", "revision": doc["revision"], "at": result["now"], "match_token": token}
        _audit(result, project, kind, pm_id, "Follow-up email prepared for review; no email sent.", doc)
    elif kind == "draft_document":
        if doc["status"] not in ("ready", "draft"):
            raise DomainError("Create a new revision before editing a dispatched document.")
        if doc["provider"] != "local_sample":
            raise DomainError("Create a new revision before editing a provider-bound draft.")
        doc.update(body=_text(action.get("body"), "Draft body"), status="draft")
        _audit(result, project, kind, pm_id, "Draft prepared for PM review; no external message sent.", doc)
    elif kind == "send_document":
        if doc["provider"] != "local_sample":
            raise DomainError("A provider-bound draft must use its verified provider send path, never local sample dispatch.")
        _dispatch(result, project, doc, pm_id)
    elif kind == "bind_provider_envelope":
        if not trusted_provider:
            raise DomainError("Only a verified provider adapter may bind an external envelope.")
        if doc["kind"] != "esign" or action.get("provider") != "docusign":
            raise DomainError("DocuSign envelopes apply only to e-signature documents.")
        mapping = action.get("recipient_map")
        if not isinstance(mapping, dict) or set(mapping.values()) != {r["id"] for r in doc["recipients"]} or len(mapping) != len(doc["recipients"]):
            raise DomainError("Map every exact current recipient to one provider recipient ID.")
        if action.get("revision", doc["revision"]) != doc["revision"]:
            raise DomainError("External envelope mapping targets a stale revision.")
        envelope_id = _text(action.get("envelope_id"), "Envelope ID", 160)
        for existing_project in result["projects"].values():
            for existing_doc in existing_project["documents"]:
                for existing_revision in [existing_doc] + existing_doc["revisions"]:
                    same_revision = existing_project["id"] == project["id"] and existing_doc["id"] == doc["id"] and existing_revision["revision"] == doc["revision"]
                    if existing_revision.get("envelope_id") == envelope_id and not same_revision:
                        raise DomainError("This provider envelope is already mapped to another project, document or revision.")
        envelope_status = action.get("envelope_status", "created")
        if envelope_status not in ("created", "sent", "delivered"):
            raise DomainError("Import completion evidence separately; envelope binding is not a signature.")
        if doc["status"] not in ("ready", "draft"):
            raise DomainError("A dispatched revision cannot be rebound to a provider draft.")
        if doc["provider"] == "docusign" and doc["envelope_id"] != envelope_id:
            raise DomainError("This revision already has a different provider envelope.")
        _bind_dependencies(project, doc, result["now"])
        if envelope_status == "created":
            doc.update(status="draft", provider="docusign", source_mode="provider", envelope_id=envelope_id,
                       envelope_status="created", provider_recipient_map=deepcopy(mapping))
            for recipient in doc["recipients"]:
                recipient["email"] = _stakeholder(project, recipient["id"])["email"]
            _audit(result, project, kind, pm_id, "External draft envelope bound to this revision; it has not been sent.", doc)
        else:
            if not action.get("sent_at"):
                raise DomainError("Verified provider dispatch requires the provider's original sent timestamp.")
            _dispatch(result, project, doc, pm_id, "docusign", envelope_id, mapping, action["sent_at"])
    elif kind == "record_provider_dispatch":
        if not trusted_provider:
            raise DomainError("Only a verified provider adapter may record external dispatch.")
        if doc["provider"] != "docusign" or action.get("envelope_id") != doc["envelope_id"] or str(action.get("revision")) != str(doc["revision"]):
            raise DomainError("Dispatch does not match the exact current provider envelope and revision.")
        sent_at = action.get("sent_at")
        _dt(sent_at)
        if doc["sent_at"]:
            if _dt(doc["sent_at"]) != _dt(sent_at):
                raise DomainError("Provider dispatch timestamp conflicts with the recorded original.")
            return result
        _dispatch(result, project, doc, pm_id, "docusign", doc["envelope_id"], doc["provider_recipient_map"], sent_at)
    elif kind == "record_provider_observation":
        if not trusted_provider:
            raise DomainError("Only a verified provider adapter may record external observations.")
        observation = deepcopy(action.get("observation"))
        if not isinstance(observation, dict):
            raise DomainError("A structured provider observation is required.")
        if observation.get("project_id") != project["id"] or observation.get("document_id") != doc["id"] or str(observation.get("document_revision")) != str(doc["revision"]) or observation.get("envelope_id") != doc["envelope_id"]:
            raise DomainError("Provider observation does not match the exact current document mapping.")
        fingerprint = _hash({key: value for key, value in observation.items() if key not in ("observed_at", "recorded_at", "needs_review", "fingerprint")})
        if any(o.get("fingerprint") == fingerprint for o in doc.get("provider_observations", [])):
            return result
        observation.update(needs_review=True, source_mode="provider", recorded_at=result["now"])
        observation["fingerprint"] = fingerprint
        doc.setdefault("provider_observations", []).append(observation)
        _audit(result, project, kind, pm_id, "Provider status observed for review; no signature or acceptance inferred.", doc)
    elif kind == "revise_document":
        _revise(result, project, doc, pm_id, action)
    elif kind == "void_document":
        if doc["provider"] != "local_sample":
            raise DomainError("Void the real provider envelope through its verified adapter before revising locally.")
        if doc["status"] == "voided":
            raise DomainError("This revision is already voided.")
        reason = _text(action.get("reason"), "Void reason", 2000)
        doc.update(status="voided", envelope_status="voided", return_reason=reason)
        _audit(result, project, kind, pm_id, reason, doc)
    elif kind == "simulate_event":
        if doc["source_mode"] != "sample":
            raise DomainError("Sample events cannot complete a provider-managed revision.")
        recipient_id = action.get("recipient_id")
        if not recipient_id:
            recipient_id = next((r["id"] for r in doc["recipients"] if r["status"] == "pending"), doc["recipients"][0]["id"])
        event_kind = action.get("event_type")
        sample_text = action.get("text") or "Local sample: %s for %s." % (str(event_kind).replace("_", " "), doc["title"])
        event = {"id": action.get("event_id") or "%s-S%05d" % (project["id"], len(result["event_receipts"]) + 1),
                 "project_id": project["id"], "doc_id": doc["id"], "revision": doc["revision"],
                 "envelope_id": doc["envelope_id"], "type": event_kind, "actor_id": recipient_id,
                 "occurred_at": result["now"], "text": _text(sample_text, "Sample response", 4000),
                 "reference": "sample-record:%s:%s:r%s" % (project["id"], doc["id"], doc["revision"]),
                 "source_kind": "sample_esign" if doc["kind"] == "esign" else "sample_record", "source_mode": "sample"}
        _receive(result, project, event)
    else:
        raise DomainError("Unknown or unauthorized paperwork action.")
    return result


def seed():
    """Deterministic 8+2 active projects and two explicitly completed archives."""
    state = {"schema_version": SCHEMA_VERSION, "now": NOW, "pms": deepcopy(PMS),
             "projects": {}, "event_receipts": {}, "quarantine": []}
    for index, (identity, name, site, pm_id, completed, opening) in enumerate(PROJECTS):
        pm = next(p for p in PMS if p["id"] == pm_id)
        people = [{"id": pm_id, "name": pm["name"], "role": "Deployment PM", "organization": "EQORE", "email": pm_id + "@example.invalid"}]
        role_ids = {"pm": pm_id}
        for role, (person_name, label, organization) in ROLE_PROFILES.items():
            actor_id = identity + "__" + role
            role_ids[role] = actor_id
            people.append({"id": actor_id, "name": person_name, "role": label, "organization": organization,
                           "email": role + "@" + identity.replace("_", "-") + ".example.invalid"})
        project = {"id": identity, "name": name, "site": site, "pm_id": pm_id, "status": "active", "version": 1,
                   "paperwork_only": identity not in {"harbor_components", "millbrook_cold_storage", "riverbend_logistics"},
                   "stakeholders": people, "documents": [], "history": [], "emails": [], "signed_history": [], "source_events": [],
                   "last_activity": NOW, "closeout_attestation": None}
        for number, (doc_id, title, kind, phase, owner, recipient_roles, dependencies) in enumerate(TEMPLATE):
            due = _dt(NOW) + timedelta(days=(number - completed) * 3 - (index % 3), hours=4)
            recipients = []
            for role in recipient_roles:
                person = next(p for p in people if p["id"] == role_ids[role])
                recipients.append({"id": person["id"], "name": person["name"], "role": person["role"], "status": "pending",
                                   "signed_at": None, "responded_at": None, "source_event_id": None})
            project["documents"].append({"id": doc_id, "title": title, "kind": kind, "phase": phase,
                                         "owner_id": role_ids[owner], "recipient_ids": [r["id"] for r in recipients], "recipients": recipients,
                                         "prerequisite_ids": list(dependencies), "dependency_revisions": {}, "due_at": due.isoformat(),
                                         "status": "ready", "revision": 1, "revisions": [], "source_event_ids": [],
                                         "body": "For %s: coordinate %s against the current issued scope and listed prerequisite records. Confirm the responsible parties and exceptions before dispatch.\n\nIllustrative draft for review; no external delivery or engineering approval is implied." % (name, title.lower()),
                                         "envelope_id": None, "envelope_status": "created", "provider": "local_sample", "source_mode": "sample",
                                         "provider_recipient_map": {}, "created_at": (_dt(NOW) - timedelta(days=completed * 3 + 7)).isoformat(), "sent_at": None, "completed_at": None,
                                         "completion_record": None, "return_reason": None,
                                         "email_draft": None, "summary": None, "provider_observations": [],
                                         "authority_effect": "Coordinates the stated record only; does not grant construction, engineering or operating authority.",
                                         "template_note": "Illustrative post-signing requirement; site scope and the responsible authority determine actual required records."})
        state["projects"][identity] = project
        # Seed history is visibly sample evidence, never hidden future outcomes.
        for number in range(completed):
            doc = project["documents"][number]
            state["now"] = (_dt(NOW) - timedelta(days=(completed - number) * 3, hours=4)).isoformat()
            _dispatch(state, project, doc, pm_id)
            state["now"] = (_dt(state["now"]) + timedelta(hours=4)).isoformat()
            for recipient in doc["recipients"]:
                event_kind = {"esign": "recipient_signed", "review": "review_accepted", "record": "record_received"}[doc["kind"]]
                event = {"id": "%s-seed-%s-%s" % (identity, doc["id"], recipient["id"]), "project_id": identity,
                         "doc_id": doc["id"], "revision": 1, "envelope_id": doc["envelope_id"], "type": event_kind,
                         "actor_id": recipient["id"], "occurred_at": state["now"], "text": "Authored opening record: %s." % doc["title"],
                         "reference": "sample-opening:%s:%s" % (identity, doc["id"]), "source_mode": "sample",
                         "source_kind": "sample_esign" if doc["kind"] == "esign" else "sample_record"}
                _receive(state, project, event)
        state["now"] = NOW
        if completed < 20:
            doc = project["documents"][completed]
            if opening == "draft":
                doc["status"] = "draft"
            else:
                _dispatch(state, project, doc, pm_id)
                if opening in ("partial", "returned", "declined"):
                    event_kind = "recipient_signed" if opening == "partial" else (
                        "recipient_declined" if doc["kind"] == "esign" else "review_returned" if doc["kind"] == "review" else "record_returned")
                    event = {"id": identity + "-seed-response", "project_id": identity, "doc_id": doc["id"], "revision": 1,
                             "envelope_id": doc["envelope_id"], "type": event_kind, "actor_id": doc["recipients"][0]["id"],
                             "occurred_at": NOW, "text": "Please resolve the current drawing reference and scope clarification before reissuing." if opening != "partial" else "First recipient completed; the remaining recipient must still sign.",
                             "reference": "sample-opening-response:" + identity, "source_mode": "sample",
                             "source_kind": "sample_esign" if doc["kind"] == "esign" else "sample_record"}
                    _receive(state, project, event)
            email = {"id": identity + "-opening-email", "project_id": identity, "doc_id": doc["id"],
                     "sender_id": doc["recipients"][-1]["id"], "subject": "Follow-up: " + doc["title"],
                     "text": "We are reviewing the current package. Please keep the drawing revision and named recipients visible. This email is an update, not a signature or permission to proceed.",
                     "occurred_at": NOW, "source_mode": "sample", "sender_verified": False, "provider_message_id": None}
            email["content_hash"] = _hash(email)
            project["emails"].append(email)
            _audit(state, project, "email_received", email["sender_id"], "Original opening email received; no completion inferred.", doc, email["id"], source_mode="sample")
        else:
            project.update(status="archived", completed_at=NOW, archived_at=NOW,
                           closeout_attestation={"actor_id": pm_id, "at": NOW, "text": "Authored archive example: project delivery and closeout were completed, and no current paperwork remains open.", "project_complete": True, "source_mode": "sample"})
            _audit(state, project, "project_archived", pm_id, project["closeout_attestation"]["text"], source_mode="sample")
    return state
