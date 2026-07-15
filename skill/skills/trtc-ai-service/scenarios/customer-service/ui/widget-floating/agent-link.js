/* =====================================================================
 * agent-link.js — Shared Conversational AI Connection Core
 *
 * Extracts the proven "TRTC + conversation-core agent" pipeline from
 * voice-customer-service into a reusable core that is decoupled from any
 * specific UI. This allows the widget / fullscreen / voice shells to share
 * the same connection logic and avoid drift between implementations.
 *
 * Backend contract (conversation-core skeleton — do not modify):
 *   GET  /api/v1/health                Three-LED self-check
 *   POST /api/v1/get_config            session_id / sdk_app_id / room_id / user_sig / agent_user_id
 *   POST /api/v1/agent/start           Launch the AI bot inside the TRTC room
 *   POST /api/v1/agent/stop            Stop
 *   TRTC Web SDK v5: enterRoom / startLocalAudio / sendCustomMessage
 *   client → bot:  cmdId=2, type=20000 text injection, type=20001 interrupt
 *   bot → client:  type=10000 subtitle (payload.text/end/roundid), type=10001 state
 *
 * Usage:
 *   const link = AgentLink.create({
 *     modality: { voiceInput: false },       // text_with_tts defaults to mic off
 *     on: {
 *       userFinal:  (text) => {...},          // final user utterance
 *       agentDelta: (roundid, fullText) => {},// incremental AI subtitle
 *       agentFinal: (roundid, fullText) => {},// end of one AI turn
 *       state:      (label) => {},            // listening/thinking/speaking/idle
 *       system:     (text) => {},             // system message
 *       error:      (err)  => {},
 *       health:     (checks, allOk, raw) => {},
 *     },
 *   });
 *   await link.connect();      // get_config + enterRoom + agent/start
 *   link.sendText("Hello");     // text injection (triggers userFinal callback for the caller to render)
 *   await link.disconnect();
 * ===================================================================== */
