// Real Chrome + existing loopback process fixtures. No npm packages or Internet.
// node tests/browser/console.mjs [--baseline]
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, readFile, writeFile, open } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";

const baseline = process.argv.includes("--baseline");
const navigationOnly = process.argv.includes("--navigation-only");
const output = path.resolve("output/ui-redesign", baseline ? "before" : "after");
await mkdir(output, { recursive: true });
const temporary = await mkdtemp(path.join(tmpdir(), "p2p-browser-"));
const chromePath = process.env.P2P_CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const python = path.resolve(".venv/Scripts/python.exe");
const checks = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(work, label, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await work();
    if (value) return value;
    await sleep(60);
  }
  throw new Error(`Timed out: ${label}`);
}
function pass(label) { checks.push(label); console.log(`PASS ${label}`); }

class Devtools {
  constructor(socket) {
    this.socket = socket; this.next = 0; this.pending = new Map(); this.events = [];
    socket.addEventListener("message", ({ data }) => {
      const message = JSON.parse(data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (pending) {
          clearTimeout(pending.timer); this.pending.delete(message.id);
          if (message.error) pending.reject(new Error(JSON.stringify(message.error)));
          else pending.resolve(message.result);
        }
      } else this.events.push(message);
    });
  }
  async send(method, params = {}) {
    const id = ++this.next;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 20000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async page(url) {
    await this.send("Page.navigate", { url });
    await until(() => this.evaluate('document.readyState === "complete" && !!document.querySelector("#connection-message")'), "page load");
    await until(() => this.evaluate('document.querySelector("#connection-message").textContent.includes("connected")'), "initial snapshot");
  }
  async click(id) { await this.evaluate(`document.getElementById(${JSON.stringify(id)}).click()`); }
  async submit(form) {
    await until(() => this.evaluate(`!busy && !document.querySelector('#${form} button').disabled`), `${form} ready`);
    await this.evaluate(`document.querySelector('#${form} button').click()`);
  }
  async value(id, value) {
    await this.evaluate(`{ const n=document.getElementById(${JSON.stringify(id)}); n.value=${JSON.stringify(value)}; n.dispatchEvent(new Event("change",{bubbles:true})); }`);
  }
  async file(id, filename) {
    const { root } = await this.send("DOM.getDocument");
    const { nodeId } = await this.send("DOM.querySelector", { nodeId: root.nodeId, selector: `#${id}` });
    await this.send("DOM.setFileInputFiles", { nodeId, files: [filename] });
  }
  async route(name) {
    await this.evaluate(`document.querySelector('nav a[href="#${name}"]').click()`);
    await until(() => this.evaluate(`!document.getElementById(${JSON.stringify(name)}).hidden`), `route ${name}`);
  }
  async screenshot(name, width = 1440, height = 1000, atTop = true) {
    await this.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await this.evaluate("document.fonts.ready");
    if (atTop) await this.evaluate("window.scrollTo(0,0)");
    await sleep(100);
    const { data } = await this.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(path.join(output, `${name}.png`), Buffer.from(data, "base64"));
  }
}

let servers; let chrome; let browser; const pages = [];
let serverErrors = "";
try {
  // Reuse the unchanged E2E context managers, which publish ephemeral loopback
  // ports and require graceful process exits and tracker deregistration.
  const code = `
import json,sys,httpx
from contextlib import ExitStack
from pathlib import Path
from tests.e2e.test_web_http_transfer import http_server
if __name__ == '__main__':
    with http_server() as tracker:
        with ExitStack() as stack:
            origin=stack.enter_context(http_server(Path(sys.argv[1])/'origin',tracker))
            client=stack.enter_context(http_server(Path(sys.argv[1])/'client',tracker))
            offline=stack.enter_context(http_server(Path(sys.argv[1])/'offline','http://127.0.0.1:1')) if sys.argv[2]=='full' else None
            print(json.dumps({'tracker':tracker,'origin':origin,'client':client,'offline':offline}),flush=True)
            sys.stdin.readline()
        with httpx.Client(timeout=5,trust_env=False) as observer:
            assert observer.get(tracker+'/swarms').json()==[], 'memberships remain after console shutdown'
`;
  servers = spawn(python, ["-c", code, temporary, baseline ? "baseline" : "full"], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
  let serverOutput = "";
  servers.stdout.on("data", (chunk) => { serverOutput += chunk; });
  servers.stderr.on("data", (chunk) => { serverErrors += chunk; });
  const config = await until(() => {
    if (servers.exitCode !== null) throw new Error(`Servers exited: ${serverErrors}`);
    return serverOutput.split(/\r?\n/).filter((line) => line.startsWith('{"tracker"')).map((line) => JSON.parse(line))[0];
  }, "loopback process fixtures", 60000);
  chrome = spawn(chromePath, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${path.join(temporary, "chrome")}`, "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "about:blank"], { windowsHide: true, stdio: "ignore" });
  const port = await until(async () => {
    try { return (await readFile(path.join(temporary, "chrome/DevToolsActivePort"), "utf8")).split("\n")[0]; }
    catch { return null; }
  }, "isolated headless Chrome");
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  async function connect(url) {
    const socket = new WebSocket(url); await once(socket, "open"); return new Devtools(socket);
  }
  browser = await connect(version.webSocketDebuggerUrl);
  await browser.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: path.join(temporary, "exports") });
  async function newPage(url) {
    const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
    const target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.id === targetId);
    const page = await connect(target.webSocketDebuggerUrl); pages.push(page);
    await Promise.all([page.send("Runtime.enable"), page.send("Network.enable"), page.send("Log.enable"), page.send("Page.enable")]);
    await page.send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
    await page.page(url); return page;
  }
  const origin = await newPage(config.origin);
  const client = await newPage(config.client);
  if (baseline) {
    for (const name of ["dashboard", "transfer", "network", "experiments"]) {
      await origin.route(name);
      if (name === "experiments") await until(() => origin.evaluate('document.querySelectorAll("#experiment-rows tr").length===8'), "results");
      await origin.screenshot(name, 1024, 768);
    }
    pass("baseline screenshots for all four routes");
  } else if (navigationOnly) {
    await origin.route("transfer");
    await origin.evaluate('document.querySelector(".skip-link").click()');
    assert.equal(await origin.evaluate("location.hash"),"#transfer");
    assert.equal(await origin.evaluate('document.activeElement.id'),"main-content");
    pass("skip link preserves current route and focuses content");
  } else {
    const state = async (url) => (await fetch(`${url}/api/state`)).json();
    const peerState = async (url, id, expected) => until(async () => {
      const t = (await state(url)).transfers.find((t) => t.id === id);
      if (t?.state === "failed" && expected !== "failed") throw new Error(t.error);
      return t?.state === expected && t;
    }, `${id}: ${expected}`);
    async function start(page, url, kind = "download", baselineMode = false, rate = "") {
      await until(() => page.evaluate('!busy'), "previous UI action");
      await page.route("transfer"); await page.value("kind", kind);
      await page.evaluate(`{const n=document.getElementById("download-only"); n.checked=${baselineMode}; n.dispatchEvent(new Event("change",{bubbles:true}));}`);
      await page.value("upload-rate", rate);
      const oldIds = new Set((await state(url)).transfers.map((t) => t.id));
      await page.click("start-peer");
      return until(async () => (await state(url)).transfers.find((t) => !oldIds.has(t.id))?.id, "peer started by form");
    }
    async function stop(page, id) {
      await until(() => page.evaluate('!busy'), "UI idle"); await page.route("transfer");
      await until(() => page.evaluate(`!!document.querySelector('[data-focus-key="stop-${id}"]')`), "stop rendered");
      await page.evaluate(`document.querySelector('[data-focus-key="stop-${id}"]').click()`);
    }
    // Navigation, empty session and native form validation.
    for (const name of ["dashboard", "transfer", "network", "experiments"]) {
      await origin.route(name);
      assert.equal(await origin.evaluate(`document.querySelector('nav a[aria-current="page"]').hash`), `#${name}`);
    }
    await origin.evaluate('location.hash="invalid-route"');
    await until(() => origin.evaluate('!document.getElementById("dashboard").hidden'), "invalid hash fallback");
    await origin.route("transfer");
    await origin.route("network"); await origin.route("transfer");
    await origin.evaluate("history.back()");
    await until(()=>origin.evaluate('!document.getElementById("network").hidden'),"Back navigation");
    await origin.evaluate("history.forward()");
    await until(()=>origin.evaluate('!document.getElementById("transfer").hidden'),"Forward navigation");
    assert.equal(await origin.evaluate('document.getElementById("source-form").checkValidity()'), false);
    assert.equal(await origin.evaluate('document.getElementById("start-peer").disabled'), true);
    pass("four routes, active navigation, invalid hash, empty state and required validation");

    const payload = Buffer.alloc(2 * 1024 * 1024);
    for (let i = 0; i < payload.length; i++) payload[i] = i % 251;
    const source = path.join(temporary, "browser-demo.bin"); await writeFile(source, payload);
    await origin.file("source-file", source);
    await origin.submit("source-form");
    await until(() => origin.evaluate('document.getElementById("source-feedback").textContent.startsWith("Imported")'), "source imported");
    const asset = (await state(config.origin)).assets[0];
    assert.equal(await origin.evaluate('document.getElementById("asset").value'), asset.id);
    await origin.evaluate('document.querySelector("#assets a").click()');
    const manifestPath = path.join(temporary, "exports/browser-demo.bin.manifest.json");
    await until(async () => { try { return JSON.parse(await readFile(manifestPath, "utf8")); } catch { return null; } }, "manifest anchor download");
    await client.route("transfer"); await client.file("manifest-file", manifestPath);
    await client.submit("manifest-form");
    await until(() => client.evaluate('document.getElementById("manifest-feedback").textContent.startsWith("Imported")'), "manifest UI import");
    await client.value("kind", "seed");
    assert.equal(await client.evaluate('document.getElementById("start-peer").disabled'), true);
    pass("source import, asset selection, real manifest export/import, manifest-only seed guard");

    // Invalid input and limits are UI checks; malformed data is local only.
    const malformed = path.join(temporary, "invalid.json"); await writeFile(malformed, "{}");
    await client.file("manifest-file", malformed);
    await client.submit("manifest-form");
    await until(() => client.evaluate('!document.getElementById("error").hidden'), "malformed manifest error");
    assert.match(await client.evaluate('document.getElementById("manifest-feedback").textContent'), /failed/i);
    await origin.value("upload-rate", "0");
    assert.equal(await origin.evaluate('document.getElementById("upload-rate").validity.rangeUnderflow'), true);
    await origin.value("upload-rate", "1073741825");
    assert.equal(await origin.evaluate('document.getElementById("upload-rate").validity.rangeOverflow'), true);
    pass("malformed manifest feedback and upload-cap native range validation");

    for (const [page, field, form, size, name] of [[origin,"source-file","source-form",134217729,"oversize.bin"],[client,"manifest-file","manifest-form",4194305,"oversize.json"]]) {
      await until(() => page.evaluate('!busy'), "UI ready for size guard");
      const filename=path.join(temporary,name); const handle=await open(filename,"w");
      await handle.truncate(size); await handle.close();
      await page.file(field,filename);
      const posts=page.events.filter(e=>e.method==="Network.requestWillBeSent" && e.params.request.method==="POST").length;
      await page.submit(form);
      await until(()=>page.evaluate('!document.getElementById("error").hidden && document.getElementById("error").textContent.includes("exceeds")'),"browser size guard");
      assert.equal(page.events.filter(e=>e.method==="Network.requestWillBeSent" && e.params.request.method==="POST").length,posts);
    }
    await origin.file("source-file",source);
    await client.file("manifest-file",manifestPath);
    pass("128 MiB source and 4 MiB manifest size guards reject before POST");

    const seed = await start(origin, config.origin, "seed", false, "262144");
    await peerState(config.origin, seed, "seeding");
    const first = await start(client, config.client);
    const partial = await until(async () => {
      const t = (await state(config.client)).transfers.find((t) => t.id === first);
      return t?.metrics?.verified_bytes > 0 && t.metrics.verified_bytes < payload.length && t;
    }, "partial verified bytes");
    assert.equal(partial.metrics.final_integrity, "pending");
    await client.route("network");
    await until(() => client.evaluate('document.getElementById("network-details").textContent.includes("outbound")'), "network connection snapshot");
    assert.match(await client.evaluate('document.getElementById("network-details").textContent'), /outbound/);
    await client.send("Emulation.setDeviceMetricsOverride", {width:390,height:844,deviceScaleFactor:1,mobile:false});
    await client.evaluate('document.querySelector("#network-details .table-wrap").focus(); document.querySelector("#network-details .table-wrap").scrollLeft=60');
    const region=await client.evaluate('({key:document.activeElement.dataset.focusKey,scroll:document.activeElement.scrollLeft})');
    await client.click("refresh"); await until(()=>client.evaluate('!refreshing'),"network region refresh");
    assert.equal(await client.evaluate('document.activeElement.dataset.focusKey'),region.key);
    assert.equal(await client.evaluate('document.activeElement.scrollLeft'),region.scroll);
    await client.send("Emulation.setDeviceMetricsOverride", {width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await client.route("transfer");
    await client.evaluate(`document.querySelector('[data-focus-key="stop-${first}"]').focus()`);
    await client.click("refresh");
    await until(() => client.evaluate('!refreshing'), "manual refresh");
    assert.equal(await client.evaluate('document.activeElement.dataset.focusKey'), `stop-${first}`);
    if (await client.evaluate('!!document.getElementById("advanced-settings")')) {
      await client.evaluate('document.getElementById("advanced-settings").open=false');
      await client.click("refresh"); await until(() => client.evaluate('!refreshing'), "details refresh");
      assert.equal(await client.evaluate('document.getElementById("advanced-settings").open'), false);
      await client.evaluate('document.getElementById("advanced-settings").open=true');
    }
    const completed = await peerState(config.client, first, "completed");
    assert.equal(completed.metrics.final_integrity, "verified");
    assert.equal(completed.metrics.bytes_downloaded, payload.length);
    await until(()=>client.evaluate('document.querySelectorAll("#summary-membership dd")[0].textContent==="2"'),"tracker scope counts");
    assert.deepEqual(await client.evaluate('[...document.querySelectorAll("#summary-membership dd")].map(n=>n.textContent)'),["2","1"]);
    assert.deepEqual(await client.evaluate('[...document.querySelectorAll("#summary-payload dd")].map(n=>n.textContent)'),["0 B","2.00 MiB"]);
    await until(() => client.evaluate(`!!document.querySelector('a[href="/api/transfers/${first}/file"]')`), "verified output anchor");
    await client.evaluate(`document.querySelector('a[href="/api/transfers/${first}/file"]').click()`);
    const exportedPath = path.join(temporary, "exports/browser-demo.bin");
    const exported = await until(async () => { try { const b=await readFile(exportedPath); return b.length===payload.length && b; } catch { return null; } }, "verified file download");
    assert.equal(createHash("sha256").update(exported).digest("hex"), asset.file_sha256);
    await client.route("dashboard"); await client.screenshot("dashboard-live");
    await client.route("transfer"); await client.screenshot("transfer-live");
    await client.route("network"); await client.screenshot("network-live");
    pass("capped real transfer, partial progress, network inspection, keyed focus, disclosure state, verified export SHA-256");

    await stop(origin, seed); await peerState(config.origin, seed, "stopped");
    const second = await start(client, config.client);
    const relayed = await peerState(config.client, second, "completed");
    assert.equal(relayed.metrics.downloaded_from[completed.metrics.peer_id], payload.length);
    await client.route("network"); await client.value("network-peer",first);
    await client.click("refresh"); await until(()=>client.evaluate('!refreshing'),"peer selector refresh");
    assert.equal(await client.evaluate('document.getElementById("network-peer").value'),first);
    await stop(client, first); await peerState(config.client, first, "stopped");
    await stop(client, second); await peerState(config.client, second, "stopped");
    pass("stop origin, completed-peer TCP relay, stop completed peers");

    const baselineSeed = await start(origin, config.origin, "seed");
    await peerState(config.origin, baselineSeed, "seeding");
    for (let i = 0; i < 2; i++) {
      const id = await start(client, config.client, "download", true);
      assert.equal(await client.evaluate('document.getElementById("upload-rate").disabled'), true);
      const t = await peerState(config.client, id, "completed");
      assert.equal(t.upload_rate_limit, null); assert.equal(t.metrics.upload_enabled, false);
      assert.equal(t.metrics.bytes_uploaded, 0);
      await stop(client, id); await peerState(config.client, id, "stopped");
    }
    pass("two baseline clients, disabled cap/null request and zero uploaded bytes");

    await stop(origin, baselineSeed); await peerState(config.origin, baselineSeed, "stopped");
    const slowSeed = await start(origin, config.origin, "seed", false, "65536");
    await peerState(config.origin, slowSeed, "seeding");
    const cancelled = await start(client, config.client);
    await peerState(config.client, cancelled, "downloading");
    await stop(client, cancelled);
    const stopped = await peerState(config.client, cancelled, "stopped");
    assert.equal(stopped.has_output, false);
    await stop(origin, slowSeed); await peerState(config.origin, slowSeed, "stopped");
    const failed = await start(client, config.client);
    const failure = await peerState(config.client, failed, "failed");
    assert.match(failure.error, /no reachable peers/i);
    await until(() => client.evaluate(`document.querySelector('[data-focus-key="stop-${failed}"]')?.disabled`), "failed stop gate");
    pass("cancel incomplete transfer, no-output guard, no-peer error and disabled failed control");

    await origin.route("experiments");
    await until(() => origin.evaluate('document.querySelectorAll("#experiment-rows tr").length===8'), "eight recorded configurations");
    await origin.click("reload-experiments");
    await until(() => origin.evaluate('!document.getElementById("reload-experiments").disabled'), "reload results");
    assert.equal(await origin.evaluate('document.querySelectorAll("#time-chart polyline").length'), 2);
    assert.match(await origin.evaluate('document.getElementById("experiment-audit").textContent'), /40 included trials/);
    await origin.screenshot("experiments");
    await origin.evaluate('document.querySelector(".chart-grid").scrollIntoView()');
    await origin.screenshot("experiment-plots",1440,1000,false);
    pass("recorded CSV first load/reload, eight configurations, two chart series and audit");

    for (const [width, height] of [[1440,1000],[1024,768],[768,1024],[390,844],[320,800]]) {
      for (const route of ["dashboard", "transfer", "network", "experiments"]) {
        await origin.route(route); await origin.screenshot(`${route}-${width}`, width, height);
        assert.equal(await origin.evaluate('document.documentElement.scrollWidth<=innerWidth'), true, `${route} overflow at ${width}`);
        assert.equal(await origin.evaluate('[...document.querySelectorAll("nav a")].every(a=>a.getBoundingClientRect().width>0)'), true);
      }
    }
    await origin.send("Emulation.setDeviceMetricsOverride", { width: 720, height: 500, deviceScaleFactor: 1, mobile: false });
    assert.equal(await origin.evaluate('document.documentElement.scrollWidth<=innerWidth'), true);
    await origin.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
    await origin.route("transfer");
    const fonts = await origin.evaluate('({heading:document.fonts.check(\'600 36px "Plus Jakarta Sans"\'),body:document.fonts.check(\'400 15px Inter\')})');
    assert.equal(fonts.heading, true); assert.equal(fonts.body, true);
    assert.equal(await origin.evaluate('[...document.fonts].filter(f=>/Inter|Jakarta/.test(f.family)).every(f=>f.status==="loaded")'),true);
    await origin.send("Page.navigate",{url:config.origin});
    await until(()=>origin.evaluate('document.readyState==="complete" && !!document.getElementById("main-content")'),"keyboard page reload");
    await origin.send("Input.dispatchKeyEvent",{type:"keyDown",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
    await origin.send("Input.dispatchKeyEvent",{type:"keyUp",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
    assert.equal(await origin.evaluate('document.activeElement.classList.contains("skip-link")'),true);
    await origin.send("Input.dispatchKeyEvent",{type:"keyDown",key:"Enter",code:"Enter",windowsVirtualKeyCode:13});
    await origin.send("Input.dispatchKeyEvent",{type:"keyUp",key:"Enter",code:"Enter",windowsVirtualKeyCode:13});
    await until(()=>origin.evaluate('document.activeElement.id==="main-content"'),"keyboard skip link");
    assert.match(await origin.evaluate('getComputedStyle(document.activeElement).outlineStyle'),/solid/);
    await origin.route("transfer");
    await origin.evaluate('document.querySelector(".skip-link").click()');
    assert.equal(await origin.evaluate("location.hash"),"#transfer");
    assert.equal(await origin.evaluate('document.activeElement.id'),"main-content");
    pass("all four pages at five viewports, reflow, reduced motion and local fonts");

    const polls = client.events.filter((e) => e.method === "Network.requestWillBeSent" && e.params.request.url.endsWith("/api/state"));
    assert.ok(polls.length > 10);
    const exceptions = pages.flatMap((p) => p.events).filter((e) => e.method === "Runtime.exceptionThrown" || (e.method === "Log.entryAdded" && e.params.entry.source === "security"));
    assert.deepEqual(exceptions, []);
    const external = pages.flatMap((p) => p.events).filter((e) => e.method === "Network.requestWillBeSent" && /^https?:/.test(e.params.request.url) && new URL(e.params.request.url).hostname !== "127.0.0.1");
    assert.deepEqual(external, []);
    const failures = pages.flatMap((p) => p.events).filter((e) => e.method === "Network.loadingFailed" && e.params.errorText !== "net::ERR_ABORTED");
    assert.deepEqual(failures, []);
    pass("live polling, no JS/CSP/network loading errors and no external requests");

    const offline=await newPage(config.offline);
    await until(()=>offline.evaluate('document.getElementById("tracker-status").textContent==="offline"'),"real offline tracker");
    assert.match(await offline.evaluate('document.getElementById("summary-membership").textContent'),/Unavailable/);
    await offline.route("transfer"); await offline.file("source-file",source);
    await offline.submit("source-form");
    await until(()=>offline.evaluate('document.getElementById("source-feedback").textContent.startsWith("Imported")'),"offline console import");
    assert.equal(await offline.evaluate('document.getElementById("start-peer").disabled'),true);
    pass("real tracker offline, unavailable membership and disabled Start with imported asset");

    // Fault injection is browser transport failure only. No fabricated state.
    for (const [pattern, trigger, expected] of [["*/api/state",()=>client.click("refresh"),'document.getElementById("connection-message").textContent.includes("disconnected")'],["*/api/experiments",()=>client.click("reload-experiments"),'document.getElementById("experiment-status").textContent.includes("Results unavailable")']]) {
      await client.route(pattern.includes("experiments")?"experiments":"dashboard");
      if(pattern.includes("experiments")) await until(()=>client.evaluate('!document.getElementById("reload-experiments").disabled'),"experiments idle");
      else await until(()=>client.evaluate('!refreshing'),"snapshot idle");
      await client.send("Fetch.enable",{patterns:[{urlPattern:pattern}]});
      const paused=client.events.length;
      await trigger();
      const event=await until(()=>client.events.slice(paused).find(e=>e.method==="Fetch.requestPaused"),"intercept request");
      await client.send("Fetch.failRequest",{requestId:event.params.requestId,errorReason:"ConnectionFailed"});
      await until(()=>client.evaluate(expected),"visible transport failure");
      await client.send("Fetch.disable");
      if(pattern.includes("state")) {
        assert.equal(await client.evaluate('document.querySelectorAll("#dashboard-transfers tr").length>0'),true);
        await client.click("refresh");
        await until(()=>client.evaluate('document.getElementById("connection-message").textContent.startsWith("Console connected")'),"state recovery");
      } else {
        await client.click("reload-experiments");
        await until(()=>client.evaluate('document.querySelectorAll("#experiment-rows tr").length===8'),"results recovery");
      }
    }
    pass("transport failure labels retained snapshot stale/results unavailable, then recovery");
    assert.deepEqual(pages.flatMap(p=>p.events).filter(e=>e.method==="Runtime.exceptionThrown" || (e.method==="Log.entryAdded" && e.params.entry.source==="security")),[]);
  }
  await writeFile(path.join(output, "report.json"), JSON.stringify({ baseline, checks, browser: version.Browser, temporary }, null, 2));
} catch (error) {
  for (const [index, page] of pages.entries()) {
    try {
      const diagnostics = await page.evaluate('({url:location.href,text:document.body.innerText,busy,files:[...document.querySelectorAll("input[type=file]")].map(n=>({id:n.id,files:[...n.files].map(f=>({name:f.name,size:f.size}))}))})');
      await writeFile(path.join(output, `failure-${index}.json`), JSON.stringify({ diagnostics, events: page.events }, null, 2));
      await page.screenshot(`failure-${index}`);
      console.error(JSON.stringify(diagnostics));
    } catch { /* Keep the original test failure. */ }
  }
  throw error;
} finally {
  for (const page of pages) page.socket.close();
  if (browser) { try { await browser.send("Browser.close"); } catch { /* Browser may close before replying. */ } browser.socket.close(); }
  else if (chrome) chrome.kill();
  if (servers) {
    servers.stdin.end("stop\n");
    let timer;
    const exit = servers.exitCode ?? await Promise.race([once(servers,"exit").then(([code])=>code), new Promise(resolve=>{timer=setTimeout(()=>resolve("timeout"),25000);})]);
    clearTimeout(timer);
    assert.equal(exit, 0, `fixture shutdown failed: ${serverErrors}`);
  }
}
console.log(`${checks.length} browser workflow groups passed; screenshots: ${output}`);
