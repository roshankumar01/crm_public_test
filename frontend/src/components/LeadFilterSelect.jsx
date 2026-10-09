import { useEffect, useRef, useState } from "react";

export default function LeadFilterSelect({ label, options = [], selected = [], onChange, icon }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(60);
  const root = useRef(null);
  const trigger = useRef(null);
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const escape = event => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  const choices = options.filter(option => option.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const selectedLabel = selected.length === 1 ? options.find(option => option.value === selected[0])?.label || selected[0] : `${selected.length} selected`;
  return <div className="lead-filter-select" ref={root}>
    <button type="button" ref={trigger} className={`lead-filter-trigger ${selected.length ? "has-value" : ""} ${open ? "is-open" : ""}`} aria-expanded={open} aria-label={`${label} filter${selected.length ? `, ${selected.length} selected` : ""}`} onClick={() => { setOpen(!open); setSearch(""); setLimit(60); }}>
      <span className="lead-filter-icon" aria-hidden="true">{icon}</span><span className="lead-filter-trigger-copy"><small>{label}</small><strong title={selectedLabel}>{selected.length ? selectedLabel : `All ${label.toLowerCase()}`}</strong></span>{selected.length > 0 && <span className="lead-filter-badge">{selected.length}</span>}<span aria-hidden="true">⌄</span>
    </button>
    {open && <div className="lead-filter-menu"><div className="lead-filter-menu-heading"><strong>{label}</strong><button type="button" onClick={() => onChange([])} disabled={!selected.length}>Clear</button></div>
      <input autoFocus aria-label={`Search ${label.toLowerCase()} options`} value={search} onChange={event => { setSearch(event.target.value); setLimit(60); }} onKeyDown={event => { if (event.key === "Enter") event.preventDefault(); }} placeholder={`Search ${label.toLowerCase()}…`} maxLength={255}/>
      <div className="lead-filter-option-list">{choices.slice(0, limit).map(option => <label key={option.value} className={selected.includes(option.value) ? "selected" : ""}><input type="checkbox" checked={selected.includes(option.value)} onChange={() => onChange(selected.includes(option.value) ? selected.filter(value => value !== option.value) : [...selected, option.value])}/><span title={option.label}>{option.label}</span><small>{Number(option.count || 0).toLocaleString()}</small></label>)}
        {!choices.length && <p>No matching options</p>}
        {choices.length > limit && <button type="button" className="lead-filter-more" onClick={() => setLimit(limit + 60)}>Show more options</button>}
      </div><div className="lead-filter-menu-footer">{selected.length} selected <span>Click Apply filters to update results</span></div>
    </div>}
  </div>;
}
