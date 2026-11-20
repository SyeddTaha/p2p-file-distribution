# P2P console redesign specification

Date: 2026-11-20. Status: **Approved and implemented**.

This is the visual specification for the local P2P console, approved by the user
after the audit. [DESIGN.md](DESIGN.md) links here as the current design source.
Read the
[audit](docs/frontend-redesign-audit.md) for preservation requirements and the
[implementation plan](docs/frontend-redesign-plan.md) for scope, and the
[verification record](docs/frontend-redesign-verification.md) for actual evidence
and remaining limitations.

## Brief and evidence

Students and instructors operate this console on laptops in a lit networking
lab, often alongside terminals. The main surface stays light for reading tables;
a charcoal navigation rail establishes the dark frame in the supplied reference.

Visual source: the supplied `9e66f039-e34a-46cb-a008-cf4f9833ebf6.png`,
1024 by 768 pixels. The image is design evidence; its health data, branding,
account controls and promotional content are not product requirements.

Evidence labels used below:

- **Sampled**: exact RGB values found repeatedly in flat image regions using
  Pillow read-only pixel analysis. These describe the supplied raster, not
  necessarily the original designer's source tokens.
- **Estimated**: geometry or visual interpretation of the raster. The image
  cannot reveal CSS, font metadata, original vector strokes or responsive rules.
- **Specified**: exact proposed implementation value, selected for this console.
- **Requested**: explicitly supplied by the user, rather than inferred from pixels.

## Reference analysis and translation

| Element | Observed reference, estimates unless marked | Console treatment |
|---|---|---|
| Outer composition | Lime matte, framed application around x=57..967, y=57..699; broad cast shadow | Application fills the browser with a charcoal rail and gray workspace. Do not reproduce the presentation matte or oversized artwork shadow. |
| Sidebar | About 180px wide, charcoal; white active navigation pill; small outline icons | 208px desktop rail; retain the four real hash routes and brand link. Use the lower area for existing tracker status, not an upgrade promotion. |
| Main surface | Starts near x=236; light gray; about 24px outer corner radius | Gray working canvas, 28px leading outer corners on desktop, white content cards. |
| Heading | Large black sans, roughly 32px in the raster, tight tracking | Plus Jakarta Sans, 36px desktop page titles and 28px mobile. Actual existing page names remain. |
| Card grid | Tall white left card, smaller white cards, dark lower-right panel; roughly 6px gaps | Asymmetric membership/activity/payload composition above a full-width transfer table. Use 16px gaps for real operational content. |
| Card geometry | Roughly 18..22px radii; minimal individual shadows | 20px cards, 12px fields, 999px status/navigation pills. No uniform shadow on every card. |
| Accents | Lime emphasis, lavender shapes, charcoal chart panel | Lime primary actions and P2P series; lavender local activity and baseline series, primarily against dark chart surfaces. |
| Icons | Fine monochrome outlines in small circular holders | Inline minimal SVG, 20px view box, 1.5px rounded strokes. Retain text labels. |
| Controls | Pill search, date filter, notification and menu affordances | Keep existing Refresh/Reload and actual forms. Omit account, search, dates, notifications and overflow menus without existing actions. |
| Visualization | Overlapping calorie circles, wellness dots, monthly bars | Do not translate these into invented telemetry. Retain exact verified progress and the two existing measured experiment charts. |

The raster's actual typefaces cannot be positively identified. Plus Jakarta
Sans headings and Inter body text are **Requested**, not a font identification
claim. The original raster's very small text will not be copied at that size.

## Color tokens

The six core colors are charcoal, workspace gray, white, ink, lime and lavender.
Hex values below are the exact implementation CSS values. No gradients are used.

