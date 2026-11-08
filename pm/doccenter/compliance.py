"""Source-linked document coverage, not a code-compliance determination.

The client brief supplies a checklist, not a verified jurisdiction/edition matrix.
This module only projects records. It never rewrites historical documents, signs
anything, grants access, or treats a generic Dxx packet as a specific approval.
"""
from copy import deepcopy
from datetime import datetime, timedelta

from client_reference import DOCUMENT_REQUIREMENTS


SOURCE = {
    "title": "EQORE challenge brief - Option 4: Compliance documentation at scale",
    "url": "https://docs.google.com/document/d/1ldQhkrjIGzRNjUCpFRPsN6hx4ceSVDt5MHX3-hePq2E/edit",
    "section": "Option 4; Documents NFPA 855 requires for every site",
    "basis": "Client-provided checklist; applicable code edition, local amendments and site requirements need responsible review.",
}


def _requirement(identity, title, owner, recipients, phase, related, prerequisites,
                 when, trigger, evidence, audiences, section=None, lifecycle="delivery"):
    return {"id": identity, "title": title, "kind": "record", "owner_role": owner,
            "recipient_roles": recipients, "phase": phase,
            "related_document_ids": related, "prerequisite_ids": prerequisites,
            "when": when, "update_trigger": trigger, "evidence_required": evidence,
            "audiences": audiences, "lifecycle": lifecycle,
            "source_refs": [dict(SOURCE, cited_sections=section or "Option 4 approval records")],
            "applicability": "Confirm for this site with the responsible engineer and authority."}


