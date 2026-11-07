"""Whole-project synthetic demo worlds, separate from evaluation fixtures.

Each project has an observed opening state and a complete contract-to-handoff
workflow. Future events and counterpart policies are private simulator data.
Names, commercial amounts, site conditions and authority are invented demo
assumptions, not EQORE/customer records or engineering guidance.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import scenarios

VERSION = "3.0.0"

_PROFILES = {
    "harbor_components": {
        "id": "harbor_components", "project_id": "EQ-DEMO-HARBOR-01",
        "name": "Harbor Components", "customer": "Harbor Components (synthetic)",
        "site": "Beverly, Massachusetts · synthetic manufacturing site",
        "system": {"power_kw": 250, "capacity_kwh": 500},
        "phase": "Permits and delivery coordination",
        "description": "A manufacturing deployment with an observed supplier delay, permit acceptance still pending, and a Saturday shutdown requiring operations approval.",
        "target_handoff": "2026-11-25", "budget_baseline": 240000,
        "event_count": 5,
        "assumptions": [
            "Synthetic behind-the-meter battery deployment; equipment sizing is an illustrative commercial assumption, not an engineering design.",
            "Signed scope, survey, design and equipment order are recorded; local permit acceptance and customer shutdown authority remain outstanding.",
            "The known November 13 shipping estimate misses the original November 12 rigging slot; November 17 and 19 alternatives are offered.",
            "Electrical work requires both contractor availability and an operations-authorized Saturday 08:00–12:00 customer window.",
            "PM may approve up to $2,500 incremental cost in this synthetic delegation; larger changes go to the commercial approver.",
            "Permit and utility gates model separate authorities; public references do not establish actual site permission."
        ],
        "costs": [130000, 18000, 6000, 12000, 4800, 24000, 12000, 8000, 25200],
        "actual_fractions": [0.5, 1, 0.5, 0, 0, 0.2, 0, 0, 0],
        "labor": [
            {"role": "Electrical contractor", "crew_size": 2, "hours": 80, "hourly_rate": 150, "cost": 24000, "line_id": "electrical"},
            {"role": "Rigging crew", "crew_size": 3, "hours": 8, "hourly_rate": 200, "cost": 4800, "line_id": "rigging"},
            {"role": "Civil/site crew", "crew_size": 3, "hours": 40, "hourly_rate": 100, "cost": 12000, "line_id": "site"}
        ],
    },
    "millbrook_cold_storage": {
        "id": "millbrook_cold_storage", "project_id": "EQ-DEMO-MILLBROOK-02",
        "name": "Millbrook Cold Storage", "customer": "Millbrook Cold Storage (synthetic)",
        "site": "Lowell, Massachusetts · synthetic refrigerated distribution site",
        "system": {"power_kw": 500, "capacity_kwh": 1000},
        "phase": "Survey and design coordination",
        "description": "An early-stage project with a signed scope, unresolved survey/design and institutional reviews, a protected refrigeration shutdown, and a larger labor package.",
        "target_handoff": "2027-02-12", "budget_baseline": 395000,
        "event_count": 5,
        "assumptions": [
            "Synthetic refrigerated facility; this model does not prescribe backup, isolation, protection or battery safety design.",
            "The customer has signed the project scope; survey confirmation, design issue, permit review and utility installation review must still occur.",
            "Customer operations must authorize the interruption plan because refrigeration service is operationally sensitive.",
            "The working plan reserves February 2 or 4 rigging and February 6 or 13 Saturday electrical windows; availability is not external booking confirmation.",
            "The labor estimate includes preparation and installation; the four-hour calendar task represents only the customer tie-in window.",
            "Municipal and utility paths are synthetic case assumptions, not verified Lowell requirements or a verified service-territory assignment."
        ],
        "costs": [220000, 26000, 10000, 24000, 8000, 45000, 18000, 10000, 34000],
        "actual_fractions": [0.2, 0.2, 0, 0, 0, 0, 0, 0, 0],
        "labor": [
            {"role": "Electrical contractor", "crew_size": 3, "hours": 100, "hourly_rate": 150, "cost": 45000, "line_id": "electrical"},
            {"role": "Rigging crew", "crew_size": 4, "hours": 10, "hourly_rate": 200, "cost": 8000, "line_id": "rigging"},
            {"role": "Civil/site crew", "crew_size": 4, "hours": 60, "hourly_rate": 100, "cost": 24000, "line_id": "site"}
        ],
    },
    "riverbend_logistics": {
        "id": "riverbend_logistics", "project_id": "EQ-DEMO-RIVERBEND-03",
        "name": "Riverbend Logistics", "customer": "Riverbend Logistics (synthetic)",
        "site": "Worcester, Massachusetts · synthetic logistics warehouse",
        "system": {"power_kw": 300, "capacity_kwh": 600},
        "phase": "Verification and commissioning readiness",
        "description": "An installed project awaiting qualified verification, customer IT repair, utility operating acceptance and controls testing before fleet handoff.",
        "target_handoff": "2026-11-23", "budget_baseline": 310000,
        "event_count": 5,
        "assumptions": [
            "Synthetic project with recorded installation completion; physical work and all completion records are simulated.",
            "A customer firewall connectivity failure is already observed; customer IT owns the network fix and controls owns subsequent functional testing.",
            "Qualified field verification and utility operating acceptance are separate outstanding gates; a receipt cannot authorize operation.",
            "The target is November 23 handoff after November 18 verification and November 20 controls commissioning.",
            "Posted-to-date costs are illustrative invoices at the opening snapshot; task completion does not automatically manufacture new invoices.",
            "Municipal and utility paths are synthetic case assumptions, not verified Worcester requirements or a verified service-territory assignment."
        ],
        "costs": [175000, 22000, 8000, 18000, 6400, 30000, 16000, 9000, 25600],
        "actual_fractions": [1, 1, 1, 1, 1, 0.8, 0.25, 0, 0],
        "labor": [
            {"role": "Electrical contractor", "crew_size": 2, "hours": 100, "hourly_rate": 150, "cost": 30000, "line_id": "electrical"},
            {"role": "Rigging crew", "crew_size": 4, "hours": 8, "hourly_rate": 200, "cost": 6400, "line_id": "rigging"},
            {"role": "Civil/site crew", "crew_size": 3, "hours": 60, "hourly_rate": 100, "cost": 18000, "line_id": "site"}
        ],
    },
}

_CATEGORIES = [
    ("equipment", "Battery equipment, controls and electrical materials", ["t_procure"]),
    ("engineering", "Survey and engineering", ["t_survey", "t_design"]),
    ("reviews", "Permit and utility review allowance", ["t_permit", "t_utility"]),
    ("site", "Civil and site preparation", ["t_site"]),
    ("rigging", "Rigging and equipment placement", ["t_unload"]),
    ("electrical", "Electrical installation labor", ["t_electrical"]),
    ("commissioning", "Verification and commissioning", ["t_verify", "t_commission"]),
    ("handoff", "Monitoring setup and handoff", ["t_closeout_documents", "t_customer_training", "t_handoff"]),
    ("management", "Project management and contracted overhead", ["t_contract"]),
]


def list_projects():
    """Public catalog only; no future event content or oracle outcomes."""
    fields = ("id", "name", "description", "site", "system", "phase", "target_handoff", "budget_baseline", "event_count")
    return [dict({key: deepcopy(profile[key]) for key in fields}, synthetic=True, version=VERSION)
            for profile in _PROFILES.values()]


def _profile(project_id):
    try:
        return _PROFILES[project_id]
    except (KeyError, TypeError):
        raise ValueError("Unknown demo project: " + str(project_id)) from None


def _remap(value, profile):
    """Scope the reused fixture records and human-readable text to this site."""
    if isinstance(value, dict):
        return {key: _remap(item, profile) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap(item, profile) for item in value]
    if isinstance(value, str):
        return (value.replace(scenarios.PROJECT_ID, profile["project_id"])
                .replace("Harbor Components", profile["name"])
                .replace("Simulated Beverly authority", "Simulated local permitting office"))
    return value


def _pending(state, gate_id):
    gate = state["gates"][gate_id]
    old_ids = set(gate["evidence_ids"])
    gate.update(status="pending", issuer_id=None, evidence_ids=[])
    state["evidence"] = [item for item in state["evidence"] if item["id"] not in old_ids]


def _record(state, identity, title, body, issuer="pm", kind="record"):
    return scenarios._ev(identity, title, body, issuer, kind, state["project"]["now"],
                         state["project"]["design_revision"], state["project"]["id"])


def _window(day, hour, duration):
    start = datetime.fromisoformat(day + "T%02d:00:00" % hour).replace(tzinfo=ZoneInfo("America/New_York"))
    return {"start": start.isoformat(), "end": (start + timedelta(hours=duration)).isoformat()}


def _opening_tasks(state, done):
    """Discard completion claims for work that is pending at this opening."""
    discard = set()
    for task in state["tasks"]:
        if task["id"] not in done:
            discard.update(task.get("evidence_ids", []))
            task.update(status="planned", evidence_ids=[])
    state["evidence"] = [e for e in state["evidence"] if e["id"] not in discard and not (e["id"] == "SITE_READY" and "t_site" not in done)]


def _finance(state, profile):
    lines = []
    for (identity, category, tasks), amount, fraction in zip(_CATEGORIES, profile["costs"], profile["actual_fractions"]):
        lines.append({"id": identity, "category": category, "budget": amount, "baseline": amount,
                      "committed": amount, "actual": round(amount * fraction, 2), "forecast": amount,
                      "task_ids": tasks,
                      "notes": "Synthetic contracted allocation and posted-to-date invoice amount; not supplier pricing."})
    assert sum(line["budget"] for line in lines) == profile["budget_baseline"]
    state["project"]["finance"] = {
        "currency": "USD", "as_of": state["project"]["now"], "lines": lines,
        "note": "Synthetic opening ledger. Budget is the signed baseline; committed is contracted exposure, not money spent. Actuals are illustrative posted invoices as of this snapshot and do not change merely because work is marked complete. Approved later changes are added separately by the dashboard."
    }
    state["project"]["labor"] = [dict(deepcopy(row), assumption="Hours per crew member for the complete package, including preparation. Calendar task duration represents the site window only; rates and quantities are synthetic.")
                                   for row in profile["labor"]]


def _add_gate(state, identity, label, resolver, task_ids, required_tasks=(), required_gates=(), approved=False, artifact=""):
    person = next(p for p in state["stakeholders"] if p["id"] == resolver)
    if identity not in person["can_approve"]:
        person["can_approve"].append(identity)
    evidence = _record(state, "OPENING_" + identity.upper(), label, artifact, resolver, identity)
    state["gates"][identity] = {
        "id": identity, "label": label, "status": "approved" if approved else "pending",
        "issuer_id": resolver if approved else None, "resolver_id": resolver, "required_authority": identity,
        "evidence_ids": [evidence["id"]] if approved else [], "design_revision": state["project"]["design_revision"],
        "required_tasks": list(required_tasks), "required_gates": list(required_gates),
        "required_artifact": artifact, "source_ids": ["SRC_EQORE_PM"], "synthetic": True,
    }
    if approved:
        state["evidence"].append(evidence)
    for task in state["tasks"]:
        if task["id"] in task_ids:
            task["required_gates"].append(identity)


def _strengthen_world(state, profile):
    """Explicit work packages and scoped authority; technical values stay with qualified actors."""
    pid = profile["id"]
    project = state["project"]
    tasks = {t["id"]: t for t in state["tasks"]}
    project["source_ids"] = list(dict.fromkeys(project["source_ids"] + ["SRC_EQORE_FLEET", "SRC_EQORE_COST"]))
    project["assumptions"] += [
        "Public sources inform workflow categories only. All project dates, prices, reviewer responses, site conditions and authority delegations below are invented; this is not an EQORE SOP or permitting determination.",
        "Review durations represent a selected point in a multi-month deployment. A simulated reply may advance the clock; it does not model a real review SLA or claim every review succeeds immediately.",
        "Cost allocations include assumed site-intensive labor and mobilization. They are itemized scenario estimates, not EQORE typical category proportions; electrical/structural materials are carried in the equipment/materials allocation, separate from the labor-only package.",
        "This project uses a synthetic customer-purchase cost model. EQORE also offers other commercial structures; ledger values are not quoted EQORE pricing or promised savings.",
        "Final handoff requires issued as-built documentation, a customer walkthrough, and fleet acceptance of observed telemetry and alert routing; no real battery is operated."
    ]
    fire = deepcopy(next(p for p in state["stakeholders"] if p["id"] == "inspector"))
    fire.update(id="fire", name={"harbor_components": "Devon Hayes", "millbrook_cold_storage": "Kendall Price", "riverbend_logistics": "Lee Emerson"}[pid],
                role="Fire prevention reviewer", organization="Simulated local fire prevention office", knows=["fire_review", "emergency_response", "site_access"],
                can_approve=["fire_review"], contact="fire@" + pid.replace("_", "-") + ".example")
    state["stakeholders"].append(fire)
    next(p for p in state["stakeholders"] if p["id"] == "ops")["can_approve"].append("task_completion")
    next(p for p in state["stakeholders"] if p["id"] == "facilities")["knows"].append("delivery_receipt")
    tasks["t_contract"]["description"] = "Signed purchase scope, equipment boundary, customer contacts, milestone budget and change delegation recorded; no predicted savings are treated as earned revenue."
    tasks["t_survey"]["description"] = "Survey records equipment position, rigging route, electrical tie-in, meter/CT locations, customer operations restrictions and the network owner. Qualified engineers determine actual design values."
    tasks["t_design"]["description"] = "Responsible engineer issues the current single-line, equipment layout and interfaces, with source documents and unresolved review comments indexed. A draft or email acknowledgement is insufficient."
    tasks["t_permit"]["description"] = "Record building/electrical review and separate fire-review acceptance for this project and current drawing revision. A submission receipt does not close either review."
    tasks["t_utility"]["description"] = "Record the applicable utility pathway, accepted application and installation-stage conditions; this does not grant operating authorization."
    tasks["t_procure"]["description"] = "Supplier confirms ordered configuration, shipping record and remaining equipment documentation. An arrival estimate is distinct from facility receiving evidence."
    tasks["t_site"]["description"] = "EPC attests pad, route and laydown readiness, working access and the agreed delivery interface. Construction details remain the responsibility of qualified site personnel."
    tasks["t_unload"]["description"] = "Receiving contact verifies delivered equipment against the order and visible receiving exceptions; the rigging crew separately confirms its slot and completes placement."
    tasks["t_electrical"]["description"] = "Electrical contractor uses issued drawings and separately confirmed crew/customer access. Customer operations authorizes the interruption and operating contingency; availability is not that authorization."
    tasks["t_verify"]["description"] = "Qualified verifier compares the installation with current drawings and records terminations, conductors, grounding, metering/CT orientation and protection-setting checks. Defects require installer correction and qualified reinspection; the assistant supplies no engineering settings."
    tasks["t_commission"]["title"] = "Run and record operational commissioning tests"
    tasks["t_commission"]["description"] = "Controls engineer records operational functional tests after network, field, inspection and operating-authority gates. Applicable utility witness/acceptance tests belong to the earlier utility authorization package and may precede that authorization. Network reachability alone does not demonstrate correct meter readings or battery/control behavior."
    tasks["t_handoff"]["description"] = "Fleet engineer accepts current equipment/configuration index, telemetry sample, alert routing and named support owner after customer training and as-built records. Program eligibility/enrollment is recorded separately and not inferred from physical installation."
    # Explicit downstream deliverables expose closeout work that a generic handoff box hid.
    handoff_day = project["target_handoff"]
    for identity, title, owner, dependencies, hour, detail in [
        ("t_closeout_documents", "Issue as-built and support document pack", "engineer", ["t_verify"], 9, "Issue the revision-controlled as-built single-line and layout, installation/inspection records, equipment serial and warranty index, and site emergency/support contacts."),
        ("t_customer_training", "Record customer monitoring walkthrough", "ops", ["t_commission", "t_closeout_documents"], 12, "Customer operations confirms the monitoring walkthrough, contact/escalation route and operating responsibility handoff; this does not establish savings performance.")]:
        task = {"id": identity, "title": title, "phase": "Handoff", "owner_id": owner, "predecessors": dependencies,
                "duration_hours": 1, "planned_start": _window(handoff_day, hour, 1)["start"], "resource": None,
                "required_gates": [], "status": "planned", "evidence_ids": [], "description": detail,
                "external": True, "required_evidence_kind": "task_completion", "delivery_dependent": False, "required_resources": []}
        state["tasks"].insert(-1, task)
    tasks["t_handoff"]["predecessors"] = ["t_commission", "t_closeout_documents", "t_customer_training"]
    tasks["t_handoff"]["planned_start"] = _window(handoff_day, 14, 2)["start"]
    _add_gate(state, "fire_review", "Project fire-review package accepted", "fire", ["t_permit"], ["t_design"], approved=pid == "riverbend_logistics",
              artifact="Current layout/equipment documentation, emergency response package and recorded project-specific fire-review comments accepted by the assigned fire reviewer. No universal checklist is inferred.")
    _add_gate(state, "delivery_receipt", "Physical equipment receiving record", "facilities", ["t_unload"], ["t_procure"], approved=pid == "riverbend_logistics",
              artifact="Facility receiver signs project-scoped order/serial match, arrival time and exception record; vendor ETA or shipping confirmation cannot substitute.")
    _add_gate(state, "corrective_work", "Installer corrective-work record closed", "electrician", ["t_verify"], ["t_electrical"], approved=True,
              artifact="No known open installation punch item at the opening snapshot. New qualified findings invalidate this status and require a signed contractor correction record before independent verification.")
    state["gates"]["field_verified"]["required_gates"] = ["corrective_work"]
    _add_gate(state, "final_inspection", "Final local inspection record accepted", "inspector", ["t_commission"], ["t_verify"],
              artifact="Assigned local reviewer supplies the final project inspection result for the installed revision and applicable reviewed conditions; utility authority remains separate.")
    _add_gate(state, "fleet_ready", "Fleet telemetry and support acceptance", "fleet", ["t_handoff"], ["t_commission", "t_closeout_documents"],
              artifact="Fleet engineer checks current telemetry evidence, alert delivery, configuration/equipment index and named support escalation ownership; a connected gateway alone is insufficient.")
    state["gates"]["delivery_receipt"]["execution_only"] = True
    state["gates"]["commissioned"]["required_gates"].append("final_inspection")
    artifacts = {
        "design": "Issued current single-line, site layout and engineering review record; draft documents do not authorize field changes.",
        "permit": "Project-scoped building/electrical review acceptance identifying approved drawing revision and outstanding conditions.",
        "utility_install": "Utility installation-stage acceptance and stated conditions for this project; separate operating approval remains pending.",
        "customer_window": "Operations approval of the exact interruption window, affected operations, customer contact and contingency; facilities availability is separate.",
        "corrective_work": "Electrical contractor records completed correction of each observed punch item against the issued design, with project-scoped evidence; independent verifier acceptance remains a separate step.",
        "field_verified": "Signed installer corrective-work record where relevant, followed by qualified reinspection against the current approved design.",
        "network": "Customer IT verifies the agreed controls network route and site ownership; controls performs independent functional retesting.",
        "utility_operate": "Applicable utility acceptance/witness-test record (or utility determination that it is not required), installation completion and required inspection records, followed by written authorization to interconnect/operate for this project. A receipt or witness appointment is insufficient. Tests required to obtain this authorization are distinct from the later operational commissioning task.",
        "commissioned": "Controls engineer accepts project-specific functional results and metering plausibility after prerequisite gates; no actual settings are supplied by this demo."
    }
    for gid, artifact in artifacts.items():
        state["gates"][gid]["required_artifact"] = artifact
        state["gates"][gid]["source_ids"] = ["SRC_EQORE_PM", "SRC_EQORE_PROCESS"]
    state["gates"]["utility_operate"]["required_gates"] = ["final_inspection"]
    state["gates"]["fire_review"]["source_ids"] = ["SRC_BEVERLY"] if pid == "harbor_components" else ["SRC_EQORE_PM"]
    state["gates"]["fleet_ready"]["source_ids"] = ["SRC_EQORE_FLEET", "SRC_EQORE_PROCESS"]
    state["gates"]["network"]["source_ids"] = ["SRC_ETB", "SRC_EQORE_FLEET"]
    for gate in state["gates"].values():
        gate["required_artifacts"] = [gate.get("required_artifact", gate["label"])]
        gate["assumption"] = "Synthetic project requirement. Public references support the workflow category; actual applicability, acceptance criteria and authority require responsible project review."
    # A multi-month history makes late-stage demo snapshots consistent with a full deployment.
    if pid != "millbrook_cold_storage":
        historical = {"t_contract": "2026-08-17", "t_survey": "2026-08-25", "t_design": "2026-09-10", "t_procure": "2026-09-15"}
        for identity, day in historical.items():
            tasks[identity]["planned_start"] = _window(day, 9, tasks[identity]["duration_hours"])["start"]
        project["assumptions"].append("The contract was signed in August; this opening snapshot focuses on the final deployment weeks after prior design/procurement work.")
    else:
        project["assumptions"].append("The illustrative full timeline runs from November 16 contract to February 12 handoff. Design/review/procurement lead time is represented explicitly; these dates are not promised review SLAs.")
    # Authored observations, not inferred actuals from the current working plan.
    observed_completions = ({"t_contract": "2026-11-16T09:00:00-05:00"} if pid == "millbrook_cold_storage" else {
        "t_contract": "2026-08-17T10:00:00-04:00", "t_survey": "2026-08-25T11:00:00-04:00",
        "t_design": "2026-09-10T11:00:00-04:00", "t_procure": "2026-09-15T10:00:00-04:00",
        "t_permit": "2026-11-05T10:00:00-05:00", "t_utility": "2026-11-05T11:00:00-05:00",
        "t_site": "2026-11-08T13:00:00-05:00", "t_unload": "2026-11-12T11:00:00-05:00",
        "t_electrical": "2026-11-14T12:00:00-05:00"})
    project.update(scope_start="post_signing", signed_at=observed_completions["t_contract"])
    for task in state["tasks"]:
        if task["status"] == "completed" and task["id"] in observed_completions:
            task["completed_at"] = observed_completions[task["id"]]
            for evidence in state["evidence"]:
                if evidence["id"] in task["evidence_ids"]:
                    evidence.update(effective_at=task["completed_at"], received_at=task["completed_at"])
    state["evidence"].append(_record(state, "SITE_WORK_PACKAGES", "Current project deliverable register", "\n".join(t["title"] + ": " + t["description"] for t in state["tasks"]), "pm", "scope_register"))
    # This records observed scope, not future faults or the simulator's response policies.
    project["source_mapping"] = [
        {"source_id": "SRC_EQORE_COST", "supports": "cost component categories and site-specific variation; every amount and proportion here is synthetic", "encoded_in": ["finance", "labor"]},
        {"source_id": "SRC_EQORE_PM", "supports": "stakeholder roles, issued design/field verification, budget/change control and commissioning scope", "encoded_in": ["t_design", "t_verify", "t_commission", "fire_review"]},
        {"source_id": "SRC_EQORE_PROCESS", "supports": "multi-month pathway, customer interruption coordination, utility operating gate and monitoring walkthrough", "encoded_in": ["customer_window", "utility_operate", "t_customer_training"]},
        {"source_id": "SRC_EQORE_FLEET", "supports": "telemetry, alerting, fleet/controls integration and operational ownership", "encoded_in": ["fleet_ready", "t_handoff"]},
        {"source_id": "SRC_ETB", "supports": "site IT coordination, meter checks, commissioning evidence and end-user education", "encoded_in": ["network", "field_verified", "t_customer_training"]},
        {"source_id": "SRC_NG_MA_1646", "supports": "example utility document/review and operating authorization boundaries; selected pathway is a synthetic assumption", "encoded_in": ["utility_install", "utility_operate"]}
    ]
    if pid == "harbor_components":
        project["source_mapping"].append({"source_id": "SRC_BEVERLY", "supports": "local example of distinct fire-review package and pre-commissioning inspection; applicability still requires responsible review", "encoded_in": ["fire_review", "final_inspection"]})


def initial_state(project_id):
    profile = _profile(project_id)
    state = scenarios.initial_state("normal_progress" if project_id == "millbrook_cold_storage" else "delivery_delay")
    state = _remap(state, profile)
    project = state["project"]
    project.update({key: deepcopy(profile[key]) for key in ("name", "customer", "site", "system", "phase", "target_handoff", "budget_baseline", "assumptions")})
    project.update(id=profile["project_id"], demo_project_id=project_id, scenario_id="field_discrepancy",
                   location=profile["site"], target_date=profile["target_handoff"],
                   utility="Synthetic Massachusetts utility pathway; actual service territory is unverified",
                   budget={"baseline": profile["budget_baseline"], "committed": profile["budget_baseline"], "proposed": 0},
                   demo_version=VERSION, world_version=VERSION)
    if project_id != "harbor_components":
        project["source_ids"] = [sid for sid in project["source_ids"] if sid != "SRC_BEVERLY"]
    for person in state["stakeholders"]:
        person["organization"] = person["organization"].replace("Harbor Components", profile["name"])
        person["contact"] = person["id"] + "@" + project_id.replace("_", "-") + ".example"
    # Distinct fictional people, with stable role IDs for tool interoperability.
    if project_id == "millbrook_cold_storage":
        names = {"pm": "Morgan Ellis", "ops": "Riley Foster", "facilities": "Sage Kim", "engineer": "Alex Moreno", "it": "Charlie Reed", "electrician": "Casey Lin", "rigger": "Dana Brooks"}
    elif project_id == "riverbend_logistics":
        names = {"pm": "Jamie Carter", "ops": "Robin Shah", "facilities": "Avery Kim", "engineer": "Taylor Evans", "it": "Drew Nguyen", "controls": "Sam Parker", "verifier": "Skyler Bell"}
    else:
        names = {}
    for person in state["stakeholders"]:
        person["name"] = names.get(person["id"], person["name"])
    tasks = {task["id"]: task for task in state["tasks"]}
    if project_id == "harbor_components":
        _opening_tasks(state, {"t_contract", "t_survey", "t_design", "t_procure"})
        for gate in ("permit", "customer_window"):
            _pending(state, gate)
        tasks["t_permit"]["planned_start"] = _window("2026-11-10", 9, 1)["start"]
        tasks["t_utility"]["planned_start"] = _window("2026-11-10", 10, 1)["start"]
        tasks["t_site"]["planned_start"] = _window("2026-11-11", 9, 4)["start"]
        project["delivery_eta"] = "2026-11-13T09:00:00-05:00"
        project["delivery_effective_at"] = project["now"]
        state["evidence"].append(_record(state, "OPENING_DELAY", "Observed supplier delay", "Supplier currently estimates November 13 arrival, after the November 12 planned rigging slot. November 17 and 19 rigging alternatives are offered, subject to confirmation.", "vendor", "delivery"))
        next(e for e in state["evidence"] if e["id"] == "CUSTOMER_WINDOWS")["body"] = "Facilities offers November 14 and 21, 08:00–12:00, as possible electrical windows. Operations approval is still pending; availability alone is not shutdown authority."
        state["evidence"].append(_record(state, "SHUTDOWN_REQUEST_NEEDED", "Customer shutdown decision outstanding", "Operations must decide the proposed Saturday interruption before any changed electrical schedule is committed.", "ops", "constraint"))
        state["alerts"].append({"id": "OPENING_SHUTDOWN", "kind": "authority", "severity": "high", "title": "Customer operations has not authorized the Saturday shutdown", "task_ids": ["t_electrical"], "gate_id": "customer_window", "resolver_id": "ops", "evidence_ids": ["SHUTDOWN_REQUEST_NEEDED"], "resolved": False})
    elif project_id == "millbrook_cold_storage":
        project.update(now="2026-11-16T09:00:00-05:00", delivery_eta="2027-02-01T09:00:00-05:00", delivery_effective_at="2026-11-16T09:00:00-05:00", recovery_cost=3500, schedule_change_cost=3500)
        days = {"t_contract": ("2026-11-16", 8), "t_survey": ("2026-11-17", 9), "t_design": ("2026-12-02", 9), "t_permit": ("2027-01-11", 9), "t_utility": ("2027-01-12", 10), "t_procure": ("2026-12-04", 9), "t_site": ("2027-01-19", 9), "t_unload": ("2027-02-02", 9), "t_electrical": ("2027-02-06", 8), "t_verify": ("2027-02-08", 9), "t_commission": ("2027-02-09", 9), "t_handoff": ("2027-02-12", 9)}
        for tid, (day, hour) in days.items():
            tasks[tid]["planned_start"] = _window(day, hour, tasks[tid]["duration_hours"])["start"]
        tasks["t_contract"].update(status="completed", evidence_ids=["CONTRACT_SCOPE"])
        for gid in ("customer_window", "network"):
            _pending(state, gid)
        state["calendars"] = {"rigging_crew": [_window("2027-02-02", 9, 2), _window("2027-02-04", 9, 2)], "electrical_crew": [_window("2027-02-06", 8, 4), _window("2027-02-13", 8, 4)], "customer_access": [_window("2027-02-06", 8, 4), _window("2027-02-13", 8, 4)]}
        for evidence in state["evidence"]:
            evidence["received_at"] = project["now"]
            evidence["effective_at"] = project["now"]
            if evidence["id"] == "CUSTOMER_WINDOWS":
                evidence["body"] = "Facilities offers February 6 and 13, 08:00–12:00, as potential windows. Customer operations must authorize the refrigeration interruption before electrical work."
            if evidence["id"] == "ETA_ORIGINAL":
                evidence["body"] = "Supplier's preliminary estimate is February 1 at 09:00, subject to order confirmation and later shipping evidence."
    else:
        # Actual completion records retain project/design scope and timestamps.
        for tid in ("t_unload", "t_electrical"):
            task = tasks[tid]
            finish = (datetime.fromisoformat(task["planned_start"]) + timedelta(hours=task["duration_hours"])).isoformat()
            evidence = _record(state, "OPENING_COMPLETE_" + tid, task["title"] + " completion", "Responsible actor supplied a synthetic signed completion record for this project and design.", task["owner_id"], "task_completion")
            evidence.update(effective_at=finish, received_at=finish, task_id=tid)
            state["evidence"].append(evidence)
            task.update(status="completed", evidence_ids=[evidence["id"]])
        project["now"] = "2026-11-16T09:00:00-05:00"
        for tid, day in (("t_verify", "2026-11-18"), ("t_commission", "2026-11-20"), ("t_handoff", "2026-11-23")):
            tasks[tid]["planned_start"] = _window(day, 9, tasks[tid]["duration_hours"])["start"]
        _pending(state, "network")
        state["gates"]["network"]["status"] = "blocked"
        state["evidence"].append(_record(state, "OPENING_NETWORK", "Observed controls connectivity failure", "Customer-managed firewall blocks the approved controls route. Customer IT must restore the route; controls must separately retest functionality.", "controls", "commissioning_fault"))
        state["alerts"].append({"id": "OPENING_NETWORK", "kind": "commissioning_fault", "severity": "high", "title": "Customer firewall blocks the controls connection", "task_ids": ["t_commission"], "gate_id": "network", "resolver_id": "it", "evidence_ids": ["OPENING_NETWORK"], "resolved": False})
    _strengthen_world(state, profile)
    # Commercial scope records reflect the selected project, not the base fixture.
    contract = next(e for e in state["evidence"] if e["id"] == "CONTRACT_SCOPE")
    contract["body"] = "Signed synthetic scope for %s: $%s baseline for battery deployment through commissioning and handoff. No real customer contract is represented." % (project["name"], format(profile["budget_baseline"], ","))
    for gate in state["gates"].values():
        gate["scope"] = "Only %s and design %s; separate institutional signoffs remain separate." % (project["id"], project["design_revision"])
    state["evidence"].append(_record(state, "PROJECT_ASSUMPTIONS", "Project-specific demo assumptions", "\n".join(profile["assumptions"]), "pm", "assumptions"))
    _finance(state, profile)
    return deepcopy(state)


def next_event(project_id, cursor, state):
    """Private staged events: release only after work reveals each fact."""
    profile = _profile(project_id)
    if state["project"].get("demo_project_id") != project_id:
        raise ValueError("Event project does not match selected project")
    staged = {
        "harbor_components": [("t_permit", "permit_return"), ("t_site", "rigging_withdrawal"), ("t_electrical", "field_defect"), ("t_verify", "network_fault"), ("t_commission", "fleet_gap")],
        "millbrook_cold_storage": [("t_survey", "survey_clarification"), ("t_design", "utility_return"), ("t_procure", "shipping_update"), ("t_electrical", "field_defect"), ("t_commission", "fleet_gap")],
        "riverbend_logistics": [("t_verify", "utility_receipt"), ("t_verify", "functional_retest"), ("t_commission", "late_network_fault"), ("t_commission", "fleet_gap"), ("t_closeout_documents", "support_packet")]
    }
    if cursor not in range(len(staged[project_id])):
        return None
    required, kind = staged[project_id][cursor]
    if required not in {t["id"] for t in state["tasks"] if t["status"] == "completed"}:
        return None
    at = (datetime.fromisoformat(state["project"]["now"]) + timedelta(minutes=15)).isoformat()
    eid = project_id + "_" + str(cursor) + "_" + kind
    ev = {"id": eid, "at": at, "type": "evidence_received"}
    if kind in {"permit_return", "utility_return"}:
        permit = kind == "permit_return"
        gid = "permit" if permit else "utility_install"
        body = ("Following initial acceptance, the permitting reviewer returns an amendment comment: the equipment layout's access annotation does not match the submitted site access schedule. The responsible engineer must reconcile and reissue the affected package; the permitting reviewer must accept the correction before site work. Existing procurement records remain valid."
                if permit else "Utility application review finds the equipment schedule identifier inconsistent with the issued single-line package. The engineer must reconcile the application attachments and return a controlled correction; only the utility reviewer can accept the revised installation-stage package. This documentary correction does not invent changed equipment, electrical settings or an operating permission.")
        ev.update(type="review_returned", issuer_id="inspector" if permit else "utility", gate_id=gid,
                  correction_owner_id="engineer", return_phase="site_design", affected_task_ids=["t_permit" if permit else "t_utility"],
                  affected_gate_ids=[gid], required_artifact="Revision-controlled corrected package and comment-response register, ready for separate reviewer acceptance.",
                  summary="Permitting amendment returned for engineering correction" if permit else "Utility package returned for inconsistent equipment identifier", reason=body)
    elif kind == "rigging_withdrawal":
        ev.update(type="resource_conflict", issuer_id="rigger", resource="rigging_crew", windows=[w for w in state["calendars"]["rigging_crew"] if not w["start"].startswith("2026-11-17")], summary="Rigger withdraws November 17 offer because another site confirmed the crew")
        body = "The November 17 offered rigging slot was not booked and is now unavailable. November 19 remains offered with an additional synthetic $1,200 remobilization quote beyond any already committed recovery cost. A recovery plan must use the remaining window and obtain a separate booking."
    elif kind == "survey_clarification":
        ev.update(type="field_defect", issuer_id="facilities", gate_id="design", resolver_id="engineer", task_ids=["t_design"], summary="Survey exposes an ambiguous meter/CT location in the draft single-line")
        body = "Survey photos identify two metering points while the proposed single-line labels only one. The engineer must resolve the project-specific metering boundary and issue the reviewed package before procurement or institutional submissions. This is a design coordination question, not an instruction to change field wiring."
    elif kind == "shipping_update":
        ev.update(type="delivery_update", issuer_id="vendor", eta="2027-02-01T15:00:00-05:00", summary="Supplier updates February 1 arrival to afternoon; February 2 rigging still fits")
        body = "Shipping ETA is February 1 at 15:00. It still precedes February 2 09:00 rigging; the estimate does not establish physical receipt and does not by itself justify a paid schedule change."
    elif kind == "field_defect":
        ev.update(type="field_defect", issuer_id="verifier", gate_id="corrective_work", resolver_id="electrician", task_ids=["t_verify"], summary="Field inspection finds CT orientation inconsistent with issued design")
        body = "The qualified verifier records a CT/metering orientation discrepancy against the issued design. Installer corrective-work evidence and independent reinspection are required before field verification; the assistant must not invent corrective settings."
    elif kind in {"network_fault", "late_network_fault"}:
        ev.update(type="commissioning_fault", issuer_id="controls", gate_id="network", resolver_id="it", task_ids=["t_commission"], summary="Controls connection fails after customer firewall policy changes")
        body = "The approved network path is no longer reachable. Customer IT must restore the agreed route; controls must independently confirm functional behavior afterward. Network repair does not grant operating or commissioning approval."
        if kind == "late_network_fault":
            ev["summary"] = "A post-commissioning firewall change invalidates the accepted controls test"
            body += " This finding occurred after the operational commissioning record. Preserve installation history, require fresh controls acceptance and repeat the affected commissioning and handoff work."
    elif kind == "utility_receipt":
        ev.update(issuer_id="utility", summary="Utility acknowledges verification package receipt without operating permission")
        body = "The utility reviewer acknowledges receipt of the submitted completion/verification package and keeps operating acceptance pending. Document receipt and review scheduling grant no operating authority."
    elif kind == "functional_retest":
        ev.update(type="commissioning_fault", issuer_id="controls", gate_id="commissioned", resolver_id="controls", task_ids=["t_commission"], summary="Network is reachable but controls still needs a successful metering/telemetry retest")
        body = "IT reachability does not close the controls test. The controls engineer must reconcile the project meter mapping and produce current functional results after utility and inspection permission; no numerical configuration is invented."
    elif kind == "fleet_gap":
        ev.update(type="commissioning_fault", issuer_id="fleet", gate_id="fleet_ready", resolver_id="fleet", task_ids=["t_handoff"], summary="Fleet handoff check finds alert routing has no confirmed support owner")
        body = "Telemetry is present, but the support escalation recipient and alert-delivery test have not been accepted by the fleet engineer. Complete the document pack, confirm the named owner and record the test before operational handoff."
    else:
        ev.update(issuer_id="fleet", summary="Fleet supplies support contact and monitoring packet for final acceptance")
        body = "The monitoring and support packet is now available. Fleet acceptance of alert delivery and the customer walkthrough remain separate evidenced work; possession of this packet alone does not complete handoff."
    ev["evidence"] = _record(state, eid + "_DOC", ev["summary"], body, ev["issuer_id"], "receipt" if kind == "utility_receipt" else kind)
    ev["evidence"].update(effective_at=at, received_at=at)
    return ev


def actor_response(state, request):
    """Bounded counterpart role-play with review receipts and explicit artifact outcomes."""
    profile = _profile(state["project"].get("demo_project_id"))
    if request.get("status") == "acknowledged":
        return None
    if request.get("purpose") == "rework_correction":
        record = next((r for r in state.get("rework", []) if r["id"] == request.get("rework_id")), None)
        if not record or record.get("status") != "correction_required":
            return None
        at = (datetime.fromisoformat(state["project"]["now"]) + timedelta(hours=8)).isoformat()
        evidence = _record(state, request["id"] + "_CORRECTION", "Engineering comment-response package", record.get("required_artifact", "Corrected reviewer package") + " The responsible owner supplies a project-scoped correction for resubmission; this is not reviewer acceptance.", request["recipient_id"], "correction_record")
        evidence.update(rework_id=record["id"], rework_generation=request.get("rework_generation"), effective_at=at, received_at=at)
        return {"id": request["id"] + "_CORRECTION_REPLY", "type": "request_response", "at": at, "request_id": request["id"],
                "issuer_id": request["recipient_id"], "status": "corrected", "evidence": evidence, "summary": "Owner supplies corrected package; reviewer acceptance remains outstanding"}
    gid = request.get("gate_id") or (request.get("subject_id") if request.get("subject_id") in state["gates"] else None)
    gate = state["gates"].get(gid, {})
    done = {t["id"] for t in state["tasks"] if t["status"] == "completed"}
    if gid and (any(tid not in done for tid in gate.get("required_tasks", [])) or any(state["gates"][key]["status"] != "approved" for key in gate.get("required_gates", []))):
        return None
    event = scenarios.actor_response(state, request)
    if event is None:
        return None
    event = _remap(event, profile)
    now = datetime.fromisoformat(state["project"]["now"])
    # Institutions first acknowledge a submitted package. A later separate request
    # retrieves its scoped review outcome. The model sees only received evidence.
    review_gates = {"fire_review", "permit", "utility_install", "utility_operate"}
    seen_receipt = any(e.get("kind") == "receipt" and e.get("review_gate_id") == gid for e in state["evidence"])
    if gid in review_gates and not seen_receipt and event.get("status") == "approved":
        event.update(status="acknowledged", summary="Reviewer acknowledges package receipt; " + gate["label"] + " remains pending")
        event["evidence"].update(kind="receipt", review_gate_id=gid, body="Received the current project package for " + gate["label"] + ". Review outcome is pending; this acknowledgement grants no installation or operating authority.")
    elif gid and event.get("status") == "approved":
        event["evidence"]["body"] = gate.get("required_artifact", "Scoped current-project review record") + " Supplied and accepted by the recorded authorized actor for " + state["project"]["id"] + ", design " + state["project"]["design_revision"] + ". This is a synthetic review result, not actual regulatory or engineering signoff."
        # Review and repair turnaround are scenario mechanics, not promised SLAs.
        if gid in review_gates or gid in {"final_inspection", "corrective_work", "field_verified", "network", "fleet_ready"}:
            event["at"] = (now + timedelta(hours=4)).isoformat()
        if gid == "delivery_receipt":
            arrival = datetime.fromisoformat(state["project"]["delivery_eta"])
            event["at"] = max(now + timedelta(hours=1), arrival).isoformat()
    if request.get("purpose") == "task_completion":
        task = next((t for t in state["tasks"] if t["id"] == request.get("task_id")), None)
        if task:
            event["evidence"]["body"] += " Work package: " + task["description"]
            if task.get("rework_generation", 0):
                event["at"] = max(datetime.fromisoformat(event["at"]), now + timedelta(hours=task["duration_hours"])).isoformat()
    event["evidence"].update(project_id=state["project"]["id"], design_revision=state["project"]["design_revision"], received_at=event["at"], effective_at=event["at"])
    return event
