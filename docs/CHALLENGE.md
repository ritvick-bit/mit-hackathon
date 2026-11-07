# Challenge brief: eqore, MIT Energy & Climate Hack 2026

Every agent reads this before starting work. It covers the problem, the deployment process the tool has to model, and the MVP scope.

## The company

eqore is a Somerville, MA startup (MIT/Duke founders, CEO Valeriia Tyshchenko, $1.7M seed in Nov 2025). It installs and operates behind-the-meter batteries at commercial and industrial (C&I) sites. Most are mid-size factories in New England (MA, NH) and California.

- **Customers:** facilities that spend $10K+/month on electricity (e.g., Aalberts Surface Technologies, ThermoFusion, Newton Heat Treating).
- **Why the battery pays off:** demand charges. Part of a factory's monthly bill is set by its single highest short power spike. When several machines start at once, one spike can add thousands of dollars. The battery charges when demand is low and discharges during peaks. Other revenue: time-of-use arbitrage, grid programs (ConnectedSolutions, MA Clean Peak Standard), and lower capacity charges.
- **Business model:**
  - Shared savings: $0 upfront. eqore owns and operates the system and splits the savings.
  - Purchase: the customer buys the system and pays eqore a subscription to operate it. Payback is 2–3 years.
- **Product stack:** QoreSense (metering), QoreAI (forecasts peaks and decides when to dispatch), QoreControl (battery control), QorePack (battery, e.g., 200 kW / 400 kWh).
- **Typical timeline:** 3–6 months from contract to a live system. Most of that is waiting on permits and the utility. The on-site work takes days.

## The industry problem

C&I sites use more than 60% of U.S. electricity but get about 1% of recent U.S. battery deployments. The bottleneck isn't the battery technology. It's the soft costs and coordination of deploying many small projects (a few hundred kW each). Operators only make money at portfolio scale: tens to hundreds of sites in different stages at once.

## The challenge prompt

> Build a tool that tackles one major bottleneck in deploying commercial battery storage so teams can manage tens to hundreds of projects at once.

eqore named four bottlenecks: (1) reliable site data, (2) adaptable site plans, (3) review and revisions, and (4) installation coordination.

**We chose #4: installation coordination.**

eqore's suggested direction: build *a tool that tells the project lead what the next action is, who owns it, and what it is waiting for, so a late delivery or inspection is visible before it holds everything else up.*

## The deployment process the tool must model

### Phase 1: Sign the customer (~2–6 weeks)

| # | Step | Parties | Needs |
|---|---|---|---|
| 1 | Lead & qualification | eqore sales, plant manager, customer finance | $10K+/mo spend, demand-charge tariff, outdoor space |
| 2 | Savings assessment | eqore analyst, utility data portal | Bill, 12 months of 15-min interval data, tariff |
| 3 | Site visit & proposal | eqore field engineer, facilities lead, customer's electrician | Location, tie-in point at main switchgear, fire access, photos, existing one-line diagram |
| 4 | Contract & approvals | Customer budget owner, landlord (if leased), insurer | Signed agreement, landlord consent package, insurance certificate |

**Gate: contract signed.**

### Phase 2: Engineering (~2–6 weeks)

| # | Step | Parties | Needs / produces |
|---|---|---|---|
| 5 | Select equipment | eqore engineering, battery/inverter supplier | Needs a UL 9540 listing, a UL 9540A fire-test report for that exact model, spec sheets, and a lead-time quote |
| 6 | Stamped engineering | Electrical PE, structural/civil PE, fire protection engineer | Produces one-line/three-line diagrams, arc-flash study, pad/anchoring design, NFPA 855 package, emergency response plan |

**Gate: stamped plan set.** Three parallel tracks start.

### Phase 3: Three parallel tracks (~1–4+ months)

- **3A Permitting:** building department, wiring inspector, fire marshal, master electrician. Reviewer comments loop back to engineering.
- **3B Utility interconnection:** the utility's interconnection engineer (National Grid, Eversource, PG&E). Usually the longest step. Produces the interconnection agreement and continues until Permission to Operate (PTO).
- **3C Procurement:** battery/inverter supplier, switchgear supplier, freight carrier, crane/rigging company. Lead times are 2–5+ months.

