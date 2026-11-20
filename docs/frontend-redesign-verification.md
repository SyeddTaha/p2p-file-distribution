# Frontend redesign verification

Date: 2026-11-20. Implementation follows the user's approval of the
[plan](frontend-redesign-plan.md) and [design system](../DESIGN_SYSTEM.md).

## Scope and rollback

Work stayed on `feat/local-web-console`, based on
`287e033465cff94d547e5f15c76831e613691e28`. Implementation and verification
completed before the user's later request to commit and push. No reset or stash
was performed. The existing AGENTS.md edit is unchanged and excluded from the
redesign commit.

Before implementation, `checkpoint/ui-implementation-20261120T102301Z` and
`.git/ui-audit-checkpoints/ui-implementation-20261120T102301Z/` captured and
verified 121 source files, including the approved planning documents. The
directory contains `worktree.zip`, `metadata.json`, `status.txt` and a binary
patch. The earlier pre-audit checkpoint is recorded in the audit. Recovery is
selective; neither checkpoint requires overwriting unrelated work.

## Changed files

| File | Change |
|---|---|
| `src/p2p/web/static/index.html` | Responsive sidebar/header, asymmetric live summary, local SVG icons, skip link, initially open advanced settings, all existing forms/IDs/actions retained |
| `src/p2p/web/static/style.css` | Reference palette, local typography, spacing/radius/type tokens, cards, tables, progress/status states, responsive and focus styling |
| `src/p2p/web/static/app.js` | Summary DOM grouping, chart colors, keyboard-accessible table regions, keyed network focus/scroll restoration, route-preserving skip link; request and polling logic unchanged |
| `src/p2p/web/static/favicon.svg` | Local icon matching the console mark |
| `src/p2p/web/static/fonts/inter-latin.woff2` | Local Inter variable font |
| `src/p2p/web/static/fonts/plus-jakarta-sans-latin.woff2` | Local Plus Jakarta Sans variable font |
| `src/p2p/web/static/fonts/inter-OFL.txt` | Inter license notice |
| `src/p2p/web/static/fonts/plusjakartasans-OFL.txt` | Plus Jakarta Sans license notice |
| `src/p2p/web/static/fonts/sources.json` | Font source URLs, sizes and SHA-256 provenance |
| `pyproject.toml` | Asset-only package-data patterns for SVG/fonts/licenses/provenance; no dependencies or backend configuration changed |
| `tests/browser/console.mjs` | New dependency-free browser workflow and screenshot harness; existing tests unchanged |
| `DESIGN_SYSTEM.md`, `DESIGN.md` | Current implementation tokens, asset delivery and design authority |
| `docs/frontend-redesign-audit.md`, `docs/frontend-redesign-plan.md` | Mark historical audit and approved plan; retain captured baseline and agreed scope |
| `docs/frontend-redesign-verification.md` | This implementation/evidence record |
| `docs/web-ui.md`, `docs/testing.md`, `docs/project-status.md` | Current usage, browser checks, actual validation and status |

A checkpoint SHA-256 comparison confirmed **62 protected Python, existing test,
AGENTS.md and raw-data files are unchanged**. All **42 original HTML IDs** remain
present and unique. No Python source file or existing test expectation changed.
Networking, hashing, manifests, transfer lifecycle, endpoint contracts and
benchmark logic/data are untouched.

## Commands and observed results

All Python test/lint/type commands used the existing virtualenv. Browser checks
used installed Node v23.6.0 and Chrome 157.0.8103.80. No software was installed.
The browser test performs correctness transfers, not new benchmark measurements.

