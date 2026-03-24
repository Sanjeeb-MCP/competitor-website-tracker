const PER_PAGE = 50;
const COLORS = ["#6366f1","#22c55e","#f97316","#3b82f6","#ef4444","#a855f7","#eab308","#06b6d4"];
let state = null;
let changes = [];
let filtered = [];
let currentPage = 1;
let fpFrom, fpTo;

async function loadData() {
  try {
    const [stateResp, changesResp] = await Promise.all([
      fetch("data/state.json"),
      fetch("data/changes.json"),
    ]);
    state = await stateResp.json();
    changes = await changesResp.json();
  } catch (e) {
    console.error("Failed to load data:", e);
    state = { competitors: {}, run_count: 0 };
    changes = [];
  }
  initDatePickers();
  renderAll();
}

function initDatePickers() {
  const opts = {
    dateFormat: "d M Y",
    theme: "dark",
    disableMobile: true,
    onChange: () => applyFilters(),
  };
  fpFrom = flatpickr("#date-from", { ...opts, defaultDate: new Date(Date.now() - 30*24*60*60*1000) });
  fpTo = flatpickr("#date-to", { ...opts, defaultDate: new Date() });
}

function renderAll() {
  document.getElementById("last-updated").textContent =
    "Last updated: " + (state.last_run ? formatDate(state.last_run) : "Never");
  renderGlobalStats();
  renderCompetitorCards();
  populateFilters();
  applyFilters();
  renderCharts();
}

// --- Tabs ---
document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", e => {
    e.preventDefault();
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    item.classList.add("active");
    const tab = item.dataset.tab;
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");
    document.getElementById("page-title").textContent =
      tab === "overview" ? "Overview" : tab === "changes" ? "Changes" : "Activity";
    // Show filters on overview and changes
    document.getElementById("filters-bar").style.display =
      (tab === "overview" || tab === "changes") ? "flex" : "none";
  });
});

function toggleSidebar() {
  document.querySelector(".sidebar").classList.toggle("open");
}

// --- Global Stats ---
function renderGlobalStats() {
  const c = state.competitors || {};
  const totalPages = Object.values(c).reduce((s, d) => s + (d.total_urls_discovered || 0), 0);
  const now = new Date();
  const weekAgo = new Date(now - 7*24*60*60*1000);
  const weekChanges = changes.filter(ch => new Date(ch.timestamp) >= weekAgo);
  const newPages = weekChanges.filter(ch => ch.change_type === "new_page").length;
  const updates = weekChanges.filter(ch => ch.change_type === "content_update").length;

  document.getElementById("global-stats").innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Competitors</div>
      <div class="stat-value">${Object.keys(c).length}</div>
      <div class="stat-sub">actively tracked</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Pages</div>
      <div class="stat-value">${totalPages.toLocaleString()}</div>
      <div class="stat-sub">across all sites</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">New Pages (7d)</div>
      <div class="stat-value">${newPages}</div>
      <div class="stat-sub">this week</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Content Updates (7d)</div>
      <div class="stat-value">${updates}</div>
      <div class="stat-sub">this week</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Changes</div>
      <div class="stat-value">${changes.length}</div>
      <div class="stat-sub">all time</div>
    </div>
  `;
}

// --- Competitor Cards ---
function renderCompetitorCards() {
  const container = document.getElementById("competitor-cards");
  const competitors = state.competitors || {};
  const now = new Date();
  const weekAgo = new Date(now - 7*24*60*60*1000);
  const maxPages = Math.max(...Object.values(competitors).map(d => d.total_urls_discovered || 0), 1);

  container.innerHTML = "";
  let i = 0;
  for (const [domain, data] of Object.entries(competitors)) {
    const dc = changes.filter(c => c.domain === domain);
    const wc = dc.filter(c => new Date(c.timestamp) >= weekAgo);
    const np = wc.filter(c => c.change_type === "new_page").length;
    const up = wc.filter(c => c.change_type === "content_update").length;
    const rd = wc.filter(c => c.change_type === "redirect").length;
    const pages = data.total_urls_discovered || Object.keys(data.pages || {}).length;
    const color = COLORS[i % COLORS.length];
    const pct = (pages / maxPages * 100).toFixed(0);

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <h3>${esc(data.name || domain)}</h3>
        <span class="card-domain">${esc(domain)}</span>
      </div>
      <div class="card-stats">
        <div class="card-row"><span class="label">Total pages</span><span class="val">${pages.toLocaleString()}</span></div>
        <div class="card-row"><span class="label">New (7d)</span><span class="val" style="color:var(--green)">${np}</span></div>
        <div class="card-row"><span class="label">Updates (7d)</span><span class="val" style="color:var(--yellow)">${up}</span></div>
        <div class="card-row"><span class="label">Redirects (7d)</span><span class="val" style="color:var(--orange)">${rd}</span></div>
        <div class="card-row"><span class="label">All-time changes</span><span class="val">${dc.length}</span></div>
      </div>
      <div class="card-bar"><div class="card-bar-fill" style="width:${pct}%;background:${color}"></div></div>
    `;
    container.appendChild(card);
    i++;
  }
  if (Object.keys(competitors).length === 0) {
    container.innerHTML = '<div class="empty-state">No data yet. Run the tracker to start monitoring.</div>';
  }
}

