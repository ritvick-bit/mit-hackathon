# Paperwork, delivery and contractor workspace (v0.7)

## Client-calibrated document coverage

`client_reference.py` is the read-only source catalog from EQORE's November 7 materials. `compliance.py` projects 20 specific document requirements without replacing existing D01–D20 evidence. Bootstrap includes `client_reference`; each project summary has `compliance_counts`, and the selected project has `compliance_review`. These are coverage/review states, not legal compliance determinations. Source audiences describe intended readers, not new access permissions.

Two PM-scoped actions use the existing `/api/paperwork/action` optimistic-version contract:

- `track_requirement`: `{project_id, requirement_id, due_at}` creates `C_<requirement_id>` as a local draft. The timestamp must include a timezone. Specific requirement dependencies are enforced even when the prerequisite has not yet been tracked. No external draft, email or approval is created.
- `set_requirement_review`: `{project_id, requirement_id, review_due_at?, changed_at?, change_reason?, attest_review?, review_note?}` records an explicit review date, a dated change, or review of a completed current record. `review_due_at:null` clears the schedule. A review attestation binds the server timestamp, PM and document revision; it does not change issuer evidence.

Completed tracked records needing review reappear in the next-action queue with `view:"compliance"`, `requirement_id` and `status:"review_due"`. Original completion deadlines are not reused as invented review deadlines. The ordinary document workflow handles drafts, revisions and source evidence; archives remain read-only. See [client calibration](docs/CLIENT_CALIBRATION.md) for source gaps and remaining access/integration work.

The opening page now focuses on post-signing paperwork: responsible people, drafts, signatures, source emails, current revisions and next actions. A separate paperwork portfolio lives alongside the existing three-project delivery engine in the same SQLite database. The delivery and contractor screens still share their physical-work snapshots; paperwork does not silently alter those tasks, costs or gates. The original sibling `contractor/` and `command-center/` apps remain references; their independent catalog and stores are not synchronized. Follow root `AGENTS.md` ownership rules; `CLAUDE.md` imports this guide.

## Run

From the repository root:

```sh
cd eqore-demo
python3 server.py
# Paperwork:  http://127.0.0.1:8765/ (also /paperwork.html)
# Delivery:   http://127.0.0.1:8765/delivery.html
# Contractor: http://127.0.0.1:8765/contractor.html
python3 -m unittest discover -s tests -v
# Optional isolated database:
python3 server.py --port 8766 --db /tmp/eqore-integration.sqlite3
```

Python 3.10+, standard library, no frontend build. Systems without IANA timezone data need `tzdata`. Each clone creates its own SQLite database. Live summaries require a locally authenticated `codex` CLI (`codex login`, then restart). Claude Code can edit/run this application without changing its LLM provider. No Anthropic key is required by this module. Keep databases, uploads and credentials out of Git.

## Paperwork portfolio and sessions

`paperwork.seed()` creates eight active projects for `pm_jordan` (Jordan Lee), two for `pm_casey` (Casey Morgan), and one completed archive per PM. Every project has the same illustrative twenty-document template (`D01`–`D20`), with different opening progress and responses. The three matching selectors `harbor_components`, `millbrook_cold_storage` and `riverbend_logistics` are also present in the delivery engine, but the two models are not synchronized. The five other Jordan projects and two Casey projects are paperwork-only examples.

`storage.py` retains this separate JSON state in `workspaces`, key `paperwork`, with an integer optimistic-concurrency version. State has `projects` keyed by selector; each project's `documents`, `stakeholders`, `emails`, `source_events`, `history` and `signed_history` are lists. `paperwork.view(state, pm_id, project_id)` projects only that PM's active projects, archives and optional selected project. The bootstrap adds `version`, connector status and live-model availability. API reads use the current server time for overdue calculations; the authored example dates are not live project forecasts.

The profile picker issues a short-lived local bearer token. It scopes projects and jobs to the selected PM, but does not verify a person's identity or replace production authentication. This session is separate from the contractor role picker and the older globally selected delivery PM session.