_WORKFLOW_DEFAULTS = [
    _requirement("interconnection_application", "Interconnection application", "engineer", ["engineer"],
                 "Reviews and procurement", ["D08"], ["D04"],
                 "Before utility review; use the utility's project-specific deadline.",
                 "Equipment, export mode, service or approved drawing changes.",
                 "Submitted application, utility reference, equipment and drawing revisions, submission receipt.",
                 ["EQORE", "Utility", "Facility"]),
    _requirement("interconnection_approval", "Interconnection approval", "pm", ["utility"],
                 "Reviews and procurement", ["D09", "D10"], ["D08"],
                 "At the utility's applicable approval milestone; distinct from PTO.",
                 "Revised utility conditions or changes to the approved installation.",
                 "Utility-issued approval or agreement, accepted revision, conditions and project reference.",
                 ["EQORE", "Utility", "Facility"]),
    _requirement("building_permit", "Building permit", "pm", ["ahj"],
                 "Reviews and procurement", ["D06", "D07"], ["D06"],
                 "Before work requiring this permit; confirm local applicability and dates.",
                 "Approved scope changes, authority comments or recorded expiry.",
                 "Issued building permit and approved plan revision, conditions and permit number.",
                 ["EQORE", "AHJ", "Facility", "EPC"]),
    _requirement("electrical_permit", "Electrical permit", "electrician", ["ahj"],
                 "Reviews and procurement", ["D06", "D07"], ["D06"],
                 "Before permitted electrical work; confirm local issuer and dates.",
                 "Electrical scope changes, authority comments or recorded expiry.",
                 "Issued electrical permit, responsible license holder, scope and permit number.",
                 ["EQORE", "AHJ", "Facility", "Electrical contractor"]),
    _requirement("fire_permit", "Fire approval / permit", "pm", ["fire"],
                 "Reviews and procurement", ["D06", "D07"], ["D06"],
                 "At the fire authority's required approval milestone.",
                 "Equipment, layout, access or fire/emergency response changes.",
                 "Fire authority's issued approval/permit, accepted layout and outstanding conditions.",
                 ["EQORE", "Fire authority", "Facility"]),
    _requirement("building_inspection", "Building inspection sign-off", "epc", ["ahj"],
                 "Verification", ["D17"], ["D15"],
                 "At the locally required inspection stage.",
                 "Failed inspection, corrected works or a revised permitted scope.",
                 "Authority-issued inspection outcome identifying site, permit, date and unresolved corrections.",
                 ["EQORE", "AHJ", "Facility", "EPC"], lifecycle="commissioning"),
    _requirement("electrical_inspection", "Electrical inspection sign-off", "electrician", ["ahj"],
                 "Verification", ["D17"], ["D15"],
                 "At each required electrical inspection stage; do not substitute contractor completion.",
                 "Failed inspection, electrical correction or revised permitted scope.",
                 "Electrical authority's inspection record, permit and accepted scope/stage.",
                 ["EQORE", "AHJ", "Facility", "Electrical contractor"], lifecycle="commissioning"),
    _requirement("fire_inspection", "Fire inspection sign-off", "pm", ["fire"],
                 "Verification", ["D17"], ["D15"],
                 "At the fire authority's required inspection stage.",
                 "Fire-system, layout, access or emergency-procedure changes requiring re-review.",
                 "Fire authority's inspection outcome, conditions and accepted site configuration.",
                 ["EQORE", "Fire authority", "Facility"], lifecycle="commissioning"),
    _requirement("commissioning_plan", "Commissioning plan", "controls", ["engineer", "controls"],
                 "Installation readiness", ["D18"], ["D04"],
                 "Before commissioning.",
                 "Equipment, safety-system, test procedure or commissioning-role changes.",
                 "Roles, qualified personnel, test procedures, checklists, staff training and issue-resolution process.",
                 ["EQORE", "AHJ", "Facility"], "Client brief cites NFPA 855 section 6.1"),
    _requirement("commissioning_report", "Commissioning report", "controls", ["engineer", "controls"],
                 "Verification", ["D18"], ["D04"],
                 "After tests; client brief calls for owner/AHJ delivery before final inspection and inclusion in O&M.",
                 "Retesting, unresolved defects or changes affecting recorded results.",
                 "Actual test results/logs, staff training, issues and resolutions, responsible personnel and as-built plans.",
                 ["EQORE", "AHJ", "Facility"], "Client brief cites NFPA 855 section 6.1", "commissioning"),
    _requirement("utility_pto", "Utility permission to operate (PTO)", "pm", ["utility"],
                 "Handoff", ["D19"], ["D18"],
                 "Before operation requiring utility permission; verify utility conditions.",
                 "Utility conditions or changes outside the permitted operating configuration.",
                 "Utility-issued PTO identifying the site, system, effective date and operating conditions.",
                 ["EQORE", "Utility", "Facility"], lifecycle="commissioning"),
    _requirement("signage_labels", "Signage, labels and safety data", "engineer", ["engineer", "epc"],
                 "Installation readiness", ["D04", "D17"], ["D04"],
                 "Prepare for installation; verify installed locations before handover.",
                 "Equipment, disconnect locations, hazard information or emergency contacts change.",
                 "Site-specific hazard/disconnect/system labels, safety data and installation-location verification.",
                 ["EQORE", "AHJ", "First responders", "Facility"], "Client brief cites NFPA 855 section 7.1.3"),
    _requirement("om_manual", "Operations and maintenance manual", "fleet", ["fleet", "facilities"],
                 "Handoff", ["D20"], ["D04"],
                 "Before operation.",
                 "System components, set points, procedures, service contacts or maintenance schedule change.",
                 "System/component details, manufacturer manuals, contacts, operating/safety procedures, maintenance schedule and re-permitting triggers.",
                 ["EQORE", "AHJ", "First responders", "Facility"], "Client brief cites NFPA 855 sections 4.1.2.3, 6.3, 7.1-7.3"),
    _requirement("emergency_plan", "Emergency operations plan", "engineer", ["engineer", "facilities"],
                 "Installation readiness", ["D04", "D20"], ["D04"],
                 "Prepare for operation; client brief calls for on-site availability at occupied facilities.",
                 "Changes to shutdown/isolation, alarm response, hazards, damaged-equipment handling or drill procedures.",
                 "Site-specific shutdown/isolation, alarm and emergency responses, safety information and drill process/schedule.",
                 ["EQORE", "Facility"], "Client brief cites NFPA 855 section 4.1.3.2.1"),
    _requirement("as_built_package", "As-built drawings", "engineer", ["engineer", "epc"],
                 "Verification", ["D04", "D17", "D18"], ["D04"],
                 "With the commissioning report and operating documentation.",
                 "Installed layout, equipment, wiring or maintained configuration changes.",
                 "Controlled drawings reflecting the installed configuration, revision and responsible review.",
                 ["EQORE", "AHJ", "Facility"], "Client brief: commissioning and decommissioning documentation", "commissioning"),
    _requirement("maintenance_log", "Operations and maintenance log", "fleet", ["fleet"],
                 "Operations", [], ["D19"],
                 "After each maintenance action, test, repair or training; no universal interval assumed.",
                 "Each maintenance/service/test/training event or a recorded scheduled review.",
                 "Dated activity, responsible person, work/test/training performed, outcome and follow-up.",
                 ["EQORE", "AHJ", "First responders", "Facility"], "Client brief cites NFPA 855 sections 7.1-7.3", "operations"),
    _requirement("training_record", "Staff training and drill record", "facilities", ["facilities", "controls"],
                 "Verification", ["D18", "D20"], ["D04"],
                 "During commissioning training and after later training or drills; record actual scheduled dates.",
                 "New staff, changed procedures, completed training or a scheduled drill.",
                 "Dated training/drill scope, participants, responsible trainer, results and follow-up issues.",
                 ["EQORE", "AHJ", "Facility"], "Client brief: commissioning, operations and emergency plan", "commissioning"),
    _requirement("performance_report", "Performance report", "fleet", ["fleet"],
                 "Operations", [], ["D19"],
                 "On the site's agreed reporting schedule; record the actual due date.",
                 "Reporting period ends or corrected operating data changes the result.",
                 "Reporting period, source data, operating performance and reviewer/recipient record.",
                 ["EQORE", "Facility"], "Client brief: Option 4 lifecycle documents", "operations"),
    _requirement("decommissioning_plan", "Decommissioning plan", "engineer", ["engineer", "facilities"],
                 "Decommissioning", [], [],
                 "Before decommissioning; client brief calls for prior AHJ notification.",
                 "Decommissioning scope, as-maintained configuration, sequence or adjacent-system protections change.",
                 "Roles, as-maintained/as-built plans, activity schedule, checklists, protection measures and AHJ notification record.",
                 ["EQORE", "AHJ", "Facility"], "Client brief cites NFPA 855 sections 8.1-8.3", "decommissioning"),
    _requirement("decommissioning_report", "Decommissioning report", "engineer", ["engineer", "facilities"],
                 "Decommissioning", [], [],
                 "After decommissioning.",
                 "Completion evidence, unresolved issues or as-maintained records change.",
                 "Actual work/checklists/logs, issues and resolutions, protection of adjacent systems and responsible review.",
                 ["EQORE", "AHJ", "Facility"], "Client brief cites NFPA 855 sections 8.1-8.3", "decommissioning"),
]

