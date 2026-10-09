// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const html = `<!doctype html><html><head><title>Pipeline check</title></head><body><div id="root"></div><script type="module">
import React from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,useLocation} from 'react-router-dom';
import MainCrmPage from '/src/pages/MainCrmPage.jsx';
import CustomerLifecycle from '/src/components/CustomerLifecycle.jsx';
import {AuthProvider} from '/src/context/AuthContext.jsx';
import '/src/index.css';
window.calls=[];window.statusUpdates=[];
const leads=Array.from({length:3},(_,i)=>({id:i+1,full_name:['Asha Kumar','Rahul Sharma','Meera Nair'][i],email:'learner'+i+'@example.com',phone_number:'9876543210',source:['Website','Phone','LinkedIn'][i],source_category:'INFO_EMAIL_LEADS',course:['NEBOSH IGC','NEBOSH IDIP','IOSH MS'][i],region:'India',status_of_lead:['NEW','FOLLOW_UP','CONVERTED'][i],assigned_to_user_id:i%2+1,created_at:'2026-01-0'+(i+1)+'T10:30:00Z',updated_at:'2026-03-0'+(i+1)+'T12:00:00Z'}));
window.fetch=async (url,init={})=>{window.calls.push(String(url));const u=new URL(url,location.origin);let data;
if(u.pathname==='/auth/me')data={id:1,role:'ADMIN',display_name:'Admin'};
else if(u.pathname==='/crm/leads/1/status' && init.method==='PATCH'){const body=JSON.parse(init.body);window.statusUpdates.push(body);leads[0].status_of_lead=body.status;data={id:1,status_of_lead:body.status};}
else if(u.pathname==='/leads/counselors')data=[{id:1,display_name:'Alex'},{id:2,display_name:'Ben'}];
else if(u.pathname==='/crm/leads/summary')data={total:3,source_category_counts:{INFO_EMAIL_LEADS:3}};
else if(u.pathname==='/crm/leads/filter-options')data={counselors:[{value:'1',label:'Alex',count:2},{value:'2',label:'Ben',count:1}],statuses:[{value:'NEW',label:'NEW',count:1},{value:'CONVERTED',label:'CONVERTED',count:1}],sources:[{value:'Website',label:'Website',count:1},{value:'Phone',label:'Phone',count:1}],courses:[{value:'NEBOSH IGC',label:'NEBOSH IGC',count:1},{value:'NEBOSH IDIP',label:'NEBOSH IDIP',count:1}]};
else data={items:leads,total:3,page:Number(u.searchParams.get('page')||1),pages:1};
return {ok:true,json:async()=>data};};
function Probe(){const loc=useLocation();React.useEffect(()=>{window.pipelineLocation=loc.search},[loc]);return null;}
const lifecycle={events:[{key:'igc',kind:'RESULT',title:'IGC',source_label:'Result data IGC',status:'PASS',date:'2026-01-01',fields:{}},{key:'id1',kind:'RESULT',title:'ID1',source_label:'Result data IDP',status:'REFER',date:'2026-02-01',fields:{}}]};
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,{initialEntries:['/crm/leads']},React.createElement(AuthProvider,null,React.createElement(Probe),React.createElement(MainCrmPage),React.createElement('div',{className:'page'},React.createElement(CustomerLifecycle,{lifecycle})))));
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
  await waitFor("!!document.querySelector('.crm-dated-table') && window.calls.some(u=>u.includes('/filter-options'))");
  assert.equal(await evaluate("document.querySelectorAll('.crm-date-sort').length"),2);
  assert.ok(await evaluate("document.body.textContent.includes('Result data IGC') && document.body.textContent.includes('Result data IDP')"));
  const count=await evaluate("window.calls.filter(u=>new URL(u).pathname==='/crm/leads').length");
  await evaluate("document.querySelector('[aria-label=\"Counselors filter\"]').click()");
  await waitFor("document.querySelectorAll('.lead-filter-option-list input').length===2");
  await evaluate("document.querySelector('.lead-filter-option-list input').click()");
  assert.equal(await evaluate("window.calls.filter(u=>new URL(u).pathname==='/crm/leads').length"),count,'Selecting a filter waits for Apply');
  await evaluate("document.body.dispatchEvent(new Event('pointerdown',{bubbles:true}));document.querySelector('.crm-filter-grid>.primary-button').click()");
  await waitFor("window.calls.some(u=>u.includes('counselor_ids=1'))");
  assert.ok(await evaluate("window.pipelineLocation.includes('counselor=1')"));
  await evaluate("document.querySelector('[aria-label=\"Sort by created date\"]').click()");
  await waitFor("window.calls.some(u=>u.includes('sort_by=created_at')&&u.includes('sort_direction=desc'))");
  await evaluate("document.querySelector('[aria-label=\"Sort by created date\"]').click()");
  await waitFor("window.calls.some(u=>u.includes('sort_by=created_at')&&u.includes('sort_direction=asc'))");
  await evaluate("document.querySelector('[aria-label=\"Courses filter\"]').click()");
  const beforeSearch=await evaluate("window.calls.length");
  await evaluate("const input=document.querySelector('[aria-label=\"Search courses options\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'IDIP');input.dispatchEvent(new Event('input',{bubbles:true}))");
  await waitFor("document.querySelectorAll('.lead-filter-option-list label').length===1");
  assert.equal(await evaluate("window.calls.length"),beforeSearch,'Option search is local');
  await evaluate("document.body.dispatchEvent(new Event('pointerdown',{bubbles:true}));const select=document.querySelector('tbody tr:first-child select[aria-label=\"Lead status\"]');select.value='HOT';select.dispatchEvent(new Event('change',{bubbles:true}));");
  await waitFor("!!document.querySelector('[role=dialog][aria-label=\"Explain status change\"]')");
  assert.equal(await evaluate("window.statusUpdates.length"),0,'Changing the select alone does not update status');
  await evaluate("const note=document.querySelector('[role=dialog] textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(note,'Discussed course and fees');note.dispatchEvent(new Event('input',{bubbles:true}));");
  await waitFor("!document.querySelector('[role=dialog] button[type=submit]').disabled");
  await evaluate("document.querySelector('[role=dialog] button[type=submit]').click()");
  await waitFor("window.statusUpdates.length===1 && !document.querySelector('[role=dialog]')");
  assert.deepEqual(await evaluate("window.statusUpdates[0]"),{status:'HOT',note:'Discussed course and fees'});
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await mkdir('../outputs',{recursive:true});await writeFile('../outputs/pipeline-review.png',Buffer.from(screenshot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert.ok(await evaluate("document.querySelector('.pipeline-table').scrollWidth>document.querySelector('.pipeline-table').clientWidth"));
  console.log('Pipeline browser checks passed: result labels, explicit filter apply, local option search, date sorting, URL state, and mobile scrolling.');

} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