// --- Filters ---
function populateFilters() {
  const select = document.getElementById("filter-competitor");
  for (const [domain, data] of Object.entries(state.competitors || {})) {
    const opt = document.createElement("option");
    opt.value = domain;
    opt.textContent = data.name || domain;
    select.appendChild(opt);
  }
}

document.getElementById("filter-days").addEventListener("change", function() {
  const custom = this.value === "custom";
  document.getElementById("custom-from").style.display = custom ? "flex" : "none";
  document.getElementById("custom-to").style.display = custom ? "flex" : "none";
  if (!custom) applyFilters();
});
document.getElementById("filter-competitor").addEventListener("change", applyFilters);
document.getElementById("filter-type").addEventListener("change", applyFilters);

function applyFilters() {
  const competitor = document.getElementById("filter-competitor").value;
  const type = document.getElementById("filter-type").value;
  const daysVal = document.getElementById("filter-days").value;

  filtered = changes.filter(c => {
    if (competitor && c.domain !== competitor) return false;
    if (type && c.change_type !== type) return false;
    if (daysVal === "custom") {
      const ts = new Date(c.timestamp);
      const fromDates = fpFrom.selectedDates;
      const toDates = fpTo.selectedDates;
      if (fromDates.length && ts < fromDates[0]) return false;
      if (toDates.length) {
        const toEnd = new Date(toDates[0]);
        toEnd.setHours(23, 59, 59, 999);
        if (ts > toEnd) return false;
      }
    } else if (daysVal !== "0") {
      const days = parseInt(daysVal);
      const cutoff = new Date(Date.now() - days*24*60*60*1000);
      if (new Date(c.timestamp) < cutoff) return false;
    }
    return true;
  });

  currentPage = 1;
  renderTimeline();
  renderOverviewTimeline();
}

// --- Overview Timeline (top 10 recent) ---
function renderOverviewTimeline() {
  const container = document.getElementById("overview-timeline");
  const countEl = document.getElementById("overview-change-count");
  countEl.textContent = `(${filtered.length} total)`;

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No changes found for the selected filters.</div>';
    return;
  }
  container.innerHTML = filtered.slice(0, 10).map(renderChangeItem).join("");
}

// --- Changes Timeline ---
function renderTimeline() {
  const container = document.getElementById("timeline-list");
  document.getElementById("change-count").textContent = `(${filtered.length})`;

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No changes found for the selected filters.</div>';
    document.getElementById("pagination").innerHTML = "";
    return;
  }
  const start = (currentPage - 1) * PER_PAGE;
  container.innerHTML = filtered.slice(start, start + PER_PAGE).map(renderChangeItem).join("");
  renderPagination();
}

