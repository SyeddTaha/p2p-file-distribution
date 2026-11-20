# Frontend redesign implementation plan

Date: 2026-11-20. Status: **Approved and implemented**.
The user approved this plan after reviewing the audit and specification.
The phases below retain the agreed scope and acceptance criteria; see the
[verification record](frontend-redesign-verification.md) for actual results.

The planning deliverable contained the [audit](frontend-redesign-audit.md),
[design system](../DESIGN_SYSTEM.md), and this plan. Baseline tests passed and
source/worktree rollback checkpoints protect both the pre-audit and
pre-implementation states. Implementation followed the user's explicit approval.

## Intended result

Replace the current flat top-navigation styling with the reference's charcoal
sidebar, gray canvas, rounded white cards, lime actions, lavender emphasis and
one dark local-payload panel. Use Plus Jakarta Sans headings and Inter body
typography if licensed local assets can be bundled. Maintain all four existing
pages, all controls, all data, and the existing request/polling behavior.

This is an operational P2P console, so the reference's dense health bubbles,
date filters, account/search/notification controls and upgrade illustration are
not carried over. Dense peer/transfer tables remain full width. Actual existing
experiment SVGs receive the palette without changing recorded values or axes.

## File scope after approval

| File | Proposed work |
|---|---|
| `src/p2p/web/static/index.html` | Semantic sidebar/header shell; page/card layout; existing forms/IDs/anchors; native advanced-settings disclosure; maintain direct `main > section` structure |
| `src/p2p/web/static/style.css` | Exact design tokens, local font faces if supplied, responsive grid, controls/status/progress/table/chart styling, focus and reduced motion |
| `src/p2p/web/static/app.js` | Presentation-only renderer markup/classes/icons and chart colors; preserve API helper, payloads, action guards, state calculations, hash navigation and polling semantics; preserve keyed focus and any new disclosure state |
| `src/p2p/web/static/fonts/*` | Conditional licensed local WOFF2 assets and notices; no system-wide font installation |
| `pyproject.toml` | Conditional **asset packaging only**: include chosen fonts/licenses in package data; no dependency, entrypoint, tooling or backend behavior changes |
| `DESIGN.md`, `DESIGN_SYSTEM.md`, `docs/web-ui.md`, `docs/testing.md`, `docs/project-status.md` | Make current/proposed design authority explicit, document advanced settings and actual verification; record limitations honestly |

No `.py` files, existing test assertions, API definitions, networking, scheduler,
manifest/storage/hashing code, experiment harness or raw results are in scope.
Existing tests run unchanged. If new UI regression coverage is needed, add it
without changing existing expectations or adding tooling without authorization.

The font/package-data step is explicit because the repository currently packages
only HTML/CSS/JS. Approval of the full plan includes this narrow frontend-asset
packaging step. If that step is excluded, use the specified fallback stack and
report that exact font fidelity remains unresolved. Font acquisition and license
checks happen only after approval; no package or skill installation is proposed.

## Phases and completion gates

| Phase | Work | Gate before moving on |
|---|---|---|
| 0. Approval and recheck | Obtain approval of this concrete plan; recheck branch/tree for concurrent work and preserve a fresh checkpoint if needed | Approval recorded; no unrelated work overwritten |
| 1. Static shell and tokens | Implement sidebar/main hierarchy and responsive rules; set typography, palette, radii and spacing; keep all current IDs and controls | Four hash routes, direct section selectors, labels and all form controls intact; first before/after screenshots |
| 2. Dashboard | Group five existing metrics into membership, local downloading and dark payload panels; retain tracker details and full transfer table | Counts/scope/unknown values match the original calculations; no synthetic chart or rate added |
| 3. Transfer and Network | Restyle imports and peer form; place advanced settings in initially open native details; restyle catalog, transfer entries, swarm/connection/source tables | Existing imports/exports, all settings/dependencies, Stop and output links work; no details/focus reset during polling |
| 4. Experiments | Restyle table and two SVG plots; baseline dashed lavender and P2P solid lime on dark; retain SD/axes/legend and all audit content | Results match API output; reload and unavailable/empty states work; no new benchmark run |
| 5. Verification and critique | Run unchanged tests/checks, exercise all workflows below, inspect console/network, compare screenshots, verify accessibility and revise visual defects | Every required check has evidence or an explicitly unresolved limitation; preservation is not claimed for untested workflows |
| 6. Documentation and handoff | Update current design links and user guidance; report changed files, commands/output and before/after evidence | Reviewable diff contains only approved frontend/assets/docs/packaging changes |

Prefer HTML/CSS changes first. Modify JS only where the rendered DOM or visual
styling requires it. Keep renderers producing text nodes for untrusted data and
real anchors for downloads. Do not rewrite or optimize request/lifecycle logic
as part of this redesign.

## Workflow acceptance matrix

This matrix defines acceptance criteria, not evidence by itself. Actual
completed checks and limitations are recorded in the linked verification record.
Use temporary workspaces, loopback and ephemeral ports for automated fixtures;
keep demonstration artifacts out of tracked source. Use two independent console
instances for cross-console import/transfer tests. Record actual observations.

