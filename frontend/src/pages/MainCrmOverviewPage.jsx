import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { downloadMainCrmExport, getMainCrmSummary } from "../api";
import { useAuth } from "../context/AuthContext.jsx";

export default function MainCrmOverviewPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(""); const [period, setPeriod] = useState("all");

  useEffect(() => { setSummary(null); getMainCrmSummary(period).then(setSummary).catch(requestError => setError(requestError.message)); }, [period]);
  if (!summary) return <div className="page"><div className="loading-state"><span />{error || "Loading overview..."}</div></div>;

  const count = status => summary.status_counts?.[status] || 0;
  const breakdown = status => summary.status_breakdown?.[status] || { total: count(status), normal: count(status), migrated: 0 };
  const progressTotal = ["IN_CONTACT", "NO_RESPONSE", "FOLLOW_UP", "LATER", "CALL_ME_LATER", "GOOD", "HOT"].reduce((total, status) => total + count(status), 0);
  const sortedSources = Object.entries(summary.source_counts || {}).sort(([, first], [, second]) => second - first);
  const sourceRows = sortedSources.length > 12 ? [...sortedSources.slice(0, 12), ["Other sources", sortedSources.slice(12).reduce((total, [, value]) => total + value, 0)]] : sortedSources;

  return <div className="page">
    <div className="overview-filter"><label>Date range <select className="search-input" value={period} onChange={event => setPeriod(event.target.value)}><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_month">Last 1 month</option><option value="all">All time</option></select></label><button className="secondary-button" onClick={() => downloadMainCrmExport(period)}>Download full data</button></div>
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM OVERVIEW</div><h1>Enquiry performance</h1><p className="page-description">A simple view of incoming leads, counselor activity, and registrations.</p></div><Link className="primary-button" to="/crm/leads">View lead pipeline →</Link></div>
    <div className="simple-stats"><div className="simple-stat main"><span>Total enquiries</span><strong>{summary.total}</strong><small>Across every source</small></div><div className="simple-stat"><span>New</span><strong>{breakdown("NEW").total}</strong><div className="overview-split"><span>Normal <b>{breakdown("NEW").normal}</b></span><span>Migrated <b>{breakdown("NEW").migrated}</b></span></div></div><div className="simple-stat"><span>In progress</span><strong>{progressTotal}</strong><div className="overview-split"><span>Normal <b>{["IN_CONTACT", "NO_RESPONSE", "FOLLOW_UP", "LATER", "CALL_ME_LATER", "GOOD", "HOT"].reduce((total, status) => total + breakdown(status).normal, 0)}</b></span><span>Migrated <b>{["IN_CONTACT", "NO_RESPONSE", "FOLLOW_UP", "LATER", "CALL_ME_LATER", "GOOD", "HOT"].reduce((total, status) => total + breakdown(status).migrated, 0)}</b></span></div></div><div className="simple-stat"><span>Registered</span><strong>{summary.registered}</strong><small>Matched to Upsell CRM</small></div></div>
    <div className="simple-dashboard-grid">
      <section className="feature-card"><div className="card-heading"><div><div className="eyebrow">LEAD SOURCES</div><h2>Where enquiries come from</h2></div></div><div className="plain-progress-list">{sourceRows.map(([source, total]) => <div className="plain-progress" key={source}><div><span>{source}</span><strong>{total}</strong></div><div className="plain-progress-track"><i style={{ width: `${summary.total ? total / summary.total * 100 : 0}%`, background: "#7357ff" }} /></div></div>)}{!sourceRows.length && <div className="table-message">No enquiry sources yet.</div>}</div></section>
      <section className="feature-card action-card"><div className="card-heading"><div><div className="eyebrow">NEXT STEPS</div><h2>Manage your CRM</h2></div></div><div className="action-list"><Link to="/crm/leads"><span>1</span><div><strong>Work the lead pipeline</strong><small>Assign counselors and update lead status</small></div><b>→</b></Link><Link to="/crm/analytics"><span>2</span><div><strong>Review analytics</strong><small>Compare source and conversion performance</small></div><b>→</b></Link>{user?.role === "ADMIN" && <Link to="/crm/uploads"><span>3</span><div><strong>Manage data uploads</strong><small>Create or replace an Excel upload</small></div><b>→</b></Link>}</div></section>
    </div>
  </div>;
}
