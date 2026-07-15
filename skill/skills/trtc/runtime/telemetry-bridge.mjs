#!/usr/bin/env node
// skills/trtc/runtime/telemetry-bridge.mjs
//
// Web telemetry bridge for runtime log collection.
//
// Two modes:
//   Mode A (default, visible): Launches a visible Chrome window + Vite dev
//     server. User interacts directly in the Puppeteer-managed browser.
//   Mode B (--connect): Connects to user's existing Chrome via CDP. No new
//     browser launched, no Vite started. Attaches to the page matching the URL.
//
// In both modes, every page console event is forwarded as raw text to stdout,
// which telemetry_collector.py pipes into .trtc-telemetry/runtime.log.

import { spawn } from "node:child_process";
import { connect as tcpConnect } from "node:net";
import process from "node:process";

// ---------------------------------------------------------------------------
// Argv parsing
// ---------------------------------------------------------------------------
function parseArgv(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--url") out.url = argv[++i];
    else if (a === "--workspace") out.workspace = argv[++i];
    else if (a === "--connect") out.connect = argv[++i];
  }
  const missing = ["url", "workspace"].filter((k) => !out[k]);
  if (missing.length) {
    process.stderr.write(
      `telemetry-bridge: missing required args: ${missing.join(", ")}\n` +
        `usage: node telemetry-bridge.mjs --url <u> --workspace <path> [--connect <endpoint>]\n` +
        `\n` +
        `Modes:\n` +
        `  (default)             Launch visible Chrome + Vite dev server\n` +
        `  --connect <endpoint>  Connect to existing Chrome via CDP\n` +
        `                        e.g. --connect http://localhost:9222\n`,
    );
    process.exit(2);
  }
  return out;
}

// ---------------------------------------------------------------------------
// TCP port probe
// ---------------------------------------------------------------------------
function parsePort(url) {
  const m = url.match(/:(\d+)(?:\/|$)/);
  return m ? Number.parseInt(m[1], 10) : 80;
}

function probeTcp(host, port, timeoutMs) {
  return new Promise((resolve) => {
    const socket = tcpConnect({ host, port });
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      socket.destroy();
      resolve(ok);
    };
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
    setTimeout(() => finish(false), timeoutMs);
  });
}

async function findFreePort(host, start, span) {
  for (let p = start; p < start + span; p++) {
    const occupied = await probeTcp(host, p, 200);
    if (!occupied) return p;
  }
  return null;
}

