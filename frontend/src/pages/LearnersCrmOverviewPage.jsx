import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { downloadLearnersCrmExport, getLearnersCrmOverview } from "../api";

export default function LearnersCrmOverviewPage() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(""); const [period, setPeriod] = useState("all");

  useEffect(() => {
    setSummary(null); getLearnersCrmOverview(period).then(setSummary).catch(requestError => setError(requestError.message));
  }, [period]);

  if (!summary) return <div className="page"><div className="loading-state"><span />{error || "Loading learner overview..."}</div></div>;

  return <div className="page">
    <div className="overview-filter"><label>Date range <select className="search-input" value={period} onChange={event => setPeriod(event.target.value)}><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_month">Last 1 month</option><option value="all">All time</option></select></label><button className="secondary-button" onClick={() => downloadLearnersCrmExport(period)}>Download full data</button></div>
    <div className="page-header simple-header"><div><div className="eyebrow">LEARNERS CRM</div><h1>Learner overview</h1><p className="page-description">Registered learners and their course enrolments.</p></div><Link className="primary-button" to="/learners-crm/learners">Find learner &rarr;</Link></div>
    <div className="simple-stats">
      <div className="simple-stat main"><span>Total learners</span><strong>{summary.total_learners}</strong><small>Unique email addresses</small></div>
      <div className="simple-stat"><span>Course enrolments</span><strong>{summary.total_enrolments}</strong><small>Unique enrolment IDs</small></div>
      <div className="simple-stat"><span>Active enrolments</span><strong>{summary.active}</strong><small>Completion status: Not Completed</small></div>
      <div className="simple-stat"><span>Completed enrolments</span><strong>{summary.completed}</strong><small>Completion status: Completed</small></div>
    </div>
    <div className="dashboard-panel"><div><div className="eyebrow">CONNECTED LIFECYCLE</div><h2>{summary.matched_enquiries} learners match Main CRM enquiries</h2><p>Matching uses normalized email to connect enquiry history to learner activity.</p></div></div>
    <div className="section-heading journey-heading"><div><div className="eyebrow">COURSE MAPPING</div><h2>Enrolments by category</h2></div></div>
    <div className="table-card"><table><thead><tr><th>Category</th><th>Enrolments</th></tr></thead><tbody>{(summary.course_categories || []).map(category => <tr key={category.name}><td><strong>{category.name}</strong></td><td>{category.enrolments}</td></tr>)}</tbody></table>{!summary.course_categories?.length && <div className="table-message">No learner courses uploaded yet.</div>}</div>
  </div>;
}
