# EQORE deployment workspace — v0.4

A local hackathon prototype for battery deployment coordination. It records project facts, identifies blocked work, recommends the next useful action and person to contact, and executes controlled **simulated** operations. The knowledge library is grounded in EQORE's published [deployment PM responsibilities](https://www.eqore.com/careers/project-manager-deployments), with source scope and synthetic assumptions visible.

## Start

Requires Python 3.10+ and access to the private GitHub repository. The fixed-rule app and automated tests run without ChatGPT or a Codex login. The application has no frontend build step or third-party Python dependencies on systems with an IANA timezone database. Windows installations may need the `tzdata` package for `America/New_York`.

```sh
git clone https://github.com/ritvick-bit/mit-hackathon.git
cd mit-hackathon/eqore-demo
python3 server.py
```

Open **http://127.0.0.1:8765**. The service binds only to the local machine. Use `--port 8766` if the port is occupied. Current state, audit snapshots and evaluation reports persist in `data/eqore.sqlite3`; each demo project retains its own state, event cursor and latest recommendation. Switching projects resumes saved progress. Explicit reset affects only the selected project; audit and reasoning history are retained. A newer demo-world version refreshes only untouched openings, archives their previous state, and preserves projects with recorded progress.

A fresh clone creates its own database and seeds all three demo projects. Project progress, saved recommendations and evaluation history are local to each teammate. Committed JSON validation reports are reference files; they are not automatically imported into the new database or shown as saved Evaluation/Challenge lab runs. Run the evaluations from the app to populate your own history. Databases, credentials and newly generated runtime artifacts are excluded from Git.

For live judgment, each teammate needs a compatible `codex` CLI on their `PATH` and must sign in with their own ChatGPT account (`codex login`, then `codex login status`). The app calls that authenticated runtime; it does not use canned model answers or copy credentials. Authentication is checked at server startup, so restart the service after signing in. The first screen deliberately labels its deterministic recommendation **Fixed-rule baseline**. **Rethink with ChatGPT** makes three fresh agent calls and displays **Live LLM judgment** on success. Failed live calls remain errors and never silently become baseline results.

Optional configuration:

- `EQORE_MODEL`: explicit Codex model name; otherwise the runtime default is used and is labelled unpinned in traces.
- `EQORE_MODEL_TIMEOUT`: timeout per agent call in seconds, default 150.
- `python3 server.py --db /path/to/new.sqlite3`: separate local demo database.

## Working together

Read the team repository’s `AGENTS.md` and `docs/CHALLENGE.md`, then create a branch before making changes. Run the current 153-test suite from `eqore-demo/` and open a pull request against `main`:

```sh
git switch main
git pull --ff-only
git switch -c codex/describe-your-change
# Make your changes, then run:
python3 -m unittest discover -s tests -v
git add -p
git commit -m "Describe the change"
git push -u origin codex/describe-your-change
```

Coordinate the issue and branch naming with the team’s repository rules, and include the behavior change and relevant validation in the pull request. Keep local databases and authentication out of commits. The three frozen challenge artifacts in `data/` are tracked test inputs; preserve their bytes and recorded failures when changing the implementation. Add new evaluation reports separately when they provide useful evidence.

## Five-minute walkthrough

1. Open **Demo projects** and choose Harbor Components, Millbrook Cold Storage or Riverbend Logistics. They represent different deployment stages, systems, budgets and constraints; switching preserves each project’s progress.
2. In **Project workspace**, inspect every ranked bottleneck. Current issues, waiting responses and upcoming prerequisites are labelled separately. Expand a row to see who owns it, its evidence and the work it affects. Ranking is an explicit fixed-rule aid; it is not a calculated critical path.
3. Open **Phases & timeline** to inspect the eight post-signing groups, responsible people, acceptance criteria, blockers and return paths. More than one phase may be active. Planned task dates, recorded work completion and current acceptance are displayed separately.
4. Open **Budget & resources** for the cost breakdown, dated recorded spending, proposed/committed changes, labor assumptions, resource windows, milestones and site assumptions. Estimated total means known committed cost plus current proposed exposure; actual invoices do not appear merely because a task finishes.
5. Click **Rethink with ChatGPT**. All three agents receive the observed project, its phases, open corrections, issue queue and costs. Execute the selected action and simulate counterpart replies. In **Plan & decisions**, review approvals, commitment and separate contractor confirmations.
6. **Advance simulation** introduces a later update when the project reaches its relevant stage. The project already contains observed issues at opening. A returned review or later fault can reopen affected acceptance while retaining earlier physical-work records. Inspect saved reasoning and export records in **Activity history**.
7. Open **Facts → constraint → next step** below a recommendation for its observed records, rule, consequence, permitted action, uncertainty and reconsideration conditions. In **Plan & decisions**, expand **Required evidence & basis** for each gate’s artifacts and public references.
8. In **Evaluation lab**, use **Test all demo projects** for three complete development runs. The 14 targeted cases remain a separate suite. **Open test case** is explicit; saved demo projects can be resumed afterward.
9. In **Challenge lab**, inspect the separately generated ChatGPT challenge set and run its checks. Saved runs are local to your database; committed before/after reports can also be inspected as JSON files. Fresh live product-agent probes are labelled separately from fixed-rule checks. Per-case coverage limits remain visible.

