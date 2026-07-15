/* =====================================================================
 * Ticket Agent Board — Frontend Logic
 * Backend contract: capabilities/human-handoff/manifest.yaml.endpoints
 *   GET  /api/v1/handoff/admin/tickets[?status=&limit=]     Ticket list
 *   GET  /api/v1/handoff/admin/tickets/{ticket_id}          Ticket detail
 *   POST /api/v1/handoff/admin/tickets/{ticket_id}/status   Status update
 *   GET  /api/v1/handoff/status                             Overall queue status
 *   POST /api/v1/handoff/request                            Manually submit a test ticket
 * ===================================================================== */

(function () {
  "use strict";

  /* ---------- DOM ---------- */
  const tbody = document.getElementById("ticket-rows");
  const summary = document.getElementById("list-summary");
  const filterList = document.getElementById("filter-list");
  const drawer = document.getElementById("drawer");
  const drawerBody = document.getElementById("drawer-body");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");
  const btnRefresh = document.getElementById("btn-refresh");
  const chkAuto = document.getElementById("chk-auto");
  const btnSeed = document.getElementById("btn-seed");
  const metricAgents = document.querySelector('[data-role="metric-agents"]');
  const metricWaiting = document.querySelector('[data-role="metric-waiting"]');
  const metricConnected = document.querySelector('[data-role="metric-connected"]');

  const state = {
    statusFilter: "",
    list: [],
    selectedId: null,
    autoTimer: null,
  };

  const STATUS_LABEL = {
    pending: "Pending",
    processing: "In progress",
    closed: "Closed",
    canceled: "Canceled",
    timeout: "Timeout",
  };

  const PRIORITY_LABEL = {
    low: "Low",
    normal: "Normal",
    high: "High",
    urgent: "Urgent",
  };

  /* ---------- Utilities ---------- */
  function fmtTs(ts) {
    if (!ts && ts !== 0) return "--";
    const ms = ts < 1e12 ? ts * 1000 : ts;          // compatible with epoch (seconds/milliseconds)
    const d = new Date(ms);
    if (Number.isNaN(d.getTime())) return "--";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }

  function showToast(text, tone) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.setAttribute("data-tone", tone || "");
    el.classList.add("is-visible");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("is-visible"), 2400);
  }

  /* ---------- Network ---------- */
  async function api(path, opts) {
    const init = Object.assign({ credentials: "same-origin" }, opts || {});
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
      init.headers = Object.assign({ "Content-Type": "application/json" }, init.headers || {});
    }
    const resp = await fetch(path, init);
    if (!resp.ok) {
      let detail = `${resp.status} ${resp.statusText}`;
      try {
        const j = await resp.json();
        if (j && j.detail) detail = j.detail;
      } catch (e) { /* swallow */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  async function fetchOverall() {
    try {
      const body = await api("/api/v1/handoff/status");
      const d = body.data || body;
      metricAgents.textContent = d.available_agents != null ? d.available_agents : (d.agent_pool_size ?? "--");
      metricWaiting.textContent = d.waiting ?? "--";
      metricConnected.textContent = d.connected ?? "--";
    } catch (err) {
      console.warn("overall status failed", err);
    }
  }

  async function fetchList() {
    const url = new URL("/api/v1/handoff/admin/tickets", location.origin);
    url.searchParams.set("limit", "100");
    if (state.statusFilter) url.searchParams.set("status", state.statusFilter);
    try {
      const body = await api(url.pathname + url.search);
      const data = body.data || body;
      state.list = (data.items || []).slice();
      renderList();
      summary.textContent = `${state.list.length} ticket(s) · ${state.statusFilter ? STATUS_LABEL[state.statusFilter] : "All"}`;
    } catch (err) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="7">Failed to load: ${escapeHtml(err.message || err)}</td></tr>`;
      summary.textContent = "Failed to load";
    }
  }

  /* ---------- Rendering ---------- */
  function renderList() {
    if (!state.list.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No tickets yet. Click "Insert test ticket" on the left to create one.</td></tr>';
      return;
    }
    const html = state.list.map((t) => renderRow(t)).join("");
    tbody.innerHTML = html;

    Array.from(tbody.querySelectorAll("tr[data-ticket-id]")).forEach((tr) => {
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest(".row-actions")) return;
        openDrawer(tr.getAttribute("data-ticket-id"));
      });
    });
    Array.from(tbody.querySelectorAll("[data-action]")).forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute("data-ticket-id");
        const action = btn.getAttribute("data-action");
        await onActionClick(id, action);
      });
    });
  }

  function renderRow(t) {
    const subj = t.subject || t.reason || "(empty)";
    const sel = state.selectedId === t.ticket_id ? " is-selected" : "";
    const priority = t.priority || "normal";
    const status = t.status || "pending";

    let actions = "";
    if (status === "pending") {
      actions = `
        <button class="btn btn--accent btn--small" data-action="processing" data-ticket-id="${escapeHtml(t.ticket_id)}">Connect</button>
        <button class="btn btn--ghost btn--small btn--danger" data-action="canceled" data-ticket-id="${escapeHtml(t.ticket_id)}">Cancel</button>
      `;
    } else if (status === "processing") {
      actions = `
        <button class="btn btn--ghost btn--small" data-action="closed" data-ticket-id="${escapeHtml(t.ticket_id)}">Close ticket</button>
      `;
    } else {
      actions = '<span style="color: var(--color-text-tertiary); font-size: 12px;">Resolved</span>';
    }

    return `
      <tr data-ticket-id="${escapeHtml(t.ticket_id)}" class="${sel}">
        <td><span class="ticket-id">${escapeHtml(t.ticket_id)}</span></td>
        <td>${escapeHtml(t.user_id || "--")}</td>
        <td>${escapeHtml(subj)}</td>
        <td><span class="priority" data-level="${escapeHtml(priority)}">${escapeHtml(PRIORITY_LABEL[priority] || priority)}</span></td>
        <td><span class="status-pill" data-status="${escapeHtml(status)}">${escapeHtml(STATUS_LABEL[status] || status)}</span></td>
        <td>${escapeHtml(fmtTs(t.created_at))}</td>
        <td class="ticket-table__col-actions"><div class="row-actions">${actions}</div></td>
      </tr>
    `;
  }

  function renderDetail(t) {
    if (!t) {
      drawerBody.innerHTML = '<p class="drawer__placeholder">Ticket not found.</p>';
      return;
    }
    const tx = (t.transcript || []).map((line) => `· ${line}`).join("\n");
    let actions = "";
    if (t.status === "pending") {
      actions = `
        <button class="btn btn--accent btn--small" data-detail-action="processing" data-ticket-id="${escapeHtml(t.ticket_id)}">Connect ticket</button>
        <button class="btn btn--ghost btn--small btn--danger" data-detail-action="canceled" data-ticket-id="${escapeHtml(t.ticket_id)}">Cancel ticket</button>
      `;
    } else if (t.status === "processing") {
      actions = `
        <button class="btn btn--ghost btn--small" data-detail-action="closed" data-ticket-id="${escapeHtml(t.ticket_id)}">Close ticket</button>
      `;
    }
    drawerBody.innerHTML = `
      <dl class="detail-grid">
        <dt>ID</dt><dd><span class="ticket-id">${escapeHtml(t.ticket_id)}</span></dd>
        <dt>User</dt><dd>${escapeHtml(t.user_id || "--")}</dd>
        <dt>Subject</dt><dd>${escapeHtml(t.subject || "(empty)")}</dd>
        <dt>Priority</dt><dd><span class="priority" data-level="${escapeHtml(t.priority || "normal")}">${escapeHtml(PRIORITY_LABEL[t.priority] || t.priority || "Normal")}</span></dd>
        <dt>Status</dt><dd><span class="status-pill" data-status="${escapeHtml(t.status)}">${escapeHtml(STATUS_LABEL[t.status] || t.status)}</span></dd>
        <dt>Agent</dt><dd>${escapeHtml(t.agent_id || "--")}</dd>
        <dt>Created</dt><dd>${escapeHtml(fmtTs(t.created_at))}</dd>
        <dt>Updated</dt><dd>${escapeHtml(fmtTs(t.updated_at))}</dd>
        ${t.closed_at ? `<dt>Closed</dt><dd>${escapeHtml(fmtTs(t.closed_at))}</dd>` : ""}
      </dl>
      <p class="drawer__placeholder" style="font-style:normal;">Conversation summary</p>
      <div class="transcript">${escapeHtml(t.description || t.reason || "(none)")}</div>
      ${tx ? `
        <p class="transcript__title">Conversation transcript</p>
        <div class="transcript">${escapeHtml(tx)}</div>
      ` : ""}
      ${t.feedback ? renderFeedbackBlock(t.feedback) : ""}
      ${actions ? `<div class="action-row">${actions}</div>` : ""}
    `;

    Array.from(drawerBody.querySelectorAll("[data-detail-action]")).forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-ticket-id");
        const action = btn.getAttribute("data-detail-action");
        await onActionClick(id, action);
      });
    });
  }

  /* ---------- Customer satisfaction feedback (issue 6) ---------- */
  function renderFeedbackBlock(fb) {
    const rating = Math.max(0, Math.min(5, parseInt(fb.rating, 10) || 0));
    const stars = "\u2605".repeat(rating) + "\u2606".repeat(5 - rating);
    const comment = fb.comment && String(fb.comment).trim();
    return `
      <div class="feedback-block">
        <p class="transcript__title">Customer feedback</p>
        <div class="feedback-body">
          <div class="feedback-rating">
            <span class="feedback-stars">${stars}</span>
            <span class="feedback-score">${rating}/5</span>
          </div>
          <div class="feedback-comment${comment ? "" : " feedback-empty"}">${comment ? escapeHtml(comment) : "No written comment"}</div>
        </div>
      </div>`;
  }

  function openDrawer(ticketId) {
    state.selectedId = ticketId;
    drawer.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    const t = state.list.find((x) => x.ticket_id === ticketId);
    if (t) renderDetail(t);
    else {
      // Fetch single detail (fallback when list pagination misses it)
      api(`/api/v1/handoff/admin/tickets/${encodeURIComponent(ticketId)}`)
        .then((b) => renderDetail(b.data || b))
        .catch(() => renderDetail(null));
    }
    Array.from(tbody.querySelectorAll("tr")).forEach((tr) =>
      tr.classList.toggle("is-selected", tr.getAttribute("data-ticket-id") === ticketId),
    );
  }
  function closeDrawer() {
    drawer.hidden = true;
    drawer.setAttribute("aria-hidden", "true");
    state.selectedId = null;
    Array.from(tbody.querySelectorAll("tr")).forEach((tr) => tr.classList.remove("is-selected"));
  }
  btnCloseDrawer.addEventListener("click", closeDrawer);

  /* ---------- Status transitions ---------- */
  async function onActionClick(ticketId, status) {
    const body = { status };
    if (status === "processing") body.agent_id = "agent_demo_001";
    try {
      await api(`/api/v1/handoff/admin/tickets/${encodeURIComponent(ticketId)}/status`, {
        method: "POST",
        body,
      });
      showToast(`Ticket ${ticketId.slice(0, 12)} → ${STATUS_LABEL[status] || status}`, "success");
    } catch (err) {
      showToast(`Status change failed: ${err.message || err}`, "error");
    }
    await Promise.all([fetchList(), fetchOverall()]);
    if (state.selectedId === ticketId) {
      const t = state.list.find((x) => x.ticket_id === ticketId);
      renderDetail(t);
    }
  }

  /* ---------- Filters ---------- */
  filterList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".filter-item");
    if (!btn) return;
    const status = btn.getAttribute("data-status");
    if (status === null) return;
    state.statusFilter = status;
    Array.from(filterList.querySelectorAll(".filter-item")).forEach((b) =>
      b.classList.toggle("is-active", b === btn),
    );
    await fetchList();
  });

  /* ---------- Refresh ---------- */
  async function refreshAll() {
    await Promise.all([fetchOverall(), fetchList()]);
  }
  btnRefresh.addEventListener("click", refreshAll);

  function setupAutoRefresh() {
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
    }
    if (chkAuto.checked) {
      state.autoTimer = setInterval(refreshAll, 5000);
    }
  }
  chkAuto.addEventListener("change", setupAutoRefresh);

  /* ---------- Test ticket (dev only) ---------- */
  btnSeed.addEventListener("click", async () => {
    const fakeId = "demo_seed_" + Math.random().toString(36).slice(2, 8);
    try {
      await api("/api/v1/handoff/request", {
        method: "POST",
        body: { session_id: fakeId, reason: "Manually inserted test ticket from board" },
      });
      showToast("Test ticket inserted", "success");
    } catch (err) {
      showToast(`Insert failed: ${err.message || err}`, "error");
    }
    await refreshAll();
  });

  /* ---------- Init ---------- */
  refreshAll();
  setupAutoRefresh();
})();
