import {useState} from "react";
import {getLeadReminder,saveLeadReminder,completeLeadReminder} from "../api";
import "./reminders.css";

export const reminderLabel = r => r.completed_at ? "Done" : r.overdue_days > 0 ? `Contact now · ${r.overdue_days} day${r.overdue_days===1?"":"s"} overdue` : r.remaining_days === 0 ? "Contact today" : `${r.remaining_days} day${r.remaining_days===1?"":"s"} remaining`;

export default function ReminderControl({workspace,leadId,compact=false,initial=null,onChange}) {
  const [open,setOpen]=useState(false),[reminder,setReminder]=useState(initial),[days,setDays]=useState("3"),[notes,setNotes]=useState("");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  async function show(){setOpen(true);setBusy(true);setError("");setMessage("");try{const {reminder:r}=await getLeadReminder(workspace,leadId);setReminder(r);setNotes(r?.notes||"");setDays(String(r&&!r.completed_at?r.remaining_days:3));}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function save(event){event.preventDefault();if(days==="")return;setBusy(true);setError("");try{const r=await saveLeadReminder(workspace,leadId,Number(days),notes);setReminder(r);setOpen(false);setMessage("Reminder saved");onChange?.(r);}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function done(){setBusy(true);setError("");try{const r=await completeLeadReminder(workspace,leadId);setReminder(r);setOpen(false);setMessage("Reminder marked done");onChange?.(r);}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className={`reminder-control ${compact?"compact":""}`}>
    <button type="button" className="secondary-button reminder-open" onClick={show}>◷ {reminder&&!reminder.completed_at?reminderLabel(reminder):"Set reminder"}</button>
    {!open&&message&&<span className="small-muted" role="status">{message}</span>}
    {open&&<div className="reminder-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setOpen(false);}}><form className="reminder-dialog" role="dialog" aria-modal="true" aria-label="Lead contact reminder" onSubmit={save}>
      <div className="section-heading"><div><div className="eyebrow">FOLLOW-UP PLANNER</div><h2>When should you contact this lead?</h2></div><button type="button" className="secondary-button" disabled={busy} aria-label="Close reminder" onClick={()=>setOpen(false)}>×</button></div>
      <p className="small-muted">The reminder appears on the assigned counselor’s Reminders page. Dates use India time.</p>
      {reminder&&<div className={`reminder-status ${reminder.due_now?"due":""}`}>{reminderLabel(reminder)} · Due {reminder.due_date}</div>}
      <div className="reminder-presets">{[0,1,3,7,14].map(n=><button key={n} type="button" disabled={busy} className={Number(days)===n?"selected":""} onClick={()=>setDays(String(n))}>{n===0?"Today":`${n} day${n===1?"":"s"}`}</button>)}</div>
      <label>Remind in N days<input aria-label="Reminder days" type="number" min="0" max="3650" step="1" required value={days} disabled={busy} onChange={e=>setDays(e.target.value)}/></label>
      <label>Contact note (optional)<textarea aria-label="Reminder note" maxLength="2000" rows="3" value={notes} disabled={busy} onChange={e=>setNotes(e.target.value)} placeholder="What do you need to discuss?"/></label>
      {error&&<div className="form-error" role="alert">{error}</div>}
      <div className="reminder-dialog-actions">{reminder&&!reminder.completed_at&&<button type="button" className="secondary-button" disabled={busy} onClick={done}>Mark done</button>}<button type="submit" className="primary-button" disabled={busy||days===""}>{busy?"Saving...":"Save reminder"}</button></div>
    </form></div>}
  </div>;
}