function renderChangeItem(c) {
  const badge = `<span class="badge badge-${c.change_type}">${formatType(c.change_type)}</span>`;
  const details = renderDetails(c);
  const hasDropdown = c.change_type === "content_update" && c.details &&
    ((c.details.added && c.details.added.length) || (c.details.removed && c.details.removed.length));

  let dropdown = "";
  if (hasDropdown) {
    dropdown = `
      <div class="dropdown-toggle" onclick="toggleDrop(this)">View content changes ▾</div>
      <div class="dropdown-content" style="display:none">${renderDiff(c.details)}</div>
    `;
  }

  let seoTags = "";
  const d = c.details || {};
  if (d.word_count) seoTags += `<span class="seo-tag tag-wc">${d.word_count.toLocaleString()} words</span> `;
  if (d.word_count_change) {
    const cls = d.word_count_change > 0 ? "tag-wc-up" : "tag-wc-down";
    const sign = d.word_count_change > 0 ? "+" : "";
    seoTags += `<span class="seo-tag ${cls}">${sign}${d.word_count_change} words</span> `;
  }
  if (d.h1) seoTags += `<span class="seo-tag tag-h1">H1: ${esc(d.h1.substring(0,50))}</span> `;
  if (d.schemas && d.schemas.length) seoTags += d.schemas.map(s => `<span class="seo-tag tag-schema">${esc(s)}</span>`).join(" ") + " ";
  if (d.added_schemas && d.added_schemas.length) seoTags += d.added_schemas.map(s => `<span class="seo-tag tag-schema">+${esc(s)}</span>`).join(" ") + " ";
  if (d.removed_schemas && d.removed_schemas.length) seoTags += d.removed_schemas.map(s => `<span class="seo-tag tag-noindex">-${esc(s)}</span>`).join(" ") + " ";

  return `
    <div class="change-item">
      <div class="change-header">
        ${badge}
        <span class="change-competitor">${esc(c.competitor)}</span>
        <span class="change-time">${formatDate(c.timestamp)}</span>
      </div>
      ${c.title ? `<div class="change-title">${esc(c.title)}</div>` : ""}
      <div class="change-url"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a></div>
      ${seoTags ? `<div style="margin-top:2px">${seoTags}</div>` : ""}
      ${details ? `<div class="change-details">${details}</div>` : ""}
      ${dropdown}
    </div>
  `;
}

function renderDiff(d) {
  let html = "";
  if (d.added && d.added.length) {
    html += '<div class="diff-section"><div class="diff-label diff-added-label">Added</div>';
    d.added.forEach(l => html += `<div class="diff-line diff-added">+ ${esc(l)}</div>`);
    html += "</div>";
  }
  if (d.removed && d.removed.length) {
    html += '<div class="diff-section"><div class="diff-label diff-removed-label">Removed</div>';
    d.removed.forEach(l => html += `<div class="diff-line diff-removed">- ${esc(l)}</div>`);
    html += "</div>";
  }
  return html || '<div class="diff-section">Minor text changes</div>';
}

function toggleDrop(el) {
  const c = el.nextElementSibling;
  c.style.display = c.style.display === "none" ? "block" : "none";
  el.textContent = c.style.display === "none" ? "View content changes ▾" : "Hide content changes ▴";
}

function renderDetails(c) {
  const d = c.details || {};
  const parts = [];
  if (d.summary && c.change_type === "new_page") parts.push(esc(d.summary));
  if (d.published_date) parts.push("Published: " + esc(d.published_date));
  if (d.diff_summary) parts.push(esc(d.diff_summary));
  if (d.old_title && d.new_title) parts.push(`"${esc(d.old_title)}" → "${esc(d.new_title)}"`);
  if (d.old_meta && d.new_meta) parts.push(`"${esc(d.old_meta)}" → "${esc(d.new_meta)}"`);
  if (d.old_h1 && d.new_h1) parts.push(`H1: "${esc(d.old_h1)}" → "${esc(d.new_h1)}"`);
  if (d.redirect) parts.push(`${d.redirect.status_code} → <a href="${esc(d.redirect.redirect_to)}" target="_blank">${esc(d.redirect.redirect_to)}</a>`);
  if (d.noindex) parts.push('<span class="seo-tag tag-noindex">noindex</span>');
  if (d.old_url && d.new_url) parts.push(`${esc(d.old_url)} → ${esc(d.new_url)}`);
  if (d.missing_runs && !d.redirect) parts.push(`Missing ${d.missing_runs} runs`);
  return parts.join(" &middot; ");
}

// --- Charts ---
function renderCharts() {
  renderBarChart("pub-chart", "new_page");
  renderBarChart("activity-chart", null);
}

