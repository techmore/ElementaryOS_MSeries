import http from 'node:http';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { randomBytes, timingSafeEqual, createHmac } from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { homedir } from 'node:os';
import { WebSocketServer, WebSocket } from 'ws';

const root = dirname(fileURLToPath(import.meta.url));
const secret = () => randomBytes(32).toString('base64url');
const equal = (a, b) => typeof a === 'string' && typeof b === 'string' && a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));
const send = (ws, data) => { if (ws?.readyState === WebSocket.OPEN && ws.bufferedAmount < 256 * 1024) ws.send(JSON.stringify(data)); };
const stopSocket = ws => { if (ws) { ws.close(1000, 'Session ended'); const timer = setTimeout(() => ws.terminate(), 1000); timer.unref(); } };

export function iceServers(env, now = Date.now()) {
  const result = [];
  if (env.STUN_URL) result.push({ urls: env.STUN_URL });
  if (env.TURN_URL) {
    if (!env.TURN_SECRET) throw new Error('TURN_URL requires TURN_SECRET');
    if (!/^turns?:/.test(env.TURN_URL)) throw new Error('Invalid TURN_URL');
    const username = `${Math.floor(now / 1000) + 3600}:mseries`;
    result.push({ urls: env.TURN_URL, username, credential: createHmac('sha1', env.TURN_SECRET).update(username).digest('base64') });
  }
  return result;
}

