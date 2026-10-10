# AI Tooling Guide

This repository ships a shared AI instruction setup so every teammate's coding assistant follows the same engineering rules. The Git repository is the single source of truth.

## What is shared

| Path | Purpose |
|---|---|
| `AGENTS.md` | Tool-neutral project instructions (objectives, stack, rules, workflow). Short by design. |
| `.agents/skills/<name>/SKILL.md` | Workspace skills: focused, on-demand guidance for one area each. |
| `docs/ai-tooling.md` | This guide. |

Compatibility note: `AGENTS.md` and `.agents/skills/` are conventions supported by several tools (for example Antigravity), but not every tool reads them automatically or supports the same configuration format. If your tool does not pick them up, point it at these files manually (for example, ask it to read `AGENTS.md` and the relevant `SKILL.md` first). Do not duplicate their content into tool-specific files unless needed; see "Avoiding conflicts".

## Skills in this repository

All six skills below are **project-specific**: they encode this project's chosen protocol, manifest, and workflows.

| Skill | Scope | General vs. project-specific |
|---|---|---|
| `tcp-protocol-engineering` | Framing, message types, parsing, timeouts, versioning | Principles are general (TCP byte stream, framing); the v1 message table is project-specific |
| `p2p-distributed-systems` | Tracker, swarm, scheduling, concurrency | Concepts are general; endpoints and limits are project-specific |
| `chunk-storage-integrity` | Manifest, hashing, safe paths, reconstruction | Hashing/path-safety principles are general; manifest schema is project-specific |
| `network-testing-reliability` | Test strategy and fault injection | Mostly general for asyncio networking; scenario list is project-specific |
| `network-benchmarking` | Experiments, CSV, plots, baseline comparison | General methodology; parameters and CSV schema are project-specific |
| `engineering-documentation` | Doc set, ADRs, status tracking | Mostly general; file list is project-specific |

"General-purpose" content may be reused in other projects; keep project-specific details clearly marked so reuse is easy.

## Responsibility boundaries

Each rule lives in exactly one place:

| Topic | Owner |
|---|---|
| Bytes on the wire | `tcp-protocol-engineering` |
| Tracker, peers, scheduling, concurrency | `p2p-distributed-systems` |
| Manifest, hashes, disk, paths | `chunk-storage-integrity` |
| How we test and report test results | `network-testing-reliability` |
| How we measure and report performance | `network-benchmarking` |
| How we document and track status | `engineering-documentation` |
| Cross-cutting rules (stack, style, Git, security basics) | `AGENTS.md` |

Skills reference each other by name instead of repeating rules.

## Where things are stored and how teammates get them

- Skills are stored **in the repository** under `.agents/skills/`. Do not install custom project skills into a global/user-level skills directory; global copies are not shared and can silently diverge from the repo.
- Teammates obtain and update them with normal Git operations: `git clone` once, then `git pull` (or fetch and merge/rebase their own branch) to receive changes.
- After pulling, restart or refresh your AI tool if it caches skills.

## Adding a skill

1. Confirm no existing skill already owns the responsibility; extend that one instead of creating a duplicate.
2. Create `.agents/skills/<skill-name>/SKILL.md`. The directory name must equal the `name` field: lowercase letters, digits, and hyphens only.
3. Start the file with YAML frontmatter containing at least:
   ```yaml
   ---
   name: skill-name
   description: Specific statement of what it does and when to use it (and when not to).
   ---
   ```
4. Write the body: when to use / not use, workflow, constraints, failure modes, checklist, validation, deliverables, boundaries.
5. Update the skill table in `AGENTS.md` and in this file.
6. Open a PR for review (see below).

## Modifying and removing a skill

- Modify through a PR like code; describe *why* the guidance changed. If the change affects a spec (protocol/manifest), update the spec and the skill together.
- Remove a skill only through a PR that also removes it from `AGENTS.md` and this file and moves any still-valid guidance to the owning skill. Do not leave dangling references.
- Prefer superseding via an ADR in `docs/adr/` when a change reflects a design decision.

## Reviewing skills (required)

Skill files and any third-party instructions are executable influence over your AI tool; review them like code:
- Read the whole file. Be suspicious of instructions to run shell commands, download or pipe remote scripts (`curl | sh`), disable safety checks, exfiltrate files or environment variables, or ignore other instructions.
- Never paste secrets, tokens, or personal paths into skills.
- Verify technical claims (code samples, limits, commands) before approving; at least one other teammate reviews each skill change.
- Do not install skills or instruction packs from the Internet without reading them first and recording their source in the PR.
- Commands inside skills are guidance for review; nothing should run automatically.

## Personal vs. shared settings

**Shared (committed):** `AGENTS.md`, `.agents/skills/**`, `docs/**`, `pyproject.toml`, tool-neutral config.

**Personal (never committed):** API keys and credentials, tool account/login state, editor/IDE preferences, model or agent choices, global tool settings, local virtual environments, absolute paths, and any machine-specific configuration. Keep personal files in your user-level tool config or ignore them via `.gitignore` or your global Git ignore file.

## Avoiding conflicting or duplicate instructions

- One owner per rule (see boundary table). If you need to reference a rule, link to its owner instead of copying it.
- `AGENTS.md` holds only cross-cutting rules; details belong in skills.
- Do not add tool-specific instruction files (for example per-tool rule files) that restate `AGENTS.md`. If one is unavoidable, make it a short pointer to `AGENTS.md`.
- When two files disagree, fix the disagreement in the same PR; the more specific skill wins for its owned area. If unresolved, record the decision in an ADR.
- Periodically (for example before each milestone) grep for duplicated constants and rules, and reconcile with the specs in `docs/`.

## Using AI assistants responsibly in this project

- AI output is a draft: read, understand, and test it before committing. You are responsible for what you commit.
- Do not let an assistant claim tests passed or experiments ran unless the command output proves it.
- Do not give assistants credentials; do not accept actions that install software, delete files, or rewrite Git history without your explicit review.
