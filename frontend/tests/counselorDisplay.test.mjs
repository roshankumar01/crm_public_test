// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const html = `<!doctype html><html><head><title>Counselor check</title></head><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {AuthProvider} from '/src/context/AuthContext.jsx';
import Search from '/src/pages/LearnersCrmSearchPage.jsx';import Detail from '/src/pages/LearnersCrmDetailPage.jsx';
import Learners from '/src/pages/LearnersPage.jsx';import Contact from '/src/pages/LearnerDetailPage.jsx';
import Pipeline from '/src/pages/OpportunitiesPage.jsx';import Lead from '/src/pages/LeadDetailPage.jsx';import '/src/index.css';
const owner={assigned_to_user_id:2,assigned_to_name:'Alex Counselor',assigned_to_email:'alex@example.com',assignment_source:'MAIN_CRM'};
const learner={...owner,id:1,customer_id:1,name:'Learner Example',learner_name:'Learner Example',email_id:'learner@example.com',enrolments:[]};
const lead={...owner,id:1,lead_id:1,customer_id:1,name:'Learner Example',target_code:'IGC',target_name:'IGC',status:'NEW',is_active:true};
window.fetch=async url=>{const p=new URL(url,location.origin).pathname;let data;
if(p==='/auth/me')data={id:1,role:'ADMIN',display_name:'Admin'};
else if(p==='/leads/counselors')data=[{id:2,display_name:'Alex Counselor'}];
else if(p==='/upsell/manage/catalog')data=[];
else if(p==='/upsell/manage/1')data={info:{full_name:'Learner Example'},cases:[],suggestions:[],conversions:[],changes:[],main_conversions:[]};
else if(p==='/opportunities')data={summary:{new:1},sections:[]};
else if(p==='/leads')data={items:[lead],page:1,pages:1,total:1};
else if(p==='/leads/1')data={lead,learner,activities:[],campaigns:[]};
else if(p==='/learners/contacts')data={items:[learner],page:1,pages:1,total:1};
else if(p==='/learners/contacts/1')data={learner,passed_courses:[],recommendations:[],timeline:[],campaigns:[]};
else if(p==='/learners-crm/learners')data=[learner];
else data=learner;
return {ok:true,json:async()=>data};};
const mode=new URLSearchParams(location.search).get('mode')||'pipeline';
const pages={pipeline:['/pipeline',Pipeline],search:['/search',Search],detail:['/detail/1',Detail],learners:['/learners',Learners],contact:['/contact/1',Contact],lead:['/lead/1',Lead]};
const paths={pipeline:'/pipeline',search:'/search',detail:'/detail/:learnerId',learners:'/learners',contact:'/contact/:customerId',lead:'/lead/:leadId'};
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,{initialEntries:[pages[mode][0]]},React.createElement(AuthProvider,null,React.createElement(Routes,null,React.createElement(Route,{path:paths[mode],element:React.createElement(pages[mode][1])})))));
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
  for (const mode of ['pipeline','search','detail','learners','contact','lead']) {
    await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test?mode='+mode});
    await waitFor("document.body.textContent.includes('Alex Counselor') && !document.body.textContent.includes('Loading')");
    assert.ok(await evaluate("document.body.textContent.includes('Counselor')"), mode+' shows counselor');
    if (['pipeline','search','learners','lead'].includes(mode)) assert.ok(await evaluate("document.body.textContent.includes('Main CRM')"),mode+' indicates assignment source');
    if (mode==='detail') assert.ok(await evaluate("document.body.textContent.includes('alex@example.com')"));
  }
  console.log('Counselor browser checks passed for both learner lists, both profiles, Upsell pipeline and lead details.');
} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