| Route | Contract |
| --- | --- |
| `GET /api/paperwork/accounts` | Available PM profiles |
| `POST /api/paperwork/login` | `{account_id}` → `{token, pm}` |
| `GET /api/paperwork/bootstrap?project_id=...` | PM-scoped projects, archives, metrics, action queue and optional full document register |
| `POST /api/paperwork/action` | `{expected_version, action:{type,project_id,doc_id?,...}}` → refreshed bootstrap |
| `POST /api/paperwork/assist` | `{expected_version,project_id,doc_id,kind:"summary"|"draft_email"}` → `{job_id}` |
| `GET /api/paperwork/jobs/{job_id}` | PM-scoped model-job status |
| `GET /api/paperwork/connectors` | Configuration and last successful account checks, without credentials |
| `POST /api/paperwork/connectors` | Explicit account check, provider draft creation or manual reconciliation |
| `POST /api/paperwork/oauth/start` | Begin the selected provider's OAuth authorization flow |
| `POST /api/paperwork/logout` | End the local PM session and forget its runtime provider credentials |

After login, send `Authorization: Bearer <token>`. Mutations use the integer `version` from bootstrap; a stale version returns HTTP 409 and requires a refresh/review. Do not substitute a delivery `session_version` or contractor `project_version`.

## Document lifecycle and provider boundary

Kinds are `esign`, `review` and `record`. The current coordination status can be `blocked`, `ready`, `draft`, `sent`, `partially_signed`, `completed`, `returned`, `declined` or `voided`. The public `lifecycle_status` preserves the underlying recorded state when a new dependency revision makes effective status `blocked`. Each dispatched document binds the exact prerequisite revisions. Rework retains original evidence and old signatures in `revisions`/`signed_history`; historical acceptance never silently satisfies a changed upstream record.

`action_queue` contains currently actionable open documents. Total `overdue_count` includes blocked overdue records; `actionable_overdue_count` matches the actionable overdue queue and `blocked_overdue_count` explains the remainder. Completion metrics count only the current effective completed state. Priority is an explicit status/due-date/dependency heuristic, not a computed physical-project critical path.

Normal actions include `draft_document`, `send_document` (a local sample package only), `draft_email`, `record_email`, `configure_contact`, `revise_document`, `void_document` and explicit `simulate_event`. Email drafts contain current recipients and a stable `EQORE-{project}-{doc}-r{revision}` match token; subjects retain `[token]` even after prose edits. Prepared drafts can be copied/downloaded without any mailbox connection. Recording an original email never changes document acceptance.

`archive_project` requires all current documents complete, no stale dependencies, `attest_project_complete:true` and a nonempty `attestation`. This records the PM's explicit delivery/closeout attestation; it does not derive physical completion from paperwork or overwrite the delivery engine. Archived projects are read-only.

Provider operations are reserved for the server's verified adapter path: `bind_provider_envelope`, `record_provider_dispatch`, `record_provider_observation`, `record_event` and `import_provider_email` require the Python keyword `trusted_provider=True`, which cannot be supplied through action JSON. A DocuSign draft remains `draft`; local sample dispatch/signatures cannot replace its provider binding. Dispatch uses the actual provider timestamp, not the later poll time. Provider completion requires every mapped current recipient signature and a matching completed envelope. Wrong-project, old-revision, incompatible and out-of-order events enter quarantine; repeated IDs never bypass revalidation or automatically replay a quarantined event.

No connected account is established merely by installing this checkout. The DocuSign sandbox adapter creates unsent drafts and reads provider evidence through an explicit manual sync. The optional mailbox adapter creates drafts and reads narrowly matched replies; it cannot send. There is no automatic webhook endpoint, recurring provider polling, invented signing URL or browser-return-based completion. Permit/utility records are not converted into signature envelopes, and no imported event grants construction or operating permission.

Browser authorization uses OAuth PKCE with `http://localhost:8765/api/paperwork/oauth/callback/{provider}` for `docusign` or `graph`; the current callback configuration does not follow an arbitrary server port. Public application/client IDs and provider account setup are needed before authorization can succeed. Runtime OAuth tokens are PM-session scoped and kept in memory; they are not written into the project database or returned to the page. Reconnect after server restart/logout. Email connection is optional. See [provider setup and primary-source notes](docs/PAPERWORK_COORDINATION.md).

## Delivery and contractor shared data

| Project selector | Canonical `state.project.id` |
| --- | --- |
| `harbor_components` | `EQ-DEMO-HARBOR-01` |
| `millbrook_cold_storage` | `EQ-DEMO-MILLBROOK-02` |
| `riverbend_logistics` | `EQ-DEMO-RIVERBEND-03` |

Use `(project.id, task.id)` as a compound identity. Initial task IDs are `t_contract`, `t_survey`, `t_design`, `t_permit`, `t_utility`, `t_procure`, `t_site`, `t_unload`, `t_electrical`, `t_verify`, `t_commission`, `t_closeout_documents`, `t_customer_training`, `t_handoff`. Authorized vendor work can add further tasks. Timestamps carry UTC offsets; display timezone is `America/New_York`. `project.now` is the scenario clock; `project.revision` is the domain plan revision, not an API concurrency token.

