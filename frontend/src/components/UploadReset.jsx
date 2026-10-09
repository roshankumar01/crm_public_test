import { useState } from "react";
import { getUploadResetOptions, resetSelectedUploads, resetAllCrmData } from "../api";

const TYPE_LABELS = {
  IGC: "Upsell · IGC",
  IDP: "Upsell · IDP",
  MARKETING_CAMPAIGN: "Upsell · Marketing campaign",
  LEARNERS_CRM: "Learners CRM",
  MAIN_CRM_INFO_EMAIL_LEADS: "Main CRM · Info email leads",
  MAIN_CRM_LIVE_ONLINE_LEADS: "Main CRM · Live online leads",
  MAIN_CRM_DIRECT_CALLS: "Main CRM · Direct calls",
  MAIN_CRM_CAMPAIGN_REPLIES: "Main CRM · Campaign replies",
  MAIN_CRM_CAMPAIGN_DATA: "Main CRM · Campaign data",
};

export default function UploadReset({ onReset }) {
  const [mode, setMode] = useState("all");
  const phrase = mode === "all" ? "RESET ALL CRM DATA" : "DELETE SELECTED UPLOADS";
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState([]);
  const [selected, setSelected] = useState([]);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function showOptions() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setOptions(await getUploadResetOptions());
      setSelected([]);
      setMode("all");
      setConfirmation("");
      setOpen(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (busy) return;
    setOpen(false);
    setSelected([]);
    setConfirmation("");
    setError("");
  }

  function toggle(id) {
    setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
    setConfirmation("");
  }

  async function removeSelected() {
    if ((mode === "selected" && !selected.length) || confirmation !== phrase) return;
    setBusy(true);
    setError("");
    try {
      const result = mode === "all" ? await resetAllCrmData() : await resetSelectedUploads(selected);
      setMessage(mode === "all" ? "All CRM data cleared. Accounts, course mappings and settings were preserved." : `${result.uploads_deleted} upload file${result.uploads_deleted === 1 ? "" : "s"} and linked import rows deleted.`);
      setOpen(false);
      setSelected([]);
      setConfirmation("");
      await onReset?.();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="upload-reset-section">
    <div><div className="eyebrow">DATA RESET</div><h2>Reset CRM data</h2><p>Clear all CRM data, including manual history, or remove selected uploads. Accounts, course mappings and settings are preserved.</p></div>
    <button type="button" className="upload-reset-open" onClick={showOptions} disabled={busy}>{busy && !open ? "Loading..." : "Data reset"}</button>
    {message && <div className="upload-message">{message}</div>}
    {!open && error && <div className="upload-message">{error}</div>}
    {open && <div className="upload-reset-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
      <div className="upload-reset-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-reset-title">
        <h2 id="upload-reset-title">Reset CRM data</h2>
        <label>Reset scope<select className="search-input" aria-label="Reset scope" value={mode} disabled={busy} onChange={event=>{setMode(event.target.value);setConfirmation("");}}><option value="all">Total data reset · all CRMs</option><option value="selected">Selected upload files only</option></select></label>
        <p>{mode === "all" ? "Permanently deletes all leads, contacts, enrolments, results, conversions, notes, edit history, verifications and uploads across every CRM. Accounts and settings are kept." : "Deletes selected imported rows. Shared people and manual history are retained; this is not a total reset."}</p>
        {mode === "selected" && <>
        {options.length ? <>
          <label className="upload-reset-choice"><input type="checkbox" checked={selected.length === options.length} onChange={event => { setSelected(event.target.checked ? options.map(item => item.id) : []); setConfirmation(""); }} /><strong>Select all upload files ({options.length})</strong></label>
          <div className="upload-reset-options">{options.map(item => <label className="upload-reset-choice" key={item.id}>
            <input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
            <span><strong>{item.filename}</strong><small>{TYPE_LABELS[item.import_type] || item.import_type} · {item.unique_number || `Upload #${item.id}`} · {item.rows_imported} imported · {new Date(item.uploaded_at).toLocaleString()}</small></span>
          </label>)}</div>
        </> : <p>No uploaded files are available to reset. Use Total data reset to clear remaining records.</p>}
        </>}
        <p>Type <code>{phrase}</code> to confirm.</p>
        <input className="upload-reset-confirmation" value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} placeholder={phrase} aria-label={`Type ${phrase} to confirm`} />
        {error && <div className="upload-message">{error}</div>}
        <div className="upload-reset-actions"><button type="button" onClick={close} disabled={busy}>Cancel</button><button type="button" className="upload-reset-delete" disabled={busy || (mode === "selected" && !selected.length) || confirmation !== phrase} onClick={removeSelected}>{busy ? "Deleting..." : mode === "all" ? "Reset all CRM data" : `Delete ${selected.length} selected`}</button></div>
      </div>
    </div>}
  </section>;
}