# Facts/checklist wording have one source of truth. These workflow defaults only
# map that reviewed catalog to this app's roles, phases and legacy prerequisites.
_WORKFLOWS = {r["id"]: r for r in _WORKFLOW_DEFAULTS}
REQUIREMENTS = []
for _source_definition in DOCUMENT_REQUIREMENTS:
    _definition = deepcopy(_WORKFLOWS[_source_definition["id"]])
    _definition.update(title=_source_definition["title"],
                       audiences=deepcopy(_source_definition["audience"]),
                       evidence_required=[_source_definition["completion_evidence"]] + deepcopy(_source_definition["expected_contents"]),
                       expected_contents=deepcopy(_source_definition["expected_contents"]),
                       update_trigger="; ".join(_source_definition["update_triggers"]),
                       prerequisite_requirement_ids=deepcopy(_source_definition["depends_on"]),
                       coordination_note=_source_definition["coordination_note"],
                       source_refs=[dict(SOURCE, **ref) for ref in _source_definition["source_refs"]])
    REQUIREMENTS.append(_definition)


def requirement_definition(identity):
    """Return a detached template; unknown identifiers cannot create records."""
    definition = next((r for r in REQUIREMENTS if r["id"] == identity), None)
    if not definition:
        raise ValueError("Unknown compliance requirement.")
    return deepcopy(definition)


