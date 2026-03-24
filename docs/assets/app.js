const PER_PAGE = 50;
let state = null;
let changes = [];
let filtered = [];
let currentPage = 1;

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

  renderHeader();
  renderCompetitorCards();
  populateFilters();
  applyFilters();
}

function renderHeader() {
  const competitorCount = Object.keys(state.competitors || {}).length;
  document.getElementById("last-updated").textContent =
    "Last updated: " + (state.last_run ? formatDate(state.last_run) : "Never");
  document.getElementById("total-competitors").textContent =
    "Competitors: " + competitorCount;
  document.getElementById("total-changes").textContent =
    "Total changes: " + changes.length;
}

function renderCompetitorCards() {
  const container = document.getElementById("competitor-cards");
  const competitors = state.competitors || {};
  const now = new Date();
  const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);

  container.innerHTML = "";

  for (const [domain, data] of Object.entries(competitors)) {
    const domainChanges = changes.filter((c) => c.domain === domain);
    const weekChanges = domainChanges.filter(
      (c) => new Date(c.timestamp) >= weekAgo
    );
    const newPages = weekChanges.filter((c) => c.change_type === "new_page").length;
    const updates = weekChanges.filter(
      (c) => c.change_type === "content_update"
    ).length;

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${escapeHtml(data.name || domain)}</h3>
      <div class="card-stat"><span>Total pages</span><span class="value">${data.total_urls_discovered || Object.keys(data.pages || {}).length}</span></div>
      <div class="card-stat"><span>New this week</span><span class="value">${newPages}</span></div>
      <div class="card-stat"><span>Updates this week</span><span class="value">${updates}</span></div>
      <div class="card-stat"><span>All-time changes</span><span class="value">${domainChanges.length}</span></div>
    `;
    container.appendChild(card);
  }

  if (Object.keys(competitors).length === 0) {
    container.innerHTML =
      '<div class="empty-state">No data yet. Run the tracker to start monitoring.</div>';
  }
}

function populateFilters() {
  const select = document.getElementById("filter-competitor");
  const competitors = state.competitors || {};
  for (const [domain, data] of Object.entries(competitors)) {
    const opt = document.createElement("option");
    opt.value = domain;
    opt.textContent = data.name || domain;
    select.appendChild(opt);
  }
}

function applyFilters() {
  const competitor = document.getElementById("filter-competitor").value;
  const type = document.getElementById("filter-type").value;
  const days = parseInt(document.getElementById("filter-days").value);

  filtered = changes.filter((c) => {
    if (competitor && c.domain !== competitor) return false;
    if (type && c.change_type !== type) return false;
    if (days > 0) {
      const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
      if (new Date(c.timestamp) < cutoff) return false;
    }
    return true;
  });

  currentPage = 1;
  renderTimeline();
}

function renderTimeline() {
  const container = document.getElementById("timeline-list");
  const countEl = document.getElementById("change-count");

  countEl.textContent = `(${filtered.length} changes)`;

  if (filtered.length === 0) {
    container.innerHTML =
      '<div class="empty-state">No changes found for the selected filters.</div>';
    document.getElementById("pagination").innerHTML = "";
    return;
  }

  const start = (currentPage - 1) * PER_PAGE;
  const page = filtered.slice(start, start + PER_PAGE);

  container.innerHTML = page.map((c) => renderChangeItem(c)).join("");
  renderPagination();
}

function renderChangeItem(c) {
  const badge = `<span class="badge badge-${c.change_type}">${formatType(c.change_type)}</span>`;
  const details = renderDetails(c);

  return `
    <div class="change-item">
      <div class="change-header">
        ${badge}
        <span class="change-competitor">${escapeHtml(c.competitor)}</span>
        <span class="change-time">${formatDate(c.timestamp)}</span>
      </div>
      ${c.title ? `<div class="change-title">${escapeHtml(c.title)}</div>` : ""}
      <div class="change-url"><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.url)}</a></div>
      ${details ? `<div class="change-details">${details}</div>` : ""}
    </div>
  `;
}

function renderDetails(c) {
  const d = c.details || {};
  const parts = [];

  if (d.summary) parts.push(escapeHtml(d.summary));
  if (d.published_date) parts.push("Published: " + escapeHtml(d.published_date));
  if (d.old_title && d.new_title)
    parts.push(`Title: "${escapeHtml(d.old_title)}" → "${escapeHtml(d.new_title)}"`);
  if (d.old_meta && d.new_meta)
    parts.push(`Meta: "${escapeHtml(d.old_meta)}" → "${escapeHtml(d.new_meta)}"`);
  if (d.old_hash && d.new_hash)
    parts.push(`Hash: ${d.old_hash} → ${d.new_hash}`);
  if (d.missing_runs) parts.push(`Missing for ${d.missing_runs} consecutive runs`);

  return parts.join(" &middot; ");
}

function renderPagination() {
  const container = document.getElementById("pagination");
  const totalPages = Math.ceil(filtered.length / PER_PAGE);

  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  let html = "";
  html += `<button ${currentPage === 1 ? "disabled" : ""} onclick="goToPage(${currentPage - 1})">Prev</button>`;

  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === currentPage ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`;
  }

  html += `<button ${currentPage === totalPages ? "disabled" : ""} onclick="goToPage(${currentPage + 1})">Next</button>`;
  container.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  renderTimeline();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatType(type) {
  return type.replace(/_/g, " ");
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Event listeners
document.getElementById("filter-competitor").addEventListener("change", applyFilters);
document.getElementById("filter-type").addEventListener("change", applyFilters);
document.getElementById("filter-days").addEventListener("change", applyFilters);

// Load on page ready
loadData();
