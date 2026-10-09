// Production requests always use Caddy on the same origin, even if a local
// VITE_API_URL setting was present when the frontend was built.
const API_URL = (import.meta.env.PROD ? "/api" : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000")).replace(/\/+$/, "");
const TOKEN_KEY = "learning_crm_token";

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getStoredToken();
  if (token && options.auth !== false) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${url}`, { ...options, headers });
  if (!response.ok) {
    let message = "Something went wrong.";
    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {}
    const err = new Error(message);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

export const login = (username, password) => request("/auth/login", {
  method: "POST",
  auth: false,
  body: JSON.stringify({ username, password }),
});
export const getMe = () => request("/auth/me");
export const logout = () => request("/auth/logout", { method: "POST" });

export const getLearners = (search = "") => request(`/learners${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const getLearner = learnerNumber => request(`/learners/${learnerNumber}`);
export const getUpsellContacts = (search = "", page = 1) => request(`/learners/contacts?search=${encodeURIComponent(search)}&page=${page}`);
export const getUpsellContact = customerId => request(`/learners/contacts/${customerId}`);
export const getOpportunities = () => request("/opportunities");
export const getCounselors = () => request("/leads/counselors");
export const getTrackedLeads = (params = {}) => request(`/leads?${new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "")).toString()}`);
export const getLead = leadId => request(`/leads/${leadId}`);
export const updateLeadStatus = (leadId, status, note) => request(`/leads/${leadId}/status`, {
  method: "PATCH",
  body: JSON.stringify({ status, note }),
});
export const assignLead = (leadId, counselorUserId) => request(`/leads/${leadId}/assignment`, {
  method: "PATCH",
  body: JSON.stringify({ counselor_user_id: counselorUserId || null }),
});
export const addLeadActivity = (leadId, activity) => request(`/leads/${leadId}/activities`, {
  method: "POST",
  body: JSON.stringify(activity),
});
export const getLeadAnalytics = () => request("/analytics/leads");

export async function downloadLeadAnalytics(opportunityKey = "") {
  const headers = new Headers();
  const token = getStoredToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const query = opportunityKey ? `?opportunity_key=${encodeURIComponent(opportunityKey)}` : "";
  const response = await fetch(`${API_URL}/analytics/leads/export${query}`, { headers });
  if (!response.ok) {
    let message = "Could not download analytics.";
    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {}
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^\"]+)"?/i);
  const filename = match?.[1] || "lead-analytics.xlsx";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const getImportTypes = () => request("/uploads/import-types");
export const getUploads = () => request("/uploads");
export const getUploadResetOptions = () => request("/uploads/reset-options");
export const resetSelectedUploads = uploadIds => request("/uploads/reset", {
  method: "POST",
  body: JSON.stringify({ upload_ids: uploadIds, confirmation: "DELETE SELECTED UPLOADS" }),
});

export function uploadExcel(importType, file) {
  const formData = new FormData();
  formData.append("import_type", importType);
  formData.append("file", file);
  return request("/uploads", { method: "POST", body: formData });
}

export function uploadCampaignExcel(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/campaigns/upload", { method: "POST", body: formData });
}

export function startUploadJob({ kind, file, importType, sourceCategory, uploadMode = "CREATE", uniqueNumber = "" }) {
  const formData = new FormData();
  formData.append("kind", kind);
  formData.append("file", file);
  if (importType) formData.append("import_type", importType);
  if (sourceCategory) formData.append("source_category", sourceCategory);
  formData.append("upload_mode", uploadMode);
  if (uniqueNumber) formData.append("unique_number", uniqueNumber);
  return request("/uploads/jobs", { method: "POST", body: formData });
}
export const getUploadJobProgress = jobId => request(`/uploads/jobs/${encodeURIComponent(jobId)}`);

export function getMainCrmLeads({ page = 1, pageSize = 50, sourceCategory = "ALL", search = "", counselorIds = [], statuses = [], sources = [], courses = [], sortBy = "updated_at", sortDirection = "desc" } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), source_category: sourceCategory, search });
  for (const [key, values] of [["counselor_ids", counselorIds], ["statuses", statuses], ["sources", sources], ["courses", courses]]) values.forEach(value => params.append(key, value));
  params.set("sort_by", sortBy); params.set("sort_direction", sortDirection);
  return request(`/crm/leads?${params}`);
}
export const getMainCrmFilterOptions = sourceCategory => request(`/crm/leads/filter-options?source_category=${encodeURIComponent(sourceCategory || "ALL")}`);
export const getMainCrmSummary = (period = "all") => request(`/crm/leads/summary?period=${encodeURIComponent(period)}`);
const companyDashboardQuery = (range = {}) => {
  const params = new URLSearchParams();
  if (range.startDate && range.endDate) {
    params.set("start_date", range.startDate);
    params.set("end_date", range.endDate);
  } else params.set("period", "all");
  return params.toString();
};
export const getCompanyDashboard = (section, range) => request(`/company-dashboard/${section}?${companyDashboardQuery(range)}`);
export const getCompanySalesCourses = (counselorId, range) => request(`/company-dashboard/sales/courses?${companyDashboardQuery(range)}${counselorId == null ? "" : `&counselor_id=${encodeURIComponent(counselorId)}`}`);
export const getCompanySalesSources = (counselorId, course, range) => request(`/company-dashboard/sales/sources?${companyDashboardQuery(range)}&course=${encodeURIComponent(course)}${counselorId == null ? "" : `&counselor_id=${encodeURIComponent(counselorId)}`}`);
export const getMainCrmMismatch = (period = "all",page=1,state="pending") => request(`/crm/leads/mismatch?period=${encodeURIComponent(period)}&page=${page}&state=${encodeURIComponent(state)}`);
export async function downloadCrmExport(path, filename) { const response = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${getStoredToken()}` } }); if (!response.ok) throw new Error(await response.text()); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url); }
export const downloadMainCrmExport = period => downloadCrmExport(`/crm/leads/export?period=${encodeURIComponent(period)}`, "main-crm-export.xlsx");
export const downloadLearnersCrmExport = period => downloadCrmExport(`/learners-crm/export?period=${encodeURIComponent(period)}`, "learners-crm-export.xlsx");
export const downloadUpsellCrmExport = period => downloadCrmExport(`/analytics/leads/export?period=${encodeURIComponent(period)}`, "upsell-crm-export.xlsx");
export const downloadMainCrmMismatch = (period,state="pending") => downloadCrmExport(`/crm/leads/mismatch/export?period=${encodeURIComponent(period)}&state=${encodeURIComponent(state)}`, "converted-mismatches.xlsx");
export const getMainCrmLead = leadId => request(`/crm/leads/detail/${leadId}`);
export const updateMainCrmLeadDetails = (leadId, payload) => request(`/crm/leads/${leadId}/details`, { method: "PATCH", body: JSON.stringify(payload) });
export const addMainCrmLeadNote = (leadId, note) => request(`/crm/leads/${leadId}/notes`, { method: "POST", body: JSON.stringify({ note }) });
export const getMainCrmCampaignActivities = () => request("/crm/leads/campaign-activities");
export const updateMainCrmLeadStatus = (leadId, status, note) => request(`/crm/leads/${leadId}/status`, {
  method: "PATCH", body: JSON.stringify({ status, note }),
});
export const assignMainCrmLead = (leadId, counselorUserId) => request(`/crm/leads/${leadId}/assignment`, {
  method: "PATCH", body: JSON.stringify({ counselor_user_id: counselorUserId || null }),
});
export const getMainCrmUploads = () => request("/crm/leads/uploads");
export function previewMainCrmMigration(file) {
  const formData = new FormData(); formData.append("file", file);
  return request("/crm/leads/migration-preview", { method: "POST", body: formData });
}
export function uploadMainCrmMigration(file, sourceCategories, uploadMode = "CREATE", uniqueNumber = "") {
  const formData = new FormData(); formData.append("file", file);
  formData.append("source_categories", JSON.stringify(sourceCategories));
  formData.append("upload_mode", uploadMode);
  if (uniqueNumber) formData.append("unique_number", uniqueNumber);
  return request("/crm/leads/migration-start", { method: "POST", body: formData });
}
export const getMainCrmMigrationProgress = uniqueNumber => request(`/crm/leads/migration-progress/${encodeURIComponent(uniqueNumber)}`);
export async function downloadMigrationSkipped(uniqueNumber) {
  const response = await fetch(`${API_URL}/crm/leads/migration-skipped/${encodeURIComponent(uniqueNumber)}`, { headers: { Authorization: `Bearer ${getStoredToken()}` } });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `skipped-migration-${uniqueNumber}.csv`; link.click(); URL.revokeObjectURL(url);
}
export function uploadMainCrmLeads(sourceCategory, file, uploadMode = "CREATE", uniqueNumber = "") {
  const formData = new FormData();
  formData.append("source_category", sourceCategory); formData.append("file", file);
  formData.append("upload_mode", uploadMode);
  if (uniqueNumber) formData.append("unique_number", uniqueNumber);
  return request("/crm/leads/upload", { method: "POST", body: formData });
}
export const getCounselorMapping = () => request("/crm/leads/counselor-mapping");
export const createCounselor = payload => request("/crm/leads/counselor-mapping", { method: "POST", body: JSON.stringify(payload) });
export const updateCounselor = (userId, payload) => request(`/crm/leads/counselor-mapping/${userId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const getLearnersCrmOverview = (period = "all") => request(`/learners-crm/overview?period=${encodeURIComponent(period)}`);
export const getDashboardSummary = (period = "all") => request(`/dashboard/summary?period=${encodeURIComponent(period)}`);
export async function downloadUploadSkipped(jobId) {
  const response = await fetch(`${API_URL}/uploads/jobs/${encodeURIComponent(jobId)}/skipped`, { headers: { Authorization: `Bearer ${getStoredToken()}` } });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
  link.href = url; link.download = `skipped-rows-${jobId}.csv`; link.click(); URL.revokeObjectURL(url);
}
export const searchLearnersCrm = (search, page = 1) => request(`/learners-crm/learners?search=${encodeURIComponent(search)}&page=${page}`);
export const getLearnersCrmProfile = learnerId => request(`/learners-crm/learners/${learnerId}`);
export const getLearnersCrmUploads = () => request("/learners-crm/uploads");
export const getLearnerVerification = (kind = "daily", page = 1) => request(`/learners-crm/verification?kind=${encodeURIComponent(kind)}&page=${page}`);
export const verifyDailyLearner = (id, values) => request(`/learners-crm/daily-rows/${id}/verify`, { method: "POST", body: JSON.stringify(values) });
export const getLearnerCourseMapping = () => request("/learners-crm/course-mapping");
export const createLearnerCourseCategory = name => request("/learners-crm/course-mapping/categories", { method: "POST", body: JSON.stringify({ name }) });
export const updateLearnerCourseCategory = (id, name) => request(`/learners-crm/course-mapping/categories/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const deleteLearnerCourseCategory = id => request(`/learners-crm/course-mapping/categories/${id}`, { method: "DELETE" });
export const createLearnerCourseSubcategory = (name, categoryId) => request("/learners-crm/course-mapping/subcategories", { method: "POST", body: JSON.stringify({ name, category_id: categoryId }) });
export const updateLearnerCourseSubcategory = (id, name, categoryId) => request(`/learners-crm/course-mapping/subcategories/${id}`, { method: "PATCH", body: JSON.stringify({ name, category_id: categoryId }) });
export const deleteLearnerCourseSubcategory = id => request(`/learners-crm/course-mapping/subcategories/${id}`, { method: "DELETE" });
export const createLearnerCourse = (courseName, subcategoryId) => request("/learners-crm/course-mapping/courses", { method: "POST", body: JSON.stringify({ course_name: courseName, subcategory_id: subcategoryId }) });
export const updateLearnerCourse = (id, courseName, subcategoryId) => request(`/learners-crm/course-mapping/courses/${id}`, { method: "PATCH", body: JSON.stringify({ course_name: courseName, subcategory_id: subcategoryId }) });
export const deleteLearnerCourse = id => request(`/learners-crm/course-mapping/courses/${id}`, { method: "DELETE" });
export const getRecommendationRules = () => request("/settings/recommendation-rules");
export const updateRecommendationRules = coolingDays => request("/settings/recommendation-rules", { method: "PATCH", body: JSON.stringify({ cooling_days: coolingDays }) });
export function uploadLearnersCrm(file, uploadMode = "CREATE", uniqueNumber = "") {
  const formData = new FormData(); formData.append("file", file); formData.append("upload_mode", uploadMode);
  if (uniqueNumber) formData.append("unique_number", uniqueNumber);
  return request("/learners-crm/upload", { method: "POST", body: formData });
}

// Course conversations and personal edits remain within Upsell.
export const getUpsellManagement = (id, page=1) => request(`/upsell/manage/${id}?history_page=${page}`);
export const getUpsellCourseCatalog = () => request("/upsell/manage/catalog");
export const editUpsellInfo = (id, payload) => request(`/upsell/manage/${id}/info`, {method:"PATCH",body:JSON.stringify(payload)});
export const chooseUpsellCourse = (id, mapping_id) => request(`/upsell/manage/${id}/cases`, {method:"POST",body:JSON.stringify({mapping_id})});
export const setUpsellCourseStatus = (id, caseId, status, note) => request(`/upsell/manage/${id}/cases/${caseId}/status`, {method:"PATCH",body:JSON.stringify({status,note})});
export const saveUpsellCourseActivity = (id, caseId, payload) => request(`/upsell/manage/${id}/cases/${caseId}/activities`, {method:"POST",body:JSON.stringify(payload)});
export const editUpsellCourseActivity = (id, caseId, activityId, payload) => request(`/upsell/manage/${id}/cases/${caseId}/activities/${activityId}`, {method:"PATCH",body:JSON.stringify(payload)});
export const convertUpsellCourse = (id, caseId, note) => request(`/upsell/manage/${id}/cases/${caseId}/convert`, {method:"POST",body:JSON.stringify({note})});
export const getUpsellMismatch = (period="all",page=1,state="pending") => request(`/upsell/manage/mismatch?period=${encodeURIComponent(period)}&page=${page}&state=${encodeURIComponent(state)}`);
export const downloadUpsellMismatch = (period,state="pending") => downloadCrmExport(`/upsell/manage/mismatch/export?period=${encodeURIComponent(period)}&state=${encodeURIComponent(state)}`,"upsell-mismatch.xlsx");

export const getUpsellContactHistory = (id,caseId,page=1) => request(`/upsell/manage/${id}/history/${caseId}?page=${page}`);

export const verifyMainCrmMismatch = id => request(`/crm/leads/mismatch/${id}/verify`, {method:"POST"});
export const verifyUpsellMismatch = id => request(`/upsell/manage/mismatch/${id}/verify`, {method:"POST"});

export const resetAllCrmData = () => request("/uploads/reset-all", {method:"POST",body:JSON.stringify({confirmation:"RESET ALL CRM DATA"})});

export const getLeadReminder = (workspace,id) => request(`/reminders/${workspace}/${id}`);
export const saveLeadReminder = (workspace,id,days,notes) => request(`/reminders/${workspace}/${id}`,{method:"PUT",body:JSON.stringify({days,notes})});
export const completeLeadReminder = (workspace,id) => request(`/reminders/${workspace}/${id}/complete`,{method:"POST"});
export const getReminders = (workspace,view="pending",page=1,counselorId="") => request(`/reminders/${workspace}?view=${view}&page=${page}${counselorId?`&counselor_id=${encodeURIComponent(counselorId)}`:""}`);

const counselorRangeQuery = range => range?.startDate && range?.endDate
  ? `period=custom&start_date=${encodeURIComponent(range.startDate)}&end_date=${encodeURIComponent(range.endDate)}`
  : "period=all";
export const getCounselorDashboard = range => request(`/company-dashboard/counselors?${counselorRangeQuery(range)}`);
export const getCounselorChanges = (counselorId,range,page=1,mode="all",person="") => request(`/company-dashboard/counselors/changes?counselor_id=${encodeURIComponent(counselorId)}&page=${page}&mode=${encodeURIComponent(mode)}${person?`&person=${encodeURIComponent(person)}`:""}&${counselorRangeQuery(range)}`);
