# EQORE local prototype implementation contract — v0.4

Python 3.10 standard library backend; SQLite persistence; static HTML/CSS/JS frontend. Local only. Product scope is signed contract through accepted handoff. Pre-signing sales and long-term operations are outside this implementation.

## Shared state (JSON)

Top-level: project, tasks, stakeholders, evidence, gates, calendars, events, proposals, decisions, requests, bookings, alerts, audit, rework.

- project: id, name, customer, location, utility, design_revision, revision (integer), now (ISO timestamp), target_date, status, scenario_id, synthetic=true, budget={baseline,committed,proposed}.
- tasks: [{id,title,phase,phase_id,status,owner_id,predecessors:[id],duration_hours,planned_start,resource,evidence_ids,description}]. Status: completed, ready, planned, blocked, pending. Extra fields allowed (required_gates etc).
- stakeholders: [{id,name,role,organization,knows:[str],can_approve:[str],contact,authority_source}]. Synthetic contacts use .example domains.
- evidence: [{id,title,body,issuer_id,project_id,design_revision,effective_at,received_at,kind,verified}].
- gates: object keyed by gate id; values {id,label,status,issuer_id,evidence_ids}. status pending/approved/blocked. Optional required_tasks, required_gates, required_artifacts, source_ids and assumption describe scoped acceptance. Reopened gates retain acceptance_history, invalidated_at, invalidated_evidence_ids and rework_generation.
- calendars: {resource:[{start,end}]}.
- events: [{id,type,at,summary,evidence_id}].
- proposals: [{id,based_on_revision,changes:[{task_id,planned_start}],cost_delta,status,required_approver_id,evidence_ids}].
- decisions, requests, bookings, alerts, audit are arrays of records. alerts: {id,kind,severity,title,task_ids,resolver_id,evidence_ids,resolved}.
- rework: observed correction records with id, status, trigger_event_id, reason, return_phase/return_task_id, correction_owner_id, affected gate_ids/task_ids, required_artifact/actions, invalidated_at/evidence_ids, correction_evidence_ids and resolution_evidence_ids. Status: correction_required, awaiting_reapproval, resolved or superseded. Acceptance tasks may retain completion_history when reopened; unaffected physical-work history is preserved.

## Python interfaces

engine.py:
- class DomainError(Exception) with a useful str(error).
- analyze(state) -> dict {schedule_options,impacts,constraints,ready_tasks,blocked_tasks,candidates}.
- recommend(state) -> decision dict.
- project_complete(state) -> bool. Requires nonempty tasks with all statuses complete, all modeled gates currently accepted, no unresolved/non-superseded rework, and no open alert; historical task completion alone is insufficient.
- apply_action(state, action, actor_id='coordinator') -> NEW state (do not mutate input); checks and audit included.
- apply_event(state,event) -> NEW state. This is a trusted simulator ingestion path, never directly called on raw model output. Event types agreed with scenario author.
- decision dict: {action_type,title,recipient_id,request,why_now,blocker,unlocks:[str],evidence_ids:[str],authority,alternatives:[str],while_waiting:[str],action:object,confidence:string}. Actions carry `type`; no hidden fixture expected outputs in product state.
- action types: propose_plan, request_information, request_approval, resolve_decision, commit_plan, confirm_booking, complete_task, wait, request_review. Other domain actions only after informing root.
- proposals enforce required decision, atomic feasibility and revision checks. State revisions bump for material event/plan changes; approval receipt for that exact proposal does not itself invalidate it. Requests and bookings deduplicate. Approval is trusted actor input, not inferred from text.

scenarios.py:
- list_scenarios() -> [{id,title,description,capabilities:[CAPxx],difficulty}]; public metadata only.
- initial_state(scenario_id) -> state.
- next_event(scenario_id, cursor, state) -> event or None. Private scripted events remain in module/fixtures, not runtime context.
- actor_response(state,request) -> event or None. Actions may initiate a pending request; only simulated response advances external truth.
- sources() -> list of reference records.

evaluation.py:
- run_suite(mode='baseline', decide=None, scenario_ids=None) -> JSON report. Uses real engine apply_action/apply_event. Optional decide(state) callable returns decision; server supplies LLM callable. No product code imports evaluation expectations.
- report {id,mode,created_at,product_version,summary:{passed,failed,total},cases:[{id,title,status,checks,trace,final_summary}],limitations:[str]}.

