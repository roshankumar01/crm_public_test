import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { Overview, Sales, Dinesh } = await server.ssrLoadModule("/src/pages/CompanyDashboardPage.jsx");
  const overview = renderToString(React.createElement(Overview, { data: {
    cards: { new_leads: 12, converted_leads: 4, total_leads: 20, upsell_total: 8, upsell_converted: 2, upsell_conversion_rate: 25 },
    trend: [{ label: "2026-09-01", leads: 10, converted: 3 }, { label: "2026-09-02", leads: 10, converted: 1 }],
    top_sources: [{ name: "Website", count: 9 }], top_converted_courses: [{ name: "IGC", count: 3 }],
  } }));
  assert.match(overview, /Top 7 lead sources/);
  assert.match(overview, /Website/);
  const sales = renderToString(React.createElement(Sales, { data: {
    cards: { converted: 3, leads: 12, conversion_rate: 25, unassigned: 1 },
    counselors: [{ id: 1, name: "Alex", leads: 12, converted: 3 }],
    decomposition: [{ id: 1, name: "Alex", count: 3 }],
  } }));
  assert.match(sales, /Counselor comparison/);
  assert.match(sales, /All conversions/);
  assert.match(sales, /Alex/);
  const dinesh = renderToString(React.createElement(Dinesh, { data: {
    cards: { learners: 2, result_rows: 4, igc_pass_rate: 50, idip_three_units_passed: 0 },
    igc: { learners: 2, pass: 1, fail: 1, pending: 0 },
    idip_units: [{ code: "ID1", learners: 1, pass: 1, fail: 0, pending: 0, pass_rate: 100 }],
    idip_progression: { one_unit: 1, two_units: 0, three_units: 0 },
  } }));
  assert.match(dinesh, /Latest IGC result/);
  assert.match(dinesh, /ID1/);
  console.log("Company dashboard Overview, Sales, and Dinesh pages render their charts and breakdowns.");
} finally {
  await server.close();
}