| Demo project | System assumption | Baseline | Opening situation |
| --- | --- | --- | --- |
| Harbor Components | 250 kW / 500 kWh | $240,000 | Permit and shutdown approvals plus an observed delivery conflict |
| Millbrook Cold Storage | 500 kW / 1,000 kWh | $395,000 | Signed scope, survey/design and later institutional reviews |
| Riverbend Logistics | 300 kW / 600 kWh | $310,000 | Installed system awaiting field verification, customer IT and operating acceptance |

All three use a 14-task contract-to-handoff lifecycle, with 17 stakeholders, 13 readiness/authority gates and five later stage-dependent updates per project (world version `3.0.0`). Existing completed work is evidenced at opening. Fire review, physical receiving, installer correction, independent field verification, final inspection, closeout documents, customer training and fleet acceptance have distinct owners and prerequisites. Millbrook spans November 2026–February 2027; the later-stage projects retain August contract history. Institutional acknowledgements leave approval pending until a later scoped response. Budgets, invoice snapshots, staffing, equipment sizes and local pathways are invented assumptions. A simulated physical-completion response advances the simulation clock; it does not assert real work occurred.

## Phases, source map and scoped rework

The eight application groups are **signed scope; site survey and design; permits and utility review; procurement and site preparation; delivery and installation; verification and operating authorization; operational commissioning; documents, training and fleet handoff**. They organize the task/gate model without requiring every preceding phase to finish before any later work starts. `current` means some recorded work can advance; it does not mean field work has started. A completed work package can retain its history while its acceptance is reopened.

The supplied `Battery Deployment flow.html` contains 21 nodes, six broad phase bands and four drawn rejection loops. Its post-signing structure was reviewed against primary EQORE, utility, local-authority and standards sources. The earlier Markdown export contained only introductory text; the full HTML is now available. **Source map review & application coverage** provides 17 mappings of its post-signing/operations nodes to application tasks and gates, including explicit aggregations and scope limits. The HTML’s loops are decorative in its scheduling calculation, and its duration ranges are illustrative. Its default graph computes 21.5 weeks after signing; that is authored scenario arithmetic, not a verified forecast. The app does not import those durations or claim a critical-path calculation.

Corrections include separate shipping and physical receipt, installation-stage utility review versus final operating authorization, and scoped correction instead of automatically restarting design or electrical installation. Applicable utility witness/acceptance testing can precede final written operating authorization; the app’s later commissioning task is **operational commissioning**. Equipment certification, fire-test evidence and local approval remain different records. Public reference scope and inferred product rules are labelled in `knowledge.json`.

Harbor now receives a returned permit-amendment package, Millbrook receives utility comments on inconsistent equipment identifiers, and Riverbend experiences a firewall change after accepted commissioning. A correction request identifies its owner, affected work and required artifact. Correction evidence does not grant reviewer approval: the responsible reviewer must accept a current package, and affected verification, testing or handoff must be evidenced again. Old evidence and superseded response cycles cannot silently close a new correction. Unaffected physical installation and prior completion history remain intact.

`engine.project_complete(state)` closes a project only when every task is complete, every modeled gate passes current acceptance checks, no unresolved/non-superseded rework remains, and no open alert remains. A historical handoff record alone does not make a reopened project complete.

## Implementation

