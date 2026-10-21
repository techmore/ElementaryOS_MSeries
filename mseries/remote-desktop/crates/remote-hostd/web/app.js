'use strict';
/* Phone client for the M-Series remote desktop.
   Pairs with a single-use link (#i=...), waits for the owner's approval,
   then shows the desktop over WebRTC and sends touch input over the "input"
   data channel. Reconnects with the same schedule as remote-core::backoff. */
(() => {
  const PROTOCOL = 1;
  const $ = (id) => document.getElementById(id);
  const screens = { pair: $('screen-pair'), wait: $('screen-wait'), ended: $('screen-ended'), stream: $('screen-stream') };
  const RESUME_KEY = 'mseries-remote-resume';
  const NAME_KEY = 'mseries-remote-name';

  const state = {
    ws: null, pc: null, dc: null,
    invite: null, resume: null,
    control: false, ended: false, attempt: 0,
    mods: new Set(), mode: 'touchpad',
    lastMoveSent: 0, waitTimer: null, retryTimer: null, statsTimer: null,
    frames: 0, lastFrames: 0, rtt: null, iceServers: [],
  };

  const show = (name) => { for (const [k, el] of Object.entries(screens)) el.hidden = k !== name; };
  const storage = {
    get: (s, k) => { try { return s.getItem(k); } catch { return null; } },
    set: (s, k, v) => { try { s.setItem(k, v); } catch { /* private mode */ } },
    del: (s, k) => { try { s.removeItem(k); } catch { /* private mode */ } },
  };

  function deviceName() {
    const saved = storage.get(localStorage, NAME_KEY);
    if (saved) return saved;
    const ua = navigator.userAgent;
    const os = /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : /Android/.test(ua) ? 'Android phone' : 'Phone';
    const browser = /CriOS|Chrome/.test(ua) ? 'Chrome' : /Firefox|FxiOS/.test(ua) ? 'Firefox' : /Safari/.test(ua) ? 'Safari' : 'browser';
    return `${os} (${browser})`;
  }

  function toast(text, ms = 2500) {
    const el = $('toast');
    el.textContent = text; el.hidden = false;
    clearTimeout(toast.t);
    toast.t = setTimeout(() => { el.hidden = true; }, ms);
  }

  function ended(title, copy) {
    state.ended = true;
    storage.del(sessionStorage, RESUME_KEY);
    teardownPeer();
    if (state.ws) { try { state.ws.close(); } catch { /* closed */ } }
    clearInterval(state.statsTimer); clearTimeout(state.retryTimer); clearInterval(state.waitTimer);
    $('ended-title').textContent = title;
    $('ended-copy').textContent = copy;
    show('ended');
  }

  /* ---------- signalling ---------- */
  function send(msg) { if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(msg)); }

  function connect() {
    if (state.ended) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    state.ws = ws;
    ws.onopen = () => {
      const hello = { type: 'hello', version: PROTOCOL, device: deviceName() };
      if (state.resume) hello.resume = state.resume; else hello.invite = state.invite;
      send(hello);
    };
    ws.onmessage = (e) => { let m; try { m = JSON.parse(e.data); } catch { return; } onServer(m); };
    ws.onclose = () => { if (state.ws === ws) { state.ws = null; if (!state.ended && state.resume) scheduleReconnect(); } };
    ws.onerror = () => { /* onclose follows */ };
  }

  function onServer(m) {
    switch (m.type) {
      case 'pending': waitScreen(m.expires_in_s); break;
      case 'granted':
        clearInterval(state.waitTimer);
        state.invite = null; state.resume = m.resume_token; state.attempt = 0;
        state.iceServers = (m.ice_servers || []).map((s) => ({ urls: s.urls, username: s.username, credential: s.credential }));
        storage.set(sessionStorage, RESUME_KEY, m.resume_token);
        setControl(m.control);
        show('stream');
        startPeer();
        break;
      case 'answer': if (state.pc) state.pc.setRemoteDescription({ type: 'answer', sdp: m.sdp }).catch(() => fail('Could not start the video.')); break;
      case 'candidate': if (state.pc) state.pc.addIceCandidate({ candidate: m.candidate, sdpMid: m.sdp_mid, sdpMLineIndex: m.sdp_mline_index }).catch(() => {}); break;
      case 'denied': ended('Not allowed', m.reason || 'The owner declined.'); break;
      case 'ended': ended('Session ended', m.reason || 'The session was ended.'); break;
      case 'error':
        if (m.code === 'resume_failed') ended('Session ended', m.message);
        else if (m.code === 'replaced') ended('Opened elsewhere', 'Another connection took over this session.');
        else if (m.code === 'busy') ended('Computer is busy', m.message);
        else if (m.code === 'invalid_invite') ended('Link not valid', m.message);
        else if (m.code === 'disabled') ended('Sharing is off', m.message);
        else if (m.code === 'capture_failed') ended('Cannot share the screen', 'The computer could not start sharing its screen. It may be locked or logged out.');
        else toast(m.message || 'Something went wrong');
        break;
    }
  }

  function waitScreen(seconds) {
    show('wait');
    let left = seconds;
    $('wait-left').textContent = left;
    clearInterval(state.waitTimer);
    state.waitTimer = setInterval(() => { left = Math.max(0, left - 1); $('wait-left').textContent = left; }, 1000);
  }

  /* ---------- reconnect (mirrors remote-core::backoff::Backoff::default) ---------- */
  function backoffDelay(attempt) {
    if (attempt >= 8) return null;
    const exp = Math.min(500 * 2 ** attempt, 15000);
    return exp * (0.5 + 0.5 * Math.random());
  }

  function scheduleReconnect() {
    if (state.ended || state.retryTimer) return;
    const d = backoffDelay(state.attempt++);
    if (d === null) { ended('Connection lost', 'The computer could not be reached.'); return; }
    $('reconnect').hidden = false;
    state.retryTimer = setTimeout(() => { state.retryTimer = null; teardownPeer(); connect(); }, d);
  }

  /* ---------- WebRTC ---------- */
  function teardownPeer() {
    if (state.dc) { try { state.dc.close(); } catch { /* closed */ } }
    if (state.pc) { try { state.pc.close(); } catch { /* closed */ } }
    state.dc = null; state.pc = null;
    clearInterval(state.statsTimer);
  }

  function fail(text) { toast(text); scheduleReconnect(); }

  async function startPeer() {
    teardownPeer();
    const pc = new RTCPeerConnection({ iceServers: state.iceServers });
    state.pc = pc;
    const tr = pc.addTransceiver('video', { direction: 'recvonly' });
    try {
      const caps = RTCRtpReceiver.getCapabilities('video');
      if (caps && tr.setCodecPreferences) {
        const h264 = caps.codecs.filter((c) => c.mimeType.toLowerCase() === 'video/h264');
        if (h264.length) tr.setCodecPreferences(h264);
      }
    } catch { /* default codec order */ }
    state.dc = pc.createDataChannel('input');
    state.dc.onmessage = (e) => { try { onHost(JSON.parse(e.data)); } catch { /* ignore */ } };
    state.dc.onopen = () => { $('reconnect').hidden = true; };
    pc.ontrack = (e) => { $('video').srcObject = e.streams[0] || new MediaStream([e.track]); $('video').play().catch(() => {}); };
    pc.onicecandidate = (e) => {
      if (e.candidate && pc.localDescription && state.offerSent) {
        send({ type: 'candidate', candidate: e.candidate.candidate, sdp_mid: e.candidate.sdpMid, sdp_mline_index: e.candidate.sdpMLineIndex });
      }
    };
    pc.onconnectionstatechange = () => {
      if (state.pc !== pc) return;
      if (pc.connectionState === 'connected') { $('reconnect').hidden = true; state.attempt = 0; startStats(); }
      else if (pc.connectionState === 'failed' || pc.connectionState === 'closed') { if (!state.ended) fail('Connection lost'); }
      else if (pc.connectionState === 'disconnected') {
        // Give ICE a few seconds to heal on its own, then restart it.
        $('reconnect').hidden = false;
        setTimeout(() => { if (state.pc === pc && pc.connectionState === 'disconnected') restartIce(); }, 4000);
      }
    };
    state.offerSent = false;
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((resolve) => {
      if (pc.iceGatheringState === 'complete') return resolve();
      const done = () => { if (pc.iceGatheringState === 'complete') { pc.removeEventListener('icegatheringstatechange', done); resolve(); } };
      pc.addEventListener('icegatheringstatechange', done);
      setTimeout(resolve, 1500);
    });
    state.offerSent = true;
    send({ type: 'offer', sdp: pc.localDescription.sdp });
  }

  async function restartIce() {
    const pc = state.pc;
    if (!pc || !state.ws) { scheduleReconnect(); return; }
    try {
      pc.restartIce();
      await pc.setLocalDescription(await pc.createOffer({ iceRestart: true }));
      state.offerSent = true;
      send({ type: 'offer', sdp: pc.localDescription.sdp });
    } catch { scheduleReconnect(); }
  }

  function startStats() {
    clearInterval(state.statsTimer);
    state.statsTimer = setInterval(async () => {
      const pc = state.pc; if (!pc) return;
      try {
        const report = await pc.getStats();
        report.forEach((r) => {
          if (r.type === 'inbound-rtp' && r.kind === 'video') {
            const fps = Math.max(0, (r.framesDecoded || 0) - state.lastFrames);
            state.lastFrames = r.framesDecoded || 0;
            $('stats').textContent = `${fps} fps${state.rtt != null ? ` · ${state.rtt} ms` : ''}`;
          }
        });
      } catch { /* stats unavailable */ }
      sendInput({ kind: 'ping', t: Date.now() }, true);
    }, 1000);
  }

  function onHost(m) {
    switch (m.kind) {
      case 'mode': setControl(m.control); break;
      case 'pong': state.rtt = Math.max(0, Date.now() - m.t); break;
      case 'rejected': if (m.reason === 'view_only') toast('View only. Ask the owner to allow control.'); else if (m.reason === 'desktop_locked') toast('The computer is locked.'); else if (m.reason !== 'rate_limited') toast('Input not accepted.'); break;
      case 'ended': ended('Session ended', m.reason || 'The owner ended the session.'); break;
    }
  }

  function setControl(control) {
    state.control = !!control;
    const chip = $('chip');
    chip.textContent = control ? 'Controlling' : 'View only';
    chip.classList.toggle('control', !!control);
  }

  /* ---------- input ---------- */
  function sendInput(ev, quiet) {
    const dc = state.dc;
    if (!dc || dc.readyState !== 'open') return;
    if (!quiet && !state.control && ev.kind !== 'ping') { toast('View only. Ask the owner to allow control.'); return; }
    dc.send(JSON.stringify(ev));
  }

  function modifiers() { return [...state.mods]; }

  function tapKey(key) {
    sendInput({ kind: 'key', key, modifiers: modifiers() });
    state.mods.clear();
    document.querySelectorAll('.mod.on').forEach((b) => b.classList.remove('on'));
  }

  const surface = $('surface');
  const pointers = new Map();
  let gesture = null;

  const SENS = 1.6;
  function videoRect() {
    const v = $('video');
    const r = v.getBoundingClientRect();
    const vw = v.videoWidth, vh = v.videoHeight;
    if (!vw || !vh) return r;
    const scale = Math.min(r.width / vw, r.height / vh);
    const w = vw * scale, h = vh * scale;
    return { left: r.left + (r.width - w) / 2, top: r.top + (r.height - h) / 2, width: w, height: h };
  }

  surface.addEventListener('pointerdown', (e) => {
    surface.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, t: performance.now() });
    if (pointers.size === 1) {
      const now = performance.now();
      const dragArm = state.lastTap && now - state.lastTap < 300;
      gesture = { fingers: 1, moved: false, start: now, drag: false, dragArm, pending: { dx: 0, dy: 0, sy: 0, sx: 0 } };
      if (state.mode === 'direct') directMove(e);
    } else if (gesture) {
      gesture.fingers = Math.max(gesture.fingers, pointers.size);
    }
  });

  surface.addEventListener('pointermove', (e) => {
    const p = pointers.get(e.pointerId);
    if (!p || !gesture) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX; p.y = e.clientY;
    if (Math.hypot(e.clientX - p.sx, e.clientY - p.sy) > 8) gesture.moved = true;
    if (pointers.size >= 2) {
      gesture.pending.sx += dx / pointers.size; gesture.pending.sy += -dy / pointers.size;
    } else if (state.mode === 'direct') {
      directMove(e);
    } else {
      if (gesture.dragArm && gesture.moved && !gesture.drag) { gesture.drag = true; sendInput({ kind: 'button', button: 'left', down: true }); }
      gesture.pending.dx += dx * SENS; gesture.pending.dy += dy * SENS;
    }
    flushSoon();
  });

  function directMove(e) {
    const r = videoRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    gesture.abs = { x, y };
    flushSoon();
  }

  let flushQueued = false;
  function flushSoon() { if (!flushQueued) { flushQueued = true; requestAnimationFrame(flush); } }
  function flush() {
    flushQueued = false;
    if (!gesture) return;
    const p = gesture.pending;
    if (Math.abs(p.dx) >= 0.5 || Math.abs(p.dy) >= 0.5) { sendInput({ kind: 'move', dx: round(p.dx), dy: round(p.dy) }); p.dx = 0; p.dy = 0; }
    if (Math.abs(p.sx) >= 1 || Math.abs(p.sy) >= 1) { sendInput({ kind: 'scroll', dx: round(p.sx), dy: round(p.sy) }); p.sx = 0; p.sy = 0; }
    if (gesture.abs) { sendInput({ kind: 'move_abs', x: gesture.abs.x, y: gesture.abs.y }); gesture.abs = null; }
  }
  const round = (n) => Math.round(n * 10) / 10;

  function release(e) {
    const p = pointers.get(e.pointerId);
    if (!p) return;
    pointers.delete(e.pointerId);
    if (!gesture) return;
    flush();
    if (pointers.size === 0) {
      const g = gesture; gesture = null;
      const quick = performance.now() - g.start < 300 && !g.moved;
      if (g.drag) sendInput({ kind: 'button', button: 'left', down: false });
      else if (quick && g.fingers === 1) { sendInput({ kind: 'click', button: 'left' }); state.lastTap = performance.now(); }
      else if (quick && g.fingers === 2) sendInput({ kind: 'click', button: 'right' });
      else if (quick && g.fingers >= 3) sendInput({ kind: 'click', button: 'middle' });
    }
  }
  surface.addEventListener('pointerup', release);
  surface.addEventListener('pointercancel', release);
  surface.addEventListener('contextmenu', (e) => e.preventDefault());

  /* ---------- toolbar ---------- */
  const kb = $('kb');
  $('btn-kb').addEventListener('click', () => { kb.focus(); });
  kb.addEventListener('beforeinput', (e) => {
    if (e.inputType === 'insertText' && e.data) { sendInput({ kind: 'text', text: e.data }); }
    else if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') tapKey('Enter');
    else if (e.inputType === 'deleteContentBackward') tapKey('Backspace');
    e.preventDefault();
  });
  kb.addEventListener('keydown', (e) => {
    const named = { Enter: 'Enter', Backspace: 'Backspace', Tab: 'Tab', Escape: 'Escape', ArrowLeft: 'ArrowLeft', ArrowRight: 'ArrowRight', ArrowUp: 'ArrowUp', ArrowDown: 'ArrowDown' }[e.key];
    if (named) { e.preventDefault(); tapKey(named); }
  });
  $('btn-keys').addEventListener('click', () => { $('keys').hidden = !$('keys').hidden; });
  $('keys').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.mod) { const m = b.dataset.mod; if (state.mods.has(m)) { state.mods.delete(m); b.classList.remove('on'); } else { state.mods.add(m); b.classList.add('on'); } }
    else if (b.dataset.key) tapKey(b.dataset.key);
  });
  $('btn-mode').addEventListener('click', () => {
    state.mode = state.mode === 'touchpad' ? 'direct' : 'touchpad';
    $('btn-mode').textContent = state.mode === 'touchpad' ? 'Touchpad' : 'Direct';
  });
  $('btn-full').addEventListener('click', () => {
    const el = document.documentElement;
    if (document.fullscreenElement) document.exitFullscreen(); else if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  });
  $('btn-end').addEventListener('click', () => { send({ type: 'bye' }); ended('Disconnected', 'You ended the session.'); });
  $('btn-cancel').addEventListener('click', () => { send({ type: 'bye' }); ended('Cancelled', 'You cancelled the request.'); });
  window.addEventListener('online', () => { if (state.resume && !state.ended) { clearTimeout(state.retryTimer); state.retryTimer = null; state.attempt = 0; if (state.pc) restartIce(); else { teardownPeer(); connect(); } } });

  let wakeLock = null;
  async function keepAwake() { try { if ('wakeLock' in navigator && !wakeLock) { wakeLock = await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release', () => { wakeLock = null; }); } } catch { /* optional */ } }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && !state.ended && state.resume) keepAwake(); });

  /* ---------- start ---------- */
  function init() {
    const m = /(?:^|[#&])i=([A-Za-z0-9_-]{16,64})/.exec(location.hash);
    if (m) {
      state.invite = m[1];
      // The secret never stays in the address bar, history or a shared screenshot.
      history.replaceState(null, '', location.pathname);
      $('device-name').value = deviceName();
      $('name-field').hidden = false; $('btn-connect').hidden = false;
      show('pair');
      $('btn-connect').addEventListener('click', () => {
        const name = $('device-name').value.trim().slice(0, 64) || deviceName();
        storage.set(localStorage, NAME_KEY, name);
        keepAwake(); connect();
      });
      return;
    }
    const resume = storage.get(sessionStorage, RESUME_KEY);
    if (resume) { state.resume = resume; show('stream'); $('reconnect').hidden = false; keepAwake(); connect(); return; }
    show('pair');
  }
  init();
})();
