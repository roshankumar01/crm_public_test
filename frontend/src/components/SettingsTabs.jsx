import { NavLink } from "react-router-dom";

export default function SettingsTabs() {
  return <nav className="settings-tabs" aria-label="Settings sections">
    <NavLink end to="/crm/settings" className={({ isActive }) => isActive ? "settings-tab active" : "settings-tab"}>Counselor mapping</NavLink>
    <NavLink to="/crm/settings/course-mapping" className={({ isActive }) => isActive ? "settings-tab active" : "settings-tab"}>Course mapping</NavLink>
    <NavLink to="/crm/settings/recommendation-rules" className={({ isActive }) => isActive ? "settings-tab active" : "settings-tab"}>Recommendation rules</NavLink>
  </nav>;
}
