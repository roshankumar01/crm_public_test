// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const counselors = Array.from({ length: 10 }, (_, i) => ({ id: i + 1, name: `Counselor ${i + 1}`, count: 100 - i * 5, converted: 100 - i * 5, leads: 140 - i * 5 }));
const html = `<!doctype html><html><head><title>Dashboard interaction check</title></head><body><div id="root"></div><script type="module">
import React from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import Dashboard from '/src/pages/CompanyDashboardPage.jsx';
import '/src/index.css';
sessionStorage.clear(); window.calls=[];
window.fetch=async url=>{window.calls.push(String(url));return {ok:true,json:async()=>String(url).includes('/sales/courses')?Array.from({length:10},(_,i)=>({name:'Course '+(i+1),count:10})):String(url).includes('/sales/sources')?[{name:'Website',count:7},{name:'Direct call',count:3}]:{cards:{converted:775,leads:1175,conversion_rate:66,unassigned:0},counselors:${JSON.stringify(counselors)},decomposition:${JSON.stringify(counselors)}}};};
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,null,React.createElement(Dashboard,{section:'sales'})));
</script></body></html>`;
const server = await createServer({ server: { host: "127.0.0.1", port: 5189, strictPort: true }, plugins: [{ name: "dashboard-test-page", configureServer(dev) {
  dev.middlewares.use("/__dashboard_test", async (req, res) => { res.setHeader("Content-Type", "text/html"); res.end(await dev.transformIndexHtml("/__dashboard_test", html)); });
} }] });
await server.listen();
const browser = spawn(process.env.DASHBOARD_CHROMIUM_PATH, ["--headless", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9229", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
let socket;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  let target;
  for (let i = 0; i < 60; i++) { try { target = (await (await fetch("http://127.0.0.1:9229/json/list")).json())[0]; if (target) break; } catch {} await delay(100); }
  assert.ok(target, "Chromium started");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise(resolve => socket.addEventListener("open", resolve, { once: true }));
  let id = 0; const pending = new Map();
  socket.addEventListener("message", event => { const result = JSON.parse(event.data); if (result.method === "Runtime.exceptionThrown") console.error(JSON.stringify(result.params)); if (result.id) { pending.get(result.id)?.(result); pending.delete(result.id); } });
  const send = (method, params = {}) => new Promise((resolve, reject) => { const key = ++id; pending.set(key, result => result.error ? reject(new Error(JSON.stringify(result.error))) : resolve(result.result)); socket.send(JSON.stringify({ id: key, method, params })); });
  const evaluate = async expression => { const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  const waitFor = async expression => { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await delay(50); } console.error(await evaluate("document.body.innerText")); throw new Error(`Timed out: ${expression}`); };
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: 1700, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: "http://127.0.0.1:5189/__dashboard_test" });
  await waitFor("document.querySelectorAll('button.cd-flow-card').length===8");
  assert.equal(await evaluate("window.calls.filter(url=>url.includes('/sales/courses')).length"), 0, "Branches are not requested on initial load");
  await evaluate("document.querySelector('button.cd-flow-card').click()");
  await waitFor("document.querySelectorAll('button.cd-flow-card').length===16");
  assert.equal(await evaluate("window.calls.filter(url=>url.includes('/sales/sources')).length"), 0);
  await evaluate("[...document.querySelectorAll('button.cd-flow-card')].find(el=>el.textContent.includes('Course 1')).click()");
  await waitFor("document.querySelector('.cd-flow-stage').textContent.includes('Website')");
  await evaluate("document.querySelector('.cd-date-trigger').click()");
  await waitFor("!!document.querySelector('.cd-date-popover')");
  const callsBeforeApply = await evaluate("window.calls.length");
  await evaluate("document.querySelector('.cd-date-apply').click()");
  assert.equal(await evaluate("!!document.querySelector('.cd-date-error')"), true, "Incomplete dates are rejected");
  assert.equal(await evaluate("window.calls.length"), callsBeforeApply, "Invalid ranges do not make requests");
  await evaluate("document.querySelector('.cd-date-trigger').click()");
  await evaluate("document.querySelector('.cd-date-trigger').click()");
  const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  await mkdir("../outputs", { recursive: true });
  await writeFile("../outputs/dashboard-review.png", Buffer.from(screenshot.data, "base64"));
  await evaluate("[...document.querySelectorAll('.cd-date-presets button')].find(el=>el.textContent==='Last 7 days').click()");
  await waitFor("window.calls.some(url=>url.includes('start_date=')&&url.includes('end_date='))");
  assert.equal(await evaluate("document.querySelectorAll('button.cd-flow-card').length"), 8, "Changing dates resets branches");
  await evaluate("document.querySelector('.cd-date-trigger').click()");
  await evaluate("document.querySelector('.cd-date-apply').click()");
  assert.equal(await evaluate("!!document.querySelector('.cd-date-error')"), false);
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.ok(await evaluate("document.querySelector('.cd-flow-scroll').scrollWidth>document.querySelector('.cd-flow-scroll').clientWidth"), "Tree scrolls horizontally on small screens");
  console.log("Dashboard browser checks passed: lazy branches, date ranges, branch reset, and mobile scrolling.");
} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
