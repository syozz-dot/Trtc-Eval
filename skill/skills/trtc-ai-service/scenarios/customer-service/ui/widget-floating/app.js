/* =====================================================================
 * AI Customer Service Widget — Lightweight Version (Real Conversational AI Connection)
 *
 * Key differences from the old (hardcoded IM) version:
 *   - Uses agent-link.js to actually connect to conversation-core AI (TRTC + agent/start)
 *   - AI replies come from LLM subtitle stream, not locally hardcoded text
 *   - Capabilities (handoff / tool calling) are dynamically mounted based on backend availability
 *   - KB uses silent RAG: hits only augment in the background, no FAQ text in the chat
 *
 * Backend capability probing (feature-probe; uninstalled capability routes → 404):
 *   GET /api/v1/handoff/status     human-handoff
 *   GET /api/v1/tools/list         tool-calling
 *   GET /api/v1/summary/_list      session-summary
 * ===================================================================== */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const widget = $("cs-widget");
  const launcher = $("widget-launcher");
  const btnCollapse = $("btn-collapse");
  const btnHandoff = $("btn-handoff");
  const btnMic = $("btn-mic");
  const micIconUse = $("mic-icon-use");
  const btnSend = $("btn-send");
  const btnRecheck = $("btn-recheck");
  const composer = $("composer");
  const composerInput = $("composer-input");
  const msgList = $("msg-list");
  const handoffBanner = $("handoff-banner");
  const handoffText = $("handoff-text");
  const btnCancelHandoff = $("btn-cancel-handoff");
  const statusText = document.querySelector('[data-role="status-text"]');
  const hintWrap = document.querySelector(".composer__hint");
  const hintText = document.querySelector('[data-role="kb-hit-text"]');
  const navAdmin = document.querySelector('[data-role="nav-admin"]');

  const HANDOFF_KEYWORDS = ["talk to agent", "real person", "speak to a human", "human agent", "support", "help me"];
  const HANDOFF_QUEUE_MS = 8000;
  const SIM_AGENT_ID = "demo_agent_alex";
  const KB_MIN_SCORE = 0.15;

  // Handoff connection mode (mock vs real, both code paths must be maintained):
  //   true  = mock demo: with the local_queue adapter there is no real agent; after
  //           HANDOFF_QUEUE_MS the frontend calls POST /api/v1/handoff/connect to
  //           simulate an agent taking the ticket, so the full flow can be demonstrated
  //           without a real agent.
  //   false = real integration: an agent actually picks up the ticket in your
  //           ticketing system (HH_ADAPTER=default_rest); the frontend does not fake
  //           the connection — it only polls GET /api/v1/handoff/{session_id} to
  //           reflect the real status.
  // In both modes the UI logic for "queue banner show / hide on connect or cancel
  // + muted status text" is identical.
  const SIMULATE_AGENT_CONNECT = true;

  const caps = { handoff: false, tools: false, summary: false };
  const ui = {
    started: false,
    starting: false,
    aiBubbles: {},        // roundid -> <li>
    typingNode: null,
    handoffState: null,
    handoffPolling: null,
  };

  let link = null;

  /* ============== 能力探测 ============== */
  async function probe(path) {
    try {
      const resp = await fetch(path, { credentials: "same-origin" });
      return resp.status !== 404;   // 200 / 4xx(非404) 都视为路由存在
    } catch { return false; }
  }
  async function detectCapabilities() {
    const [hh, tc, ss] = await Promise.all([
      probe("/api/v1/handoff/status"),
      probe("/api/v1/tools/list"),
      probe("/api/v1/summary/_list"),
    ]);
    caps.handoff = hh;
    caps.tools = tc;
    caps.summary = ss;
    btnHandoff.hidden = !caps.handoff;
    if (navAdmin) navAdmin.hidden = !caps.handoff;
  }

  /* ============== 健康自检（顶部 LED）============== */
  function renderHealth(checks) {
    ["tencent_cloud", "trtc", "llm"].forEach((k) => {
      const led = document.querySelector(`.led[data-led="${k}"]`);
      if (!led) return;
      const item = checks[k];
      const ok = item && item.status === "ok";
      led.setAttribute("data-status", checks[k] ? (ok ? "ok" : "error") : "unknown");
    });
  }

  /* ============== 浮窗开合 ============== */
  function expand() {
    widget.classList.remove("widget--collapsed");
    widget.classList.add("widget--expanded");
    if (!ui.started && !ui.starting) startConversation();
    else composerInput.focus();
  }
  function collapse() {
    widget.classList.remove("widget--expanded");
    widget.classList.add("widget--collapsed");
  }

  /* ============== 消息渲染 ============== */
  function pushMsg(role, text) {
    const li = document.createElement("li");
    li.className = `msg msg--${role}`;
    li.textContent = text;
    msgList.appendChild(li);
    msgList.scrollTop = msgList.scrollHeight;
    return li;
  }
  const pushUserMsg = (t) => pushMsg("user", t);
  const pushAiMsg = (t) => pushMsg("ai", t);
  const pushSystemMsg = (t) => pushMsg("system", t);

  function showTyping() {
    if (ui.typingNode) return;
    const li = document.createElement("li");
    li.className = "msg--typing";
    li.innerHTML = "<span></span><span></span><span></span>";
    msgList.appendChild(li);
    msgList.scrollTop = msgList.scrollHeight;
    ui.typingNode = li;
  }
  function hideTyping() {
    if (ui.typingNode) { ui.typingNode.remove(); ui.typingNode = null; }
  }

  function setStatusText(t) { if (statusText) statusText.textContent = t; }
  function setHint(text, tone) {
    if (hintText) hintText.textContent = text;
    if (hintWrap) hintWrap.setAttribute("data-tone", tone || "");
  }

  /* ============== 启动会话（真接通）============== */
  async function startConversation() {
    if (ui.started || ui.starting) return;
    ui.starting = true;
    setStatusText("正在接通…");
    setHint("正在接通 AI…", "");
    showTyping();

    const h = await link.checkHealth();
    if (!h.allOk) {
      hideTyping();
      ui.starting = false;
      setStatusText("未就绪");
      setHint("三把 Key 未全部就绪", "error");
      pushSystemMsg("AI 服务尚未就绪：请确认 Tencent Cloud / TRTC / LLM 三盏指示灯全绿后重试。");
      return;
    }

    try {
      await link.connect({ language: "zh" });
      ui.started = true;
      ui.starting = false;
      hideTyping();
      composerInput.disabled = false;
      btnSend.disabled = false;
      composerInput.focus();
      setStatusText("已接通");
      setHint("已接通 · 输入问题开始对话", "kb");
      pushSystemMsg("已接通 AI 客服。" + (caps.handoff ? "需要真人时点右上角或说“转人工”。" : ""));
    } catch (err) {
      hideTyping();
      ui.starting = false;
      setStatusText("接通失败");
      setHint("接通失败，请重试", "error");
      pushSystemMsg(`接通失败：${err.message || err}。请检查网络后重试。`);
      console.error("[widget] connect failed", err);
    }
  }

  /* ============== KB silent RAG ============== */
  async function silentKbLookup(query) {
    try {
      const resp = await AgentLink._api("/api/v1/kb/search", {
        method: "POST",
        body: { query, top_k: 1 },
      });
      const hits = (resp && (resp.data || resp.hits)) || [];
      if (!hits.length) return;
      const top = hits[0];
      if (typeof top.score === "number" && top.score < KB_MIN_SCORE) return;
      // 不做任何 DOM 渲染：KB 命中在后端静默增强 LLM 答案，前端保持干净
      console.debug("[kb hit]", (top.entry && top.entry.id) || top.id, "score=", top.score);
    } catch (e) { console.debug("[kb] error", e); }
  }

  /* ============== 用户每句话后的副作用 ============== */
  function onUserUtterance(text) {
    const lower = text.toLowerCase();
    if (caps.handoff && HANDOFF_KEYWORDS.some((kw) => lower.includes(kw.toLowerCase()))) {
      requestHandoff(`keyword trigger: ${text}`);
      return;
    }
    silentKbLookup(text);
  }

  /* ============== 转人工（真实工单流）============== */
  async function requestHandoff(reason) {
    if (!caps.handoff || !link.sessionId) return;
    if (ui.handoffState === "waiting" || ui.handoffState === "connected") {
      pushSystemMsg("您已在转人工队列中，请稍候。");
      return;
    }
    btnHandoff.disabled = true;
    try {
      const resp = await AgentLink._api("/api/v1/handoff/request", {
        method: "POST",
        body: { session_id: link.sessionId, reason: reason || "user-initiated" },
      });
      renderHandoff((resp && resp.data) || {});
      startHandoffProgress();
      startHandoffPoll();
    } catch (err) {
      pushSystemMsg("转人工申请失败，请稍后重试。");
      console.warn("[handoff] request failed", err);
    } finally {
      btnHandoff.disabled = false;
    }
  }

  function renderHandoff(data) {
    const st = data.state || "waiting";
    ui.handoffState = st;
    // banner 只在「排队中」这一瞬态显示
    if (st === "waiting") {
      const pos = data.queue_position != null ? data.queue_position : "-";
      handoffText.textContent = `正在为您接通人工…当前排在第 ${pos} 位`;
      handoffBanner.setAttribute("data-state", "waiting");
      handoffBanner.hidden = false;
      setStatusText("排队中");
      return;
    }
    // 非排队态：banner 一律消失，改用对话区灰字 hint 告知用户
    handoffBanner.hidden = true;
    if (st === "connected") {
      pushSystemMsg(`已接通人工座席 ${data.agent_id || ""}`.trim());
      setStatusText("人工接通");
    } else if (st === "timeout") {
      pushSystemMsg("人工座席暂无空闲，请稍后重试。");
      setStatusText(ui.started ? "已接通" : "");
      ui.handoffState = null;
    }
    // canceled 由 cancelHandoff 统一处理（推灰字 + 隐藏），此处不重复
  }

  function startHandoffProgress() {
    // 仅 mock 模式：本地无真实座席，排队 HANDOFF_QUEUE_MS 后伪造一次座席接入。
    // 真实接入（SIMULATE_AGENT_CONNECT=false）时跳过——座席在工单系统侧真实接单，
    // 由 startHandoffPoll 轮询反映真实状态。
    if (!SIMULATE_AGENT_CONNECT) return;
    setTimeout(async () => {
      if (ui.handoffState !== "waiting" || !link.sessionId) return;
      try {
        await AgentLink._api("/api/v1/handoff/connect", {
          method: "POST",
          body: { session_id: link.sessionId, agent_id: SIM_AGENT_ID },
        });
      } catch (e) { console.warn("[handoff] simulate connect failed", e); }
    }, HANDOFF_QUEUE_MS);
  }

  function startHandoffPoll() {
    stopHandoffPoll();
    ui.handoffPolling = setInterval(async () => {
      if (!link.sessionId) return;
      try {
        const resp = await fetch(`/api/v1/handoff/${encodeURIComponent(link.sessionId)}`);
        if (!resp.ok) return;
        const body = await resp.json();
        renderHandoff((body && body.data) || {});
        if (["connected", "canceled", "timeout", "closed"].includes(ui.handoffState)) {
          stopHandoffPoll();
        }
      } catch (e) { /* ignore */ }
    }, 2500);
  }
  function stopHandoffPoll() {
    if (ui.handoffPolling) { clearInterval(ui.handoffPolling); ui.handoffPolling = null; }
  }

  async function cancelHandoff() {
    if (!link.sessionId) return;
    try {
      await AgentLink._api("/api/v1/handoff/cancel", {
        method: "POST",
        body: { session_id: link.sessionId },
      });
    } catch (e) { console.warn("[handoff] cancel failed", e); }
    stopHandoffPoll();
    ui.handoffState = null;
    handoffBanner.hidden = true;                       // banner 立即消失
    setStatusText(ui.started ? "已接通" : "");
    pushSystemMsg("已取消排队");                         // 对话区灰字提示
  }

  /* ============== 输入提交 ============== */
  async function handleSubmit(text) {
    if (!text) return;
    if (!ui.started) { pushSystemMsg("正在接通，请稍候…"); return; }
    // 工具调用：/tool <name> {json}（前端直调 invoke 并渲染结构化卡片）
    if (/^\/tool(\s|$)/i.test(text)) {
      await handleToolCommand(text);
      return;
    }
    pushUserMsg(text);
    link.sendText(text, true);   // silent：气泡已本地渲染，避免字幕回放双气泡
    showTyping();
    onUserUtterance(text);
  }

  /* ============== 工具调用（tool-calling 前端卡片）============== */
  function parseToolCommand(text) {
    const m = text.match(/^\/tool\s+([A-Za-z0-9_\-]{1,64})\s*(\{[\s\S]*\})?\s*$/i);
    if (!m) return null;
    let params = {};
    if (m[2]) { try { params = JSON.parse(m[2]); } catch { params = {}; } }
    return { name: m[1], params };
  }

  async function handleToolCommand(text) {
    pushUserMsg(text);
    if (!caps.tools) {
      pushSystemMsg("当前未启用工具调用能力（tool-calling）。");
      return;
    }
    const parsed = parseToolCommand(text);
    if (!parsed) {
      pushSystemMsg('工具格式：/tool <name> {"参数":"值"}，例如 /tool get_business_info {"topic":"all"}');
      return;
    }
    const card = renderToolCard({ name: parsed.name, state: "running" });
    try {
      const resp = await AgentLink._api("/api/v1/tools/invoke", {
        method: "POST",
        body: { name: parsed.name, params: parsed.params },
      });
      const d = (resp && resp.data) || {};
      renderToolCard({ name: d.tool || parsed.name, state: d.ok ? "ok" : "error",
                       track: d.track, output: d.output, error: d.error, latency: d.latency_ms }, card);
      // 把工具结果交给 AI 组织成自然语言回复
      if (d.ok && link.connected) {
        link.sendText(
          `[tool_result name=${d.tool} ok=true]\n${JSON.stringify(d.output)}\n[/tool_result]\n请用自然语言向用户简要说明以上结果。`,
          true,
        );
        showTyping();
      }
    } catch (err) {
      renderToolCard({ name: parsed.name, state: "error", error: err.message || String(err) }, card);
    }
  }

  function renderToolCard(info, existing) {
    const li = existing || document.createElement("li");
    if (!existing) { li.className = "tool-card"; msgList.appendChild(li); }
    li.setAttribute("data-state", info.state || "running");
    const stateLabel = { running: "调用中", ok: "成功", error: "失败" }[info.state] || info.state;
    const trackLabel = info.track ? ` · ${info.track}` : "";
    let bodyHtml = "";
    if (info.state === "running") {
      bodyHtml = `<div class="tool-card__body tool-card__body--muted">正在执行…</div>`;
    } else if (info.state === "error") {
      bodyHtml = `<div class="tool-card__body tool-card__body--err">${escapeHtml(info.error || "调用失败")}</div>`;
    } else {
      bodyHtml = `<pre class="tool-card__body">${escapeHtml(JSON.stringify(info.output, null, 2))}</pre>`;
    }
    li.innerHTML = `
      <div class="tool-card__head">
        <svg class="icon" width="16" height="16"><use href="#icon-tool"/></svg>
        <span class="tool-card__name">${escapeHtml(info.name)}</span>
        <span class="tool-card__status" data-s="${info.state}">${stateLabel}${trackLabel}</span>
      </div>
      ${bodyHtml}`;
    msgList.scrollTop = msgList.scrollHeight;
    return li;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  /* ============== agent-link 回调 ============== */
  function buildLink() {
    return AgentLink.create({
      modality: { voiceInput: false },
      on: {
        health: (checks) => renderHealth(checks),
        userFinal: (text) => {
          // 仅语音输入路径会触发（文本走 silent）；此处兜底渲染
          pushUserMsg(text);
          showTyping();
          onUserUtterance(text);
        },
        agentDelta: (roundid, fullText) => {
          hideTyping();
          let bubble = ui.aiBubbles[roundid];
          if (!bubble) { bubble = pushAiMsg(fullText); ui.aiBubbles[roundid] = bubble; }
          else { bubble.textContent = fullText; msgList.scrollTop = msgList.scrollHeight; }
        },
        agentFinal: (roundid, fullText) => {
          const bubble = ui.aiBubbles[roundid];
          if (bubble) bubble.textContent = fullText;
          delete ui.aiBubbles[roundid];
        },
        state: (label) => {
          if (!ui.started) return;
          const map = { listening: "聆听中", thinking: "思考中", speaking: "回复中", idle: "已接通" };
          if (ui.handoffState !== "connected") setStatusText(map[label] || "已接通");
        },
        error: (err) => console.warn("[widget] link error", err),
      },
    });
  }

  /* ============== 事件绑定 ============== */
  launcher.addEventListener("click", expand);
  btnCollapse.addEventListener("click", collapse);
  btnCancelHandoff.addEventListener("click", cancelHandoff);
  btnHandoff.addEventListener("click", () => requestHandoff("user clicked talk-to-agent"));
  if (btnRecheck) btnRecheck.addEventListener("click", () => link.checkHealth());

  btnMic.addEventListener("click", async () => {
    const on = await link.toggleMic();
    btnMic.classList.toggle("active", on);
    if (micIconUse) micIconUse.setAttribute("href", on ? "#icon-mic" : "#icon-mic-off");
  });

  let imeComposing = false;
  composerInput.addEventListener("compositionstart", () => { imeComposing = true; });
  composerInput.addEventListener("compositionend", () => { imeComposing = false; });
  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (imeComposing) return;
    const text = composerInput.value.trim();
    if (!text) return;
    composerInput.value = "";
    await handleSubmit(text);
  });

  /* ============== 初始化 ============== */
  link = buildLink();
  link.checkHealth();
  detectCapabilities();
  setInterval(() => link.checkHealth(), 30000);
})();
