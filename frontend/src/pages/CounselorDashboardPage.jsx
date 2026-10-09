import {useEffect, useState} from "react";
import {Link, NavLink, useNavigate, useSearchParams} from "react-router-dom";
import {getCounselorChanges, getCounselorDashboard} from "../api";
import {DateRangePicker, rangePreset} from "./CompanyDashboardPage.jsx";
import "./company-dashboard.css";
import "./counselor-dashboard.css";

const number = value => Number(value || 0).toLocaleString();
const initialRange = () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem("counselor_dashboard_range") || "null");
    if (saved?.startDate && saved?.endDate && saved.startDate <= saved.endDate) return saved;
    if (saved?.startDate === "" && saved?.endDate === "") return saved;
  } catch {}
  return rangePreset(7);
};
const prettyDate = value => value ? new Date(value).toLocaleString("en-IN", {dateStyle:"medium", timeStyle:"short"}) : "";
const title = type => ({STATUS_CHANGE:"Status change", NOTE:"Note added", CONTACT:"Contact recorded", CONTACT_EDIT:"Contact edited"})[type] || type?.replaceAll("_"," ") || "Update";

function Metric({label,value,detail,tone}) {
  return <article className={`co-metric co-${tone}`}><span>{label}</span><strong>{number(value)}</strong><small>{detail}</small></article>;
}

function CounselorChart({rows=[],onSelect}) {
  const [mode,setMode]=useState("overview"),[countMode,setCountMode]=useState("all");
  const main=row=>countMode==="unique"?row.unique_main_people:row.main_updates;
  const upsell=row=>countMode==="unique"?row.unique_upsell_people:row.upsell_updates;
  const total=row=>countMode==="unique"?row.unique_people:row.total_updates;
  const max=Math.max(1,...rows.map(row=>mode==="leads"?row.leads_given:mode==="main"?main(row):mode==="upsell"?upsell(row):Math.max(row.leads_given,total(row))));
  const height=value=>`${Math.max(value?7:0,Number(value||0)/max*226)}px`;
  return <section className="co-panel"><div className="co-section-head"><div><span>TEAM ACTIVITY</span><h2>Work by counselor</h2><p>Each update is credited to the person who made it. Leads use their assignment date.</p></div><div className="co-chart-controls"><div className="co-chart-toggle" role="group" aria-label="Update counting">{[["all","Every update"],["unique","Unique people"]].map(([key,label])=><button type="button" key={key} className={countMode===key?"active":""} aria-pressed={countMode===key} onClick={()=>setCountMode(key)}>{label}</button>)}</div><div className="co-chart-toggle" role="group" aria-label="Chart breakdown">{[["overview","Overview"],["leads","Leads given"],["main","Main CRM"],["upsell","Upsell"]].map(([key,label])=><button type="button" key={key} className={mode===key?"active":""} aria-pressed={mode===key} onClick={()=>setMode(key)}>{label}</button>)}</div></div></div>
    {!rows.length?<div className="co-empty">No counselors are available.</div>:<><div className="co-chart-scroll"><div className="co-chart" style={{minWidth:`${Math.max(720,rows.length*112)}px`}}><div className="co-grid"><span>{number(max)}</span><span>{number(Math.round(max/2))}</span><span>0</span></div><div className="co-chart-groups">{rows.map(row=><button className="co-chart-group" type="button" key={row.id} onClick={()=>onSelect(row.id)} aria-label={`${row.name}: ${row.leads_given} leads given, ${total(row)} ${countMode==="unique"?"unique people":"updates"}, ${main(row)} Main CRM, ${upsell(row)} Upsell. View changes.`}><div className="co-bars">{(mode==="overview"||mode==="leads")&&<div className="co-bar co-leads" style={{height:height(row.leads_given)}} title={`${row.leads_given} leads given`}/ >}{mode==="overview"&&(countMode==="unique"?<div className="co-bar co-unique" style={{height:height(total(row))}} title={`${total(row)} unique people across both CRMs`}/>:<div className="co-bar-stack" style={{height:height(total(row))}} title={`${total(row)} updates`}><i className="co-main" style={{height:total(row)?`${main(row)/total(row)*100}%`:"0%"}}/><i className="co-upsell" style={{height:total(row)?`${upsell(row)/total(row)*100}%`:"0%"}}/></div>)}{mode==="main"&&<div className="co-bar co-main" style={{height:height(main(row))}} title={`${main(row)} Main CRM ${countMode==="unique"?"unique people":"updates"}`}/ >}{mode==="upsell"&&<div className="co-bar co-upsell" style={{height:height(upsell(row))}} title={`${upsell(row)} Upsell ${countMode==="unique"?"unique people":"updates"}`}/ >}</div><strong>{row.name}</strong><span>{mode==="overview"?`${number(total(row))} ${countMode==="unique"?(total(row)===1?"person":"people"):"updates"}`:number(mode==="leads"?row.leads_given:mode==="main"?main(row):upsell(row))}</span></button>)}</div></div></div><div className="co-legend"><span><i className="co-leads"/>Leads given</span>{countMode==="unique"&&<span><i className="co-unique"/>Unique people across both CRMs</span>}<span><i className="co-main"/>Main CRM {countMode==="unique"?"people":"updates"}</span><span><i className="co-upsell"/>Upsell {countMode==="unique"?"people":"updates"}</span></div></>}
  </section>;
}

