const PER_PAGE = 50;
const COLORS = ["#00ff88","#00aaff","#ff8800","#ffff00","#ff3333","#cc66ff","#00ffcc","#88ff00"];
let state = null;
let changes = [];
let filteredOverview = [];
let filteredChanges = [];
let currentPage = 1;
let fpFrom, fpTo, fpFromC, fpToC;

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
  const opts = { dateFormat: "d M Y", theme: "dark", disableMobile: true };
  fpFrom = flatpickr("#date-from", { ...opts, onChange: () => applyOverviewFilters() });
  fpTo = flatpickr("#date-to", { ...opts, onChange: () => applyOverviewFilters() });
  fpFromC = flatpickr("#date-from-changes", { ...opts, onChange: () => applyChangesFilters() });
  fpToC = flatpickr("#date-to-changes", { ...opts, onChange: () => applyChangesFilters() });
}

function renderAll() {
  document.getElementById("last-updated").textContent =
    "Last sync: " + (state.last_run ? formatDate(state.last_run) : "—");
  renderGlobalStats();
  renderCompetitorCards();
  populateFilters();
  applyOverviewFilters();
  applyChangesFilters();
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
    document.getElementById("overview-filters").style.display = tab === "overview" ? "flex" : "none";
    document.getElementById("changes-filters").style.display = tab === "changes" ? "flex" : "none";
    // Close sidebar on mobile after selecting a tab
    closeSidebar();
  });
});

function toggleSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  const isOpen = sidebar.classList.contains("open");
  if (isOpen) {
    closeSidebar();
  } else {
    sidebar.classList.add("open");
    overlay.classList.add("active");
  }
}

function closeSidebar() {
  document.querySelector(".sidebar").classList.remove("open");
  document.getElementById("sidebar-overlay").classList.remove("active");
}

// --- Global Stats ---
function renderGlobalStats() {
  const c = state.competitors || {};
  const totalPages = Object.values(c).reduce((s, d) => s + (d.total_urls_discovered || 0), 0);
  const now = new Date();
  const weekAgo = new Date(now - 7*24*60*60*1000);
  const wc = changes.filter(ch => new Date(ch.timestamp) >= weekAgo);

  document.getElementById("global-stats").innerHTML = `
    <div class="stat-card"><div class="stat-label">Competitors</div><div class="stat-value">${Object.keys(c).length}</div><div class="stat-sub">actively tracked</div></div>
    <div class="stat-card"><div class="stat-label">Pages Indexed</div><div class="stat-value">${totalPages.toLocaleString()}</div><div class="stat-sub">total discovered</div></div>
    <div class="stat-card"><div class="stat-label">New Pages (7d)</div><div class="stat-value">${wc.filter(ch=>ch.change_type==="new_page").length}</div><div class="stat-sub">this week</div></div>
    <div class="stat-card"><div class="stat-label">Content Updates (7d)</div><div class="stat-value">${wc.filter(ch=>ch.change_type==="content_update").length}</div><div class="stat-sub">this week</div></div>
    <div class="stat-card"><div class="stat-label">Total Changes</div><div class="stat-value">${changes.length}</div><div class="stat-sub">all time</div></div>
  `;
}