| Command | Actual output / result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -ra` (first implementation run) | `390 passed, 1 warning in 61.19s (0:01:01)`; exit 0 |
| `.\.venv\Scripts\python.exe -m pytest -ra` (after skip-link correction) | `390 passed, 1 warning in 71.35s (0:01:11)`; exit 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | `All checks passed!`; exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench` | `58 files already formatted`; exit 0 |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests bench` | `Success: no issues found in 58 source files`; exit 0 |
| `node --check src/p2p/web/static/app.js` | No output; exit 0 |
| `node --check tests/browser/console.mjs` | No output; exit 0 |
| `node tests/browser/console.mjs --baseline` | `1 browser workflow groups passed`; four pre-edit screenshots; exit 0 |
| `node tests/browser/console.mjs` (completed expanded run) | `13 browser workflow groups passed`; real transfers, responsive screenshots and failure/recovery; exit 0 |
| `node tests/browser/console.mjs` (final repeat after visual polish) | `13 browser workflow groups passed`; additionally requires empty tracker membership after graceful console shutdown; exit 0 |
| `git diff --check` | Exit 0; no whitespace errors; Git emitted LF/CRLF conversion notices |

The pytest warning is the existing upstream Starlette/httpx deprecation. The
virtualenv lacked setuptools for wheel construction, so an initial direct build
attempt reported `ModuleNotFoundError: No module named 'setuptools'`. A repeat
using the already installed system Python/setuptools succeeded; no installation
was performed. A PowerShell Python here-string invoked
`setuptools.build_meta.build_wheel('output/ui-redesign/package')` and inspected
the ZIP: both WOFF2 files, both licenses, provenance JSON, favicon and existing
HTML/CSS/JS were present. A final build compared all nine packaged static assets
byte-for-byte against current source and passed. That build emitted the existing project license-table
deprecation warning. Generated wheel/build files are ignored.

Initial browser runs exposed two test-sequencing problems: clicking Import
while a previous action's button was disabled, and inspecting connection markup
before the next one-second snapshot. The harness now waits for action readiness
and the required visible observation. A genuine new skip-link bug was reproduced
with `--navigation-only`: its hash target triggered the existing invalid-route
fallback. The corrected click handler focuses main content without changing the
route; the full browser run tests both keyboard focus and route preservation.
Existing backend behavior was not changed to satisfy automation.

## Browser workflow coverage

The completed expanded run verifies:

1. All four routes, active selection, Back/Forward, invalid-hash fallback,
   empty-state eligibility and native required validation.
2. Source import, asset selection, a real manifest-anchor download and second
   console import, with manifest-only seeding disabled.
3. Malformed manifest feedback and numeric cap bounds.
4. Source/manifest size rejection at 128 MiB/4 MiB before an HTTP POST.
5. Capped real TCP transfer with partial verified bytes and pending final hash,
   network inspection, exact tracker/local scope counts, retained keyboard focus
   and network horizontal scroll, persistent settings disclosure, verified file
   export and independent SHA-256 equality.
6. Stop origin, serve a later download from a completed peer, preserve inspected
   peer selection, then stop completed peers.
7. Two download-only clients, disabled upload cap/null submitted value, disabled
   uploads and exactly zero uploaded bytes.
8. Cancellation of an incomplete transfer, no output link, no-peer failure and
   disabled Stop for failed entries.
9. Recorded CSV first visit/reload, eight configurations, two plot series,
   sample-SD/audit content and no experiment execution.
10. All four routes at 1440x1000, 1024x768, 768x1024, 390x844 and 320x800 without
    page-level horizontal overflow; 720x500 reflow, reduced-motion setting,
    loaded local fonts and keyboard skip-link focus/route preservation.
11. Repeated live polling and no unexpected JS exceptions, CSP violations,
    external page requests or network loading failures during normal workflows.
12. A separate console with a real unavailable tracker: offline/error state,
    unavailable counts rather than zero, and disabled Start despite an import.
13. Injected browser transport failures: stale retained console snapshot and
    unavailable experiment status, followed by successful recovery.

Intentional malformed-manifest HTTP errors and injected transport failures are
negative test cases, not silently ignored normal-workflow errors. No fabricated
state replaces real data. Servers use existing isolated E2E fixtures, ephemeral
loopback ports and temporary files, and must exit gracefully.

Existing pytest coverage additionally verifies final-file corruption and output
rejection, missing/invalid CSV, unsafe filenames/manifests, Host/Origin/action
guards, capacity limits, repeat-stop/cancellation races, tracker expiry and
shutdown/deregistration. These are API/engine checks rather than newly executed
browser corruption scenarios.

## Visual evidence and design comparison

Ignored artifacts are under `output/ui-redesign/`:

- `before/dashboard.png`, `before/transfer.png`, `before/network.png`,
  `before/experiments.png`: original 1024x768 console.
- `after/dashboard-live.png`, `after/transfer-live.png`,
  `after/network-live.png`: real two-console transfer session.
- `after/experiment-plots.png`: both dark plots, SD, legend and methodology.
- `after/<route>-<width>.png`: each route at the five listed viewport widths.
- `after/report.json`: latest completed browser run and workflow names.

Desktop/mobile Dashboard, File Transfer, network and plot screenshots were
visually inspected against the supplied reference. The charcoal rail, white
active pill, gray canvas, leading rounded shell, white/lavender/dark composition,
lime/lavender accents and typography follow it. Mobile uses four visible
wrapping links rather than a hidden drawer. A final polish aligns membership
numbers when labels wrap and removes nested rounded table framing in swarm cards.

Deliberate adaptations: the working console fills the viewport instead of using
the reference artwork's outer lime matte; P2P tables span the content width;
health bubbles, account controls, search, date filters, notifications and upgrade
content are omitted because the engine supplies no corresponding workflow.
The two existing measured charts retain their values and SD meaning.

Not claimed: pixel identity to unrelated health content, screen-reader testing,
native browser-menu 200% zoom, other browser engines or other operating systems.
The reduced viewport tests exercise reflow but are not a native zoom-menu test.
Fault injection of final-file corruption remains covered by existing API tests.
