# Handbook investigation and coverage checklist

Audit date: 2026-11-20. Documentation-only task.

Starting branch: `feat/local-web-console`. Starting commit:
`121b31f82b094ef68b3f512c83f4e8c33a6b5548`. Starting working tree: clean.
The unchanged Git commit is the production-code reference and rollback checkpoint;
new handbook files can be reviewed independently. No production edits are planned.

## Investigation

- [x] Inspect repository tree, repository instructions and current project status.
- [x] Read repository documentation, configuration and CLI entry points.
- [x] Trace protocol messages, codec and TCP connection lifecycle.
- [x] Trace tracker registry, HTTP API and peer lifecycle.
- [x] Trace manifest validation, chunk storage and final publication.
- [x] Trace scheduler, downloader, retries, concurrency, metrics and upload limiter.
- [x] Inventory every dashboard control and HTTP integration.
- [x] Inspect benchmark runner, analysis, plots and committed measurements.
- [x] Inspect test cases and fixtures; run available validation without installing software.
- [x] Record conflicts between existing documentation and current implementation.

## Deliverables and review

- [x] Main handbook: all 21 requested chapters, self-contained explanations and diagrams.
- [x] Independent quick revision guide.
- [x] Independent three-console demonstration script (8000 / 8090 / 8081 / 8092).
- [x] Source map: 31 production/support Python files, 270 class/function definitions, 25 named JavaScript functions, assets/configuration and call chains.
- [x] 100 answered viva questions, categorized glossary and worked examples.
- [x] Verify paths, symbols, CLI options, protocol bytes and benchmark arithmetic.
- [x] Check Markdown links, diagram structure/manual syntax and documentation-only diff; rendered Mermaid QA unavailable.
- [x] Publish organized Notion pages and read back all 21 chapters/three guides plus both parent pages.
- [x] Update project status with evidence and unresolved gaps.

## Evidence and unresolved gaps

### New checks actually run

| Command/action | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest` | `390 passed, 1 warning in 78.99s (0:01:18)`; exit 0. Existing upstream Starlette/httpx deprecation. |
| `.\.venv\Scripts\ruff.exe check .` | `All checks passed!`; exit 0 |
| `.\.venv\Scripts\mypy.exe src/p2p tests bench docs/build_course_report.py` | `Success: no issues found in 59 source files`; exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench docs/build_course_report.py` | `59 files already formatted`; exit 0 |
| `node --check src/p2p/web/static/app.js` | Exit 0; no output |
| CLI module help for `p2p.cli`, `p2p.web`, `bench.run_experiments`, `bench.plot_results` | Existing commands/options printed; source parsers also inspected |
| `node tests/browser/console.mjs` (two attempts) | Each exited 1 after four PASS groups; same payload DOM assertion at line 270, described below |
| `.\.venv\Scripts\python.exe output/handbook/rehearse.py` | Fixed-port preflight stopped with WinError 10048; no rehearsal services started over occupied ports |
| `Get-NetTCPConnection` filtered to documented ports | Existing listeners found on 8000, 8090, 8081; left untouched |
| `.\.venv\Scripts\python.exe output/handbook/rehearse.py --ephemeral` | `8 documentation rehearsal groups passed; no performance CSV written`; exit 0; four processes on free loopback ports with isolated OS temporary workspaces |
| Read-only benchmark audit using `bench.analysis` | 180 rows, 40 included complete measured trials, eight warmups, eight configuration summaries, no failed/incomplete exclusions; all recorded retry/integrity counters zero; handbook table recomputed |
| `.\.venv\Scripts\python.exe output/handbook/validate_docs.py` | Links/fences/headings/test references/valid manifest and SHA-256 example/exact codec bytes/benchmark rounding checked; 21 chapters and 100 answers confirmed; no issues; final counts in local ignored validation JSON |
| Protected-file SHA-256 comparison | 103 tracked files outside docs byte-identical, including production, frontend, tests, dependencies and raw CSV |

The helper scripts, extracted symbol/test/document inventories and JSON evidence
live under ignored `output/handbook/`; they are local verification aids, not new
production code or committed tests. The source map was generated from inspected
Python AST definitions and reviewed alongside explicit execution/ownership notes.

### Three-console rehearsal assertions

1. Independent tracker and three HTTP console processes became ready.
2. Raw source import generated four chunks; manifest export/import into independent B/C catalogs preserved swarm identity.
3. A's capped TCP transfer completed at B; verified payload and independent exported SHA-256 matched.
4. A was absent before C started; completed B supplied exactly 1 MiB to C, with matching independent output hash.
5. Two concurrent baseline clients uploaded zero, received only origin payload, and passed independent file hashes.
6. A fresh 65,536 B/s source setting permitted a verified single-client 1 MiB transfer.
7. Recorded-results API returned eight summaries/five measured repetitions and a 48-trial audit.
8. All owned consoles exited gracefully; tracker membership stayed empty.

These are correctness assertions, not timing measurements. They do not establish
LAN/WAN or fault-workload performance.

### Unresolved gaps and interpretation

- Both fresh browser runs stopped at `tests/browser/console.mjs:270`. The API had
  observed completion, but the browser DOM still showed the previous poll's
  `1.75 MiB` instead of expected `2.00 MiB`. The intervening harness wait checks
  tracker membership already present before completion, so it does not synchronize
  a new completed payload snapshot. This polling synchronization gap is inferred
  from source and failure diagnostics. Tests/production were not changed; later
  groups were not newly verified. Historical 13-group success remains historical.
- Requested fixed-port commands are checked against entry points, but were not
  newly launched over existing services. The fresh three-console API rehearsal
  used free ports and temporary workspaces. No full new manual four-terminal
  browser demonstration is claimed.
- Mermaid/mermaid-cli are not installed. Twelve diagram blocks across handbook
  and revision were checked for structure and reviewed for conventional syntax;
  no new rendered diagrams or Notion diagram visual QA is claimed. No software
  was installed to change that limitation.
- No new performance sweep, CPU/RAM measurement, packet capture, real-network
  experiment, screen-reader check or cross-platform/browser-engine study ran.
- Handbook Chapter 3 records historical/incomplete examples, current parser
  differences, missing universal write/close deadlines, synchronous chunk I/O
  and stylesheet/spec drift. These are documented observations, not backend fixes.

### Notion publication

Created and read back [P2P File Distribution | Complete Project Handbook](https://app.notion.com/p/41eb29626ff5811785fdd572ff908886).
It contains a handbook child with 21 ordered chapter pages and three independent
guide children. All 24 content pages and both parent pages were fetched after
creation; content endpoints and hierarchy were checked, with no reported
truncation/unknown blocks. Notion normalizes some code language labels and inline
markup; repository-relative links are preserved as textual paths in that copy.
Markdown remains the source of truth. The connector's page-panel handoff was
requested for the parent; no separate browser visual inspection is claimed.

### Changed tracked-content scope

Added the four requested Markdown files and this audit checklist; updated only
`docs/project-status.md` among existing files. No runtime feature was added,
changed, removed, committed or pushed.
