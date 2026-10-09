import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getUpsellContacts } from "../api";

export default function LearnersPage() {
  const [result, setResult] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getUpsellContacts(submittedSearch, page).then(setResult).finally(() => setLoading(false));
  }, [submittedSearch, page]);

  return <div className="page">
    <div className="page-header"><div><div className="eyebrow">CRM</div><h1>Learners</h1><p className="page-description">Search learners and inspect their complete learning journey.</p></div></div>
    <form className="toolbar" onSubmit={event => { event.preventDefault(); setPage(1); setSubmittedSearch(search.trim()); }}><input className="search-input" placeholder="Search by name, email or phone..." value={search} onChange={e => setSearch(e.target.value)} /><button className="primary-button" type="submit">Search</button></form>
    <div className="table-card"><table><thead><tr><th>Learner</th><th>Learner number</th><th>Email</th><th>Phone</th><th>Counselor</th><th>Last activity</th><th></th></tr></thead><tbody>
      {!loading && result.items.map(l => <tr key={l.customer_id}><td><div className="learner-cell"><div className="avatar">{l.name?.charAt(0)?.toUpperCase()}</div><strong>{l.name}</strong></div></td><td>{l.learner_number || "—"}</td><td>{l.email_id || "—"}</td><td>{l.contact_number || "—"}</td><td><strong>{l.assigned_to_name || "Unassigned"}</strong>{l.assignment_source === "MAIN_CRM" && <div className="small-muted">From Main CRM</div>}</td><td>{l.last_activity_date || "—"}</td><td><Link className="text-link" to={`/upsell/contacts/${l.customer_id}`}>View →</Link></td></tr>)}
    </tbody></table>{loading && <div className="table-message">Loading learners...</div>}{!loading && result.items.length === 0 && <div className="table-message">No learners found.</div>}</div>
    <div className="toolbar toolbar-space"><span className="small-muted">Page {result.page} of {result.pages} · {result.total} learners</span><div className="toolbar-actions"><button className="secondary-button" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>Previous</button><button className="secondary-button" disabled={page >= result.pages} onClick={() => setPage(value => value + 1)}>Next</button></div></div>
  </div>;
}
