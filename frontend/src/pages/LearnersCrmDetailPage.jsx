import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { getLearnersCrmProfile } from "../api";
import CustomerLifecycle from "../components/CustomerLifecycle.jsx";

function Field({ label, value }) {
  return <div className="profile-field"><span>{label}</span><strong>{value || "Not provided"}</strong></div>;
}

export default function LearnersCrmDetailPage() {
  const { learnerId } = useParams();
  const location = useLocation();
  const [learner, setLearner] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getLearnersCrmProfile(learnerId).then(setLearner).catch(requestError => setError(requestError.message)); }, [learnerId]);
  const back = `/learners-crm/learners${location.state?.search ? `?search=${encodeURIComponent(location.state.search)}` : ""}`;
  const counts = useMemo(() => ({
    completed: learner?.enrolments.filter(item => item.completion_status?.trim().toLowerCase() === "completed").length || 0,
    active: learner?.enrolments.filter(item => item.completion_status?.trim().toLowerCase() === "not completed").length || 0,
  }), [learner]);
  if (error) return <div className="page"><Link className="back-link" to={back}>← Back to Find learners</Link><div className="empty-card">{error}</div></div>;
  if (!learner) return <div className="page"><div className="loading-state"><span />Loading learner...</div></div>;
  return <div className="page profile-detail-page">
    <Link className="back-link" to={back}>← Back to Find learners</Link>
    <div className="profile-hero premium-profile"><div className="profile-avatar">{learner.learner_name?.[0]?.toUpperCase()}</div><div className="profile-main"><div className="eyebrow">LEARNER PROFILE</div><h1>{learner.learner_name}</h1><div className="profile-number">{learner.enrolments.length} course enrolment{learner.enrolments.length === 1 ? "" : "s"}</div></div><div className="profile-contact"><div><span>Email</span><strong>{learner.email_id}</strong></div><div><span>Phone</span><strong>{learner.phone_number || "Not provided"}</strong></div></div></div>
    <div className="profile-summary-grid"><div className="profile-summary-card"><span>Total enrolments</span><strong>{learner.enrolments.length}</strong></div><div className="profile-summary-card"><span>Active enrolments</span><strong>{counts.active}</strong></div><div className="profile-summary-card"><span>Completed enrolments</span><strong>{counts.completed}</strong></div></div>
    <CustomerLifecycle lifecycle={learner.lifecycle} />
    <section className="profile-section"><div className="section-heading"><div><div className="eyebrow">CONTACT</div><h2>Learner details</h2></div></div><div className="profile-fields"><Field label="Full name" value={learner.learner_name} /><Field label="Email" value={learner.email_id} /><Field label="Phone number" value={learner.phone_number} /><Field label="Counselor" value={learner.assigned_to_name || "Unassigned"} /><Field label="Counselor email" value={learner.assigned_to_email} /><Field label="Profile created" value={learner.created_at && new Date(learner.created_at).toLocaleString()} /><Field label="Last updated" value={learner.updated_at && new Date(learner.updated_at).toLocaleString()} /></div></section>
    <section className="profile-section"><div className="section-heading"><div><div className="eyebrow">COURSE HISTORY</div><h2>Enrolments</h2></div></div><div className="profile-record-list">{learner.enrolments.map(item => <article className="profile-record-card" key={item.enrolment_id}><div className="profile-record-heading"><div><div className="eyebrow">ENROLMENT {item.enrolment_id}</div><h3>{item.course_name} <span className={`learner-verification-tick ${item.verification_status === "UNMATCHED" ? "unmatched" : "verified"}`} title={item.verification_status === "UNMATCHED" ? "Migrated learner without Main CRM match; eligible for Upsell" : "Verified learner"}>✓</span></h3><p className="small-muted">{[item.course_category, item.course_sub_category].filter(Boolean).join(" / ") || "Unmapped category"}</p></div><span className={item.completion_status?.trim().toLowerCase() === "completed" ? "status-pill pass" : "status-pill"}>{item.completion_status || "No status"}</span></div><div className="profile-fields"><Field label="Enrolment ID" value={item.enrolment_id} /><Field label="Enrolment date" value={item.enrolment_date} /><Field label="Start date" value={item.start_date} /><Field label="Completion date" value={item.completion_date} /><Field label="Record created" value={item.created_at && new Date(item.created_at).toLocaleString()} /><Field label="Record updated" value={item.updated_at && new Date(item.updated_at).toLocaleString()} /></div></article>)}{!learner.enrolments.length && <div className="empty-card">No enrolments found for this learner.</div>}</div></section>
  </div>;
}
