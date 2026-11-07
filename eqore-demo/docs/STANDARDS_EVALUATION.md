# Document specificity evaluation — 7 November 2026

## Assessment

Relay is a useful, source-linked paperwork coordinator for EQORE's option 4. It is **partly specific to NFPA 855 and the other named rules, but it is not a code-compliance validator**. The document categories and lifecycle logic are grounded in the client brief. A `Current record` status means a current document revision has completion evidence and a recorded PM review; it does not prove that an engineer has checked every applicable clause or that an AHJ has approved the installation.

All 12 client-shared files were readable. The shared packet contains drawings, examples, photographs and the brief; it does not include a complete set of issued permits, actual inspection results, PTO, commissioning results, or current O&M and emergency documents for a live project. The assessment therefore distinguishes the **application's checklist specificity** from the **actual site's compliance**, which cannot be determined from this packet.

## Scorecard

| Dimension | Assessment | Evidence / limit |
| --- | --- | --- |
| EQORE option 4 document coverage | Strong | Twenty distinct catalog categories cover utility applications/approvals, three permit and inspection tracks, commissioning, as-builts, labels/SDS, O&M, emergency planning, training, performance and decommissioning. These are categories, not a claim that every site has exactly twenty mandatory files. |
| NFPA 855 content detail | Partial, improved this round | The client-cited section pointers now have more concrete equipment, procedure, test, distribution and change-control evidence prompts. Exact adopted-edition clause checking is still absent. |
| Equipment / plan specificity | Partial | The Century-Tywood reference is tied to its model, inverter count, ratings, revision and sheet references. Existing active projects are not silently relabeled as this real site. The engine does not yet extract and compare every uploaded file's model/settings against project facts. |
| Jurisdiction and edition control | Partial | Official adoption references and an explicit code-basis discrepancy are recorded. There is no per-project approved code/edition matrix with an AHJ acceptance record yet. |
| Document revision and authority logic | Good foundation | Generic packets do not automatically satisfy distinct permits. Applications, signatures, inspections and PTO remain different records. Changed prerequisites and stale reviews require follow-up. |
| Content validation | Missing | Checklist text and a human review do not verify certificate scope, test results, professional qualifications, SDS placement, the full contents of a report, or regulatory acceptance. |
| Audience access and operations records | Partial | Intended audiences and later-life records are modeled. First-responder public extracts, authenticated AHJ/facility access, approved access policies and recurring service-record instances are not a complete production workflow. |

The practical readiness judgment is: **suitable for demonstrating document coordination and review handoffs; not ready to declare a site “NFPA 855 compliant.”**

## Requirements checked against the client brief

The section numbers below are the client's pointers, not an independently verified clause-by-clause transcription. The README does not identify an edition for its table. NFPA currently publishes a 2026 edition; the publisher page alone is insufficient to apply its contents to a Massachusetts permit. [EQORE brief](https://docs.google.com/document/d/1ldQhkrjIGzRNjUCpFRPsN6hx4ceSVDt5MHX3-hePq2E/edit), [NFPA publication information](https://www.nfpa.org/codes-and-standards/nfpa-855-standard-development/855).

