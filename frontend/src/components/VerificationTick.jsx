import "./verification.css";

export default function VerificationTick({record, label=false}) {
  const verified = Boolean(record?.verified);
  const title = record?.verification_source || (verified ? "Verified enrolment" : "Pending verification");
  const detail = record?.verified_by ? ` · ${record.verified_by}${record.verified_at ? ` · ${new Date(record.verified_at).toLocaleString()}` : ""}` : "";
  return <span className={`verification-tick ${verified ? "verified" : "pending"}`} role="img" aria-label={title} title={title + detail}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/></svg>
    {label && <span>{verified ? "Verified" : "Unverified"}</span>}
  </span>;
}
