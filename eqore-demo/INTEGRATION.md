# PM workspace integration handoff (v0.5)

This folder is the working PM application. The contractor portal and command center remain separate modules; this handoff does not claim they are connected. Follow the repository's root `AGENTS.md` ownership rules. `CLAUDE.md` here makes this guide discoverable to Claude Code.

## Run and verify

From the team repository root:

```sh
cd eqore-demo
python3 server.py                         # http://127.0.0.1:8765/
python3 -m unittest discover -s tests -v
# Optional isolated database / alternate port:
python3 server.py --port 8766 --db /tmp/eqore-integration.sqlite3
```

Python 3.10+, standard library; no frontend build. Systems without IANA timezone data need `tzdata`. Each clone seeds its own SQLite database. Keep databases, uploaded reports and credentials out of Git. Live summaries require the locally authenticated `codex` CLI (`codex login`, then restart the server); Claude Code can edit and run the application without changing its LLM provider. No Anthropic key is required by this module.

## Current data contract

`GET /api/bootstrap` returns `state`, `session_version`, derived `dashboard`, `phases`, `operations`, public `vendors`, `workspace.calendar`, and the project catalog. Treat derived projections as read-only. `storage.py` persists the canonical PM snapshot; `engine.py` and `operations.py` validate mutations.

| Project selector (`projects[].id`) | Canonical PM `state.project.id` |
| --- | --- |
| `harbor_components` | `EQ-DEMO-HARBOR-01` |
| `millbrook_cold_storage` | `EQ-DEMO-MILLBROOK-02` |
| `riverbend_logistics` | `EQ-DEMO-RIVERBEND-03` |

Tasks use project-scoped string IDs: `t_contract`, `t_survey`, `t_design`, `t_permit`, `t_utility`, `t_procure`, `t_site`, `t_unload`, `t_electrical`, `t_verify`, `t_commission`, `t_closeout_documents`, `t_customer_training`, `t_handoff`. Use `(project.id, task.id)` as a compound identity. Vendor changes can add further work-package tasks; do not assume exactly 14 forever.

Task fields include `title`, `owner_id`, `predecessors`, `duration_hours`, `planned_start`, `status`, `required_gates`, `required_resources`, and `evidence_ids`. Timestamps carry UTC offsets; calendar display uses `America/New_York`. `project.now` is the scenario clock. `project.revision` binds proposals to a plan and is distinct from the API's `session_version`.

Core `state` contains tasks, stakeholders, gates, calendars, evidence, proposals, decisions, requests and bookings. The additional `state.operations` holds source messages, support cases, inquiries, replies, vendor proposals, decisions, bookings and audit. These two proposal collections have different contracts; do not concatenate or interchange them. `vendors.py` defines supported capabilities: `rigging`, `electrical_ct`, `epc_interconnection`.

## API adapters

POST JSON with `Content-Type: application/json`. Every mutation below needs the latest `expected_version` from `session_version`; success returns a fresh bootstrap except asynchronous jobs. A stale request returns HTTP 409: reload, review and retry the intended action, never blindly replay an approval.

| Route | Additional payload / result |
| --- | --- |
| `POST /api/projects/select` | `project_id`: selector ID from the table above |
| `POST /api/messages` | `sender_id`, `raw_text`, `subject`, optional `case_id`, `attachments` |
| `POST /api/message-summary` | `message_id`; returns `job_id` |
| `GET /api/jobs/{job_id}` | Poll until `completed` or `failed`; completed summary result includes refreshed bootstrap |
| `GET /api/attachments/{id}` | Original image bytes, restricted to references in the selected project |
| `POST /api/operations` | `operation: {type, ...}`; route uses PM actor |
| `POST /api/operations/respond` | Counterpart simulator only: `actor_id`, `operation`; not a production contractor-auth API |

Example original report (substitute the current version and a recorded sender):

```json
{"expected_version":12,"sender_id":"electrician","subject":"Additional electrical support","raw_text":"Please arrange qualified support to resolve the reported metering discrepancy.","attachments":[]}
```

Messages accept 1–40,000 text characters, subject up to 250, and at most four images of 4 MiB each. Each attachment is `{name, mime_type, data_base64}`; PNG/JPEG/WebP only, with raw base64 rather than a data URL. Metadata and bytes are saved atomically. Responses contain original messages in `operations.messages`; the endpoint currently generates the message ID, so an integration must add an external-report ID mapping/idempotency guard before retrying deliveries.

