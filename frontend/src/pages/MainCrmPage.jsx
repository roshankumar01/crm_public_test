import StatusUpdateControl from "../components/StatusUpdateControl";
import ReminderControl from "../components/ReminderControl";
import VerificationTick from "../components/VerificationTick";
﻿import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { assignMainCrmLead, getCounselors, getMainCrmFilterOptions, getMainCrmLeads, getMainCrmSummary, updateMainCrmLeadStatus } from "../api";
import { useAuth } from "../context/AuthContext.jsx";
import LeadFilterSelect from "../components/LeadFilterSelect.jsx";
import "./main-crm-pipeline.css";

const SOURCES = [["ALL", "All leads"], ["INFO_EMAIL_LEADS", "Info email leads"], ["LIVE_ONLINE_LEADS", "Live online leads"], ["DIRECT_CALLS", "Direct calls"]];
const STATUSES = [["NEW", "New"], ["NO_RESPONSE", "No Response"], ["FOLLOW_UP", "Follow up"], ["LATER", "Later"], ["CONVERTED", "Converted"], ["CALL_ME_LATER", "Call me later"], ["GOOD", "Good"], ["NOT_INTERESTED", "Not interested"], ["INVALID", "Invalid"], ["HOT", "Hot"], ["OTHERS", "Others"], ["BLANK", "blank"]];
const LEGACY_STATUSES = [["IN_CONTACT", "In contact"], ["REJECTED", "Rejected"]];
const FILTER_KEYS = [["counselorIds", "counselor", "Counselors", "counselors", "◎"], ["statuses", "status", "Statuses", "statuses", "◈"], ["sources", "lead_source", "Sources", "sources", "↗"], ["courses", "course", "Courses", "courses", "▤"]];
const statusLabels = Object.fromEntries([...STATUSES, ...LEGACY_STATUSES]);
const emptyFilters = () => Object.fromEntries(FILTER_KEYS.map(([key]) => [key, []]));
function optionsFor(lead) {
  const options = lead.is_migrated ? STATUSES : [...STATUSES, ...LEGACY_STATUSES];
  return options.some(([value]) => value === lead.status_of_lead) ? options : [...options, [lead.status_of_lead, lead.status_of_lead.replaceAll("_", " ")]];
}
function DateCell({ value }) {
  const date = value ? new Date(value) : null;
  return <td className="crm-date-cell" title={value || "Date unavailable"}>{date && !Number.isNaN(date.getTime()) ? <><time dateTime={value}>{date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })}</time><small>{date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</small></> : "—"}</td>;
}