// --- Cards ---
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
    const pages = data.total_urls_discovered || Object.keys(data.pages || {}).length;
    const color = COLORS[i % COLORS.length];

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <h3>${esc(data.name || domain)}</h3>
        <span class="card-domain">${esc(domain)}</span>
      </div>
      <div class="card-stats">
        <div class="card-row"><span class="label">Pages</span><span class="val">${pages.toLocaleString()}</span></div>
        <div class="card-row"><span class="label">New (7d)</span><span class="val" style="color:var(--green)">${wc.filter(c=>c.change_type==="new_page").length}</span></div>
        <div class="card-row"><span class="label">Updates (7d)</span><span class="val" style="color:var(--yellow)">${wc.filter(c=>c.change_type==="content_update").length}</span></div>
        <div class="card-row"><span class="label">Total events</span><span class="val">${dc.length}</span></div>
      </div>
      <div class="card-bar"><div class="card-bar-fill" style="width:${(pages/maxPages*100).toFixed(0)}%;background:${color}"></div></div>
    `;
    container.appendChild(card);
    i++;
  }
  if (!Object.keys(competitors).length) {
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

// Overview: time range only
document.getElementById("filter-days").addEventListener("change", function() {
  const custom = this.value === "custom";
  document.getElementById("custom-from").style.display = custom ? "flex" : "none";
  document.getElementById("custom-to").style.display = custom ? "flex" : "none";
  if (!custom) applyOverviewFilters();
});

function applyOverviewFilters() {
  filteredOverview = filterByTime(changes, "filter-days", fpFrom, fpTo);
  renderOverviewTimeline();
}

// Changes: all filters
document.getElementById("filter-competitor").addEventListener("change", applyChangesFilters);
document.getElementById("filter-type").addEventListener("change", applyChangesFilters);
document.getElementById("filter-days-changes").addEventListener("change", function() {
  const custom = this.value === "custom";
  document.getElementById("custom-from-changes").style.display = custom ? "flex" : "none";
  document.getElementById("custom-to-changes").style.display = custom ? "flex" : "none";
  if (!custom) applyChangesFilters();
});

function applyChangesFilters() {
  const competitor = document.getElementById("filter-competitor").value;
  const type = document.getElementById("filter-type").value;

  filteredChanges = filterByTime(changes, "filter-days-changes", fpFromC, fpToC);
  if (competitor) filteredChanges = filteredChanges.filter(c => c.domain === competitor);
  if (type) filteredChanges = filteredChanges.filter(c => c.change_type === type);

  currentPage = 1;
  renderTimeline();
}

function filterByTime(src, selectId, fpFromRef, fpToRef) {
  const val = document.getElementById(selectId).value;
  return src.filter(c => {
    const ts = new Date(c.timestamp);
    if (val === "custom") {
      if (fpFromRef?.selectedDates?.length && ts < fpFromRef.selectedDates[0]) return false;
      if (fpToRef?.selectedDates?.length) {
        const end = new Date(fpToRef.selectedDates[0]); end.setHours(23,59,59,999);
        if (ts > end) return false;
      }
    } else if (val !== "0") {
      if (ts < new Date(Date.now() - parseInt(val)*24*60*60*1000)) return false;
    }
    return true;
  });
}

// --- Overview Timeline ---
function renderOverviewTimeline() {
  const container = document.getElementById("overview-timeline");
  document.getElementById("overview-change-count").textContent = `(${filteredOverview.length} total)`;
  if (!filteredOverview.length) {
    container.innerHTML = '<div class="empty-state">No changes found for the selected time range.</div>';
    return;
  }
  container.innerHTML = filteredOverview.slice(0, 10).map(renderChangeItem).join("");
}

// --- Changes Timeline ---
function renderTimeline() {
  const container = document.getElementById("timeline-list");
  document.getElementById("change-count").textContent = `(${filteredChanges.length})`;
  if (!filteredChanges.length) {
    container.innerHTML = '<div class="empty-state">No changes match the selected filters.</div>';
    document.getElementById("pagination").innerHTML = "";
    return;
  }
  const start = (currentPage - 1) * PER_PAGE;
  container.innerHTML = filteredChanges.slice(start, start + PER_PAGE).map(renderChangeItem).join("");
  renderPagination();
}

function renderChangeItem(c) {
  const badge = `<span class="badge badge-${c.change_type}">${formatType(c.change_type)}</span>`;
  const details = renderDetails(c);
  // Always show dropdown for content_update
  let dropdown = "";
  if (c.change_type === "content_update" && c.details) {
    dropdown = `<div class="dropdown-toggle" onclick="toggleDrop(this)">View content changes ▾</div>
      <div class="dropdown-content" style="display:none">${renderDiff(c.details)}</div>`;
  }
  let seoTags = "";
  const d = c.details || {};
  if (d.word_count) seoTags += `<span class="seo-tag tag-wc">${d.word_count.toLocaleString()} words</span> `;
  if (d.word_count_change) {
    const cls = d.word_count_change > 0 ? "tag-wc-up" : "tag-wc-down";
    seoTags += `<span class="seo-tag ${cls}">${d.word_count_change>0?"+":""}${d.word_count_change} words</span> `;
  }
  if (d.h1) seoTags += `<span class="seo-tag tag-h1">H1: ${esc(d.h1.substring(0,50))}</span> `;
  if (d.schemas?.length) seoTags += d.schemas.map(s=>`<span class="seo-tag tag-schema">${esc(s)}</span>`).join(" ")+" ";
  if (d.added_schemas?.length) seoTags += d.added_schemas.map(s=>`<span class="seo-tag tag-schema">+${esc(s)}</span>`).join(" ")+" ";
  if (d.removed_schemas?.length) seoTags += d.removed_schemas.map(s=>`<span class="seo-tag tag-noindex">-${esc(s)}</span>`).join(" ")+" ";

  return `<div class="change-item">
    <div class="change-header">${badge}<span class="change-competitor">${esc(c.competitor)}</span><span class="change-time">${formatDate(c.timestamp)}</span></div>
    ${c.title?`<div class="change-title">${esc(c.title)}</div>`:""}
    <div class="change-url"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a></div>
    ${seoTags?`<div style="margin-top:2px">${seoTags}</div>`:""}
    ${details?`<div class="change-details">${details}</div>`:""}
    ${dropdown}
  </div>`;
}

function renderDiff(d) {
  let h = "";
  if (d.added?.length) {
    h += '<div class="diff-section"><div class="diff-label diff-added-label">+ ADDED</div>';
    d.added.forEach(l => h += `<div class="diff-line diff-added">+ ${esc(l)}</div>`);
    h += "</div>";
  }
  if (d.removed?.length) {
    h += '<div class="diff-section"><div class="diff-label diff-removed-label">- REMOVED</div>';
    d.removed.forEach(l => h += `<div class="diff-line diff-removed">- ${esc(l)}</div>`);
    h += "</div>";
  }
  if (!h) {
    // No diff data yet — show what we know
    let info = '<div class="diff-section">';
    if (d.diff_summary) {
      info += `<div class="diff-line" style="border-left:3px solid var(--yellow);color:var(--yellow);padding:4px 8px">${esc(d.diff_summary)}</div>`;
    }
    if (d.old_hash && d.new_hash) {
      info += `<div style="font-size:0.7rem;color:var(--text-muted);margin-top:6px;font-family:var(--mono-font)">Hash changed: ${esc(d.old_hash)} → ${esc(d.new_hash)}</div>`;
    }
    if (d.word_count_change) {
      const sign = d.word_count_change > 0 ? "+" : "";
      info += `<div style="font-size:0.7rem;color:var(--text-muted);margin-top:4px">Word count: ${d.old_word_count || "?"} → ${d.new_word_count || "?"} (${sign}${d.word_count_change})</div>`;
    }
    if (!d.diff_summary && !d.old_hash) {
      info += '<div style="color:var(--text-muted)">Content diff will be available after the next crawl cycle.</div>';
    }
    info += "</div>";
    h = info;
  }
  return h;
}

function toggleDrop(el) {
  const c = el.nextElementSibling;
  c.style.display = c.style.display === "none" ? "block" : "none";
  el.textContent = c.style.display === "none" ? "View content changes ▾" : "Hide content changes ▴";
}

function renderDetails(c) {
  const d = c.details || {};
  const p = [];
  if (d.summary && c.change_type === "new_page") p.push(esc(d.summary));
  if (d.published_date) p.push("Published: " + esc(d.published_date));
  if (d.diff_summary) p.push(esc(d.diff_summary));
  if (d.old_title && d.new_title) p.push(`"${esc(d.old_title)}" → "${esc(d.new_title)}"`);
  if (d.old_meta && d.new_meta) p.push(`"${esc(d.old_meta)}" → "${esc(d.new_meta)}"`);
  if (d.old_h1 && d.new_h1) p.push(`H1: "${esc(d.old_h1)}" → "${esc(d.new_h1)}"`);
  if (d.redirect) p.push(`${d.redirect.status_code} → <a href="${esc(d.redirect.redirect_to)}" target="_blank">${esc(d.redirect.redirect_to)}</a>`);
  if (d.noindex) p.push('<span class="seo-tag tag-noindex">NOINDEX</span>');
  if (d.old_url && d.new_url) p.push(`${esc(d.old_url)} → ${esc(d.new_url)}`);
  if (d.missing_runs && !d.redirect) p.push(`Missing ${d.missing_runs} runs`);
  return p.join(" &middot; ");
}

// --- Charts ---
function renderCharts() {
  renderBarChart("pub-chart", "new_page");
  renderBarChart("activity-chart", null);
}

function renderBarChart(containerId, filterType) {
  const container = document.getElementById(containerId);
  const competitors = Object.entries(state.competitors || {});
  if (!competitors.length || !changes.length) { container.innerHTML = '<div class="empty-state">Not enough data yet. Charts will populate after more crawl cycles.</div>'; return; }
  const weeks = {};
  const rel = filterType ? changes.filter(c=>c.change_type===filterType) : changes;
  rel.forEach(c => {
    const d = new Date(c.timestamp); const ws = new Date(d); ws.setDate(d.getDate()-d.getDay());
    const key = ws.toISOString().slice(0,10);
    if (!weeks[key]) weeks[key] = {};
    weeks[key][c.domain] = (weeks[key][c.domain]||0) + 1;
  });
  const sorted = Object.keys(weeks).sort().slice(-12);
  if (!sorted.length) { container.innerHTML = '<div class="empty-state">Not enough data yet. Charts will populate after more crawl cycles.</div>'; return; }
  const domains = competitors.map(([d])=>d);
  const maxVal = Math.max(...sorted.map(w=>Math.max(...domains.map(d=>weeks[w]?.[d]||0))),1);

  let barsHtml = "";
  sorted.forEach(week => {
    let bars = "";
    domains.forEach((domain,i) => {
      const val = weeks[week]?.[domain]||0;
      bars += `<div class="chart-bar" style="height:${val/maxVal*140}px;background:${COLORS[i%COLORS.length]}" title="${competitors[i][1].name}: ${val}"></div>`;
    });
    barsHtml += `<div class="chart-bar-group">${bars}<span class="chart-bar-label">${new Date(week).toLocaleDateString("en-US",{month:"short",day:"numeric"})}</span></div>`;
  });
  let legend = '<div class="chart-legend">';
  competitors.forEach(([d,data],i) => legend += `<div class="legend-item"><div class="legend-dot" style="background:${COLORS[i%COLORS.length]}"></div>${esc(data.name)}</div>`);
  container.innerHTML = `<div class="chart">${barsHtml}</div>${legend}</div>`;
}

// --- Excel Export ---
function exportExcel() {
  if (typeof XLSX === "undefined") { alert("Loading..."); return; }
  // Use whichever tab is active
  const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab;
  const src = activeTab === "changes" ? filteredChanges : filteredOverview;
  const rows = src.map(c => ({
    Date: c.timestamp, Competitor: c.competitor, Domain: c.domain,
    "Change Type": c.change_type, Title: c.title||"", URL: c.url,
    "Diff Summary": c.details?.diff_summary||"",
    "Old Title": c.details?.old_title||"", "New Title": c.details?.new_title||"",
    "Old Meta": c.details?.old_meta||"", "New Meta": c.details?.new_meta||"",
    "Old H1": c.details?.old_h1||"", "New H1": c.details?.new_h1||"",
    "Word Count": c.details?.new_word_count||c.details?.word_count||"",
    "Word Count Change": c.details?.word_count_change||"",
    "Schemas": (c.details?.schemas||c.details?.added_schemas||[]).join(", "),
    "Redirect To": c.details?.redirect?.redirect_to||"",
    "Noindex": c.details?.noindex?"Yes":"",
    "Added Content": (c.details?.added||[]).join(" | "),
    "Removed Content": (c.details?.removed||[]).join(" | "),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), "Changes");
  const summary = Object.entries(state.competitors||{}).map(([domain,data])=>{
    const dc = changes.filter(c=>c.domain===domain);
    return { Competitor:data.name, Domain:domain, "Total Pages":data.total_urls_discovered||0,
      "Total Changes":dc.length, "New Pages":dc.filter(c=>c.change_type==="new_page").length,
      "Content Updates":dc.filter(c=>c.change_type==="content_update").length,
      Redirects:dc.filter(c=>c.change_type==="redirect").length,
      Removed:dc.filter(c=>c.change_type==="page_removed").length };
  });
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(summary), "Summary");
  XLSX.writeFile(wb, "competitor-tracker-export.xlsx");
}

// --- Pagination ---
function renderPagination() {
  const el = document.getElementById("pagination");
  const tp = Math.ceil(filteredChanges.length/PER_PAGE);
  if (tp<=1) { el.innerHTML=""; return; }
  let h = `<button ${currentPage===1?"disabled":""} onclick="goToPage(${currentPage-1})">Prev</button>`;
  for (let i=Math.max(1,currentPage-2);i<=Math.min(tp,currentPage+2);i++)
    h+=`<button class="${i===currentPage?"active":""}" onclick="goToPage(${i})">${i}</button>`;
  h+=`<button ${currentPage===tp?"disabled":""} onclick="goToPage(${currentPage+1})">Next</button>`;
  el.innerHTML=h;
}
function goToPage(p){currentPage=p;renderTimeline();window.scrollTo({top:0,behavior:"smooth"});}

// --- Helpers ---
function formatDate(iso){if(!iso)return"---";return new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",hour:"2-digit",minute:"2-digit"});}
function formatType(t){return t.replace(/_/g," ");}
function esc(s){if(!s)return"";const d=document.createElement("div");d.textContent=s;return d.innerHTML;}

loadData();
