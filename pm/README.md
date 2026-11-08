# EQORE PM platform (demo)

The project manager's side of the installation-coordination tool. A PM signs in with their work email, sees their own portfolio on a map, and opens a dashboard for each project. Contractors don't use a portal: they work by email, and the PM emails them from here through their own Gmail account.

The look comes from the deployment workspace in `eqore-demo/` (it loads `eqore-demo/web/styles.css` directly), recoloured in `styles.css` to Black Pearl `#06162B` (headings, dark backgrounds), Abbey `#505455` (body text) and French Gray `#B9B9BB` (dividers, with lighter tints for backgrounds and cards). Red, yellow and green stay as status colours. The **document center is Yichang's** (Relay, from `eqore-demo/` on branch `codex/paperwork-coordination`), merged in as described below. All projects, companies, people and documents are synthetic demo data.

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
  - **Timeline:** 16 steps from contract to energize, with a line filled in up to the current step. Completed steps show their dates. Green when on time, red when behind. The Timeline page adds a **Gantt chart**: one bar per step for its forecast dates, with the original plan hatched behind it when it has moved, and a line for today. Bars are green when on the timeline, yellow when there is something to do soon (a to-do due within two weeks, a small slip, or at risk), and red when delayed (a reported problem, or 5+ work days late). Done steps are faded. Hovering a bar shows the step description, dates, owner and the reason for its colour. Clicking a bar or a table row opens the task: description, dates, slack, what it waits on and unlocks, your to-dos on it, products it needs and its documents. The task popup has its own link (`#/project/<JOB>/timeline?task=<step>`). The page also has a table of planned and forecast dates, owners and slack.
  - **Calendar:** a month view of task starts, milestones, paperwork due dates and meetings, plus the PM's own Google Calendar when signed in with Google. Click it for the large view.
  - **Inbox:** paperwork emails (documents to sign or complete) scanned from Gmail, labelled by department (permitting, utility, contracts, procurement, engineering, construction). Click an email to open it in Gmail, or "Go to my email" for the inbox.
  - **To do:** delays, documents the PM has to fill out or sign, PM tasks, and contractors to chase, sorted by urgency.
  - **Document center:** counts of complete, in-progress and waiting-on-you documents, and a link to the project's document center.
  - **Subcontractors:** their open items, delays and recent updates.
  - **Procurement:** delayed products and the next deliveries.
