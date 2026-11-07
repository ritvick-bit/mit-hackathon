"""Read-only calibration from EQORE's shared hackathon materials, 2026-11-07.

These are source observations and a document-workflow specification, not a code
compliance determination or a statement of a live project's approval status.
Do not treat sample drawings as permits, signed records, or operating permission.
"""
from copy import deepcopy

FOLDER_URL = "https://drive.google.com/drive/folders/1jIKHYSAZA7svu1927qdxGs1MWZO2s-3K"
README_URL = "https://docs.google.com/document/d/1ldQhkrjIGzRNjUCpFRPsN6hx4ceSVDt5MHX3-hePq2E/edit"


def _source(identity, title, drive_id, kind, pages, summary, limitations):
    return {"id": identity, "title": title,
            "url": README_URL if identity == "eqore_brief" else "https://drive.google.com/file/d/%s/view" % drive_id,
            "kind": kind, "page_count": pages, "access": "reviewed", "summary": summary,
            "limitations": limitations}


SOURCE_CATALOG = [
    _source("eqore_brief", "EQORE challenge brief / README", "1ldQhkrjIGzRNjUCpFRPsN6hx4ceSVDt5MHX3-hePq2E", "client_brief", None,
            "Option 4 is Compliance documentation at scale: track site documents, deadlines, changes and the information each party needs.",
            ["NFPA section references are quoted by the client brief; its table does not identify the applicable edition or confirm adoption at each site."]),
    _source("century_plan", "Full Engineered Plan Set.pdf", "16G4kOOd73SFwHW8agiF8O8eHzksmNE7L", "site_plan_set", 20,
            "EQORE Century-Tywood reference: 250 kW AC / 760 kWh; Gotion Edge 760; two Dynapower MPS125 inverters; Holliston, MA.",
            ["The 20-page supplied file does not contain every sheet named in its index.",
             "Revision B and date 01/11/2026 are printed on the drawings; date convention and current controlling revision need confirmation.",
             "Drawings and engineering stamps do not establish AHJ approval, inspection completion, utility PTO or as-built status."]),
    _source("bess_sample_1", "BESS IFC Sample 1.pdf", "1eaaFvw9uDC60DXiZYDLUA1nnC3uA8JqO", "comparison_plan_set", 14,
            "Anonymized 30 kW / 150 kWh Viridi RPS LINK-EX example with site/electrical drawings, data sheets and E-400 labels.",
            ["Project name and address are placeholders; it is not evidence of Century-Tywood's configuration.",
             "Voltage references differ by drawing context; an engineer must resolve the system boundary before reuse."]),
    _source("bess_sample_2", "BESS IFC Sample 2.pdf", "1gZ2Pk1yS7I57OICqKFmWmD-T7gG22tsh", "comparison_plan_set", 11,
            "Separate Delta example: 528 kWh, three 176 kWh cabinets and two PCS125 units derated to 99.5 kVA each (199 kVA total).",
            ["The table labels system size in kW but its value is written as 199 kVA; preserve the stated unit and seek engineering clarification.",
             "Contains California/DSA references; do not transfer these code assumptions or emergency-label wording to a Massachusetts site.",
             "The drawing says UL9540 and UL9540A listed. UL 9540A is a test method; request the actual report separately from system certification evidence."]),
    _source("lowland_map", "79 Lowland Street Map.pdf", "1XnXePGTqmZRWWmgDUZUhy2UP2KG9PDW7", "site_map", 1,
            "Holliston municipal map showing Lowland Street, surrounding parcels, zoning, buildings and hydrant symbols.",
            ["Printed 03/11/2025; the map states that it is for informational/planning purposes.",
             "It does not certify setbacks, hydrant accessibility, survey boundaries or approval of a battery location."]),
    _source("site_pole", "Copy of Power Pole.pdf", "1rZvFFN2hZ_Yp-qdOP6ie3O0uBnQfjJBz", "field_photo", 1,
            "Pole photograph with visible 54 and 6A markings; useful for reconciling site identifiers.",
            ["A photograph is not a utility-approved point-of-interconnection record."]),
    _source("site_bill", "Eversource utility bill (provided sample)", "1ZlW1imNO8lhY9TWcX6eQ2yJwXv9cn1bW", "utility_bill", 3,
            "Visual review associates Eversource delivery service with Tywood at 79 Lowland Street.",
            ["The supplied PDF's text encoding is unreliable; relevant header information was read visually.",
             "Account identifiers, balances and charges are excluded from this application reference.",
             "A bill does not prove interconnection approval or PTO."]),
    _source("site_panel", "Main Distribution Panel.pdf", "1AXVqh5yKuR7rFGkDyRjic5rIcjcVf3-H", "field_photo", 1,
            "Existing Cutler-Hammer switchboard/main disconnect and labeled feeder sections are visible.",
            ["A photograph alone does not verify spare capacity, available fault current, as-built wiring or an approved tie-in."]),
    _source("site_meter", "Revenue Meter.pdf", "1qzd5jUb6iEiurNZUictaDHIB3vb_h3l-", "field_photo", 1,
            "Honeywell Type A39SM revenue-meter photograph, consistent with the meter type called out in the plan.",
            ["Meter serials are omitted; readings and permission to modify utility equipment are not inferred."]),
    _source("site_transformer", "Transformer.pdf", "1jXUY6cfig3ivklRrP8aD_uLK9EPQLjwy", "field_photo", 1,
            "Howard Industries equipment-label photograph supports equipment identification.",
            ["Visible identification labels do not independently establish transformer electrical capacity or approved interconnection scope."]),
    _source("built_photo_1", "Sample Built Plan.jpeg", "1Cv9EQxN6UK8Qn3B16T7qQ0j4lgNdBaMd", "installation_photo", None,
            "Outdoor installation with EQORE-branded enclosure, Dynapower equipment, disconnects, labels and bollards.",
            ["No verified date/site association or approval status is supplied; resemblance to a drawing is not as-built acceptance."]),
    _source("built_photo_2", "Sample Built Plan 2.jpeg", "1Ls1ouCM9VYlHOYNQykspKdxVqEvU-zyC", "installation_photo", None,
            "Another installation photograph with multiple modular cabinets, disconnects, conduit and bollards.",
            ["Do not infer exact battery capacity, project identity, operating state or compliance from this photograph."]),
]