export default function MainCrmPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const isAdmin = user?.role === "ADMIN";
  const [result, setResult] = useState(null), [summary, setSummary] = useState(null);
  const [counselors, setCounselors] = useState([]), [filterOptions, setFilterOptions] = useState({});
  const [loading, setLoading] = useState(false), [saving, setSaving] = useState(null);
  const [message, setMessage] = useState(""), [refreshKey, setRefreshKey] = useState(0);
  const activeSource = SOURCES.some(([value]) => value === params.get("source")) ? params.get("source") : "ALL";
  const search = params.get("q") || "";
  const page = Math.max(1, Number.parseInt(params.get("page"), 10) || 1);
  const filters = Object.fromEntries(FILTER_KEYS.map(([key, param]) => [key, params.getAll(param)]));
  const filterSignature = JSON.stringify(filters);
  const [draftFilters, setDraftFilters] = useState(filters), [searchInput, setSearchInput] = useState(search);
  const sortBy = params.get("sort") === "created_at" ? "created_at" : "updated_at";
  const sortDirection = params.get("order") === "asc" ? "asc" : "desc";
  useEffect(() => { setSearchInput(search); }, [search]);
  useEffect(() => { setDraftFilters(filters); }, [filterSignature]);

  function submitSearch(event) {
    event.preventDefault();
    setParams(current => {
      const next = new URLSearchParams(current), term = searchInput.trim();
      if (term) next.set("q", term); else next.delete("q");
      FILTER_KEYS.forEach(([key, param]) => { next.delete(param); draftFilters[key].forEach(value => next.append(param, value)); });
      next.delete("page"); return next;
    });
  }
  function resetFilters() {
    setSearchInput(""); setDraftFilters(emptyFilters());
    setParams(current => { const next = new URLSearchParams(current); FILTER_KEYS.forEach(([, param]) => next.delete(param)); next.delete("q"); next.delete("page"); return next; });
  }
  function removeFilter(param, value) {
    setParams(current => { const next = new URLSearchParams(current), remaining = next.getAll(param).filter(item => item !== value); next.delete(param); remaining.forEach(item => next.append(param, item)); next.delete("page"); return next; });
  }
  function selectSort(field, direction) {
    setParams(current => { const next = new URLSearchParams(current); next.set("sort", field); next.set("order", direction); next.delete("page"); return next; });
  }
  function selectSource(source) {
    setParams(current => { const next = new URLSearchParams(current); if (source === "ALL") next.delete("source"); else next.set("source", source); next.delete("page"); return next; });
  }
  function selectPage(nextPage) {
    setParams(current => { const next = new URLSearchParams(current); if (nextPage <= 1) next.delete("page"); else next.set("page", String(nextPage)); return next; });
  }
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setMessage("");
    getMainCrmLeads({ page, sourceCategory: activeSource, search, ...filters, sortBy, sortDirection })
      .then(data => { if (!cancelled) { setResult(data); if (page > data.pages) selectPage(data.pages); } })
      .catch(error => { if (!cancelled) { setMessage(error.message); setResult(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, activeSource, search, filterSignature, sortBy, sortDirection, refreshKey]);
  useEffect(() => {
    let cancelled = false;
    getMainCrmFilterOptions(activeSource).then(data => { if (!cancelled) setFilterOptions(data); }).catch(error => { if (!cancelled) setMessage(error.message); });
    return () => { cancelled = true; };
  }, [activeSource, refreshKey]);
  useEffect(() => {
    let cancelled = false;
    getMainCrmSummary().then(data => { if (!cancelled) setSummary(data); }).catch(error => { if (!cancelled) setMessage(error.message); });
    return () => { cancelled = true; };
  }, [refreshKey]);
  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    getCounselors().then(data => { if (!cancelled) setCounselors(data); }).catch(error => { if (!cancelled) setMessage(error.message); });
    return () => { cancelled = true; };
  }, [isAdmin]);
  async function changeStatus(id, status, note) {
    try { setSaving(id); await updateMainCrmLeadStatus(id, status, note); setRefreshKey(value => value + 1); }
    catch (error) { setMessage(error.message); throw error; } finally { setSaving(null); }
  }
  async function changeCounselor(id, value) {
    try { setSaving(id); await assignMainCrmLead(id, value ? Number(value) : null); setRefreshKey(value => value + 1); }
    catch (error) { setMessage(error.message); } finally { setSaving(null); }
  }
  if (!result && !message) return <div className="page"><div className="loading-state"><span/>Loading Main CRM…</div></div>;
  const leads = result?.items || [];
  const appliedCount = Object.values(filters).reduce((sum, values) => sum + values.length, 0);
  const pending = JSON.stringify(draftFilters) !== filterSignature || searchInput.trim() !== search;
  const displayOptions = { ...filterOptions, statuses: (filterOptions.statuses || []).map(option => ({ ...option, label: statusLabels[option.value] || option.label.replaceAll("_", " ") })) };
  const dateHeading = (field, label) => <th aria-sort={sortBy === field ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" className={`crm-date-sort ${sortBy === field ? "active" : ""}`} onClick={() => selectSort(field, sortBy === field && sortDirection === "desc" ? "asc" : "desc")} title={`Sort by ${label.toLowerCase()}`} aria-label={`Sort by ${label.toLowerCase()}`}>{label}<span aria-hidden="true">{sortBy === field ? (sortDirection === "desc" ? "↓" : "↑") : "↕"}</span></button></th>;
  return <div className="page main-crm-page">
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM</div><h1>Lead pipeline</h1><p className="page-description">Manage every enquiry before registration and connect converted people to their learner lifecycle.</p></div><div className="opportunity-count">{(summary?.total ?? result?.total ?? 0).toLocaleString()}<span>total leads</span></div></div>
    {message && <div className="upload-message page-message">{message}</div>}
    <div className="main-crm-source-tabs">{SOURCES.map(([value, label]) => <button type="button" key={value} className={activeSource === value ? "source-tab active" : "source-tab"} onClick={() => selectSource(value)}>{label}<span>{value === "ALL" ? summary?.total ?? "…" : summary?.source_category_counts?.[value] ?? "…"}</span></button>)}</div>
    <form className="crm-filter-panel" onSubmit={submitSearch}>
      <div className="crm-filter-heading"><div><strong>Refine your pipeline</strong><small className={pending ? "pending" : ""}>{pending ? "Changes ready to apply" : appliedCount ? `${appliedCount} selections applied` : "Combine filters to find the right leads"}</small></div><button type="button" onClick={resetFilters} disabled={!appliedCount && !search && !pending}>Reset filters</button></div>
      <div className="crm-filter-search"><input className="search-input" value={searchInput} onChange={event => setSearchInput(event.target.value)} placeholder="Search name, email, phone, course or source" aria-label="Search leads" maxLength={320}/><span className="crm-filter-count">{loading ? "Updating results…" : <><strong>{(result?.total ?? 0).toLocaleString()}</strong>matching leads</>}</span></div>
      <div className="crm-filter-grid">{FILTER_KEYS.map(([key, , label, optionKey, icon]) => <LeadFilterSelect key={key} label={label} icon={icon} options={displayOptions[optionKey] || []} selected={draftFilters[key]} onChange={values => setDraftFilters(current => ({ ...current, [key]: values }))}/>)}<button type="submit" className="primary-button" disabled={loading}>Apply filters</button></div>
      {appliedCount > 0 && <div className="crm-filter-chips">{FILTER_KEYS.flatMap(([key, param, label, optionKey]) => filters[key].map(value => <button type="button" key={`${key}-${value}`} onClick={() => removeFilter(param, value)} aria-label={`Remove ${label.toLowerCase()} filter ${displayOptions[optionKey]?.find(option => option.value === value)?.label || value}`}><span>{label}: {displayOptions[optionKey]?.find(option => option.value === value)?.label || value}</span><b aria-hidden="true">×</b></button>))}</div>}
    </form>
    <div className="crm-results-meta"><span>Dates shown in your local time</span><label>Sort <select aria-label="Sort leads by date" value={`${sortBy}:${sortDirection}`} onChange={event => { const [field, direction] = event.target.value.split(":"); selectSort(field, direction); }}><option value="updated_at:desc">Updated · newest first</option><option value="updated_at:asc">Updated · oldest first</option><option value="created_at:desc">Created · newest first</option><option value="created_at:asc">Created · oldest first</option></select></label></div>
    <div className={`table-card pipeline-table ${loading ? "crm-results-loading" : ""}`} aria-busy={loading}><table className="main-leads-table crm-dated-table"><thead><tr><th>Lead</th><th>Source</th><th>Course / Region</th><th>Status</th><th>Counselor</th>{dateHeading("created_at", "Created date")}{dateHeading("updated_at", "Updated date")}<th>Profile</th></tr></thead><tbody>{leads.map(lead => <tr key={lead.id}>
      <td><div className="learner-cell"><div className="avatar">{lead.full_name?.[0]?.toUpperCase()}</div><div><Link className="profile-name-link" to={`/crm/leads/${lead.id}`} state={{ from: location.pathname + location.search }}>{lead.full_name}</Link><div className="small-muted">{lead.email || "No email"}</div><div className="small-muted">{lead.phone_number || "No phone"}</div></div></div></td>
      <td><strong>{lead.source || "—"}</strong><div className="small-muted">{SOURCES.find(item => item[0] === lead.source_category)?.[1]}</div>{lead.is_migrated && <div className="small-muted">Migrated</div>}</td>
      <td><strong>{lead.course || "—"}</strong><div className="small-muted">{lead.region || "No region"}{lead.age ? ` · Age ${lead.age}` : ""}</div></td>
      <td><StatusUpdateControl value={lead.status_of_lead} options={optionsFor(lead)} disabled={loading || saving === lead.id} onSave={(status,note)=>changeStatus(lead.id,status,note)}/>{lead.status_of_lead==="CONVERTED"&&<VerificationTick record={lead}/>}</td>
      <td>{isAdmin ? <select className="compact-select" value={lead.assigned_to_user_id || ""} disabled={loading || saving === lead.id} onChange={event => changeCounselor(lead.id, event.target.value)}><option value="">Unassigned</option>{counselors.map(counselor => <option key={counselor.id} value={counselor.id}>{counselor.display_name}</option>)}</select> : <strong>{lead.counselor || "Unassigned"}</strong>}<div className="small-muted">{lead.counselor_email || "No counselor email"}</div></td>
      <DateCell value={lead.created_at}/><DateCell value={lead.updated_at}/>
      <td><Link className="text-link" to={`/crm/leads/${lead.id}`} state={{ from: location.pathname + location.search }}>View full profile →</Link><ReminderControl workspace="main" leadId={lead.id} compact/>{lead.matched_learner_number && <div className="small-muted">Registered learner #{lead.matched_learner_number}</div>}</td>
    </tr>)}</tbody></table>{!leads.length && <div className="table-message">No leads match these filters.</div>}</div>
    {result && <nav className="crm-pagination" aria-label="Lead pages"><button className="secondary-button" disabled={loading || page <= 1} onClick={() => selectPage(page - 1)}>← Previous</button><span>Page {result.page} of {result.pages}</span><button className="secondary-button" disabled={loading || page >= result.pages} onClick={() => selectPage(page + 1)}>Next →</button></nav>}
  </div>;
}
