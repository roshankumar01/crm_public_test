import {useState} from "react";
import "./status-update.css";

export default function StatusUpdateControl({value,options,onSave,disabled=false,label="Lead status"}) {
  const [target,setTarget]=useState(null),[note,setNote]=useState(""),[saving,setSaving]=useState(false),[error,setError]=useState("");
  const title=options.find(([code])=>code===target)?.[1]||target;
  async function save(event){event.preventDefault();if(!note.trim()||!target)return;
    setSaving(true);setError("");try{await onSave(target,note.trim());setTarget(null);setNote("");}
    catch(e){setError(e.message);}finally{setSaving(false);}}
  return <span className="status-update-control"><select aria-label={label} className="compact-select" value={value} disabled={disabled||saving} onChange={event=>{if(event.target.value!==value){setTarget(event.target.value);setNote("");setError("");}}}>{options.map(([code,text,optionDisabled])=><option key={code} value={code} disabled={optionDisabled}>{text}</option>)}</select>
    {target&&<div className="status-update-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!saving)setTarget(null);}}><form className="status-update-dialog" role="dialog" aria-modal="true" aria-label="Explain status change" onSubmit={save}>
      <div className="eyebrow">CONTACT NOTE REQUIRED</div><h2>Update status to {title}</h2><p>Describe what you spoke about or what happened. This note and status change will be saved together under your name.</p>
      <label>New contact note<textarea autoFocus rows="4" maxLength="2000" required value={note} onChange={e=>setNote(e.target.value)} placeholder="What happened in this conversation?"/></label>
      {error&&<div className="form-error" role="alert">{error}</div>}
      <div className="status-update-actions"><button className="secondary-button" type="button" disabled={saving} onClick={()=>setTarget(null)}>Cancel</button><button className="primary-button" type="submit" disabled={saving||!note.trim()}>{saving?"Saving...":"Save status and note"}</button></div>
    </form></div>}
  </span>;
}
