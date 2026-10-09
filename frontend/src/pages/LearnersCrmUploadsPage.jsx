import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLearnersCrmUploads, startUploadJob } from "../api";
import UploadProgress from "../components/UploadProgress.jsx";
import useUploadJob from "../hooks/useUploadJob.js";

const MIGRATED_COLUMNS = ["enrolment_id", "learner_name", "email_id", "phone_number (optional)", "course_name", "enrolment_date", "start_date", "completion_date", "completion_status"];
const DAILY_COLUMNS = ["enrolment_id", "learner_name", "email", "phone", "course", "created_date", "enrolment_date", "start_date", "counselor_name"];

export default function LearnersCrmUploadsPage({ refreshKey = 0 }) {
  const [uploads, setUploads] = useState([]);
  const [mode, setMode] = useState("CREATE");
  const [target, setTarget] = useState("");
  const [migratedFile, setMigratedFile] = useState(null);
  const [dailyFile, setDailyFile] = useState(null);
  const [message, setMessage] = useState("");
  const [dailyMessage, setDailyMessage] = useState("");
  const [unmappedCourses, setUnmappedCourses] = useState([]);
  const [starting, setStarting] = useState(false);
  async function load() {
    try { setUploads(await getLearnersCrmUploads()); }
    catch (error) { setMessage(error.message); }
  }
  const migratedJob = useUploadJob("learners_crm_upload_job", job => {
    if (job.status === "FAILED") setMessage(`Migration upload failed: ${job.error_message}`);
    else {
      setMessage(`Migration upload complete: ${job.rows_imported} enrolments imported; ${job.rows_skipped} skipped.`);
      setUnmappedCourses(job.result?.unmapped_courses || []);
    }
    load();
  }, error => setMessage(`Could not check migration progress: ${error.message}`));
  const dailyJob = useUploadJob("learners_daily_upload_job", job => {
    if (job.status === "FAILED") setDailyMessage(`Daily upload failed: ${job.error_message}`);
    else setDailyMessage(`Daily upload complete: ${job.rows_imported} accepted, ${job.result?.rows_verified || 0} verified, ${job.result?.rows_pending || 0} awaiting review, ${job.rows_skipped} skipped.`);
    load();
  }, error => setDailyMessage(`Could not check daily progress: ${error.message}`));
  useEffect(() => { load(); }, [refreshKey]);

  async function submit(event, kind) {
    event.preventDefault();
    const file = kind === "LEARNERS_DAILY" ? dailyFile : migratedFile;
    if (!file) return;
    if (kind === "LEARNERS_CRM" && mode === "UPDATE" && !target) return setMessage("Choose a migrated upload to replace.");
    try {
      setStarting(true);
      const result = await startUploadJob({ kind, file,
        uploadMode: kind === "LEARNERS_DAILY" ? "CREATE" : mode,
        uniqueNumber: kind === "LEARNERS_DAILY" ? "" : target });
      if (kind === "LEARNERS_DAILY") {
        dailyJob.begin(result);
        setDailyMessage("Daily import started. Rows needing review will appear on the Learners CRM verification page.");
        setDailyFile(null);
      } else {
        migratedJob.begin(result);
        setMessage("Migration import started.");
        setUnmappedCourses([]);
        setMigratedFile(null);
      }
      event.target.reset();
    } catch (error) {
      if (kind === "LEARNERS_DAILY") setDailyMessage(error.message);
      else setMessage(error.message);
    } finally { setStarting(false); }
  }

  return <section className="upload-workspace-section">
    {message && <div className="upload-message page-message">{message}</div>}
    <UploadProgress progress={migratedJob.progress} jobId={migratedJob.jobId} />
    {dailyMessage && <div className="upload-message page-message">{dailyMessage}</div>}
    <UploadProgress progress={dailyJob.progress} jobId={dailyJob.jobId} />
    {unmappedCourses.length > 0 && <div className="format-card page-message"><strong>{unmappedCourses.length} course names are unmapped.</strong><p>Assign them in <Link to="/crm/settings/course-mapping">Settings / Course mapping</Link>.</p><details><summary>Show course names</summary><ul>{unmappedCourses.map(name => <li key={name}>{name}</li>)}</ul></details></div>}
    <div className="upload-layout">
      <form className="upload-card" onSubmit={event => submit(event, "LEARNERS_CRM")}>
        <div className="upload-icon">↑</div><h2>Learners migrated</h2>
        <label>Action</label><div className="segmented-control"><button type="button" className={mode === "CREATE" ? "segment active" : "segment"} onClick={() => setMode("CREATE")}>New upload</button><button type="button" className={mode === "UPDATE" ? "segment active" : "segment"} onClick={() => setMode("UPDATE")}>Update upload</button></div>
        {mode === "UPDATE" && <><label>Upload to replace</label><select value={target} onChange={event => setTarget(event.target.value)} required><option value="">Select upload number</option>{uploads.filter(item => item.import_type === "LEARNERS_CRM").map(item => <option key={item.id} value={item.unique_number}>{item.unique_number} — {item.filename}</option>)}</select></>}
        <label>Excel or CSV file</label><input type="file" accept=".xlsx,.csv" onChange={event => setMigratedFile(event.target.files[0] || null)} />
        <button className="primary-button" disabled={starting || !!migratedJob.jobId || !migratedFile}>{migratedJob.jobId ? "Import in progress" : mode === "UPDATE" ? "Replace migrated upload" : "Import migrated learners"}</button>
      </form>
      <div className="format-card"><div className="eyebrow">MIGRATED COLUMNS</div><h3>Existing learner format</h3>{MIGRATED_COLUMNS.map(column => <div className="format-item" key={column}><strong>{column}</strong></div>)}<p className="small-muted">Migrated learners stay eligible for Upsell. Their Main CRM match appears as a green or red tick.</p></div>
    </div>
    <div className="upload-layout">
      <form className="upload-card" onSubmit={event => submit(event, "LEARNERS_DAILY")}>
        <div className="upload-icon">+</div><h2>Daily learners</h2>
        <p className="small-muted">A Main CRM match and a recognized counselor verify a row automatically. Otherwise it waits for admin review.</p>
        <label>Excel or CSV file</label><input type="file" accept=".xlsx,.csv" onChange={event => setDailyFile(event.target.files[0] || null)} />
        <button className="primary-button" disabled={starting || !!dailyJob.jobId || !dailyFile}>{dailyJob.jobId ? "Import in progress" : "Import daily learners"}</button>
        <Link className="text-link" to="/learners-crm/verification">Review pending learners</Link>
      </form>
      <div className="format-card"><div className="eyebrow">DAILY COLUMNS</div><h3>Daily upload format</h3>{DAILY_COLUMNS.map(column => <div className="format-item" key={column}><strong>{column}</strong></div>)}<p className="small-muted">Each row needs an enrolment ID, course, enrolment date, and at least one contact method.</p></div>
    </div>
    <div className="section-heading"><div><div className="eyebrow">HISTORY</div><h2>Recent learner uploads</h2></div></div>
    <div className="table-card"><table><thead><tr><th>Upload number</th><th>Type</th><th>File</th><th>Status</th><th>Rows</th><th>Imported</th><th>Skipped</th><th>Uploaded</th></tr></thead><tbody>{uploads.map(item => <tr key={item.id}><td><strong>{item.unique_number}</strong></td><td>{item.import_type === "LEARNERS_DAILY" ? "Daily" : "Migrated"}</td><td>{item.filename}</td><td><span className={item.status === "COMPLETED" ? "status-pill pass" : item.status === "FAILED" ? "status-pill fail" : "status-pill"}>{item.status}</span></td><td>{item.rows_total}</td><td>{item.rows_imported}</td><td>{item.rows_skipped}</td><td>{new Date(item.uploaded_at).toLocaleString()}</td></tr>)}</tbody></table>{!uploads.length && <div className="table-message">No learner uploads yet.</div>}</div>
  </section>;
}