function ChangeCard({item,onViewPerson}) {
  const href=item.workspace==="main"?`/crm/leads/${item.lead_id}`:`/upsell/leads/${item.lead_id}`;
  const note=item.after_note?.trim() || "";
  return <article className="co-change-card"><div className="co-change-top"><div><span className={`co-workspace co-workspace-${item.workspace}`}>{item.workspace==="main"?"MAIN CRM":"UPSELL CRM"}</span><span className="co-action-type">{title(item.action_type)}</span>{note.length>0&&note.length<=3&&<span className="co-short-note">Very short note</span>}</div><time dateTime={item.created_at}>{prettyDate(item.created_at)}</time></div><div className="co-change-name"><div><strong>{item.lead_name}</strong><span>{item.course||"Course not specified"}</span></div><Link to={href}>Open lead →</Link></div>
    {(item.before_status||item.after_status)&&<div className="co-status-change"><span>Status</span><strong>{item.before_status||"—"}</strong><b>→</b><strong>{item.after_status||"—"}</strong></div>}
    {(item.before_note!==null||item.after_note!==null)&&<div className="co-note-compare"><div><span>Previous note</span><p>{item.before_note || "No previous note"}</p></div><div><span>New or changed note</span><p>{item.after_note || "No note supplied"}</p></div></div>}
    <div className="co-change-foot">Updated by <strong>{item.actor_name}</strong>{item.assigned_counselor_name&&<> · Assigned to {item.assigned_counselor_name}</>}{item.channel&&<> · {item.channel.replaceAll("_"," ")}</>}</div>{onViewPerson&&item.person_updates>1&&<button className="co-view-person" type="button" onClick={()=>onViewPerson(item.person_key)}>View all {item.person_updates} updates for this person →</button>}</article>;
}

