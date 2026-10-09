// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const html = `<!doctype html><html><head><title>Counselor reminder check</title></head><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter} from 'react-router-dom';import {AuthProvider} from '/src/context/AuthContext.jsx';import Page from '/src/pages/RemindersPage.jsx';import Control from '/src/components/ReminderControl.jsx';import '/src/index.css';
window.calls=[];const workspace=location.search.includes('upsell')?'upsell':'main';
let reminder={id:1,lead_id:7,due_date:'2026-10-01',remaining_days:3,overdue_days:0,due_now:false,notes:'Call about the course',completed_at:null,name:'Jordan Learner',email:'jordan@example.com',phone:'5551234',course:'IGC',counselor:'Alex Counselor'};
window.fetch=async(url,options={})=>{const u=new URL(url,location.origin),p=u.pathname,body=options.body?JSON.parse(options.body):null;window.calls.push({p,method:options.method||'GET',body});let data;
if(p==='/auth/me')data={id:2,role:'COUNSELOR',display_name:'Alex Counselor'};
else if(p==='/reminders/'+workspace){const view=u.searchParams.get('view');const include=view==='completed'?!!reminder.completed_at:view==='due'?reminder.due_now:!reminder.completed_at;data={items:include?[reminder]:[],total:include?1:0,page:1,pages:1,today:'2026-09-28',counts:{due:reminder.due_now&&!reminder.completed_at?1:0,upcoming:!reminder.due_now&&!reminder.completed_at?1:0,completed:reminder.completed_at?1:0}};}
else if(p==='/reminders/'+workspace+'/7/complete'){reminder={...reminder,completed_at:'2026-09-28T12:00:00Z',due_now:false};data=reminder;}
else if(p==='/reminders/'+workspace+'/7'&&options.method==='PUT'){reminder={...reminder,remaining_days:body.days,notes:body.notes,completed_at:null,due_now:body.days===0,due_date:body.days===0?'2026-09-28':'2026-10-05'};data=reminder;}
else if(p==='/reminders/'+workspace+'/7')data={reminder,today:'2026-09-28'};
else throw new Error('Unexpected request '+p);
return {ok:true,json:async()=>structuredClone(data)};};
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,null,React.createElement(AuthProvider,null,React.createElement(Page,{workspace}))));
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
  await send('Emulation.setDeviceMetricsOverride',{width:1450,height:1000,deviceScaleFactor:1,mobile:false});
  for(const workspace of ['main','upsell']){
    await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test?'+workspace});
    await waitFor("document.body.textContent.includes('Jordan Learner') && document.body.textContent.includes('My reminders')");
    assert.ok(await evaluate("document.body.textContent.includes('3 days remaining')"));
    assert.equal(await evaluate("window.calls.filter(c=>c.p.endsWith('/7')).length"),0,'No per-lead fetch until reminder opens');
    assert.equal(await evaluate("!!document.querySelector('select[aria-label=\"Reminder counselor\"]')"),false,'Counselor cannot choose another owner');
    await evaluate("document.querySelector('.reminder-open').click()");
    await waitFor("!!document.querySelector('[role=dialog]') && !document.querySelector('input[aria-label=\"Reminder days\"]').disabled");
    await evaluate("Array.from(document.querySelectorAll('.reminder-presets button')).find(b=>b.textContent==='Today').click()");
    await evaluate("document.querySelector('.reminder-dialog button[type=submit]').click()");
    await waitFor("!document.querySelector('[role=dialog]') && document.body.textContent.includes('Contact today') && document.body.textContent.includes('1 lead to contact now')");
    assert.equal(await evaluate("window.calls.find(c=>c.method==='PUT').body.days"),0);
    await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Mark done').click()");
    await waitFor("document.body.textContent.includes('No reminders in this view')");
    await evaluate("{const e=document.querySelector('select[aria-label=\"Reminder view\"]');e.value='completed';e.dispatchEvent(new Event('change',{bubbles:true}));}");
    await waitFor("document.body.textContent.includes('Jordan Learner') && !!document.querySelector('.reminder-status.done')");
    await evaluate("document.querySelector('.reminder-open').click()");
    await waitFor("!!document.querySelector('[role=dialog]') && !document.querySelector('input[aria-label=\"Reminder days\"]').disabled");
    await evaluate("Array.from(document.querySelectorAll('.reminder-presets button')).find(b=>b.textContent==='7 days').click()");
    await waitFor("document.querySelector('input[aria-label=\"Reminder days\"]').value==='7'");
    await evaluate("document.querySelector('.reminder-dialog button[type=submit]').click()");
    await waitFor("!document.querySelector('[role=dialog]') && document.body.textContent.includes('No reminders in this view')");
    await evaluate("{const e=document.querySelector('select[aria-label=\"Reminder view\"]');e.value='pending';e.dispatchEvent(new Event('change',{bubbles:true}));}");
    await waitFor("document.body.textContent.includes('7 days remaining')");
    assert.equal(await evaluate("document.querySelector('a.text-link').getAttribute('href')"),workspace==='main'?'/crm/leads/7':'/upsell/leads/7');
  }
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await mkdir('../outputs',{recursive:true});await writeFile('../outputs/reminders-review.png',Buffer.from(screenshot.data,'base64'));
  console.log('Reminder browser checks passed in Main/Upsell: counselor scope, countdown, today alert, save, done, reschedule, profile links and on-demand lead reads.');
} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