## HTTP contract

GET /api/bootstrap -> {version,state,session_version,analysis,dashboard,phases,workflow_review,projects,mode,recommendation,scenarios,sources,runtime,evaluations,challenge_design,challenge_reports,capabilities,reasoning_history}. version is 0.4.0; mode is project or scenario. projects contains public metadata, selected flag, live metrics, current_phase_titles and phase_summary. phase_summary contains version, active_phase_ids/titles, open_rework_count, all_accepted and compact statuses for each phase. dashboard contains ranked bottlenecks, metrics, finance, resources and milestones.
GET /api/health -> {ok:true,version:"0.4.0"}.
POST /api/projects/select {project_id,expected_version} -> same envelope, restoring saved project/cursor/recommendation without resetting.
POST /api/projects/reset {project_id,expected_version} -> fresh selected project, other project records unchanged.
POST /api/reset {scenario_id,expected_version} -> same envelope (fresh targeted test case; saved demo projects unaffected).
POST /api/clock {expected_version} -> advance simulated time to the next observed request deadline, without inferring a reply or approval.
POST /api/event {expected_version} -> inject next scripted event, same envelope.
POST /api/action {action:object,expected_version:int,actor_id?:string} -> same envelope; action originates from displayed recommendation or explicit UI controls. Top-level actor_id is accepted only for explicitly simulated resolve_decision controls; action text cannot grant authority. resolve_decision uses status='approved'|'rejected'.
POST /api/respond {request_id,expected_version} -> deliver trusted scripted actor reply, same envelope.
POST /api/decide {mode:'live'|'baseline'} -> {job_id}; GET /api/jobs/:id -> {status:'running'|'completed'|'failed',result?,error?}. On completed, result is bootstrap envelope. Live runs use evidence, planner, coordinator responsibilities and preserve traces.
POST /api/evaluate {mode:'baseline'|'live',suite?:'scenarios'|'projects'|'challenges',scenario_ids?:[],project_ids?:[]} -> {job_id}; job result is report, bootstrap includes recent reports.
GET /api/export -> JSON snapshot, current phase summary, recommendation, dashboard, retained reasoning contexts and previous-world archives (no hidden scenario facts). Existing export fields remain available.

Action, event and response mutations require expected_version from bootstrap's session_version. It is separate from the domain revision and detects stale screens. Generated reasoning snapshots persist independently of later actions/resets; export includes their observed project contexts. The displayed history is filtered to the selected project and retained across its resets.

confirm_booking creates a pending counterpart request; only its trusted actor response confirms the booking. complete_task records digital work or consumes existing verified scoped completion evidence. Neither operation can manufacture external truth.

runtime: {provider:'ChatGPT via Codex',available:boolean,authenticated:boolean,detail:string,live_calls:number}. recommendation includes mode baseline/live, optional agent_trace. Initial recommendation is explicitly baseline. No silent live-to-baseline fallback. Errors JSON {error:string}, appropriate 400/409/500.

UI: refined warm light operations console, sidebar project/capabilities navigation, project status, prominent next action card, dependency map, stakeholders/authority, evidence/source register, decisions and audit, scenario controls and eval report. Plain JS fetch. Escape all externally supplied strings; never innerHTML untrusted markup. Synthetic labels and live/baseline labels explicit.

## Whole-project demo extension

projects.py exposes list_projects, initial_state, next_event and actor_response; private future events never enter model observations. Project metadata adds demo_project_id, site, system, target_handoff, assumptions, finance and labor. finance.lines records initial budget/committed/actual amounts with as_of; later committed plan changes are reconciled in the dashboard without manufacturing invoices.

Store.project_snapshots persists state, event cursor and recommendation for each demo project. A global session version increments on each switch and mutation, so a stale browser or in-flight model call cannot write into another project. Project reasoning stores the exact observed snapshot and is filtered by project ID.

dashboard.summarize returns all independent current constraints and explicitly tagged future prerequisites, avoiding repeated rows for downstream effects. Rank is a transparent rule score. Live ChatGPT may select among validated candidates using the entire project overview; it does not silently replace fixed-rule ranking with an unrecorded LLM judgment.


## Grounded explanations and independent challenges

