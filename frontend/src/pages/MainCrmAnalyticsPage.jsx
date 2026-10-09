import { useEffect, useState } from "react";
import { getMainCrmSummary } from "../api";

export default function MainCrmAnalyticsPage() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getMainCrmSummary().then(setSummary).catch(requestError => setError(requestError.message)); }, []);
  if (!summary) return <div className="page"><div className="loading-state"><span />{error || "Loading analytics..."}</div></div>;
  const sortedSources = Object.entries(summary.source_breakdown || {}).sort(([, first], [, second]) => second.total - first.total);
  const sourceRows = sortedSources.length > 50 ? [...sortedSources.slice(0, 50), ["Other sources", sortedSources.slice(50).reduce((total, [, row]) => ({ total: total.total + row.total, converted: total.converted + row.converted, registered: total.registered + row.registered }), { total: 0, converted: 0, registered: 0 })]] : sortedSources;
  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM ANALYTICS</div><h1>Lead analytics</h1><p className="page-description">Source volumes, conversions, and registered-customer matching.</p></div></div>
    <div className="simple-stats"><div className="simple-stat main"><span>Total leads</span><strong>{summary.total}</strong><small>All uploaded enquiries</small></div><div className="simple-stat"><span>Converted</span><strong>{summary.status_counts?.CONVERTED || 0}</strong><small>Marked converted</small></div><div className="simple-stat"><span>Registered</span><strong>{summary.registered}</strong><small>Linked learner lifecycle</small></div><div className="simple-stat"><span>Unassigned</span><strong>{summary.unassigned}</strong><small>Need a counselor</small></div></div>
    <section className="feature-card performance-table"><div className="card-heading"><div><div className="eyebrow">SOURCE BREAKDOWN</div><h2>Performance by data source</h2></div></div><div className="table-card"><table><thead><tr><th>Source</th><th>Leads</th><th>Converted</th><th>Registered</th><th>Conversion rate</th></tr></thead><tbody>{sourceRows.map(([value, row]) => <tr key={value}><td><strong>{value}</strong></td><td>{row.total}</td><td>{row.converted}</td><td>{row.registered}</td><td>{row.total ? Math.round(row.converted / row.total * 100) : 0}%</td></tr>)}</tbody></table></div></section>
  </div>;
}
