# EQORE client calibration — 7 November 2026

## Source and scope

The [client's shared folder](https://drive.google.com/drive/folders/1jIKHYSAZA7svu1927qdxGs1MWZO2s-3K) contains 12 readable files in the root and two subfolders. The [README](https://docs.google.com/document/d/1ldQhkrjIGzRNjUCpFRPsN6hx4ceSVDt5MHX3-hePq2E/edit) calls option 4 **Compliance documentation at scale**. This supersedes the older team brief's characterization of option 4 as installation coordination for this module.

The immediate PM workflow remains post-signing: identify missing or outdated records, assign their preparation/review, preserve original emails and signatures, and advance the right next document. The client brief also covers operational records and eventual decommissioning. These are separate later-life requirements; commissioning does not make a decommissioning report immediately overdue. Crew, delivery and procurement tools remain accessible under Site coordination.

## Material reviewed

`client_reference.py` provides a source inventory, source-linked observations, a Century-Tywood reference case and the document catalog. No downloaded bills, photos or full drawings are copied into the source repository or served by the local HTTP server. Links point to the supplied Drive originals. Billing identifiers, amounts and private contact details are excluded from the reference data.

| Material | Use | Important limit |
| --- | --- | --- |
| README | Document types, update triggers, intended readers | Client-provided specification; adopted editions and site applicability still require review |
| Full Engineered Plan Set, 20 pages | Century-Tywood, Holliston: 250 kW AC / 760 kWh, Gotion Edge 760 and two Dynapower MPS125 units | Missing indexed sheets; no inferred permit, inspection, PTO or current construction state |
| BESS IFC Sample 1, 14 pages | Comparison of drawing and labeling structure | Separate 30 kW / 150 kWh Viridi example |
| BESS IFC Sample 2, 11 pages | Comparison of equipment schedules, drawings and signage | Separate Delta example; preserve 199 kVA as written, do not silently convert to kW |
| Lowland municipal map | Site and parcel context | Planning information, not a certified survey or approved battery location |
| Pole, panel, meter and transformer PDFs | Field evidence and identifier comparison | Photos cannot establish electrical adequacy or authority approval |
| Eversource bill, 3 pages | Delivery-utility context for the supplied site | Not interconnection approval; sensitive account values excluded |
| Two built-plan photographs | Installation/label evidence examples | Site identity, date, operating state and acceptance unverified |

The plan's pole reference is inconsistent across the cover sheet, single-line diagram and supplied photograph. The reference case exposes the discrepancy and the responsible engineer/utility follow-up. An indexed sheet absent from this export means missing from the shared sample, not that the engineer never produced it.

## Application behavior

- Existing D01–D20 records, signatures, provider IDs, stored profiles and archives are preserved. A generic completed packet is related evidence to review, not automatic coverage of every specific requirement.
- Each project exposes a read-only `compliance_review` with required evidence, responsible role, timing, update trigger, intended audience, related records and source links.
- `track_requirement` adopts one catalog item as `C_<requirement_id>` with an explicit PM-selected due timestamp. It creates a local draft and an audit event, sends nothing, and enters the existing document/revision/email workflow.
- `set_requirement_review` records an explicit next-review date, a dated site change, or a review of a completed current revision. It never modifies a signature or regulatory acceptance. Current-record review is not a legal compliance certification.
- Review dates and changes are explicit. No universal renewal interval is guessed. Later-life items remain separate until the project phase or an explicit deadline makes them relevant.
- Archived projects show retrospective coverage gaps without changing the archived snapshot or allowing writes.
- The source case is a reference, not a new live project. Its actual status, deadlines, costs and counterpart assignments remain unknown.

## Access and integration boundary

The audiences describe who will need a document; they do not grant access. The app still uses the existing PM-scoped local profile preview. First-responder QR access, authenticated AHJ/facility portals and controlled document sharing are future work. Emergency procedures must come from reviewed site-specific source documents; this feature does not generate operating instructions.

The client's mailbox provider is Gmail. The earlier request to defer actual mailbox connection remains in force. Existing DocuSign sandbox integration is retained; a local tracked requirement is not automatically a DocuSign envelope, and permit/inspection/PTO records do not become signature requests merely because DocuSign is available.

## Validation

Run the existing paperwork suites, `tests/test_compliance.py`, `tests/test_requirement_actions.py`, and `node tests/test_paperwork_navigation.cjs`. Check projection immutability, cross-PM and archive boundaries, duplicate adoption, required timestamps, current-revision binding, changes after review, and that generic completed records cannot satisfy specific requirement coverage.