**Coupling risk:** if a reviewer or the utility forces an equipment change, all three tracks go back for revision.

### Phase 4: Construction (~1–3 weeks on site)

| # | Step | Parties | Depends on |
|---|---|---|---|
| 7 | Pre-construction scheduling | eqore PM, facilities manager, electrician, crane company | Permits issued, delivery date, crew and crane booked, customer shutdown window |
| 8 | Civil work | Concrete/civil sub, fencing/bollard installer | The pad needs ~7+ days to cure |
| 9 | Delivery & placement | Freight carrier, crane crew | Cured pad AND equipment delivered |
| 10 | Electrical installation | Licensed electrical contractor | A rough inspection must pass before trenches are filled |
| 11 | Tie-in to switchgear | Electrician + customer | A planned power shutdown (often a weekend) |
| 12 | Controls & comms (parallel with 10–11) | eqore controls team, customer IT | |

### Phase 5: Inspections & switch-on (~1–4 weeks)

| # | Step | Parties | Notes |
|---|---|---|---|
| 13 | Final inspections | Building inspector, wiring inspector, fire marshal | A failure loops back to step 10 |
| 14 | Commissioning | Manufacturer field tech + eqore | |
| 15 | Utility PTO | Utility | Needs the interconnection agreement (3B), certificate of completion, inspection sign-offs, and sometimes a witness test or meter swap. **The battery cannot run before PTO.** |
| 16 | Energize & hand over | eqore | QoreAI calibrates; the customer gets a dashboard |

### Phase 6: Operations

| # | Step | Notes |
|---|---|---|
| 17 | Program enrollment | Seasonal deadlines. Missing summer can cost a year of program revenue. |
| 18 | Operate & maintain | 10+ years |

**Illustrative schedule:** live about 28 weeks after first contact (about 21 weeks after contract). The critical path usually runs through utility interconnection → PTO.

## What's hard for a project lead with 50–200 sites

- **Cross-party dependencies:** one task (e.g., "set cabinets") can be waiting on a supplier, a subcontractor, a permit, and the customer's shutdown window all at once.
- **Shared resources:** the same electrical crew, crane company, or town fire marshal serves many projects, so one slip cascades.
- **Rework coupling:** one equipment change sends permits, interconnection, and procurement back for revision.
- **External deadlines:** program enrollment seasons, financing milestones, and tax-credit "placed in service" dates.
- **Today:** all of this lives in spreadsheets, email, and people's heads, so blockers are only discovered after they've caused a delay.

## MVP scope

1. **Data model:** Project → Tasks (from the 18-step template above). Each task has an owner party (role + company), status, planned/actual dates, duration, finish-to-start dependencies, required documents/inputs, and blockers.
2. **"Next action" view per project:** the next task, who owns it, and what it's waiting on.
3. **Portfolio view:** all projects on one screen, ranked by risk of slipping. Critical path computed per project (forward/backward pass, slack).
4. **Slip propagation:** when one date moves (e.g., a delivery is 3 weeks late), recompute every downstream task and the go-live date, and flag which other projects share that resource (crane, crew, inspector, utility).
5. **Early warnings:** "delivery lands before the pad is cured", "shutdown window not approved 2 weeks before tie-in", "PTO will miss the program enrollment deadline".
6. **Contractor/party view:** one list per contractor or agency of everything it owes across all projects.

**Optional AI layer:** parse emails or contractor updates into task status changes, and draft nudge messages to whoever owns a blocked task.

## Demo

Seed ~30–50 fake projects at different stages in MA/CA. Show the portfolio dashboard, then inject a supplier delay or a failed inspection. The audience watches affected projects re-rank, critical paths shift, and the tool surface the next actions and their owners.

## Constraints

- Hackathon timebox. Keep the stack simple (a web app).
- Durations are illustrative industry estimates, not eqore's real data. Use synthetic project data only.