Every engine candidate contains `reasoning` with `version`, `based_on_revision`, `observed_state_digest`, `summary`, exact observed `facts` (id/label/value/JSON-pointer ref/evidence_ids), `constraint`, `consequence`, `authorized_action`, `expected_unlocks`, `uncertainties`, and `reconsider_when`. This is a public explanation record. `why_now` uses the short summary. `reasoning.validate_reasoning` checks snapshot freshness and exact references. Live judgment chooses a candidate, supporting fact IDs and enumerated priority grounds; canonical facts and executable requests cannot be overwritten by model draft prose.

Project world version 3.0.0 contains 14 tasks, 17 stakeholders, 13 gates and 5 private staged updates per project. Gates expose `required_artifacts`, `source_ids`, and explicitly synthetic `assumption`. A gate marked `execution_only` blocks physical completion but does not prevent advance schedule planning against an ETA. Installer correction, independent verification, final inspection and fleet acceptance retain separate authorities.

`challenges.py` independently generates 12 designs with fresh ChatGPT inference from frozen public observations and interfaces. Designer input excludes engine source, candidate ranks, future events, fixes and expected evaluator outcomes. Frozen engine source is retained only for reproducing BEFORE checks and was not supplied to the designer. Expected challenge outcomes never enter product-agent prompts. `run_suite(mode='baseline',phase='after',decide=None,scenario_ids=None)` returns a challenge report with preserved checks, traces, product hashes, coverage limits and live-decision counts. The browser replay is baseline; fresh live probes are separately recorded. A passed executable subset does not claim complete coverage of the natural-language design.

The store archives untouched previous world versions before refresh; progress-bearing saved projects are not overwritten. Exports include previous world archives for the selected demo project.


## Post-signing phases and source-map review

`phases.summarize(state, analysis=None)` derives an observed view without mutating saved state. Eight groups cover signed scope; site/design; permits and utility review; procurement/site preparation; installation; verification/operating authorization; operational commissioning; documents/training/fleet handoff. Older records without phase_id or rework remain readable through known task mappings and defaults.

The summary contains phases, active_phase_ids/titles, rework_routes, open/resolved/superseded rework counts, all_accepted, dependency edges, warnings and scope/timing/status notes. Each phase contains its task/gate IDs, owners, exit criteria, blockers, ready work, pending requests, acceptance_current, historical_work_complete and milestones. Status is completed, current, waiting, upcoming or rework. `current` means at least some work can advance, not that physical execution has begun. Several phases can be active concurrently. Links express actual task/acceptance prerequisites, not a universal serial ordering of whole phases.

Planned dates come from synthetic task windows. Recorded actual finishes require scoped completion evidence. A historical finish does not establish current acceptance after an invalidation. Phase spans are not summed into a total or represented as a critical path. The dashboard and completion controls retain the engine’s action/authority checks; phase labels never grant permission.

The supplied full HTML map has 21 nodes, six phase bands and four drawn loops. `knowledge.workflow_review` records verified public claims, corrections, inference labels, timing limits and 17 source-node-to-application coverage mappings. The original Markdown-only export was incomplete, but the subsequently supplied HTML has been reviewed. Its loops are not part of its schedule calculation; its default 21.5-week post-signing graph result is authored scenario arithmetic. Durations and ranges are not adopted as measured benchmarks. Equipment selection/civil detail/electrical work are partly aggregated; operational enrollment and long-term dispatch are not implemented. Program eligibility/status is a handoff information boundary only.

Utility review, applicable acceptance/witness testing and final written operating authorization remain distinct. Witness commissioning testing can precede authorization under the applicable process; the later t_commission task represents operational commissioning. No generic receipt, test report or conditional review is permission for ordinary operation. NFPA 855, UL 9540 and UL 9540A retain distinct purposes and applicability limits.

## Scoped correction and renewed acceptance

A trusted `review_returned` event requires a current scoped reviewer record, correction owner, reason and required artifact. The engine records the affected acceptance scope and invalidates dependent acceptance tasks/gates as necessary. It preserves unaffected completed physical work and prior evidence/history. A correction request creates a pending counterpart request; the named owner’s fresh correction record moves rework to awaiting_reapproval, not approved.

