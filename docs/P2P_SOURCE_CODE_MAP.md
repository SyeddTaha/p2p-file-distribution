# P2P source code map

Reference: `feat/local-web-console`, commit `121b31f82b094ef68b3f512c83f4e8c33a6b5548`, audited 20 November 2026. All paths/definition lines below were checked against this source snapshot. Production code, tests and dependencies are unchanged by this documentation task.

This document is a navigation reference, not a replacement for [the self-contained handbook](P2P_COMPLETE_PROJECT_HANDBOOK.md). Use [the demo script](P2P_DEMO_SCRIPT.md) for runnable service commands and [revision](P2P_VIVA_QUICK_REVISION.md) for viva review.

## Contents

1. [Execution call chains](#execution-call-chains)
2. [Interfaces, arguments and failure boundaries](#interfaces-arguments-and-failure-boundaries)
3. [State ownership](#state-ownership)
4. [Production Python files and definitions](#production-python-files-and-definitions)
5. [Frontend and assets](#frontend-and-assets)
6. [Configuration, tests and documentation](#configuration-tests-and-documentation)

## Execution call chains

| Entry or action | Actual flow |
|---|---|
| Installed `p2p` command | `pyproject.toml` project script → `p2p.cli:main` → `build_parser` → tracker Uvicorn or `asyncio.run(_run_peer_command)` |
| `python -m p2p.web` | `web/__main__.py:main` → `create_app(workspace,tracker_url)` → Uvicorn loopback HTTP listener |
| Source import | JS `setupUpload` → POST assets → `create_app.import_asset` → `Console.import_asset` → thread writes → `build_manifest` → `write_manifest` → Asset |
| Manifest import | Same HTTP route, manifest_only=true → `load_manifest` → duplicate-key hook and `validate_manifest` → manifest-only Asset |
| Start seed | POST transfers → `StartTransfer.model_validate_json` → `Console.start` → tracked `_run` → `SwarmPeer.start` → seed manifest equality → listener → started announce → heartbeat |
| Start download | Same console flow → peer start → `SwarmPeer.download` → heartbeat discovery → `_connect_to_peers` → `PeerConnection.connect/perform_handshake` → scheduler/coordinator |
| Request path | `SwarmDownloader.run` → `_download_from_peer` → `DownloadWorker.fetch_next` → `reserve_next` → `_request_one` → `send_request` → codec encode/write |
| Serving path | `PeerServer._handle_client` → accept/handshake → `SwarmPeer._serve_connection` → receive REQUEST → `_read_chunk`/threaded `_read_and_verify_chunk` → limiter acquire → send PIECE |
| Receiving path | Sole `_read_peer_messages` task → `receive_message` → codec read/decode/state validation → queue → worker → `StorageManager.write_chunk` → scheduler mark_verified |
| Share newly accepted index | Coordinator `_broadcast_have` to other outbound peers + `SwarmPeer._on_chunk_verified` updates listener bitfield and notifies inbound peers |
| Finish | Coordinator `to_thread(storage.finalize)` → whole-file SHA-256 + os.replace → close outbound connections → peer completed announce → return output → console completed, keep serving |
| Stop | POST stop → shared Console stop task → cancel/join `_run` → `SwarmPeer.close` shared shielded cleanup → cancel heartbeat/stop listener/best-effort stopped/HTTP close |
| State polling | JS refresh → GET state → bounded tracker health/list reads + Asset/Transfer descriptions → peer copied snapshots → render functions |
| Recorded results | GET experiments → `to_thread(read_experiments)` → `parse_csv_results` → `calculate_stats` → table/SVG; no runner/Matplotlib invoked |
| Benchmark command | Config validation → seeded shuffled trials → fresh tracker/peers/temp files → common download release + independent hashes → cleanup → append rows |
| Plot command | `parse_csv_results` → audit complete trials → `calculate_stats` → Agg error-bar figures, summary/audit CSVs |

## Interfaces, arguments and failure boundaries

Read signatures below literally: `Path` is a local server filesystem path, not browser remote path; manifest `object` inputs are validated before use; byte counts are bytes; `_bps` rate fields in this code still mean bytes/second. `-> None` methods act through owned state. Properties are copied/read observations where documented, not promises of cross-thread synchronization.

| Interface | Important arguments and returns | Internal steps and failure/role |
|---|---|---|
| `build_manifest(file_path,chunk_size)` | Local file; default 256 KiB → validated FileManifest dict | Bounded reads update chunk and whole SHA-256; rejects empty/unsafe/over-limit input; called by CLI/import/seed check/runner |
| `validate_manifest(manifest)` | Untrusted object → copied exact-schema dictionary | Exact fields/types/order/count/length/hash syntax; ManifestError on invalid data; does not know actual unknown payload yet |
| `load_manifest(manifest_path)` | Local JSON file → FileManifest | Reads cap+1, rejects duplicate keys and malformed JSON, then validates |
| `write_manifest(manifest,path)` | Validatable object/local destination → None | Canonical bytes, sibling temporary file, flush/fsync, os.replace, temporary cleanup |
| `compute_swarm_id(manifest)` | Validatable manifest → lowercase SHA-256 string | Hash compact sorted-key validated JSON; filename/layout participate |
| `StorageManager(manifest,download_dir)` | Manifest and isolated destination → storage owner | Validates paths; truncates fresh part; no resume |
| `write_chunk(index,data)` | Valid zero-based int and bytes → true if newly stored, false if duplicate accepted index | Validate exact length/hash, seek/write/flush then mark; ChunkIntegrityError, OSError, RuntimeError paths |
| `finalize()` | No args → final target Path | Require all indices; fsync/hash disk file; mismatch marks failed and preserves part; replace only on match |
| `PeerConnection.connect(host,port,...)` | Address, local identity/swarm/count/bitfield/timeouts → handshaken connection by default | Connect deadline; cleanup on handshake failure/cancellation; ConnectionError/ProtocolError/ConnectionClosed |
| `receive_message()` | Established connection → typed REQUEST/PIECE/HAVE | One reader; reject wrong states/ranges/unsolicited pieces; update remote HAVE bitfield |
| `send_request(index)` | Index → None; records pending index | Enforce range, no duplicate, inflight ceiling; frame write; failures close connection |
| `close()` on connection/peer | No args → None | Shared shielded cleanup task; repeated callers join same resource cleanup |
| `PeerServer.start/stop` | Constructor host/port/identity/on_connection/caps; start returns bound port | Accept tracks handler/connection before handshake; reject excess; shutdown cancels/joins handlers and sockets |
| `SwarmRegistry.announce(request)` | Validated announce → interval and compact other-peer list | Lazy expiry, update/remove/promote, exclude self, sample at most 50; no total population cap |
| `evict_stale(swarm_id=None)` | One/all swarms → number evicted | Monotonic age strictly greater than interval*multiplier; remove empty swarms |
| `reserve_next(peer_id)` | Registered availability → reserved index or None | Filter/sort missing indices, seeded choice, synchronous state/ownership update |
| `release(index,peer_id,failed=...)` | Optional owner guard → whether release occurred | In-flight returns missing; no network; used after failure/cancellation/retirement |
| `mark_verified(index,peer_id=...)` | Storage-accepted index → whether owner accepted | Scheduler state only; does not hash or write bytes itself |
| `DownloadWorker.fetch_next()` | Constructor connection/scheduler/storage and retry settings → verified index or None | Reserve, request/consume queue, validate storage, count bytes; max attempts; last_error distinguishes exhausted failure |
| `SwarmDownloader.run()` | Constructor handshaken connections plus matching scheduler/storage → set of verified indices | Own sole readers/bounded inboxes/one-request-per-peer batches, HAVE updates, retirement, finalization; always closes owned outbound streams |
| `SwarmPeer.start()` | Constructor manifest/tracker/destination/optional source/upload policy/seed → listener port | Verify seed, bind, announce, remember peers, heartbeat; rollback aggregates cleanup errors |
| `SwarmPeer.download()` | Started download peer → published Path | Initial discovery/connections only; copies counters on failure; completed announce can fail after publication |
| `SwarmPeer._read_chunk(index)` | Available verified index → bytes | Upload-enabled gate; choose source/part/final; threaded read/recheck; bad local bytes not sent |
| `SwarmPeer.snapshot()` | Owning event loop → PeerSnapshot | Copies exact verified lengths, final state, counters, connections/source contributions; performs no discovery/scheduling I/O |
| `TokenBucketRateLimiter.acquire(n)` | Positive payload-byte count → None after permission | Shared lock, refill, proportional wait, oversized acquisition support; CancelledError propagates without unfulfilled subtraction |
| `Console.import_asset(request,name,manifest_only)` | Raw HTTP body, safe basename and mode → Asset | Bounds/catalog/import slots/UUID directory; thread joins on cancellation; invalid import file removed |
| `Console.start(options)` | Strict StartTransfer → starting Transfer | Eligibility/size/history/active bounds; queues _run, does not complete transfer synchronously |
| `Console.stop(id)` | Known transfer UUID → None | Shared stop task cancels/joins transfer; unknown id HTTP404; files retained |
| `finish_disk_task(task)` | Task wrapping thread work → its result | Shield/join before cleanup; retains outer cancellation even when joined task fails |
| `tracker_json(client,url)` | HTTPX client and tracker URL → parsed JSON | Stream response cap before parse; status errors and deadline supplied by caller |
| `run_single_trial(config,mode,N,repetition,is_warmup,metadata)` | Validated experiment settings → one CSV Row per client | Fresh ASGI tracker/real TCP peers, common start, independent output hash, graceful cleanup; failed observations retained |
| `parse_csv_results(path,experiment_id)` | Raw current-schema CSV → run summaries, audit list, caption | Reject mixed context/invalid totals/duplicates; exclude whole failed/incomplete/warmup trials with reasons |
| `calculate_stats(runs)` | Included run summaries → configuration mean/sample-SD/count records | Trial-level aggregation; one-observation SD displayed zero |
| `generate_all_plots(path,out,experiment_id)` | Raw CSV and output dir → four figure Paths | Calls shared analysis, writes audit/summary, draws Agg graphs; rejects no successful measured trials |

## State ownership

| Owner | Owned mutable data | Boundary |
|---|---|---|
| Tracker registry | Swarm dicts, PeerRecord last_seen/completeness | Synchronous operations on tracker loop; no persistence |
| Console | Asset/Transfer catalogs, peer task/stop task references, import slots | One console instance per process/workspace; API IDs select owned records |
| SwarmPeer | Listener, HTTP client, heartbeat, local available indices, upload limiter/counter, downloader reference | Start/download/close lifecycle; source verification before announcing |
| PeerConnection | State, remote identity/bitfield, pending requests, write lock, close task | Exactly one reader at a time; serialized writes |
| DownloadScheduler | Index states, reservation owners, remote availability | No await inside reservation; not a thread-safe shared service |
| DownloadWorker | One connection's attempts, completed indices, verified-byte counters | One outstanding request; queue consumed by worker |
| SwarmDownloader | Readers, inboxes, active/retired sources, request batches, duration | Owns passed outbound connections; closes them on completion/error |
| StorageManager | Part/target paths, accepted indices, final integrity | Sync bounded chunk writes; final hash offloaded by caller; no resume |
| Token bucket | Tokens, refill time, lock | Shared per uploader, not per socket |

## Production Python files and definitions

The following definition index is extracted from Python syntax trees, then cross-checked against the call chains above. It includes 31 Python files across `src/p2p`, `bench`, and the existing report exporter, with 270 class/function definitions including nested HTTP route closures. A signature shows parameters/defaults/return annotation; a description explains its responsibility. Explicitly raised errors are a static aid, not an exhaustive list of every exception a dependency can propagate. Full behavior and parameters are explained above and in the owning handbook chapter.

### `bench/__init__.py`

Reproducible benchmark runner and analysis tools.

Imports/dependencies: none. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

### `bench/analysis.py`

Pure benchmark trial validation and aggregation, shared by plots and web UI.

Imports/dependencies: `__future__`, `collections`, `csv`, `dataclasses`, `logging`, `math`, `pathlib`, `statistics`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`RunSummary`](../bench/analysis.py#L57) (line 57) | `class` | Structured type or domain exception; see related methods. Fields: run_id: str, mode: str, num_clients: int, values: dict[str, float]. |
| [`ConfigSummary`](../bench/analysis.py#L65) (line 65) | `class` | Structured type or domain exception; see related methods. Fields: mode: str, num_clients: int, count: int, means: dict[str, float], stds: dict[str, float]. |
| [`positive_number`](../bench/analysis.py#L73) (line 73) | `(value: str, field: str, *, allow_zero: bool=False) → float` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`parse_csv_results`](../bench/analysis.py#L80) (line 80) | `(csv_path: Path, experiment_id: str \| None=None) → tuple[list[RunSummary], list[dict[str, str]], str]` | Validate complete trials; retain exclusions in an explicit audit, never partial successes. Explicit raises: ValueError. |
| [`calculate_stats`](../bench/analysis.py#L183) (line 183) | `(runs: list[RunSummary]) → list[ConfigSummary]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `bench/plot_results.py`

Headless plots and derived summaries: python -m bench.plot_results.

Imports/dependencies: `__future__`, `argparse`, `csv`, `logging`, `matplotlib`, `matplotlib.pyplot`, `pathlib`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`generate_all_plots`](../bench/plot_results.py#L25) (line 25) | `(csv_path: Path, output_dir: Path, experiment_id: str \| None=None) → list[Path]` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`main`](../bench/plot_results.py#L119) (line 119) | `() → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `bench/run_experiments.py`

Reproducible loopback sweeps: python -m bench.run_experiments.

Imports/dependencies: `__future__`, `argparse`, `asyncio`, `csv`, `dataclasses`, `datetime`, `fastapi`, `hashlib`, `httpx`, `logging`, `math`, `os`, `p2p.config`, `p2p.peer.client`, `p2p.storage.manager`, `p2p.storage.manifest`, `p2p.tracker.registry`, `p2p.tracker.server`, `pathlib`, `platform`, `random`, `subprocess`, `tempfile`, `time`, `uuid`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ExperimentConfig`](../bench/run_experiments.py#L85) (line 85) | `class` | Both modes use identical source bytes, chunk sizes and origin limits. Fields: experiment_id: str, output_path: Path, modes: tuple[str, ...], client_counts: tuple[int, ...], repetitions: int, warmup: bool, file_size_bytes: int, chunk_size_bytes: int, seeder_upload_limit_bps: float, leecher_upload_limit_bps: float, seed: int, work_dir: Path \| None, trial_timeout_s: float \| None, notes: str. |
| [`ExperimentConfig.__post_init__`](../bench/run_experiments.py#L103) (line 103) | `(self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`get_system_metadata`](../bench/run_experiments.py#L139) (line 139) | `() → Row` | Capture environment without personal paths, usernames or hostnames. |
| [`validate_csv`](../bench/run_experiments.py#L170) (line 170) | `(csv_path: Path) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`append_rows`](../bench/run_experiments.py#L177) (line 177) | `(csv_path: Path, rows: list[Row]) → None` | Append each completed trial, including failures, without overwriting prior rows. |
| [`prepare_source`](../bench/run_experiments.py#L189) (line 189) | `(path: Path, size: int, seed: int) → None` | Generate seeded bytes in bounded blocks outside the event loop. |
| [`file_hash`](../bench/run_experiments.py#L197) (line 197) | `(path: Path) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`run_single_trial`](../bench/run_experiments.py#L202) (line 202) | `async (config: ExperimentConfig, *, mode: str, num_clients: int, repetition: int, is_warmup: bool, system_meta: Row) → list[Row]` | Fresh tracker, peers, ports and directories; one retained observation per client. Explicit raises: FileIntegrityError. |
| [`run_experiments`](../bench/run_experiments.py#L356) (line 356) | `async (config: ExperimentConfig) → list[Row]` | Interleave configurations, flush each trial, and log warmups in the raw CSV. |
| [`parse_args`](../bench/run_experiments.py#L389) (line 389) | `(args: list[str] \| None=None) → ExperimentConfig` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`main`](../bench/run_experiments.py#L432) (line 432) | `() → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: SystemExit. |

### `docs/build_course_report.py`

Export the report as standalone HTML and optional PDF without new packages.

Regenerate plots first. PDF export requires an already installed Chrome/Chromium.
The Markdown renderer supports only the constructs used by course-report.md.

Imports/dependencies: `__future__`, `argparse`, `base64`, `html`, `os`, `pathlib`, `re`, `shutil`, `subprocess`, `tempfile`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`inline`](../docs/build_course_report.py#L61) (line 61) | `(text: str) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`inline.link`](../docs/build_course_report.py#L66) (line 66) | `(match: re.Match[str]) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`render_page`](../docs/build_course_report.py#L73) (line 73) | `(text: str) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`find_browser`](../docs/build_course_report.py#L133) (line 133) | `(explicit: Path \| None) → Path` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: FileNotFoundError. |
| [`build_report`](../docs/build_course_report.py#L151) (line 151) | `(*, pdf: bool=False, browser: Path \| None=None) → Path` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: RuntimeError. |
| [`main`](../docs/build_course_report.py#L198) (line 198) | `() → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/__init__.py`

P2P File Distribution System package.

Imports/dependencies: none. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

### `src/p2p/cli.py`

Command-line entry point for the tracker and swarm peers.

Imports/dependencies: `__future__`, `argparse`, `asyncio`, `collections.abc`, `httpx`, `logging`, `p2p.peer.client`, `p2p.peer.downloader`, `p2p.storage.manifest`, `pathlib`, `uvicorn`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`build_parser`](../src/p2p/cli.py#L21) (line 21) | `() → argparse.ArgumentParser` | Create the command-line parser. |
| [`_run_peer_command`](../src/p2p/cli.py#L70) (line 70) | `async (args: argparse.Namespace) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`main`](../src/p2p/cli.py#L116) (line 116) | `(argv: Sequence[str] \| None=None) → None` | Run the selected CLI command. |

### `src/p2p/peer/__init__.py`

Peer TCP data plane package.

Imports/dependencies: `p2p.peer.client`, `p2p.peer.connection`, `p2p.peer.downloader`, `p2p.peer.rate_limiter`, `p2p.peer.scheduler`, `p2p.peer.server`. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

Public exports: `ChunkState`, `ConnectionState`, `DownloadScheduler`, `DownloadError`, `DownloadWorker`, `IN_FLIGHT`, `NoAvailablePeersError`, `PeerConnection`, `PeerServer`, `SwarmDownloader`, `SwarmPeer`, `TokenBucketRateLimiter`.

### `src/p2p/peer/client.py`

Tracker-connected peer lifecycle for seeding and downloading a swarm.

Imports/dependencies: `__future__`, `asyncio`, `hashlib`, `hmac`, `httpx`, `logging`, `math`, `p2p.config`, `p2p.peer.connection`, `p2p.peer.downloader`, `p2p.peer.metrics`, `p2p.peer.rate_limiter`, `p2p.peer.scheduler`, `p2p.peer.server`, `p2p.protocol`, `p2p.storage.manager`, `p2p.storage.manifest`, `p2p.tracker.models`, `pathlib`, `random`, `typing`, `uuid`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`SwarmPeer`](../src/p2p/peer/client.py#L37) (line 37) | `class` | Peer lifecycle joining tracker discovery, serving, and downloading. |
| [`SwarmPeer.__init__`](../src/p2p/peer/client.py#L47) (line 47) | `(self, manifest: object, tracker_url: str, download_dir: Path, *, seed_file: Path \| None=None, host: str='127.0.0.1', listen_port: int=0, peer_id: str \| None=None, tracker_transport: httpx.AsyncBaseTransport \| None=None, tracker_timeout: float=10.0, upload_enabled: bool=True, upload_rate_limit: float \| None=None, scheduler_seed: int=0) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`SwarmPeer.listen_port`](../src/p2p/peer/client.py#L141) (line 141) | `(self) → int` | Return the listener's assigned port after start. Explicit raises: RuntimeError. |
| [`SwarmPeer.snapshot`](../src/p2p/peer/client.py#L147) (line 147) | `(self) → PeerSnapshot` | Copy live engine state on its owning event loop, without network I/O. |
| [`SwarmPeer.is_seeder`](../src/p2p/peer/client.py#L201) (line 201) | `(self) → bool` | Whether every manifest chunk is locally available. |
| [`SwarmPeer._local_bitfield`](../src/p2p/peer/client.py#L205) (line 205) | `(self) → Bitfield` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer.start`](../src/p2p/peer/client.py#L209) (line 209) | `async (self) → int` | Start the peer listener, announce its presence, and launch heartbeats. Explicit raises: BaseExceptionGroup, RuntimeError, ValueError. |
| [`SwarmPeer._announce`](../src/p2p/peer/client.py#L270) (line 270) | `async (self, event: AnnounceEvent) → AnnounceResponse` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer._remember_peers`](../src/p2p/peer/client.py#L284) (line 284) | `(self, peers: list[PeerInfo]) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer.heartbeat`](../src/p2p/peer/client.py#L289) (line 289) | `async (self) → None` | Refresh tracker registration and peer discovery immediately. Explicit raises: RuntimeError. |
| [`SwarmPeer._heartbeat_loop`](../src/p2p/peer/client.py#L296) (line 296) | `async (self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer._read_chunk`](../src/p2p/peer/client.py#L307) (line 307) | `async (self, index: int) → bytes` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ProtocolError, RuntimeError. |
| [`SwarmPeer._read_and_verify_chunk`](../src/p2p/peer/client.py#L332) (line 332) | `(path: Path, offset: int, length: int, expected_hash: str) → bytes` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: OSError. |
| [`SwarmPeer._serve_connection`](../src/p2p/peer/client.py#L343) (line 343) | `async (self, connection: PeerConnection) → None` | Serve verified REQUESTs and record remote HAVE notifications. Explicit raises: ProtocolError. |
| [`SwarmPeer._on_chunk_verified`](../src/p2p/peer/client.py#L366) (line 366) | `async (self, index: int) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer._connect_to_peers`](../src/p2p/peer/client.py#L382) (line 382) | `async (self, peers: list[PeerInfo]) → list[PeerConnection]` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: result. |
| [`SwarmPeer._connect_to_peers.connect`](../src/p2p/peer/client.py#L398) (line 398) | `async (peer: PeerInfo) → PeerConnection` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer.download`](../src/p2p/peer/client.py#L476) (line 476) | `async (self) → Path` | Discover peers, download verified chunks, then announce completion. Explicit raises: NoAvailablePeersError, RuntimeError. |
| [`SwarmPeer.wait_until_stopped`](../src/p2p/peer/client.py#L530) (line 530) | `async (self) → None` | Keep serving as a seeder until the caller cancels or closes the peer. |
| [`SwarmPeer.close`](../src/p2p/peer/client.py#L534) (line 534) | `async (self) → None` | Stop serving, stop heartbeat, announce stopped, and release HTTP resources. |
| [`SwarmPeer._close_resources`](../src/p2p/peer/client.py#L544) (line 544) | `async (self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer.__aenter__`](../src/p2p/peer/client.py#L572) (line 572) | `async (self) → Self` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmPeer.__aexit__`](../src/p2p/peer/client.py#L576) (line 576) | `async (self, exc_type: type[BaseException] \| None, exc_val: BaseException \| None, exc_tb: object) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/peer/connection.py`

Peer TCP connection management, state machine, and message exchange.

Imports/dependencies: `__future__`, `asyncio`, `enum`, `logging`, `p2p.config`, `p2p.protocol`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`normalize_socket_host`](../src/p2p/peer/connection.py#L35) (line 35) | `(host: str) → str` | Remove URI-style brackets from IPv6 literals before socket use. |
| [`ConnectionState`](../src/p2p/peer/connection.py#L42) (line 42) | `class: enum.Enum` | Lifecycle states for a peer TCP connection. |
| [`PeerConnection`](../src/p2p/peer/connection.py#L52) (line 52) | `class` | Manages an individual peer TCP connection and its protocol state machine. |
| [`PeerConnection.__init__`](../src/p2p/peer/connection.py#L62) (line 62) | `(self, reader: asyncio.StreamReader \| None=None, writer: asyncio.StreamWriter \| None=None, *, swarm_id: str, my_peer_id: str, my_listen_port: int, chunk_count: int, local_bitfield: Bitfield, handshake_timeout: float=HANDSHAKE_TIMEOUT_SEC, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC, max_inflight: int=MAX_INFLIGHT_PER_PEER) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`PeerConnection.state`](../src/p2p/peer/connection.py#L110) (line 110) | `(self) → ConnectionState` | Current lifecycle state of the connection. |
| [`PeerConnection.is_connected`](../src/p2p/peer/connection.py#L115) (line 115) | `(self) → bool` | True if the connection has completed handshake and is in steady state. |
| [`PeerConnection.is_closed`](../src/p2p/peer/connection.py#L124) (line 124) | `(self) → bool` | True if the connection is closed. |
| [`PeerConnection.remote_peer_id`](../src/p2p/peer/connection.py#L129) (line 129) | `(self) → str \| None` | Peer ID of the remote peer once verified in handshake, or None. |
| [`PeerConnection.remote_listen_port`](../src/p2p/peer/connection.py#L134) (line 134) | `(self) → int \| None` | Listening port of the remote peer once verified in handshake, or None. |
| [`PeerConnection.remote_handshake`](../src/p2p/peer/connection.py#L139) (line 139) | `(self) → Handshake \| None` | Handshake payload received from the remote peer, or None. |
| [`PeerConnection.remote_bitfield`](../src/p2p/peer/connection.py#L144) (line 144) | `(self) → Bitfield \| None` | Bitfield of chunk availability for the remote peer, or None. |
| [`PeerConnection.my_peer_id`](../src/p2p/peer/connection.py#L149) (line 149) | `(self) → str` | Local peer identifier. |
| [`PeerConnection.swarm_id`](../src/p2p/peer/connection.py#L154) (line 154) | `(self) → str` | Swarm identifier. |
| [`PeerConnection.chunk_count`](../src/p2p/peer/connection.py#L159) (line 159) | `(self) → int` | Total chunk count for this swarm. |
| [`PeerConnection.local_bitfield`](../src/p2p/peer/connection.py#L164) (line 164) | `(self) → Bitfield` | Local bitfield. |
| [`PeerConnection.pending_requests`](../src/p2p/peer/connection.py#L169) (line 169) | `(self) → frozenset[int]` | Outstanding chunk request indices sent to this peer. |
| [`PeerConnection.connect`](../src/p2p/peer/connection.py#L178) (line 178) | `async (cls, host: str, port: int, *, swarm_id: str, my_peer_id: str, my_listen_port: int, chunk_count: int, local_bitfield: Bitfield, connect_timeout: float=CONNECT_TIMEOUT_SEC, handshake_timeout: float=HANDSHAKE_TIMEOUT_SEC, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC, max_inflight: int=MAX_INFLIGHT_PER_PEER, auto_handshake: bool=True) → Self` | Establish an outbound TCP connection to a peer and optionally perform handshake. Explicit raises: ConnectionError. |
| [`PeerConnection.accept`](../src/p2p/peer/connection.py#L230) (line 230) | `(cls, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, swarm_id: str, my_peer_id: str, my_listen_port: int, chunk_count: int, local_bitfield: Bitfield, handshake_timeout: float=HANDSHAKE_TIMEOUT_SEC, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC, max_inflight: int=MAX_INFLIGHT_PER_PEER) → Self` | Wrap an accepted inbound TCP connection ready for handshake. |
| [`PeerConnection.perform_handshake`](../src/p2p/peer/connection.py#L264) (line 264) | `async (self) → None` | Execute two-way handshake and bitfield exchange. Explicit raises: ConnectionClosed, ProtocolError. |
| [`PeerConnection.receive_message`](../src/p2p/peer/connection.py#L363) (line 363) | `async (self) → Message` | Receive and process the next steady-state protocol message. Explicit raises: ConnectionClosed, ProtocolError. |
| [`PeerConnection.send_request`](../src/p2p/peer/connection.py#L447) (line 447) | `async (self, chunk_index: int) → None` | Send a REQUEST message for a chunk index. Explicit raises: ProtocolError. |
| [`PeerConnection.send_piece`](../src/p2p/peer/connection.py#L480) (line 480) | `async (self, chunk_index: int, data: bytes) → None` | Send a PIECE message delivering data for a chunk index. Explicit raises: ProtocolError. |
| [`PeerConnection.send_have`](../src/p2p/peer/connection.py#L501) (line 501) | `async (self, chunk_index: int) → None` | Send a HAVE broadcast message announcing newly verified chunk availability. Explicit raises: ProtocolError. |
| [`PeerConnection.has_chunk`](../src/p2p/peer/connection.py#L522) (line 522) | `(self, chunk_index: int) → bool` | Check if remote peer has chunk_index according to remote bitfield. Explicit raises: ProtocolError. |
| [`PeerConnection.cancel_pending_request`](../src/p2p/peer/connection.py#L534) (line 534) | `(self, chunk_index: int) → bool` | Release a pending request reservation without network I/O. |
| [`PeerConnection.update_local_bitfield`](../src/p2p/peer/connection.py#L544) (line 544) | `(self, bitfield: Bitfield) → None` | Update local bitfield representation. |
| [`PeerConnection.close`](../src/p2p/peer/connection.py#L553) (line 553) | `async (self) → None` | Close connection cleanly and release pending resources. |
| [`PeerConnection._close_writer`](../src/p2p/peer/connection.py#L571) (line 571) | `async (writer: asyncio.StreamWriter \| None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`PeerConnection._send_message`](../src/p2p/peer/connection.py#L583) (line 583) | `async (self, msg: Message) → None` | Serialize and send a message through the connection writer. Explicit raises: ConnectionClosed. |
| [`PeerConnection.__aenter__`](../src/p2p/peer/connection.py#L589) (line 589) | `async (self) → Self` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`PeerConnection.__aexit__`](../src/p2p/peer/connection.py#L592) (line 592) | `async (self, exc_type: type[BaseException] \| None, exc_val: BaseException \| None, exc_tb: Any) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/peer/downloader.py`

Async download worker for requesting and validating peer chunks.

Imports/dependencies: `__future__`, `asyncio`, `collections.abc`, `logging`, `math`, `p2p.config`, `p2p.peer.connection`, `p2p.peer.scheduler`, `p2p.protocol`, `p2p.storage.manager`, `time`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`DownloadError`](../src/p2p/peer/downloader.py#L38) (line 38) | `class: RuntimeError` | Base error for a swarm download that cannot complete. |
| [`NoAvailablePeersError`](../src/p2p/peer/downloader.py#L42) (line 42) | `class: DownloadError` | Raised when missing chunks are not available from any active peer. |
| [`DownloadWorker`](../src/p2p/peer/downloader.py#L46) (line 46) | `class` | Sequential chunk worker for one already-connected peer. |
| [`DownloadWorker.__init__`](../src/p2p/peer/downloader.py#L49) (line 49) | `(self, connection: PeerConnection, scheduler: DownloadScheduler, storage: StorageManager, *, max_retries: int=3, retry_delay: float=0.05, inbound_messages: asyncio.Queue[Message \| Exception] \| None=None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: TypeError, ValueError. |
| [`DownloadWorker.completed`](../src/p2p/peer/downloader.py#L87) (line 87) | `(self) → frozenset[int]` | Chunks successfully downloaded by this worker. |
| [`DownloadWorker.finish_chunk`](../src/p2p/peer/downloader.py#L91) (line 91) | `async (self, chunk_index: int) → None` | Mark a chunk complete only after StorageManager verified it. Explicit raises: ChunkIntegrityError, RuntimeError. |
| [`DownloadWorker._request_one`](../src/p2p/peer/downloader.py#L103) (line 103) | `async (self, chunk_index: int) → Piece` | Request a single chunk and return its received PIECE payload. Explicit raises: ProtocolError, queued_message. |
| [`DownloadWorker.fetch_next`](../src/p2p/peer/downloader.py#L136) (line 136) | `async (self) → int \| None` | Reserve and download the next chunk from the connected peer. Explicit raises: AssertionError, RuntimeError. |
| [`DownloadWorker.run`](../src/p2p/peer/downloader.py#L175) (line 175) | `async (self) → set[int]` | Download as many chunks as possible from the connected peer. |
| [`SwarmDownloader`](../src/p2p/peer/downloader.py#L188) (line 188) | `class` | Coordinate bounded parallel chunk downloads across connected peers. |
| [`SwarmDownloader.__init__`](../src/p2p/peer/downloader.py#L197) (line 197) | `(self, connections: Iterable[PeerConnection], scheduler: DownloadScheduler, storage: StorageManager, *, max_retries: int=3, retry_delay: float=0.05, max_peer_connections: int=MAX_PEER_CONNECTIONS, max_global_inflight: int=MAX_GLOBAL_INFLIGHT, availability_timeout: float=STALL_TIMEOUT_SEC, on_chunk_verified: Callable[[int], Awaitable[None]] \| None=None, advertise_chunks: bool=True) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: TypeError, ValueError. |
| [`SwarmDownloader.downloaded_from`](../src/p2p/peer/downloader.py#L281) (line 281) | `(self) → dict[str, int]` | Copy verified payload contributions, including retired connections. |
| [`SwarmDownloader.bytes_downloaded`](../src/p2p/peer/downloader.py#L293) (line 293) | `(self) → int` | Total verified payload bytes downloaded across all workers. |
| [`SwarmDownloader.total_retries`](../src/p2p/peer/downloader.py#L300) (line 300) | `(self) → int` | Total retry attempts made across all workers. |
| [`SwarmDownloader.chunk_hash_failures`](../src/p2p/peer/downloader.py#L305) (line 305) | `(self) → int` | Total chunk integrity/hash failures encountered. |
| [`SwarmDownloader.duration_seconds`](../src/p2p/peer/downloader.py#L312) (line 312) | `(self) → float` | Download duration in seconds measured via monotonic clock. |
| [`SwarmDownloader._register_connections`](../src/p2p/peer/downloader.py#L319) (line 319) | `(self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`SwarmDownloader._read_peer_messages`](../src/p2p/peer/downloader.py#L340) (line 340) | `async (self, peer_id: str, connection: PeerConnection) → None` | Own reads from a peer and dispatch updates to its download worker. |
| [`SwarmDownloader._start_readers`](../src/p2p/peer/downloader.py#L357) (line 357) | `(self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmDownloader._retire_peer`](../src/p2p/peer/downloader.py#L364) (line 364) | `async (self, peer_id: str) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmDownloader._broadcast_have`](../src/p2p/peer/downloader.py#L385) (line 385) | `async (self, chunk_index: int, source_peer_id: str) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmDownloader._download_from_peer`](../src/p2p/peer/downloader.py#L399) (line 399) | `async (self, peer_id: str) → int \| None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`SwarmDownloader._wait_for_peer_update`](../src/p2p/peer/downloader.py#L409) (line 409) | `async (self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: NoAvailablePeersError. |
| [`SwarmDownloader.run`](../src/p2p/peer/downloader.py#L424) (line 424) | `async (self) → set[int]` | Download available chunks in parallel, finalize storage, and close peers. Explicit raises: NoAvailablePeersError. |

### `src/p2p/peer/metrics.py`

Copied diagnostic snapshots; taking a snapshot never drives network work.

Imports/dependencies: `dataclasses`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ConnectionSnapshot`](../src/p2p/peer/metrics.py#L7) (line 7) | `class` | Structured type or domain exception; see related methods. Fields: peer_id: str \| None, direction: str, state: str, available_chunks: int \| None, pending_requests: int. |
| [`PeerSnapshot`](../src/p2p/peer/metrics.py#L16) (line 16) | `class` | Structured type or domain exception; see related methods. Fields: peer_id: str, swarm_id: str, host: str, port: int, online: bool, upload_enabled: bool, upload_rate_limit: float \| None, verified_chunks: int, verified_bytes: int, final_integrity: str, bytes_uploaded: int, bytes_downloaded: int, retries: int, chunk_hash_failures: int, duration_seconds: float, throughput_bytes_per_s: float, downloaded_from: dict[str, int], connections: tuple[ConnectionSnapshot, ...]. |

### `src/p2p/peer/rate_limiter.py`

Async token-bucket rate limiter for upload bandwidth control.

The limiter is shared across all connections of a single peer so the
aggregate upload rate is capped regardless of how many leechers are
downloading simultaneously.  An injectable monotonic clock supports
deterministic unit tests.

Imports/dependencies: `__future__`, `asyncio`, `collections.abc`, `math`, `time`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`TokenBucketRateLimiter`](../src/p2p/peer/rate_limiter.py#L18) (line 18) | `class` | Async token-bucket rate limiter. |
| [`TokenBucketRateLimiter.__init__`](../src/p2p/peer/rate_limiter.py#L35) (line 35) | `(self, rate_bytes_per_sec: float, *, burst_bytes: float \| None=None, clock: Callable[[], float] \| None=None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`TokenBucketRateLimiter.rate`](../src/p2p/peer/rate_limiter.py#L67) (line 67) | `(self) → float` | Sustained rate in bytes per second. |
| [`TokenBucketRateLimiter.burst`](../src/p2p/peer/rate_limiter.py#L72) (line 72) | `(self) → float` | Maximum bucket capacity in bytes. |
| [`TokenBucketRateLimiter._refill`](../src/p2p/peer/rate_limiter.py#L76) (line 76) | `(self) → None` | Add tokens for elapsed time since the last refill. |
| [`TokenBucketRateLimiter.acquire`](../src/p2p/peer/rate_limiter.py#L84) (line 84) | `async (self, num_bytes: int) → None` | Wait until *num_bytes* tokens are available, then consume them. Explicit raises: ValueError. |
| [`TokenBucketRateLimiter.available_tokens`](../src/p2p/peer/rate_limiter.py#L123) (line 123) | `(self) → float` | Current token count (without refilling — a snapshot). |

### `src/p2p/peer/scheduler.py`

Chunk selection and reservation logic for peer downloads.

Imports/dependencies: `__future__`, `collections.abc`, `enum`, `p2p.protocol`, `random`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ChunkState`](../src/p2p/peer/scheduler.py#L12) (line 12) | `class: StrEnum` | Download lifecycle state for a chunk. |
| [`DownloadScheduler`](../src/p2p/peer/scheduler.py#L23) (line 23) | `class` | Tracks which chunks are still needed, reserved, or already verified. |
| [`DownloadScheduler.__init__`](../src/p2p/peer/scheduler.py#L30) (line 30) | `(self, chunk_count: int, *, verified_chunks: Iterable[int] \| None=None, rng: random.Random \| None=None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`DownloadScheduler.chunk_count`](../src/p2p/peer/scheduler.py#L53) (line 53) | `(self) → int` | Total chunk count for the swarm. |
| [`DownloadScheduler.missing_chunks`](../src/p2p/peer/scheduler.py#L58) (line 58) | `(self) → frozenset[int]` | Return the set of chunks still missing. |
| [`DownloadScheduler.inflight_chunks`](../src/p2p/peer/scheduler.py#L65) (line 65) | `(self) → frozenset[int]` | Return the set of chunks currently in flight. |
| [`DownloadScheduler.verified_chunks`](../src/p2p/peer/scheduler.py#L70) (line 70) | `(self) → frozenset[int]` | Return the set of chunks already verified. |
| [`DownloadScheduler.is_complete`](../src/p2p/peer/scheduler.py#L77) (line 77) | `(self) → bool` | True when every chunk has been verified. |
| [`DownloadScheduler.state_for`](../src/p2p/peer/scheduler.py#L81) (line 81) | `(self, chunk_index: int) → ChunkState` | Return the current state for a single chunk. Explicit raises: ValueError. |
| [`DownloadScheduler.register_peer`](../src/p2p/peer/scheduler.py#L89) (line 89) | `(self, peer_id: str, bitfield: Bitfield \| None) → None` | Register or refresh a peer's available chunk set. Explicit raises: ValueError. |
| [`DownloadScheduler.update_peer_bitfield`](../src/p2p/peer/scheduler.py#L99) (line 99) | `(self, peer_id: str, bitfield: Bitfield \| None) → None` | Compatibility wrapper for peer-bitfield updates. |
| [`DownloadScheduler.update_peer_have`](../src/p2p/peer/scheduler.py#L103) (line 103) | `(self, peer_id: str, chunk_index: int) → None` | Record a HAVE broadcast from a peer. Explicit raises: ValueError. |
| [`DownloadScheduler.has_chunk`](../src/p2p/peer/scheduler.py#L111) (line 111) | `(self, peer_id: str, chunk_index: int) → bool` | Return whether the peer advertises the chunk. |
| [`DownloadScheduler.available_chunks_for`](../src/p2p/peer/scheduler.py#L117) (line 117) | `(self, peer_id: str) → frozenset[int]` | Chunks this peer advertises as available. |
| [`DownloadScheduler.available_missing_for`](../src/p2p/peer/scheduler.py#L121) (line 121) | `(self, peer_id: str) → frozenset[int]` | Missing chunks advertised by a peer and eligible for reservation. |
| [`DownloadScheduler.reserve_next`](../src/p2p/peer/scheduler.py#L129) (line 129) | `(self, peer_id: str) → int \| None` | Reserve the next missing chunk available from a peer and return it. |
| [`DownloadScheduler.reserve`](../src/p2p/peer/scheduler.py#L151) (line 151) | `(self, chunk_index: int, peer_id: str) → bool` | Reserve a specific chunk for a peer if it is still eligible. Explicit raises: ValueError. |
| [`DownloadScheduler._reserve`](../src/p2p/peer/scheduler.py#L164) (line 164) | `(self, chunk_index: int, peer_id: str) → None` | Internal helper that marks a chunk as in-flight. |
| [`DownloadScheduler.release`](../src/p2p/peer/scheduler.py#L169) (line 169) | `(self, chunk_index: int, peer_id: str \| None=None, *, failed: bool=False) → bool` | Release an in-flight chunk reservation. |
| [`DownloadScheduler.release_all`](../src/p2p/peer/scheduler.py#L194) (line 194) | `(self, peer_id: str) → list[int]` | Release all in-flight chunks assigned to a peer. |
| [`DownloadScheduler.unregister_peer`](../src/p2p/peer/scheduler.py#L203) (line 203) | `(self, peer_id: str) → list[int]` | Forget a peer and release any chunks reserved to it. |
| [`DownloadScheduler.mark_verified`](../src/p2p/peer/scheduler.py#L208) (line 208) | `(self, chunk_index: int, *, peer_id: str \| None=None) → bool` | Mark a chunk as verified after a valid PIECE payload passes validation. Explicit raises: ValueError. |
| [`DownloadScheduler.mark_missing`](../src/p2p/peer/scheduler.py#L228) (line 228) | `(self, chunk_index: int) → None` | Reset a chunk to missing if validation or transfer fails. Explicit raises: ValueError. |
| [`DownloadScheduler.complete_chunk`](../src/p2p/peer/scheduler.py#L237) (line 237) | `(self, chunk_index: int, *, peer_id: str \| None=None) → bool` | Alias for mark_verified used by downloader workers. |
| [`DownloadScheduler.__len__`](../src/p2p/peer/scheduler.py#L241) (line 241) | `(self) → int` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/peer/server.py`

Async TCP listener server for inbound peer connections.

Imports/dependencies: `__future__`, `asyncio`, `collections.abc`, `logging`, `p2p.config`, `p2p.peer.connection`, `p2p.protocol`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`PeerServer`](../src/p2p/peer/server.py#L25) (line 25) | `class` | Async TCP listener accepting incoming peer connections for a swarm. |
| [`PeerServer.__init__`](../src/p2p/peer/server.py#L28) (line 28) | `(self, host: str='127.0.0.1', port: int=0, *, swarm_id: str, my_peer_id: str, chunk_count: int, local_bitfield: Bitfield, on_connection: PeerConnectionHandler \| None=None, handshake_timeout: float=HANDSHAKE_TIMEOUT_SEC, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC, max_inflight: int=MAX_INFLIGHT_PER_PEER, max_connections: int=MAX_PEER_CONNECTIONS) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`PeerServer.is_running`](../src/p2p/peer/server.py#L71) (line 71) | `(self) → bool` | True if the server is active and listening. |
| [`PeerServer.listen_port`](../src/p2p/peer/server.py#L76) (line 76) | `(self) → int` | The actual bound port number. Explicit raises: RuntimeError. |
| [`PeerServer.active_connections`](../src/p2p/peer/server.py#L83) (line 83) | `(self) → frozenset[PeerConnection]` | Set of currently connected peers. |
| [`PeerServer.active_connection_count`](../src/p2p/peer/server.py#L88) (line 88) | `(self) → int` | Count of currently active connections. |
| [`PeerServer.update_local_bitfield`](../src/p2p/peer/server.py#L92) (line 92) | `(self, bitfield: Bitfield) → None` | Update the bitfield advertised to future incoming connections. |
| [`PeerServer.update_max_connections`](../src/p2p/peer/server.py#L97) (line 97) | `(self, max_connections: int) → None` | Adjust the inbound connection limit without dropping existing peers. Explicit raises: ValueError. |
| [`PeerServer.start`](../src/p2p/peer/server.py#L107) (line 107) | `async (self) → int` | Start the TCP listener server on host and port. Explicit raises: RuntimeError. |
| [`PeerServer.stop`](../src/p2p/peer/server.py#L136) (line 136) | `async (self) → None` | Stop the listener server and close all active connections cleanly. Explicit raises: ExceptionGroup. |
| [`PeerServer._handle_client`](../src/p2p/peer/server.py#L179) (line 179) | `async (self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) → None` | Handle an accepted incoming TCP socket connection. |
| [`PeerServer.__aenter__`](../src/p2p/peer/server.py#L235) (line 235) | `async (self) → Self` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`PeerServer.__aexit__`](../src/p2p/peer/server.py#L239) (line 239) | `async (self, exc_type: type[BaseException] \| None, exc_val: BaseException \| None, exc_tb: Any) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/protocol/__init__.py`

Wire framing, message protocol, and codec package.

Imports/dependencies: `p2p.protocol.codec`, `p2p.protocol.messages`. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

Public exports: `Bitfield`, `ConnectionClosed`, `Handshake`, `Have`, `Message`, `MessageType`, `Piece`, `ProtocolError`, `Request`, `decode_body`, `decode_frame`, `encode_frame`, `encode_message`, `read_frame`, `read_message`, `write_frame`, `write_message`.

### `src/p2p/protocol/codec.py`

Wire framing codec, serialization, and stream I/O for the P2P protocol.

Imports/dependencies: `__future__`, `asyncio`, `p2p.config`, `p2p.protocol.messages`, `struct`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`encode_frame`](../src/p2p/protocol/codec.py#L31) (line 31) | `(msg_type: int, payload: bytes) → bytes` | Encode a wire frame from a message type and payload. Explicit raises: ProtocolError. |
| [`decode_body`](../src/p2p/protocol/codec.py#L58) (line 58) | `(body: bytes) → Message` | Decode a message body (type byte + payload) into a typed Message. Explicit raises: ProtocolError. |
| [`decode_frame`](../src/p2p/protocol/codec.py#L128) (line 128) | `(frame: bytes) → Message` | Decode an entire wire frame (including 4-byte length prefix). Explicit raises: ProtocolError. |
| [`encode_message`](../src/p2p/protocol/codec.py#L158) (line 158) | `(msg: Message) → bytes` | Serialize a high-level Message into a complete wire frame. Explicit raises: ProtocolError. |
| [`read_frame`](../src/p2p/protocol/codec.py#L183) (line 183) | `async (reader: asyncio.StreamReader, *, max_body: int=MAX_FRAME_SIZE, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC) → bytes` | Read a single length-prefixed frame body from an async stream. Explicit raises: ConnectionClosed, ProtocolError. |
| [`write_frame`](../src/p2p/protocol/codec.py#L246) (line 246) | `async (writer: asyncio.StreamWriter, frame: bytes, *, lock: asyncio.Lock \| None=None) → None` | Write an encoded frame to an async stream and drain backpressure. Explicit raises: ConnectionClosed, ProtocolError. |
| [`write_frame._do_write`](../src/p2p/protocol/codec.py#L267) (line 267) | `async () → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ConnectionClosed. |
| [`read_message`](../src/p2p/protocol/codec.py#L281) (line 281) | `async (reader: asyncio.StreamReader, *, max_body: int=MAX_FRAME_SIZE, idle_timeout: float=IDLE_TIMEOUT_SEC, stall_timeout: float=STALL_TIMEOUT_SEC) → Message` | Read and decode a complete message from an async stream. |
| [`write_message`](../src/p2p/protocol/codec.py#L295) (line 295) | `async (writer: asyncio.StreamWriter, msg: Message, *, lock: asyncio.Lock \| None=None) → None` | Encode and write a Message to an async stream. |

### `src/p2p/protocol/messages.py`

Protocol message definitions, type codes, and exception types.

Imports/dependencies: `__future__`, `collections.abc`, `dataclasses`, `enum`, `json`, `math`, `p2p.config`, `re`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ProtocolError`](../src/p2p/protocol/messages.py#L23) (line 23) | `class: Exception` | Raised when a remote peer violates the wire protocol. |
| [`ConnectionClosed`](../src/p2p/protocol/messages.py#L27) (line 27) | `class: Exception` | Raised when a connection is closed cleanly on a frame boundary. |
| [`MessageType`](../src/p2p/protocol/messages.py#L31) (line 31) | `class: enum.IntEnum` | Application-layer message type codes. |
| [`Handshake`](../src/p2p/protocol/messages.py#L42) (line 42) | `class` | Handshake payload exchanged upon connection establishment. Fields: version: int, peer_id: str, swarm_id: str, listen_port: int. |
| [`Handshake.validate`](../src/p2p/protocol/messages.py#L50) (line 50) | `(self) → None` | Validate handshake fields against protocol requirements. Explicit raises: ProtocolError. |
| [`Handshake.to_json_bytes`](../src/p2p/protocol/messages.py#L87) (line 87) | `(self) → bytes` | Serialize handshake to UTF-8 JSON bytes. Explicit raises: ProtocolError. |
| [`Handshake.from_json_bytes`](../src/p2p/protocol/messages.py#L106) (line 106) | `(cls, data: bytes) → Self` | Parse and validate handshake from UTF-8 JSON bytes. Explicit raises: ProtocolError. |
| [`Bitfield`](../src/p2p/protocol/messages.py#L143) (line 143) | `class` | Bitmask indicating chunk availability. Fields: bitfield: bytes. |
| [`Bitfield.validate`](../src/p2p/protocol/messages.py#L148) (line 148) | `(self) → None` | Validate basic bitfield invariants. Explicit raises: ProtocolError. |
| [`Bitfield.has_chunk`](../src/p2p/protocol/messages.py#L155) (line 155) | `(self, chunk_index: int) → bool` | Check if chunk at chunk_index is indicated as available. Explicit raises: ProtocolError. |
| [`Bitfield.with_chunk`](../src/p2p/protocol/messages.py#L167) (line 167) | `(self, chunk_index: int) → Self` | Return a new Bitfield with chunk_index marked as present. Explicit raises: ProtocolError. |
| [`Bitfield.validate_for_swarm`](../src/p2p/protocol/messages.py#L184) (line 184) | `(self, chunk_count: int) → None` | Validate bitfield length and spare bits against expected chunk count. Explicit raises: ProtocolError. |
| [`Bitfield.to_indices`](../src/p2p/protocol/messages.py#L216) (line 216) | `(self, chunk_count: int \| None=None) → set[int]` | Return the set of chunk indices marked present. |
| [`Bitfield.from_indices`](../src/p2p/protocol/messages.py#L232) (line 232) | `(cls, indices: Iterable[int], chunk_count: int) → Self` | Construct a Bitfield from an iterable of chunk indices for a known chunk count. Explicit raises: ProtocolError. |
| [`Request`](../src/p2p/protocol/messages.py#L253) (line 253) | `class` | Request for a specific chunk index. Fields: chunk_index: int. |
| [`Request.validate`](../src/p2p/protocol/messages.py#L258) (line 258) | `(self) → None` | Validate request fields. Explicit raises: ProtocolError. |
| [`Piece`](../src/p2p/protocol/messages.py#L269) (line 269) | `class` | Delivered chunk data for a specific chunk index. Fields: chunk_index: int, data: bytes. |
| [`Piece.validate`](../src/p2p/protocol/messages.py#L275) (line 275) | `(self) → None` | Validate piece fields. Explicit raises: ProtocolError. |
| [`Have`](../src/p2p/protocol/messages.py#L294) (line 294) | `class` | Announcement that a verified chunk is now available. Fields: chunk_index: int. |
| [`Have.validate`](../src/p2p/protocol/messages.py#L299) (line 299) | `(self) → None` | Validate have fields. Explicit raises: ProtocolError. |

### `src/p2p/storage/__init__.py`

Storage management, manifest handling, and hash verification package.

Imports/dependencies: `p2p.storage.manager`, `p2p.storage.manifest`. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

Public exports: `ChunkDescriptor`, `ChunkIntegrityError`, `FileIntegrityError`, `FileManifest`, `IncompleteFileError`, `ManifestError`, `StorageManager`, `build_manifest`, `compute_swarm_id`, `load_manifest`, `validate_manifest`, `validate_safe_filename`, `write_manifest`.

### `src/p2p/storage/manager.py`

Verified chunk persistence and atomic file finalization.

Imports/dependencies: `__future__`, `hashlib`, `hmac`, `os`, `p2p.storage.manifest`, `pathlib`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ChunkIntegrityError`](../src/p2p/storage/manager.py#L13) (line 13) | `class: ValueError` | Raised when chunk data does not match its validated manifest entry. |
| [`IncompleteFileError`](../src/p2p/storage/manager.py#L17) (line 17) | `class: ValueError` | Raised when finalization is attempted before all chunks are verified. |
| [`FileIntegrityError`](../src/p2p/storage/manager.py#L21) (line 21) | `class: ValueError` | Raised when the reconstructed file does not match its manifest digest. |
| [`validate_safe_filename`](../src/p2p/storage/manager.py#L25) (line 25) | `(download_dir: Path, file_name: str) → Path` | Resolve a safe base filename beneath the requested download directory. Explicit raises: ValueError. |
| [`StorageManager`](../src/p2p/storage/manager.py#L38) (line 38) | `class` | Own a single download's temporary file and verified chunk state. |
| [`StorageManager.__init__`](../src/p2p/storage/manager.py#L41) (line 41) | `(self, manifest: object, download_dir: Path) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`StorageManager.final_integrity`](../src/p2p/storage/manager.py#L58) (line 58) | `(self) → str` | Distinguish a pending whole-file check from an observed hash failure. |
| [`StorageManager.verified_chunks`](../src/p2p/storage/manager.py#L65) (line 65) | `(self) → frozenset[int]` | Return an immutable snapshot of verified chunk indices. |
| [`StorageManager.write_chunk`](../src/p2p/storage/manager.py#L69) (line 69) | `(self, index: int, data: bytes) → bool` | Verify and persist one chunk; return False for an already verified index. Explicit raises: ChunkIntegrityError, OSError, RuntimeError. |
| [`StorageManager.finalize`](../src/p2p/storage/manager.py#L103) (line 103) | `(self) → Path` | Verify the complete temporary file and atomically publish it. Explicit raises: FileIntegrityError, IncompleteFileError, RuntimeError. |

### `src/p2p/storage/manifest.py`

Manifest creation, validation, parsing, and swarm identity.

Imports/dependencies: `__future__`, `hashlib`, `json`, `os`, `p2p.config`, `pathlib`, `re`, `tempfile`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`ChunkDescriptor`](../src/p2p/storage/manifest.py#L39) (line 39) | `class: TypedDict` | Structured type or domain exception; see related methods. Fields: index: int, length: int, sha256: str. |
| [`FileManifest`](../src/p2p/storage/manifest.py#L45) (line 45) | `class: TypedDict` | Structured type or domain exception; see related methods. Fields: manifest_version: int, file_name: str, file_size: int, chunk_size: int, chunk_count: int, file_sha256: str, chunks: list[ChunkDescriptor]. |
| [`ManifestError`](../src/p2p/storage/manifest.py#L55) (line 55) | `class: ValueError` | Raised when a manifest is malformed or violates the v1 schema. |
| [`_validate_file_name`](../src/p2p/storage/manifest.py#L59) (line 59) | `(file_name: object) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ManifestError. |
| [`_is_sha256_digest`](../src/p2p/storage/manifest.py#L74) (line 74) | `(value: object) → bool` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`validate_manifest`](../src/p2p/storage/manifest.py#L78) (line 78) | `(manifest: object) → FileManifest` | Validate and return a v1 manifest dictionary. Explicit raises: ManifestError. |
| [`_canonical_json`](../src/p2p/storage/manifest.py#L153) (line 153) | `(manifest: FileManifest) → bytes` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`compute_swarm_id`](../src/p2p/storage/manifest.py#L157) (line 157) | `(manifest: object) → str` | Return the SHA-256 of the validated manifest's canonical JSON bytes. |
| [`build_manifest`](../src/p2p/storage/manifest.py#L163) (line 163) | `(file_path: Path, chunk_size: int=DEFAULT_CHUNK_SIZE) → FileManifest` | Build a manifest by hashing a file in bounded-size chunks. Explicit raises: ManifestError. |
| [`_reject_duplicate_keys`](../src/p2p/storage/manifest.py#L209) (line 209) | `(pairs: list[tuple[str, object]]) → dict[str, object]` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ManifestError. |
| [`load_manifest`](../src/p2p/storage/manifest.py#L218) (line 218) | `(manifest_path: Path) → FileManifest` | Read and validate a JSON manifest without loading oversized input. Explicit raises: ManifestError. |
| [`write_manifest`](../src/p2p/storage/manifest.py#L231) (line 231) | `(manifest: object, manifest_path: Path) → None` | Validate and atomically write a manifest as UTF-8 JSON. |

### `src/p2p/tracker/__init__.py`

Tracker HTTP control plane package.

Imports/dependencies: none. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

### `src/p2p/tracker/models.py`

Pydantic models and request/response schemas for the Tracker HTTP control plane.

Imports/dependencies: `__future__`, `enum`, `ipaddress`, `p2p.config`, `p2p.protocol.messages`, `pydantic`, `re`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`_is_valid_ip`](../src/p2p/tracker/models.py#L20) (line 20) | `(host: str) → bool` | Check if host is a valid IPv4 or IPv6 address (including bracketed IPv6). |
| [`_is_valid_rfc1123_hostname`](../src/p2p/tracker/models.py#L30) (line 30) | `(host: str) → bool` | Check if host conforms to RFC 1123 DNS hostname syntax. |
| [`AnnounceEvent`](../src/p2p/tracker/models.py#L46) (line 46) | `class: enum.StrEnum` | Lifecycle events sent by peers in tracker announcements. |
| [`AnnounceRequest`](../src/p2p/tracker/models.py#L55) (line 55) | `class: BaseModel` | Peer announcement payload sent via POST /announce. Fields: swarm_id: str, peer_id: str, host: str, port: int, event: AnnounceEvent, is_seeder: bool. |
| [`AnnounceRequest.validate_swarm_id`](../src/p2p/tracker/models.py#L69) (line 69) | `(cls, value: object) → str` | Validate swarm ID as exactly 64 lowercase hexadecimal characters. Explicit raises: ValueError. |
| [`AnnounceRequest.validate_peer_id`](../src/p2p/tracker/models.py#L79) (line 79) | `(cls, value: object) → str` | Validate peer ID as 1..64 safe characters. Explicit raises: ValueError. |
| [`AnnounceRequest.validate_host`](../src/p2p/tracker/models.py#L91) (line 91) | `(cls, value: object) → str` | Validate advertised host as a valid IPv4, IPv6, or RFC 1123 hostname. Explicit raises: ValueError. |
| [`AnnounceRequest.validate_port`](../src/p2p/tracker/models.py#L105) (line 105) | `(cls, value: object) → int` | Validate listening port is an integer in 1..65535. Explicit raises: ValueError. |
| [`AnnounceRequest.validate_is_seeder`](../src/p2p/tracker/models.py#L115) (line 115) | `(cls, value: object) → bool` | Validate is_seeder is strictly a boolean. Explicit raises: ValueError. |
| [`PeerInfo`](../src/p2p/tracker/models.py#L122) (line 122) | `class: BaseModel` | Peer connection descriptor returned in announcement responses. Fields: peer_id: str, host: str, port: int. |
| [`PeerInfo.validate_peer_id`](../src/p2p/tracker/models.py#L133) (line 133) | `(cls, value: object) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`PeerInfo.validate_host`](../src/p2p/tracker/models.py#L140) (line 140) | `(cls, value: object) → str` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`PeerInfo.validate_port`](../src/p2p/tracker/models.py#L151) (line 151) | `(cls, value: object) → int` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`AnnounceResponse`](../src/p2p/tracker/models.py#L157) (line 157) | `class: BaseModel` | Tracker response to a peer announcement. Fields: interval: int, peers: list[PeerInfo]. |
| [`SwarmPeerInfo`](../src/p2p/tracker/models.py#L164) (line 164) | `class: BaseModel` | Detailed peer descriptor returned by swarm inspection endpoints. Fields: peer_id: str, host: str, port: int, last_seen: float, is_seeder: bool. |
| [`SwarmPeersResponse`](../src/p2p/tracker/models.py#L174) (line 174) | `class: BaseModel` | Response returned by GET /swarms/{swarm_id}/peers. Fields: swarm_id: str, peers: list[SwarmPeerInfo]. |

### `src/p2p/tracker/registry.py`

In-memory swarm registry, peer management, and injectable clock for the tracker.

Imports/dependencies: `__future__`, `dataclasses`, `p2p.config`, `p2p.tracker.models`, `random`, `time`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`Clock`](../src/p2p/tracker/registry.py#L24) (line 24) | `class: Protocol` | Protocol for monotonic time sources to enable deterministic clock injection. |
| [`Clock.now`](../src/p2p/tracker/registry.py#L27) (line 27) | `(self) → float` | Return the current timestamp in monotonic seconds. |
| [`MonotonicClock`](../src/p2p/tracker/registry.py#L32) (line 32) | `class` | Default clock implementation using system monotonic time. |
| [`MonotonicClock.now`](../src/p2p/tracker/registry.py#L35) (line 35) | `(self) → float` | Return system monotonic time in seconds. |
| [`PeerRecord`](../src/p2p/tracker/registry.py#L41) (line 41) | `class` | Internal tracker record representing an active peer in a swarm. Fields: peer_id: str, host: str, port: int, last_seen: float, is_seeder: bool. |
| [`SwarmRegistry`](../src/p2p/tracker/registry.py#L51) (line 51) | `class` | In-memory swarm registry tracking active peers, heartbeats, and stale expiry. |
| [`SwarmRegistry.__init__`](../src/p2p/tracker/registry.py#L58) (line 58) | `(self, clock: Clock \| None=None, *, heartbeat_interval: int=DEFAULT_HEARTBEAT_INTERVAL_SEC, expiry_multiplier: int=STALE_PEER_EXPIRY_MULTIPLIER, max_peers_per_announce: int=MAX_PEERS_PER_ANNOUNCE, rng: random.Random \| None=None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`SwarmRegistry.heartbeat_interval`](../src/p2p/tracker/registry.py#L96) (line 96) | `(self) → int` | Interval in seconds peers should wait between regular announcements. |
| [`SwarmRegistry.expiry_multiplier`](../src/p2p/tracker/registry.py#L101) (line 101) | `(self) → int` | Multiplier applied to heartbeat_interval before evicting a stale peer. |
| [`SwarmRegistry.expiry_timeout`](../src/p2p/tracker/registry.py#L106) (line 106) | `(self) → float` | Duration in seconds after last_seen before a peer is considered stale. |
| [`SwarmRegistry.max_peers_per_announce`](../src/p2p/tracker/registry.py#L111) (line 111) | `(self) → int` | Maximum number of peer records returned in an announce response. |
| [`SwarmRegistry.announce`](../src/p2p/tracker/registry.py#L115) (line 115) | `(self, request: AnnounceRequest) → AnnounceResponse` | Process a peer announcement and return an active peer list. |
| [`SwarmRegistry.evict_stale`](../src/p2p/tracker/registry.py#L163) (line 163) | `(self, swarm_id: str \| None=None) → int` | Evict peers whose inactivity exceeds the expiry timeout. |
| [`SwarmRegistry.get_swarm_peers`](../src/p2p/tracker/registry.py#L193) (line 193) | `(self, swarm_id: str) → list[SwarmPeerInfo]` | Return diagnostic descriptors for all active peers in a swarm. |
| [`SwarmRegistry.get_peer`](../src/p2p/tracker/registry.py#L214) (line 214) | `(self, swarm_id: str, peer_id: str) → PeerRecord \| None` | Look up an active peer record without modifying state. |
| [`SwarmRegistry.peer_count`](../src/p2p/tracker/registry.py#L221) (line 221) | `(self, swarm_id: str \| None=None) → int` | Return the count of active peers in a specific swarm or across all swarms. |
| [`SwarmRegistry.active_swarms`](../src/p2p/tracker/registry.py#L228) (line 228) | `(self) → list[str]` | Return a list of all currently tracked swarm IDs. |

### `src/p2p/tracker/server.py`

FastAPI application for the Tracker HTTP control plane.

Imports/dependencies: `__future__`, `fastapi`, `p2p.protocol.messages`, `p2p.tracker.models`, `p2p.tracker.registry`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`get_registry`](../src/p2p/tracker/server.py#L20) (line 20) | `() → SwarmRegistry` | Dependency provider returning the active SwarmRegistry instance. |
| [`health_check`](../src/p2p/tracker/server.py#L33) (line 33) | `() → dict[str, Any]` | Basic health check endpoint returning server status. |
| [`announce`](../src/p2p/tracker/server.py#L39) (line 39) | `async (request: AnnounceRequest, registry: Annotated[SwarmRegistry, Depends(get_registry)]) → AnnounceResponse` | Process a peer announcement and return active peers in the swarm. |
| [`list_swarms`](../src/p2p/tracker/server.py#L48) (line 48) | `async (registry: Annotated[SwarmRegistry, Depends(get_registry)]) → list[SwarmPeersResponse]` | Read active membership across swarms, applying normal lazy expiry. |
| [`get_swarm_peers`](../src/p2p/tracker/server.py#L64) (line 64) | `async (swarm_id: Annotated[str, Path(pattern=HEX_64_PATTERN.pattern)], registry: Annotated[SwarmRegistry, Depends(get_registry)]) → SwarmPeersResponse` | Return active peers for the requested swarm, or empty list if unknown. |

### `src/p2p/web/__init__.py`

Local-only web control console for the existing P2P engine.

Imports/dependencies: none. Refer to the execution chains for callers and collaborating components.

Package marker/re-export module; no separate class/function definitions.

### `src/p2p/web/__main__.py`

Run independently of the unchanged p2p CLI: python -m p2p.web.

Imports/dependencies: `argparse`, `p2p.web.app`, `pathlib`, `uvicorn`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`main`](../src/p2p/web/__main__.py#L11) (line 11) | `() → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/web/app.py`

Local HTTP UI; file distribution continues through peer TCP sockets.

Imports/dependencies: `__future__`, `asyncio`, `collections.abc`, `contextlib`, `fastapi`, `fastapi.responses`, `fastapi.staticfiles`, `httpx`, `json`, `p2p.config`, `p2p.tracker.models`, `p2p.web.experiments`, `p2p.web.service`, `pathlib`, `pydantic`, `starlette.middleware.trustedhost`, `typing`, `urllib.parse`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`tracker_json`](../src/p2p/web/app.py#L32) (line 32) | `async (client: httpx.AsyncClient, url: str) → Any` | Bound response bytes before parsing untrusted tracker JSON. Explicit raises: ValueError. |
| [`create_app`](../src/p2p/web/app.py#L44) (line 44) | `(workspace: Path=Path('downloads/web-console'), tracker_url: str='http://127.0.0.1:8000', *, tracker_transport: httpx.AsyncBaseTransport \| None=None, benchmark_csv: Path \| None=None) → FastAPI` | Create an isolated console. Only startup configuration selects local paths. Explicit raises: HTTPException, ValueError. |
| [`create_app.lifespan`](../src/p2p/web/app.py#L61) (line 61) | `async (app: FastAPI) → AsyncIterator[None]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`create_app.local_guard`](../src/p2p/web/app.py#L78) (line 78) | `async (request: Request, call_next: Any) → Response` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`create_app.index`](../src/p2p/web/app.py#L100) (line 100) | `async () → FileResponse` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`create_app.state`](../src/p2p/web/app.py#L104) (line 104) | `async (request: Request) → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`create_app.import_asset`](../src/p2p/web/app.py#L132) (line 132) | `async (request: Request, name: str, manifest_only: bool=False) → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`create_app.manifest`](../src/p2p/web/app.py#L139) (line 139) | `async (asset_id: str) → FileResponse` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`create_app.start`](../src/p2p/web/app.py#L148) (line 148) | `async (request: Request) → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`create_app.stop`](../src/p2p/web/app.py#L162) (line 162) | `async (transfer_id: str) → dict[str, str]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`create_app.output`](../src/p2p/web/app.py#L167) (line 167) | `async (transfer_id: str) → FileResponse` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`create_app.experiments`](../src/p2p/web/app.py#L176) (line 176) | `async () → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

### `src/p2p/web/experiments.py`

Read recorded trials through the existing harness's validation and analysis.

Imports/dependencies: `dataclasses`, `pathlib`, `typing`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`read_experiments`](../src/p2p/web/experiments.py#L8) (line 8) | `(csv_path: Path) → dict[str, Any]` | No experiment execution or fallback sample data. |

### `src/p2p/web/service.py`

Bounded asset storage and ownership of console peer tasks.

Imports/dependencies: `__future__`, `asyncio`, `dataclasses`, `fastapi`, `httpx`, `logging`, `p2p.config`, `p2p.peer.client`, `p2p.storage.manager`, `p2p.storage.manifest`, `pathlib`, `pydantic`, `typing`, `uuid`. Refer to the execution chains for callers and collaborating components.

| Definition | Parameters → return | Responsibility / explicit errors |
|---|---|---|
| [`StartTransfer`](../src/p2p/web/service.py#L40) (line 40) | `class: BaseModel` | Structured type or domain exception; see related methods. Fields: asset_id: str, kind: Literal['seed', 'download'], upload_rate_limit: float \| None, download_only: bool. |
| [`Asset`](../src/p2p/web/service.py#L50) (line 50) | `class` | Structured type or domain exception; see related methods. Fields: id: str, manifest: FileManifest, manifest_path: Path, source: Path \| None, swarm_id: str. |
| [`Asset.describe`](../src/p2p/web/service.py#L57) (line 57) | `(self) → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`Transfer`](../src/p2p/web/service.py#L71) (line 71) | `class` | Structured type or domain exception; see related methods. Fields: id: str, asset: Asset, options: StartTransfer, state: str, error: str \| None, peer: SwarmPeer \| None, task: asyncio.Task[None] \| None, stop_task: asyncio.Task[None] \| None, output: Path \| None. |
| [`Transfer.describe`](../src/p2p/web/service.py#L82) (line 82) | `(self) → dict[str, Any]` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`finish_disk_task`](../src/p2p/web/service.py#L100) (line 100) | `async (task: asyncio.Task[T]) → T` | Join thread work even on cancellation, before a caller cleans its files. |
| [`Console`](../src/p2p/web/service.py#L109) (line 109) | `class` | Own imported assets, peer lifecycles and cleanup on one event loop. |
| [`Console.__init__`](../src/p2p/web/service.py#L112) (line 112) | `(self, workspace: Path, tracker_url: str, tracker_transport: httpx.AsyncBaseTransport \| None=None) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`Console._directory`](../src/p2p/web/service.py#L126) (line 126) | `(self, relative: Path) → Path` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: ValueError. |
| [`Console.import_asset`](../src/p2p/web/service.py#L134) (line 134) | `async (self, request: Request, name: str, manifest_only: bool) → Asset` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`Console.start`](../src/p2p/web/service.py#L191) (line 191) | `(self, options: StartTransfer) → Transfer` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`Console._run`](../src/p2p/web/service.py#L211) (line 211) | `async (self, transfer: Transfer) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`Console.stop`](../src/p2p/web/service.py#L253) (line 253) | `async (self, transfer_id: str) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. Explicit raises: HTTPException. |
| [`Console._stop_transfer`](../src/p2p/web/service.py#L263) (line 263) | `async (self, transfer: Transfer) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |
| [`Console.close`](../src/p2p/web/service.py#L271) (line 271) | `async (self) → None` | Internal helper in its enclosing lifecycle or route; see execution flow above. |

## Frontend and assets

`src/p2p/web/static/index.html` contains the four direct `main > section` routes and all forms/DOM hooks. Its IDs are API consumers' rendering hooks, not backend resources. `style.css` provides local font faces, colors, sidebar/mobile wrapping navigation, semantic state styling, native details, tables with contained scrolling, focus and reduced-motion rules. `favicon.svg` and `fonts/*.woff2` are local visual assets; OFL text files and `sources.json` supply license/provenance. `pyproject.toml` includes them as package data. No frontend framework/build system is involved.

### JavaScript named functions

All functions below live in `src/p2p/web/static/app.js`. API, DOM and event details are explained in handbook Chapter 13. Anonymous submit/click handlers are listed separately after this table.

| Function/definition line | Parameters | Responsibility |
|---|---|---|
| [`el`](../src/p2p/web/static/app.js#L12) (12) | `tag, text, className` | Create element using textContent; avoid remote HTML injection. |
| [`bytes`](../src/p2p/web/static/app.js#L18) (18) | `value` | Format B/KiB/MiB or explicit Unavailable. |
| [`status`](../src/p2p/web/static/app.js#L24) (24) | `value) { return el("span", value, `state state-${value}`` | Create text-labeled state pill. |
| [`link`](../src/p2p/web/static/app.js#L25) (25) | `label, url) { const a = el("a", label` | Create actual anchor for artifact exports. |
| [`cell`](../src/p2p/web/static/app.js#L26) (26) | `row, content, className` | Append text/Node table cell. |
| [`empty`](../src/p2p/web/static/app.js#L31) (31) | `target, message, columns` | Render explicit empty/unavailable state. |
| [`table`](../src/p2p/web/static/app.js#L37) (37) | `headers, rows, focusKey` | Build semantic table in keyboard-accessible scrolling region. |
| [`definition`](../src/p2p/web/static/app.js#L47) (47) | `list, label, value` | Append label/value pair to definition list. |
| [`progress`](../src/p2p/web/static/app.js#L50) (50) | `transfer` | Render native progress from exact verified bytes/counts. |
| [`api`](../src/p2p/web/static/app.js#L59) (59) | `url, options = {}` | Fetch same-origin JSON; action header, deadlines and HTTP error extraction. |
| [`showError`](../src/p2p/web/static/app.js#L71) (71) | `error) { $("error").textContent = error.message; $("error"` | Display error message in global alert. |
| [`syncOptions`](../src/p2p/web/static/app.js#L72) (72) | `` | Enforce source/operation/baseline/cap/start enablement. |
| [`renderAssets`](../src/p2p/web/static/app.js#L81) (81) | `` | Render catalog and export links, preserve selection. |
| [`renderDashboard`](../src/p2p/web/static/app.js#L101) (101) | `` | Tracker counts, local totals and transfer/integrity rows. |
| [`renderTransfers`](../src/p2p/web/static/app.js#L125) (125) | `` | Peer metrics, state/errors, Stop and verified-output controls. |
| [`renderNetwork`](../src/p2p/web/static/app.js#L150) (150) | `` | Tracker membership, selected local connections and positive source bytes. |
| [`render`](../src/p2p/web/static/app.js#L197) (197) | `` | Run live renderers and restore keyed focus/horizontal scroll. |
| [`refresh`](../src/p2p/web/static/app.js#L207) (207) | `` | Coalesce state requests; render success or label stale retained snapshot. |
| [`refreshAfterAction`](../src/p2p/web/static/app.js#L221) (221) | `` | Join pending refresh then request a current snapshot. |
| [`action`](../src/p2p/web/static/app.js#L225) (225) | `work` | Guard concurrent mutation actions and refresh after outcome. |
| [`setupUpload`](../src/p2p/web/static/app.js#L231) (231) | `form, input, feedback, manifestOnly` | Bind native file submit; size guard, raw upload, feedback and selection. |
| [`svgNode`](../src/p2p/web/static/app.js#L248) (248) | `tag, attributes, text` | Construct SVG element/attributes/text with DOM APIs. |
| [`chart`](../src/p2p/web/static/app.js#L253) (253) | `id, summaries, metric, divisor, unit` | Plot existing N=1,2,4,8 summaries with mean/sample-SD and mode styles. |
| [`loadExperiments`](../src/p2p/web/static/app.js#L281) (281) | `` | Read recorded summaries/audit; render table/charts/exclusions or unavailable. |
| [`navigate`](../src/p2p/web/static/app.js#L308) (308) | `` | Resolve hash route, aria-current and lazy experiment load. |

The `$` arrow helper resolves DOM IDs. Event handlers bind Refresh, Reload results, selected network peer, asset/kind/baseline changes, both import forms, Start peer JSON submission, dynamic Stop buttons, hash navigation and the skip-to-content focus action. Boot calls navigate/refresh and installs the 1000ms non-overlapping state polling cadence. The advanced settings element itself is outside regenerated DOM, so its disclosure state persists.

### UI request map

| Method/path | Browser function | Server route inside `create_app` → owner |
|---|---|---|
| GET `/` and `/static/*` | Browser load | index / StaticFiles; local HTML/CSS/JS/font assets |
| GET `/api/state` | refresh | state → tracker_json + Console catalogs + descriptions/snapshot |
| POST `/api/assets?name=...&manifest_only=...` | setupUpload | import_asset → Console.import_asset |
| GET `/api/assets/{id}/manifest` | Export anchor | manifest → FileResponse of validated manifest |
| POST `/api/transfers` | peer-form handler | start → strict StartTransfer → Console.start |
| POST `/api/transfers/{id}/stop` | dynamic button/action | stop → Console.stop |
| GET `/api/transfers/{id}/file` | Export anchor | output → output gate + FileResponse |
| GET `/api/experiments` | loadExperiments | experiments → read_experiments → bench.analysis |

## Configuration, tests and documentation

| File/group | Role and connections |
|---|---|
| `pyproject.toml` | Python >=3.12; runtime FastAPI/Uvicorn/HTTPX; development pytest/asyncio/cov/Ruff/mypy/Matplotlib; installed CLI; static package data; strict test/type/lint configuration |
| `requirements.txt` | Existing teammate development dependencies plus editable local package; no new dependency in handbook task |
| `.gitignore` | Excludes part files, downloads/output, caches, environments and regenerated plots; explicitly retains the raw experiment CSV |
| `bench/results/experiments.csv` | Versioned 180 client rows/48 trials; current schema from CSV_FIELDNAMES; no hand-edited/fabricated measurements |
| `bench/plots/` | Ignored derived plots, summary and audit regenerated by plotter; .gitkeep retains directory |
| `tests/unit/` | Message/storage/scheduler/registry/limiter/CLI/peer/analysis/console worker checks; some focused socket tests |
| `tests/integration/` | Real loopback peer/download faults, tracker/console APIs, baseline and tiny runner sweeps |
| `tests/e2e/test_full_transfer.py` | RecordingTrackerApp plus three concurrent clients in both modes and staged completed-peer relay |
| `tests/e2e/test_web_http_transfer.py` | Spawned real HTTP tracker/console process fixtures and TCP transfer/baseline/relay, with graceful cleanup assertions |
| `tests/helpers/clock.py` | Shared FakeClock now/advance/set for deterministic expiry tests |
| `tests/browser/console.mjs` | Existing Chrome DevTools workflow harness; current handbook attempts stop on a stale-payload DOM assertion, documented in coverage checklist |
| `docs/protocol.md` | Wire/state spec; actual codec/connection authoritative for exact parsing |
| `docs/manifest-format.md`, `manifest.md` | Manifest schema/integrity; summary sketch is abbreviated and not a valid complete multi-chunk input |
| `docs/architecture.md`, `web-ui.md`, `cli.md` | Current module/lifecycle/API usage |
| `docs/experiments.md`, `course-report.md`, `demo.md` | Method, frozen measurement report and prior CLI demo; report snapshot predates optional frontend |
| `docs/testing.md`, `project-status.md` | Historical/current verification and limitations; dates/commands distinguish evidence snapshots |
| `docs/adr/0001..0009` | Stack, framing, manifest/storage, scheduling, lifecycle, baseline, limiter, runner and console decisions |
| `DESIGN.md`, `DESIGN_SYSTEM.md`, `PRODUCT.md` | Current visual authority and product context; historical design/audit docs retain older states |
| `context/PROJECT_CONTEXT.md` | Original course context and goals; not proof every optional feature is implemented |
| `AGENTS.md`, `.agents/skills/`, `docs/ai-tooling.md`, `skills-lock.json` | Contributor/AI guidance and installed skill provenance, not product AI functionality |
| Root smoke payload/manifest/downloads | Local demonstration artifacts; not independent protocol/storage implementations |

### Cross-check rules when the code changes

Definition lines belong to the stated commit. After changing production files, refresh this map and check qualified names rather than relying on old line offsets. A TypedDict/type annotation is not runtime validation; read validate methods. A function docstring is not evidence of a test run; use the coverage record. A recorded benchmark revision is not the handbook revision. Missing telemetry, reconnection, resume, authentication and rarest-first are limitations, not hidden functions to search for.
