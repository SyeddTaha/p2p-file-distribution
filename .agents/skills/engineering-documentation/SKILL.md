---
name: engineering-documentation
description: Create and maintain the project's documentation set (README, architecture overview, protocol specification, manifest specification, testing guide, experiment methodology, architecture decision records, and project status), keeping it concise, accurate, updated alongside code, and honest about what is implemented, tested, partially implemented, or planned. Use whenever a code change affects behavior, a design decision is made, or status needs updating. Not for deciding the technical content of the protocol, storage, scheduler, tests, or experiments themselves; those belong to their owning skills.
---

# Engineering Documentation

## When to use / when not to use

Use when:
- a code change alters behavior, interfaces, limits, or file formats;
- a design decision is made or a plausible alternative is rejected;
- a feature changes state (planned -> implemented -> tested);
- starting or finishing any task (read and update status);
- writing README/usage instructions.

Do **not** use to decide technical specifics. Take them from the owning skill: wire format -> `tcp-protocol-engineering`; tracker/swarm/scheduling -> `p2p-distributed-systems`; manifest/hashing/storage -> `chunk-storage-integrity`; test strategy -> `network-testing-reliability`; experiment design -> `network-benchmarking`. This skill owns **structure, accuracy, and upkeep** of docs, not the engineering decisions inside them.

## Documentation set and ownership of content

| File | Purpose | Technical content from |
|---|---|---|
| `README.md` | What the project is, status summary, quick start, repo map | all |
| `docs/architecture.md` | Components, responsibilities, state ownership, sequence of a download, failure behavior, tracker endpoints | `p2p-distributed-systems` |
| `docs/protocol.md` | Wire format spec: frames, message table, state machine, limits, timeouts, versioning, errors | `tcp-protocol-engineering` |
| `docs/manifest.md` | Manifest schema, validation rules, swarm ID, limits, hashing | `chunk-storage-integrity` |
| `docs/testing.md` | How to run tests, conventions, scenario matrix, known flaky tests | `network-testing-reliability` |
| `docs/experiments.md` | Methodology, parameters, environment, results, limitations | `network-benchmarking` |
| `docs/adr/NNNN-title.md` | One decision each, with alternatives | any |
| `docs/project-status.md` | Current truth on feature state, open issues | all |
| `docs/ai-tooling.md` | How the AI skills/instructions are managed | this repo's AI setup |

Create a doc when the code it describes first exists (or when a design is agreed); do not create empty placeholder docs with filler text.

## Status tracking (the single source of truth)

`docs/project-status.md` lists each feature with exactly one state:
- **Planned**: agreed, no code.
- **Partially implemented**: some code exists; list what is missing.
- **Implemented**: code complete, **no** adequate tests yet.
- **Tested**: code complete with automated tests that were run and passed (record date/commit and command).

Rules:
- Never mark something Implemented/Tested because you *intend* to finish it.
- "Tested" requires that tests were actually executed; record the command and result.
- Benchmarks have their own state: Not run / Smoke-tested only / Run (with dataset link and commit).
- Move entries between states in the same PR as the code change.
- Keep an "Open issues / known limitations" list and a "Decisions needed" list.

## Architecture Decision Records

Create an ADR for: choosing among viable designs, adding a dependency, changing the protocol or manifest, adding a non-goal item, scheduling policy, expiry policy, resume support.

Template (`docs/adr/NNNN-short-title.md`, sequential numbers, never renumber):

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD

## Context
What problem, what constraints.

## Decision
What we chose, in one or two paragraphs.

## Alternatives considered
- Option A: why rejected.
- Option B: why rejected.

## Consequences
Trade-offs, follow-up work, what becomes harder.
```

Accepted ADRs are not rewritten; supersede them with a new ADR.

## Workflow (every task)

1. Read `docs/project-status.md` and the spec(s) for the area you will touch.
2. Make the code change.
3. In the same change, update affected docs: spec tables, limits, examples, diagrams, status entries, ADR if a decision was made.
4. Verify doc claims against code: field names, type codes, constants, command lines, file paths. If a doc says something the code does not do, fix the doc or the code.
5. Re-read your edit for filler, vague claims, and stale statements; delete them.

## Writing standards

- Concise and specific; prefer tables for message formats, limits, and state lists; prefer short examples that actually run/parse.
- Describe *current* behavior in specs; put future ideas under "Planned" or in ADRs, clearly labeled.
- No marketing language or unsupported claims ("blazing fast", "robust", "scalable") unless backed by cited data.
- Every command shown has been checked for correctness; mark untested commands as untested.
- Use relative paths and placeholders; no personal paths, usernames, hostnames, or secrets.
- Diagrams: Mermaid or ASCII text in the repo (diffable); avoid binary-only diagrams without a source.
- Link between docs instead of duplicating content; single source of truth per fact.
- Docs must be understandable without chat history: define terms (chunk, swarm, tracker, seeder, leecher) once in `docs/architecture.md`.

## Common failure modes

- Docs written once and never updated; spec and code drift.
- Planned features described in present tense.
- Duplicated facts in several files that diverge (e.g. limits in README and protocol.md).
- Claiming tests/benchmarks passed or ran without recording command and result.
- Generic filler paragraphs that say nothing about this project.
- ADRs missing rejected alternatives.
- Machine-specific paths in examples.

## Checklist

- [ ] Status doc updated with correct states and dates.
- [ ] Spec tables match constants/types in code.
- [ ] ADR added or updated for any decision.
- [ ] No unsupported claims; measured vs. planned clearly separated.
- [ ] README quick start steps verified or explicitly marked unverified.
- [ ] No duplicate sources of truth.

## Expected deliverables

Updated docs from the table above in every PR that changes behavior, plus accurate `docs/project-status.md`. For substantial changes, mention in the PR description which docs were updated.
