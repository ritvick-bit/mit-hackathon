# Unified PM and contractor workspace (v0.6)

This module serves PM and contractor screens over the same three project snapshots and decision engine. Command-center ideas now appear as project readiness, procurement and external-partner calendars derived from those records. The original sibling `contractor/` and `command-center/` applications remain reference implementations; their 25-job seed catalog, JSON database and localStorage are not imported or synchronized. Follow root `AGENTS.md` ownership rules; this module's `CLAUDE.md` imports this guide.

## Run

From the repository root:

```sh
cd eqore-demo
python3 server.py
# PM:         http://127.0.0.1:8765/
# Contractor: http://127.0.0.1:8765/contractor.html
python3 -m unittest discover -s tests -v
# Optional isolated database:
python3 server.py --port 8766 --db /tmp/eqore-integration.sqlite3
```

Python 3.10+, standard library, no frontend build. Systems without IANA timezone data need `tzdata`. Each clone creates its own SQLite database. Live summaries require a locally authenticated `codex` CLI (`codex login`, then restart). Claude Code can edit/run this application without changing its LLM provider. No Anthropic key is required by this module. Keep databases, uploads and credentials out of Git.

## Shared data

| Project selector | Canonical `state.project.id` |
| --- | --- |
| `harbor_components` | `EQ-DEMO-HARBOR-01` |
| `millbrook_cold_storage` | `EQ-DEMO-MILLBROOK-02` |
| `riverbend_logistics` | `EQ-DEMO-RIVERBEND-03` |

Use `(project.id, task.id)` as a compound identity. Initial task IDs are `t_contract`, `t_survey`, `t_design`, `t_permit`, `t_utility`, `t_procure`, `t_site`, `t_unload`, `t_electrical`, `t_verify`, `t_commission`, `t_closeout_documents`, `t_customer_training`, `t_handoff`. Authorized vendor work can add further tasks. Timestamps carry UTC offsets; display timezone is `America/New_York`. `project.now` is the scenario clock; `project.revision` is the domain plan revision, not an API concurrency token.

`storage.py` owns snapshots, images, versions and audit history. `engine.py` owns dependencies, authority, gates and acceptance. `operations.py` owns source-linked vendor cases, offers, approval and commitment. `contractor_bridge.py` adapts assigned-party reports, quotes, bookings and completion into those same rules without another scheduler. `project_resources.py` derives procurement, readiness, subcontractors and calendar views.

Core `state` holds tasks, stakeholders, gates, evidence, calendars, proposals, decisions, requests and bookings. `state.operations` contains vendor cases/messages/inquiries/replies and its own scoped proposals/decisions/bookings; these proposal collections have different contracts. `state.contractor_reports` links stable client report IDs to original messages, actors, tasks and cases.

## PM API

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

The server binds to loopback and validates localhost Host/Origin. PM still has one globally selected session; simultaneous PM users need per-user selection and real authentication before shared deployment. Contractor project hashes prevent accidental cross-project writes but do not make the preview role picker production security. Inquiries and notifications are local records, not external email. Projects, credentials, prices, ratings and delegated roles remain authored demonstration data; `POLICY_DEMO_01` is not EQORE's internal SOP.
