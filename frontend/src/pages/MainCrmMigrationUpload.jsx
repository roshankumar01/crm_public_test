import { useEffect, useState } from "react";
import { downloadMigrationSkipped, getMainCrmMigrationProgress, previewMainCrmMigration, uploadMainCrmMigration } from "../api";

const CATEGORIES = [
  ["INFO_EMAIL_LEADS", "Info email leads"],
  ["LIVE_ONLINE_LEADS", "Live online leads"],
  ["DIRECT_CALLS", "Direct calls"],
];
const COLUMNS = "Name | Sales owner | Owner Email | Mobile | Course Name | Age | status of lead | Regions | Last assigned at | First assigned at | Created at | Updated at | Created by | Updated By | Other Phone numbers | Source | Recent note | Email | Email IDs | Message";
const JOB_KEY = "main_crm_migration_job";

export default function MainCrmMigrationUpload({ uploads, reload }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [mode, setMode] = useState("CREATE");
  const [target, setTarget] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobNumber, setJobNumber] = useState(() => sessionStorage.getItem(JOB_KEY) || "");
  const [progress, setProgress] = useState(null);
  const [message, setMessage] = useState("");
  const migrationUploads = uploads.filter(upload => upload.source_category === "MIGRATION");

  useEffect(() => {
    if (!jobNumber) return;
    let cancelled = false;
    let timer;
    async function poll() {
      try {
        const result = await getMainCrmMigrationProgress(jobNumber);
        if (cancelled) return;
        setProgress(result);
        if (result.status === "COMPLETED" || result.status === "FAILED") {
          sessionStorage.removeItem(JOB_KEY);
          setJobNumber("");
          setMessage(result.status === "FAILED"
            ? `Migration ${jobNumber} failed: ${result.error_message || "Unknown error"}`
            : `Migration ${jobNumber} complete: ${result.rows_imported} rows imported, ${result.rows_skipped} skipped.`);
          reload();
        } else {
          timer = setTimeout(poll, 1500);
        }
      } catch (error) {
        if (cancelled) return;
        setMessage(`Could not check migration progress: ${error.message}. Retrying...`);
        timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [jobNumber, reload]);

  async function chooseFile(chosen) {
    setFile(chosen); setPreview(null); setMapping({}); setMessage("");
    if (!chosen) return;
    try {
      setPreviewing(true);
      const result = await previewMainCrmMigration(chosen);
      setPreview(result);
      setMapping(Object.fromEntries(result.sources.map(item => [item.source, item.suggested_category])));
    } catch (error) { setMessage(`Preview unavailable: ${error.message}. You can still import this file.`); }
    finally { setPreviewing(false); }
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return setMessage("Choose an old CRM Excel or CSV file first.");
    if (mode === "UPDATE" && !target) return setMessage("Choose a migration upload to replace.");
    try {
      setUploading(true); setMessage("");
      const result = await uploadMainCrmMigration(file, mapping, mode, target);
      sessionStorage.setItem(JOB_KEY, result.unique_number);
      setProgress({ ...result, processed: 0, rows_imported: 0, rows_skipped: 0 });
      setJobNumber(result.unique_number);
      setMessage(`Migration ${result.unique_number} started. You can leave this page and return to check progress.`);
      await reload();
    } catch (error) { setMessage(error.message); }
    finally { setUploading(false); }
  }

  return <section className="upload-workspace-section">
    <div className="section-heading"><div><div className="eyebrow">OLD CRM MIGRATION</div><h2>Migrate old CRM leads</h2><p className="small-muted">Upload one Excel file containing all three lead sources. Review where each Source value will go before importing.</p></div></div>
    {message && <div className="upload-message page-message">{message}</div>}
    {progress?.status === "PROCESSING" && <div className="migration-progress" role="status" aria-live="polite"><div><strong>Importing {progress.processed?.toLocaleString() || 0} of {progress.rows_total?.toLocaleString() || 0} rows</strong><span>{progress.rows_total ? Math.round((progress.processed || 0) / progress.rows_total * 100) : 0}%</span></div><progress value={progress.processed || 0} max={progress.rows_total || 1} /><p className="small-muted">{progress.rows_imported?.toLocaleString() || 0} imported · {progress.rows_skipped?.toLocaleString() || 0} skipped</p></div>}
    {progress?.status === "COMPLETED" && progress.rows_skipped > 0 && <div className="migration-progress"><strong>{progress.rows_skipped.toLocaleString()} rows skipped</strong><button className="secondary-button" onClick={() => downloadMigrationSkipped(progress.unique_number)}>Download skipped rows</button></div>}
    <div className="upload-layout">
      <form className="upload-card" onSubmit={submit}>
        <h3>Migration upload</h3>
        <label>Action</label>
        <div className="segmented-control"><button type="button" className={mode === "CREATE" ? "segment active" : "segment"} onClick={() => setMode("CREATE")}>New upload</button><button type="button" className={mode === "UPDATE" ? "segment active" : "segment"} onClick={() => setMode("UPDATE")}>Replace migration</button></div>
        {mode === "UPDATE" && <><label>Migration to replace</label><select value={target} onChange={event => setTarget(event.target.value)}><option value="">Select migration number</option>{migrationUploads.map(upload => <option key={upload.id} value={upload.unique_number}>{upload.unique_number} — {upload.filename}</option>)}</select></>}
        <label>Old CRM Excel or CSV file</label>
        <input type="file" accept=".xlsx,.csv" onChange={event => chooseFile(event.target.files[0] || null)} />
        {previewing && <p className="small-muted">Checking source values...</p>}
        {preview && <><p className="small-muted">{preview.rows_total} rows found. Check the source mapping:</p>{preview.sources.map(item => <div className="format-item" key={item.source}><label>{item.source || "(blank Source)"} · {item.count} rows</label><select value={mapping[item.source]} onChange={event => setMapping(current => ({ ...current, [item.source]: event.target.value }))}>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>)}</>}
        <button className="primary-button" disabled={uploading || !!jobNumber || !file}>{uploading ? "Starting import..." : jobNumber ? "Import in progress" : mode === "UPDATE" ? "Replace migration data" : "Import old CRM data"}</button>
      </form>
      <div className="format-card"><div className="eyebrow">EXPECTED FORMAT</div><h3>Old CRM export columns</h3><p>{COLUMNS}</p><div className="format-item"><strong>How rows are matched</strong><p>Email IDs is used as the primary email and Email is the fallback; phone is read from Mobile or Other Phone numbers. A row needs at least one of these. Matching leads receive a migration activity while their current CRM edits are preserved.</p></div><div className="format-item"><strong>Legacy details</strong><p>Recent note and Message appear in lead history. The original row, including assignment and audit dates, remains available there.</p></div></div>
    </div>
  </section>;
}