REFERENCE_CASES = [{
    "id": "century_tywood_reference",
    "name": "Century-Tywood J3 Corp",
    "site": "79 Lowland St, Holliston, MA",
    "city": "Holliston", "state": "MA",
    "case_kind": "source_reference",
    "current_stage": None,
    "system_power_kw": 250, "system_energy_kwh": 760,
    "battery_model": "Gotion Edge 760",
    "inverter_model": "2 x Dynapower MPS125",
    "utility": "Eversource (delivery service in supplied bill)",
    "authority": "Town of Holliston, MA (named AHJ in plan)",
    "industry": "Manufacturing; the site plan labels production, assembly, inspection and packing areas",
    "source_revision": "B", "source_date_as_printed": "01/11/2026",
    "source_refs": [{"source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"},
                    {"source_id": "site_bill", "page": 1}],
    "scope": "Outdoor battery system connected to the facility's main distribution panel, with site sensing and computing controls.",
    "verified_facts": [
        {"fact": "250 kW AC / 760 kWh, Gotion Edge 760 with two Dynapower MPS125 inverters", "source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"},
        {"fact": "The plan specifies a main-distribution-panel connection and current sensing; the proposed breaker is Eaton/Cutler-Hammer HKD3400F, 400 A.", "source_id": "century_plan", "page": 2, "sheet": "ESS-4.1"},
        {"fact": "The planned conduit route crosses a private driveway to an outdoor concrete pad; the package includes a 500 kVA isolation transformer and controls auxiliaries.", "source_id": "century_plan", "page": 3, "sheet": "ESS-5.0"},
        {"fact": "A single-line diagram identifies the point of interconnection, disconnects, sensing unit and battery/inverter connections.", "source_id": "century_plan", "page": 18, "sheet": "ESS-13.0"},
        {"fact": "The municipal map includes parcels, zoning and hydrant locations near Lowland Street.", "source_id": "lowland_map", "page": 1},
    ],
    "review_flags": [
        {"id": "missing_indexed_sheets", "title": "Request the complete controlling plan package", "owner_role": "Responsible engineer",
         "reason": "The supplied 20-page export indexes ESS-18 signage, ESS-19 fire resistance/suppression and ESS-20 NFPA 855 compliance, but those sheets are absent from this file.",
         "source_refs": [{"source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"}],
         "does_not_mean": "Absent from the shared sample is not evidence that the project's engineer never produced the sheets."},
        {"id": "pole_identifier_mismatch", "title": "Reconcile the utility pole reference", "owner_role": "Responsible engineer and utility interconnection contact",
         "reason": "The site plan calls out pole 54; the single-line diagram calls out 22/6A; the supplied photograph shows 54 and 6A. Confirm the identifier before the next utility submission.",
         "source_refs": [{"source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"},
                         {"source_id": "century_plan", "page": 18, "sheet": "ESS-13.0"},
                         {"source_id": "site_pole", "page": 1}]},
        {"id": "source_currency", "title": "Confirm the current equipment revision", "owner_role": "Responsible engineer",
         "reason": "Revision B records an inverter change to two Dynapower MPS125 units. Confirm that the utility package, commissioning plan, O&M manual and emergency plan all describe the current installed configuration.",
         "source_refs": [{"source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"}]},
    ],
    "unknowns": ["Current construction and operating stage", "Executed agreement and actual document deadlines",
                 "Current controlling plan revision and its full sheet set", "Issued permit numbers and inspection outcomes",
                 "Interconnection approval and utility PTO", "Commissioning results and current O&M/emergency records",
                 "Confirmed applicable code editions and AHJ-specific requirements", "Project budget and actual expenditure"],
    "scenario_assumptions": ["Any demo status, deadline, signer assignment or incoming message attached to this reference case must be labeled as an authored test scenario.",
                             "This source case must not overwrite the facts or approval histories of existing demonstration projects."],
}]