Live analysis saves `message.summary` separately from `assertions`, `image_observations`, and `extraction`. A validated vendor-help request can open a case and inquiries. Claims remain reported observations; neither summary nor photo can authorize work, establish an engineering finding or close a utility gate.

Operations follow `request_availability` → `receive_vendor_reply` → `propose_vendor` → `approve_proposal` / `request_approval` → `commit_proposal` → `confirm_booking`. Use existing case, inquiry, proposal and booking IDs returned by the server. `approve_and_commit` combines two validated PM steps. `reject_proposal` and `request_clarification` retain source history. Read `operations.apply` and `tests/test_operations.py` for exact payloads and validations. Scripted replies are available through `simulate_vendor_replies`; no external messages are sent.

Approval binds to the exact quote, scope, design and project revision. Price/date/qualification/capacity changes require revalidation. Approval, plan commitment, counterpart booking, physical completion and independent acceptance stay separate. `POLICY_DEMO_01` is an authored delegation policy, not an EQORE internal policy.

## Differences to resolve with teammates

Inspected contractor ref `origin/4-contractor-portal` at `1dc494c`, and command-center ref `origin/1-install-command-center` at `8a6f079`. Recheck their latest contracts before integration.

- Contractor and command-center share 25 `JOB-###` records and contractor task IDs such as `T-JOB-001-electrical`. PM uses the three distinct projects above. No valid crosswalk exists yet: do not equate sites just because city or industry matches. Agree on one catalog, then map project, task, party and vendor IDs explicitly.
- Contractor uses a 12-step installation template, date-only work/calendar-day durations and `done`; PM has post-signing phases, hourly windows, explicit gates and `completed`. `t_utility` is pre-install review, not permission to operate. Contractor commissioning precedes PTO; PM's operational commissioning follows operating authorization. Preserve the distinction between permitted acceptance testing and operation when mapping these steps.
- Contractor owns a separate JSON document (`GET/PUT /api/state`, `base_version`); command-center keeps localStorage; PM owns SQLite snapshots. Do not mirror whole states both ways or let two schedulers commit competing dates. Select one authoritative mutation path and publish its resulting task/date/approval projections back to the other views.
- Contractor currently allows six uploaded photos and supports more trades. PM allows four and three vendor capabilities. Align validation explicitly; reject unsupported mappings instead of silently dropping photos or treating utility/AHJ parties as interchangeable vendors.
- Contractor uses Anthropic summaries; PM uses authenticated Codex/ChatGPT. Preserve provider/mode/error provenance. Choose one report-analysis service or keep both explicitly separate; do not relabel fixed-rule output as live LLM output.
- **CSS compatibility:** contractor `index.html` imports `../eqore-demo/web/styles.css`, expecting v0.4 tokens/classes (`--navy`, `--paper`, `.app-shell`, `.button`, `.panel`). That import contract is preserved: `styles.css` retains the old base, while the v0.5 PM page loads `pm.css`. `legacy.css` serves the older testing UI. Future shared tokens/components should be extracted deliberately; do not replace the compatibility stylesheet with the PM layout.

## Suggested integration sequence

1. Run both modules unchanged and their tests (`node contractor/model.test.js`, `node command-center/engine.test.js` from repository root). Verify the contractor's preserved base CSS import and the PM page's separate `pm.css` load.
2. Agree on one project catalog and explicit ID/time/status mappings. Start with one matched test project and one electrical-support report; preserve raw text, photos, source identity and external report ID.
3. Add a server adapter that validates project membership and authenticated contractor identity, then ingests the original report. Have PM triage create the case. Do not accept a browser-supplied actor as proof of authority.
4. Drive vendor offers and PM approval through one canonical domain service. Return committed schedule changes and approval/booking status to the contractor portal; show pending acceptance separately from completed work.
5. Test duplicate deliveries, stale versions, concurrent PM/contractor edits, changed quotes, expired qualifications, above-limit approval, conflicting crews and missing utility acceptance. Compare budgets and dates in both views after each transition.
6. Before a shared deployment, replace local actor impersonation with real authentication/authorization and project-scoped requests. The PM server currently uses one globally selected project/session, not per-user selection; two users switching projects can interfere. It accepts only localhost Host/Origin values and binds to loopback, so the contractor's port 8780 cannot directly call it from a browser. Design an authenticated same-origin gateway or explicit scoped integration API; do not just remove these checks.

The UI is presentation-ready for the hackathon; data, outreach, bookings and delegated roles remain authored demo fixtures. Production communications, authentication and a unified contractor backend are not implemented in this version. Source scope and assumptions remain in `README.md` and `docs/PM_VENDOR_SOURCES.md`.
