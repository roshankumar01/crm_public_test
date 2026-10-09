import { useEffect, useState } from "react";
import SettingsTabs from "../components/SettingsTabs.jsx";
import { getRecommendationRules, updateRecommendationRules } from "../api";

export default function RecommendationRulesSettingsPage() {
  const [rules, setRules] = useState(null);
  const [days, setDays] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { getRecommendationRules().then(data => { setRules(data); setDays(data.cooling_days); }).catch(err => setError(err.message)); }, []);
  async function save(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try { const next = await updateRecommendationRules(Number(days)); setRules(next); setMessage("Cooling period updated. Upsell opportunities will refresh."); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM ADMIN</div><h1>Settings</h1><p className="page-description">Control when learners become eligible for the next course.</p></div></div>
    <SettingsTabs />
    {error && <div className="form-error page-message">{error}</div>}{message && <div className="upload-message page-message">{message}</div>}
    {!rules ? <div className="loading-state">Loading recommendation rules...</div> : <>
      <section className="feature-card"><div className="eyebrow">COOLING PERIOD</div><h2>Stage 1 to Stage 2</h2><p>Start counting from each Stage 1 course enrolment date.</p><form className="course-mapping-create" onSubmit={save}><label htmlFor="cooling-days">Cooling days</label><div><input id="cooling-days" type="number" min="0" max="3650" value={days} onChange={event => setDays(event.target.value)} /><button className="primary-button" disabled={busy || days === "" || Number(days) === rules.cooling_days}>Save days</button></div></form></section>
      <section className="feature-card"><div className="eyebrow">CURRENT PATHWAY</div><h2>Recommendation stages</h2><p><strong>Stage 1:</strong> {rules.stage_one.join(", ")}</p><p><strong>Stage 2:</strong> {rules.stage_two.join(", ")}</p><p><strong>Stage 3 after an IGC pass:</strong> {rules.stage_three.join(", ")}</p><p><strong>IDIP units:</strong> {rules.idip_rule}</p><p>Courses already enrolled are excluded. Edit course placement in Course mapping.</p></section>
    </>}
  </div>;
}