| File | Responsibility |
| --- | --- |
| `server.py` | Local HTTP API, background reasoning/evaluation jobs and explicit simulator controls |
| `storage.py` | SQLite snapshots, durable audit history, reports and stale-state conflict protection |
| `engine.py` | Dependencies, calendars, permission checks, scoped correction/retest cycles, proposals, atomic commitment and current project acceptance |
| `phases.py` | Read-only post-signing phase status, planned/actual distinctions, acceptance dependencies and observed return paths |
| `reasoning.py` | Checkable causal explanations with exact observed fact references and snapshot digests |
| `challenges.py` | Independent LLM challenge design, frozen before-state probes and auditable reruns |
| `llm.py` | Fresh evidence, planning and coordinator agents through ChatGPT/Codex; structured validated handoffs |
| `projects.py` | Three complete project worlds, cost/labor assumptions and private staged updates |
| `dashboard.py` | Complete ranked issue queue, cost reconciliation, milestones and resource summary |
| `scenarios.py` | Original 14 targeted development cases and bounded stakeholder responses |
| `project_evaluation.py` | Whole-project runs with independent transition, scope and outcome checks |
| `knowledge.json` | Public references, source-map review and 17 coverage mappings, applicability and explicit synthetic policies |
| `evaluation.py` | Independent outcome checks and traces using the actual engine operations |
| `web/` | Responsive operations interface, decision/dependency views and evaluation lab |
| `tests/` | Adversarial engine checks, fixture validation, evaluator negative controls and HTTP integration tests |

The model receives curated observed project records, public rework records, compact derived phase status, applicable source summaries and feasible action candidates. It interprets evidence and selects an action, supporting facts and prioritization grounds; the engine owns feasibility and permissions. Each action’s short explanation is built from exact project facts. Live output cannot replace those dates, costs, authority or executable request with invented prose. The separate model drafts are retained and labelled in traces. Runtime prompts exclude scenario names, future events and expected answers. Each agent runs in a fresh temporary working directory with filesystem-command, browser, app, plugin, collaboration and memory features disabled. Tool-call output is rejected. This is a local demo boundary, not process-level isolation of separate production services.

User execution is separate from recommendation. A recommendation binds to the current snapshot; a concurrent project change discards an in-flight result. Browser mutations carry a session version. Internal approval, plan commitment, contractor confirmation and physical completion remain distinct. Approver delegation is rechecked at commitment. Acknowledgements keep a request open; the synthetic policy permits follow-up at 24 hours and escalation at 48 hours. Physical receipt is required for unloading, while an ETA can support advance planning. Model text cannot resolve an approval or supply physical evidence. The explicit approval controls impersonate a synthetic role only within this demo; production authentication/authorization is not implemented.

## Tests and evaluation

```sh
python3 -m unittest discover -s tests -v
python3 evaluation.py --output data/baseline-evaluation.json
python3 evaluation.py --live --case delivery_delay --case wrong_scope --output data/live-evaluation.json
```

The HTTP integration test requires permission to bind a localhost socket. Live tests use the existing ChatGPT account and can take several minutes per case. The full 14-case suite defaults to the fixed-rule baseline. A failed evaluation exits with a report identifying failed checks; inspect the summary and case traces.

Development cases cover normal progress, delivery recovery, delay within slack, issued-design changes, utility acknowledgements, field discrepancies, network readiness, customer nonresponse, duplicate/older messages, stale approval, shared crews, commercial approval, scoped checklist review and wrong-project evidence with embedded hostile instructions.

Evaluations check observed actions and final state, including required progress. Always waiting fails a reachable case. Honest blocking passes only when the required external response is unavailable under the scenario and the appropriate contact was requested. Case reports preserve hashes, mode, action traces, checks and live-agent call metadata. These are visible development fixtures; no sealed holdout or real-world effectiveness claim is made. Model output can vary; the default model is not pinned unless `EQORE_MODEL` is set.

**Current v0.4 validation:** 153 automated tests passed in the final regression run. All **14/14 targeted baseline cases**, **3/3 whole-project baseline runs** and **12/12 existing independent executable challenge subsets** pass. Every whole-project run processed all five staged updates and reached current accepted handoff. Reports are `data/baseline-evaluation-v04.json`, `data/project-evaluation-v04.json` and `data/challenge-results-after-v04.json`.

The challenge rerun uses the existing independently authored set and frozen opening snapshots; it is not a newly generated held-out suite for every phase feature. Seven challenge dimensions remain only partially covered, as the report states. General linked-change accounting, dynamically creating corrective physical-work tasks and targeted cost-explanation quality remain outside those executable checks.

Two selected fresh live decisions also pass, using **six fresh role calls**, in `data/phase-live-decisions-v04.json`: Harbor requests the corrected engineering package; Riverbend requests restoration of the agreed IT route while the affected controls retest remains required. These are two isolated decisions, **not full live-LLM runs** of the projects. Earlier baseline, challenge and live reports remain preserved; they describe their own versions.

