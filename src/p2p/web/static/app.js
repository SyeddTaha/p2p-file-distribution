"use strict";

const $ = (id) => document.getElementById(id);
let state = { assets: [], transfers: [], tracker: { swarms: null } };
let refreshing = false;
let currentRefresh = null;
let busy = false;
let experimentsLoaded = false;
let assetSignature = "";
let peerSignature = "";

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function bytes(value) {
  if (value === null || value === undefined) return "Unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1048576) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1048576).toFixed(2)} MiB`;
}
function status(value) { return el("span", value, `state state-${value}`); }
function link(label, url) { const a = el("a", label); a.href = url; return a; }
function cell(row, content, className) {
  const td = el("td", undefined, className);
  td.append(content instanceof Node ? content : document.createTextNode(String(content)));
  row.append(td); return td;
}
function empty(target, message, columns) {
  target.replaceChildren();
  if (columns) {
    const row = el("tr"); const td = cell(row, message, "empty"); td.colSpan = columns; target.append(row);
  } else target.append(el("p", message, "muted"));
}
function table(headers, rows) {
  const wrap = el("div", undefined, "table-wrap"); const t = el("table");
  const head = el("thead"); const tr = el("tr");
  headers.forEach((text) => tr.append(el("th", text))); head.append(tr);
  const body = el("tbody"); rows.forEach((row) => body.append(row));
  t.append(head, body); wrap.append(t); return wrap;
}
function definition(list, label, value) {
  const pair = el("div"); pair.append(el("dt", label), el("dd", value)); list.append(pair);
}
function progress(transfer) {
  const wrap = el("div"); const m = transfer.metrics;
  if (!m) { wrap.append(el("span", "Pending peer startup", "muted")); return wrap; }
  const bar = el("progress"); bar.max = transfer.file_size; bar.value = m.verified_bytes;
  bar.setAttribute("aria-label", `Verified bytes for ${transfer.file_name}`);
  wrap.append(el("span", `${m.verified_chunks} / ${transfer.chunk_count} chunks`), bar,
    el("span", `${bytes(m.verified_bytes)} / ${bytes(transfer.file_size)}`, "muted"));
  return wrap;
}
async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options, headers: { "X-P2P-UI": "1", ...options.headers },
    signal: AbortSignal.timeout(options.method ? 150000 : 15000),
  });
  if (!response.ok) {
    const text = await response.text(); let message = text;
    try { message = JSON.parse(text).detail || text; } catch { /* Plain HTTP error. */ }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return response.json();
}
function showError(error) { $("error").textContent = error.message; $("error").hidden = false; }
function syncOptions() {
  const currentAsset = state.assets.find((a) => a.id === $("asset").value);
  const seeding = $("kind").value === "seed";
  $("download-only").disabled = seeding;
  if (seeding) $("download-only").checked = false;
  $("upload-rate").disabled = $("download-only").checked;
  $("start-peer").disabled = busy || !state.tracker.online || !currentAsset || (seeding && !currentAsset.can_seed);
  $("start-peer").title = state.tracker.online ? "" : "Start the tracker before starting a peer";
}
function renderAssets() {
  const signature = state.assets.map((a) => a.id).join(",");
  if (signature !== assetSignature) {
    const selected = $("asset").value; $("asset").replaceChildren();
    if (!state.assets.length) $("asset").append(new Option("Import a file or manifest first", ""));
    state.assets.forEach((asset) => $("asset").append(new Option(`${asset.file_name} (${asset.id.slice(0, 6)})`, asset.id)));
    if (state.assets.some((a) => a.id === selected)) $("asset").value = selected;
    assetSignature = signature;
  }
  const body = $("assets"); body.replaceChildren();
  state.assets.forEach((asset) => {
    const row = el("tr"); const name = el("div");
    name.append(el("div", asset.file_name, "file-name"), el("span", `${bytes(asset.file_size)} · ${asset.chunk_count} chunks`, "muted")); cell(row, name);
    const hashes = el("div"); hashes.append(el("code", `Swarm: ${asset.swarm_id}`, "hash"), el("code", `SHA-256: ${asset.file_sha256}`, "hash")); cell(row, hashes);
    cell(row, asset.can_seed ? "Imported source" : "Manifest only");
    cell(row, link("Save manifest", `/api/assets/${asset.id}/manifest`)); body.append(row);
  });
  if (!state.assets.length) empty(body, "Import a source file to create a manifest, or import an existing manifest.", 4);
  syncOptions();
}
function renderDashboard() {
  const tracker = state.tracker;
  $("tracker-status").replaceChildren(status(tracker.online ? "online" : "offline"));
  $("tracker-url").textContent = tracker.url;
  $("tracker-error").textContent = tracker.error || "";
  const summary = $("summary"); summary.replaceChildren();
  const swarms = tracker.swarms;
  const peerCount = swarms ? new Set(swarms.flatMap((s) => s.peers.map((p) => p.peer_id))).size : "Unavailable";
  definition(summary, "Active peers (tracker)", String(peerCount));
  definition(summary, "Active swarms (tracker)", swarms ? String(swarms.length) : "Unavailable");
  definition(summary, "Downloading (local)", String(state.transfers.filter((t) => t.state === "downloading").length));
  definition(summary, "Uploaded (local payload)", bytes(state.transfers.reduce((sum, t) => sum + (t.metrics?.bytes_uploaded || 0), 0)));
  definition(summary, "Downloaded (local payload)", bytes(state.transfers.reduce((sum, t) => sum + (t.metrics?.bytes_downloaded || 0), 0)));
  const body = $("dashboard-transfers"); body.replaceChildren();
  state.transfers.forEach((t) => {
    const row = el("tr"); const name = el("div"); name.append(el("p", t.file_name, "file-name"), el("code", t.metrics?.peer_id || t.id)); cell(row, name);
    cell(row, status(t.state)); cell(row, progress(t));
    cell(row, bytes(t.metrics?.bytes_downloaded), "numeric"); cell(row, bytes(t.metrics?.bytes_uploaded), "numeric");
    cell(row, status(t.metrics?.final_integrity || "pending")); body.append(row);
  });
  if (!state.transfers.length) empty(body, "No local peers. Use File Transfer to import a file and start seeding or downloading.", 6);
}
function renderTransfers() {
  const host = $("transfer-details"); host.replaceChildren();
  state.transfers.forEach((t) => {
    const entry = el("article", undefined, "transfer-entry"); const heading = el("div", undefined, "transfer-heading");
    heading.append(el("h3", `${t.file_name} · ${t.kind}`), status(t.state)); entry.append(heading);
    entry.append(el("code", t.metrics?.peer_id || t.id), progress(t));
    const dl = el("dl"); const m = t.metrics;
    definition(dl, "Mode", t.download_only ? "Download-only" : "P2P");
    definition(dl, "Upload cap", t.upload_rate_limit === null ? "Unlimited" : `${bytes(t.upload_rate_limit)}/s`);
    definition(dl, "Download mean", m ? `${bytes(m.throughput_bytes_per_s)}/s` : "Unavailable");
    definition(dl, "Transfer duration", m ? `${m.duration_seconds.toFixed(2)} s` : "Unavailable");
    definition(dl, "Retries / rejected chunks", m ? `${m.retries} / ${m.chunk_hash_failures}` : "Unavailable");
    definition(dl, "Final SHA-256", m?.final_integrity || "pending"); entry.append(dl);
    entry.append(el("code", `Expected SHA-256: ${t.file_sha256}`, "hash"));
    if (t.error) entry.append(el("p", t.error, "error"));
    const actions = el("div", undefined, "actions"); const stop = el("button", "Stop peer");
    stop.dataset.focusKey = `stop-${t.id}`;
    stop.disabled = busy || ["failed", "stopped"].includes(t.state);
    stop.addEventListener("click", () => action(async () => { await api(`/api/transfers/${t.id}/stop`, { method: "POST" }); }));
    actions.append(stop);
    if (t.has_output) actions.append(link("Save verified file", `/api/transfers/${t.id}/file`));
    entry.append(actions); host.append(entry);
  });
  if (!state.transfers.length) empty(host, "No peers started in this console.");
}
function renderNetwork() {
  const host = $("swarms"); host.replaceChildren(); const swarms = state.tracker.swarms;
  if (!swarms) empty(host, "Membership unavailable. Check the tracker status on Dashboard.");
  else if (!swarms.length) empty(host, "The tracker currently has no active swarms.");
  else swarms.forEach((swarm) => {
    const entry = el("article", undefined, "swarm-entry");
    entry.append(el("code", swarm.swarm_id, "hash"));
    const seeds = swarm.peers.filter((p) => p.is_seeder).length;
    entry.append(el("p", `${swarm.peers.length} peers · ${seeds} seeders · ${swarm.peers.length - seeds} leechers`, "muted"));
    const rows = swarm.peers.map((p) => {
      const local = state.transfers.find((t) => t.metrics?.peer_id === p.peer_id); const row = el("tr");
      cell(row, el("code", p.peer_id)); cell(row, el("code", `${p.host}:${p.port}`));
      cell(row, p.is_seeder ? "Seeder (complete)" : "Leecher");
      cell(row, local?.metrics ? (local.metrics.upload_enabled ? "Enabled" : "Disabled (baseline)") : "Unknown (remote)");
      cell(row, local ? local.state : "Registered; connection state unavailable"); return row;
    });
    entry.append(table(["Peer", "Address", "Role", "Upload capability", "Local state"], rows)); host.append(entry);
  });
  const signature = state.transfers.map((t) => t.id).join(",");
  if (signature !== peerSignature) {
    const selected = $("network-peer").value; $("network-peer").replaceChildren();
    state.transfers.forEach((t) => $("network-peer").append(new Option(`${t.file_name} · ${t.metrics?.peer_id || t.id}`, t.id)));
    if (state.transfers.some((t) => t.id === selected)) $("network-peer").value = selected;
    peerSignature = signature;
  }
  state.transfers.forEach((t, index) => {
    $("network-peer").options[index].textContent = `${t.file_name} · ${t.metrics?.peer_id || t.id}`;
  });
  const details = $("network-details"); details.replaceChildren();
  const transfer = state.transfers.find((t) => t.id === $("network-peer").value);
  if (!transfer?.metrics) { empty(details, "Start a local peer to inspect connections and chunk sources."); return; }
  const m = transfer.metrics;
  details.append(el("p", `Listener: ${m.host}:${m.port} · ${m.online ? "online" : "stopped"}`, "muted"), el("code", `Swarm: ${m.swarm_id}`, "hash"));
  const rows = m.connections.map((c) => {
    const row = el("tr"); cell(row, el("code", c.peer_id || "Handshake pending")); cell(row, c.direction);
    cell(row, c.state === "closed" ? "disconnected" : c.state.replaceAll("_", " "));
    cell(row, c.available_chunks ?? "Unavailable"); cell(row, c.pending_requests); return row;
  });
  if (rows.length) details.append(table(["Remote peer", "Direction", "Connection", "Advertised chunks", "Pending requests"], rows));
  else details.append(el("p", "No observed TCP connections for this peer.", "muted"));
  details.append(el("h3", "Verified chunk sources"));
  const sources = Object.entries(m.downloaded_from).filter(([, value]) => value > 0).map(([peer, count]) => {
    const row = el("tr"); cell(row, el("code", peer)); cell(row, bytes(count), "numeric"); return row;
  });
  if (sources.length) details.append(table(["Serving peer", "Verified bytes received"], sources));
  else details.append(el("p", "No verified payload received by this peer yet.", "muted"));
}
function render() {
  const focusKey = document.activeElement?.dataset.focusKey;
  renderAssets(); renderDashboard(); renderTransfers(); renderNetwork();
  if (focusKey) document.querySelector(`[data-focus-key="${focusKey}"]`)?.focus({ preventScroll: true });
}
function refresh() {
  if (refreshing) return currentRefresh;
  refreshing = true; $("refresh").disabled = true;
  currentRefresh = (async () => {
    try {
      state = await api("/api/state"); render();
      $("connection-message").textContent = `Console connected · Last snapshot ${new Date().toLocaleTimeString()}`;
    } catch (error) {
      $("connection-message").textContent = "Console disconnected. Displayed values are from the last successful snapshot.";
      showError(error);
    } finally { refreshing = false; $("refresh").disabled = false; }
  })();
  return currentRefresh;
}
async function refreshAfterAction() {
  if (refreshing) await currentRefresh;
  await refresh();
}
async function action(work) {
  if (busy) return;
  busy = true; $("error").hidden = true; syncOptions();
  try { await work(); } catch (error) { showError(error); }
  finally { busy = false; await refreshAfterAction(); syncOptions(); }
}
function setupUpload(form, input, feedback, manifestOnly) {
  $(form).addEventListener("submit", (event) => {
    event.preventDefault(); const file = $(input).files[0]; if (!file) return;
    action(async () => {
      const button = $(form).querySelector("button"); button.disabled = true;
      $(feedback).textContent = manifestOnly ? "Uploading and validating manifest…" : "Uploading and hashing file…";
      try {
        const limit = manifestOnly ? 4194304 : 134217728;
        if (file.size > limit) throw new Error(`Selected file exceeds ${bytes(limit)}.`);
        const result = await api(`/api/assets?name=${encodeURIComponent(file.name)}&manifest_only=${manifestOnly}`, { method: "POST", body: file });
        $(feedback).textContent = `Imported ${result.file_name}. ${result.chunk_count} chunks; manifest ready.`;
        await refreshAfterAction(); $("asset").value = result.id;
      } catch (error) { $(feedback).textContent = "Import failed."; throw error; }
      finally { button.disabled = false; }
    });
  });
}
function svgNode(tag, attributes, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text; return node;
}
function chart(id, summaries, metric, divisor, unit) {
  const svg = $(id); svg.replaceChildren();
  const data = summaries.filter((s) => [1, 2, 4, 8].includes(s.num_clients));
  if (!data.length) return;
  const maximum = Math.max(...data.map((s) => (s.means[metric] + s.stds[metric]) / divisor)) * 1.1 || 1;
  const x = (n) => 65 + [1, 2, 4, 8].indexOf(n) * 137;
  const y = (v) => 225 - v / maximum * 190;
  for (let tick = 0; tick <= 4; tick++) {
    const value = maximum * tick / 4;
    svg.append(svgNode("line", { x1: 60, x2: 485, y1: y(value), y2: y(value), stroke: "#d7ddd9" }));
    svg.append(svgNode("text", { x: 51, y: y(value) + 4, "text-anchor": "end" }, value.toFixed(1)));
  }
  [1, 2, 4, 8].forEach((n) => svg.append(svgNode("text", { x: x(n), y: 249, "text-anchor": "middle" }, String(n))));
  svg.append(svgNode("text", { x: 65, y: 20 }, unit), svgNode("text", { x: 260, y: 272, "text-anchor": "middle" }, "Number of clients (N)"));
  for (const mode of ["baseline", "p2p"]) {
    const items = data.filter((s) => s.mode === mode).sort((a, b) => a.num_clients - b.num_clients);
    const color = mode === "p2p" ? "#21633f" : "#59635d";
    svg.append(svgNode("polyline", { points: items.map((s) => `${x(s.num_clients)},${y(s.means[metric] / divisor)}`).join(" "), fill: "none", stroke: color, "stroke-width": 2, "stroke-dasharray": mode === "baseline" ? "5 3" : "none" }));
    items.forEach((s) => {
      const px = x(s.num_clients); const mean = s.means[metric] / divisor; const sd = s.stds[metric] / divisor;
      const low = y(Math.max(0, mean - sd)); const high = y(mean + sd);
      svg.append(svgNode("line", { x1: px, x2: px, y1: low, y2: high, stroke: color }),
        svgNode("line", { x1: px - 4, x2: px + 4, y1: low, y2: low, stroke: color }),
        svgNode("line", { x1: px - 4, x2: px + 4, y1: high, y2: high, stroke: color }),
        svgNode("circle", { cx: px, cy: y(mean), r: 3, fill: color }));
    });
  }
}
async function loadExperiments() {
  $("reload-experiments").disabled = true; $("experiment-status").textContent = "Reading benchmark CSV…";
  $("experiment-rows").replaceChildren(); $("exclusions").replaceChildren();
  $("experiment-caption").textContent = ""; $("experiment-audit").textContent = "";
  $("time-chart").replaceChildren(); $("throughput-chart").replaceChildren();
  try {
    const data = await api("/api/experiments");
    if (!data.available) throw new Error(data.error);
    $("experiment-status").textContent = `Source: ${data.source}`;
    $("experiment-caption").textContent = data.caption;
    const included = data.audit.filter((a) => a.reason === "included").length;
    const warmups = data.audit.filter((a) => a.reason === "warmup").length;
    const excluded = data.audit.filter((a) => !["included", "warmup"].includes(a.reason));
    $("experiment-audit").textContent = `${included} included trials · ${warmups} warmups · ${excluded.length} failed or incomplete trials excluded. Table and charts show means ± sample standard deviation.`;
    data.summaries.filter((s) => [1, 2, 4, 8].includes(s.num_clients)).sort((a, b) => a.num_clients - b.num_clients || a.mode.localeCompare(b.mode)).forEach((s) => {
      const row = el("tr"); cell(row, s.num_clients); cell(row, s.mode === "p2p" ? "P2P" : "Baseline"); cell(row, s.count, "numeric");
      cell(row, `${s.means.makespan_s.toFixed(3)} ± ${s.stds.makespan_s.toFixed(3)}`, "numeric");
      cell(row, `${(s.means.aggregate_throughput_bytes_per_s / 1048576).toFixed(3)} ± ${(s.stds.aggregate_throughput_bytes_per_s / 1048576).toFixed(3)}`, "numeric");
      cell(row, `${s.means.peer_share_pct.toFixed(2)}%`, "numeric"); $("experiment-rows").append(row);
    });
    if (!data.summaries.length) empty($("experiment-rows"), "No complete successful measured trials.", 6);
    chart("time-chart", data.summaries, "makespan_s", 1, "Seconds");
    chart("throughput-chart", data.summaries, "aggregate_throughput_bytes_per_s", 1048576, "MiB/s");
    excluded.forEach((a) => $("exclusions").append(el("p", `${a.run_id}: ${a.reason}`, "error")));
  } catch (error) { $("experiment-status").textContent = `Results unavailable: ${error.message}`; }
  finally { $("reload-experiments").disabled = false; }
}
function navigate() {
  const page = location.hash.slice(1) || "dashboard";
  const valid = ["dashboard", "transfer", "network", "experiments"].includes(page) ? page : "dashboard";
  document.querySelectorAll("main > section").forEach((section) => { section.hidden = section.id !== valid; });
  document.querySelectorAll("nav a").forEach((a) => {
    if (a.hash === `#${valid}`) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  if (valid === "experiments" && !experimentsLoaded) { experimentsLoaded = true; loadExperiments(); }
}
$("refresh").addEventListener("click", refresh);
$("reload-experiments").addEventListener("click", loadExperiments);
$("network-peer").addEventListener("change", renderNetwork);
["asset", "kind", "download-only"].forEach((id) => $(id).addEventListener("change", syncOptions));
setupUpload("source-form", "source-file", "source-feedback", false);
setupUpload("manifest-form", "manifest-file", "manifest-feedback", true);
$("peer-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(async () => {
    const rate = $("upload-rate").value;
    const result = await api("/api/transfers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      asset_id: $("asset").value, kind: $("kind").value,
      upload_rate_limit: rate && !$("download-only").checked ? Number(rate) : null,
      download_only: $("download-only").checked,
    }) });
    $("peer-feedback").textContent = `Peer queued: ${result.id}. See its state below.`;
  });
});
window.addEventListener("hashchange", navigate);
navigate(); refresh();
setInterval(refresh, 1000);
