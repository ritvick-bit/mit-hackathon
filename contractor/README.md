# EQORE contractor portal (demo)

The contractor and agency side of the installation-coordination tool. It uses the same look as the deployment workspace in `eqore-demo/` (it loads `eqore-demo/web/styles.css` directly) and the same 25 jobs as `command-center/` (it loads `command-center/data.js`), so job IDs match the PM map.

All companies, people, sites, rates and dates are synthetic demo data.

## Run

From the repo root (Python 3.10+, standard library only):

```sh
python contractor/server.py          # http://127.0.0.1:8780/
```

Sign in with any demo account from the drop-down on the login page (password `demo`). Use two browser tabs to see both sides at once: a contractor in one, the PM (`pm@eqore.demo.example`) in the other. The sign-in is per tab, and both tabs share one record kept by the server in `contractor/data/` (git-ignored). **Reset demo** in the sidebar restores the starting data for everyone.

## What a contractor can do

- **Tasks & timeline:** every task they own across all projects, a three-week timeline, and a notice when the PM or another contractor's update moves one of their dates.
- **Mark done:** "Is this done? Yes, done" records the finish, recalculates that project's timeline (every downstream task and the go-live date), logs it for the PM and tells every contractor whose dates moved. A task can't be marked done while it's still waiting on another task.
- **Report a problem:** details, photos (resized in the browser, stored by the server), urgency 1–5 (1 is most urgent), and optionally a request for another company:
  - *They take over this task* or *They do work before this task*, type of company, work days and start date.
  - **Check available companies** searches the contractor database (`db.js`): same trade, same state, within the company's service radius, free on those days given their EQORE tasks and outside bookings, plus travel/mobilization time. Each option shows the go-live date the project would have and the cost.
  - If nobody is available, the report goes to the PM marked **urgent**.
- **Project timeline:** the full 12-step timeline for any project they work on, with owners and what each step waits on.

## What the PM does

- **Approvals:** reports sorted urgent first, each with an **AI summary**, the contractor's text and photos, current go-live and the resource options. **Approve** re-checks the company is still free, then books it: the task (or a new task) appears on that company's dashboard, every affected date moves, and every affected contractor sees an update. **Decline / Acknowledge** sends the PM's note back to the contractor.
- **Projects:** all projects with next task, owner, go-live versus target and open reports. **Activity:** the audit trail.

## AI summary

`server.py` calls Claude (`claude-opus-5-5`) through the Anthropic Python SDK, with the report text, photos and project record. To turn it on:

```sh
pip install anthropic
export ANTHROPIC_API_KEY=...         # or: ant auth login
```

Without the SDK or credentials, the PM sees a **fixed-rule summary** labelled with the reason the AI summary was unavailable. It never presents a rule-based summary as AI output.

## Tests

```sh
node contractor/model.test.js
```

## Files

| File | What it does |
| --- | --- |
| `server.py` | Serves the repo root, shared state with version checks, photo uploads, AI summary |
| `db.js` | Sample contractor and agency database: trade, base, crews, rates, certifications, service radius, outside bookings |
| `model.js` | Project timelines (forward pass), contractor tasks, done/report actions, resource search, PM approval, change notices |
| `app.js`, `index.html`, `styles.css` | The portal UI (login, contractor pages, PM pages) |
| `model.test.js` | Node tests for the model |
