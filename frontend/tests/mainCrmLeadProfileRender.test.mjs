import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { MainCrmLeadContent, EditHistory } = await server.ssrLoadModule("/src/pages/MainCrmLeadDetailPage.jsx");
  const activity = {
    id: 1, activity_type: "EDIT", activity_date: "2026-09-28", created_at: "2026-09-28T12:00:00",
    notes: "Lead information updated", raw_data: { changes: { email: { from: "old@example.com", to: "new@example.com" } }, edited_by: { id: 1, name: "Admin" } },
  };
  const data = {
    lead: { id: 136894, full_name: "Example Learner", email: "new@example.com", status_of_lead: "NEW", source: "Website" },
    activities: [], changes: [activity], lifecycle: { events: [] },
  };
  const html = renderToString(React.createElement(MemoryRouter, null, React.createElement(MainCrmLeadContent, { data })));
  assert.match(html, /Example Learner/);
  assert.match(html, /Show edit history/);
  assert.match(html, /Lead activity/);
  assert.match(html, /new@example.com/);
  assert.doesNotMatch(html, /Information edited by/);
  const failedWrite = renderToString(React.createElement(MemoryRouter, null,
    React.createElement(MainCrmLeadContent, { data, error: "Could not save the note" })));
  assert.match(failedWrite, /Example Learner/);
  assert.match(failedWrite, /Could not save the note/);
  const history = renderToString(React.createElement(EditHistory, { changes: [activity] }));
  assert.match(history, /Information edited by .*Admin/);
  assert.match(history, /old@example.com/);
  assert.match(history, /new@example.com/);
  console.log("Main CRM lead profile keeps field edits in expandable history with actor and before/after values.");
} finally {
  await server.close();
}