(function (global) {
  "use strict";

  const ECHO_TTL_MS = 30_000;

  function uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  async function api(path, options = {}) {
    const resp = await fetch(path, {
      method: options.method || "GET",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let data;
    try { data = await resp.json(); } catch { data = {}; }
    if (!resp.ok) {
      const msg = (data && (data.detail?.message || data.detail || data.msg)) || resp.statusText;
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function create(opts) {
    opts = opts || {};
    const cb = opts.on || {};
    const modality = Object.assign({ voiceInput: false }, opts.modality || {});

    const state = {
      connected: false,
      healthy: false,
      sessionId: null,
      sdkAppId: 0,
      roomId: null,
      userId: null,
      userSig: null,
      agentUserId: null,
      trtcClient: null,
      micEnabled: false,
      aiRoundText: {},
      aiRoundLast: {},
      userBubbleOpen: false,
      localEchoes: [],
    };

    const emit = (name, ...args) => {
      const fn = cb[name];
      if (typeof fn === "function") {
        try { fn(...args); } catch (e) { console.error(`[agent-link] cb ${name} error`, e); }
      }
    };

    // ---------- local echo dedup（避免主动渲染 + bot 字幕回放双气泡）----------
    function pushLocalEcho(text) {
      const now = Date.now();
      state.localEchoes = state.localEchoes.filter((e) => now - e.at < ECHO_TTL_MS);
      state.localEchoes.push({ text: (text || "").trim(), at: now });
    }
    function consumeLocalEcho(text) {
      const tt = (text || "").trim();
      if (!tt) return false;
      const now = Date.now();
      state.localEchoes = state.localEchoes.filter((e) => now - e.at < ECHO_TTL_MS);
      for (let i = 0; i < state.localEchoes.length; i++) {
        const a = state.localEchoes[i].text.toLowerCase(), b = tt.toLowerCase();
        if (a === b || a.includes(b) || b.includes(a)) {
          state.localEchoes.splice(i, 1);
          return true;
        }
      }
      return false;
    }

    // ---------- 健康自检 ----------
    async function checkHealth() {
      try {
        const data = await api("/api/v1/health");
        const checks = data.checks || {};
        let allOk = true;
        for (const k of ["tencent_cloud", "trtc", "llm"]) {
          if ((checks[k] || {}).status !== "ok") allOk = false;
        }
        state.healthy = allOk;
        emit("health", checks, allOk, data);
        return { checks, allOk, raw: data };
      } catch (err) {
        state.healthy = false;
        emit("health", {}, false, null);
        return { checks: {}, allOk: false, raw: null };
      }
    }

    // ---------- TRTC 自定义消息处理 ----------
    function handleCustomMessage(data, eventUserId) {
      if (!data || typeof data !== "object") return;

      if (data.type === 10001) {
        const code = data.payload && data.payload.state;
        const map = { 1: "listening", 2: "thinking", 3: "speaking", 4: "idle" };
        emit("state", map[code] || "idle");
        return;
      }
      if (data.type !== 10000) return;

      const text = (data.payload && data.payload.text) || "";
      const sender = data.sender || eventUserId || "";
      const end = data.payload && data.payload.end === true;
      const roundid = (data.payload && data.payload.roundid) || "";
      const isUser = sender === state.userId;

      if (isUser) {
        if (end && text.trim()) {
          const tt = text.trim();
          if (consumeLocalEcho(tt)) return;   // 已本地渲染过，跳过回放
          emit("userFinal", tt);
        }
        return;
      }

      // AI 字幕：自动识别增量 / 累积，按 roundid 聚合
      if (text.trim() && roundid) {
        const last = state.aiRoundLast[roundid] || "";
        const cur = state.aiRoundText[roundid] || "";
        const isAccumulative = last && text.startsWith(last);
        state.aiRoundText[roundid] = isAccumulative ? text : (cur + text);
        state.aiRoundLast[roundid] = text;
        emit("agentDelta", roundid, state.aiRoundText[roundid]);
      }
      if (end && roundid) {
        const finalText = state.aiRoundText[roundid] || text;
        emit("agentFinal", roundid, finalText);
        delete state.aiRoundText[roundid];
        delete state.aiRoundLast[roundid];
      }
    }

    // ---------- 连接 ----------
    async function connect(startOpts) {
      if (state.connected) return;
      startOpts = startOpts || {};
      const cfg = await api("/api/v1/get_config", { method: "POST", body: {} });
      const data = cfg.data || {};
      Object.assign(state, {
        sessionId: data.session_id,
        sdkAppId: data.sdk_app_id,
        roomId: parseInt(data.room_id, 10),
        userId: data.user_id,
        userSig: data.user_sig,
        agentUserId: data.agent_user_id,
      });

      if (typeof global.TRTC === "undefined") throw new Error("TRTC Web SDK not loaded");
      const TRTC = global.TRTC;
      state.trtcClient = TRTC.create();
      state.trtcClient.on(TRTC.EVENT.CUSTOM_MESSAGE, (event) => {
        try {
          const txt = new TextDecoder().decode(event.data);
          handleCustomMessage(JSON.parse(txt), event.userId);
        } catch (e) { console.warn("[agent-link] parse custom msg failed", e); }
      });
      state.trtcClient.on(TRTC.EVENT.ERROR, (err) => emit("error", err));

      await state.trtcClient.enterRoom({
        roomId: state.roomId,
        scene: "rtc",
        sdkAppId: state.sdkAppId,
        userId: state.userId,
        userSig: state.userSig,
      });

      // 文本模态默认拉起本地音频但静音（用于接收 TTS 下行 + 备用上行）；纯文本也能跑
      try {
        await state.trtcClient.startLocalAudio();
        await state.trtcClient.updateLocalAudio({ mute: true });
        state.micEnabled = false;
      } catch (e) {
        console.warn("[agent-link] mic init skipped:", e);
      }

      await api("/api/v1/agent/start", {
        method: "POST",
        body: {
          session_id: state.sessionId,
          language: startOpts.language || "zh",
          greeting: startOpts.greeting,
          instructions: startOpts.instructions,
        },
      });
      state.connected = true;
      emit("state", "idle");
      return { sessionId: state.sessionId };
    }

    async function disconnect() {
      try {
        if (state.sessionId) {
          await api("/api/v1/agent/stop", { method: "POST", body: { session_id: state.sessionId } });
        }
      } catch (e) { console.warn("[agent-link] stop api error", e); }
      try {
        if (state.trtcClient) {
          await state.trtcClient.exitRoom();
          state.trtcClient.destroy();
        }
      } catch (e) { console.warn("[agent-link] exitRoom failed", e); }
      state.trtcClient = null;
      state.connected = false;
      state.sessionId = null;
      state.micEnabled = false;
      state.localEchoes = [];
      emit("state", "idle");
    }

    // ---------- 文本注入 ----------
    async function sendCustom(message) {
      if (!state.trtcClient) return false;
      try {
        await state.trtcClient.sendCustomMessage({
          cmdId: 2,
          data: new TextEncoder().encode(JSON.stringify(message)).buffer,
        });
        return true;
      } catch (e) { console.warn("[agent-link] sendCustomMessage failed", e); return false; }
    }

    function sendInterrupt() {
      return sendCustom({
        type: 20001,
        sender: state.userId,
        receiver: [state.agentUserId],
        payload: { id: uuid(), timestamp: Date.now() },
      });
    }

    /** 发送文本给 AI。silent=true 时不触发 userFinal（用于卡片自动追问已自行渲染的场景）。 */
    function sendText(text, silent) {
      const t = (text || "").trim();
      if (!t || !state.trtcClient) return false;
      pushLocalEcho(t);
      sendInterrupt();
      setTimeout(() => {
        sendCustom({
          type: 20000,
          sender: state.userId,
          receiver: [state.agentUserId],
          payload: { id: uuid(), message: t, timestamp: Date.now() },
        });
      }, 120);
      if (!silent) emit("userFinal", t);
      return true;
    }

    async function toggleMic() {
      if (!state.trtcClient) return state.micEnabled;
      state.micEnabled = !state.micEnabled;
      try {
        await state.trtcClient.updateLocalAudio({ mute: !state.micEnabled });
        if (state.micEnabled) sendInterrupt();
      } catch (e) {
        console.error("[agent-link] toggleMic failed", e);
        state.micEnabled = !state.micEnabled;
      }
      return state.micEnabled;
    }

    return {
      checkHealth,
      connect,
      disconnect,
      sendText,
      toggleMic,
      get connected() { return state.connected; },
      get healthy() { return state.healthy; },
      get sessionId() { return state.sessionId; },
      get micEnabled() { return state.micEnabled; },
      get modality() { return modality; },
    };
  }

  global.AgentLink = { create, _api: api };
})(window);
