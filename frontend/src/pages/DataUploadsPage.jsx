import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import UploadReset from "../components/UploadReset.jsx";
import MainCrmUploadsPage from "./MainCrmUploadsPage.jsx";
import LearnersCrmUploadsPage from "./LearnersCrmUploadsPage.jsx";
import UploadsPage from "./UploadsPage.jsx";

const SECTIONS = [
  { id: "main", label: "Main CRM", description: "Enquiries and campaign lifecycle" },
  { id: "learners", label: "Learners CRM", description: "Profiles and course enrolments" },
  { id: "upsell", label: "Upsell CRM", description: "Course results and marketing campaigns" },
];

export default function DataUploadsPage() {
  const [searchParams] = useSearchParams();
  const [refreshKey, setRefreshKey] = useState(0);
  const section = SECTIONS.some(item => item.id === searchParams.get("section")) ? searchParams.get("section") : "main";

  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM DATA MANAGEMENT</div><h1>Data uploads</h1><p className="page-description">Upload and manage files for all three CRM workspaces in one place.</p></div></div>
    <nav className="upload-section-tabs" aria-label="Upload workspace">
      {SECTIONS.map(item => <Link key={item.id} to={item.id === "main" ? "/crm/uploads" : `/crm/uploads?section=${item.id}`} className={section === item.id ? "upload-section-tab active" : "upload-section-tab"} aria-current={section === item.id ? "page" : undefined}>
        <strong>{item.label}</strong><span>{item.description}</span>
      </Link>)}
    </nav>
    {section === "main" && <MainCrmUploadsPage refreshKey={refreshKey} />}
    {section === "learners" && <LearnersCrmUploadsPage refreshKey={refreshKey} />}
    {section === "upsell" && <UploadsPage refreshKey={refreshKey} />}
    <UploadReset onReset={() => setRefreshKey(value => value + 1)} />
  </div>;
}
