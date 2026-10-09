import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import RemindersPage from "./pages/RemindersPage.jsx";
import AppLayout from "./components/AppLayout.jsx";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import LeadAnalyticsPage from "./pages/LeadAnalyticsPage.jsx";
import UpsellMismatchPage from "./pages/UpsellMismatchPage.jsx";
import LeadDetailPage from "./pages/LeadDetailPage.jsx";
import LearnerDetailPage from "./pages/LearnerDetailPage.jsx";
import LearnersPage from "./pages/LearnersPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OpportunitiesPage from "./pages/OpportunitiesPage.jsx";
import MainCrmPage from "./pages/MainCrmPage.jsx";
import MainCrmOverviewPage from "./pages/MainCrmOverviewPage.jsx";
import MainCrmAnalyticsPage from "./pages/MainCrmAnalyticsPage.jsx";
import MainCrmMismatchPage from "./pages/MainCrmMismatchPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import CourseMappingSettingsPage from "./pages/CourseMappingSettingsPage.jsx";
import RecommendationRulesSettingsPage from "./pages/RecommendationRulesSettingsPage.jsx";
import MainCrmLeadDetailPage from "./pages/MainCrmLeadDetailPage.jsx";
import LearnersCrmOverviewPage from "./pages/LearnersCrmOverviewPage.jsx";
import LearnersCrmSearchPage from "./pages/LearnersCrmSearchPage.jsx";
import LearnersCrmDetailPage from "./pages/LearnersCrmDetailPage.jsx";
import LearnersCrmVerificationPage from "./pages/LearnersCrmVerificationPage.jsx";
import DataUploadsPage from "./pages/DataUploadsPage.jsx";
import CompanyDashboardPage from "./pages/CompanyDashboardPage.jsx";
import CounselorDashboardPage from "./pages/CounselorDashboardPage.jsx";

function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page">Loading CRM...</div>;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

function RequireAdmin() {
  const { user } = useAuth();
  return user?.role === "ADMIN" ? <Outlet /> : <Navigate to="/upsell" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route path="/crm" element={<MainCrmOverviewPage />} />
              <Route element={<RequireAdmin />}>
                <Route path="/dashboard" element={<CompanyDashboardPage section="overview" />} />
                <Route path="/dashboard/sales" element={<CompanyDashboardPage section="sales" />} />
                <Route path="/dashboard/dinesh" element={<CompanyDashboardPage section="dinesh" />} />
                <Route path="/dashboard/counselors" element={<CounselorDashboardPage section="overview" />} />
                <Route path="/dashboard/counselors/changes" element={<CounselorDashboardPage section="changes" />} />
              </Route>
              <Route path="/crm/reminders" element={<RemindersPage workspace="main" />} />
              <Route path="/upsell/reminders" element={<RemindersPage workspace="upsell" />} />
              <Route path="/crm/leads" element={<MainCrmPage />} />
              <Route path="/crm/leads/:leadId" element={<MainCrmLeadDetailPage />} />
              <Route path="/crm/analytics" element={<MainCrmAnalyticsPage />} />
              <Route path="/crm/mismatch" element={<MainCrmMismatchPage />} />
              <Route path="/crm/campaigns" element={<Navigate to="/crm" replace />} />
              <Route element={<RequireAdmin />}>
                <Route path="/crm/uploads" element={<DataUploadsPage />} />
                <Route path="/crm/settings" element={<SettingsPage />} />
                <Route path="/crm/settings/course-mapping" element={<CourseMappingSettingsPage />} />
                <Route path="/crm/settings/recommendation-rules" element={<RecommendationRulesSettingsPage />} />
                <Route path="/crm/mapping" element={<Navigate to="/crm/settings" replace />} />
              </Route>
              <Route path="/upsell" element={<DashboardPage />} />
              <Route path="/upsell/opportunities" element={<OpportunitiesPage />} />
              <Route path="/upsell/opportunities/idp" element={<OpportunitiesPage />} />
              <Route path="/upsell/leads/:leadId" element={<LeadDetailPage />} />
              <Route path="/upsell/mismatch" element={<UpsellMismatchPage />} />
              <Route path="/upsell/lead-analytics" element={<LeadAnalyticsPage />} />
              <Route path="/upsell/campaigns" element={<Navigate to="/upsell" replace />} />
              <Route path="/upsell/learners/:learnerNumber" element={<LearnerDetailPage />} />
              <Route path="/upsell/contacts/:customerId" element={<LearnerDetailPage />} />
              <Route element={<RequireAdmin />}>
                <Route path="/upsell/learners" element={<LearnersPage />} />
                <Route path="/upsell/uploads" element={<Navigate to="/crm/uploads?section=upsell" replace />} />
              </Route>
              <Route path="/learners-crm">
                <Route index element={<LearnersCrmOverviewPage />} />
                <Route path="learners" element={<LearnersCrmSearchPage />} />
                <Route path="learners/:learnerId" element={<LearnersCrmDetailPage />} />
                <Route element={<RequireAdmin />}>
                  <Route path="verification" element={<LearnersCrmVerificationPage />} />
                  <Route path="uploads" element={<Navigate to="/crm/uploads?section=learners" replace />} />
                </Route>
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/crm" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
