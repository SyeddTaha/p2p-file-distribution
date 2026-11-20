# 0009. Local web console for course demonstrations

- Status: Accepted
- Date: 2026-11-20

## Context

The course demonstration needs visible peer membership, transfer progress,
integrity checks and measured comparisons. A frontend is a repository non-goal
unless a documented exception exists. The user explicitly requested this bounded
exception: a minimal local interface to the implemented engine.

## Decision

Add an optional FastAPI application under `src/p2p/web`, launched separately with
`python -m p2p.web`. Bind its server and managed peers to `127.0.0.1`. Serve packaged
HTML/CSS/vanilla JavaScript without additional dependencies, external assets,
databases or UI frameworks. Preserve the existing CLI and TCP protocol. The
tracker gains only `GET /swarms`, applying its normal lazy expiry.

Each console owns bounded in-memory catalogs and tracked peer tasks. Browser
source/manifest imports write only to UUID directories beneath a startup-configured
workspace. HTTP import/export handles local artifacts; actual file distribution
runs between `SwarmPeer` listeners over TCP. Repeated stop requests share one
cleanup task. Lifespan shutdown cancels and awaits peers. Console import thread
work is joined before import cancellation cleanup finishes.

Expose copied engine snapshots: verified chunk bytes, final-hash state, live
downloader counters, connection state and per-source payload contributions. No
timer-based progress or synthetic activity. Tracker `is_seeder` still means local
completeness; remote upload capability and remote connection counters are unknown.

Move the plotting script's existing pure CSV validation/aggregation into
`bench/analysis.py`, preserving plotting imports and commands. Read the versioned
raw CSV through that same code and render tables and two SVG charts with sample SD.
Keep experiment execution in the terminal harness: displaying existing results
does not imply new measurements.

## Alternatives considered

- Proxy distribution through HTTP: obscures the course's TCP data plane and
  duplicates working networking logic.
- React, a UI framework, or a hosted site: unnecessary dependencies/infrastructure.
- Add controls to the tracker: couples discovery to peer files and worker tasks.
- Poll final counters or estimate progress: neither accurately describes live work.
- Read generated summary files: they can be missing or stale; raw trial validation
  keeps exclusions and repetitions consistent with the existing plotting harness.

## Consequences

This frontend exception covers a local demonstration console only, not an
authenticated remote service. Trusted Host checks, same-origin enforcement and a
custom mutation header prevent ordinary cross-site browser operations. Startup
configuration controls paths and tracker URL; HTTP clients cannot supply arbitrary
filesystem paths or tracker URLs.

Limits: 128 MiB per source/download, four concurrent imports, 64 catalog entries,
16 active peers and 64 historical transfers per process. Files persist; restart
clears memory only. Resume, catalog restoration, live cap changes, LAN console
operation and browser experiment execution are out of scope. Benchmark display
requires a checkout containing `bench/` and the recorded CSV.
