import { useEffect, useState } from "react";
import { getImportTypes, getUploads, startUploadJob } from "../api";
import UploadProgress from "../components/UploadProgress.jsx";
import useUploadJob from "../hooks/useUploadJob.js";

export default function UploadsPage({ refreshKey = 0 }) {
  const [importTypes, setImportTypes] = useState([]);
  const [importType, setImportType] = useState("");
  const [file, setFile] = useState(null);
  const [campaignFile, setCampaignFile] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [campaignUploading, setCampaignUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [campaignMessage, setCampaignMessage] = useState("");
  const courseJob = useUploadJob("upsell_course_upload_job", job => {
    setMessage(job.status === "FAILED" ? `Course upload failed: ${job.error_message}` :
      `Imported ${job.rows_imported} course records. ${job.rows_skipped} skipped.`);
    loadUploads();
  }, error => setMessage(`Could not check course upload: ${error.message}. Retrying...`));
  const campaignJob = useUploadJob("upsell_campaign_upload_job", job => {
    const result = job.result || {};
    setCampaignMessage(job.status === "FAILED" ? `Campaign upload failed: ${job.error_message}` :
      `Imported ${job.rows_imported} campaign rows. ${result.learners_created || 0} learners created, ${result.duplicates_skipped || 0} duplicates skipped.`);
    loadUploads();
  }, error => setCampaignMessage(`Could not check campaign upload: ${error.message}. Retrying...`));

  async function loadUploads() {
    setUploads(await getUploads());
  }

  useEffect(() => {
    Promise.all([getImportTypes(), getUploads()]).then(([types, history]) => {
      setImportTypes(types);
      setUploads(history);
      if (types.length) setImportType(types[0].import_type);
    }).catch(e => setMessage(e.message)).finally(() => setLoading(false));
  }, [refreshKey]);

  async function handleUpload(event) {
    event.preventDefault();
    if (!importType || !file) {
      setMessage("Choose an import type and Excel/CSV file.");
      return;
    }
    try {
      setUploading(true);
      setMessage("");
      const result = await startUploadJob({ kind: "COURSE", file, importType });
      courseJob.begin(result);
      setMessage("Course import started. You can leave this page and return to check progress.");
      setFile(null);
      event.target.reset();
      await loadUploads();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleCampaignUpload(event) {
    event.preventDefault();
    if (!campaignFile) {
      setCampaignMessage("Choose a campaign Excel/CSV file.");
      return;
    }
    try {
      setCampaignUploading(true);
      setCampaignMessage("");
      const result = await startUploadJob({ kind: "CAMPAIGN", file: campaignFile });
      campaignJob.begin(result);
      setCampaignMessage("Campaign import started. You can leave this page and return to check progress.");
      setCampaignFile(null);
      event.target.reset();
      await loadUploads();
    } catch (e) {
      setCampaignMessage(e.message);
    } finally {
      setCampaignUploading(false);
    }
  }

  if (loading) return <div>Loading upload system...</div>;
  const selectedImporter = importTypes.find(item => item.import_type === importType);
  const displayColumn = column => `${column.name}${column.required ? " *" : ""}`;

  return <section className="upload-workspace-section">

    <div className="upload-layout">
      <form className="upload-card" onSubmit={handleUpload}>
        <div className="upload-icon">↑</div><h2>Upload course data</h2><p>Choose the course importer and upload its Excel or CSV file. These rows create learning-history records.</p>
        <label>Import type</label><select value={importType} onChange={e => setImportType(e.target.value)}>{importTypes.map(t => <option key={t.import_type} value={t.import_type}>{t.display_name}</option>)}</select>
        {selectedImporter && <div className="format-item"><strong>This file will receive these columns</strong><p>{selectedImporter.columns.map(displayColumn).join(" | ")}</p><p className="small-muted">* Mandatory column</p></div>}
        <label>File</label><input type="file" accept=".xlsx,.csv" onChange={e => setFile(e.target.files[0] || null)} />
        <button type="submit" className="primary-button" disabled={uploading || !!courseJob.jobId || !file}>{uploading ? "Starting import..." : courseJob.jobId ? "Import in progress" : "Upload course file"}</button>
        {message && <div className="upload-message">{message}</div>}
        <UploadProgress progress={courseJob.progress} jobId={courseJob.jobId} />
      </form>
      <div className="format-card"><div className="eyebrow">EXPECTED FORMAT</div><h3>{selectedImporter?.display_name || "Course importer"}</h3><p>{selectedImporter?.description}</p><div className="format-item"><strong>All accepted column names</strong>{selectedImporter?.columns.map((column, index) => <div key={column.name}><p>{index + 1}. {displayColumn(column)}</p>{column.note && <p className="small-muted">{column.note}</p>}</div>)}<p className="small-muted">* Mandatory column. IDP also requires either a course-style column or at least one ID result column.</p></div></div>
    </div>

    <div className="upload-layout campaign-upload-section">
      <form className="upload-card" onSubmit={handleCampaignUpload}>
        <div className="upload-icon">M</div><h2>Upload marketing campaigns</h2><p>Campaigns are linked by learner number. If a learner is new, a basic learner profile is created automatically and can be completed later.</p>
        <div className="format-item"><strong>This file will receive these columns</strong><p>Learner number * | Marketing type * | Campaign name *</p><p className="small-muted">* Mandatory column</p></div>
        <label>Campaign file</label><input type="file" accept=".xlsx,.csv" onChange={e => setCampaignFile(e.target.files[0] || null)} />
        <button type="submit" className="primary-button" disabled={campaignUploading || !!campaignJob.jobId || !campaignFile}>{campaignUploading ? "Starting import..." : campaignJob.jobId ? "Import in progress" : "Upload campaign file"}</button>
        {campaignMessage && <div className="upload-message">{campaignMessage}</div>}
        <UploadProgress progress={campaignJob.progress} jobId={campaignJob.jobId} />
      </form>
      <div className="format-card"><div className="eyebrow">REQUIRED COLUMNS</div><h3>Marketing campaign format</h3><div className="format-item"><strong>Learner number *</strong><p>Must match an existing learner, or a basic learner profile will be created.</p></div><div className="format-item"><strong>Marketing type *</strong><p>For example: Email, WhatsApp, SMS or Event.</p></div><div className="format-item"><strong>Campaign name *</strong><p>The name used to identify the campaign.</p></div><p className="small-muted">* Mandatory column</p></div>
    </div>

    <div className="section-heading"><div><div className="eyebrow">HISTORY</div><h2>Recent uploads</h2></div></div>
    <div className="table-card"><table><thead><tr><th>File</th><th>Type</th><th>Status</th><th>Rows</th><th>Imported</th><th>Skipped</th><th>Uploaded</th></tr></thead><tbody>{uploads.map(u => <tr key={u.id}><td>{u.filename}</td><td>{u.import_type}</td><td><span className={u.status === "COMPLETED" ? "status-pill pass" : u.status === "FAILED" ? "status-pill fail" : "status-pill"}>{u.status}</span></td><td>{u.rows_total}</td><td>{u.rows_imported}</td><td>{u.rows_skipped}</td><td>{new Date(u.uploaded_at).toLocaleString()}</td></tr>)}</tbody></table>{uploads.length === 0 && <div className="table-message">No uploads yet.</div>}</div>
  </section>;
}
