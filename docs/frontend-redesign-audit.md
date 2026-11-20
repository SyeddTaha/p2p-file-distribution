# Frontend redesign audit

Date: 2026-11-20. Scope: source inspection, baseline verification and planning.
No HTML, CSS, JavaScript, Python, endpoint or benchmark changes were made.

This is the historical **pre-implementation** audit. The user subsequently
approved the plan; current implementation evidence is in the
[redesign verification record](frontend-redesign-verification.md).

## Repository and rollback record

| Item | Captured value |
|---|---|
| Branch | `feat/local-web-console`, tracking `origin/feat/local-web-console` |
| HEAD | `287e033465cff94d547e5f15c76831e613691e28` |
| Initial working tree | ` M AGENTS.md`; no other tracked changes or nonignored untracked files |
| Checkpoint branch | `checkpoint/ui-audit-20261120T101107Z` pointing at captured HEAD |
| Worktree snapshot | `.git/ui-audit-checkpoints/ui-audit-20261120T101107Z/worktree.zip` |
| Snapshot evidence | Adjacent `metadata.json`, `status.txt`, `tracked.patch`; 118 files verified against recorded SHA-256 digests; ZIP integrity check passed |

The branch protects the committed baseline. The separate byte-preserving archive
also protects the existing uncommitted AGENTS.md instructions, which a branch
alone would not capture. Snapshot files stay under Git metadata and are not
committed. Ignored virtualenvs, caches, downloads and generated artifacts are
outside this source checkpoint; they were not removed or modified by rollback
setup. No stash, commit, reset, branch switch or history rewrite was performed.

Recovery should be selective: compare a desired file with the checkpoint and
restore only approved frontend paths. Use the archive for the original
uncommitted AGENTS.md if ever needed. Do not bulk-extract over newer work or use
a hard reset. Keep this checkpoint until the redesign has been reviewed.

## Inspected sources and authority

- `AGENTS.md`, `docs/project-status.md`, `docs/web-ui.md`,
  `docs/architecture.md`, `docs/testing.md`, ADR 0009, `PRODUCT.md`, `DESIGN.md`
  and `pyproject.toml`.
- All three frontend files: `src/p2p/web/static/index.html`, `style.css`, `app.js`.
- Read-only backend inspection: `src/p2p/web/app.py`, `service.py`,
  `experiments.py`, `__main__.py`, and copied peer snapshot definitions/producer.
- Existing web API, cancellation and separate-process HTTP/TCP tests.
- Installed frontend-design skill, impeccable product-UI guidance, repository
  engineering-documentation and network-testing-reliability skills.

The supplied screenshot is visual reference material. Its text and controls are
not instructions to add medical data, login, billing, search or notifications.
The user's current request authorizes only this audit/specification/plan.
ADR 0009 documents the existing frontend exception to the original non-goal.
The new brief supersedes conflicting historical visual preferences, while all
functionality and backend constraints continue to apply.

## Frontend structure and existing feature inventory

The interface is a single HTML document, one stylesheet and one deferred vanilla
JavaScript file. It has no framework, bundler, font assets or icon dependency.