function renderBarChart(containerId, filterType) {
  const container = document.getElementById(containerId);
  const competitors = Object.entries(state.competitors || {});
  if (!competitors.length || !changes.length) {
    container.innerHTML = '<div class="empty-state">Not enough data yet.</div>';
    return;
  }

  const weeks = {};
  const rel = filterType ? changes.filter(c => c.change_type === filterType) : changes;
  rel.forEach(c => {
    const d = new Date(c.timestamp);
    const ws = new Date(d); ws.setDate(d.getDate() - d.getDay());
    const key = ws.toISOString().slice(0, 10);
    if (!weeks[key]) weeks[key] = {};
    if (!weeks[key][c.domain]) weeks[key][c.domain] = 0;
    weeks[key][c.domain]++;
  });

  const sorted = Object.keys(weeks).sort().slice(-12);
  if (!sorted.length) {
    container.innerHTML = '<div class="empty-state">Not enough data yet.</div>';
    return;
  }

  const domains = competitors.map(([d]) => d);
  const maxVal = Math.max(...sorted.map(w => Math.max(...domains.map(d => weeks[w]?.[d] || 0), 0)), 1);

  let barsHtml = "";
  sorted.forEach(week => {
    let bars = "";
    domains.forEach((domain, i) => {
      const val = weeks[week]?.[domain] || 0;
      const h = (val / maxVal * 140);
      bars += `<div class="chart-bar" style="height:${h}px;background:${COLORS[i % COLORS.length]}" title="${competitors[i][1].name}: ${val}"></div>`;
    });
    const label = new Date(week).toLocaleDateString("en-US", {month:"short", day:"numeric"});
    barsHtml += `<div class="chart-bar-group">${bars}<span class="chart-bar-label">${label}</span></div>`;
  });

  let legend = '<div class="chart-legend">';
  competitors.forEach(([d, data], i) => {
    legend += `<div class="legend-item"><div class="legend-dot" style="background:${COLORS[i % COLORS.length]}"></div>${esc(data.name)}</div>`;
  });
  legend += '</div>';
  container.innerHTML = `<div class="chart">${barsHtml}</div>${legend}`;
}

// --- Excel Export ---
function exportExcel() {
  if (typeof XLSX === "undefined") { alert("Excel library loading..."); return; }
  const src = filtered.length ? filtered : changes;
  const rows = src.map(c => ({
    Date: c.timestamp,
    Competitor: c.competitor,
    Domain: c.domain,
    "Change Type": c.change_type,
    Title: c.title || "",
    URL: c.url,
    "Diff Summary": c.details?.diff_summary || "",
    "Old Title": c.details?.old_title || "",
    "New Title": c.details?.new_title || "",
    "Old Meta": c.details?.old_meta || "",
    "New Meta": c.details?.new_meta || "",
    "Old H1": c.details?.old_h1 || "",
    "New H1": c.details?.new_h1 || "",
    "Word Count": c.details?.new_word_count || c.details?.word_count || "",
    "Word Count Change": c.details?.word_count_change || "",
    "Schemas": (c.details?.schemas || c.details?.added_schemas || []).join(", "),
    "Redirect To": c.details?.redirect?.redirect_to || "",
    "Noindex": c.details?.noindex ? "Yes" : "",
    "Added Content": (c.details?.added || []).join(" | "),
    "Removed Content": (c.details?.removed || []).join(" | "),
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Changes");

  const summary = Object.entries(state.competitors || {}).map(([domain, data]) => {
    const dc = changes.filter(c => c.domain === domain);
    return {
      Competitor: data.name, Domain: domain,
      "Total Pages": data.total_urls_discovered || 0,
      "Total Changes": dc.length,
      "New Pages": dc.filter(c => c.change_type === "new_page").length,
      "Content Updates": dc.filter(c => c.change_type === "content_update").length,
      "Redirects": dc.filter(c => c.change_type === "redirect").length,
      "Removed": dc.filter(c => c.change_type === "page_removed").length,
    };
  });
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(summary), "Summary");
  XLSX.writeFile(wb, "competitor-tracker-export.xlsx");
}

// --- Pagination ---
function renderPagination() {
  const container = document.getElementById("pagination");
  const tp = Math.ceil(filtered.length / PER_PAGE);
  if (tp <= 1) { container.innerHTML = ""; return; }
  let h = `<button ${currentPage===1?"disabled":""} onclick="goToPage(${currentPage-1})">Prev</button>`;
  for (let i = Math.max(1,currentPage-2); i <= Math.min(tp,currentPage+2); i++)
    h += `<button class="${i===currentPage?"active":""}" onclick="goToPage(${i})">${i}</button>`;
  h += `<button ${currentPage===tp?"disabled":""} onclick="goToPage(${currentPage+1})">Next</button>`;
  container.innerHTML = h;
}
function goToPage(p) { currentPage=p; renderTimeline(); window.scrollTo({top:0,behavior:"smooth"}); }

// --- Helpers ---
function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {month:"short",day:"numeric",year:"numeric",hour:"2-digit",minute:"2-digit"});
}
function formatType(t) { return t.replace(/_/g," "); }
function esc(s) { if (!s) return ""; const d=document.createElement("div"); d.textContent=s; return d.innerHTML; }

loadData();
