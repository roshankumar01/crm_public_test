import {useEffect,useState} from "react";
import {Link} from "react-router-dom";
import {useAuth} from "../context/AuthContext.jsx";
import {getMainCrmMismatch,getUpsellMismatch,downloadMainCrmMismatch,downloadUpsellMismatch,verifyMainCrmMismatch,verifyUpsellMismatch} from "../api";
import VerificationTick from "./VerificationTick";

export default function ConversionMismatch({upsell=false}) {
  const {user}=useAuth();
  const [period,setPeriod]=useState("all"),[state,setState]=useState("pending"),[page,setPage]=useState(1);
  const [data,setData]=useState(null),[error,setError]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(null),[downloading,setDownloading]=useState(false);
  useEffect(()=>{let cancelled=false;setData(null);setError("");setNotice("");
    (upsell?getUpsellMismatch:getMainCrmMismatch)(period,page,state).then(d=>{if(!cancelled)setData(d);}).catch(e=>{if(!cancelled)setError(e.message);});
    return()=>{cancelled=true;};},[upsell,period,page,state]);
  async function verify(item){setBusy(item.id);setError("");try{
    const result=await (upsell?verifyUpsellMismatch:verifyMainCrmMismatch)(item.id);
    setData(d=>state==="pending"?{...d,total:Math.max(0,d.total-1),items:d.items.filter(row=>row.id!==item.id)}:{...d,items:d.items.map(row=>row.id===item.id?{...row,...result}:row)});
    setNotice("Verified as enrolled. Uploaded results are still required for a pass or completion.");
  }catch(e){setError(e.message);}finally{setBusy(null);}}
  async function download(){setDownloading(true);try{await (upsell?downloadUpsellMismatch:downloadMainCrmMismatch)(period,state);}catch(e){setError(e.message);}finally{setDownloading(false);}}
  return <div className="page verification-report">
    <div className="page-header simple-header"><div><div className="eyebrow">{upsell?"UPSELL CRM":"MAIN CRM"}</div><h1>Conversion / registration mismatch</h1><p className="page-description">{upsell?"Registration matches the same person and course subcategory.":"Registration matches the same person in Learners CRM or uploaded result data."} Admin verification confirms enrolment.</p></div><button className="primary-button" disabled={!data?.total||downloading||busy!==null} onClick={download}>{downloading?"Preparing report...":"Download report ↓"}</button></div>
    <div className="verification-filters"><label>Date range<select className="search-input" disabled={busy!==null} value={period} onChange={e=>{setPeriod(e.target.value);setPage(1);}}><option value="all">All time</option><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_month">Last 1 month</option></select></label><label>Verification<select className="search-input" aria-label="Verification filter" disabled={busy!==null} value={state} onChange={e=>{setState(e.target.value);setPage(1);}}><option value="pending">Pending verification</option><option value="verified">Verified conversions</option><option value="all">All converted records</option></select></label></div>
    {error&&<div className="form-error">{error}</div>}{notice&&<div className="verification-notice" role="status">{notice} {state!=="verified"&&<button className="text-link" onClick={()=>{setState("verified");setPage(1);}}>Show verified records</button>}</div>}
    <div className="simple-stats"><div className="simple-stat main"><span>{state==="pending"?"Pending verifications":state==="verified"?"Verified conversions":"Converted records"}</span><strong>{data?.total??"—"}</strong><small>Green tick: registered or admin verified · Gray tick: unverified</small></div></div>
    <div className="table-card"><table><thead><tr><th>Person</th><th>Contact</th>{upsell&&<><th>Main category</th><th>Subcategory</th></>}<th>Course</th>{!upsell&&<th>Source</th>}<th>Counselor</th><th>{upsell?"Converted":"Updated"}</th><th>Verification</th><th></th></tr></thead><tbody>{(data?.items||[]).map(item=><tr key={item.id}><td><strong>{upsell?item.name:item.full_name}</strong></td><td>{item.email||"—"}<div className="small-muted">{(upsell?item.phone:item.phone_number)||"—"}</div></td>{upsell&&<><td>{item.main_category}</td><td>{item.sub_category}</td></>}<td>{(upsell?item.course_name:item.course)||"Not provided"}</td>{!upsell&&<td>{item.source||"—"}</td>}<td>{item.counselor||"Unassigned"}</td><td>{(upsell?item.converted_at:item.updated_at)?new Date(upsell?item.converted_at:item.updated_at).toLocaleString():"—"}</td><td className="verification-cell"><VerificationTick record={item} label/>{item.verified_by&&<div className="small-muted">Verified by {item.verified_by}</div>}{!item.verified&&user?.role==="ADMIN"&&<button className="primary-button" disabled={busy!==null} onClick={()=>verify(item)}>{busy===item.id?"Verifying...":"Verify enrolment"}</button>}</td><td><Link className="text-link" to={upsell?`/upsell/leads/${item.lead_id}`:`/crm/leads/${item.id}`}>{upsell?"Manage":"Full profile"} →</Link></td></tr>)}</tbody></table>{!data&&!error&&<div className="table-message">Checking registrations...</div>}{data&&!data.total&&<div className="table-message">No conversions in this filter.</div>}</div>
    {data&&<div className="toolbar toolbar-space"><button className="secondary-button" disabled={page<=1||busy!==null} onClick={()=>setPage(p=>p-1)}>Previous</button><span className="small-muted">Page {page} of {data.pages||1} · {data.total} records</span><button className="secondary-button" disabled={page>=(data.pages||1)||busy!==null} onClick={()=>setPage(p=>p+1)}>Next</button></div>}
  </div>;
}
