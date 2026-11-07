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

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| Dashboard: portfolio view ranked by slip risk, per-project next action, owner and blocker, "inject a delay" demo control. Currently also holds the Python engine, seed data and server. | `winnie104703` (Yichang) | `eqore-demo/` |
| Startup page: map of all project sites (MA/CA) and the tasks overview | `vaggarmandaar-cell` (Mandaar) | `command-center/` (in PR #3, not merged yet) |
| Contractor side: what each contractor/agency sees (everything they owe across projects) and what they can do (update status, report delays, confirm dates) | `ritvick-bit` (Ritvick) | TBD: depends on which app it plugs into |
| Docs | `ritvick-bit` (Ritvick) | `docs/` |

**Open decision (lead):** `eqore-demo/` (Python, with its own engine) and `command-center/` (static JS, with its own `engine.js`) are two separate apps. The lead decides whether they merge into one app and whose engine and data model is the shared one. Until then, don't edit the other app's engine or data. Ask on the board.

**Shared contract:** the data model (the Project/Task/Party/Resource schema) is what every other area builds on. Its owner posts the first version on the board early. Any later change to it gets an `@all` post before it merges.