class InputBridge {
  constructor(onFailure) { this.onFailure = onFailure; this.child = null; }
  start() {
    return new Promise((resolve, reject) => {
      const child = spawn('/usr/bin/python3', [join(root, 'input_bridge.py')], { stdio: ['pipe', 'pipe', 'pipe'] });
      this.child = child;
      let ready = false, buffer = '';
      const timer = setTimeout(() => { this.stop(); reject(new Error('Input bridge timed out')); }, 5000);
      child.stdout.on('data', chunk => {
        buffer += chunk;
        if (buffer.length > 8192) { this.stop(); return; }
        let end;
        while ((end = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
          try {
            const event = JSON.parse(line);
            if (event.ready) { ready = true; clearTimeout(timer); resolve(); }
            if (event.error) { clearTimeout(timer); reject(new Error(event.error)); this.onFailure(event.error); this.stop(); }
          } catch { this.stop(); }
        }
      });
      child.stderr.resume();
      const failed = () => {
        clearTimeout(timer);
        if (this.child === child) { this.child = null; this.onFailure('Input bridge stopped'); }
        if (!ready) reject(new Error('Input unavailable: requires an unlocked Pantheon/Mutter Wayland session and python3-gi'));
      };
      child.once('error', failed); child.once('exit', failed);
      child.stdin.on('error', () => {});
    });
  }
  input(event) {
    if (this.child?.stdin.writable && this.child.stdin.writableLength < 8192) this.child.stdin.write(JSON.stringify(event) + '\n');
  }
  stop() {
    const child = this.child; this.child = null;
    if (child) { child.stdin.end(); const timer = setTimeout(() => child.kill('SIGKILL'), 1500); timer.unref(); }
  }
}

export function createApp({ ownerKey, env = process.env, bridgeFactory = callback => new InputBridge(callback), clock = () => Date.now() }) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(ownerKey)) throw new Error('Owner key must be a 32-byte base64url token');
  const origins = new Set((env.MSERIES_WEBRTC_ORIGINS || 'http://127.0.0.1:8789,http://localhost:8789').split(','));
  if ([...origins].some(o => { try { const u = new URL(o); return u.origin !== o || (!['https:'].includes(u.protocol) && !['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname)); } catch { return true; } })) throw new Error('Origins must be exact HTTPS origins (HTTP allowed only for localhost)');
  const publicUrl = env.MSERIES_WEBRTC_PUBLIC_URL || '';
  if (publicUrl) {
    const u = new URL(publicUrl);
    if (!origins.has(u.origin) || u.protocol !== 'https:' || u.username || u.password || u.search || u.hash || !u.pathname.endsWith('/')) throw new Error('PUBLIC_URL must be an allowed HTTPS URL with a trailing slash');
  }
  const ice = () => iceServers(env, clock()); ice();
  let session = null;
  const clients = new Set();
  const endSession = () => {
    const old = session; session = null;
    if (old) { old.bridge.stop(); for (const ws of old.clients) stopSocket(ws); }
  };
  const broadcast = () => {
    if (session) for (const ws of session.clients) send(ws, { type: 'status', control: session.control, peers: [...session.clients].filter(c => c.role !== 'host').length });
  };
  const server = http.createServer(async (req, res) => {
    const headers = {
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
      'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
      'Permissions-Policy': 'camera=(), microphone=(), display-capture=(self)',
    };
    const reply = (code, body, type = 'application/json') => { res.writeHead(code, { ...headers, 'Content-Type': type }); res.end(type === 'application/json' ? JSON.stringify(body) : body); };
    try {
      const path = new URL(req.url, 'http://local').pathname;
      if (path === '/health' && req.method === 'GET') return reply(200, { ok: true });
      if (path === '/api/session' && req.method === 'POST') {
        if (!origins.has(req.headers.origin)) return reply(403, { error: 'Origin refused' });
        if (!equal(req.headers.authorization, `Bearer ${ownerKey}`)) return reply(401, { error: 'Owner key required' });
        endSession();
        const id = secret().slice(0, 16), tokens = { host: secret(), viewer: secret(), controller: secret() };
        const current = { id, tokens, clients: new Set(), control: false, pending: false, requested: false, expires: clock() + 4 * 3600_000 };
        current.bridge = bridgeFactory(error => { if (session !== current) return; current.control = false; current.requested = false; send(current.host, { type: 'error', error }); broadcast(); });
        session = current;
        return reply(201, { id, tokens, expires: current.expires, relayConfigured: !!env.TURN_URL, publicUrl });
      }
      const files = { '/': ['index.html', 'text/html; charset=utf-8'], '/app.mjs': ['app.mjs', 'text/javascript'], '/style.css': ['style.css', 'text/css'] };
      if (req.method === 'GET' && files[path]) {
        const [file, type] = files[path]; return reply(200, await readFile(join(root, 'public', file)), type);
      }
      return reply(404, { error: 'Not found' });
    } catch { reply(500, { error: 'Request failed' }); }
  });
  server.requestTimeout = 10_000; server.headersTimeout = 10_000;
  const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024, perMessageDeflate: false });
  server.on('upgrade', (req, socket, head) => {
    if (req.url !== '/signal' || !origins.has(req.headers.origin) || clients.size >= 16) { socket.destroy(); return; }
    wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws));
  });
  wss.on('connection', ws => {
    clients.add(ws); ws.alive = true;
    ws.on('pong', () => { ws.alive = true; });
    const authTimer = setTimeout(() => ws.terminate(), 5000);
    let bucket = 120, last = clock();
    ws.on('message', async data => {
      const now = clock(); bucket = Math.min(120, bucket + (now - last) / 1000 * 90); last = now;
      if (--bucket < 0) return ws.terminate();
      try {
        const message = JSON.parse(data);
        if (!ws.role) {
          const s = session;
          if (!s || message.type !== 'join' || message.id !== s.id || s.expires <= clock()) return ws.terminate();
          const role = Object.keys(s.tokens).find(r => equal(s.tokens[r], message.token));
          if (!role || (role !== 'host' && !s.host) || (role === 'host' && s.host) || (role === 'controller' && [...s.clients].some(c => c.role === 'controller')) || s.clients.size >= 6) return ws.terminate();
          ws.role = role; ws.peerId = secret().slice(0, 16); ws.session = s; s.clients.add(ws); clearTimeout(authTimer);
          if (role === 'host') s.host = ws;
          send(ws, { type: 'joined', role, peerId: ws.peerId, iceServers: ice() });
          if (role !== 'host') send(s.host, { type: 'peer', peerId: ws.peerId, role });
          broadcast(); return;
        }
        const s = ws.session;
        if (s !== session || s.expires <= clock()) return ws.terminate();
        if (message.type === 'signal') {
          const signal = message.signal;
          if (!signal || typeof signal !== 'object' || (signal.description && signal.description.type !== (ws.role === 'host' ? 'offer' : 'answer'))) return;
          if (ws.role === 'host') {
            const peer = [...s.clients].find(c => c.peerId === message.to && c !== ws);
            if (peer) send(peer, { type: 'signal', from: ws.peerId, signal });
          } else send(s.host, { type: 'signal', from: ws.peerId, signal });
        } else if (message.type === 'control' && ws.role === 'host') {
          if (message.enabled === false) { s.control = false; s.requested = false; s.bridge.stop(); broadcast(); }
          else if (message.enabled === true && !s.control && !s.pending) {
            s.pending = true; s.requested = true;
            try {
              await s.bridge.start();
              if (session !== s || !s.requested) { s.bridge.stop(); return; }
              s.control = true; broadcast();
            } catch (error) { send(ws, { type: 'error', error: error.message }); }
            finally { s.pending = false; }
          }
        } else if (message.type === 'input' && ws.role === 'controller' && s.control) s.bridge.input(message.event);
        else if (message.type === 'stop' && ws.role === 'host') endSession();
      } catch { send(ws, { type: 'error', error: 'Invalid message' }); }
    });
    ws.on('error', () => {});
    ws.on('close', () => {
      clearTimeout(authTimer); clients.delete(ws);
      const s = ws.session;
      if (!s) return;
      s.clients.delete(ws);
      if (s !== session) return;
      if (ws.role === 'host') endSession();
      else { if (ws.role === 'controller') { s.control = false; s.requested = false; s.bridge.stop(); } send(s.host, { type: 'left', peerId: ws.peerId }); broadcast(); }
    });
  });
  const timer = setInterval(() => {
    if (session?.expires <= clock()) endSession();
    for (const ws of clients) { if (!ws.alive) ws.terminate(); else { ws.alive = false; ws.ping(); } }
  }, 15_000); timer.unref();
  const close = async () => { clearInterval(timer); endSession(); for (const ws of clients) ws.terminate(); wss.close(); await new Promise(resolve => server.close(resolve)); };
  return { server, close };
}

async function main() {
  const config = join(process.env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'mseries-webrtc');
  await mkdir(config, { recursive: true, mode: 0o700 });
  const keyFile = join(config, 'owner.key');
  let ownerKey;
  try { ownerKey = (await readFile(keyFile, 'utf8')).trim(); }
  catch (error) { if (error.code !== 'ENOENT') throw error; ownerKey = secret(); await writeFile(keyFile, ownerKey + '\n', { mode: 0o600, flag: 'wx' }); }
  if ((await stat(keyFile)).mode & 0o077) throw new Error('owner.key must be readable only by its owner (chmod 600)');
  const app = createApp({ ownerKey });
  app.server.listen(Number(process.env.PORT || 8789), process.env.HOST || '127.0.0.1', () => console.log('M-series WebRTC ready; use mseries-webrtc-open to open the host page.'));
  for (const sig of ['SIGTERM', 'SIGINT']) process.once(sig, async () => { await app.close(); process.exit(0); });
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main().catch(error => { console.error(error.message); process.exitCode = 1; });
