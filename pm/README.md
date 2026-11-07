# EQORE PM platform (demo)

The project manager's side of the installation-coordination tool. A PM signs in with their work email, sees their own portfolio on a map, and opens a dashboard for each project. Contractors don't use a portal: they work by email, and the PM emails them from here through their own Gmail account.

The look comes from the deployment workspace in `eqore-demo/` (it loads `eqore-demo/web/styles.css` directly). All projects, companies, people and documents are synthetic demo data (`data.js`).

## Run

From the repo root (Python 3.10+, standard library only):

```sh
python pm/server.py          # then open http://localhost:8790/
```

Use `localhost`, not `127.0.0.1` (the server redirects you): Google's sign-in sends you back to `localhost`, and the sign-in cookie has to match.

**Demo accounts** (password `demo`, synthetic inbox and calendar): `jordan.lee@eqore.demo.example` (Eastern MA, 14 projects), `sam.ortiz@eqore.demo.example` (Central/Western MA, 11), `priya.shah@eqore.demo.example` (California, 12).

## Pages

- **Login:** work email. A Google account goes through Google's own sign-in, which signs the PM in here *and* connects Gmail and Google Calendar in one step. EQORE never sees the Google password. The demo accounts use a password.
- **Portfolio:** a map of the PM's projects (scroll or pinch to zoom). Green = on schedule, yellow = an action item for the PM (due within 3 work days or overdue), red = a reported problem that moves go-live. Hover a dot for the name and status; click it to open the project. The three-line menu (top right, opens on hover) has Portfolio, Dashboard (each project) and Log out.
- **Project dashboard:**
  - **Timeline:** 16 steps from contract to energize, with a line filled in up to the current step. Completed steps show their dates. Green when on time, red when behind. The Timeline page adds planned and forecast dates, owners and slack.
  - **Calendar:** a month view of task starts, milestones, paperwork due dates and meetings, plus the PM's own Google Calendar when signed in with Google. Click it for the large view.
  - **Inbox:** paperwork emails (documents to sign or complete) scanned from Gmail, labelled by department (permitting, utility, contracts, procurement, engineering, construction). Click an email to open it in Gmail, or "Go to my email" for the inbox.
  - **To do:** delays, documents the PM has to fill out or sign, PM tasks, and contractors to chase, sorted by urgency.
  - **Document center:** a link to the document center page. Yichang is building the full version; for now the page lists each document and its status.
  - **Subcontractors:** their open items, delays and recent updates.
- **Subcontractors page:** tasks by contractor, colour-coded against the timeline (done, in progress, at risk, pushed back by someone else's delay, delayed by their own problem). Each contractor has a **Documents** popup (signing history and who has to act next: PM, contractor or customer) and an **Email** button that drafts a message and sends it from the PM's Gmail. The **Contractor database** popup searches all companies by job type, task, name, state and availability. Availability counts the company's EQORE jobs on every project, their crew count, and work booked with other clients.

## Document center hand-off

Subcontractor task chips and each document in a contractor's **Documents** popup link into the document center: a document opens that exact document, and a task chip opens the paperwork for that step. Today they open this app's document page, scrolled to the document and highlighted. When the full document center is ready, set `DOC_CENTER` in `app.js` to a function that builds its URL. It receives a query string with `project` plus either `doc` (the document id) or `step` (the step key). Document ids are stable: `<JOB>:<step>:doc<n>`, for example `JOB-001:interconnection:doc1` (the interconnection agreement).

## Connect Gmail and Google Calendar (about 5 minutes)

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project (or pick one).
2. **APIs & Services → Library:** enable the **Gmail API** and the **Google Calendar API**.
3. **APIs & Services → OAuth consent screen:** choose *External* (or *Internal* for a Workspace org), fill in the app name and your email, and add yourself (and teammates) as **test users**.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID:** type *Web application*. Under *Authorized redirect URIs*, add `http://localhost:8790/auth/google/callback`.
5. Either download the JSON and save it as `pm/google_oauth.json` (git-ignored), or set environment variables:
   ```sh
   export GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   export GOOGLE_CLIENT_SECRET=...
   ```
6. Restart `python pm/server.py`. It prints `Google sign-in ready`.

Permissions requested: sign-in (`openid email profile`), read Gmail (`gmail.readonly`), send as the PM (`gmail.send`), and read the calendar (`calendar.readonly`). Google tokens are held only in the server's memory for the session and never reach the browser. A Google account that isn't one of the demo PMs sees Jordan's sample portfolio (set `PM_DEFAULT_PORTFOLIO` to change it) with its own real inbox and calendar.

## Tests

```sh
node pm/model.test.js
```

## Files

| File | What it does |
| --- | --- |
| `server.py` | Serves the repo root, sign-in (demo accounts and Google OAuth), Gmail paperwork scan, Google Calendar, sending email |
| `data.js` | Synthetic data: PMs, the 16-step template and its paperwork, companies (from the old contractor portal's database), 37 MA/CA projects, reported delays |
| `model.js` | Forecast (forward pass) and slack (backward pass), project status, to-dos, documents, calendar items, subcontractor updates, contractor availability |
| `app.js`, `index.html`, `styles.css` | The app |
| `model.test.js` | Node tests for the model |
