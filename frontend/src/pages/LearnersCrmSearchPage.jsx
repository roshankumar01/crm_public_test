import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { searchLearnersCrm } from "../api";

export default function LearnersCrmSearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryFromUrl = searchParams.get("search") || "";
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const [search, setSearch] = useState(queryFromUrl);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeQuery, setActiveQuery] = useState(queryFromUrl);

  useEffect(() => {
    let cancelled = false;
    setSearch(queryFromUrl);
    setActiveQuery(queryFromUrl);
    setLoading(true);
    setResults(null);
    setError("");
    searchLearnersCrm(queryFromUrl, page).then(rows => { if (!cancelled) setResults(rows); })
      .catch(requestError => { if (!cancelled) setError(requestError.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [queryFromUrl, page]);

  function submit(event) {
    event.preventDefault();
    const query = search.trim();
    setSearchParams(query ? { search: query, page: "1" } : { page: "1" });
  }

  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">LEARNERS CRM</div><h1>Find a learner</h1><p className="page-description">Recent learners appear below. Search by email address, phone number, or enrolment ID to see all their course enrolments.</p></div></div>
    <form className="learner-search-form" onSubmit={submit} role="search">
      <label className="sr-only" htmlFor="learner-search">Email, phone number, or enrolment ID</label>
      <input id="learner-search" className="search-input" value={search} onChange={event => setSearch(event.target.value)} maxLength={320} placeholder="Email, phone number, or enrolment ID" />
      <button className="primary-button" type="submit" disabled={loading}>{loading ? "Loading..." : search.trim() ? "Search learners" : "Show recent learners"}</button>
    </form>
    {error && <div className="upload-message page-message">{error}</div>}
    {loading && <div className="loading-state"><span />Loading learners...</div>}
    {results?.length === 0 && <div className="empty-card">{activeQuery ? "No learners matched that search." : "No learners have been uploaded yet."}</div>}
    {results?.length > 0 && <div className="learner-search-results">
      <div className="section-heading"><div><div className="eyebrow">{activeQuery ? "SEARCH RESULTS" : "RECENT LEARNERS"}</div><h2>{activeQuery ? `${results.length} learner${results.length === 1 ? "" : "s"} found` : "Recently updated learners"}</h2></div></div>
      <p className="small-muted">Page {page}. Showing up to five recent enrolments per learner; open a profile for the full history.</p>
      {results.map(learner => <section className="feature-card learner-search-result" key={learner.id}>
        <div className="learner-search-header"><div><div className="eyebrow">LEARNER</div><h2><Link className="profile-name-link" to={`/learners-crm/learners/${learner.id}`} state={{ search: activeQuery }}>{learner.learner_name}</Link></h2><Link className="text-link" to={`/learners-crm/learners/${learner.id}`} state={{ search: activeQuery }}>View full profile →</Link></div><div className="learner-search-contact"><span>{learner.email_id}</span><span>{learner.phone_number || "No phone number"}</span><span>Counselor: <strong>{learner.assigned_to_name || "Unassigned"}</strong>{learner.assignment_source === "MAIN_CRM" && <small className="small-muted"> ? Main CRM</small>}</span></div></div>
        <div className="table-card"><table><thead><tr><th>Enrolment ID</th><th>Course</th><th>Category</th><th>Status</th><th>Enrolment date</th><th>Start date</th><th>Completion date</th></tr></thead><tbody>{learner.enrolments.map(enrolment => <tr key={enrolment.enrolment_id}><td><strong>{enrolment.enrolment_id}</strong> <span className={`learner-verification-tick ${enrolment.verification_status === "UNMATCHED" ? "unmatched" : "verified"}`} title={enrolment.verification_status === "UNMATCHED" ? "Migrated learner without Main CRM match; eligible for Upsell" : "Verified learner"}>✓</span></td><td>{enrolment.course_name}</td><td>{enrolment.course_category || "Unmapped"}</td><td><span className={enrolment.completion_status?.trim().toLowerCase() === "completed" ? "status-pill pass" : "status-pill"}>{enrolment.completion_status || "—"}</span></td><td>{enrolment.enrolment_date || "—"}</td><td>{enrolment.start_date || "—"}</td><td>{enrolment.completion_date || "—"}</td></tr>)}</tbody></table></div>
      </section>)}
      <div className="toolbar toolbar-space"><button className="secondary-button" disabled={page <= 1} onClick={() => setSearchParams(activeQuery ? { search: activeQuery, page: String(page - 1) } : { page: String(page - 1) })}>Previous</button><button className="secondary-button" disabled={results.length < 25} onClick={() => setSearchParams(activeQuery ? { search: activeQuery, page: String(page + 1) } : { page: String(page + 1) })}>Next</button></div>
    </div>}
  </div>;
}
