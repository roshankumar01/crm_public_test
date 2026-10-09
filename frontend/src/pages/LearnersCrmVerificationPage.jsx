import { useEffect, useState } from "react";
import { getCounselors, getLearnerVerification, verifyDailyLearner } from "../api";

const TABS = [
  ["daily", "Daily pending"],
  ["daily_verified", "Daily verified"],
  ["migrated", "Migrated unmatched"],
  ["migrated_matched", "Migrated matched"],
];

function VerificationRow({ item, counselors, onVerified }) {
  const [email, setEmail] = useState(item.email || "");
  const [phone, setPhone] = useState(item.phone || "");
  const [counselorId, setCounselorId] = useState(item.counselor_user_id || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const pending = item.status === "PENDING";
  async function verify() {
    try {
      setSaving(true); setError("");
      await verifyDailyLearner(item.id, { email, phone, counselor_user_id: Number(counselorId) || null });
      onVerified();
    } catch (issue) { setError(issue.message); }
    finally { setSaving(false); }
  }
  return <tr>
    <td><strong>{item.learner_name}</strong><small className="small-muted" style={{ display: "block" }}>{item.enrolment_id}</small></td>
    <td>{item.course_name}</td>
    <td>{pending ? <input aria-label={`Email for ${item.learner_name}`} value={email} onChange={event => setEmail(event.target.value)} /> : item.email || "—"}</td>
    <td>{pending ? <input aria-label={`Phone for ${item.learner_name}`} value={phone} onChange={event => setPhone(event.target.value)} /> : item.phone || "—"}</td>
    <td>{pending ? <select aria-label={`Counselor for ${item.learner_name}`} value={counselorId} onChange={event => setCounselorId(event.target.value)}><option value="">Select counselor</option>{counselors.map(user => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select> : item.counselor_name || "—"}</td>
    <td><span className={`learner-verification-tick ${item.status === "VERIFIED" ? "verified" : item.status === "UNMATCHED" ? "unmatched" : "pending"}`} title={item.status === "UNMATCHED" ? "No Main CRM match; eligible for Upsell" : item.status === "PENDING" ? "Waiting for admin verification" : "Verified"}>✓</span>{pending && <small className="small-muted" style={{ display: "block" }}>{item.matched_main ? "Main CRM match found" : "No Main CRM match"}</small>}</td>
    <td>{pending && <button className="primary-button" disabled={saving || !counselorId || (!email && !phone)} onClick={verify}>{saving ? "Verifying..." : "Verify"}</button>}{error && <small className="page-message" style={{ display: "block" }}>{error}</small>}</td>
  </tr>;
}

export default function LearnersCrmVerificationPage() {
  const [kind, setKind] = useState("daily");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [counselors, setCounselors] = useState([]);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { getCounselors().then(setCounselors).catch(issue => setError(issue.message)); }, []);
  useEffect(() => {
    let cancelled = false;
    setResult(null); setError("");
    getLearnerVerification(kind, page).then(data => { if (!cancelled) setResult(data); })
      .catch(issue => { if (!cancelled) setError(issue.message); });
    return () => { cancelled = true; };
  }, [kind, page, refresh]);
  return <div className="page learner-verification-page">
    <div className="page-header simple-header"><div><div className="eyebrow">LEARNERS CRM</div><h1>Learner verification</h1><p className="page-description">Review daily learners before they enter Upsell. Migrated learners remain eligible; the red tick shows that no Main CRM contact matches them.</p></div></div>
    <div className="segmented-control" role="tablist" aria-label="Verification status">{TABS.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={kind === value} className={kind === value ? "segment active" : "segment"} onClick={() => { setKind(value); setPage(1); }}>{label}</button>)}</div>
    {error && <div className="page-message">{error}</div>}
    {!result && !error && <div className="loading-state"><span />Loading learners...</div>}
    {result && <><p className="small-muted">{result.total} records · Page {page}</p><div className="table-card"><table><thead><tr><th>Learner / enrolment</th><th>Course</th><th>Email</th><th>Phone</th><th>Counselor</th><th>Match</th><th>Action</th></tr></thead><tbody>{result.items.map(item => <VerificationRow key={item.id} item={item} counselors={counselors} onVerified={() => setRefresh(value => value + 1)} />)}</tbody></table>{!result.items.length && <div className="table-message">No records in this view.</div>}</div><div className="toolbar toolbar-space"><button className="secondary-button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><button className="secondary-button" disabled={page * 25 >= result.total} onClick={() => setPage(page + 1)}>Next</button></div></>}
  </div>;
}