Only the authorized reviewer can provide renewed gate acceptance. Existing invalidated evidence cannot be reused; effective evidence time must be current to the invalidation, and response generation must match the current review cycle. Superseded requests cannot resolve a later rejection. A new fault after commissioning can therefore reopen controls testing and affected handoff even though installation remains historically complete. Resolved and superseded cycles remain visible, while only unresolved/non-superseded cycles block completion.

The curated LLM context includes public rework and compact derived phases, excluding future events, expected outcomes and private actor scripts. Prompts require scoped correction/review/retest, preserved unaffected work and concurrent progress. They do not authorize new engineering settings, physical work or external approval.

## v0.4 validation record

The final regression run passed all 153 automated tests. Versioned reports show 14/14 targeted baseline cases, 3/3 whole-project baseline runs with all five staged updates, and 12/12 executable subsets of the existing independent challenge set. Seven challenge dimensions remain partially covered. Those challenges use frozen public opening snapshots and do not by themselves establish coverage of every expanded phase feature.

`data/phase-live-decisions-v04.json` records two passing selected live decisions and six fresh role calls: Harbor’s corrected engineering package and Riverbend’s IT restoration with a separate required controls retest. These are isolated decisions, not complete live runs. Reports: `data/baseline-evaluation-v04.json`, `data/project-evaluation-v04.json`, `data/challenge-results-after-v04.json`. Earlier reports and original failures remain retained with their version and scope.

## v0.5 PM workspace, messages and vendor decisions

This section extends the historical v0.4 contract above. `APP_VERSION` and the health/bootstrap version are now `0.5.0`. The PM interface opens on the portfolio map and ranked project list, then opens a site overview and focused decision, inbox, calendar or vendor view. Existing engine, phase, evaluation and saved-project interfaces remain available.

`operations.ensure(state)` adds observed decision cases and pending simulated inquiries without resetting saved project work. It is idempotent; an obsolete opening case is skipped when its affected work has already completed. `operations.apply(state, payload, actor_id='pm', vendor_profiles=None)` returns a new state or raises `engine.DomainError` without partial changes. `operations.summarize(state, vendor_profiles=None)` returns public observed records and derived options.

The persisted `state.operations` object contains `version`, `messages`, `cases`, `inquiries`, `replies`, `proposals`, `decisions`, `bookings` and `audit`. Bootstrap adds `operations`, the public `vendors` directory, and `workspace: {calendar, timezone}`. Project catalog entries also contain an `operation_summary` for portfolio ranking. The operations view includes:

- `messages`: original `id`, `project_id`, `issuer_id`, `sender_name`, `text`, `subject`, `received_at`, attachment metadata and `content_hash`; optional separate `summary`, `assertions`, `image_observations`, `extraction` and `triage_status`.
- `cases`: `id`, `title`, `why`, `request`, `priority`, `status`, `source_message_ids`, stakeholders, affected tasks, required gates, vendor capability, inquiries, ranked `options`, `current_proposal`, proposal history and bookings.
- `options`: vendor identity, reply status, eligibility/exclusion reasons, ranking score/reasons, received quote ID, earliest start, duration, total incremental price, expiry, qualifications and performance sample counts/provenance. Unknown price is `null`, never zero. Ranking is a transparent deterministic comparison; it does not claim independent verification of fictional reputation.
- `proposals`: exact work package, before/after task dates/resources, incremental cost and budget totals, source evidence, quote ID, project/design revision, required approver/authority, conditions and immutable content hash. `proposed_cost` sums active current proposals for the financial view.
- `bookings`: case/task/proposal IDs, recipient, optional vendor ID, `planned_start`, `start`, `end`, status and confirmation provenance. Saved reservations constrain vendor capacity across projects.

Message content and attachment hashes are immutable. Linking an original to a case or adding its reading summary does not rewrite the original. Several messages may support one case. LLM assertions are marked `reported_not_authorized`; neither readable summaries nor extracted claims establish approved design, availability, a quote, task completion or institutional permission.

### Added HTTP routes

