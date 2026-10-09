// Optional browser check: set DASHBOARD_CHROMIUM_PATH to a local Chromium binary.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";

if (!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile = await mkdtemp(path.join(tmpdir(), "gwg-dashboard-test-"));
const html = `<!doctype html><html><head><title>Upsell course workflow check</title></head><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {AuthProvider} from '/src/context/AuthContext.jsx';import Lead from '/src/pages/LeadDetailPage.jsx';import Mismatch from '/src/pages/UpsellMismatchPage.jsx';import MainMismatch from '/src/pages/MainCrmMismatchPage.jsx';import '/src/index.css';
const owner={assigned_to_user_id:2,assigned_to_name:'Alex Counselor',assignment_source:'MAIN_CRM'};
const learner={customer_id:1,name:'Main Person',email_id:'main@example.com'};
const lead={...owner,id:1,customer_id:1,target_code:'IGC',status:'NEW',is_active:true};
const courses=[{id:1,category_id:1,subcategory_id:1,main_category:'Safety',sub_category:'IGC',course_name:'IGC Version 2'},{id:2,category_id:1,subcategory_id:2,main_category:'Safety',sub_category:'Nebosh PSM',course_name:'Process Safety Management'}];
let info={full_name:'Main Person',email:'main@example.com'}, cases=[], changes=[], nextActivity=1;
const mainRows=[{id:7,full_name:'Main Person',email:'main@example.com',course:'IGC',counselor:'Alex Counselor',status_of_lead:'CONVERTED',updated_at:'2026-09-28T12:00:00Z',verified:false}];
if(location.search.includes('mismatch'))cases=[{...courses[0],id:1,lead_id:1,status:'CONVERTED',activities:[],converted_at:'2026-09-28T12:00:00Z',counselor:'Alex Counselor',verified:false}];
const report=(items,u)=>{const state=u.searchParams.get('state')||'pending';const filtered=items.filter(c=>state==='all'||(state==='verified'?c.verified:!c.verified));return {items:filtered,page:1,pages:1,total:filtered.length};};
window.calls=[];window.fetch=async(url,options={})=>{const u=new URL(url,location.origin);const p=u.pathname;const body=options.body?JSON.parse(options.body):{};window.calls.push({path:p,method:options.method||'GET',body});let data;
if(p==='/auth/me')data={id:1,role:location.search.includes('counselor')?'COUNSELOR':'ADMIN',display_name:'Admin'};
else if(p==='/leads/counselors')data=[{id:2,display_name:'Alex Counselor'}];
else if(p==='/leads/1')data={lead,learner,activities:[],campaigns:[]};
else if(p==='/upsell/manage/catalog')data=courses;
else if(p==='/upsell/manage/1')data={info,main_lead_id:7,suggestions:[{lead_id:1,sub_category:'IGC',stage:2,reason:'Eligible learning pathway'}],cases:cases.filter(c=>c.status!=='CONVERTED'),conversions:cases.filter(c=>c.status==='CONVERTED'),changes,conversion_total:cases.filter(c=>c.status==='CONVERTED').length,history_pages:1,main_conversions:[]};
else if(p==='/upsell/manage/1/info'){changes.unshift({id:changes.length+1,created_at:'2026-09-28T12:00:00Z',raw_data:{changes:{full_name:{from:info.full_name,to:body.full_name}},edited_by:{name:'Admin'}}});info=body;data={ok:true};}
else if(p==='/upsell/manage/1/cases'){cases.forEach(c=>c.is_current=false);const c={...courses.find(c=>c.id===body.mapping_id),id:cases.length+1,mapping_id:body.mapping_id,lead_id:1,status:'NEW',activities:[],activity_count:0,is_current:true};cases.push(c);lead.status='NEW';data={case_id:c.id};}
else if(p==='/upsell/manage/mismatch')data=report(cases.filter(c=>c.status==='CONVERTED').map(c=>({...c,name:info.full_name,email:info.email})),u);
else if(p==='/crm/leads/mismatch')data=report(mainRows,u);
else if(p==='/upsell/manage/mismatch/1/verify'||p==='/crm/leads/mismatch/7/verify'){const row=p.startsWith('/crm/')?mainRows[0]:cases[0];Object.assign(row,{verified:true,verification_source:'Admin verified enrolment',verified_by:'Admin',verified_at:'2026-09-28T12:00:00Z'});data=row;}
else {const match=p.match(/cases\\/(\\d+)\\/(activities|convert|status)(?:\\/(\\d+))?/);const c=cases.find(c=>c.id===Number(match?.[1]));if(!c)throw new Error('Unexpected request '+p);
if(match[2]==='convert'){c.status='CONVERTED';c.is_current=false;c.converted_at='2026-09-28T12:00:00Z';c.counselor='Alex Counselor';c.converted_by='Admin';lead.status='CONVERTED';}
else if(match[2]==='status'){c.status=body.status;lead.status=body.status;}
else if(match[3]){const a=c.activities.find(a=>a.id===Number(match[3]));Object.assign(a,body,{edited_by:'Admin'});}
else {c.activities.unshift({...body,id:nextActivity++,created_at:'2026-09-28T12:00:00Z',user_name:'Admin'});c.activity_count++;}data={ok:true};}
return {ok:true,json:async()=>structuredClone(data)};};
const route=location.search.includes('main-mismatch')?'/crm/mismatch':location.search.includes('mismatch')?'/upsell/mismatch':'/upsell/leads/1';
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,{initialEntries:[route]},React.createElement(AuthProvider,null,React.createElement(Routes,null,React.createElement(Route,{path:'/upsell/leads/:leadId',element:React.createElement(Lead)}),React.createElement(Route,{path:'/upsell/mismatch',element:React.createElement(Mismatch)}),React.createElement(Route,{path:'/crm/mismatch',element:React.createElement(MainMismatch)})))));
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
  await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test'});
  await waitFor("document.body.textContent.includes('Main Person') && document.body.textContent.includes('From Main CRM')");
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('h2')).slice(0,4).map(e=>e.textContent)"),['Recommended next steps','Main Person','Lead status','Select a course to begin']);
  await evaluate("window.inputValue=(selector,value)=>{const e=document.querySelector(selector);Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}));};window.selectValue=(label,value)=>{const e=document.querySelector('select[aria-label=\"'+label+'\"]');e.value=value;e.dispatchEvent(new Event('change',{bubbles:true}));};window.clickText=text=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent===text).click();clickText('Edit information')");
  await waitFor("!!document.querySelector('.profile-fields-edit input')");
  await evaluate("inputValue('.profile-fields-edit input','Upsell Person');clickText('Save changes')");
  await waitFor("document.body.textContent.includes('Upsell Person') && !document.querySelector('.profile-fields-edit')");
  await evaluate("clickText('Show edit history')");
  await waitFor("document.body.textContent.includes('Information edited by Admin') && document.body.textContent.includes('Main Person')");
  await evaluate("clickText('Hide edit history');selectValue('Main category','Safety');");
  await waitFor("!document.querySelector('select[aria-label=\"Subcategory\"]').disabled");
  await evaluate("selectValue('Subcategory','IGC')");
  await waitFor("!document.querySelector('select[aria-label=\"Course\"]').disabled");
  await evaluate("selectValue('Course','1')");
  await waitFor("!document.querySelector('#upsell-contact-form fieldset').disabled");
  await evaluate("selectValue('Course lead status','IN_CONTACT')");
  await waitFor("!!document.querySelector('[role=dialog][aria-label=\"Explain status change\"]')");
  assert.equal(await evaluate("window.calls.filter(c=>c.path.endsWith('/cases/1/status')).length"),0,'Upsell status waits for a note');
  await evaluate("inputValue('[role=dialog] textarea','Spoke about the IGC schedule');document.querySelector('[role=dialog] button[type=submit]').click()");
  await waitFor("window.calls.some(c=>c.path.endsWith('/cases/1/status')) && !document.querySelector('[role=dialog]')");
  assert.deepEqual(await evaluate("window.calls.find(c=>c.path.endsWith('/cases/1/status')).body"),{status:'IN_CONTACT',note:'Spoke about the IGC schedule'});
  await evaluate("inputValue('#upsell-contact-form textarea','IGC contact note');clickText('Save contact')");
  await waitFor("!!document.querySelector('.activity-card') && document.querySelector('.activity-card').textContent.includes('IGC contact note')");
  await evaluate("document.querySelector('.upsell-activity-heading button').click()");
  await evaluate("inputValue('#upsell-contact-form textarea','IGC edited note');clickText('Save changes')");
  await waitFor("document.querySelector('.activity-card').textContent.includes('IGC edited note')");
  await evaluate("inputValue('#upsell-contact-form textarea','Agreed to IGC enrolment');clickText('Update converted')");
  await waitFor("document.querySelectorAll('.upsell-converted-card').length===1 && document.querySelector('select[aria-label=\"Course\"]').value===''");
  assert.equal(await evaluate("document.querySelector('#upsell-contact-form fieldset').disabled"),true);
  await evaluate("selectValue('Main category','Safety');");
  await evaluate("selectValue('Subcategory','Nebosh PSM')");
  await evaluate("selectValue('Course','2')");
  await waitFor("!document.querySelector('#upsell-contact-form fieldset').disabled && document.querySelector('#upsell-contact-form h2').textContent==='Process Safety Management'");
  assert.ok(await evaluate("!document.querySelector('#upsell-contact-form').textContent.includes('IGC edited note')"),'Contact histories stay separate');
  await evaluate("inputValue('#upsell-contact-form textarea','PSM contact note');clickText('Save contact')");
  await waitFor("document.querySelector('#upsell-contact-form').textContent.includes('PSM contact note')");
  await evaluate("inputValue('#upsell-contact-form textarea','Agreed to PSM enrolment');clickText('Update converted')");
  await waitFor("document.querySelectorAll('.upsell-converted-card').length===2");
  assert.ok(await evaluate("!window.calls.some(c=>c.path.startsWith('/crm/') && c.method!=='GET')"),'Upsell edits do not write Main CRM');
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await mkdir('../outputs',{recursive:true});await writeFile('../outputs/upsell-manage-review.png',Buffer.from(screenshot.data,'base64'));
  await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test?mismatch'});
  await waitFor("!!document.querySelector('.verification-tick.pending') && document.body.textContent.includes('Verify enrolment')");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Verify enrolment').click()");
  await waitFor("document.body.textContent.includes('Verified as enrolled')");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Show verified records').click()");
  await waitFor("!!document.querySelector('.verification-tick.verified')");
  assert.ok(await evaluate("document.querySelector('.verification-cell').textContent.includes('Admin')"));
  assert.equal(await evaluate("window.calls.filter(c=>c.method==='POST'&&c.path==='/upsell/manage/mismatch/1/verify').length"),1);

  await waitFor("!!document.querySelector('.verification-tick.verified') && !document.body.textContent.includes('Verify enrolment')");
  await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test?main-mismatch'});
  await waitFor("!!document.querySelector('.verification-tick.pending') && document.body.textContent.includes('Verify enrolment')");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Verify enrolment').click()");
  await waitFor("document.body.textContent.includes('Verified as enrolled')");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Show verified records').click()");
  await waitFor("!!document.querySelector('.verification-tick.verified')");
  assert.equal(await evaluate("window.calls.filter(c=>c.method==='POST'&&c.path==='/crm/leads/mismatch/7/verify').length"),1);
  const verificationScreenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await writeFile('../outputs/verification-review.png',Buffer.from(verificationScreenshot.data,'base64'));
  await send('Page.navigate',{url:'http://127.0.0.1:5189/__dashboard_test?mismatch&counselor'});
  await waitFor("!!document.querySelector('.verification-tick.pending')");
  assert.ok(await evaluate("!document.body.textContent.includes('Verify enrolment')"),'Counselors cannot verify');
  console.log('Upsell browser workflow passed: section order, local info edits/history, all three course selectors, contact save/edit, isolated course histories, two conversions, empty next panel, Main/Upsell verification, green/gray ticks, verified filter and counselor restrictions.');
} finally {
  socket?.close(); browser.kill(); await server.close();
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  assert.ok(path.resolve(profile).startsWith(`${path.resolve(tmpdir())}${path.sep}`) && path.basename(profile).startsWith("gwg-dashboard-test-"));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
