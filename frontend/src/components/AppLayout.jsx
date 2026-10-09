import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const icons = { dashboard: "⌁", learners: "◎", leads: "◇", analytics: "⌗", campaigns: "◌", uploads: "⇧", reminders: "\u23f1", settings: "\u2699" };
const linkClass = ({ isActive }) => isActive ? "nav-link active" : "nav-link";
function NavItem({ to, icon, children, end }) { return <NavLink to={to} end={end} className={linkClass}><span className="nav-icon">{icons[icon]}</span><span>{children}</span></NavLink>; }

export default function AppLayout() {
  const { user, logout } = useAuth(); const navigate = useNavigate(); const location = useLocation(); const isAdmin = user?.role === "ADMIN";
  const isUpsell = location.pathname.startsWith("/upsell");
  const isLearnersCrm = location.pathname.startsWith("/learners-crm");
  const isDashboard = location.pathname.startsWith("/dashboard");
  async function handleLogout() { await logout(); navigate("/login", { replace: true }); }
  const initials = user?.display_name?.split(" ").map(part => part[0]).slice(0, 2).join("").toUpperCase() || "LC";
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">C</div><div><div className="brand-name">GWG CRM</div><div className="brand-subtitle">Workspace</div></div></div>
      <div className="workspace-tabs three-workspaces" aria-label="CRM workspace switcher">
        <NavLink to="/crm" className={({ isActive }) => isActive ? "workspace-tab active" : "workspace-tab"}>Main CRM</NavLink>
        <NavLink to="/learners-crm" className={({ isActive }) => isActive ? "workspace-tab active" : "workspace-tab"}>Learners CRM</NavLink>
        <NavLink to="/upsell" className={({ isActive }) => isActive ? "workspace-tab active" : "workspace-tab"}>Upsell CRM</NavLink>
        {isAdmin && <NavLink to="/dashboard" className={({ isActive }) => isDashboard ? "workspace-tab active" : "workspace-tab"}>Dashboard</NavLink>}
      </div>
      {isDashboard ? <>
        <div className="nav-label">Company dashboard</div>
        <nav className="nav"><NavItem to="/dashboard" end icon="dashboard">Overview</NavItem><NavItem to="/dashboard/sales" icon="analytics">Sales</NavItem><NavItem to="/dashboard/dinesh" icon="learners">Dinesh</NavItem><NavItem to="/dashboard/counselors" end icon="leads">Counselors</NavItem><NavItem to="/dashboard/counselors/changes" icon="analytics">Change log</NavItem></nav>
      </> : isUpsell ? <>
        <div className="nav-label">Upsell menu</div>
        <nav className="nav"><NavItem to="/upsell" end icon="dashboard">Overview</NavItem>{isAdmin && <NavItem to="/upsell/learners" icon="learners">Learners</NavItem>}<NavItem to="/upsell/opportunities" icon="leads">{isAdmin ? "Lead pipeline" : "My leads"}</NavItem><NavItem to="/upsell/lead-analytics" icon="analytics">Analytics</NavItem><NavItem to="/upsell/reminders" icon="reminders">Reminders</NavItem><NavItem to="/upsell/mismatch" icon="analytics">Mismatch</NavItem></nav>
      </> : isLearnersCrm ? <>
        <div className="nav-label">Learners CRM menu</div>
        <nav className="nav"><NavItem to="/learners-crm" end icon="dashboard">Overview</NavItem><NavItem to="/learners-crm/learners" icon="learners">Find learner</NavItem>{isAdmin && <NavItem to="/learners-crm/verification" icon="analytics">Verification</NavItem>}</nav>
      </> : <>
        <div className="nav-label">Main CRM menu</div>
        <nav className="nav"><NavItem to="/crm" end icon="dashboard">Overview</NavItem><NavItem to="/crm/leads" icon="leads">{isAdmin ? "Lead pipeline" : "My leads"}</NavItem><NavItem to="/crm/analytics" icon="analytics">Analytics</NavItem><NavItem to="/crm/reminders" icon="reminders">Reminders</NavItem><NavItem to="/crm/mismatch" icon="analytics">Mismatch</NavItem>{isAdmin && <NavItem to="/crm/uploads" icon="uploads">Data uploads</NavItem>}</nav>
      </>}
      <div className="sidebar-bottom">
        {isAdmin && !isUpsell && !isLearnersCrm && <nav className="nav sidebar-settings" aria-label="Administration"><NavItem to="/crm/settings" icon="settings">Settings</NavItem></nav>}
        <div className="sidebar-footer user-footer"><div className="user-avatar">{initials}</div><div className="user-meta"><strong>{user?.display_name}</strong><span>{isAdmin ? "Administrator" : "Counselor"}</span></div></div>
        <button type="button" className="nav-link sidebar-logout-link" onClick={handleLogout}><span className="nav-icon" aria-hidden="true">&rarr;</span><span>Log out</span></button>
      </div>
    </aside>
    <main className="main-content"><Outlet /></main>
  </div>;
}
