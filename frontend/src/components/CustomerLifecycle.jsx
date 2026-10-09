import VerificationTick from "./VerificationTick";
import { useState } from "react";
import { Link } from "react-router-dom";

const LABELS = {
  ENQUIRY: "Main CRM", ENROLMENT: "Learners CRM", COMPLETION: "Learners CRM",
  RESULT: "Result data", MARKETING: "Marketing", UPSELL: "Upsell CRM",
};

const labelFor = value => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const displayValue = value => value !== null && typeof value === "object" ? JSON.stringify(value) : value;

export default function CustomerLifecycle({ lifecycle }) {
  const [showAll, setShowAll] = useState(false);
  const events = lifecycle?.events || [];
  const visible = showAll ? events : events.slice(0, 20);

  return <section className="profile-section customer-lifecycle">
    <div className="section-heading"><div><div className="eyebrow">LIFECYCLE STORY</div><h2>Learning journey</h2></div></div>
    {events.length ? <div className="journey">{visible.map((event, index) => {
      const fields = Object.entries(event.fields || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
      const original = Object.entries(event.raw_data || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
      const status = event.status?.replaceAll("_", " ");
      const statusClass = event.status === "PASS" || event.status === "Completed" ? "status-pill pass" : event.status === "FAIL" ? "status-pill fail" : "status-pill";
      return <div className="journey-item" key={event.key}>
        <div className="journey-rail"><div className={event.status === "PASS" || event.kind === "COMPLETION" ? "journey-dot pass" : "journey-dot"}>{event.status === "PASS" || event.kind === "COMPLETION" ? "✓" : ""}</div>{index < visible.length - 1 && <div className="journey-line" />}</div>
        <article className="journey-card lifecycle-journey-card">
          <div className="journey-card-header"><div><div className="journey-date">{event.date?.slice(0, 10) || "Date unavailable"}</div><span className="lifecycle-source">{event.source_label || LABELS[event.kind] || event.kind}</span><h3>{event.href ? <Link to={event.href}>{event.title}</Link> : event.title}{event.kind === "RESULT" && status ? ` - ${status.toUpperCase()}` : ""}</h3></div>{status && <span className={statusClass}>{status}{event.verified&&<VerificationTick record={{verified:true,verification_source:event.source_label}}/>}</span>}</div>
          {event.detail && <p className="lifecycle-event-detail">{event.detail}</p>}
          {fields.length > 0 && <div className="detail-grid">{fields.map(([key, value]) => <div key={key}><span>{labelFor(key)}</span><strong>{displayValue(value)}</strong></div>)}</div>}
          {original.length > 0 && <details className="profile-original-data"><summary>View original uploaded row</summary><div className="detail-grid">{original.map(([key, value]) => <div key={key}><span>{labelFor(key)}</span><strong>{displayValue(value)}</strong></div>)}</div></details>}
        </article>
      </div>;
    })}</div> : <div className="empty-card">No linked customer activity yet.</div>}
    {events.length > 20 && <button type="button" className="secondary-button lifecycle-more" onClick={() => setShowAll(value => !value)}>{showAll ? "Show recent activity" : `Show all ${events.length} events`}</button>}
  </section>;
}