def _date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def _active(definition, project, documents):
    lifecycle = definition["lifecycle"]
    recorded = project.get("lifecycle", "delivery")
    if lifecycle == "delivery":
        return True
    if lifecycle == "decommissioning":
        return recorded == "decommissioning"
    statuses = {d.get("id"): d.get("status") for d in documents}
    if lifecycle == "operations":
        return recorded in ("operations", "decommissioning") or statuses.get("D19") == "completed"
    return (recorded in ("commissioning", "operations", "decommissioning")
            or statuses.get("D15") == "completed"
            or statuses.get("D17") == "completed"
            or statuses.get("D19") == "completed")


def review(project, now, document_views=None):
    """Read-only, JSON-safe coverage against client guidance and recorded dates.

    Optional metadata is project.compliance_records[requirement_id], with explicit
    review_due_at, expires_at, changed_at and reviewed_at timestamps. Invalid or
    date-only metadata is shown for review, never silently assigned a timezone.
    """
    instant = _date(now)
    if instant is None:
        raise ValueError("Compliance review requires a timestamp with timezone.")
    documents = list(document_views if document_views is not None else project.get("documents", []))
    archive = project.get("status") == "archived"
    metadata = project.get("compliance_records", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    rows = []
    for definition in REQUIREMENTS:
        row = deepcopy(definition)
        identity = row["id"]
        related = [d for d in documents if d.get("id") in row["related_document_ids"]]
        tracked = [d for d in documents if d.get("requirement_id") == identity]
        meta = metadata.get(identity, {})
        meta = meta if isinstance(meta, dict) else {}
        row.update(tracked_document_ids=[d["id"] for d in tracked],
                   related_document_ids=[d["id"] for d in related],
                   related_documents=[{"id": d["id"], "title": d.get("title", d["id"]), "status": d.get("status")} for d in related],
                   due_at=None, status="missing_record", reason="No requirement-specific record is tracked.",
                   action_title="Track " + row["title"], priority=55,
                   review=deepcopy(meta),
                   audience_access="Intended audience only; sharing and access permissions are not granted by this checklist.")
        owner = next((p for p in project.get("stakeholders", [])
                      if p.get("id") == project.get("pm_id") and row["owner_role"] == "pm"
                      or p.get("id", "").endswith("__" + row["owner_role"])), None)
        row.update(owner_id=owner.get("id") if owner else None,
                   owner_name=owner.get("name") if owner else row["owner_role"])
        if related:
            row["reason"] += " Related packets are available; their titles alone do not establish this record."
        if not tracked and not _active(row, project, documents):
            row.update(status="not_yet_due", priority=0,
                       reason="Applies at the %s stage; no current deadline is recorded." % row["lifecycle"],
                       action_title="Plan " + row["title"])
        elif tracked:
            # Duplicate mappings need a person to choose the authoritative record.
            if len(tracked) != 1:
                row.update(status="needs_review", priority=70,
                           reason="Multiple records claim this requirement; identify the authoritative current record.",
                           action_title="Review duplicate records")
            else:
                document = tracked[0]
                completion = document.get("completion_record") or {}
                status = document.get("status")
                completed_evidence = (status == "completed" and completion.get("revision") == document.get("revision")
                                      and bool(completion.get("source_event_ids")))
                review_at = _date(meta.get("reviewed_at"))
                completed_at = _date(completion.get("at"))
                reviewed = (review_at is not None and review_at <= instant
                            and completed_at is not None and review_at >= completed_at
                            and bool(meta.get("reviewer_id"))
                            and meta.get("reviewed_document_revision") == document.get("revision"))
                complete = completed_evidence and reviewed
                row["record_source_mode"] = document.get("source_mode")
                row["due_at"] = document.get("due_at") if _date(document.get("due_at")) else None
                if complete:
                    row.update(status="current_record", priority=0,
                               reason="The current revision has completion evidence and a recorded PM review. This is document status, not a finding of code compliance.",
                               action_title="Open current record")
                elif status in ("blocked", "returned", "declined", "voided"):
                    row.update(status="update_due", priority=90,
                               reason="The tracked record is %s; resolve its current scope or revision before relying on it." % status,
                               action_title="Review " + row["title"])
                elif completed_evidence:
                    row.update(status="needs_review", priority=70,
                               reason="The current revision has completion evidence but still needs a recorded PM review of this requirement.",
                               action_title="Review " + row["title"])
                else:
                    row.update(status="needs_review", priority=65,
                               reason="A specific record is tracked, but its current revision has no complete evidence record.",
                               action_title="Complete " + row["title"])
                due = _date(row["due_at"])
                if not completed_evidence and due and due < instant:
                    row.update(status="update_due", priority=95,
                               reason="The tracked record's recorded deadline has passed; completion evidence is still outstanding.")
                elif not completed_evidence and due and due <= instant + timedelta(days=30) and row["status"] == "needs_review":
                    row.update(status="upcoming", priority=75,
                               reason="The tracked record is due within 30 days and still needs completion evidence.")
                review_due = min((_date(meta.get(k)) for k in ("review_due_at", "expires_at") if _date(meta.get(k))), default=None)
                if completed_evidence:
                    row["due_at"] = review_due.isoformat() if review_due else None
                if complete and review_due:
                    row["due_at"] = review_due.isoformat()
                    if review_due <= instant:
                        row.update(status="update_due", priority=95,
                                   reason="The recorded review or expiry date has arrived; review the document before continued reliance.",
                                   action_title="Review " + row["title"])
                    elif review_due <= instant + timedelta(days=30):
                        row.update(status="upcoming", priority=75,
                                   reason="The recorded review or expiry date is within 30 days.",
                                   action_title="Schedule review of " + row["title"])
                changed = _date(meta.get("changed_at"))
                last_review = _date(meta.get("reviewed_at"))
                if meta.get("reviewed_document_revision") is not None and meta["reviewed_document_revision"] != document.get("revision"):
                    row.update(status="update_due", priority=95,
                               reason="The tracked document revision changed after its recorded review; review the new revision.",
                               action_title="Review revised " + row["title"])
                if changed and changed <= instant and (last_review is None or changed > last_review):
                    row.update(status="update_due", priority=98,
                               reason="A recorded site change is newer than the last document review; verify and update the affected record.",
                               action_title="Update " + row["title"])
        invalid = [key for key in ("review_due_at", "expires_at", "changed_at", "reviewed_at")
                   if meta.get(key) is not None and _date(meta.get(key)) is None]
        if invalid:
            row.update(status="needs_review", priority=max(row["priority"], 70),
                       reason="Invalid or timezone-free metadata requires review: " + ", ".join(invalid) + ".")
        row["read_only"] = archive
        rows.append(row)
    counts = {key: sum(r["status"] == key for r in rows) for key in
              ("missing_record", "needs_review", "current_record", "update_due", "upcoming", "not_yet_due")}
    actions = [] if archive else sorted(
        [deepcopy(r) for r in rows if r["status"] not in ("current_record", "not_yet_due")],
        key=lambda r: (-r["priority"], r["due_at"] or "9999", r["title"]))
    return {"source": deepcopy(SOURCE), "scope": "retrospective" if archive else "active_project",
            "counts": counts, "requirements": rows, "actions": actions,
            "summary": {"requirement_count": len(rows), "attention_count": len(actions),
                        "tracked_count": sum(bool(r["tracked_document_ids"]) for r in rows)},
            "note": "Client-guided document coverage, not certification. Related packets do not automatically satisfy a specific requirement. Intended audiences are not access grants."}
