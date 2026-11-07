# Relay — EQORE paperwork, delivery and contractor workspace

Read and follow the team repository's root `AGENTS.md` before editing this module or another teammate's files. Version 0.7 opens the paperwork PM workspace at `/` and `/paperwork.html`; the earlier delivery workspace is at `/delivery.html` and the partner view is at `/contractor.html`. Run this module's `server.py` for all three.

Paperwork has a separate PM-scoped portfolio in the same SQLite database. Its document completion and provider evidence must not mutate physical-work tasks, budgets or operating gates. The delivery and contractor views continue sharing their canonical three-project state. The sibling `contractor/` and `command-center/` apps remain reference implementations; do not import their independent stores.

Profile selection is local preview identity, not production authentication. Provider integration creates drafts and manually reads verified status; it does not send email/signature requests or receive automatic webhooks. Do not claim a live connection without an actual successful account check. Email connection is optional; prepared drafts work without one. Read the integration guide before changing revision semantics, provider trust, concurrency or routing.

@INTEGRATION.md
