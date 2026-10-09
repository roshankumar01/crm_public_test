import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { getCompanyDashboard, getCompanySalesCourses, getCompanySalesSources } from "../api";
import "./company-dashboard.css";

const formatNumber = value => Number(value || 0).toLocaleString();
const localDate = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
export const rangePreset = days => {
  if (days === "all") return { startDate: "", endDate: "" };
  const end = new Date(), start = new Date();
  if (days === "yesterday") { end.setDate(end.getDate() - 1); start.setDate(start.getDate() - 1); }
  else if (days === "year") start.setMonth(0, 1);
  else start.setDate(end.getDate() - days + 1);
  return { startDate: localDate(start), endDate: localDate(end) };
};
const initialRange = () => {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem("company_dashboard_range") || "null");
    if (saved?.startDate && saved?.endDate && saved.startDate <= saved.endDate) return saved;
  } catch {}
  return { startDate: "", endDate: "" };
};

export function DateRangePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState("");
  const root = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const escape = event => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  const apply = range => { onChange(range); setDraft(range); setError(""); setOpen(false); };
  const label = value.startDate ? `${new Date(`${value.startDate}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} – ${new Date(`${value.endDate}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}` : "All time";
  return <div className="cd-date-picker" ref={root}>
    <button type="button" className={`cd-date-trigger ${open ? "active" : ""}`} aria-expanded={open} onClick={() => { setDraft(value); setError(""); setOpen(!open); }}><span className="cd-date-icon" aria-hidden="true">▦</span><span><small>DATE RANGE</small><strong>{label}</strong></span><span className="cd-date-chevron">⌄</span></button>
    {open && <div className="cd-date-popover"><div className="cd-date-popover-head"><strong>Choose a date range</strong><span>Filter every dashboard metric</span></div>
      <div className="cd-date-presets">{[[1, "Today"], ["yesterday", "Yesterday"], [7, "Last 7 days"], [30, "Last 1 month"], ["year", "This year"], ["all", "All time"]].map(([days, name]) => <button type="button" key={name} onClick={() => apply(rangePreset(days))}>{name}</button>)}</div>
      <div className="cd-date-fields"><label>From<input type="date" value={draft.startDate} onChange={event => setDraft({ ...draft, startDate: event.target.value })}/></label><label>To<input type="date" value={draft.endDate} onChange={event => setDraft({ ...draft, endDate: event.target.value })}/></label></div>
      {error && <p className="cd-date-error">{error}</p>}
      <div className="cd-date-actions"><button type="button" className="cd-date-clear" onClick={() => apply(rangePreset("all"))}>Clear range</button><button type="button" className="cd-date-apply" onClick={() => { if (!draft.startDate || !draft.endDate || draft.startDate > draft.endDate) setError("Choose a valid start and end date."); else apply(draft); }}>Apply range</button></div>
    </div>}
  </div>;
}

function MetricCard({ eyebrow, value, detail, accent = "violet", icon }) {
  return <article className={`cd-metric cd-metric-${accent}`}>
    <div className="cd-metric-top"><span>{eyebrow}</span><i aria-hidden="true">{icon}</i></div>
    <strong>{value}</strong><small>{detail}</small>
  </article>;
}

function Panel({ kicker, title, hint, children, className = "" }) {
  return <section className={`cd-panel ${className}`}><div className="cd-panel-heading"><div><span>{kicker}</span><h2>{title}</h2></div>{hint && <small>{hint}</small>}</div>{children}</section>;
}

function TrendChart({ points = [], field, color, name }) {
  if (!points.length) return <div className="cd-empty">No {name.toLowerCase()} data in this period.</div>;
  const width = 720, height = 220, top = 12, bottom = 34, left = 36, right = 10;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const max = Math.max(1, ...points.map(point => Number(point[field] || 0)));
  const coords = points.map((point, index) => [left + index * plotWidth / Math.max(points.length - 1, 1), top + plotHeight * (1 - Number(point[field] || 0) / max)]);
  const path = coords.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${path} L${coords.at(-1)[0].toFixed(1)} ${top + plotHeight} L${coords[0][0].toFixed(1)} ${top + plotHeight} Z`;
  const ticks = [0, 1, 2, 3].map(index => Math.round(max * index / 3));
  const labels = [...new Set([0, Math.round((points.length - 1) / 4), Math.round((points.length - 1) / 2), Math.round((points.length - 1) * 3 / 4), points.length - 1])];
  return <div className="cd-chart-wrap"><svg className="cd-line-chart" role="img" aria-label={`${name} trend`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
    <defs><linearGradient id={`cd-fill-${field}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".22"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
    {ticks.map((tick, index) => { const y = top + plotHeight * (1 - index / 3); return <g key={index}><line x1={left} y1={y} x2={width - right} y2={y} stroke="#e9e7f2" strokeDasharray="4 6"/><text x={left - 8} y={y + 4} textAnchor="end" fill="#a19eae" fontSize="10">{formatNumber(tick)}</text></g>; })}
    <path d={area} fill={`url(#cd-fill-${field})`}/><path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
    {coords.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={points.length > 40 ? 2 : 3.5} fill={color}><title>{`${points[index].label}: ${formatNumber(points[index][field])}`}</title></circle>)}
    {labels.map(index => <text key={index} x={coords[index][0]} y={height - 8} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"} fill="#9491a3" fontSize="10">{points[index].label}</text>)}
  </svg></div>;
}

function RankedBars({ rows = [], color = "#6c4bf4" }) {
  if (!rows.length) return <div className="cd-empty">No records for this period.</div>;
  const max = Math.max(...rows.map(row => row.count), 1);
  return <div className="cd-ranked-list">{rows.map((row, index) => <div className="cd-ranked-row" key={`${row.name}-${index}`}>
    <span className="cd-rank">{String(index + 1).padStart(2, "0")}</span>
    <div className="cd-ranked-main"><div><strong title={row.name}>{row.name}</strong><b>{formatNumber(row.count)}</b></div><div className="cd-bar-track"><i style={{ width: `${row.count / max * 100}%`, background: color }}/></div></div>
  </div>)}</div>;
}

export function Overview({ data }) {
  const cards = data.cards || {};
  return <>
    <div className="cd-metrics cd-metrics-three">
      <MetricCard eyebrow="NEW LEADS" value={formatNumber(cards.new_leads)} detail={`From ${formatNumber(cards.total_leads)} enquiries in this period`} accent="violet" icon="↗"/>
      <MetricCard eyebrow="CONVERTED LEADS" value={formatNumber(cards.converted_leads)} detail="Main CRM leads marked converted" accent="mint" icon="✓"/>
      <MetricCard eyebrow="UPSELL CONVERSION" value={`${cards.upsell_conversion_rate || 0}%`} detail={`${formatNumber(cards.upsell_converted)} of ${formatNumber(cards.upsell_total)} active opportunities`} accent="peach" icon="↗"/>
    </div>
    <div className="cd-grid-two">
      <Panel kicker="MOMENTUM" title="Lead volume" hint="By lead creation date"><TrendChart points={data.trend} field="leads" color="#6b4cf2" name="Leads"/></Panel>
      <Panel kicker="OUTCOMES" title="Conversions" hint="Converted leads by creation date"><TrendChart points={data.trend} field="converted" color="#18b994" name="Conversions"/></Panel>
    </div>
    <div className="cd-grid-two">
      <Panel kicker="ACQUISITION" title="Top 7 lead sources" hint="Where enquiries started"><RankedBars rows={data.top_sources}/></Panel>
      <Panel kicker="DEMAND" title="Top 7 courses converted" hint="Main CRM converted leads"><RankedBars rows={data.top_converted_courses} color="#17b996"/></Panel>
    </div>
  </>;
}

function CounselorBars({ rows = [], mode }) {
  if (!rows.length) return <div className="cd-empty">No counselor leads in this period.</div>;
  const max = Math.max(1, ...rows.map(row => mode === "conversion" ? row.converted : row.leads));
  return <div className="cd-counselor-scroll"><div className="cd-counselor-chart" style={{ minWidth: `${Math.max(580, rows.length * 88)}px` }}>
    {rows.map(row => {
      const height = (mode === "conversion" ? row.converted : row.leads) / max * 170;
      const convertedHeight = row.converted / max * 170;
      const remainingHeight = Math.max(0, height - convertedHeight);
      return <div className="cd-counselor-column" key={row.id ?? "unassigned"} title={`${row.name}: ${row.leads} leads, ${row.converted} conversions`}>
        <span className="cd-bar-number">{formatNumber(mode === "conversion" ? row.converted : row.leads)}</span>
        <div className="cd-vertical-track">
          {mode === "both" ? <><i className="cd-vertical-remaining" style={{ height: remainingHeight }}/><i className="cd-vertical-converted" style={{ height: convertedHeight }}/></>
            : <i className={mode === "conversion" ? "cd-vertical-converted" : "cd-vertical-leads"} style={{ height }}/>}</div>
        <span className="cd-counselor-name" title={row.name}>{row.name}</span>
      </div>;
    })}
  </div></div>;
}

const FLOW_X = [16, 272, 528, 784];
const FLOW_WIDTH = 212;
const FLOW_TOP = 66;
const FLOW_ROW = 104;
const FLOW_BATCH = 8;

function FlowCard({ name, count, parentCount, selected, onClick, x, y, root = false }) {
  const percent = parentCount ? Math.round(count / parentCount * 1000) / 10 : 0;
  const content = <><div className="cd-flow-card-top"><strong title={name}>{name}</strong>{onClick && <span className="cd-flow-expand" aria-hidden="true">{selected ? "−" : "+"}</span>}</div><div className="cd-flow-card-stat"><b>{formatNumber(count)}</b><span>{root ? "conversions" : `${percent}% of previous`}</span></div><div className="cd-flow-track"><i style={{ width: `${root ? (count ? 100 : 0) : percent}%` }}/></div></>;
  const style = { left: x, top: y, width: FLOW_WIDTH };
  return onClick ? <button type="button" className={`cd-flow-card ${selected ? "selected" : ""}`} style={style} onClick={onClick} aria-label={`Explore ${name}, ${count} conversions`}>{content}</button>
    : <div className={`cd-flow-card ${root ? "cd-flow-root" : ""}`} style={style}>{content}</div>;
}

function SalesTree({ rows = [], range }) {
  const [counselor, setCounselor] = useState(null);
  const [course, setCourse] = useState(null);
  const [courses, setCourses] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [visible, setVisible] = useState([FLOW_BATCH, FLOW_BATCH, FLOW_BATCH]);
  const requestId = useRef(0);
  useEffect(() => {
    requestId.current += 1; setCounselor(null); setCourse(null); setCourses([]); setSources([]); setLoading(""); setError(""); setVisible([FLOW_BATCH, FLOW_BATCH, FLOW_BATCH]);
    return () => { requestId.current += 1; };
  }, [range.startDate, range.endDate]);
  if (!rows.length) return <div className="cd-empty">No counselor conversions in this date range.</div>;
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  const shownCounselors = rows.slice(0, visible[0]);
  const shownCourses = courses.slice(0, visible[1]);
  const shownSources = sources.slice(0, visible[2]);
  const rootY = FLOW_TOP + Math.max(0, (shownCounselors.length - 1) * FLOW_ROW / 2);
  const activeCounselorIndex = shownCounselors.findIndex(row => row.id === counselor?.id);
  const counselorY = FLOW_TOP + activeCounselorIndex * FLOW_ROW;
  const activeCourseIndex = shownCourses.findIndex(row => row.name === course?.name);
  const courseY = FLOW_TOP + activeCourseIndex * FLOW_ROW;
  const height = FLOW_TOP + Math.max(shownCounselors.length, shownCourses.length, shownSources.length, 1) * FLOW_ROW + 22;
  const link = (x1, y1, x2, y2, key, active) => <g key={key}><path d={`M${x1} ${y1} C${x1 + 42} ${y1}, ${x2 - 42} ${y2}, ${x2} ${y2}`} fill="none" stroke={active ? "#138df4" : "#bed8f4"} strokeWidth={active ? 2.5 : 1.5}/><circle cx={x2} cy={y2} r={active ? 5 : 3.5} fill={active ? "#138df4" : "#78b4ea"}/></g>;
  const openCounselor = async row => {
    if (row.id === counselor?.id) { requestId.current += 1; setCounselor(null); setCourse(null); setCourses([]); setSources([]); setLoading(""); setError(""); return; }
    const current = ++requestId.current;
    setCounselor(row); setCourse(null); setCourses([]); setSources([]); setVisible([visible[0], FLOW_BATCH, FLOW_BATCH]); setLoading("courses"); setError("");
    try { const result = await getCompanySalesCourses(row.id, range); if (current === requestId.current) setCourses(result); }
    catch (err) { if (current === requestId.current) setError(err.message); }
    finally { if (current === requestId.current) setLoading(""); }
  };
  const openCourse = async row => {
    if (row.name === course?.name) { requestId.current += 1; setCourse(null); setSources([]); setLoading(""); setError(""); return; }
    const current = ++requestId.current;
    setCourse(row); setSources([]); setVisible([visible[0], visible[1], FLOW_BATCH]); setLoading("sources"); setError("");
    try { const result = await getCompanySalesSources(counselor.id, row.name, range); if (current === requestId.current) setSources(result); }
    catch (err) { if (current === requestId.current) setError(err.message); }
    finally { if (current === requestId.current) setLoading(""); }
  };
  return <div className="cd-flow-shell"><div className="cd-flow-scroll"><div className="cd-flow-guide"><span>01 / TOTAL</span><span>02 / COUNSELOR</span><span>03 / COURSE</span><span>04 / LEAD SOURCE</span></div>
    <div className="cd-flow-stage" style={{ height }}>
      <svg className="cd-flow-lines" viewBox={`0 0 1012 ${height}`} aria-hidden="true">
        {shownCounselors.map((row, index) => link(FLOW_X[0] + FLOW_WIDTH, rootY + 43, FLOW_X[1], FLOW_TOP + index * FLOW_ROW + 43, `a-${row.id}`, row.id === counselor?.id))}
        {activeCounselorIndex >= 0 && shownCourses.map((row, index) => link(FLOW_X[1] + FLOW_WIDTH, counselorY + 43, FLOW_X[2], FLOW_TOP + index * FLOW_ROW + 43, `b-${row.name}`, row.name === course?.name))}
        {activeCourseIndex >= 0 && shownSources.map((row, index) => link(FLOW_X[2] + FLOW_WIDTH, courseY + 43, FLOW_X[3], FLOW_TOP + index * FLOW_ROW + 43, `c-${row.name}`, true))}
      </svg>
      <FlowCard root name="All conversions" count={total} parentCount={total} x={FLOW_X[0]} y={rootY}/>
      {shownCounselors.map((row, index) => <FlowCard key={row.id ?? "unassigned"} {...row} parentCount={total} selected={row.id === counselor?.id} onClick={() => openCounselor(row)} x={FLOW_X[1]} y={FLOW_TOP + index * FLOW_ROW}/>)}
      {shownCourses.map((row, index) => <FlowCard key={row.name} {...row} parentCount={counselor?.count} selected={row.name === course?.name} onClick={() => openCourse(row)} x={FLOW_X[2]} y={FLOW_TOP + index * FLOW_ROW}/>)}
      {shownSources.map((row, index) => <FlowCard key={row.name} {...row} parentCount={course?.count} x={FLOW_X[3]} y={FLOW_TOP + index * FLOW_ROW}/>)}
      {loading && <div className="cd-flow-wait" style={{ left: FLOW_X[loading === "courses" ? 2 : 3], top: FLOW_TOP }}>Loading {loading}…</div>}
      {counselor && !loading && !courses.length && !error && <div className="cd-flow-wait" style={{ left: FLOW_X[2], top: FLOW_TOP }}>No courses found</div>}
      {course && !loading && !sources.length && !error && <div className="cd-flow-wait" style={{ left: FLOW_X[3], top: FLOW_TOP }}>No sources found</div>}
    </div></div>
    {error && <p className="cd-flow-error">Could not load branch: {error}</p>}
    <div className="cd-flow-foot">{[[rows, 0, "counselors"], [courses, 1, "courses"], [sources, 2, "sources"]].map(([items, index, label]) => items.length > visible[index] && <button type="button" key={label} onClick={() => setVisible(current => current.map((count, slot) => slot === index ? count + FLOW_BATCH : count))}>Show more {label} <span>({items.length - visible[index]} remaining)</span></button>)}</div>
  </div>;
}

export function Sales({ data, range = {} }) {
  const [mode, setMode] = useState("both"); const cards = data.cards || {};
  return <>
    <div className="cd-metrics cd-metrics-four">
      <MetricCard eyebrow="TOTAL CONVERSIONS" value={formatNumber(cards.converted)} detail="Main CRM converted leads" icon="✓" accent="violet"/>
      <MetricCard eyebrow="TOTAL LEADS" value={formatNumber(cards.leads)} detail="Enquiries in this period" icon="↗" accent="mint"/>
      <MetricCard eyebrow="CONVERSION RATE" value={`${cards.conversion_rate || 0}%`} detail="Converted ÷ total leads" icon="%" accent="peach"/>
      <MetricCard eyebrow="UNASSIGNED" value={formatNumber(cards.unassigned)} detail="Leads awaiting a counselor" icon="⌁" accent="sky"/>
    </div>
    <Panel kicker="TEAM PERFORMANCE" title="Counselor comparison" hint="Conversions are part of total leads">
      <div className="cd-toggle" role="group" aria-label="Counselor chart metric">{[["conversion", "Conversions"], ["leads", "Leads"], ["both", "Both"]].map(([key, label]) => <button key={key} type="button" className={mode === key ? "active" : ""} onClick={() => setMode(key)}>{label}</button>)}</div>
      <CounselorBars rows={data.counselors} mode={mode}/>
      {mode === "both" && <div className="cd-legend"><span><i className="cd-legend-converted"/>Converted</span><span><i className="cd-legend-remaining"/>Other leads</span></div>}
    </Panel>
    <Panel kicker="CONVERSION PATH" title="Where conversions come from" hint="Select a counselor, then a course">
      <SalesTree rows={data.decomposition} range={range}/>
    </Panel>
  </>;
}

function ResultStack({ outcome, title }) {
  const total = outcome.learners || 0;
  const segments = [["pass", "Passed", "#16b88e"], ["fail", "Failed", "#f37676"], ["pending", "Pending / other", "#b5b6c7"]];
  return <div className="cd-result-row"><div className="cd-result-row-head"><strong>{title}</strong><span>{formatNumber(total)} learners · {outcome.pass_rate || 0}% pass rate</span></div>
    <div className="cd-result-track">{segments.map(([key, label, color]) => outcome[key] > 0 && <i key={key} style={{ width: `${outcome[key] / total * 100}%`, background: color }} title={`${label}: ${outcome[key]}`}/>)}</div>
    <div className="cd-result-detail">{segments.map(([key, label, color]) => <span key={key}><i style={{ background: color }}/>{label} <b>{formatNumber(outcome[key])}</b></span>)}</div>
  </div>;
}

export function Dinesh({ data }) {
  const cards = data.cards || {}; const igc = data.igc || {};
  const total = igc.learners || 0;
  const pass = total ? (igc.pass || 0) / total * 100 : 0;
  const fail = total ? (igc.fail || 0) / total * 100 : 0;
  return <>
    <div className="cd-metrics cd-metrics-four">
      <MetricCard eyebrow="LEARNERS WITH RESULTS" value={formatNumber(cards.learners)} detail="Unique learner numbers" icon="◎" accent="violet"/>
      <MetricCard eyebrow="RESULT RECORDS" value={formatNumber(cards.result_rows)} detail="IGC and IDIP uploads" icon="▤" accent="sky"/>
      <MetricCard eyebrow="IGC PASS RATE" value={`${cards.igc_pass_rate || 0}%`} detail="Pass ÷ decided IGC results" icon="✓" accent="mint"/>
      <MetricCard eyebrow="ALL IDIP UNITS PASSED" value={formatNumber(cards.idip_three_units_passed)} detail="ID1, ID2 and ID3" icon="◆" accent="peach"/>
    </div>
    <div className="cd-grid-two cd-results-grid">
      <Panel kicker="IGC OUTCOMES" title="Latest IGC result" hint="One latest result per learner">
        <div className="cd-donut-layout"><div className="cd-donut" style={{ background: `conic-gradient(#16b88e 0 ${pass}%, #f37676 ${pass}% ${pass + fail}%, #b5b6c7 ${pass + fail}% 100%)` }}><div><strong>{formatNumber(total)}</strong><span>learners</span></div></div>
          <div className="cd-donut-legend"><div><i className="pass"/><span>Passed</span><strong>{formatNumber(igc.pass)}</strong></div><div><i className="fail"/><span>Failed</span><strong>{formatNumber(igc.fail)}</strong></div><div><i className="pending"/><span>Pending / other</span><strong>{formatNumber(igc.pending)}</strong></div></div></div>
      </Panel>
      <Panel kicker="IDIP PROGRESSION" title="Units passed" hint="Unique learners at each milestone">
        <div className="cd-progression">{[["one_unit", "At least 1 unit"], ["two_units", "At least 2 units"], ["three_units", "All 3 units"]].map(([key, label], index) => <div key={key}><span className="cd-progression-mark">0{index + 1}</span><div><strong>{formatNumber(data.idip_progression?.[key])}</strong><span>{label}</span></div></div>)}</div>
      </Panel>
    </div>
    <Panel kicker="IDIP UNIT RESULTS" title="ID1 · ID2 · ID3" hint="Latest result for each learner and unit">
      {(data.idip_units || []).map(unit => <ResultStack key={unit.code} title={unit.code} outcome={unit}/>)}
      {!data.idip_units?.length && <div className="cd-empty">No IDIP unit results in this period.</div>}
    </Panel>
    <p className="cd-method-note">Pass rates use the latest result per learner and course. Pending and other results are excluded from the pass rate denominator. The date filter uses the uploaded result event date.</p>
  </>;
}

export default function CompanyDashboardPage({ section = "overview" }) {
  const [range, setRange] = useState(initialRange); const [data, setData] = useState(null); const [error, setError] = useState("");
  const changeRange = next => { try { window.sessionStorage.setItem("company_dashboard_range", JSON.stringify(next)); } catch {} setRange(next); };
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    getCompanyDashboard(section, range).then(result => { if (active) setData(result); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [section, range.startDate, range.endDate]);
  const headings = { overview: ["Company overview", "A clear view of demand, conversions and growth."], sales: ["Sales performance", "Follow team results from first enquiry to conversion."], dinesh: ["Dinesh · Results intelligence", "IGC and IDIP outcomes from the Upsell result uploads."] };
  return <div className="page cd-page">
    <header className="cd-hero"><div className="cd-hero-glow"/><div className="cd-hero-content"><div className="cd-eyebrow"><span/> GWG INTELLIGENCE / {section.toUpperCase()}</div><h1>{headings[section][0]}</h1><p>{headings[section][1]}</p></div><div className="cd-hero-mark" aria-hidden="true">GWG<span>↗</span></div></header>
    <div className="cd-toolbar"><nav className="cd-tabs" aria-label="Dashboard pages"><NavLink end to="/dashboard">Overview</NavLink><NavLink to="/dashboard/sales">Sales</NavLink><NavLink to="/dashboard/dinesh">Dinesh</NavLink><NavLink to="/dashboard/counselors">Counselors</NavLink></nav><DateRangePicker value={range} onChange={changeRange}/></div>
    {error && <div className="cd-alert">Could not load dashboard: {error}</div>}
    {!data && !error && <div className="cd-loading"><span/>Preparing dashboard…</div>}
    {data && (section === "sales" ? <Sales data={data} range={range}/> : section === "dinesh" ? <Dinesh data={data}/> : <Overview data={data}/>)}
  </div>;
}