| Workflow | Required browser check / expected result |
|---|---|
| Boot/navigation | All four text links, brand, direct hashes, invalid-hash fallback and Back/Forward work; only the intended section is visible; active pill/aria-current correct |
| Fresh empty session | Guidance explains import/start; no fake transfers, peers or results; zero membership differs from unavailable |
| Import source | Native picker and required validation; valid nonempty source imports/hashes; feedback and disabled state visible; returned asset selected; size and server errors readable |
| Manifest exchange | Save manifest from origin; import into second console; correct catalog/source distinction; JSON accept hint and 4 MiB guard retained; malformed/unsafe manifest errors remain visible |
| Start eligibility | Tracker offline/no asset disables Start; manifest-only cannot seed; source can seed; operation and baseline/cap interactions match original behavior |
| Upload caps / advanced | Blank means unlimited; min/max/step validation; selected numeric value sent unchanged; cap shown per peer; apply only on new peers; disclosure open state and current form values survive refresh |
| P2P transfer | Start source and downloader; observe verified byte/chunk progress, lifecycle and final integrity separately; compare downloaded output bytes and SHA-256; no false success at chunk completion |
| Peer lifecycle | Stop incomplete download; early Stop; Stop seed; Stop completed peer; stopped/failed button gates; repeated actions guarded; no lost focused Stop control on live snapshots |
| Completed relay | Complete P2P download, stop origin, start later downloader; actual completed peer serves payload; positive source contribution reported; output verified |
| Baseline mode | Enable download-only on every new client with one origin; cap disabled/sent null; local upload capability labeled disabled; clients upload zero even when complete |
| Exports/history | Every Save manifest link downloads correct artifact; Save verified file appears only with actual output; retained history and full identifiers accessible after stop |
| Network inspection | Inspect all local peers; selection retained while status updates; role, address, local/remote capability, connection direction/state/chunks/pending requests and positive source bytes visible |
| Refresh behavior | Initial state read, 1000ms timer, no overlapping snapshot requests, manual Refresh and post-action refresh remain; no duplicate click handlers; update while other pages are hidden |
| Tracker failure | Stop tracker while console stays alive; offline/error/unavailable distinguished; Start disabled; no conversion of unavailable counts to zero |
| Console failure | Interrupt console reachability; existing values labeled stale, error shown; browser recovery restores live data; no label implying continuing live telemetry |
| Transfer failure | No-peer and controlled final-integrity failure paths retain explicit errors; failed hash never gains verified label or output link; rely on existing isolated fault tests for safe corruption setup |
| Recorded results | First-visit load and Reload; source, caption, eight current configurations, trial counts, mean/SD, share, two charts, legend/audit and limitations match API; missing/invalid CSV shows unavailable without fabricated fallback |
| Keyboard/accessibility | All forms/links/buttons operable; labels and native validation retained; visible focus, logical reading order, live feedback; no forced focus jump; full values reachable without hover |
| Responsive/zoom | Screenshots at 1440x1000, 1024x768, 768x1024 and 390x844; 320px overflow check and 200% zoom; one-column forms where needed, contained table scrolling, no lost controls |
| Browser diagnostics | Inspect console for JS/CSP errors and Network for failed requests, blocked fonts, unhandled rejections, unexpected external calls or duplicate polling; separate deliberately injected failures from regressions |

Do not manually damage existing user files to test hash errors. Existing
test-local fault injection covers corruption without touching real artifacts.

## Automated checks after implementation

Run the existing full suite once after final changes; use focused tests while
iterating. Add repetitions only if new failures/races justify them. Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench
.\.venv\Scripts\python.exe -m mypy src/p2p tests bench
node --check src/p2p/web/static/app.js
git diff --check
```

If fonts are bundled, verify same-origin font delivery, computed font family,
CSP compliance and inclusion in a locally built distribution using already
available tooling. No dependency fetch/install is implied. Do not silently
ship checkout-only typography that disappears from the installed package.

Existing API and separate-process E2E coverage must stay unchanged and passing.
It does not replace browser JavaScript workflow testing. Use already available
browser tools or a documented manual run; no new browser dependency is installed
without authorization. If browser automation is unavailable, record the exact
missing coverage and obtain manual evidence before claiming it is complete.

## Visual review criteria

Compare the supplied 1024x768 reference with the console at that viewport and
the proposed larger laptop viewport. Inspect:

- Dark rail, white active pill, gray canvas, rounded leading main corners,
  lime/lavender/charcoal color relationships and consistent outline icons.
- Heading/body hierarchy, real font rendering, card radius, spacing rhythm and
  asymmetric membership/activity/payload grouping.
- Clean table density, full access to technical data, visible validation/errors
  and retained actions at narrow widths.
- Dark plot axes/legend/SD contrast and consistent semantic states; values stay
  grounded in API responses or the identified recorded dataset.

Pixel identity is not a reasonable target for unrelated health content. The
approved visual language is the target; P2P functionality takes precedence if
reference geometry would hide controls or data. Report any such divergence.

## Rollback and delivery

Keep the original checkpoint from the audit and any new pre-implementation
checkpoint. Restore only selected approved frontend files after checking for
intervening work; the audit explains the committed ref and full worktree archive.
No destructive recovery command or history rewrite is part of this plan.

The final implementation report must list all changed files, exact check
commands and results, workflow/browser coverage, screenshots and unresolved
limitations. Update project status to **Implemented** or **Tested** only when
the corresponding evidence exists. The verification record distinguishes browser,
API, visual inspection and checks that were not performed.