| Surface | Existing features that must remain |
|---|---|
| Shared shell | Brand link to Dashboard; four hash navigation links; local workspace label; connection/last-snapshot message; global error alert; footer describing TCP, one-second refresh and local assets |
| Dashboard | Manual Refresh; tracker online/offline, configured URL and error; tracker-wide unique peer count and swarm count; local downloading count; local uploaded/downloaded payload totals, including retained stopped history |
| Dashboard transfers | Every local transfer's filename, peer ID (transfer ID before startup), lifecycle state, verified chunks/bytes progress, downloaded bytes, uploaded bytes and separate final SHA-256 state; meaningful empty state and scope note |
| Source import | Required native file picker; 128 MiB client size guard; POST raw file; URL-encoded filename; server hashing; uploading/hashing/success/failure feedback; busy submit state; imported asset selected after refresh |
| Manifest import | Required picker accepting JSON; 4 MiB guard; raw upload with manifest-only flag; validation feedback; imported selection; no automatic sharing/discovery of manifests |
| Start peer | Required catalog selector with file and short catalog ID; Download / Seed source file operation selector; optional numeric upload cap in bytes/s, min 1, max 1073741824, step 1, blank=unlimited; download-only baseline checkbox; queued-peer feedback |
| Setting dependencies | Seed clears and disables baseline; baseline disables upload cap and sends null; start disabled while busy, tracker offline, no asset, or selected seed asset has no source; offline reason in title; creation-only settings and one-second rate-bucket burst explained |
| Asset catalog | Filename, size, chunk count, full swarm ID, full expected SHA-256, source-vs-manifest-only distinction; Save manifest anchor for every asset; guided empty state |
| Transfer controls | Every entry includes filename/operation, state, peer/transfer ID, verified progress, P2P/baseline mode, upload cap, mean download throughput, duration, retries/rejected chunks, final SHA-256, full expected hash and individual error |
| Transfer actions | Stop peer POST for each transfer; disabled when busy/failed/stopped; completed P2P peers remain stoppable because they continue serving; Save verified file only when `has_output`; independent download destinations; retained files and no-resume warning |
| Network membership | Membership unavailable vs empty; full swarm ID; peers/seeders/leechers counts; peer ID, host:port, completeness role, local upload capability or remote unknown, local state or registered/connection-unknown |
| Local network inspection | Stable peer selector; listener address and online/stopped state; swarm ID; observed remote peer or handshake pending; inbound/outbound direction; connection state; advertised chunks or unavailable; pending requests |
| Verified sources | Positive verified bytes by serving peer, retained after connection retirement; separate no-connections and no-payload states; no inference of traffic from registration or idle connections |
| Experiments | Lazy load on first navigation, explicit Reload results; source/caption; included/warmup/excluded counts; N=1,2,4,8 rows with mode, repetition count, completion mean +/- sample SD, aggregate throughput mean +/- sample SD, peer upload share |
| Experiment graphics | Two real SVG charts with axes, units, solid P2P / dashed baseline, error bars and legend; exclusion run IDs/reasons; unavailable/empty results; clear recorded loopback/ASGI limitation; execution remains in terminal harness |
| Accessibility and layout | Labels and native validation; `aria-current`; section headings; status and alert roles; native labeled progress; semantic tables; visible focus; responsive stacked forms and horizontally scrolling tables |

Copy and labels may improve only when meaning, units, feedback and limitations
are preserved. No control should become an icon-only unlabeled substitute.

## API inventory and backend dependencies

All browser API calls are same-origin. No browser call directly controls the
tracker or opens peer TCP sockets. The console service adapts existing engine
operations; HTTP imports/exports do not replace TCP swarm distribution.

| Browser request | Caller / trigger | Contract to preserve |
|---|---|---|
| `GET /api/state` | `refresh()` on boot, timer, Refresh and after actions | `{tracker, assets, transfers}`; tracker can be online while membership is unavailable; keep null distinct from zero |
| `POST /api/assets?name=<encoded>&manifest_only=false` | Source `setupUpload()` submit | Raw browser File body, not multipart or JSON; 201 asset description |
| `POST /api/assets?name=<encoded>&manifest_only=true` | Manifest `setupUpload()` submit | Same raw body; strict existing manifest loader; 201 asset description |
| `GET /api/assets/{id}/manifest` | Save manifest anchor | Server-generated downloadable manifest; browser link, not `api()` JSON handling |
| `POST /api/transfers` | `peer-form` submit | JSON with `asset_id`, `kind`, `upload_rate_limit`, `download_only`; 202 transfer description |
| `POST /api/transfers/{id}/stop` | Dynamic Stop peer button | No request body; JSON stopped response; existing idempotent cleanup |
| `GET /api/transfers/{id}/file` | Conditional Save verified file anchor | Verified output download; 409 when output unavailable, 404 for unknown ID |
| `GET /api/experiments` | First Experiments navigation / Reload | `available`, `source`, `caption`, `summaries`, `audit`, or unavailable error; presentation only |

`api()` always adds `X-P2P-UI: 1`. JSON mutations also send
`Content-Type: application/json`. Request timeouts are 150000ms whenever a
method is supplied, otherwise 15000ms. Non-success responses use JSON `detail`
when available, falling back to raw response text. Preserve these behaviors.

Backend observations relevant to layout and integration, not change proposals:

- The FastAPI console serves `/`, `/static/*` and its existing APIs. Trusted
  hosts are loopback names, supplied Origin must match, and mutations require
  the custom header. CSP restricts scripts/styles/connect/images and the
  default resource source to self. Use separate local JS/CSS and inline SVG;
  no inline event scripts, external assets or weakened policy.
- `/api/state` checks tracker `/health` then `/swarms`, with validation/time
  limits. The browser must distinguish console disconnection, tracker offline
  and unavailable membership. The peer engine separately handles discovery,
  announcements, heartbeats and TCP messages.
- `Asset.describe()` supplies `id`, `file_name`, `file_size`, `chunk_count`,
  `chunk_size`, `file_sha256`, `swarm_id`, `can_seed`.
- `Transfer.describe()` supplies `id`, `asset_id`, file metadata, `kind`,
  `download_only`, `upload_rate_limit`, `state`, `error`, `has_output`, `metrics`.
  Metrics can be null before startup. States include starting, downloading,
  completed, seeding, stopped and failed.
- Copied metrics provide peer/swarm IDs, host/port, online/upload-enabled flags,
  cap, verified chunks/bytes, final integrity, payload uploaded/downloaded,
  retries, chunk failures, duration, mean throughput, source contributions and
  observed connections. Connection data contains remote peer ID, direction,
  state, available chunks and pending requests. No historical series is supplied.
- Backend bounds: 128 MiB source/download, 4 MiB manifest, 4 concurrent imports,
  64 assets, 16 active peers and 64 historical transfers. Limits/errors remain
  backend-owned. Settings reject unknown fields. Files persist but catalogs and
  history are in-memory; restart is not resume.
- Experiment results come from `bench/results/experiments.csv` through existing
  `bench.analysis`, without invoking Matplotlib or running trials in the UI.
  The existing source-checkout dependency and unavailable behavior remain.
- Package data currently includes HTML/CSS/JS only. Bundled font binaries need
  a narrow packaging-metadata addition; see the proposed design specification.

## Event and rendering inventory

| Handler/function | Existing responsibility / preservation requirement |
|---|---|
| Boot | `navigate(); refresh(); setInterval(refresh, 1000)`; no pause-on-hidden or replacement transport |
| `hashchange -> navigate` | Dashboard default; invalid hash falls back; toggles only `main > section`; updates `nav a[aria-current]`; loads experiments once |
| `refresh.click -> refresh` | Manual snapshot request; disables Refresh while pending |
| `refresh` / `currentRefresh` | Coalesce overlapping snapshot requests; render only on success; retain last successful data and label it stale on failure; re-enable Refresh in finally |
| `action` / `refreshAfterAction` | Single busy mutation guard; hide prior error at action start; report failures; wait for in-progress snapshot then request a fresh one after work; preserve import's own refresh before selecting its asset |
| Source/manifest submit | `setupUpload` prevents navigation, reads first selected file, checks size, disables submit, reports import stages, refreshes catalog and selects returned ID, restores submit on failure/success |
| `asset`, `kind`, `download-only` change | `syncOptions` enforces current cross-field enable/disable rules; upload-rate value is read on submit |
| `peer-form.submit` | Prevent default; read controls; convert nonempty cap with Number or send null; use action guard; report queued ID |
| Dynamic Stop peer click | Bound for every rendered transfer; invokes guarded POST; uses `data-focus-key=stop-<id>` to restore focus after replacement |
| `network-peer.change` | Rerenders the selected local peer's connections/sources without a mutation |
| `reload-experiments.click` | Reads recorded results independently of periodic state refresh; disables Reload until finished |
| `renderAssets` | Rebuild selector only when asset-ID signature changes; preserve valid selected asset; render catalog every snapshot; sync start eligibility |
| `renderDashboard` | Compute unique tracker peers, active swarms and local counters; rebuild transfer table; never infer global traffic |
| `renderTransfers` | Rebuild all transfer details/actions from snapshots; no fake progress or fabricated integrity |
| `renderNetwork` | Rebuild membership; preserve selected transfer using ID signature; refresh option text after peer startup; render connections and positive verified source bytes |
| `render` | Run all four live renderers, including hidden pages; restore keyed button focus without scrolling |
| `loadExperiments` / `chart` | Clear previous table/charts/audit before loading; sort/filter existing summaries; calculate axes from mean+SD; preserve values, line meaning and exclusions |