export default function CounselorDashboardPage({section="overview"}) {
  const [range,setRange]=useState(initialRange),[summary,setSummary]=useState(null),[error,setError]=useState("");
  const [changes,setChanges]=useState(null),[page,setPage]=useState(1),[changesError,setChangesError]=useState("");
  const [logMode,setLogMode]=useState("all"),[person,setPerson]=useState("");
  const [searchParams,setSearchParams]=useSearchParams(),navigate=useNavigate();
  const counselorId=Number(searchParams.get("counselor")||0);
  function changeRange(next){try{sessionStorage.setItem("counselor_dashboard_range",JSON.stringify(next));}catch{}setRange(next);setPage(1);setPerson("");}
  function chooseCounselor(id){setSearchParams(id?{counselor:String(id)}:{});setPage(1);setPerson("");}
  function chooseLogMode(next){setLogMode(next);setPerson("");setPage(1);}
  function viewPerson(key){setPerson(key);setLogMode("all");setPage(1);}
  useEffect(()=>{let live=true;setSummary(null);setError("");getCounselorDashboard(range).then(data=>{if(live)setSummary(data);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[range.startDate,range.endDate]);
  useEffect(()=>{if(section!=="changes"||!counselorId){setChanges(null);return;}let live=true;setChanges(null);setChangesError("");getCounselorChanges(counselorId,range,page,logMode,person).then(data=>{if(live)setChanges(data);}).catch(e=>{if(live)setChangesError(e.message);});return()=>{live=false;};},[section,counselorId,page,logMode,person,range.startDate,range.endDate]);
  const cards=summary?.cards||{};
  return <div className="page cd-page co-page"><header className="cd-hero co-hero"><div className="cd-hero-glow"/><div className="cd-hero-content"><div className="cd-eyebrow"><span/> GWG INTELLIGENCE / COUNSELORS</div><h1>{section==="changes"?"Counselor change log":"Counselor activity"}</h1><p>{section==="changes"?"Review each recorded update, note and status change.":"See the work given to each counselor and the activity they recorded."}</p></div><div className="co-hero-badge">TEAM<br/><strong>INSIGHT</strong></div></header>
    <div className="cd-toolbar"><nav className="cd-tabs" aria-label="Counselor dashboard pages"><NavLink to="/dashboard/counselors" end>Overview</NavLink><NavLink to="/dashboard/counselors/changes">Change log</NavLink></nav><DateRangePicker value={range} onChange={changeRange}/></div>
    {error&&<div className="cd-alert">Could not load counselor data: {error}</div>}
    {!summary&&!error&&<div className="cd-loading"><span/>Loading counselor data…</div>}
    {summary&&section==="overview"&&<><div className="co-metrics"><Metric label="MAIN CRM LEADS GIVEN" value={cards.leads_given} detail="Currently assigned in selected dates" tone="violet"/><Metric label="TOTAL UPDATES" value={cards.total_updates} detail={`Unique people updated: ${number(cards.unique_people)}`} tone="dark"/><Metric label="MAIN CRM UPDATES" value={cards.main_updates} detail={`Unique people updated: ${number(cards.unique_main_people)}`} tone="mint"/><Metric label="UPSELL UPDATES" value={cards.upsell_updates} detail={`Unique people updated: ${number(cards.unique_upsell_people)}`} tone="sky"/></div><CounselorChart rows={summary.counselors} onSelect={id=>navigate(`/dashboard/counselors/changes?counselor=${id}`)}/><p className="co-method">Leads given counts Main CRM leads currently assigned to each counselor, using the date of their latest assignment. Updates count actions by the counselor who actually saved them; administrator edits are excluded. Unique people are counted once per counselor in the chart and once across the team in the cards, using linked contacts across both CRMs. Main and Upsell unique counts can overlap. Historical assignment dates before this release use the lead creation date when no assignment timestamp was stored.</p></>}
    {summary&&section==="changes"&&<><div className="co-log-toolbar"><div><span>TRANSPARENT RECORD</span><h2>Every counselor update</h2><p>Choose a counselor to inspect their actions in this date range. Unique people shows the latest action for each linked person.</p></div><div className="co-log-filters"><div className="co-log-mode" role="group" aria-label="Change log filter"><button type="button" className={logMode==="all"?"active":""} aria-pressed={logMode==="all"} onClick={()=>chooseLogMode("all")}>All updates</button><button type="button" className={logMode==="unique"?"active":""} aria-pressed={logMode==="unique"} onClick={()=>chooseLogMode("unique")}>Unique people</button></div><label>Counselor<select aria-label="Choose counselor" value={counselorId||""} onChange={e=>chooseCounselor(e.target.value)}><option value="">Select a counselor</option>{summary.counselors.map(person=><option value={person.id} key={person.id}>{person.name}</option>)}</select></label></div></div>{!counselorId&&<div className="co-empty">Select a counselor to see their changes.</div>}{changesError&&<div className="cd-alert">Could not load changes: {changesError}</div>}{counselorId&&!changes&&!changesError&&<div className="cd-loading"><span/>Loading changes…</div>}{changes&&<><div className="co-log-count"><span><strong>{number(changes.total)}</strong> {logMode==="unique"?"unique people updated":"updates"} by {changes.counselor.name}{person&&" ? One person"}</span>{person&&<button type="button" onClick={()=>{setPerson("");setLogMode("unique");setPage(1);}}>Back to unique people</button>}</div><div className="co-change-list">{changes.items.map(item=><ChangeCard key={item.id} item={item} onViewPerson={logMode==="unique"?viewPerson:null}/>)}</div>{!changes.items.length&&<div className="co-empty">No recorded {logMode==="unique"?"people":"updates"} for this counselor in the selected dates.</div>}{changes.pages>1&&<div className="co-pagination"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>← Previous</button><span>Page {page} of {changes.pages}</span><button disabled={page>=changes.pages} onClick={()=>setPage(p=>p+1)}>Next →</button></div>}</>}</>}
  </div>;
}
