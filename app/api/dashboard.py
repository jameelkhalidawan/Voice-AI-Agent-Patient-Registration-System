"""Read-only HTML dashboard for the patient intake demo."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f3f6fb">
  <title>Care Cloud · Patient dashboard</title>
  <style>
    :root {
      color-scheme: light dark;
      --page: #f3f6fb;
      --surface: #ffffff;
      --text: #172033;
      --muted: #5d687b;
      --border: #dce3ee;
      --accent: #155eef;
      --accent-hover: #004eeb;
      --banner: #fff7db;
      --banner-border: #f1d477;
      --error-bg: #fff0f0;
      --error-text: #9b1c1c;
      --shadow: 0 12px 32px rgb(29 50 84 / 8%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--page);
      color: var(--text);
    }
    .shell { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 36px 0 48px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark {
      display: grid; place-items: center; width: 42px; height: 42px; border-radius: 13px;
      background: #e8efff; color: var(--accent); font-weight: 800; font-size: 20px;
    }
    h1 { margin: 0; font-size: clamp(1.35rem, 3vw, 1.8rem); letter-spacing: -0.035em; }
    .subtitle { margin: 4px 0 0; color: var(--muted); font-size: .92rem; }
    .docs-link { color: var(--accent); font-weight: 650; text-decoration: none; white-space: nowrap; }
    .docs-link:hover { text-decoration: underline; }
    .banner {
      margin: 0 0 20px; padding: 12px 16px; border: 1px solid var(--banner-border);
      border-radius: 12px; background: var(--banner); color: #59440a; font-size: .94rem;
    }
    .panel {
      overflow: hidden; border: 1px solid var(--border); border-radius: 18px;
      background: var(--surface); box-shadow: var(--shadow);
    }
    .panel-head {
      display: flex; align-items: center; justify-content: space-between; gap: 18px;
      padding: 20px 22px; border-bottom: 1px solid var(--border);
    }
    .count { margin: 0; color: var(--muted); font-size: .92rem; }
    .controls { display: flex; align-items: center; gap: 10px; }
    .search {
      width: min(310px, 42vw); min-height: 42px; padding: 9px 12px; border: 1px solid var(--border);
      border-radius: 10px; background: var(--surface); color: var(--text); font: inherit;
    }
    .search:focus-visible, .refresh:focus-visible, .docs-link:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--accent) 32%, transparent); outline-offset: 2px;
    }
    .refresh {
      min-height: 42px; padding: 9px 14px; border: 0; border-radius: 10px;
      background: var(--accent); color: #fff; font: inherit; font-weight: 650; cursor: pointer;
    }
    .refresh:hover { background: var(--accent-hover); }
    .refresh:disabled { opacity: .65; cursor: wait; }
    .sr-only {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
    }
    .content { padding: 0 22px 22px; }
    .message { margin: 22px 0 0; padding: 22px; border-radius: 12px; color: var(--muted); text-align: center; }
    .error { background: var(--error-bg); color: var(--error-text); text-align: left; }
    .table-wrap { overflow-x: auto; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th { padding: 15px 12px; color: var(--muted); font-size: .76rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    td { padding: 16px 12px; border-top: 1px solid var(--border); vertical-align: top; font-size: .93rem; }
    tbody tr:hover { background: color-mix(in srgb, var(--accent) 4%, var(--surface)); }
    .patient-name { font-weight: 650; }
    .muted { color: var(--muted); }
    [hidden] { display: none !important; }
    @media (max-width: 720px) {
      .shell { width: min(100% - 22px, 600px); padding-top: 22px; }
      .topbar { align-items: flex-start; }
      .panel-head { align-items: stretch; flex-direction: column; padding: 17px; }
      .controls { width: 100%; }
      .search { width: 100%; min-width: 0; }
      .refresh { flex: 0 0 auto; }
      .content { padding: 0 15px 17px; }
      .table-wrap { overflow: visible; }
      table, tbody, tr, td { display: block; width: 100%; }
      thead { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
      tbody { display: grid; gap: 12px; padding-top: 14px; }
      tbody tr { overflow: hidden; border: 1px solid var(--border); border-radius: 12px; }
      td { display: grid; grid-template-columns: minmax(112px, 38%) minmax(0, 1fr); gap: 10px; padding: 11px 12px; border-top: 1px solid var(--border); overflow-wrap: anywhere; }
      td:first-child { border-top: 0; }
      td::before { content: attr(data-label); color: var(--muted); font-size: .78rem; font-weight: 700; }
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --page: #101725; --surface: #182235; --text: #eef3fb; --muted: #a7b3c7;
        --border: #2d3b52; --accent: #80aaff; --accent-hover: #9bbcff;
        --banner: #342c18; --banner-border: #625323; --error-bg: #3b2025; --error-text: #ffb8c0;
        --shadow: 0 12px 32px rgb(0 0 0 / 18%);
      }
      .brand-mark { background: #26385e; }
      .banner { color: #f4dda0; }
      .refresh { color: #101725; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">C</div>
        <div>
          <h1>Patient dashboard</h1>
          <p class="subtitle">Care Cloud · Registration overview</p>
        </div>
      </div>
      <a class="docs-link" href="/docs">API docs <span aria-hidden="true">↗</span></a>
    </header>

    <p class="banner">Demo data only. Do not enter real patient information.</p>

    <section class="panel" aria-label="Registered patients">
      <div class="panel-head">
        <p id="patient-count" class="count" aria-live="polite">Loading patients…</p>
        <div class="controls">
          <label class="sr-only" for="search">Search by name or last four phone digits</label>
          <input id="search" class="search" type="search" placeholder="Search name or last 4 digits" autocomplete="off">
          <button id="refresh" class="refresh" type="button">Refresh</button>
        </div>
      </div>
      <div class="content">
        <p id="loading-state" class="message" role="status">Loading patients…</p>
        <p id="empty-state" class="message" hidden>No patients registered yet</p>
        <div id="error-state" class="message error" role="alert" hidden></div>
        <p id="no-matches-state" class="message" hidden>No patients match your search.</p>
        <div id="table-wrap" class="table-wrap" hidden>
          <table>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Date of birth</th>
                <th scope="col">Phone</th>
                <th scope="col">City / state</th>
                <th scope="col">Preferred language</th>
                <th scope="col">Registered</th>
              </tr>
            </thead>
            <tbody id="patient-rows"></tbody>
          </table>
        </div>
      </div>
    </section>
  </main>

  <script>
    "use strict";
    const countNode = document.getElementById("patient-count");
    const searchNode = document.getElementById("search");
    const refreshButton = document.getElementById("refresh");
    const loadingNode = document.getElementById("loading-state");
    const emptyNode = document.getElementById("empty-state");
    const errorNode = document.getElementById("error-state");
    const noMatchesNode = document.getElementById("no-matches-state");
    const tableWrap = document.getElementById("table-wrap");
    const rowsNode = document.getElementById("patient-rows");
    let patients = [];

    function text(value) {
      return value === null || value === undefined ? "—" : String(value);
    }

    function maskPhone(value) {
      const digits = String(value ?? "").replace(/\D/g, "");
      const lastFour = digits.slice(-4).padStart(4, "•");
      return `•••-•••-${lastFour}`;
    }

    function formatDob(value) {
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? ""));
      if (!match) return text(value);
      const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
      if (Number.isNaN(date.getTime())) return text(value);
      return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
    }

    function formatLocalTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "—";
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
    }

    function appendCell(row, label, value, className = "") {
      const cell = document.createElement("td");
      cell.dataset.label = label;
      if (className) cell.className = className;
      cell.textContent = value;
      row.appendChild(cell);
    }

    function filteredPatients() {
      const query = searchNode.value.trim().toLocaleLowerCase();
      if (!query) return patients;
      const digits = query.replace(/\D/g, "");
      return patients.filter((patient) => {
        const name = `${text(patient.first_name)} ${text(patient.last_name)}`.toLocaleLowerCase();
        const lastFour = String(patient.phone_number ?? "").replace(/\D/g, "").slice(-4);
        return name.includes(query) || (digits.length > 0 && lastFour.includes(digits));
      });
    }

    function renderRows() {
      const visiblePatients = filteredPatients();
      rowsNode.replaceChildren();
      for (const patient of visiblePatients) {
        const row = document.createElement("tr");
        const fullName = `${text(patient.first_name)} ${text(patient.last_name)}`.trim();
        const location = [patient.city, patient.state]
          .filter((part) => part !== null && part !== undefined && String(part).trim() !== "")
          .map((part) => String(part))
          .join(", ") || "—";
        appendCell(row, "Name", fullName || "—", "patient-name");
        appendCell(row, "Date of birth", formatDob(patient.date_of_birth));
        appendCell(row, "Phone", maskPhone(patient.phone_number));
        appendCell(row, "City / state", location);
        appendCell(row, "Preferred language", text(patient.preferred_language));
        appendCell(row, "Registered", formatLocalTime(patient.created_at));
        rowsNode.appendChild(row);
      }
      countNode.textContent = searchNode.value.trim()
        ? `${visiblePatients.length} of ${patients.length} patients`
        : `${patients.length} ${patients.length === 1 ? "patient" : "patients"}`;
      tableWrap.hidden = visiblePatients.length === 0;
      noMatchesNode.hidden = patients.length === 0 || visiblePatients.length !== 0;
    }

    async function loadPatients() {
      refreshButton.disabled = true;
      loadingNode.hidden = false;
      errorNode.hidden = true;
      emptyNode.hidden = true;
      noMatchesNode.hidden = true;
      tableWrap.hidden = true;
      rowsNode.replaceChildren();
      countNode.textContent = "Loading patients…";
      try {
        const response = await fetch("/patients", {
          method: "GET",
          headers: { "Accept": "application/json" },
          cache: "no-store"
        });
        let envelope;
        try {
          envelope = await response.json();
        } catch (_) {
          throw new Error(`The patient API returned an unreadable response (HTTP ${response.status}).`);
        }
        if (!response.ok || envelope.error) {
          const message = envelope.error && typeof envelope.error.message === "string"
            ? envelope.error.message
            : `Could not load patients (HTTP ${response.status}).`;
          throw new Error(message);
        }
        if (!Array.isArray(envelope.data)) {
          throw new Error("The patient API response did not contain a patient list.");
        }
        patients = envelope.data;
        loadingNode.hidden = true;
        if (patients.length === 0) {
          countNode.textContent = "0 patients";
          emptyNode.hidden = false;
          return;
        }
        renderRows();
      } catch (error) {
        patients = [];
        countNode.textContent = "Patients unavailable";
        loadingNode.hidden = true;
        errorNode.textContent = error instanceof Error
          ? `Unable to load patients. ${error.message}`
          : "Unable to load patients. Please try again.";
        errorNode.hidden = false;
      } finally {
        refreshButton.disabled = false;
      }
    }

    searchNode.addEventListener("input", renderRows);
    refreshButton.addEventListener("click", loadPatients);
    loadPatients();
  </script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def get_dashboard() -> HTMLResponse:
    """Serve the self-contained read-only patient dashboard."""

    return HTMLResponse(content=DASHBOARD_HTML)