`storage.py` owns snapshots, images, versions and audit history. `engine.py` owns dependencies, authority, gates and acceptance. `operations.py` owns source-linked vendor cases, offers, approval and commitment. `contractor_bridge.py` adapts assigned-party reports, quotes, bookings and completion into those same rules without another scheduler. `project_resources.py` derives procurement, readiness, subcontractors and calendar views.

Core `state` holds tasks, stakeholders, gates, evidence, calendars, proposals, decisions, requests and bookings. `state.operations` contains vendor cases/messages/inquiries/replies and its own scoped proposals/decisions/bookings; these proposal collections have different contracts. `state.contractor_reports` links stable client report IDs to original messages, actors, tasks and cases.

## Delivery PM API

`GET /api/bootstrap` returns selected state, integer `session_version`, derived dashboard/phases/operations, public vendors and `workspace.resources`. Resources include project subcontractor work packages/offers, procurement, calendar, approximate city map anchors and 14 explicit readiness criteria. Accepted-count is not a critical-path score or dispatch authorization. External partners belong to project work packages; there is no EQORE-owned crew pool.

`GET /api/bootstrap?project_id=harbor_components` reads that project without changing selection. If it differs from the selected project, `session_version` is `-1`, deliberately unsuitable for mutation. `GET /api/updates?project_id=...` returns `portfolio_revision`, `project_revision` and `report_count` for refresh detection without changing selection.

PM POST routes remain session-based: send JSON with `expected_version` from the selected bootstrap. Routes include `/api/projects/select`, `/api/messages`, `/api/operations`, `/api/message-summary` and existing engine actions. `/api/operations` uses the PM actor; `/api/operations/respond` remains a local counterpart simulator. A stale request returns HTTP 409: refresh and review before retrying an approval.

## Contractor API

The role picker is a local preview identity mechanism, not production authentication. The server issues an expiring token and derives subsequent actor identity from it; action payloads cannot choose another task owner or approver.

| Route | Contract |
| --- | --- |
| `GET /api/contractor/accounts` | Recorded assigned parties and inquiry recipients |
| `POST /api/contractor/login` | `{actor_id}` → `{token, actor}` |
| `GET /api/contractor/bootstrap` | Assigned projects with opaque `project_version`, owned tasks, timeline, reports, offers, bookings and updates |
| `POST /api/contractor/action` | `{project_id, expected_project_version, action}` → refreshed contractor bootstrap |
| `GET /api/contractor/jobs/{job_id}` | Summary-job status limited to its actor |
| `GET /api/contractor/attachments/{project_selector}/{attachment_id}` | Checks project membership and original-report access |
| `POST /api/contractor/logout` | Invalidates preview session |

After login, send `Authorization: Bearer <token>`; POST requires `Content-Type: application/json`. `project_version` is an opaque snapshot hash: do not increment it or substitute the PM version. Contractor writes are project-scoped and never switch PM selection. Updating the selected project invalidates stale PM screens too.

Example report action, using a current token/hash and an owned task:

```json
{"project_id":"harbor_components","expected_project_version":"<opaque snapshot hash>","action":{"type":"report_problem","client_report_id":"report-20261107-001","task_id":"t_unload","subject":"Replacement rigging support","raw_text":"The original unloading slot conflicts with the delivery update. Please arrange a replacement mobilization.","urgency":2,"attachments":[],"support":{"capability":"rigging","mode":"takeover","duration_hours":1}}}
```

Retain `client_report_id` on retries: 8–100 letters, digits, hyphens or underscores. Identical content is idempotent; changed content with the same ID is rejected. After 409, refresh the version before retrying. A new report or revised content needs a new ID.

Actions: `report_problem` / `message`, `completion_report`, `confirm_booking`, `receive_vendor_reply`. Only the assigned task owner may report/complete work, and only the named counterpart may confirm a booking or answer its inquiry. Completion requires `attest_complete: true`, a finished work window and domain prerequisites; it does not replace independent acceptance. Read `contractor_bridge.apply` and `operations.apply` for exact payloads.

Support capabilities: `rigging`, `electrical_ct`, `epc_interconnection`. `mode: before` requests preceding work; automatic `takeover` is limited to rigging of `t_unload`. Other trades/takeovers, changes to authorized packages and completed-work rework remain for PM scope review. Urgency is 1 (highest) through 5. Supported requests link matching cases or create scoped cases and local availability inquiries; they cannot approve spending or overwrite utility/customer authority.