| Record group | Client pointer / other basis | What the current checklist asks for | Remaining verification |
| --- | --- | --- | --- |
| Commissioning plan and report | NFPA 855 §6.1, as cited in the brief | Current battery/inverter and drawing/settings revision; applicable alarm, interlock and safety-system tests; qualified roles; acceptance criteria; actual results; defect closure; training; as-builts; owner/AHJ distribution and O&M inclusion | Confirm full requirements and timing in the accepted edition; obtain actual tests, sign-offs and delivery records. A signed cover is not a passed test. |
| O&M manual and operations record | Client cites §§4.1.2.3, 6.3, 7.1–7.3 and electronic record §7.1.6.2 | Manufacturer manuals for the installed combination; reviewed procedures and maintenance intervals; service/test/training entries with dates, people and outcomes | Validate manual completeness, actual access, scheduled recurring work and installed settings. Do not invent an annual interval. |
| Emergency operations plan | Client cites §4.1.3.2.1 | Reviewed site-specific response material, hazards/SDS, equipment/isolation/access references, current contacts, on-site availability and training/drill records | Qualified review of procedures and current site conditions; approved audience-specific extracts. The app must not invent firefighting or isolation instructions. |
| Decommissioning plan and report | Client cites §§8.1–8.3 | Current as-maintained package, parties, reviewed scope, schedule/checklists, adjacent-system protection, AHJ notice, actual closeout records | Confirm the adopted edition/AHJ's submission timing. “Before decommissioning” in the starter brief does not establish that an earlier plan is unnecessary. |
| Labels and SDS | Client cites §7.1.3 for SDS; other markings require their own code/manufacturer basis | Separate SDS location/weather-protection review from hazard, system and disconnect labels; exact equipment/locations, dated installation evidence and reviewer | Review complete adopted clauses and the installed labels. The supplied Century-Tywood export omits its indexed signage sheet. |
| Building/electrical/fire permits and inspections | State/local code and authority process, not all NFPA 855 | Separate authority-issued records, permit identifiers, accepted revisions, conditions, inspection stage and corrective closure | Current municipality-specific forms/checklists, code basis and actual issued outcomes. One generic completed “permit” cannot cover all three tracks. |
| Interconnection and PTO | Utility tariff and accepted project conditions | Exact equipment/settings/export mode and point of interconnection; submission/approval references; completion and inspection evidence; explicit operating authorization | Confirm service territory, applicable tariff/review track, required witness/meter work and actual utility authorization. No assumed simplified track or universal deadline. |
| Performance reports | Client's option 4 lifecycle scope | Reporting basis, period, source data, review and exceptions | Identify owner/contract/program requirement; do not label this a universal NFPA 855 obligation. |

## Current adoption and source issues

### Massachusetts code basis must be recorded per permit

As reviewed on 7 November 2026:

- The state fire-code page identifies the 2021 NFPA 1 basis and distinguishes proposed October 2026 amendments from adopted rules. State battery-storage guidance identifies NFPA 855 (2020) as the referenced edition. These references support a Massachusetts review starting point; the site's accepted permit conditions still matter. [Massachusetts fire code](https://www.mass.gov/info-details/massachusetts-fire-code), [August 2025 state BESS guidance, appendix](https://www.mass.gov/doc/guidance-on-electric-battery-storage-and-electric-vehicle-chargersaugust-2025/download).
- The building-code page identifies 780 CMR tenth edition and its 2021 IBC basis with Massachusetts amendments. The ninth/tenth edition concurrency period ended June 30, 2025. [Massachusetts building code](https://www.mass.gov/handbook/tenth-edition-of-the-ma-state-building-code-780).
- The electrical-code page identifies NFPA 70 (2026) with state amendments, effective April 24, 2026. [Massachusetts electrical code](https://www.mass.gov/info-details/massachusetts-electrical-code).

Century-Tywood sheet ESS-1.0 lists 2020 references for NFPA 1, 855 and 70, and incorrectly names 527 CMR 12.00 as a building code. Its engineer/AHJ should reconcile those references with the permit date and accepted basis. This is not proof that an existing permit is invalid, nor a reason to replace every NFPA 855:2020 reference with 2026. The app now surfaces that specific follow-up. [Supplied plan, page 1](https://drive.google.com/file/d/16G4kOOd73SFwHW8agiF8O8eHzksmNE7L/view).

IFC §1207, IBC and NEC Article 706 are relevant pointers supplied by EQORE. They must not be merged into a single universal rule set: adoption, amendments, permit timing, occupancy, equipment and installation conditions matter. The California/DSA comparison plan and anonymized sample listing 2024 IBC/IFC plus 2023 NEC are not a Massachusetts code basis.

### Equipment certification is not a fire-test report

UL identifies UL 9540 as the system/equipment safety standard and UL 9540A as the thermal-runaway fire-propagation test method. Battery and inverter component references (for example UL 1973 and UL 1741) do not, by themselves, establish certification of every assembled system configuration. The app now asks for exact certification scope and a separate relevant fire-test report where required by the accepted design basis. [UL Solutions](https://www.ul.com/services/energy-storage-system-testing-and-certification).

One supplied comparison drawing says “UL9540 AND UL9540A LISTED.” Do not propagate that wording as proof of two listings. Obtain the certification and test records and confirm the relevant models/configuration. A vendor brochure, drawing note or an LLM summary is insufficient.

### Utility approval has its own evidence chain

Massachusetts describes application/review, construction, completion documentation and utility permission as separate process steps. Relay preserves that separation; neither an equipment approval nor a signed DocuSign envelope establishes PTO. The exact utility conditions remain project-specific. [Massachusetts interconnection overview](https://www.mass.gov/doc/interconnection-factsheet/download).

## Changes made in this review

`client_reference.py` now includes:

- More specific evidence prompts for all twenty existing categories, without changing requirement IDs or dependency ordering.
- Official edition/adoption references shown alongside the client brief, kept separate from the twelve-file client inventory.
- A code-basis reconciliation flag for Century-Tywood, alongside missing-sheet, pole-identifier and equipment-revision flags.
- Explicit distinctions between UL certification and testing, SDS and other markings, document completion and technical acceptance, and published versus adopted editions.
- Exact-equipment/configuration prompts that flow into the coverage view and new tracked-document drafts.

These improvements make the work more grounded. They do not implement full code-text checking or silently certify source documents.

## Exact missing inputs to request from EQORE

For one pilot site, request these in order:

1. **Accepted code basis:** permit application/issue dates, AHJ, accepted code/edition list and local amendments, plus reviewer conditions or approved exceptions. Ask the responsible engineer to reconcile ESS-1.0 rather than asking the PM to choose editions.
2. **Controlling equipment and plan package:** current full stamped/accepted set including indexed ESS-18/19/20, as-built deviations if installed, exact battery/inverter model/count and current protection/settings revision; resolve pole 54 versus 22/6A.
3. **Manufacturer evidence:** UL 9540 certification scope for the actual configured system, applicable UL 9540A report(s), installation/O&M instructions and SDS; identify report/model/revision and any installation limitations.
4. **Issued authority and utility records:** separate building/electrical/fire permits and inspection outcomes, correction notices/closures, the utility application/agreement and conditions, completion/witness/meter records where required, and actual PTO if issued.
5. **Operating-document examples:** reviewed commissioning plan/results and defect log, current O&M and emergency plans, label/location evidence, training/service logs, actual due/review dates, and the responsible reviewer for each.
6. **Distribution policy:** which approved version each of EQORE, facility, AHJ and first responders may see, what is public, and the designated person who approves emergency extracts and changes.

These inputs support a narrow, real pilot. Do not request every future lifecycle document as immediately overdue for an installation-stage project.

## Pressure-test cases that matter next

1. Submit a UL 9540A report as if it were a UL 9540 system certificate; the technical reviewer must not treat it as equivalent.
2. Replace the inverter model after utility approval; require review of the application, accepted configuration, commissioning and operating records.
3. Upload a signed commissioning cover without test results or unresolved-defect closure; signature completion must remain distinct from technical acceptance.
4. Supply a generic combined permit packet; do not automatically fulfill building, electrical and fire requirements.
5. Apply a California sample's labels and code edition to Holliston; flag site/edition mismatch rather than accept copied references.
6. Treat NFPA's newest publication as automatically adopted in Massachusetts; require the permit-specific basis.
7. Provide an application acknowledgement or inspection result as PTO; block the equivalence.
8. Reach handoff with omitted signage/fire/NFPA sheets; request the controlling full set, without claiming the real engineer never produced them.
9. Change emergency contacts/isolation references after PM review; return the affected record to review.
10. Ask an LLM to invent missing emergency procedures or declare compliance from a photo; retain the gap and route to the responsible reviewer.

Cases 1, 3, 5, 6, 8 and 10 expose content-review capabilities that are not currently deterministic validators. They should be reported as capability gaps, not counted as passed merely because a checklist exists. Existing engine tests can verify record authority, revision, dependency, timing and access behavior separately.

## Verification limits

The official public pages establish edition/adoption metadata and the certification/test distinction. Full adopted NFPA 855 clause text was not independently read through the free-access viewer in this review; a verified clause matrix remains outstanding. Some Mass.gov direct page/PDF fetches returned 403 while their official indexed text was readable. This does not affect access to EQORE's twelve shared files, but it limits primary-text verification of the full regulations. No current code-certification claim should be made from this review.

The source enrichment passed the existing 14 compliance tests, and an additional catalog integrity check verified all twenty IDs, dependency references, valid HTTPS source links, detached JSON output and coverage of the enriched checklists.
