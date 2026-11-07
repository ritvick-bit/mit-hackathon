# EQORE deployment coordination — refined product plan

Version 0.2 · November 7, 2026 · Planning only; no product implementation has begun.

This plan incorporates the user's direction to ground the product in EQORE's deployment project-manager responsibilities and automate the associated work across the deployment lifecycle. It supersedes any interpretation of earlier discussion that limits the product to delivery rescheduling. Delivery delay remains the first detailed disruption case.

## 1. Product objective and evidence basis

Build an agentic system that advances commercial and industrial battery deployments from signed contract through commissioning and handoff. It should maintain project knowledge, identify blockers, select useful next actions, coordinate the appropriate parties, manage authorized updates, and show the evidence and authority supporting its decisions.

Primary source: [EQORE — Project Manager, Deployments](https://www.eqore.com/careers/project-manager-deployments), checked November 7, 2026. Relevant locator: “What you'll do,” bullets 1–8.

The published responsibilities cover concurrent projects; schedules, budgets, procurement, changes and variance; permitting and utility review; field contractors and vendors; installation verification; testing and commissioning; customer coordination; and reusable procedures. The field-verification examples include design conformity, terminations, conductor sizing, grounding, CT/meter orientation and protection settings.

These statements establish the role's stated scope. They do not establish actual internal approval limits, software coverage, incident frequency, named project contacts, or measured improvement potential. Proposed capabilities below are our design, not claims about EQORE's existing systems.

Supporting references already reviewed:

- [EQORE lifecycle](https://www.eqore.com/how-it-works)
- [EQORE internal-tools role](https://www.eqore.com/careers/full-stack-internal-tools-engineer)
- [National Grid Massachusetts interconnection tariff](https://www.nationalgrid.com/document/601641/download), subject to project applicability
- [Beverly permitting example](https://www.beverlyma.gov/DocumentCenter/View/7578/Commercial-BESS-Permitting-and-Conditions), local scope only
- [Energy Toolbase deployment experience](https://www.energytoolbase.com/blog/energy-storage/modeling-deploying-energy-storage/), vendor experience rather than an EQORE procedure

## 2. Responsibility-to-capability-to-test coverage

The following is proposed product coverage. Every responsibility will have requirements, states, actors, evidence and tests; implementation maturity will be reported separately for each capability.

| ID | Workstream | Proposed automation | Simulated participants | Representative test |
| --- | --- | --- | --- | --- |
| CAP01 | Project ownership and portfolio coordination | Track milestones, outstanding decisions, commitments and cross-project resource conflicts; explain project priorities | PM, designated management approver, project teams | Two projects need the same crew; propose a feasible allocation without changing unauthorized commitments |
| CAP02 | Schedule, procurement and cost control | Reconcile estimates and confirmations; track ordered/received items; assess schedule and budget consequences; prepare change orders and update authorized baselines | Vendors, logistics contacts, PM, designated commercial approver | Delivery slips; an alternative has a stated extra cost and requires a scoped decision |
| CAP03 | Permits and interconnection | Assemble evidence, track requests and reviews, route questions, maintain stage-specific approval status and follow-up actions | Utility reviewer, local authority, fire official, engineer | A reviewer acknowledges receipt but asks for a revision; approval-dependent work remains pending |
| CAP04 | Field coordination | Align site readiness, delivery, unloading, electrical work, access and customer windows; maintain confirmation status | EPC contractor, electrician, rigger, vendor, customer site contact | Equipment arrival misses a crew slot; find feasible options while continuing independent work |
| CAP05 | Installation verification and readiness | Maintain revision-specific checklists; collect measurements, records and photos; flag discrepancies; route corrective work and required signoff | Qualified field verifier, electrician, engineer, relevant inspector | A documented metering-orientation discrepancy is unresolved; a vendor message cannot clear the required signoff |
| CAP06 | Commissioning and operational handoff | Check readiness, coordinate functional tests, track defects and retests, collect results, route applicable enrollment work and assemble handoff records | Controls engineer, fleet engineer, equipment support, customer IT, relevant program contact | A controls communication fault prevents a successful test; route to the appropriate resolver and preserve incomplete status |
| CAP07 | Customer continuity and communication | Track operating constraints and authorized windows; prepare specific requests and status updates; explain impacts and record confirmations | Customer facilities, operations, authorized customer decision-maker, PM | A proposed interruption conflicts with a recorded production constraint; seek an alternative or authorized decision |
| CAP08 | Learning across deployments | Propose checklist and template improvements from observed failures; preserve applicability and review before adopting new policy | PM, technical/process owner | A repeated missing-document problem yields a scoped checklist proposal without converting a local condition into a universal rule |

## 3. What automation means

The ambition is full coverage of the PM's digital coordination and decision-support work. The system should perform permitted routine steps, rather than only describe what a PM could do. Each action is classified as:

1. Autonomous within an explicit policy: record observations, identify missing evidence, calculate impacts, prepare requests, update permitted records and progress eligible work.
2. Proposed pending a decision: changes requiring project, commercial, technical or customer authorization.
3. Externally performed and evidenced: physical construction, measurements, inspections, tests and professional or institutional approvals.

For the third class, automation covers preparation, scheduling, information requests, evidence review, discrepancy tracking, escalation and recording authorized outcomes. An LLM's interpretation of a drawing or photograph does not establish an unobserved physical condition or manufacture a signoff.

All counterpart messages, bookings, submissions and physical events in the initial demo are simulated. Represent them as simulated in both UI and traces. No actual site control is part of the prototype.

## 4. People, authority and interaction model

Model role, actual project contact and current interaction state separately. Each stakeholder record contains organization, project scope, responsibilities, information they can provide, decisions they may authorize, source of that authority, contact route, delegation/escalation route, and active requests or commitments.

Candidate roles come from the source-grounded workstreams above. Additional contacts such as customer IT, logistics and commercial approvers are proposed where the case requires them, not asserted as EQORE's actual organization chart. Exact names and authority are synthetic until supplied or evidenced.

The simulator gives each actor bounded knowledge, permitted decisions, response timing, availability, objections and escalation behavior. Actors cannot know undisclosed events or approve outside their assigned scope. An actor's title or an incoming message claiming authority is insufficient to grant permission.

## 5. Knowledge and operational state

Maintain four related layers:

- Reference knowledge: EQORE business context, utility/local requirements and equipment documentation, with source, locator, date, version and applicability.
- Operational rules: reviewed prerequisites, evidence requirements, approval limits, allowed actions and escalation policies. Mark synthetic policies explicitly.
- Current project records: design, tasks, resource calendars, procurement, budget/change records, evidence, proposals, decisions, confirmations and revisions.
- Interaction records: requests, replies, promised dates, outstanding issues and owner/next-action assignments.

Use source applicability and project identity when assembling context. Keep historical evidence without allowing an older or differently scoped document to silently replace current facts. Approval validity is linked to its subject, conditions and revision.

## 6. Decision behavior and visualization

For each next-action recommendation, record:

`current facts → blocked requirement → downstream effect → feasible action → responsible person and authority → requested response → observable completion condition`.

Include source/evidence links, relevant deadlines, alternatives, independent work that can continue, and conditions requiring reconsideration. Priority uses project objectives, hard constraints, deadline sensitivity, work enabled and useful uncertainty reduction. Do not invent incident probabilities or claim a universal optimal priority score.

The UI renders the same structured records used by execution: project/portfolio view, dependency map, next-action card, evidence and authority view, pending decisions, cost/schedule consequences and action history. Visual explanation is not treated as proof that an action occurred.

## 7. Live LLM and controlled tools

Use real LLM calls for evidence interpretation, option generation, uncertainty assessment, next-action selection, stakeholder requests and explanations. Distinct logical product agents remain coordinator, evidence/requirements and recovery planning, with shared authoritative project records and structured handoffs.

Code validates dependencies, resource availability, permission scope, evidence linkage, duplicate events, revision freshness and committed state changes. Explicit operations must cover proposal persistence, decision requests and authorized resolutions, atomic plan commitment, mocked booking operations and reconciliation queries.

Define which observations and changes require proposal revalidation. Receipt of approval for an unchanged proposal must not create an endless invalidation loop. Recheck relevant constraints at commitment; distinguish facts/evidence updates from changes to an approved plan.

On November 7, 2026, the installed Codex client reported ChatGPT authentication, and one minimal live inference request completed successfully. The local product-to-runtime adapter and isolated product contexts remain to be implemented and tested. This check verifies connectivity, not product functionality. Product decisions must use fresh inference; any replayed model output is explicitly identified as replay.

## 8. Realistic simulation and evaluation

The research/scenario-authoring process produces sourced mechanisms and internally consistent synthetic projects. Each executable case defines initial records, applicable requirements, people and authority, visible documents, resource calendars, event timing, actor responses, budgets, acceptable outcomes and reset behavior.

Run cases through the current product's real interfaces. Pin product/scenario versions, model/prompt configuration, rules, initial state and event seed. Keep the simulator's hidden truth, future events and expected outcomes unavailable to runtime agents. Validate scenario reachability and assumptions before scoring.

Hard checks cover truth of approvals, authorization, feasible commitments, version/evidence integrity, idempotence, accurate reporting and required progress. Qualitative review addresses the usefulness of next actions and explanations. Accept multiple valid sequences; the same model in another role is not independent ground truth. Distinguish intermediate waiting from terminal correct-block, and require an observable reason for blocking.

Report coverage by CAP01–CAP08, not only aggregate scenario pass rate. Track useful completion and remaining blockers, customer-constraint compliance, schedule/cost consequences under assumptions, avoidable requests or changes, tool/model usage and repeated-run variability. Preserve failed traces and regression cases. Scored runs cannot rewrite their own expectations.

Maintain the proposed initial budget of 8–12 development cases, allowing cases to cover multiple capabilities. Add 4–6 fresh holdout cases after the specification stabilizes. Expand the suite if this budget leaves important responsibilities untested. Synthetic results do not establish historical EQORE incident rates or operational savings.

## 9. Refined delivery sequence

### Planning outputs first

1. Evidence/applicability register and CAP01–CAP08 coverage matrix.
2. Full deployment workflow and stakeholder/authority map.
3. Decision casebook with varied knowledge and authority conditions.
4. State/tool contracts, revision rules and two complete initial fixtures.
5. Paper execution traces, visual storyboard and independent acceptance checks.

### Later implementation, when requested

1. Build shared state, scoped knowledge retrieval, controlled operations and simulator with a fixed-rule reference run.
2. Implement a thin normal lifecycle from contract through simulated commissioning/handoff, with physical steps supplied as external evidence events. This represents every workstream; detailed automation maturity remains visible.
3. Make delivery recovery the first deep interaction, including resource conflicts, customer windows, decision authority, procurement and an explicit cost/change consequence where relevant. Connect live LLM decisions early.
4. Expand to design/review changes, missing or failed verification evidence, failed commissioning/controls readiness, and customer constraints.
5. Add a second synthetic project to test shared resources and portfolio priorities; test checklist-improvement proposals separately from policy adoption.
6. Run regressions and fresh holdouts, compare the baseline and agent versions, and polish the visual demo once persisted behavior is verified.

The first detailed case is an entry point into the complete PM workflow. A responsibility represented only by a placeholder or simulated external event will be labelled accordingly; it will not be reported as implemented autonomous capability.

## 10. Open assumptions to resolve or configure

- EQORE's internal approval/delegation limits and escalation policies.
- Actual stakeholder directory, existing tools and integration contracts.
- Synthetic site's jurisdiction, utility pathway, equipment configuration and required evidence.
- Explicit project priorities, cost assumptions, resource calendars and response delays.
- Which human decisions the demo exposes interactively versus which authorized actor responses are scripted.

Public research supports the workflow; these unknowns do not require inventing private company policy or blocking the prototype on unavailable sponsor data.
