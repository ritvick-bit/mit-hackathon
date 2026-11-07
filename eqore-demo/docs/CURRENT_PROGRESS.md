# Relay paperwork checkpoint — 7 November 2026

**Branch:** `codex/paperwork-coordination` in `ritvick-bit/mit-hackathon`

**Run:** `python3 eqore-demo/server.py` → `http://localhost:8765/`

- Working: PM portfolio map, prioritized paperwork actions, project/stakeholder document history, revisions and dependencies, archives, and 20 EQORE-grounded document categories.
- Latest UI: one **Draft email** action opens the current editable draft. **Generate with ChatGPT** inside the editor offers a suggestion; **Use suggestion** or **Keep my draft** preserves PM control. Save, copy and download remain explicit. Nothing is emailed.
- DocuSign: real developer-account authorization, account access and unsent test-draft creation verified. Text drafts receive signature/date fields; project envelopes support manual status reconciliation. Local test credentials are not part of Git.
- Evaluation: 19 adversarial cases passed after five workflow fixes; a live ChatGPT prompt-injection probe preserved approval state. A separate real DocuSign check exposed and fixed provider recipient-ID mapping. See [pressure report](PRESSURE_TEST_REPORT.md).
- Standards: evidence checklists are grounded in EQORE materials and distinguish permits, PTO, UL certification/testing and code editions. Clause-by-clause NFPA 855 validation is not implemented. See [standards evaluation](STANDARDS_EVALUATION.md).
- Remaining integration: production identity/token storage, automated provider webhooks, executed-PDF/certificate archiving and Gmail connection. Ritvick’s `pm/` uses separate `JOB-*` IDs; agree explicit identity mapping before wiring its document links. See [integration handoff](../INTEGRATION.md#current-team-pm-platform-handoff).

Existing project records are preserved. The earlier delivery/contractor tools remain secondary; the current focus is post-signing paperwork coordination.