| CSS token | Value | Evidence | Role |
|---|---|---|---|
| `--color-sidebar` | `#222124` | Sampled | Navigation and dark payload/chart panels |
| `--color-canvas` | `#E1E1E1` | Sampled | Main workspace |
| `--color-surface` | `#FFFFFF` | Sampled | Forms, tables, membership cards, active navigation |
| `--color-ink` | `#19181B` | Specified | Headings and normal text on light surfaces |
| `--color-lime` | `#DAF163` | Sampled | Primary action background, P2P chart line, highlights |
| `--color-lavender` | `#BBB2F5` | Sampled | Activity surfaces, baseline chart line, secondary emphasis |
| `--color-muted` | `#626067` | Specified | Secondary text on canvas and white |
| `--color-line` | `#D4D2D8` | Specified | Decorative separators and table rules |
| `--color-control-border` | `#817D88` | Specified | Input boundaries and neutral secondary controls |
| `--color-hover` | `#F1F0F4` | Specified | Neutral row and secondary-action hover |
| `--color-on-dark` | `#E8E6ED` | Specified | Body text and chart axes on charcoal |
| `--color-lime-hover` | `#CBE64E` | Specified | Primary action hover |
| `--color-lavender-ink` | `#6953BA` | Specified | Light-surface links and focus rings |
| `--color-success` / `--color-success-bg` | `#31521D` / `#EEF5DE` | Specified | Verified, completed, online, seeding |
| `--color-error` / `--color-error-bg` | `#A12622` / `#FCEDEA` | Specified; error ink retained from current CSS | Failed and offline |
| `--color-pending` / `--color-pending-bg` | `#67521D` / `#F6F0DC` | Specified | Starting and pending, with explicit text |
| `--color-idle` / `--color-idle-bg` | `#626067` / `#F1F0F4` | Specified | Stopped and unavailable |

`#DCEA95` is the **Sampled** outer presentation matte. It is not a console
background token. Pure white is deliberately retained to follow this reference.

Use charcoal text on lime/lavender, never white. Reference lavender and lime
are unsuitable as small text or thin informative lines on white. Experiment
series will use these colors on charcoal with solid/dashed differentiation.

Calculated sRGB contrast ratios for the selected pairs:

| Pair | Ratio |
|---|---|
| Charcoal `#222124` on lime | 12.77:1 |
| Charcoal on lavender | 8.24:1 |
| Muted `#626067` on canvas | 4.74:1 |
| Muted on white | 6.20:1 |
| Lavender ink on white | 5.92:1 |
| On-dark text on charcoal | 12.95:1 |

These calculations verify only those pairs. Verify all final component states
and boundaries during implementation: 4.5:1 for normal text, 3:1 for large text
and essential non-text indicators. A color change alone never communicates state.

## Typography tokens

All sizes assume the browser's default 16px root, with browser resizing preserved.
These are **Specified** implementation values rather than measured font metrics.

| Token | Value / role |
|---|---|
| `--font-heading` | `"Plus Jakarta Sans", "Inter", "Segoe UI", sans-serif` |
| `--font-body` | `"Inter", "Segoe UI", system-ui, sans-serif` |
| `--font-code` | `ui-monospace, "Cascadia Code", Consolas, monospace` |
| `--text-page` | `2.25rem`, weight 600, line-height 1.15, tracking `-0.04em` |
| `--text-page-mobile` | `1.75rem`, weight 600, line-height 1.2 |
| `--text-section` | `1.375rem`, weight 600, line-height 1.3, tracking `-0.02em` |
| `--text-card` | `1rem`, weight 600, line-height 1.4 |
| `--text-metric` | `2.5rem`, weight 600, line-height 1.1, tracking `-0.04em`; activity count |
| `--text-membership` | `3.5rem` desktop; `2.5rem` tablet/mobile, `2rem` below 375px; weight 600, line-height 1.05 |
| `--text-body` | `0.9375rem`, weight 400, line-height 1.6 |
| `--text-control` | `0.875rem`, weight 500 or 600, line-height 1.4 |
| `--text-caption` | `0.8125rem`, weight 400, line-height 1.5 |
| `--text-code` | `0.8125rem`, weight 400, line-height 1.5 |

Use heading family for page/section headings and large counts; Inter for
controls, tables and prose. Use tabular numerals for counters, byte totals,
durations and rates. Reserve monospace for hashes, peer IDs and addresses.
Keep explanatory prose under 75ch. Sentence case throughout; preserve units.

### Local font delivery