Helpers also form part of the presentation contract: `bytes` uses B/KiB/MiB
and explicit unavailable text; `progress` uses exact verified bytes as the native
value/max; `status` emits `state-*`; `table`, `cell`, `definition`, `empty` create
semantic content. Remote values enter the DOM with `textContent`/text nodes,
not HTML interpolation. `svgNode` builds SVG with DOM APIs.

### DOM hooks to retain

Keep these IDs unique and available before deferred script initialization:

```text
Shared: connection-message, error
Dashboard: dashboard, dashboard-title, refresh, tracker-status, tracker-url,
  tracker-error, summary, dashboard-transfers
Transfers: transfer, transfer-title, source-form, source-file, source-feedback,
  manifest-form, manifest-file, manifest-feedback, peer-form, asset, kind,
  upload-rate, download-only, start-peer, peer-feedback, assets, transfer-details
Network: network, network-title, swarms, network-peer, network-details
Experiments: experiments, experiments-title, reload-experiments,
  experiment-status, experiment-caption, experiment-audit, experiment-rows,
  time-chart, throughput-chart, exclusions
```

Structural selectors also matter: `main > section`, `nav a`, form-local first
`button`, and `[data-focus-key]`. Avoid moving sections under an extra wrapper,
inserting an unrelated first button into either import form, or putting unrelated
anchors into the main `nav`. Scope icon CSS separately from chart SVG styling.

## Baseline verification actually run

Run against captured HEAD plus the existing AGENTS.md edit, before documentation
edits. Existing virtualenv and Node only; nothing installed or fetched.

| Command | Actual output / result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -ra` | `390 passed, 1 warning in 107.13s (0:01:47)`; exit 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | `All checks passed!`; exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench` | `58 files already formatted`; exit 0 |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests bench` | `Success: no issues found in 58 source files`; exit 0 |
| `node --check src/p2p/web/static/app.js` | No output; exit 0 |
| `git diff --check` (after documentation edits) | Exit 0; no whitespace errors; Git emitted its existing AGENTS.md LF/CRLF conversion notice |

The warning is the existing `StarletteDeprecationWarning` about using httpx with
Starlette TestClient. No dependency update is proposed for this visual task.

The suite includes `tests/integration/test_web_console.py`,
`tests/unit/test_web_service.py`, and `tests/e2e/test_web_http_transfer.py`:
real loopback transfer, partial verified progress, rate caps, manifest export/
import, final hash success/failure, no-peer failure, baseline zero uploads,
completed-peer relay, cancellation, limits, Host/Origin/header guards, static
asset delivery, recorded results, shutdown and deregistration. These tests call
HTTP APIs; they do not execute browser JavaScript or assert visual layout.

Not run in this audit: browser workflow interaction, screenshot capture of the
current console, browser console/network checks, keyboard/screen-reader QA,
responsive rendering or a new benchmark measurement sweep. The supplied
reference was visually inspected and sampled. Its proposed geometry remains an
estimate. Passing backend/API tests does not prove browser functionality or
future redesign fidelity. Those remain implementation acceptance gates.

After writing the documentation, a read-only SHA-256 comparison against the
checkpoint confirmed that all 118 original files remain byte-identical except
`docs/project-status.md`. In particular, the existing AGENTS.md edit, frontend,
Python code, tests and package configuration are untouched. Documentation checks
also confirmed that local Markdown links resolve, fenced blocks are balanced,
and all 42 existing HTML IDs are included in this inventory. The three new
documents are the only added source files.

## Risks carried into the plan

1. DOM rebuilds can reset focus or newly introduced details state every second.
2. Moving sections/navigational links can break current selector assumptions.
3. Pale accents need dark text or dark plot backgrounds for contrast.
4. Backend guards prohibit remote font/icon CDNs; font package data is incomplete.
5. The reference has much less information than real transfer/network tables.
   Preserve columns and technical data, allowing contained scroll and page height.
6. The current UI does not expose global throughput, CPU/RAM, timeout counts,
   live cap changes, resume, automatic manifests, search or account features.
   The redesign must not suggest those exist.

See [DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md) and the
[implementation plan](frontend-redesign-plan.md). Existing implementation and
test expectations remain untouched.
