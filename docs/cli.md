# Command-Line Interface

Install the project (the repository's `requirements.txt` installs it in editable
mode) to expose the `p2p` command. All commands are available through
`python -m p2p.cli` as well.

## Start the tracker

```powershell
p2p tracker-start --host 127.0.0.1 --port 8000
```

The tracker runs in the foreground. Stop it with Ctrl+C. Its registry is
in-memory, so peers must re-announce after a tracker restart.

## Create and distribute a manifest

```powershell
p2p create-manifest .\payload.bin --chunk-size 262144 --output .\payload.manifest.json
```

`--chunk-size` is optional and defaults to the project chunk size. If `--output`
is omitted, the manifest is written next to the source file with
`.manifest.json` appended to its path. Transfer the resulting manifest to each
peer out of band; tracker discovery uses its canonical SHA-256 swarm ID.

## Seed a file

```powershell
p2p seed-file .\payload.manifest.json .\payload.bin --tracker-url http://127.0.0.1:8000
```

The seeder validates the entire file against the manifest before starting its
listener and announcing `started`. It responds only with chunks whose length
and SHA-256 match the manifest. The command keeps serving until Ctrl+C, then
announces `stopped` on a best-effort basis.

## Download and continue seeding

```powershell
p2p download-file .\payload.manifest.json --download-dir .\downloads --tracker-url http://127.0.0.1:8000
```

The peer announces `started`, discovers peers through `/announce`, downloads
available chunks concurrently, verifies each chunk and the complete file, then
announces `completed`. It remains online and serves its verified file until
Ctrl+C. On shutdown it stops accepting connections, cancels heartbeats, and
announces `stopped`.

Both peer commands accept `--listen-port` (default `0`, which requests an
ephemeral port) and `--host` (default `127.0.0.1`). The host is both the bind
address and the address advertised to the tracker; set it to an address peers
can reach when running across machines. IPv4, IPv6 literals, and hostnames are
accepted; URI-style IPv6 brackets are removed at the socket boundary.

Expected runtime input and network errors from peer commands, including a
download with no reachable peers, are reported as `p2p: error: ...` with a
nonzero exit code and no traceback. Tracker bind errors are logged by Uvicorn
and also exit nonzero. Argument syntax errors are handled by `argparse`.

## Download without uploading (client-server baseline)

Add `--no-upload` to `download-file` on every client, keeping the original
`seed-file` process unchanged:

```powershell
p2p download-file .\payload.manifest.json --download-dir .\downloads --tracker-url http://127.0.0.1:8000 --no-upload
```

This option disables chunk advertising and serving during and after the
download. Verification and tracker lifecycle events still run, and the process
remains online until Ctrl+C. It does not restrict which remote peers can supply
data, so an origin-only baseline requires all clients to use `--no-upload` and
exactly one uploading origin. The Python equivalent is
`SwarmPeer(..., upload_enabled=False)`.

Rate limits and the experiment runner remain planned. This mode alone does
not provide controlled performance measurements. The parser/dispatch and
loopback transfer paths are automated-tested; the new flag has not had a
separate multi-process Windows smoke test.

## Verification scope

Parser and command dispatch tests cover all four subcommands. The in-process
end-to-end tests exercise tracker requests through FastAPI `ASGITransport` and
peer transfers through real loopback TCP connections; they do not launch
separate tracker and peer OS processes. A separate Windows smoke test used
three process terminals and a fourth verification prompt to check real tracker,
seeder, and leecher processes, clean Ctrl+C shutdown, file equality, and
tracker deregistration. See
[testing.md](testing.md) for the procedure and [project-status.md](project-status.md)
for the recorded result.