def _requirement(identity, title, phase, owner_role, audience, evidence, triggers,
                 section="Option 4", depends_on=None, contents=None):
    return {"id": identity, "title": title, "phase": phase, "owner_role": owner_role,
            "audience": audience, "completion_evidence": evidence, "update_triggers": triggers,
            "depends_on": depends_on or [], "expected_contents": contents or [],
            "coordination_note": "Owner roles, dependency ordering and evidence checks are proposed workflow rules derived from the brief; they are not quoted statutory requirements.",
            "source_refs": [{"source_id": "eqore_brief", "section": section}],
            "authority_note": "Client-brief workflow requirement. Confirm applicability, adopted edition and acceptance criteria with the responsible engineer/AHJ/utility. A prepared file or email is not approval."}


DOCUMENT_REQUIREMENTS = [
    _requirement("interconnection_application", "Utility interconnection application", "Reviews", "Responsible engineer", ["Utility", "EQORE"],
                 "Submitted current application with utility reference and the exact plan/equipment revision.",
                 ["Equipment or capacity change", "Point-of-interconnection change", "Utility comments"], contents=["Site and service information", "Current single-line diagram", "Equipment schedule", "Utility submission reference"]),
    _requirement("interconnection_approval", "Utility interconnection approval", "Reviews", "Utility interconnection contact", ["Utility", "EQORE", "Facility"],
                 "Official utility approval or executed interconnection agreement with scope, conditions and revision recorded.",
                 ["Changed approved equipment or settings", "Expired or amended utility approval"], depends_on=["interconnection_application"]),
    _requirement("building_permit", "Building permit and conditions", "Reviews", "AHJ permit contact", ["AHJ", "EQORE", "Facility", "EPC"],
                 "Issued building permit with permit number, approved scope, conditions and any expiry date.",
                 ["Layout or structural change", "Permit expiry", "AHJ correction notice"]),
    _requirement("electrical_permit", "Electrical permit and conditions", "Reviews", "Electrical contractor", ["AHJ", "EQORE", "Facility", "Electrical contractor"],
                 "Issued electrical permit with issuer, permit reference and controlling drawing revision.",
                 ["Electrical scope or equipment change", "Permit expiry", "Inspector comments"]),
    _requirement("fire_permit", "Fire approval and conditions", "Reviews", "Fire authority contact", ["AHJ", "Fire authority", "EQORE", "Facility"],
                 "Official fire-review acceptance/permit and its conditions, identified separately from other permits.",
                 ["Battery chemistry, quantity or location change", "Fire-protection change", "Fire-authority comments"]),
    _requirement("building_inspection", "Building inspection sign-off", "Verification", "AHJ inspector", ["AHJ", "EQORE", "Facility"],
                 "Dated inspection result identifying the site, permit and disposition; correction closure if applicable.",
                 ["Failed inspection", "Subsequent work within the permitted scope"], depends_on=["building_permit"]),
    _requirement("electrical_inspection", "Electrical inspection sign-off", "Verification", "Electrical inspector", ["AHJ", "Utility", "EQORE", "Facility"],
                 "Official inspection sign-off or certificate for the permitted installation; unresolved corrections remain open.",
                 ["Failed inspection", "Reworked electrical installation"], depends_on=["electrical_permit"]),
    _requirement("fire_inspection", "Fire inspection sign-off", "Verification", "Fire authority contact", ["AHJ", "Fire authority", "EQORE", "Facility"],
                 "Dated fire inspection acceptance and documented closure of required corrections.",
                 ["Failed inspection", "Fire-protection or access change"], depends_on=["fire_permit"]),
    _requirement("commissioning_plan", "Commissioning plan", "Verification", "Commissioning lead", ["AHJ", "Facility", "EQORE"],
                 "Reviewed site-specific plan identifying the current equipment, responsible personnel and test/checklist package before commissioning.",
                 ["Before commissioning", "Equipment or protection-system change", "Revised commissioning scope"],
                 section="Documents NFPA 855 requires for every site / commissioning (6.1)",
                 contents=["Roles and qualified service personnel", "Applicable fire detection, suppression and ventilation tests", "Checklists and logs", "Staff training plan", "Current drawings"]),
    _requirement("commissioning_report", "Commissioning report and issue closure", "Verification", "Commissioning lead", ["AHJ", "Facility", "EQORE"],
                 "Completed test records, responsible-person sign-off, issue resolutions and recorded distribution to the owner/AHJ; retain in the O&M manual.",
                 ["After commissioning tests", "Retest after correction", "Before final inspection per client brief"],
                 section="Documents NFPA 855 requires for every site / commissioning (6.1)", depends_on=["commissioning_plan"],
                 contents=["Actual test results", "Exceptions and resolutions", "Training records", "As-built references", "Owner/AHJ distribution record"]),
    _requirement("utility_pto", "Utility permission to operate (PTO)", "Handoff", "Utility interconnection contact", ["Utility", "EQORE", "Facility"],
                 "Explicit written utility authorization for this site and configuration; application receipt, signatures and inspection completion alone do not satisfy it.",
                 ["Before authorized operation", "Utility conditions or approved configuration change"],
                 depends_on=["interconnection_approval", "electrical_inspection", "commissioning_report"]),
    _requirement("as_built_package", "As-built drawing package", "Handoff", "Responsible engineer", ["AHJ", "Facility", "EQORE"],
                 "Revision-controlled installed-condition drawings reviewed by the responsible engineer, linked from commissioning and O&M records.",
                 ["Field change", "Equipment replacement", "Commissioning closeout"], section="Documents NFPA 855 requires for every site / commissioning and decommissioning",
                 contents=["Installed equipment schedule", "Single-line diagram", "Layout and disconnect locations", "Changes from issued design"]),
    _requirement("signage_labels", "Signage, labels and safety-data record", "Handoff", "Electrical contractor", ["AHJ", "First responders", "Facility", "EQORE"],
                 "Current approved label schedule and installation evidence tied to disconnect/system locations; responsible review of safety-data availability.",
                 ["Before operation", "Equipment, disconnect or hazard information change", "Missing or damaged label"],
                 section="Client brief: safety-data sheets (7.1.3); confirm separate code basis for hazard/disconnect labels",
                 contents=["Hazard and disconnect labels", "System labels", "Safety-data location", "Dated installation photos and review"]),
    _requirement("om_manual", "Operations and maintenance manual", "Handoff", "Fleet operations lead", ["AHJ", "First responders", "Facility", "EQORE"],
                 "Reviewed manual for the installed system before operation, with controlled revision and access/distribution recorded.",
                 ["Before operation", "Equipment, set-point or service-contact change", "Revised manufacturer instructions"],
                 section="Documents NFPA 855 requires for every site / O&M (4.1.2.3, 6.3, 7.1-7.3)",
                 depends_on=["as_built_package", "commissioning_report"],
                 contents=["System size and components", "Manufacturer manuals", "Service contacts", "Operating settings and procedures", "Changes requiring re-permitting", "Maintenance schedule"]),
    _requirement("emergency_plan", "Emergency operations plan", "Handoff", "Facility operations lead", ["Facility", "EQORE"],
                 "Current site-specific plan reviewed by responsible personnel, with on-site availability confirmed and any responder-facing extract explicitly approved.",
                 ["Before occupied-facility operation", "Conditions affecting emergency response change", "Revised alarm, isolation or contact details"],
                 section="Documents NFPA 855 requires for every site / emergency plan (4.1.3.2.1)",
                 contents=["Reviewed shutdown/isolation information", "BMS-alarm response", "Fire/explosion/release response", "Damaged-equipment handling", "Drill procedures and schedule"]),
    _requirement("maintenance_log", "Operations and maintenance log", "Operations", "Fleet operations lead", ["AHJ", "First responders", "Facility", "EQORE"],
                 "Dated service entry recording action, responsible person, result, issues and linked test or repair evidence.",
                 ["Every maintenance action", "Every test or repair", "Next scheduled service due"],
                 section="Documents NFPA 855 requires for every site / operations record (7.1-7.3)", depends_on=["om_manual"]),
    _requirement("training_record", "Staff training and drill record", "Operations", "Facility operations lead", ["AHJ", "Facility", "EQORE"],
                 "Dated record of training/drill scope, participants, responsible trainer and follow-up issues.",
                 ["Commissioning training", "New staff or revised procedures", "Scheduled drill"],
                 section="Documents NFPA 855 requires for every site / commissioning, operations and emergency plan", depends_on=["emergency_plan", "om_manual"]),
    _requirement("performance_report", "Performance report", "Operations", "Fleet operations lead", ["Facility", "EQORE"],
                 "Period-specific operating/performance report with source data and review recorded.",
                 ["Agreed reporting deadline", "Significant operating change"], contents=["Reporting period", "Source data", "Exceptions and follow-up"]),
    _requirement("decommissioning_plan", "Decommissioning plan and AHJ notice", "Decommissioning", "Responsible engineer", ["AHJ", "Facility", "EQORE"],
                 "Reviewed plan before decommissioning plus documented advance AHJ notification; do not mark overdue merely because installation is underway.",
                 ["Decommissioning scheduled", "Changed equipment condition or removal method"],
                 section="Documents NFPA 855 requires for every site / decommissioning (8.1-8.3)",
                 contents=["Roles", "As-built/as-maintained drawings", "Schedule and checklists", "Adjacent-system protection", "Issue-resolution plan"]),
    _requirement("decommissioning_report", "Decommissioning completion report", "Decommissioning", "Responsible engineer", ["AHJ", "Facility", "EQORE"],
                 "Completed removal/activity logs, issues and resolutions, final report and distribution record after decommissioning.",
                 ["After decommissioning", "Outstanding closeout correction"],
                 section="Documents NFPA 855 requires for every site / decommissioning (8.1-8.3)", depends_on=["decommissioning_plan"]),
]


