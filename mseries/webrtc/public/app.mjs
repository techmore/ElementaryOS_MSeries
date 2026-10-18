const $ = id => document.getElementById(id);
const status = message => { $('status').textContent = message; };
const fragment = new URLSearchParams(location.hash.slice(1));
const ownerKey = fragment.get('owner') || '';
const invitation = fragment.get('join');
history.replaceState(null, '', location.pathname);
$('owner-key').value = ownerKey;
if (invitation) { $('host').hidden = true; status('Connecting to shared desktop…'); }
let socket, source, credentials, role, ice = [], active = false, control = false, recorder, recordingBytes = 0, recordingUrl;
const peers = new Map();
const send = message => { if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 65536) socket.send(JSON.stringify(message)); };
function showStream(stream) {
  $('screen').srcObject = stream;
  $('empty').hidden = !!stream;
  $('record').disabled = !stream || !!recorder;
  $('sound').hidden = !stream?.getAudioTracks().length || role === 'host';
  if (stream) $('screen').play().catch(() => { $('sound').hidden = false; });
}
function controls() { $('controls').hidden = role !== 'controller' || !control; $('allow-control').checked = control; $('control-invite').hidden = !control; }
function peer(id) {
  if (peers.has(id)) return peers.get(id);
  const pc = new RTCPeerConnection({ iceServers: ice });
  const p = { pc, queue: Promise.resolve(), candidates: [] }; peers.set(id, p);
  pc.onicecandidate = event => { if (event.candidate) send({ type: 'signal', to: id, signal: { candidate: event.candidate.toJSON() } }); };
  pc.ontrack = event => {
    const stream = $('screen').srcObject || new MediaStream();
    if (!stream.getTracks().includes(event.track)) stream.addTrack(event.track);
    showStream(stream);
  };
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'connected') status(role === 'host' ? `Sharing · ${peers.size} connected device(s)` : 'Connected to desktop');
    if (pc.connectionState === 'failed') status('Video connection failed. Check the TURN relay and open a fresh invite.');
  };
  return p;
}
function enqueue(p, callback) { p.queue = p.queue.then(callback).catch(error => status(error.message)); return p.queue; }
async function connect(id, token) {
  const signaling = new URL('signal', location.href);
  signaling.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(signaling);
  socket.onopen = () => send({ type: 'join', id, token });
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === 'joined') { role = message.role; ice = message.iceServers; active = true; status(role === 'host' ? 'Sharing. Copy a link to connect another device.' : 'Waiting for screen…'); }
    if (message.type === 'status') { control = message.control; controls(); }
    if (message.type === 'error') { status(message.error); $('allow-control').disabled = false; controls(); }
    if (message.type === 'peer' && source) {
      const p = peer(message.peerId);
      enqueue(p, async () => {
        for (const track of source.getTracks()) {
          const sender = p.pc.addTrack(track, source);
          if (track.kind === 'video') { const parameters = sender.getParameters(); parameters.encodings ||= [{}]; parameters.encodings[0].maxBitrate = 3_000_000; await sender.setParameters(parameters); }
        }
        await p.pc.setLocalDescription(await p.pc.createOffer());
        send({ type: 'signal', to: message.peerId, signal: { description: p.pc.localDescription.toJSON() } });
      });
    }
    if (message.type === 'signal') {
      const p = peer(message.from);
      enqueue(p, async () => {
        const { description, candidate } = message.signal;
        if (description) {
          await p.pc.setRemoteDescription(description);
          for (const c of p.candidates.splice(0)) await p.pc.addIceCandidate(c);
          if (description.type === 'offer') {
            await p.pc.setLocalDescription(await p.pc.createAnswer());
            send({ type: 'signal', signal: { description: p.pc.localDescription.toJSON() } });
          }
        } else if (candidate) {
          if (p.pc.remoteDescription) await p.pc.addIceCandidate(candidate); else if (p.candidates.length < 100) p.candidates.push(candidate);
        }
      });
    }
    if (message.type === 'left') { peers.get(message.peerId)?.pc.close(); peers.delete(message.peerId); }
  };
  socket.onerror = () => status('Could not reach the sharing service.');
  socket.onclose = () => { cleanup(); status('Session ended. Open a new invitation to reconnect.'); };
}
async function startSharing(stream) {
  if (source || active) throw new Error('Already sharing');
  source = stream;
  try {
    const response = await fetch(new URL('api/session', location.href), { method: 'POST', headers: { Authorization: `Bearer ${$('owner-key').value.trim()}` } });
    if (!response.ok) throw new Error('Host authentication failed. Open the desktop launcher.');
    credentials = await response.json(); role = 'host';
    const publicBase = new URL(location.href);
    // The public origin is supplied by the operator, never by an invite sender.
    const publicUrl = credentials.publicUrl;
    if (publicUrl) publicBase.href = publicUrl;
    publicBase.search = '';
    if (!publicBase.pathname.endsWith('/')) publicBase.pathname += '/';
    for (const [field, token] of [['view-link', credentials.tokens.viewer], ['control-link', credentials.tokens.controller]]) {
      publicBase.hash = new URLSearchParams({ join: `${credentials.id}.${token}` }).toString(); $(field).value = publicBase.href;
    }
    $('owner-key').value = ''; $('owner-key').parentElement.hidden = true;
    $('connection-note').textContent = credentials.relayConfigured ? 'TURN relay configured for networks that block direct video.' : 'No TURN relay configured. Same-network connections may work; remote networks still need qualification.';
    $('invites').hidden = false; $('stop').disabled = false; $('share').disabled = true;
    showStream(source);
    source.getVideoTracks()[0].onended = stopSharing;
    await connect(credentials.id, credentials.tokens.host);
  } catch (error) { cleanup(); throw error; }
}
function cleanup() {
  active = false; control = false;
  if (recorder && recorder.state !== 'inactive') recorder.stop();
  source?.getTracks().forEach(track => track.stop()); source = null;
  for (const p of peers.values()) p.pc.close(); peers.clear();
  const remote = $('screen').srcObject; remote?.getTracks().forEach(track => track.stop()); showStream(null);
  $('invites').hidden = true; $('stop').disabled = true; $('share').disabled = false; $('allow-control').checked = false; controls();
  $('view-link').value = ''; $('control-link').value = ''; credentials = null;
  if (!invitation) { $('owner-key').parentElement.hidden = false; $('owner-key').value = ownerKey; }
}
function stopSharing() { send({ type: 'stop' }); socket?.close(); cleanup(); status('Sharing stopped. All links revoked.'); }
$('share').onclick = async () => {
  try {
    if (!navigator.mediaDevices?.getDisplayMedia) throw new Error('Screen capture requires a desktop browser on HTTPS or localhost.');
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 15, max: 30 } }, audio: $('audio').checked });
    await startSharing(stream);
  } catch (error) { status(error.message); }
};
$('stop').onclick = stopSharing;
$('allow-control').onchange = () => { send({ type: 'control', enabled: $('allow-control').checked }); };
for (const [button, field] of [['copy-view', 'view-link'], ['copy-control', 'control-link']]) $(button).onclick = () => navigator.clipboard.writeText($(field).value).then(() => status('Invite copied.')).catch(() => { $(field).select(); status('Select and copy the invitation link.'); });
$('sound').onclick = () => { $('screen').muted = false; $('screen').play().catch(error => status(error.message)); };
$('record').onclick = () => {
  try {
    const stream = $('screen').srcObject;
    const mimeType = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/mp4', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
    if (!stream || !mimeType) throw new Error('Recording is unavailable in this browser.');
    if (recordingUrl) { URL.revokeObjectURL(recordingUrl); recordingUrl = null; }
    const chunks = []; recordingBytes = 0; $('download').hidden = true;
    recorder = new MediaRecorder(stream, { mimeType });
    recorder.ondataavailable = event => {
      if (!event.data.size) return;
      chunks.push(event.data); recordingBytes += event.data.size;
      if (recordingBytes >= 256 * 1024 * 1024 && recorder?.state === 'recording') { recorder.stop(); status('Recording reached 256 MiB. Save it before starting another.'); }
    };
    recorder.onstop = () => {
      recordingUrl = URL.createObjectURL(new Blob(chunks, { type: mimeType }));
      $('download').href = recordingUrl; $('download').download = `mseries-screen-${new Date().toISOString().replaceAll(':', '-')}.${mimeType.includes('mp4') ? 'mp4' : 'webm'}`;
      $('download').hidden = recordingBytes === 0;
      $('record-note').textContent = 'Recording ready. Save it before closing this page.'; $('record-note').classList.remove('recording');
      recorder = null; $('record').disabled = !$('screen').srcObject; $('finish-record').disabled = true;
    };
    recorder.onerror = () => { status('Recording failed. Save any partial recording.'); if (recorder?.state !== 'inactive') recorder.stop(); };
    recorder.start(1000); $('record').disabled = true; $('finish-record').disabled = false;
    $('record-note').textContent = '● Recording locally · automatic stop at 256 MiB'; $('record-note').classList.add('recording');
  } catch (error) { status(error.message); }
};
$('finish-record').onclick = () => recorder?.stop();
const input = event => { if (role === 'controller' && control) send({ type: 'input', event }); };
let pointer, motion = { dx: 0, dy: 0 }, scheduled = false;
$('touchpad').onpointerdown = event => { $('touchpad').setPointerCapture(event.pointerId); pointer = { x: event.clientX, y: event.clientY, total: 0 }; };
$('touchpad').onpointermove = event => {
  if (!pointer) return;
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
  pointer.total += Math.abs(dx) + Math.abs(dy); pointer.x = event.clientX; pointer.y = event.clientY;
  motion.dx += dx; motion.dy += dy;
  if (!scheduled) { scheduled = true; requestAnimationFrame(() => { input({ kind: 'move', dx: Math.max(-1000, Math.min(1000, motion.dx)), dy: Math.max(-1000, Math.min(1000, motion.dy)) }); motion = { dx: 0, dy: 0 }; scheduled = false; }); }
};
$('touchpad').onpointerup = () => { if (pointer?.total < 8) input({ kind: 'click', button: 'left' }); pointer = null; };
$('touchpad').onpointercancel = () => { pointer = null; };
$('touchpad').onwheel = event => { event.preventDefault(); input({ kind: 'scroll', dx: Math.max(-1000, Math.min(1000, event.deltaX)), dy: Math.max(-1000, Math.min(1000, event.deltaY)) }); };
$('touchpad').onkeydown = event => {
  if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key)) return;
  event.preventDefault(); input({ kind: 'key', key: event.key, modifiers: ['ctrl', 'alt', 'shift', 'meta'].filter(m => event[`${m}Key`]) });
};
$('left-click').onclick = () => input({ kind: 'click', button: 'left' });
$('right-click').onclick = () => input({ kind: 'click', button: 'right' });
$('scroll-up').onclick = () => input({ kind: 'scroll', dx: 0, dy: -100 });
$('scroll-down').onclick = () => input({ kind: 'scroll', dx: 0, dy: 100 });
$('send-text').onclick = () => { if ($('text').value) { input({ kind: 'text', text: $('text').value }); $('text').value = ''; } };
for (const button of document.querySelectorAll('[data-key]')) button.onclick = () => input({ kind: 'key', key: button.dataset.key });
window.addEventListener('pagehide', () => { socket?.close(); cleanup(); });
window.addEventListener('beforeunload', event => { if (active || recorder || recordingUrl) { event.preventDefault(); event.returnValue = ''; } });
if (invitation) {
  const [id, token] = invitation.split('.');
  if (/^[A-Za-z0-9_-]{16}$/.test(id || '') && /^[A-Za-z0-9_-]{43}$/.test(token || '')) connect(id, token); else status('Invalid invitation. Ask the host for a new link.');
}
// Export the media attachment for browser tests with a synthetic canvas stream.
export { startSharing, peers };
