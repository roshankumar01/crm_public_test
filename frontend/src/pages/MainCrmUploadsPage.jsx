import { useEffect, useState } from "react";
import { getMainCrmUploads, startUploadJob } from "../api";
import UploadProgress from "../components/UploadProgress.jsx";
import useUploadJob from "../hooks/useUploadJob.js";
import MainCrmMigrationUpload from "./MainCrmMigrationUpload";

const TYPES = [
  ["INFO_EMAIL_LEADS", "Info email leads", "Web enquiry, live chat, landing-page and social-media leads. The source column keeps the sub-source."],
  ["LIVE_ONLINE_LEADS", "Live online leads", "Online leads imported separately from the live-chat leads contained in Info email leads."],
  ["DIRECT_CALLS", "Direct calls", "Inbound and outbound call enquiries."],
  ["CAMPAIGN_REPLIES", "Campaign replies", "User replies to email campaigns, matched by normalized email."],
  ["CAMPAIGN_DATA", "Campaign data", "Marketing messages sent to leads, matched by normalized email."],
];

const COLUMNS = {
  INFO_EMAIL_LEADS: ["full_name", "email", "phone_number", "whatsapp_number", "source", "course", "region", "age", "status_of_lead", "counselor", "sales_owner", "counsilor_email", "note"],
  LIVE_ONLINE_LEADS: ["FULLNAME", "EMAIL", "PHONENUMBER", "WHATSAPPNUMBER", "SOURCE", "COURSE", "REGIONS", "COUNSILORNAME", "COUNTRY"],
  DIRECT_CALLS: ["date", "full_name", "email", "phone_number", "whatsapp_number", "source", "country/region", "course", "service_type", "status", "counselor", "counselor_email", "call_type", "test_status", "comment", "followup_date"],
  CAMPAIGN_REPLIES: ["date", "email", "campaign_type", "course", "full_user_reply", "campaign name", "campaign description"],
  CAMPAIGN_DATA: ["date", "email", "campaign_type", "campaign name", "campaign description", "course_campaign"],
};

const REQUIRED_COLUMNS = {
  INFO_EMAIL_LEADS: new Set(["full_name", "email", "phone_number", "source", "course"]),
  LIVE_ONLINE_LEADS: new Set(["FULLNAME", "EMAIL", "PHONENUMBER", "WHATSAPPNUMBER", "SOURCE", "COURSE", "REGIONS", "COUNSILORNAME", "COUNTRY"]),
  DIRECT_CALLS: new Set(["date", "full_name", "email", "phone_number", "course"]),
  CAMPAIGN_REPLIES: new Set(["date", "email", "campaign_type", "course", "full_user_reply", "campaign name", "campaign description"]),
  CAMPAIGN_DATA: new Set(["date", "email", "campaign_type", "campaign name", "campaign description", "course_campaign"]),
};

function displayColumn(type, column) {
  return `${column}${REQUIRED_COLUMNS[type].has(column) ? " *" : ""}`;
}

export default function MainCrmUploadsPage({ refreshKey = 0 }) {
  const [uploads, setUploads] = useState([]);
  const [mode, setMode] = useState("CREATE");
  const [type, setType] = useState("INFO_EMAIL_LEADS");
  const [target, setTarget] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const { begin, jobId, progress } = useUploadJob("main_crm_upload_job", job => {
    setMessage(job.status === "FAILED" ? `Upload failed: ${job.error_message}` :
      `Upload complete: ${job.rows_imported} rows imported, ${job.rows_skipped} skipped.`);
    load();
  }, error => setMessage(`Could not check upload progress: ${error.message}. Retrying...`));

  async function load() {
    try { setUploads(await getMainCrmUploads()); }
    catch (error) { setMessage(error.message); }
  }

  useEffect(() => { load(); }, [refreshKey]);

  async function submit(event) {
    event.preventDefault();
    if (!file) return setMessage("Choose an Excel or CSV file.");
    if (mode === "UPDATE" && !target) return setMessage("Choose the previous upload to update.");
    try {
      setUploading(true);
      setMessage("");
      const result = await startUploadJob({ kind: "MAIN_CRM", file, sourceCategory: type, uploadMode: mode, uniqueNumber: target });
      begin(result);
      setMessage("Import started. You can leave this page and return to check progress.");
      setFile(null);
      event.target.reset();
      await load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setUploading(false);
    }
  }

  const selectedType = TYPES.find(item => item[0] === type);

  return <section className="upload-workspace-section">
    {message && <div className="upload-message page-message">{message}</div>}
    <UploadProgress progress={progress} jobId={jobId} />
    <div className="upload-layout">
      <form className="upload-card" onSubmit={submit}>
        <div className="upload-icon">↑</div><h2>Upload CRM data</h2>
        <label>Action</label>
        <div className="segmented-control"><button type="button" className={mode === "CREATE" ? "segment active" : "segment"} onClick={() => setMode("CREATE")}>New upload</button><button type="button" className={mode === "UPDATE" ? "segment active" : "segment"} onClick={() => setMode("UPDATE")}>Update upload</button></div>
        {mode === "UPDATE" && <><label>Upload to replace</label><select value={target} onChange={event => { setTarget(event.target.value); const item = uploads.find(upload => upload.unique_number === event.target.value); if (item) setType(item.source_category); }}><option value="">Select upload number</option>{uploads.filter(upload => upload.unique_number && upload.source_category !== "MIGRATION").map(upload => <option key={upload.id} value={upload.unique_number}>{upload.unique_number} — {upload.filename}</option>)}</select></>}
        <label>Upload type</label>
        <select value={type} onChange={event => setType(event.target.value)}>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <p className="small-muted">{selectedType?.[2]}</p>
        <div className="format-item"><strong>This file will receive these columns</strong><p>{COLUMNS[type].map(column => displayColumn(type, column)).join(" | ")}</p><p className="small-muted">* Mandatory column</p></div>
        <label>Excel or CSV file</label>
        <input type="file" accept=".xlsx,.csv" onChange={event => setFile(event.target.files[0] || null)} />
        <button className="primary-button" disabled={uploading || !!jobId || !file}>{uploading ? "Starting import..." : jobId ? "Import in progress" : mode === "UPDATE" ? "Replace upload data" : "Create upload"}</button>
      </form>
      <div className="format-card">
        <div className="eyebrow">EXPECTED FORMAT</div><h3>{selectedType?.[1]}</h3>
        <div className="format-item"><strong>All column names</strong>{COLUMNS[type].map((column, index) => <p key={column}>{index + 1}. {displayColumn(type, column)}</p>)}<p className="small-muted">* Mandatory column</p></div>
        <div className="format-item"><strong>Email and phone normalization</strong><p>Email casing and spaces are removed for matching. Phone punctuation and country-code differences are normalized to the final ten digits.</p></div>
        <div className="format-item"><strong>Update upload</strong><p>Select an upload reference to replace its lifecycle rows with the new file.</p></div>
      </div>
    </div>
    <MainCrmMigrationUpload uploads={uploads} reload={load} />
    <div className="section-heading"><div><div className="eyebrow">UPLOAD REFERENCES</div><h2>Recent Main CRM uploads</h2></div></div>
  </section>;
}