# These are review aids, separate from the 12 client-supplied files. A published
# edition is not automatically the edition adopted for an existing permit.
STANDARDS_REFERENCES = {
    "nfpa_855": {
        "title": "NFPA 855 publication and edition information",
        "url": "https://www.nfpa.org/codes-and-standards/nfpa-855-standard-development/855",
        "section": "2026 published edition; verify the edition adopted for this site",
        "basis": "Publisher edition metadata; full adopted clause text still requires responsible review",
    },
    "ma_fire": {
        "title": "Massachusetts fire-code adoption",
        "url": "https://www.mass.gov/info-details/massachusetts-fire-code",
        "section": "527 CMR 1.00 / NFPA 1 (2021); proposed October 2026 amendments are not adopted rules",
        "basis": "Massachusetts Department of Fire Services; checked 2026-11-07",
    },
    "ma_ess": {
        "title": "Massachusetts battery-storage guidance",
        "url": "https://www.mass.gov/doc/guidance-on-electric-battery-storage-and-electric-vehicle-chargersaugust-2025/download",
        "section": "August 2025 appendix: NFPA 855 (2020) referenced by the state fire code",
        "basis": "State guidance; reconcile with current code and the permit's accepted basis",
    },
    "ma_building": {
        "title": "Massachusetts building-code adoption",
        "url": "https://www.mass.gov/handbook/tenth-edition-of-the-ma-state-building-code-780",
        "section": "780 CMR tenth edition / 2021 IBC with state amendments",
        "basis": "State code page; permit timing and existing-building scope need review",
    },
    "ma_electrical": {
        "title": "Massachusetts electrical-code adoption",
        "url": "https://www.mass.gov/info-details/massachusetts-electrical-code",
        "section": "527 CMR 12.00 / NFPA 70 (2026), effective April 24, 2026",
        "basis": "State code page; do not overwrite the accepted basis of an earlier permit",
    },
    "ul_ess": {
        "title": "UL ESS certification and fire testing",
        "url": "https://www.ul.com/services/energy-storage-system-testing-and-certification",
        "section": "UL 9540 system certification; UL 9540A thermal-runaway propagation test method",
        "basis": "UL Solutions; certification and fire-test evidence are different records",
    },
    "ma_interconnection": {
        "title": "Massachusetts interconnection process",
        "url": "https://www.mass.gov/doc/interconnection-factsheet/download",
        "section": "May 2025 process overview; utility review and completion documentation",
        "basis": "State process guidance; exact tariff, review track and utility conditions remain site-specific",
    },
}