Both font families are bundled as Latin variable WOFF2 under
`src/p2p/web/static/fonts/`, with their SIL Open Font License notices.
`sources.json` in that directory records original download URLs and SHA-256
digests. Both are served from the console itself using `font-display: swap`.
Other scripts and unsupported glyphs use the fallback stacks.

The existing Content Security Policy permits same-origin assets and blocks
external font stylesheets. Do not add Google Fonts requests, remote icons,
data-URL fonts or loosen the policy. Font files were acquired only after the
user approved the plan; no software, skill or system font was installed.

The approved asset-only change to `pyproject.toml` includes static SVG, WOFF2,
license TXT and provenance JSON in package data. A locally built wheel was
inspected to verify those assets are included. Dependencies, Python code and
the existing Content Security Policy are unchanged.

## Spacing, geometry and elevation

All values below are **Specified**, informed by the estimated reference geometry.

| Token family | Exact values |
|---|---|
| Space | `--space-1: 4px`, `--space-2: 8px`, `--space-3: 12px`, `--space-4: 16px`, `--space-5: 20px`, `--space-6: 24px`, `--space-8: 32px`, `--space-10: 40px` |
| Layout | `--sidebar-width: 208px`, `--content-max: 1440px`, `--page-gutter: 28px`, `--grid-gap: 16px` |
| Radius | `--radius-shell: 28px`, `--radius-card: 20px`, `--radius-control: 12px`, `--radius-pill: 999px` |
| Controls | `--control-height: 44px`, `--nav-height: 44px`, `--icon-size: 20px`, `--progress-height: 8px` |
| Card padding | `24px` desktop, `20px 16px` mobile |
| Table cells | `12px 16px`; headers `12px 16px`; numeric columns right aligned |
| Border | `1px solid var(--color-line)` for separators; control border uses its stronger token |
| Focus | `3px solid var(--color-lavender-ink)`, `3px` offset on light; lime outline on dark |
| Shadow | Cards: `none`; application frame if needed: `0 12px 32px rgb(34 33 36 / 0.08)` |
| Motion | Color/opacity only, `140ms cubic-bezier(0.22, 1, 0.36, 1)`; reduced motion removes transitions |

Do not animate progress from elapsed time. Never draw a progress estimate between
snapshots. Native verified progress follows the latest engine observation.

## Layout

Keep all four routes in one document and retain `main > section` for each page.
Left-align headings, labels and prose. Keep tables full width instead of squeezing
six columns into the reference's narrow health cards.

Desktop Dashboard, schematic rather than a pixel mockup:

```text
+----------------+---------------------------------------------------+
| P2P console    | Dashboard                               [Refresh] |
|                | Console connection / last snapshot / global error |
| Dashboard     *| Tracker status, URL and any tracker error          |
| File Transfer  | +--------------------+--------------------------+  |
| Peer Network   | | Tracker membership | Downloading (local)      |  |
| Experiments    | | Active peers       +--------------------------+  |
|                | | Active swarms      | Local payload totals     |  |
|                | |                    | Uploaded / Downloaded    |  |
|                | +--------------------+--------------------------+  |
| Local workspace| +-----------------------------------------------+ |
|                | | Local transfers: full six-column live table  | |
|                | +-----------------------------------------------+ |
+----------------+---------------------------------------------------+
```

Membership is the tall white block; local downloading uses a restrained
lavender surface; local payload uses the dark block. All five current summary
values remain. The summary does not become a throughput/history chart. Existing
tracker health stays distinct from browser-to-console connection health.

Other pages use the same shell:

- **File Transfer:** two import forms side by side, then Start a peer,
  asset/manifest table, and every transfer entry with its controls. Use native
  `<details>` for advanced upload/baseline settings, initially open so existing
  settings remain discoverable. Keep limits and essential mode warnings visible.
- **Peer Network:** full-width swarm tables followed by local peer selector,
  observed TCP connections, and verified source-contribution table. Do not turn
  these into a decorative topology that implies unavailable connection data.
