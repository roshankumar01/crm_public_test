import StatusUpdateControl from "../components/StatusUpdateControl";
import ReminderControl from "../components/ReminderControl";
import VerificationTick from "../components/VerificationTick";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { assignLead, downloadLeadAnalytics, getCounselors, getOpportunities, getTrackedLeads, updateLeadStatus } from "../api";
import { useAuth } from "../context/AuthContext.jsx";

const STATUS_OPTIONS = [["NEW", "New"], ["IN_CONTACT", "In contact"], ["REJECTED", "Rejected"], ["CONVERTED", "Converted"]];
const PAGE_SIZE = 50;
function Stat({ label, value, caption }) { return <div className="stat-card"><div className="stat-label">{label}</div><div className="stat-value">{value ?? 0}</div><div className="stat-caption">{caption}</div></div>; }
function SortHeader({ label, field, selected, direction, onSort }) { return <th><button className={selected === field ? "column-sort active" : "column-sort"} onClick={() => onSort(field)}>{label} <span>{selected === field ? (direction === "asc" ? "↑" : "↓") : "↕"}</span></button></th>; }

export default function OpportunitiesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [overview, setOverview] = useState(null);
  const [result, setResult] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [counselors, setCounselors] = useState([]);
  const [viewMode, setViewMode] = useState("ALL");
  const [selectedSection, setSelectedSection] = useState("IGC");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [counselorFilter, setCounselorFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("waiting");
  const [direction, setDirection] = useState("desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const loadSummary = useCallback(async () => {
    const [next, users] = await Promise.all([getOpportunities(), isAdmin ? getCounselors() : Promise.resolve([])]);
    setOverview(next); setCounselors(users);
    setSelectedSection(current => next.sections.some(item => item.key === current) ? current : next.sections[0]?.key || "IGC");
  }, [isAdmin]);
  const loadPage = useCallback(async () => {
    const data = await getTrackedLeads({ page, page_size: PAGE_SIZE, active_only: true,
      section: viewMode === "CURRENT" ? selectedSection : undefined, status: statusFilter,
      counselor: isAdmin ? counselorFilter : undefined, search: submittedSearch, sort: sortBy, direction });
    if (page > data.pages) { setPage(data.pages); return; }
    setResult(data);
  }, [page, viewMode, selectedSection, statusFilter, counselorFilter, submittedSearch, sortBy, direction, isAdmin]);
  useEffect(() => { loadSummary().then(loadPage).catch(err => setError(err.message)).finally(() => setLoading(false)); }, [loadSummary, loadPage]);
  useEffect(() => { const timer = setInterval(() => { loadSummary().then(loadPage).catch(err => setError(err.message)); }, 60000); return () => clearInterval(timer); }, [loadSummary, loadPage]);
  function resetPage(setter, value) { setter(value); setPage(1); }
  function onSort(field) { if (sortBy === field) setDirection(current => current === "asc" ? "desc" : "asc"); else { setSortBy(field); setDirection("asc"); } setPage(1); }
  async function mutate(id, action, rethrow=false) { setSaving(id); setError(""); try { await action(); await Promise.all([loadSummary(), loadPage()]); } catch (err) { setError(err.message); if(rethrow) throw err; } finally { setSaving(null); } }
  async function download() { setDownloading(true); setError(""); try { await downloadLeadAnalytics(selectedSection); } catch (err) { setError(err.message); } finally { setDownloading(false); } }
  if (loading) return <div className="page"><div className="loading-state"><span />Loading leads...</div></div>;
  if (error && !overview) return <div className="page"><div className="empty-card">{error}</div></div>;
  const summary = overview?.summary || {};
  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">LEAD PIPELINE</div><h1>{viewMode === "ALL" ? (isAdmin ? "All leads" : "My leads") : "Opportunities"}</h1><p className="page-description">Review leads and update their progress one page at a time.</p></div><div className="opportunity-count">{result.total}<span>matching leads</span></div></div>
    {error && <div className="form-error page-message">{error}</div>}
    <div className="stat-grid"><Stat label="New" value={summary.new} caption="Need first contact" /><Stat label="In contact" value={summary.in_contact} caption="Follow-up in progress" /><Stat label="Converted" value={summary.converted} caption="Successful upsells" /><Stat label="Rejected" value={summary.rejected} caption="Offers declined" /></div>
    <div className="toolbar toolbar-space"><div className="segmented-control"><button className={viewMode === "ALL" ? "segment active" : "segment"} onClick={() => resetPage(setViewMode, "ALL")}>All leads</button><button className={viewMode === "CURRENT" ? "segment active" : "segment"} onClick={() => resetPage(setViewMode, "CURRENT")}>Opportunities</button></div><div className="toolbar-actions"><Link className="secondary-button" to="/upsell/lead-analytics">View analytics →</Link>{viewMode === "CURRENT" && <button className="primary-button" onClick={download} disabled={downloading}>{downloading ? "Preparing Excel..." : "Download this stage ↓"}</button>}</div></div>
    {viewMode === "CURRENT" && <div className="toolbar course-filter"><select className="search-input" aria-label="Opportunity stage" value={selectedSection} onChange={event => resetPage(setSelectedSection, event.target.value)}>{(overview?.sections || []).map(item => <option key={item.key} value={item.key}>{item.title} ({item.count})</option>)}</select></div>}
    <form className="pipeline-filters" onSubmit={event => { event.preventDefault(); resetPage(setSubmittedSearch, search.trim()); }}><input className="search-input" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search learner, email, phone or board number" /><button className="primary-button" type="submit">Search</button><select className="compact-select" value={statusFilter} onChange={event => resetPage(setStatusFilter, event.target.value)}><option value="ALL">All statuses</option>{STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>{isAdmin && <select className="compact-select" value={counselorFilter} onChange={event => resetPage(setCounselorFilter, event.target.value)}><option value="ALL">All counselors</option><option value="UNASSIGNED">Unassigned</option>{counselors.map(item => <option key={item.id} value={String(item.id)}>{item.display_name}</option>)}</select>}<span className="filter-count">{result.total} found</span></form>
    <div className="table-card pipeline-table"><table><thead><tr><SortHeader label="Learner" field="learner" selected={sortBy} direction={direction} onSort={onSort} /><SortHeader label="Trigger" field="trigger" selected={sortBy} direction={direction} onSort={onSort} /><th>Latest campaign</th><SortHeader label="Waiting" field="waiting" selected={sortBy} direction={direction} onSort={onSort} /><SortHeader label="Status" field="status" selected={sortBy} direction={direction} onSort={onSort} /><SortHeader label="Counselor" field="counselor" selected={sortBy} direction={direction} onSort={onSort} /><SortHeader label="Contact" field="contact" selected={sortBy} direction={direction} onSort={onSort} /><th>Action</th></tr></thead><tbody>{result.items.map(lead => <tr key={lead.lead_id}><td><div className="learner-cell"><div className="avatar">{lead.name?.[0]?.toUpperCase()}</div><div><strong>{lead.name}</strong><div className="small-muted">{lead.learner_number ? `#${lead.learner_number} · ` : ""}{lead.target_name}</div></div></div></td><td><strong>{lead.trigger_courses?.join(", ") || lead.target_code}</strong><div className="small-muted">{lead.trigger_date || "No date"}</div></td><td>{lead.latest_campaign ? <div className="campaign-cell"><span>{lead.latest_campaign.marketing_type}</span><strong>{lead.latest_campaign.campaign_name}</strong></div> : "—"}</td><td>{lead.days_since_trigger != null ? `${lead.days_since_trigger} days` : "—"}</td><td><StatusUpdateControl value={lead.status} options={STATUS_OPTIONS.map(([value,label])=>[value,label,value==="CONVERTED"])} disabled={saving === lead.lead_id} onSave={(status,note)=>mutate(lead.lead_id,()=>updateLeadStatus(lead.lead_id,status,note),true)}/>{lead.status==="CONVERTED"&&<VerificationTick record={lead}/>}<div className="small-muted">Record conversions in Manage</div></td><td>{isAdmin ? <select className="compact-select" value={lead.assigned_to_user_id || ""} disabled={saving === lead.lead_id} onChange={event => mutate(lead.lead_id, () => assignLead(lead.lead_id, event.target.value ? Number(event.target.value) : null))}><option value="">Unassigned</option>{counselors.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select> : <strong>{lead.assigned_to_name || "Unassigned"}</strong>}{lead.assignment_source === "MAIN_CRM" && <div className="small-muted">From Main CRM</div>}</td><td><div>{lead.email_id || "—"}</div><div className="small-muted">{lead.contact_number || "—"}</div></td><td><Link className="text-link" to={`/upsell/leads/${lead.lead_id}`}>Manage →</Link><ReminderControl workspace="upsell" leadId={lead.lead_id} compact/></td></tr>)}</tbody></table>{!result.items.length && <div className="table-message">No leads match these filters.</div>}</div>
    <div className="toolbar toolbar-space"><span className="small-muted">Page {result.page} of {result.pages} · {result.total} leads</span><div className="toolbar-actions"><button className="secondary-button" disabled={page <= 1} onClick={() => setPage(current => current - 1)}>Previous</button><button className="secondary-button" disabled={page >= result.pages} onClick={() => setPage(current => current + 1)}>Next</button></div></div>
  </div>;
}