# Evidence checklist additions are PM review prompts. They do not claim that the
# app has inspected a certificate, read a full code clause, or granted approval.
_EVIDENCE_DETAILS = {
    "interconnection_application": [
        "Utility tariff/review track and service territory; do not infer the simplified track from the battery size alone",
        "Exact battery and inverter model/count, kW and kWh separately, export mode and protection/settings revision",
        "Manufacturer cut sheets and utility-requested certification/test evidence; verify the submitted combination matches the plan",
        "Reconciled service, meter and point-of-interconnection identifiers; log discrepancies before submission",
    ],
    "interconnection_approval": [
        "Utility-issued approval-to-install/agreement and conditions, with current equipment and drawing revisions",
        "Explicit distinction between application receipt, permission to construct and permission to operate",
    ],
    "building_permit": [
        "Permit-date code basis: jurisdiction, adopted IBC/state edition, local amendments and AHJ conditions",
        "Site layout, pad/anchoring and structural package identifiers tied to the accepted plan revision",
    ],
    "electrical_permit": [
        "Permit-date NFPA 70/NEC edition, state amendments and applicable ESS Article 706 review recorded by the electrical reviewer",
        "Current single-line, equipment ratings, grounding/protection and disconnect/label drawing references",
    ],
    "fire_permit": [
        "AHJ-confirmed NFPA 1/855 or IFC code basis, edition, local amendments and site-specific conditions",
        "Exact system certification scope under UL 9540 and a separate UL 9540A test report where required by the applicable design/approval basis",
        "Manufacturer installation instructions and engineer review of the tested equipment configuration, layout, spacing and fire-protection assumptions",
        "Current fire-protection, access, signage and emergency-plan sheet/revision references; resolve omitted indexed sheets",
        "Record the authority's acceptance or requested corrections; a product data sheet is not a fire approval",
    ],
    "building_inspection": [
        "Inspection type/stage, permit and accepted drawing revision; separate each required inspection and correction closure",
    ],
    "electrical_inspection": [
        "Inspector-issued outcome and stage, equipment/drawing revision and outstanding corrective items",
        "Utility-required certificate of completion or municipal sign-off, if applicable, retained separately from PTO",
    ],
    "fire_inspection": [
        "Accepted fire-review scope, installed configuration, relevant safety-system test references and correction closure",
        "Verify labels, safety-data location and emergency information against the approved site package",
    ],
    "commissioning_plan": [
        "Document the NFPA 855 edition and client-cited section 6.1 as a review pointer; confirm the applicable clause with the reviewer",
        "Battery/inverter identifiers and current drawing revision, operating mode, set points and applicable manufacturer test procedures",
        "Test matrix for installed alarms, interlocks and safety systems; record why any detection, suppression or ventilation item is not applicable",
        "Acceptance criteria, qualified personnel, witness/approval needs and issue-resolution responsibilities",
    ],
    "commissioning_report": [
        "Dated, signed results against the approved test matrix, actual equipment/settings revision and measured outcomes",
        "Open defects, retest results and closure evidence; a completed signature envelope alone is not a passed test",
        "Evidence of owner/AHJ delivery at the required milestone and incorporation into the controlled O&M package",
    ],
    "utility_pto": [
        "Utility closeout reference, municipal inspection/certificate of completion and witness-test or waiver records as required by that utility",
        "Any required meter/protection changes, approval conditions and explicit effective authorization for this configuration",
    ],
    "as_built_package": [
        "Installed model/count, battery chemistry/capacity, inverter rating, isolation equipment, disconnects and protection/settings revision",
        "Engineer-reviewed field deviations, including label, access and safety-system changes; linked approvals where required",
    ],
    "signage_labels": [
        "Separate the SDS requirement cited as NFPA 855 7.1.3 from hazard/system/disconnect marking requirements in the applicable code and manufacturer instructions",
        "Record the SDS posting location relative to the disconnect or the AHJ-approved alternative; check outdoor weather protection",
        "Exact equipment and hazard information, disconnect identifiers, revision, dated installation photos and responsible reviewer",
    ],
    "om_manual": [
        "Controlled manufacturer manuals matching the installed battery/inverter combination and current as-built/settings revision",
        "Reviewed startup, inspection and maintenance procedures for the installed alarms, interlocks, controls and safety systems",
        "Site-specific maintenance intervals and next service dates set from manufacturer/AHJ/owner requirements, not a universal generated cadence",
        "Service/test/training records and a record of who can obtain the current approved manual",
    ],
    "emergency_plan": [
        "Site-specific, responsible-person-approved response material; do not generate unreviewed shutdown or firefighting instructions",
        "Current equipment, hazard/SDS information, isolation/disconnect locations, access map and responsible contact revisions",
        "Record on-site availability, drill/training schedule and approved audience-specific copies",
    ],
    "maintenance_log": [
        "Equipment/component identifier and manual/procedure revision, dated action/test/repair, person, result and unresolved issue",
        "Next service date only when established by the site's reviewed maintenance schedule",
    ],
    "training_record": [
        "Procedure/plan revision used, attendance, trainer qualification, drill outcome and follow-up actions",
    ],
    "performance_report": [
        "Owner/contract/program reporting basis and period; this client-requested record is not asserted as a universal NFPA 855 obligation",
    ],
    "decommissioning_plan": [
        "Confirm the applicable edition/AHJ's submission timing; the client's starter timing is not proof that no earlier plan is required",
        "Current as-maintained equipment and drawings, responsible qualified parties, reviewed removal/protection scope and advance AHJ notification",
    ],
    "decommissioning_report": [
        "Actual activity/checklist records, qualified parties, issues/resolutions, adjacent-system protection and final distribution record",
    ],
}
_STANDARDS_BY_REQUIREMENT = {
    "interconnection_application": ["ma_interconnection", "ul_ess"],
    "interconnection_approval": ["ma_interconnection"],
    "building_permit": ["ma_building"], "building_inspection": ["ma_building"],
    "electrical_permit": ["ma_electrical"], "electrical_inspection": ["ma_electrical", "ma_interconnection"],
    "fire_permit": ["ma_fire", "ma_ess", "ul_ess"], "fire_inspection": ["ma_fire", "ma_ess"],
    "utility_pto": ["ma_interconnection"],
    "commissioning_plan": ["nfpa_855", "ma_ess"], "commissioning_report": ["nfpa_855", "ma_ess"],
    "as_built_package": ["nfpa_855"], "signage_labels": ["nfpa_855", "ma_electrical"],
    "om_manual": ["nfpa_855", "ma_ess"], "emergency_plan": ["nfpa_855", "ma_ess"],
    "maintenance_log": ["nfpa_855"], "training_record": ["nfpa_855"],
    "decommissioning_plan": ["nfpa_855"], "decommissioning_report": ["nfpa_855"],
}
for _item in DOCUMENT_REQUIREMENTS:
    _item["expected_contents"].extend(_EVIDENCE_DETAILS.get(_item["id"], []))
    _item["source_refs"].extend(deepcopy(STANDARDS_REFERENCES[key]) for key in _STANDARDS_BY_REQUIREMENT.get(_item["id"], []))
    _item["verification_scope"] = "Tracks evidence and human review; does not validate document content against code clauses or determine legal compliance."
    _item["code_basis_status"] = "site_confirmation_required"