The repository includes those four v0.4 reports, `data/phases-v04.png`, and the three frozen challenge test artifacts: `data/challenge-design-v03.json`, `data/challenge-results-before-v03.json`, and `data/challenge-live-before-v03.json`. Other historical report filenames below refer to the original development workspace and are not included in a fresh clone. Their results describe the recorded versions; rerunning a suite creates a new local report.

**Previous v0.3 validation:** 117 automated tests passed; all 14 targeted baseline cases and all 3 complete-project baseline runs passed. Each expanded project processed 4 staged updates and reached evidenced handoff. Reports are `data/baseline-evaluation-v03.json` and `data/project-evaluation-v03.json`.

A separate fresh ChatGPT designer generated 12 adversarial challenges from frozen public observations and interfaces. BEFORE execution found two failures: commitment accepted after approver authority revocation, and an immediate duplicate request after acknowledgement. Both were fixed; the original failures remain in `data/challenge-results-before-v03.json`, and all 12 executed AFTER probe subsets pass in `data/challenge-results-after-v03.json`. Fresh product-agent checks then found an explanation defect in two early-stage cases: a proposed design was described as issued/approved. Those original live traces and failures remain in `data/challenge-live-before-v03.json`; the design-status distinction is now enforced against scoped acceptance evidence. Fresh post-fix live probes pass in all 3 selected cases (CH01, CH08, CH11), with 9 fresh role calls, in `data/challenge-live-probes-v03.json`. CH01 offers 4 permitted candidates; the other two exercise a single permitted next step. A separate fresh three-role decision on the expanded Harbor project selected the delivery recovery action with its exact date conflict; see `data/project-live-decision-v03.json`. These are selected live decisions, not complete live runs of all three projects. A passing probe covers its implemented checks, not every authored design dimension. Unimplemented linked-change aggregation, corrective-task creation and targeted cost-explanation quality remain explicitly untested.

**Previous v0.2 project-dashboard validation:** 75 automated checks passed, including persistence across project switches, stale-state isolation, cost reconciliation, complete issue queues and authority boundaries. All 14 targeted baseline cases and all 3 whole-project baseline runs passed; each full project processed both staged updates and reached evidenced handoff. Those versioned reports are `data/baseline-evaluation-v02.json` and `data/project-evaluation-v02.json`. A fresh three-agent ChatGPT smoke test also selected the earliest permit authority dependency from Harbor’s complete project context; its observed state and decision are saved in `data/project-live-decision-v02.json`. The three new full-project runs are baseline evaluations, not full live-LLM runs.

Previous version validation on November 7, 2026: **50 automated checks passed; all 14 baseline cases passed; both selected live cases passed across 57 fresh agent calls.** Delivery recovery reached handoff, while wrong-project approval left commissioning correctly blocked. Reports were saved in the original workspace as `data/baseline-evaluation.json` and `data/live-evaluation.json` and imported into that workspace's Evaluation lab. The final persistence layer also replayed all 13 recorded live delivery actions, reproduced the same final state and retained all 13 reasoning snapshots; that explicitly labelled replay was recorded in `data/persistent-replay-validation.json`.

## Current scope

All projects, contacts, costs, delegation limits and counterpart responses are synthetic. No real email, permit submission, booking, payment or equipment control occurs. Public references are contextual evidence, not an EQORE internal SOP or a determination of project-specific engineering/regulatory compliance.

The scope begins with a signed agreement and ends at accepted handoff. Sales qualification, pre-signing negotiations and ongoing dispatch/O&M are excluded. Program eligibility/status may be carried in handoff information; actual enrollment, seasonal eligibility decisions, program revenue and savings are not simulated.

The prototype covers the PM workstreams at different depths. Delivery recovery and authority tracking are executable; three independently saved project workspaces support inspection and continued execution. Shared resources remain recorded reservations; the app does not optimize staffing across an interactive portfolio. Checklist learning reviews a scoped authored proposal rather than mining a historical corpus. Physical inspections and tests arrive as simulated qualified-actor evidence. Production integrations, document ingestion, real identity/delegation, richer schedule optimization, fresh holdouts and repeated live evaluations remain future work.

The detailed planning record remains in `EQORE_PM_GROUNDED_PLAN_v0_2.md`; it is historical planning context, not a claim that all planned production capabilities are finished.
