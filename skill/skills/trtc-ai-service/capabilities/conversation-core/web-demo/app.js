/* TRTC Conversational AI · Web Demo
 * Health check → request room credentials (get_config) → TRTC enterRoom + start AI
 * Subtitles come from TRTC custom messages: type=10000 (subtitle), type=10001 (AI state)
 * User text messages sent to the AI bot: sendCustomMessage(cmdId:2, type:20000)
 *   → AI treats it as "user speech" and responds (voice + subtitle)
 */
(function () {
  'use strict';

  const elIndicators = document.querySelectorAll('.indicator');
  const btnRecheck = document.getElementById('btn-recheck');
  const btnStart = document.getElementById('btn-start');
  const btnMic = document.getElementById('btn-mic');
  const btnStop = document.getElementById('btn-stop');
  const btnSend = document.getElementById('btn-send');
  const txt = document.getElementById('text-input');
  const conv = document.getElementById('conversation');
  const micLabel = document.getElementById('mic-label');
  const micIcon = document.getElementById('mic-icon');
  const agentStatusEl = document.getElementById('agent-status');

  const state = {
    healthy: false,
    sessionId: null,
    sdkAppId: 0,
    roomId: null,
    userId: null,
    userSig: null,
    agentUserId: null,
    taskId: null,
    trtcClient: null,
    micEnabled: false,
    aiRoundText: {},      // roundid -> 累积文本（可能是增量也可能累积）
    aiRoundLast: {},      // roundid -> 上一帧
    aiRoundBubbleId: {},  // roundid -> dom id
    userTurnText: '',
    userBubbleId: null,
  };

  // ====================== HTTP helpers ======================
  async function api(path, options = {}) {
    const resp = await fetch(path, {
      method: options.method || 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let data;
    try { data = await resp.json(); } catch { data = {}; }
    if (!resp.ok) {
      const msg = (data && (data.detail?.message || data.detail || data.msg)) || resp.statusText;
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return data;
  }

  // ====================== UI helpers ======================
  function setIndicator(key, ok, latency) {
    elIndicators.forEach((el) => {
      if (el.dataset.key !== key) return;
      const led = el.querySelector('.led');
      const lat = el.querySelector('.latency');
      led.classList.remove('led-unknown', 'led-ok', 'led-fail', 'led-pending');
      if (ok === 'pending') {
        led.classList.add('led-pending');
        lat.textContent = '...';
      } else if (ok) {
        led.classList.add('led-ok');
        lat.textContent = latency != null ? `${latency}ms` : 'ok';
      } else {
        led.classList.add('led-fail');
        lat.textContent = latency != null ? `${latency}ms` : 'fail';
      }
    });
  }

  function clearPlaceholder() {
    const p = conv.querySelector('.placeholder');
    if (p) p.remove();
  }

  function makeBubble(role, text) {
    clearPlaceholder();
    const div = document.createElement('div');
    div.className = `bubble ${role}`;
    div.textContent = text || '';
    conv.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return div;
  }

  function updateBubble(el, text) {
    if (!el) return;
    el.textContent = text;
    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function setAgentStatus(label, cls = '') {
    agentStatusEl.innerHTML = `<span class="agent-state agent-state-${cls || 'idle'}">${label}</span>`;
  }

  function updateMicUI() {
    btnMic.classList.toggle('btn-active', state.micEnabled);
    micLabel.textContent = state.micEnabled ? 'Mic on' : 'Mic off';
    micIcon.textContent = state.micEnabled ? '🔴' : '🎙️';
  }

  // ====================== Health ======================
  async function runHealthCheck() {
    ['tencent_cloud', 'trtc', 'llm'].forEach((k) => setIndicator(k, 'pending'));
    btnStart.disabled = true;
    try {
      const data = await api('/api/v1/health');
      const checks = data.checks || {};
      let allOk = true;
      for (const k of ['tencent_cloud', 'trtc', 'llm']) {
        const c = checks[k] || {};
        const ok = c.status === 'ok';
        if (!ok) allOk = false;
        setIndicator(k, ok, c.latency_ms);
        if (!ok && c.detail) console.warn(`[health] ${k}:`, c.error_code, c.detail);
      }
      state.healthy = allOk;
      btnStart.disabled = !allOk;
      if (!data.configured) {
        clearPlaceholder();
        makeBubble(
          'agent',
          `Credentials missing: ${(data.missing || []).join(', ')}\nRun: python scripts/setup-credentials.py`
        );
      }
    } catch (err) {
      ['tencent_cloud', 'trtc', 'llm'].forEach((k) => setIndicator(k, false));
      console.error('[health] error', err);
    }
  }

  // ====================== TRTC custom message handling ======================
  // type:10000 字幕（user / ai），type:10001 AI 状态
  function handleCustomMessage(data, eventUserId) {
    if (!data || typeof data !== 'object') return;

    if (data.type === 10001) {
      const stateCode = data.payload && data.payload.state;
      const map = {
        1: ['listening', 'listening'],
        2: ['thinking',  'thinking'],
        3: ['speaking',  'speaking'],
        4: ['interrupted', 'idle'],
      };
      const m = map[stateCode] || ['idle', 'idle'];
      setAgentStatus(m[0], m[1]);
      return;
    }

    if (data.type !== 10000) return;
    const text = (data.payload && data.payload.text) || '';
    const sender = data.sender || eventUserId || '';
    const end = data.payload && data.payload.end === true;
    const roundid = (data.payload && data.payload.roundid) || '';
    const isUser = sender === state.userId;

    if (isUser) {
      // 用户语音 ASR：仅 end=true 才落入气泡，避免半句乱码
      if (end && text.trim()) {
        if (!state.userBubbleId) {
          state.userBubbleId = makeBubble('user', text.trim());
        } else {
          const cur = state.userBubbleId.textContent || '';
          updateBubble(state.userBubbleId, cur ? `${cur} ${text.trim()}` : text.trim());
        }
        // 一次 user finalize 后，下一次新 ASR 进入新气泡
        setTimeout(() => { state.userBubbleId = null; }, 1500);
      }
      return;
    }

    // AI 字幕：增量/累积自适应，按 roundid 聚合到同一气泡
    if (text.trim() && roundid) {
      const last = state.aiRoundLast[roundid] || '';
      const cur  = state.aiRoundText[roundid] || '';
      const isAccumulative = last && text.startsWith(last);
      state.aiRoundText[roundid] = isAccumulative ? text : (cur + text);
      state.aiRoundLast[roundid] = text;

      let bubble = state.aiRoundBubbleId[roundid];
      if (!bubble) {
        bubble = makeBubble('agent', state.aiRoundText[roundid]);
        state.aiRoundBubbleId[roundid] = bubble;
      } else {
        updateBubble(bubble, state.aiRoundText[roundid]);
      }
    }

    if (end && roundid) {
      const bubble = state.aiRoundBubbleId[roundid];
      const finalText = state.aiRoundText[roundid] || text;
      if (bubble) updateBubble(bubble, finalText);
      delete state.aiRoundText[roundid];
      delete state.aiRoundLast[roundid];
      delete state.aiRoundBubbleId[roundid];
    }
  }

  // ====================== Start / Stop ======================
  async function startConversation() {
    btnStart.disabled = true;
    setAgentStatus('connecting...', 'thinking');
    try {
      // 1) get_config
      const cfg = await api('/api/v1/get_config', { method: 'POST', body: {} });
      const data = cfg.data || {};
      Object.assign(state, {
        sessionId: data.session_id,
        sdkAppId: data.sdk_app_id,
        roomId: parseInt(data.room_id, 10),  // TRTC enterRoom 要求 roomId 是 number（数字房间号）
        userId: data.user_id,
        userSig: data.user_sig,
        agentUserId: data.agent_user_id,
      });

      // 2) TRTC create + enterRoom
      if (typeof TRTC === 'undefined') throw new Error('TRTC Web SDK not loaded');
      state.trtcClient = TRTC.create();

      state.trtcClient.on(TRTC.EVENT.CUSTOM_MESSAGE, (event) => {
        try {
          const txt = new TextDecoder().decode(event.data);
          const parsed = JSON.parse(txt);
          handleCustomMessage(parsed, event.userId);
        } catch (e) { console.warn('parse custom msg failed', e); }
      });

      state.trtcClient.on(TRTC.EVENT.ERROR, (err) => {
        console.error('[trtc] error', err);
      });

      await state.trtcClient.enterRoom({
        roomId: state.roomId,
        scene: 'rtc',
        sdkAppId: state.sdkAppId,
        userId: state.userId,
        userSig: state.userSig,
      });

      // 3) start local audio (默认静音；用户点 Mic 后才开)
      try {
        await state.trtcClient.startLocalAudio();
        await state.trtcClient.updateLocalAudio({ mute: true });
        state.micEnabled = false;
      } catch (e) {
        console.warn('mic init failed (continue text-only):', e);
      }

      // 4) StartAIConversation
      await api('/api/v1/agent/start', {
        method: 'POST',
        body: { session_id: state.sessionId, language: 'en' },
      });

      btnStop.disabled = false;
      btnSend.disabled = false;
      btnMic.disabled = false;
      txt.disabled = false;
      txt.focus();
      updateMicUI();
      setAgentStatus('ready', 'idle');
    } catch (err) {
      console.error('[start] error', err);
      makeBubble('agent', `Start failed: ${err.message || err}`);
      setAgentStatus('error', 'idle');
      await safeExitRoom();
      btnStart.disabled = !state.healthy;
    }
  }

  async function stopConversation() {
    btnStop.disabled = true;
    btnMic.disabled = true;
    btnSend.disabled = true;
    txt.disabled = true;
    txt.value = '';
    try {
      if (state.sessionId) {
        await api('/api/v1/agent/stop', {
          method: 'POST',
          body: { session_id: state.sessionId },
        });
      }
    } catch (e) {
      console.warn('[stop] api error', e);
    }
    await safeExitRoom();
    state.sessionId = null;
    state.taskId = null;
    state.micEnabled = false;
    updateMicUI();
    setAgentStatus('idle', 'idle');
    btnStart.disabled = !state.healthy;
  }

  async function safeExitRoom() {
    try {
      if (state.trtcClient) {
        await state.trtcClient.exitRoom();
        state.trtcClient.destroy();
      }
    } catch (e) {
      console.warn('exitRoom failed', e);
    } finally {
      state.trtcClient = null;
    }
  }

  // ====================== Mic toggle ======================
  async function toggleMic() {
    if (!state.trtcClient) return;
    state.micEnabled = !state.micEnabled;
    try {
      await state.trtcClient.updateLocalAudio({ mute: !state.micEnabled });
      // 用户刚开 mic 即将说话 → 立刻打断 AI 当前 TTS（智能打断）
      if (state.micEnabled) sendInterrupt();
    } catch (e) {
      console.error('toggleMic failed', e);
      state.micEnabled = !state.micEnabled; // revert
    }
    updateMicUI();
  }

  // ====================== Text injection (端侧 → AI bot) ======================
  // 协议参考：https://cloud.tencent.com/document/product/647/115412
  //   - type:20000 = 把文字当作"用户说的话"喂给 AI bot，触发一轮 LLM → TTS + 字幕
  //     payload 字段名必须是 `message`（不是 text）
  //   - type:20001 = 立即打断 AI 当前 TTS（用户开始新一轮输入时触发智能打断）
  // 通过 TRTC sendCustomMessage(cmdId:2) 端到端发送。

  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  async function sendCustomToAgent(message) {
    if (!state.trtcClient) return false;
    try {
      await state.trtcClient.sendCustomMessage({
        cmdId: 2,
        data: new TextEncoder().encode(JSON.stringify(message)).buffer,
      });
      return true;
    } catch (e) {
      console.warn('sendCustomMessage failed', e);
      return false;
    }
  }

  function sendInterrupt() {
    return sendCustomToAgent({
      type: 20001,
      sender: state.userId,
      receiver: [state.agentUserId],
      payload: { id: uuid(), timestamp: Date.now() },
    });
  }

  async function sendText() {
    const text = (txt.value || '').trim();
    if (!text || !state.trtcClient) return;
    txt.value = '';
    // 立即渲染用户气泡
    makeBubble('user', text);

    // 1) 先打断 AI 当前 TTS（智能打断）
    sendInterrupt();

    // 2) 略延后一点点，确保 interrupt 生效，再推用户回合给 AI
    //    AI bot 收到 type:20000 后会跳过 ASR、直接走 LLM → TTS + 字幕回放
    setTimeout(() => {
      sendCustomToAgent({
        type: 20000,
        sender: state.userId,
        receiver: [state.agentUserId],
        payload: {
          id: uuid(),
          message: text,           // ← 协议规范字段名（不是 text）
          timestamp: Date.now(),
        },
      });
    }, 120);
  }

  // ====================== Bindings ======================
  btnRecheck.addEventListener('click', runHealthCheck);
  btnStart.addEventListener('click', startConversation);
  btnStop.addEventListener('click', stopConversation);
  btnMic.addEventListener('click', toggleMic);
  btnSend.addEventListener('click', sendText);

  // IME（中文输入法）兼容：拼音上屏时按空格/回车不应触发发送
  //   - compositionstart / compositionend 跟踪输入法是否在编辑中
  //   - event.isComposing 是 W3C 标准属性
  //   - event.keyCode === 229 是 IME 状态下 Enter 的兜底信号（旧浏览器）
  let imeComposing = false;
  txt.addEventListener('compositionstart', () => { imeComposing = true; });
  txt.addEventListener('compositionend',   () => { imeComposing = false; });
  txt.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (imeComposing || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    sendText();
  });

  runHealthCheck();
})();