REFERENCE_CASES[0]["review_flags"].append({
    "id": "code_basis_reconciliation", "title": "Confirm the permit's adopted code editions",
    "owner_role": "Responsible engineer and AHJ",
    "reason": "The cover lists 2020 references for NFPA 1/855/70 and calls 527 CMR 12.00 a building code. Massachusetts identifies 527 CMR 12.00 as electrical code and currently uses NFPA 70 (2026), effective April 24, 2026. Its fire-code guidance references NFPA 1 (2021) and NFPA 855 (2020). Record the permit date and accepted basis before reusing this cover.",
    "does_not_mean": "A newer published edition does not automatically invalidate an earlier accepted permit. NFPA 855 (2026) publication is not proof that Massachusetts adopted that edition.",
    "source_refs": [{"source_id": "century_plan", "page": 1, "sheet": "ESS-1.0"},
                    deepcopy(STANDARDS_REFERENCES["ma_electrical"]), deepcopy(STANDARDS_REFERENCES["ma_fire"]),
                    deepcopy(STANDARDS_REFERENCES["ma_ess"])],
})


def calibration_reference():
    """Return a detached, JSON-friendly source catalog for read-only display."""
    return deepcopy({
        "reviewed_at": "2026-11-07", "folder_url": FOLDER_URL,
        "focus": "Option 4: Compliance documentation at scale",
        "source_count": len(SOURCE_CATALOG), "sources": SOURCE_CATALOG,
        "reference_cases": REFERENCE_CASES, "requirements": DOCUMENT_REQUIREMENTS,
        "standards_references": list(STANDARDS_REFERENCES.values()),
        "boundaries": [
            "Client-brief section pointers and official edition references guide document review; the permit-specific adopted basis and full clause text still require confirmation.",
            "Current record means evidence and PM review are recorded. The app does not certify technical content or legal compliance.",
            "Access audiences are a proposed document-sharing specification, not permission grants or implemented access controls.",
            "Source drawings and photographs provide context, not proof of permits, inspections, signatures, commissioning or PTO.",
            "Existing project statuses, budgets, people and deadlines are not replaced by this reference material.",
        ],
    })