- **Experiments:** dataset status/caption/audit, full table, then the two existing
  SVG charts in dark panels. Preserve axes, units, sample SD, legend, exclusions
  and the loopback limitation. No run-experiment action is proposed.

### Responsive rules, specified rather than inferred

| Viewport | Structure |
|---|---|
| `>= 1200px` | 208px persistent rail; 28px workspace gutter; asymmetric Dashboard grid; two-column imports/charts |
| `800..1199px` | 184px rail; 20px gutter; summary can become two columns; peer fields wrap; full tables keep internal horizontal scrolling |
| `< 800px` | Replace vertical rail with a compact charcoal header and four visible, wrapping text navigation links; 16px gutter; single-column forms, cards and charts |
| `320px` and up | No page-level horizontal overflow. Tables scroll in labeled, keyboard-accessible regions; full hashes wrap in details. Buttons may wrap, never disappear. |

No mobile navigation drawer is necessary. This avoids adding a focus-trapping
overlay. At 200% zoom the layout reflows using the same rules.

## Component and state contract

| Component | Treatment and required behavior |
|---|---|
| Navigation | White active pill on charcoal with existing `aria-current="page"`; 20px icons plus text; all four routes and browser history work. |
| Primary buttons | Lime fill, charcoal label, 44px minimum height, 12px radius; retain exact action semantics. |
| Secondary buttons / links | Neutral outlined controls; export links remain real anchors. Stop peer stays directly accessible. |
| File inputs | Keep real labeled native file inputs and submit buttons; do not replace them with a nonfunctional drop zone. |
| Forms | Preserve required/accept/min/max/step constraints, busy gates, source eligibility, asset selection and response feedback. |
| Advanced settings | Upload cap and baseline switch remain in the same peer form with existing IDs; disclosure state must survive refreshes. Caps still apply only at peer creation. |
| Status | Text-labeled pills for starting, downloading, seeding, completed, failed, stopped, online/offline and pending/verified/failed integrity. Pending never implies verified. |
| Progress | Native `<progress>` with current accessible label, verified bytes and chunk count. Whole-file SHA-256 remains separate. |
| Tables | Semantic headers; original columns/data retained; restrained row rules; scoped scroll region when needed; no clipping of actions. |
| Identifiers | Full swarm ID, SHA-256, peer ID and address remain readable/selectable; no irreversible truncation behind a tooltip. |
| Feedback | Persistent inline loading/import/queued messages, global `role="alert"`, connection `role="status"`, and per-transfer errors. |
| Empty/unavailable | Preserve the distinction among zero members, unavailable tracker membership, no local transfers, missing results and stale console data. |
| Charts | Existing N=1,2,4,8 recorded series only; baseline lavender dashed, P2P lime solid; high-contrast axes and visible SD; table remains the numerical equivalent. |
| SVG icons | Inline local SVG; decorative icons use `aria-hidden="true"` and `focusable="false"`; chart styling must not leak into navigation icons. |

Every interactive component needs default, hover, active, focus, disabled,
loading and applicable error styling. Preserve `hidden` semantics. New wrappers
must not disrupt labels, document order or keyboard access.

Polling replaces dynamic DOM on every successful snapshot. Stop peer controls
and network scroll regions retain keyed focus. Network tables also retain their
horizontal scroll position. Advanced settings live outside regenerated content,
so their open state and form values survive polling without a separate state store.

## Review against the brief

The initial temptation is to reproduce the reference's bubble chart and several
identical metric tiles. This proposal instead keeps the tall white / lavender /
dark composition for actual membership and local payload, while moving the
dense transfer table across the full content width. That retains the visual
identity without inventing instantaneous rates, historical samples or health-like
scores. The memorable element is the charcoal frame and asymmetric summary;
forms and technical tables stay quiet and conventional.

Existing PRODUCT.md preferences for restrained decoration still apply. The
user's newer brief explicitly replaces the old top navigation, system-only
typography and 4px corners. The implementation records that change in the current
design documentation while retaining the original audit as historical evidence.

Approval covered the design direction and the linked implementation scope.
The implementation uses the specified palette and structure; browser evidence
and explicit verification limits are in the linked verification record.
