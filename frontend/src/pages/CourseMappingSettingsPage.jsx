import { useEffect, useState } from "react";
import SettingsTabs from "../components/SettingsTabs.jsx";
import { createLearnerCourse, createLearnerCourseCategory, createLearnerCourseSubcategory, deleteLearnerCourse, deleteLearnerCourseCategory, deleteLearnerCourseSubcategory, getLearnerCourseMapping, updateLearnerCourse, updateLearnerCourseCategory, updateLearnerCourseSubcategory } from "../api";

export default function CourseMappingSettingsPage() {
  const [data, setData] = useState(null);
  const [mainId, setMainId] = useState(null);
  const [subId, setSubId] = useState(null);
  const [mainName, setMainName] = useState("");
  const [subName, setSubName] = useState("");
  const [courseName, setCourseName] = useState("");
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const next = await getLearnerCourseMapping();
    setData(next);
    setMainId(current => next.categories.some(item => item.id === current) ? current : next.categories[0]?.id ?? null);
  }
  useEffect(() => { load().catch(err => setError(err.message)); }, []);
  const main = data?.categories.find(item => item.id === mainId);
  useEffect(() => { setSubId(current => main?.subcategories.some(item => item.id === current) ? current : main?.subcategories[0]?.id ?? null); }, [mainId, data]);
  const sub = main?.subcategories.find(item => item.id === subId);
  const allSubs = data?.categories.flatMap(item => item.subcategories.map(child => ({ ...child, main: item.name }))) || [];
  const courseCount = allSubs.reduce((sum, item) => sum + item.courses.length, 0);

  async function run(action, success) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); await load(); setMessage(success); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  function submit(event, action, success) { event.preventDefault(); run(action, success); }
  function confirmDelete(label, action) { if (window.confirm(`Delete ${label}?`)) run(action, `${label} deleted.`); }

  return <div className="page">
    <div className="page-header simple-header"><div><div className="eyebrow">MAIN CRM ADMIN</div><h1>Settings</h1><p className="page-description">Edit the course names and subcategories used for learner uploads and Upsell recommendations.</p></div></div>
    <SettingsTabs />
    {error && <div className="form-error page-message">{error}</div>}{message && <div className="upload-message page-message">{message}</div>}
    {!data ? <div className="loading-state">Loading course mapping...</div> : <>
      <div className="section-heading"><h2>{data.categories.length} main categories · {allSubs.length} subcategories · {courseCount} courses</h2></div>
      <div className="course-mapping-layout">
        <aside className="course-category-panel">
          <form className="course-mapping-create" onSubmit={event => submit(event, async () => { const item = await createLearnerCourseCategory(mainName); setMainId(item.id); setMainName(""); }, "Main category added.")}><label>New main category</label><div><input value={mainName} onChange={event => setMainName(event.target.value)} /><button className="primary-button" disabled={busy || !mainName.trim()}>Add</button></div></form>
          <div className="course-category-list">{data.categories.map(item => <button type="button" key={item.id} className={item.id === mainId ? "course-category-item active" : "course-category-item"} onClick={() => { setMainId(item.id); setDraft(null); }}><span>{item.name}</span><strong>{item.subcategories.length}</strong></button>)}</div>
        </aside>
        <section className="course-mapping-main">{main ? <>
          <div className="course-category-edit"><strong>{main.name}</strong><button className="secondary-button" disabled={busy} onClick={() => { const name = window.prompt("Main category name", main.name); if (name?.trim()) run(() => updateLearnerCourseCategory(main.id, name), "Main category renamed."); }}>Rename</button><button className="secondary-button" disabled={busy || main.subcategories.length > 0} onClick={() => confirmDelete(`main category ${main.name}`, () => deleteLearnerCourseCategory(main.id))}>Delete empty</button></div>
          <form className="course-mapping-create" onSubmit={event => submit(event, async () => { const item = await createLearnerCourseSubcategory(subName, main.id); setSubId(item.id); setSubName(""); }, "Subcategory added.")}><label>New subcategory in {main.name}</label><div><input value={subName} onChange={event => setSubName(event.target.value)} /><button className="primary-button" disabled={busy || !subName.trim()}>Add</button></div></form>
          <div className="course-category-list">{main.subcategories.map(item => <button type="button" key={item.id} className={item.id === subId ? "course-category-item active" : "course-category-item"} onClick={() => { setSubId(item.id); setDraft(null); }}><span>{item.name}</span><strong>{item.courses.length}</strong></button>)}</div>
          {sub ? <>
            <div className="course-category-edit"><strong>{sub.name}</strong><button className="secondary-button" disabled={busy} onClick={() => { const name = window.prompt("Subcategory name", sub.name); if (name?.trim()) run(() => updateLearnerCourseSubcategory(sub.id, name, main.id), "Subcategory renamed."); }}>Rename</button><select aria-label="Move subcategory to main category" value={main.id} disabled={busy} onChange={event => run(() => updateLearnerCourseSubcategory(sub.id, sub.name, Number(event.target.value)), "Subcategory moved.")}>{data.categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="secondary-button" disabled={busy || sub.courses.length > 0} onClick={() => confirmDelete(`subcategory ${sub.name}`, () => deleteLearnerCourseSubcategory(sub.id))}>Delete empty</button></div>
            <form className="course-mapping-create" onSubmit={event => submit(event, async () => { await createLearnerCourse(courseName, sub.id); setCourseName(""); }, "Course mapped.")}><label htmlFor="new-mapped-course">New course in {sub.name}</label><div><input id="new-mapped-course" value={courseName} onChange={event => setCourseName(event.target.value)} placeholder="Name in upload file" /><button className="primary-button" disabled={busy || !courseName.trim()}>Add course</button></div></form>
            <div className="course-mapping-heading"><h3>{sub.courses.length} mapped courses</h3><input className="search-input" value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter courses" /></div>
            <div className="course-mapping-list">{sub.courses.filter(item => item.course_name.toLowerCase().includes(filter.toLowerCase())).map(item => draft?.id === item.id ? <form key={item.id} className="course-mapping-edit-row" onSubmit={event => submit(event, async () => { await updateLearnerCourse(item.id, draft.name, Number(draft.subId)); setDraft(null); }, "Course updated.")}><input aria-label="Course name" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /><select aria-label="Course subcategory" value={draft.subId} onChange={event => setDraft({ ...draft, subId: event.target.value })}>{allSubs.map(choice => <option key={choice.id} value={choice.id}>{choice.main} / {choice.name}</option>)}</select><button className="primary-button" disabled={busy || !draft.name.trim()}>Save</button><button type="button" onClick={() => setDraft(null)}>Cancel</button></form> : <div key={item.id} className="course-mapping-row"><span>{item.course_name}</span><button onClick={() => setDraft({ id: item.id, name: item.course_name, subId: String(sub.id) })}>Edit / move</button><button disabled={busy} onClick={() => confirmDelete(`course ${item.course_name}`, () => deleteLearnerCourse(item.id))}>Remove</button></div>)}</div>
          </> : <div className="empty-card">Add a subcategory to start mapping courses.</div>}
        </> : <div className="empty-card">Add a main category to start mapping courses.</div>}</section>
      </div>
      <section className="feature-card course-unmapped-section"><h2>{data.unmapped_courses.length} unmapped course names</h2><div className="course-mapping-list">{data.unmapped_courses.map(item => <div className="course-mapping-row" key={item.course_name}><span>{item.course_name}<small>{item.enrolments} enrolments</small></span><button disabled={!sub} onClick={() => { setCourseName(item.course_name); document.getElementById("new-mapped-course")?.focus(); }}>Use name</button></div>)}{!data.unmapped_courses.length && <div className="table-message">All enrolment courses are mapped.</div>}</div></section>
    </>}
  </div>;
}
