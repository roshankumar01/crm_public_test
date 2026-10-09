// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const html = `<!doctype html><html><head><title>Total CRM reset check</title></head><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import Reset from '/src/components/UploadReset.jsx';import '/src/index.css';
window.calls=[];window.resetCount=0;
window.fetch=async(url,options={})=>{const p=new URL(url,location.origin).pathname;window.calls.push({p,method:options.method||'GET',body:options.body?JSON.parse(options.body):null});
if(p==='/uploads/reset-options')return {ok:true,json:async()=>[]};
if(p==='/uploads/reset-all')return {ok:true,json:async()=>({all_data_reset:true,uploads_deleted:0})};
throw new Error('Unexpected request '+p);};
createRoot(document.getElementById('root')).render(React.createElement(Reset,{onReset:()=>window.resetCount++}));
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
  await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test'});
  await waitFor("document.body.textContent.includes('Reset CRM data')");
  await evaluate("window.clickText=text=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent===text).click();window.selectMode=value=>{const e=document.querySelector('select[aria-label=\"Reset scope\"]');e.value=value;e.dispatchEvent(new Event('change',{bubbles:true}));};clickText('Data reset')");
  await waitFor("!!document.querySelector('[role=dialog]')");
  assert.equal(await evaluate("document.querySelector('select').value"),'all');
  assert.equal(await evaluate("document.querySelector('.upload-reset-delete').disabled"),true);
  await evaluate("selectMode('selected')");
  await waitFor("document.body.textContent.includes('No uploaded files are available')");
  assert.equal(await evaluate("document.querySelector('.upload-reset-delete').disabled"),true);
  await evaluate("selectMode('all')");
  await evaluate("const input=document.querySelector('.upload-reset-confirmation');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'RESET ALL CRM DATA');input.dispatchEvent(new Event('input',{bubbles:true}));");
  await waitFor("!document.querySelector('.upload-reset-delete').disabled");
  await evaluate("clickText('Reset all CRM data')");
  await waitFor("document.body.textContent.includes('All CRM data cleared') && window.resetCount===1");
  assert.deepEqual(await evaluate("window.calls.filter(c=>c.method==='POST')"),[{p:'/uploads/reset-all',method:'POST',body:{confirmation:'RESET ALL CRM DATA'}}]);
  assert.equal(await evaluate("!!document.querySelector('[role=dialog]')"),false);
  console.log('Total reset browser checks passed: no uploads required, scope selection, typed confirmation, correct endpoint, success and refresh.');
} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