| Route | Request and result |
| --- | --- |
| `POST /api/operations` | `{operation:{type,...}, expected_version}`; returns bootstrap. The trusted actor is always `pm`; an actor field inside the operation cannot override it. |
| `POST /api/operations/respond` | `{operation:{type,...}, actor_id, expected_version}`; explicit demo response only. The route admits the commercial approver for authority-response actions, or the named vendor/counterpart for quote and booking responses. Domain checks still enforce exact scope and authority. |
| `POST /api/messages` | `{sender_id, subject, raw_text, case_id?, attachments?:[{name,mime_type?,data_base64}], expected_version}`; saves the original and returns bootstrap. Text is limited to 40,000 characters; at most four PNG/JPEG/WebP images, each at most **4 MiB**, are accepted. Original bytes are stored separately from metadata. HTML/SVG uploads are rejected. |
| `POST /api/message-summary` | `{message_id, expected_version}`; starts a live ChatGPT/Codex analysis job and returns `{job_id}`. `GET /api/jobs/:id` returns running/completed/failed status; successful result is bootstrap. Source quotes must occur in the original text and referenced tasks must exist. A stale project/session result is discarded. |
| `GET /api/attachments/:id` | Returns an original image only when it belongs to and is referenced by the selected project. Metadata contains its content hash and local route; arbitrary filesystem paths are not accepted. |

Session `expected_version` remains distinct from domain project revision. Mutations are transactionally stored, and a project switch or intervening mutation invalidates an in-flight message analysis result. Live message analysis requires the local ChatGPT/Codex login, retains its actual trace, and has no silent deterministic fallback. The PM reading summary and structured internal observations are separate outputs of the same original text/images. A narrowly validated additional-help request may open a sourcing case and inquiries; it cannot authorize work.

### Decision and execution lifecycle

1. A scoped case automatically issues up to three **simulated** availability inquiries to eligible directory vendors. Replies are initially absent. `simulate_vendor_replies` advances explicit demo replies; `receive_vendor_reply` requires the queried vendor actor and retains the original reply. Updated availability requires a new immutable reply ID.
2. `propose_vendor` selects a received eligible quote and builds an additional work package plus dependent schedule changes. Capability, geography, qualification validity through the work window, capacity, complete price, quote freshness and feasible resource windows are checked. Proposed dates for affected counterpart appointments remain conditional.
3. `request_approval` records a pending request to the delegated approver. `approve_proposal` records exact approval; `approve_and_commit` performs approval and commitment atomically when the caller has authority. Changes above PM delegation require the commercial approver. `simulate_authority_response` is an explicit demo control, not an interpretation of email wording. `reject_proposal` and `request_clarification` keep the underlying issue open.
4. `commit_proposal` revalidates exact content, state/design revision, current quote, authority, constraints and cross-project reservations. It inserts the real project task and dependencies, shifts affected task dates, adds the approved incremental cost to committed exposure and a ledger line with `actual: 0`, and invalidates stale legacy proposals. It creates required bookings; it does not create invoices, payments, completion records or utility permission.
5. `confirm_booking` requires the named counterpart and current unsuperseded window, with capacity/qualification revalidation. Generic engine booking responses are synchronized back into the operations view. Approval and availability alone do not confirm a booking.
6. Physical completion uses the existing engine’s qualified, project/design-scoped evidence and timing checks. A case-specific execution hold prevents affected work from bypassing the additional package; the responsible reviewer separately accepts the completed scope. Electrical correction enables independent field verification, while permit, customer interruption, inspection, utility operating acceptance and controls gates retain their own authorities. Cases resolve only after their package and affected work complete.

SQLite stores vendor profiles in `vendor_profiles`, original image bytes and hashes in `attachments`, and operations state in the existing session/project JSON snapshots and history. Startup enrichment preserves progressed records and is separate from an explicit project reset. `vendors.list_vendors()` includes private simulator reply policy for storage; `vendors.public_profiles()` and public workspace projections remove `demo_response`. Future quotes, private actor scripts and evaluator outcomes are not exposed to the UI or product-model context.

All vendor identities, qualifications, prices, performance histories, project observations and outreach in this demo are fictional. The three opening cases cover Harbor’s delivery/rigging conflict, Millbrook’s pre-submission EPC/utility-document discrepancy, and Riverbend’s CT/metering discrepancy with independent reinspection. Vendor lead time never guarantees utility review or operating authorization. The complete regression suite reached 200 passing tests during this implementation, including domain and HTTP boundary checks; separate live text/image probes exercised actual ChatGPT inference. This validation is synthetic development coverage, not a real deployment or a complete live-project benchmark.
