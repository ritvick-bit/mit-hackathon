# Team rules for every agent

## 0. What we're building

**eqore challenge, MIT Energy & Climate Hack 2026: installation coordination for commercial battery deployments.** A portfolio tool that tells a project lead managing 50–200 sites the next action on each project, who owns it, and what it's waiting on, so a late delivery or inspection is visible before it holds everything else up.

Read `docs/CHALLENGE.md` before starting work. It has the 18-step deployment process, the MVP scope, and the demo plan. All project data is synthetic.

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. Team: `@ritvick-bit` (Ritvick, team lead), `@winnie104703` (Yichang), `@vaggarmandaar-cell` (Mandaar), `@all` (everyone).
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Humans over agents. Only the team lead reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board.

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`. The author merges their own PR once it works locally.
5. Always `git fetch` and rebase before pushing. Never force-push shared branches.
6. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what

Every agent checks this table before editing a file.

**Lead decision (Ritvick, Nov 7):** `pm/` (the EQORE PM platform) is the team's one app. Everyone builds on it from `main`. Run it with `python pm/server.py` and open http://localhost:8765 (demo login `jordan.lee@eqore.demo.example` / `demo`). `pm/README.md` explains every page, the data, Google and DocuSign setup, and the tests. `eqore-demo/` and `command-center/` stay as reference prototypes. New features go into `pm/`.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| PM platform: login, portfolio map, project dashboards, timeline and Gantt, calendar, inbox, to-dos, procurement, subcontractors, server, data model | `ritvick-bit` (Ritvick, lead) | `pm/` (everything not listed below) |
| Document center: Yichang's paperwork engine (documents, revisions, signing events, compliance review, DocuSign and Gmail connectors) and its screens | `winnie104703` (Yichang) | `pm/doccenter/paperwork*.py`, `compliance.py`, `client_reference.py`, `pm/doccenter.js` (the adapter, signing and stand-ins in `pm/doccenter/` are Ritvick's) |
| Original dashboard prototype (reference) | `winnie104703` (Yichang) | `eqore-demo/` |
| Startup map prototype (reference). The lead will confirm where Mandaar's next work goes in `pm/`; ask on the board. | `vaggarmandaar-cell` (Mandaar) | `command-center/` (PR #3, not merged) |
| Docs | `ritvick-bit` (Ritvick) | `docs/` |

Before editing a file someone else owns, ask its owner on the board, as in section 1.

**Shared contract:** the data model is what every other area builds on: `pm/data.js` (projects, steps, companies, products), `pm/model.js` (schedule and derived views) and the document center's records (`pm/doccenter/`). Its owner posts the first version on the board early. Any later change to it gets an `@all` post before it merges.
