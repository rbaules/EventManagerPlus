"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "assets", "recovery_supervisor.js"),
  "utf8"
);

function createBrowser(pathname) {
  const listeners = new Map();
  const documentListeners = new Map();
  const values = new Map();
  let reloads = 0;
  const storage = {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
  };
  const window = {
    location: {pathname, reload: () => { reloads += 1; }},
    crypto: {randomUUID: () => "12345678-1234-1234-1234-123456789abc"},
    addEventListener: (name, callback) => listeners.set(name, callback),
    setTimeout,
    clearTimeout,
  };
  const document = {
    visibilityState: "visible",
    addEventListener: (name, callback) => documentListeners.set(name, callback),
  };
  const navigator = {onLine: true};
  const fetchCalls = [];
  const context = {
    window,
    document,
    navigator,
    sessionStorage: storage,
    AbortController,
    Date,
    Math,
    Promise,
    fetch: async (url, options) => {
      fetchCalls.push({url, options});
      return {status: url === "/health" ? 200 : 204};
    },
  };
  vm.runInNewContext(source, context, {filename: "recovery_supervisor.js"});
  return {
    listeners,
    documentListeners,
    navigator,
    values,
    fetchCalls,
    reloads: () => reloads,
  };
}

async function delay(milliseconds) {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function testSingleRescueReload() {
  const browser = createBrowser("/app/llegadas");
  browser.navigator.onLine = false;
  browser.listeners.get("offline")();
  assert.equal(browser.values.get("evp_network_outage"), "1");
  assert.equal(browser.reloads(), 0);

  browser.navigator.onLine = true;
  browser.listeners.get("online")();
  browser.listeners.get("online")();
  browser.documentListeners.get("visibilitychange")();
  await delay(2800);

  assert.equal(browser.reloads(), 1);
  assert.equal(browser.values.get("evp_rescue_reload_done"), "1");
  assert.equal(
    browser.fetchCalls.filter((call) => call.url === "/health").length,
    1
  );
  assert.ok(browser.fetchCalls.every((call) => call.options.credentials === "omit"));

  browser.listeners.get("online")();
  await delay(2700);
  assert.equal(browser.reloads(), 1);
}

async function testProtectedRoutes() {
  for (const pathname of ["/", "/auth/callback", "/auth/callback/"]) {
    const browser = createBrowser(pathname);
    browser.navigator.onLine = false;
    browser.listeners.get("offline")();
    browser.navigator.onLine = true;
    browser.listeners.get("online")();
    await delay(20);
    assert.equal(browser.reloads(), 0);
    assert.equal(browser.fetchCalls.length, 0);
  }
}

(async () => {
  await testSingleRescueReload();
  await testProtectedRoutes();
  console.log("OK - one rescue reload, event deduplication and protected routes passed.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