async function waitForPort(host, port, attempts, intervalMs) {
  for (let i = 0; i < attempts; i++) {
    if (await probeTcp(host, port, intervalMs)) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Raw log emitter — outputs console text as-is, like Chrome DevTools
// ---------------------------------------------------------------------------
function emitRaw(line) {
  process.stdout.write(line + "\n");
}

// ---------------------------------------------------------------------------
// Attach console listeners to a page
// ---------------------------------------------------------------------------
function attachPageListeners(page) {
  page.on("console", (msg) => {
    let text;
    try { text = msg.text(); } catch { text = String(msg); }
    const location = msg.location();
    const source = location && location.url
      ? `${location.url.split("/").pop()}:${location.lineNumber ?? 0}`
      : "";
    const prefix = source ? `${source} ` : "";
    emitRaw(`${prefix}${text}`);
  });

  page.on("pageerror", (err) => {
    const message = err && err.message ? err.message : String(err);
    emitRaw(`[pageerror] ${message}`);
  });

  page.on("requestfailed", (req) => {
    const failure = req.failure();
    emitRaw(`[requestfailed] ${req.url()} :: ${failure ? failure.errorText : "unknown"}`);
  });
}

// ---------------------------------------------------------------------------
// Mode A: Launch visible browser + Vite dev server
// ---------------------------------------------------------------------------
async function modeVisible(puppeteer, url, workspace) {
  const host = "localhost";
  const requestedPort = parsePort(url);

  // Find free port
  const chosenPort = await findFreePort(host, requestedPort, 20);
  if (chosenPort === null) {
    emitRaw(`telemetry-bridge: no free port in [${requestedPort}, ${requestedPort + 20})`);
    process.exit(1);
  }
  if (chosenPort !== requestedPort) {
    emitRaw(`telemetry-bridge: port ${requestedPort} occupied; using ${chosenPort}`);
  }
  const targetUrl = url.replace(`:${requestedPort}`, `:${chosenPort}`);

  // Spawn Vite dev server
  const vite = spawn("npm", ["run", "dev", "--", "--port", String(chosenPort), "--strictPort"], {
    cwd: workspace,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let viteExited = false;
  vite.on("exit", (code, signal) => {
    viteExited = true;
    emitRaw(`telemetry-bridge: vite exited code=${code} signal=${signal || ""}`);
  });
  vite.stdout.resume();
  vite.stderr.on("data", (chunk) => {
    const text = chunk.toString("utf8").trimEnd();
    if (text) emitRaw(`[vite] ${text}`);
  });

  // Wait for dev server
  const ready = await waitForPort(host, chosenPort, 60, 1000);
  if (!ready || viteExited) {
    emitRaw(`telemetry-bridge: vite not ready on port ${chosenPort}`);
    try { vite.kill("SIGTERM"); } catch {}
    process.exit(1);
  }

  // Launch VISIBLE browser (headless: false)
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: false,
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
      ],
    });
  } catch (e) {
    emitRaw(`telemetry-bridge: chromium launch failed: ${e.message}`);
    try { vite.kill("SIGTERM"); } catch {}
    process.exit(1);
  }

  const page = await browser.newPage();

  // Install error probes before page load
  await page.evaluateOnNewDocument(() => {
    const tag = (probe, payload) =>
      console.log(JSON.stringify({ __probe: probe, ...payload }));
    window.addEventListener("error", (e) => {
      tag("page_error", { message: (e && e.message) || String(e), filename: e && e.filename, lineno: e && e.lineno });
    });
    window.addEventListener("unhandledrejection", (e) => {
      const reason = e && e.reason;
      tag("unhandled_rejection", { message: reason && reason.message ? reason.message : String(reason) });
    });
  });

  // Attach console listeners
  attachPageListeners(page);

  // Navigate
  try {
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
  } catch (e) {
    emitRaw(`telemetry-bridge: page.goto failed url=${targetUrl} err=${e.message}`);
  }

  emitRaw(`telemetry-bridge: [visible mode] page loaded at ${targetUrl}, capturing events...`);

  // Shutdown handler — ensure Chromium is fully closed before exit
  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    try { await browser.close(); } catch {}
    try { vite.kill("SIGTERM"); } catch {}
    // Give Vite a moment to exit gracefully, then force-kill
    await new Promise((r) => setTimeout(r, 500));
    try { if (!viteExited) vite.kill("SIGKILL"); } catch {}
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

// ---------------------------------------------------------------------------
// Mode B: Connect to existing Chrome via CDP
// ---------------------------------------------------------------------------
async function modeConnect(puppeteer, connectEndpoint, targetUrl) {
  emitRaw(`telemetry-bridge: [connect mode] connecting to ${connectEndpoint}`);

  // Connect to existing browser
  let browser;
  try {
    if (connectEndpoint.startsWith("ws://") || connectEndpoint.startsWith("wss://")) {
      browser = await puppeteer.connect({ browserWSEndpoint: connectEndpoint });
    } else {
      browser = await puppeteer.connect({ browserURL: connectEndpoint });
    }
  } catch (e) {
    emitRaw(`telemetry-bridge: failed to connect to browser at ${connectEndpoint}: ${e.message}`);
    emitRaw(`Hint: Start Chrome with --remote-debugging-port=9222`);
    process.exit(1);
  }

  emitRaw(`telemetry-bridge: connected to browser`);

  // Find the target page
  const pages = await browser.pages();
  const targetPort = parsePort(targetUrl);
  let page = pages.find((p) => {
    const u = p.url();
    return u.includes(`localhost:${targetPort}`) || u.includes(`127.0.0.1:${targetPort}`);
  });

  if (!page) {
    // Try matching by full URL
    page = pages.find((p) => p.url().includes(targetUrl));
  }

  if (!page) {
    emitRaw(`telemetry-bridge: no page found matching ${targetUrl}. Listing open pages:`);
    for (const p of pages) {
      emitRaw(`  - ${p.url()}`);
    }
    if (pages.length > 0) {
      emitRaw(`telemetry-bridge: attaching to first available page. Open ${targetUrl} in the browser to capture its events.`);
      page = pages[0];
    } else {
      emitRaw(`telemetry-bridge: no pages found in browser`);
      await browser.disconnect();
      process.exit(1);
    }
  } else {
    emitRaw(`telemetry-bridge: found target page: ${page.url()}`);
  }

  // Attach console listeners
  attachPageListeners(page);

  // Also listen for new pages (user might navigate or open new tabs)
  browser.on("targetcreated", async (target) => {
    if (target.type() === "page") {
      try {
        const newPage = await target.page();
        if (newPage) {
          const newUrl = newPage.url();
          if (newUrl.includes(`localhost:${targetPort}`) || newUrl.includes(`127.0.0.1:${targetPort}`)) {
            emitRaw(`telemetry-bridge: new matching page detected: ${newUrl}`);
            attachPageListeners(newPage);
          }
        }
      } catch {}
    }
  });

  emitRaw(`telemetry-bridge: [connect mode] capturing events from ${page.url()}...`);

  // Shutdown handler — disconnect only, don't close user's browser
  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    emitRaw(`telemetry-bridge: disconnecting (browser stays open)`);
    try { await browser.disconnect(); } catch {}
    setTimeout(() => process.exit(0), 100).unref();
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const args = parseArgv(process.argv.slice(2));
  const { url, workspace, connect: connectEndpoint } = args;

  emitRaw(`telemetry-bridge: starting (mode=${connectEndpoint ? "connect" : "visible"})`);

  // Import Puppeteer
  let puppeteer;
  try {
    puppeteer = (await import("puppeteer")).default;
  } catch (e) {
    emitRaw(`telemetry-bridge: puppeteer import failed: ${e.message}. Run \`cd runtime && npm install\`.`);
    process.exit(1);
  }

  if (connectEndpoint) {
    await modeConnect(puppeteer, connectEndpoint, url);
  } else {
    await modeVisible(puppeteer, url, workspace);
  }

  // Keep alive — shutdown is driven by SIGTERM from telemetry_collector.py
  setInterval(() => {}, 60_000).unref();
}

main().catch((e) => {
  emitRaw(`telemetry-bridge: fatal ${e && e.stack ? e.stack : e}`);
  process.exit(1);
});