## Originals and model analysis

Reports accept 1–40,000 text characters, subject up to 250, and four PNG/JPEG/WebP images of at most 4 MiB each. Attachments are `{name, mime_type, data_base64}` with raw base64, not a data URL. Original text, images and report linkage persist together. PM `/api/messages` still lacks contractor report-id idempotency; external adapters should use the contractor flow.

A new contractor message starts project-scoped ChatGPT analysis when connected and a model slot is free. The original is saved first. Concurrent changes to that project discard stale analysis; changing PM selection alone does not redirect it. Busy/failed analysis leaves the original available for PM retry. No login or a failed call means no live summary, not an undisclosed fixed-rule substitute. `message.summary` is separate from reported `assertions`, `image_observations` and `extraction`; no model text grants authority or certifies engineering work.

## Boundaries and compatibility

Offer → exact proposal → authorized approval → commitment → counterpart booking → evidenced work → independent acceptance remain separate. Quotes, qualifications, scope, design, calendars and authority are rechecked. Posted actuals do not rise on approval. Shared cost allocations are not counted once per vendor. ETA differs from physical receipt; installation-stage utility review differs from operating authorization; available access windows differ from shutdown permission.

PM uses `web/pm.css`; the new partner page uses `web/contractor.css`. `web/styles.css` preserves the v0.4 import contract of the original sibling contractor app. `legacy.css` serves `/legacy.html`, the internal evaluation workspace outside primary PM navigation. Original sibling modules remain independently runnable references, not additional authorities over unified state.

The server binds to loopback and validates localhost Host/Origin. The delivery PM workspace still has one globally selected session; paperwork has separate PM-scoped sessions and a shared portfolio version. Real identity authentication is required before shared production deployment. Contractor project hashes prevent accidental cross-project writes but do not make the role picker production security. Delivery inquiries and notifications remain local records. All seeded projects, credentials, prices, ratings and delegated roles are authored examples; deliberately imported provider records are separately labelled. `POLICY_DEMO_01` is not EQORE's internal SOP.

### Relay portfolio and Gmail direction

The primary landing page is the PM-scoped US project map with wheel zoom, pointer pan, regional presets and ranked paperwork actions. `web/paperwork-map.js` owns the viewport; `RelayMap.render(projects, all, {region})` returns markup and `RelayMap.attach(root)` binds interaction after rendering. Lists scroll without pagination. Project overview is action-first; the register is an explicit subview. The compact sidebar expands on hover or keyboard focus, with a toggle for touch, and the UI keeps local navigation history for Back. Map coordinates are illustrative city-centre anchors returned by `paperwork.view`; do not infer surveyed addresses or share other PMs’ projects. Gmail is the preferred mailbox provider, with optional loopback OAuth setup; no mailbox connection is assumed. Existing DocuSign and physical-work boundaries remain unchanged.


## Current team PM-platform handoff

The `origin/7-pm-platform` branch introduces `pm/` with a `DOC_CENTER(query)` hook. It passes `project=<JOB-id>` and either `doc=<JOB>:<step>:doc<n>` or `step=<step>`. Those IDs are a separate seed dataset, not aliases for Relay's projects. Do not map `JOB-001` to a similarly placed/name-matched site or mark records complete based on matching titles.

Relay's supported direct URLs currently use `http://localhost:8765/paperwork.html?project_id=<canonical-project-id>&doc_id=<canonical-document-id>` (document) or `?project_id=<canonical-project-id>` (project). Login preserves the target and the backend checks PM membership. A shared ID/import contract is still needed before the new PM platform's links can safely target those records. The live APIs and `client_reference.py`/`compliance.py` can be reused; keep a single authoritative record store and translate identities explicitly. This change does not edit the teammate-owned `pm/` application.

### DocuSign connection verification

The existing `/api/paperwork/connectors` endpoint accepts `operation: create_connection_draft`, `provider: docusign`, a test `email`, and the current `expected_version`. It requires a successful account check, writes a durable idempotent test request scoped to the PM/account, creates an unsent draft, and exposes only safe result metadata via `connectors.latest_connection_test`. Test records never enter a project's document register or advance an approval. The normal project envelope operation still requires current prerequisites, an e-signature document, and reviewed recipient addresses.

For review results and limits, read `docs/STANDARDS_EVALUATION.md` and `docs/PRESSURE_TEST_REPORT.md`. Existing provider status, request/response bodies, database files and OAuth credentials must not be copied into Git.
