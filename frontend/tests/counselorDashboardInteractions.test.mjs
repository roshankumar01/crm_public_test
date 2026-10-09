import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdtemp, mkdir, rm, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {createServer} from "vite";

if(!process.env.DASHBOARD_CHROMIUM_PATH) throw new Error("Set DASHBOARD_CHROMIUM_PATH to run the browser check.");
const profile=await mkdtemp(path.join(tmpdir(),"gwg-counselor-dashboard-"));
const html=`<!doctype html><html><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter,Routes,Route} from 'react-router-dom';
import Page from '/src/pages/CounselorDashboardPage.jsx';import '/src/index.css';
window.calls=[];window.fetch=async url=>{const u=new URL(url,location.origin);window.calls.push(u.pathname+u.search);let data;
if(u.pathname.endsWith('/changes')){const unique=u.searchParams.get('mode')==='unique';const person=u.searchParams.has('person');data={counselor:{id:2,name:'Alex'},total:unique?1:person?3:1,page:1,pages:1,items:[{id:9,workspace:'upsell',lead_id:7,lead_name:'Learner A',course:'IGC',action_type:'CONTACT_EDIT',before_note:'Discussed course dates',after_note:'.',actor_name:'Alex',person_key:'customer:1',person_updates:unique?3:null,created_at:'2026-10-06T09:00:00Z'}]};}
else data={cards:{leads_given:4,total_updates:5,main_updates:3,upsell_updates:2,unique_people:1,unique_main_people:1,unique_upsell_people:1},counselors:[{id:2,name:'Alex',leads_given:4,total_updates:5,main_updates:3,upsell_updates:2,unique_people:1,unique_main_people:1,unique_upsell_people:1,active:true},{id:3,name:'Ben',leads_given:0,total_updates:0,main_updates:0,upsell_updates:0,unique_people:0,unique_main_people:0,unique_upsell_people:0,active:true}]};
return {ok:true,json:async()=>data};};
createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,{initialEntries:['/dashboard/counselors']},React.createElement(Routes,null,React.createElement(Route,{path:'/dashboard/counselors',element:React.createElement(Page,{section:'overview'})}),React.createElement(Route,{path:'/dashboard/counselors/changes',element:React.createElement(Page,{section:'changes'})}))));
</script></body></html>`;
const server=await createServer({server:{host:"127.0.0.1",port:5191,strictPort:true},plugins:[{name:"counselor-dashboard-test",configureServer(dev){dev.middlewares.use("/__counselor_test",async(_req,res)=>{res.setHeader("Content-Type","text/html");res.end(await dev.transformIndexHtml("/__counselor_test",html));});}}]});
await server.listen();
const browser=spawn(process.env.DASHBOARD_CHROMIUM_PATH,["--headless","--no-sandbox","--disable-gpu","--remote-debugging-port=9231",`--user-data-dir=${profile}`,"about:blank"],{windowsHide:true,stdio:"ignore"});
let socket;const delay=ms=>new Promise(r=>setTimeout(r,ms));
try{
  let target;for(let i=0;i<60;i++){try{target=(await(await fetch("http://127.0.0.1:9231/json/list")).json())[0];if(target)break;}catch{}await delay(100);}assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener("open",r,{once:true}));let id=0;const pending=new Map();
  socket.addEventListener("message",e=>{const result=JSON.parse(e.data);if(result.method==="Runtime.exceptionThrown")console.error(JSON.stringify(result.params));if(result.id){pending.get(result.id)?.(result);pending.delete(result.id);}});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,r=>r.error?reject(new Error(JSON.stringify(r.error))):resolve(r.result));socket.send(JSON.stringify({id:key,method,params}));});
  const evaluate=async expression=>{const r=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const waitFor=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(50);}throw new Error(`Timed out: ${expression}`);};
  await send("Runtime.enable");await send("Page.navigate",{url:"http://127.0.0.1:5191/__counselor_test"});
  await waitFor("document.body.textContent.includes('Work by counselor')");
  assert.equal(await evaluate("document.querySelectorAll('.co-metric').length"),4);
  assert.equal(await evaluate("document.querySelectorAll('.co-chart-group').length"),2);
  assert.ok(await evaluate("document.body.textContent.includes('Unique people updated: 1')"));
  await send("Emulation.setDeviceMetricsOverride",{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await mkdir("../outputs",{recursive:true});
  let screenshot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
  await writeFile("../outputs/counselor-dashboard-overview.png",Buffer.from(screenshot.data,"base64"));
  await evaluate("Array.from(document.querySelectorAll('.co-chart-toggle button')).find(b=>b.textContent==='Upsell').click()");
  assert.equal(await evaluate("document.querySelectorAll('.co-chart-group .co-upsell').length"),2);
  await evaluate("Array.from(document.querySelectorAll('[aria-label=\"Update counting\"] button')).find(b=>b.textContent==='Unique people').click()");
  assert.ok(await evaluate("document.querySelector('.co-chart-group').getAttribute('aria-label').includes('1 unique people')"));
  await evaluate("document.querySelector('.co-chart-group').click()");
  await waitFor("!!document.querySelector('.co-change-card')");
  assert.ok(await evaluate("document.body.textContent.includes('Discussed course dates') && document.body.textContent.includes('Very short note')"));
  assert.ok(await evaluate("window.calls.some(c=>c.includes('counselor_id=2'))"));
  await evaluate("Array.from(document.querySelectorAll('[aria-label=\"Change log filter\"] button')).find(b=>b.textContent==='Unique people').click()");
  await waitFor("window.calls.some(c=>c.includes('mode=unique')) && !!document.querySelector('.co-view-person')");
  await evaluate("document.querySelector('.co-view-person').click()");
  await waitFor("window.calls.some(c=>c.includes('person=customer%3A1')) && document.body.textContent.includes('Back to unique people')");
  screenshot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
  await writeFile("../outputs/counselor-dashboard-change-log.png",Buffer.from(screenshot.data,"base64"));
  await evaluate("document.querySelector('.cd-date-trigger').click()");
  await waitFor("!!document.querySelector('.cd-date-popover')");
  await evaluate("Array.from(document.querySelectorAll('.cd-date-presets button')).find(b=>b.textContent==='Today').click()");
  await waitFor("window.calls.filter(c=>c.includes('period=custom')).length>=4");
  console.log("Counselor dashboard browser flow passed: metrics, all counselors, chart breakdown, drilldown, note comparison, short-note flag, date filter.");
}finally{socket?.close();browser.kill();await server.close();await new Promise(r=>browser.exitCode!==null?r():browser.once("exit",r));await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:100});}