- **Procurement page:** every product bought for the project (battery cabinets, inverter, switchgear, materials, and anything the PM adds), with supplier, PO, status, and order, promised and expected delivery dates. The step each product is needed for is shown too. Clicking a delivery date opens the calendar on that day, and deliveries appear on the calendar. Delays (later than promised), expected delays (arriving after the step that needs it starts) and overdue deliveries are red. A late delivery holds back the step that needs it, so the timeline and go-live move and the project turns red. Each product has a **Documents** popup (purchase order, spec sheet, delivery receipt, plus any added) linked to the document center, and an **Email supplier** button with a draft that fits the situation.
- **Document center page:** Yichang's document center for this project (see below).
- **Subcontractors page:** tasks by contractor, colour-coded against the timeline (done, in progress, at risk, pushed back by someone else's delay, delayed by their own problem). Each contractor has a **Documents** popup (signing history and who has to act next: PM, contractor or customer) and an **Email** button that drafts a message and sends it from the PM's Gmail. The **Contractor database** popup searches all companies by job type, task, name, state and availability. Availability counts the company's EQORE jobs on every project, their crew count, and work booked with other clients.

## Adding and editing

The PM can add, edit and delete **products** (Procurement page) and **contractors** (Subcontractors page, or "Add" in the contractor database). **Documents** can be added (Add document on a contractor's or product's Documents popup), and their details edited (Edit details on any document card): name, step, product, due date and notes. Everything else about a document, such as drafts, packages, signatures, revisions and voiding, happens in the document center. For contractors, the PM can edit contact details and choose which steps they own on the project, which moves that step and its paperwork to them. A brand-new supplier or company can be created from the product and contractor forms. Product and contractor edits are saved per PM by the server in `pm/data/<PM id>.json`, and every timeline is recalculated. Documents are saved in `pm/data/paperwork.json`. Both are git-ignored. Delete the `pm/data/` folder to go back to the generated demo data.

## Document center (Yichang's Relay, merged)

`pm/doccenter/` is Yichang's document engine, copied unchanged from `eqore-demo/` (branch `codex/paperwork-coordination`, commit `1d6abe2`): `paperwork.py`, `paperwork_api.py`, `paperwork_connectors.py`, `paperwork_oauth.py`, `compliance.py` and `client_reference.py`. `doccenter.js` is his `web/paperwork.js`, with the same screens and actions, mounted in each project's **Document center** page. Its styles are in `doccenter.css`. The parts that connect it to this platform:

- **`adapter.py`:** uses this platform's sign-in (no profile picker), stores records in `pm/data/paperwork.json` instead of SQLite, and seeds each project. The first time a PM signs in, the app sends a plan for each of their projects. The plan contains his 20-document template (D01–D20) with each document dated from the project's timeline. Documents for finished work are replayed as completed, current ones are sent or partly signed, and a reported problem leaves its step's document returned. Each product also gets a purchase order, a spec sheet (for equipment) and a delivery receipt. After seeding, his records are the only source of documents: to-dos, the inbox, calendar paperwork dates, and the subcontractor and product Documents popups all read them. The adapter also adds two actions to his set, `add_document` and `edit_document_details`.
- **Small stand-ins** for the eqore-demo modules his code imported: `engine.py` (DomainError), `projects.py` (no delivery catalog), `storage.py` (JSON store with his optimistic-version contract) and `llm.py`. `llm.py` makes his reading summaries and email drafts run on **Claude** (`claude-opus-5-5`, Anthropic SDK) instead of ChatGPT via Codex. To turn it on, run `pip install anthropic` and set `ANTHROPIC_API_KEY`. Without them, the AI buttons are hidden, as in his version.
- **Features:** a project overview with next actions and stages, a document register (filter by status, stage, timeline step or product), and document detail with the document, original emails, signing events and dependencies. Actions include editing drafts, preparing local packages, revisions, voiding, sample responses and recording emails. There are also contact pages with signed history, the compliance coverage review against EQORE's 20 requirements (track a requirement, set review dates), EQORE references, and project archiving. Email drafts can be saved, copied or downloaded, or sent through the platform's compose window with **Send with my email**.
- **Signing (platform addition, `doccenter/signing.py`):** on a signature document you prepare, **Sign and send** works two ways:
  - *DocuSign connected:* **Sign with DocuSign and send** sends the envelope with you as the first signer, signing in the platform (embedded signing, in a window over the page), and the document's recipients as the next signers. DocuSign emails them once you have signed. When you finish, DocuSign returns you to the document, which records your signature and syncs the envelope. The other signers' signatures are recorded by his **Sync DocuSign status** from DocuSign's own records, never assumed. Each signer needs a real email address, set from their contact page (**Edit project contact**); the demo addresses can't receive mail.
  - *Not connected:* a signature pad (draw or type) signs the current revision in the platform. Your name, the time and a fingerprint of the exact text are saved, then the document goes to its recipients. **Email the signed copy** opens your email with the signed PDF attached: it is sent from your Gmail when you're signed in with Google, or downloads so you can attach it to a Gmail draft.
  - **View PDF** on any document renders it, with its signatures, as a PDF (`/api/paperwork/document.pdf`).
- **Versions (platform addition):** the **Versions** tab lists every revision with when and why it was replaced and whether you signed it. You can view any earlier revision with its signatures, compare it with the current one (added and removed lines), open or download it as a PDF, and edit: **Edit this draft**, **Edit in a new revision**, **Copy into current draft** or **Restore as new revision**. Earlier revisions are never changed: edits go into the current draft or a new revision, so signed history stays intact.
- **Integrations:** DocuSign sandbox drafts, sync and connection tests work as in his version, with OAuth callbacks on this server (`http://localhost:8790/api/paperwork/oauth/callback/docusign`). A PM signed in with Google already has Gmail connected, so his Gmail draft and reply-sync use that sign-in (the platform asks for `gmail.compose` for drafts).
- **Links:** every link into the document center goes through `docLink`/`stepDocsLink` in `app.js`: `#/project/<JOB>/documents?doc=<id>`, `?step=<step key>` or `?product=<product id>`. Document ids are his: `D01`–`D20`, `C_<requirement>` for tracked compliance documents, `P-<product>-po` / `-spec` / `-receipt`, and `X<n>` for documents the PM adds.

## Connect DocuSign (developer sandbox)

1. In a free [DocuSign developer account](https://developers.docusign.com/), open **Apps and Keys** and add an app (integration key). Choose authorization code grant with PKCE (no secret), and add the redirect URI `http://localhost:8790/api/paperwork/oauth/callback/docusign`.
2. Give the server the key: save `{"client_id": "<integration key>"}` as `pm/docusign.json` (git-ignored, read at startup), or `export EQORE_DOCUSIGN_CLIENT_ID=<integration key>`, or paste it into the form in step 3.
3. In any project's **Document center → Integrations**, choose **Connect account** for DocuSign, sign in to the developer account and allow access. Then choose **Test connection**.
4. On a signature document, set real email addresses for its signers (Contacts → Edit project contact). **Sign with DocuSign and send** then opens your signing page, and DocuSign emails the others.

The connection lasts for the server session (tokens stay in memory, as in Yichang's version). Sign-and-send uses DocuSign's sandbox (`demo.docusign.net`), so nothing is legally binding.

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

Permissions requested: sign-in (`openid email profile`), read Gmail (`gmail.readonly`), send as the PM (`gmail.send`), create Gmail drafts for the document center (`gmail.compose`), and read the calendar (`calendar.readonly`). Google tokens are held only in the server's memory for the session and never reach the browser. A Google account that isn't one of the demo PMs sees Jordan's sample portfolio (set `PM_DEFAULT_PORTFOLIO` to change it) with its own real inbox and calendar.

## Tests

```sh
node pm/model.test.js                               # schedule, status, products, edits, document-center plan and feed
python -m unittest discover -s pm/doccenter -v      # the document-center adapter and signing (DocuSign against a fake server)
```

## Files

| File | What it does |
| --- | --- |
| `server.py` | Serves the repo root, sign-in (demo accounts and Google OAuth), Gmail paperwork scan, Google Calendar, sending email, saving each PM's edits, and the document center API (`/api/paperwork/*`) |
| `doccenter/` | Yichang's document engine (unchanged copies), the adapter, signing (DocuSign embedded signing, platform signatures, signed PDFs), stand-ins and tests |
| `doccenter.js`, `doccenter.css` | Yichang's document center screens, mounted in each project's Document center page |
| `data.js` | Synthetic data: PMs, the 16-step template and its paperwork, companies (from the old contractor portal's database), 37 MA/CA projects, the products each project buys, reported delays |
| `model.js` | Forecast (forward pass, including delivery dates) and slack (backward pass), project status, products, to-dos, the document-center seed plan and feed, the PM's edits, calendar items, subcontractor updates, contractor availability |
| `app.js`, `index.html`, `styles.css` | The app |
| `model.test.js` | Node tests for the model |
