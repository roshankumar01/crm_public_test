import {useCallback,useEffect,useState} from "react";
import {Link} from "react-router-dom";
import {getCounselors,getReminders,completeLeadReminder} from "../api";
import {useAuth} from "../context/AuthContext.jsx";
import ReminderControl,{reminderLabel} from "../components/ReminderControl";

const companyDay=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());

export default function RemindersPage({workspace}) {
  const {user}=useAuth(); const admin=user?.role==="ADMIN";
  const [view,setView]=useState("pending"),[page,setPage]=useState(1),[owner,setOwner]=useState("");
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(null),[owners,setOwners]=useState([]),[revision,setRevision]=useState(0);
  const refresh=useCallback(()=>setRevision(r=>r+1),[]);
  useEffect(()=>{let cancelled=false;setData(null);setError("");getReminders(workspace,view,page,owner).then(d=>{if(!cancelled)setData(d);}).catch(e=>{if(!cancelled)setError(e.message);});return()=>{cancelled=true;};},[workspace,view,page,owner,revision]);
  useEffect(()=>{let day=companyDay();const check=()=>{const next=companyDay();if(next!==day){day=next;refresh();}};const timer=setInterval(check,60000);window.addEventListener("focus",check);return()=>{clearInterval(timer);window.removeEventListener("focus",check);};},[refresh]);
  useEffect(()=>{if(admin)getCounselors().then(setOwners).catch(e=>setError(e.message));},[admin]);
  useEffect(()=>{setPage(1);setView("pending");setOwner("");},[workspace]);
  async function done(row){setBusy(row.id);setError("");try{await completeLeadReminder(workspace,row.lead_id);refresh();}catch(e){setError(e.message);}finally{setBusy(null);}}
  const base=workspace==="main"?"/crm":"/upsell";
  return <div className="page reminders-page"><div className="page-header simple-header"><div><div className="eyebrow">{workspace==="main"?"MAIN CRM":"UPSELL CRM"} · FOLLOW-UP PLANNER</div><h1>{admin?"Counselor reminders":"My reminders"}</h1><p className="page-description">Keep every follow-up on track. Due leads stay here until you contact them or reschedule.</p></div><button className="secondary-button" onClick={refresh}>Refresh reminders</button></div>
    <div className="simple-stats"><div className="simple-stat main"><span>Contact now</span><strong>{data?.counts?.due??"—"}</strong><small>Due today and overdue</small></div><div className="simple-stat"><span>Coming up</span><strong>{data?.counts?.upcoming??"—"}</strong><small>Scheduled for later</small></div><div className="simple-stat"><span>Done</span><strong>{data?.counts?.completed??"—"}</strong><small>Follow-ups marked done</small></div></div>
    {data?.counts?.due>0&&<div className="reminder-urgent" role="status"><strong>{data.counts.due} lead{data.counts.due===1?"":"s"} to contact now.</strong> Check the highlighted reminders below.</div>}
    <div className="reminder-toolbar"><select className="search-input" aria-label="Reminder view" value={view} onChange={e=>{setView(e.target.value);setPage(1);}}><option value="pending">All pending reminders</option><option value="due">Contact now</option><option value="upcoming">Upcoming</option><option value="completed">Done</option></select>{admin&&<select className="search-input" aria-label="Reminder counselor" value={owner} onChange={e=>{setOwner(e.target.value);setPage(1);}}><option value="">All counselors</option><option value={user.id}>My reminders</option>{owners.map(o=><option value={o.id} key={o.id}>{o.display_name}</option>)}</select>}<span className="small-muted">Company date: {data?.today||"…"} · India time</span></div>
    {error&&<div className="form-error" role="alert">{error}</div>}
    <div className="table-card"><table><thead><tr><th>Lead</th><th>Course</th><th>Counselor</th><th>Contact date</th><th>Countdown</th><th>Note</th><th>Actions</th></tr></thead><tbody>{(data?.items||[]).map(row=><tr key={row.id} className={row.due_now?"reminder-due-row":""}><td><strong>{row.name||"Unknown"}</strong><div className="small-muted">{row.email||"—"}</div><div className="small-muted">{row.phone||"—"}</div></td><td>{row.course||"Not provided"}</td><td>{row.counselor||"Unassigned"}</td><td>{row.due_date}</td><td><span className={`reminder-status ${row.due_now?"due":row.completed_at?"done":""}`}>{reminderLabel(row)}</span></td><td className="reminder-note">{row.notes||"—"}</td><td><div className="reminder-action-group"><Link className="text-link" to={`${base}/leads/${row.lead_id}`}>Open lead →</Link>{!row.completed_at&&<button className="secondary-button" disabled={busy!==null} onClick={()=>done(row)}>{busy===row.id?"Saving...":"Mark done"}</button>}</div><ReminderControl workspace={workspace} leadId={row.lead_id} initial={row} compact onChange={refresh}/></td></tr>)}</tbody></table>{!data&&!error&&<div className="table-message">Loading reminders...</div>}{data&&!data.items.length&&<div className="table-message">No reminders in this view. Set one from a lead’s profile or pipeline.</div>}</div>
    {data&&<div className="toolbar toolbar-space"><button className="secondary-button" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Previous</button><span className="small-muted">Page {page} of {data.pages} · {data.total} reminders</span><button className="secondary-button" disabled={page>=data.pages} onClick={()=>setPage(p=>p+1)}>Next</button></div>}
  </div>;
}
