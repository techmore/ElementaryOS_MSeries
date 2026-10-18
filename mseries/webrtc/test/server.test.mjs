import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { WebSocket } from 'ws';
import { createApp, iceServers } from '../server.mjs';

async function fixture(t) {
  const ownerKey = randomBytes(32).toString('base64url');
  const origin = 'http://localhost:8789', events = [], bridges = [];
  let now = Date.now();
  const app = createApp({ ownerKey, clock: () => now, bridgeFactory: () => {
    const bridge = { start: async () => { events.push('start'); }, input: e => events.push(e), stop: () => events.push('stop') }; bridges.push(bridge); return bridge;
  }});
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${app.server.address().port}`;
  t.after(() => app.close());
  const create = async (key = ownerKey) => fetch(`${url}/api/session`, { method: 'POST', headers: { origin, authorization: `Bearer ${key}` } });
  const session = await (await create()).json();
  const connections = [];
  async function connect(role, token = session.tokens[role]) {
    const ws = new WebSocket(url.replace('http:', 'ws:') + '/signal', { origin });
    const messages = [];
    ws.on('message', data => messages.push(JSON.parse(data)));
    await new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', reject); });
    ws.send(JSON.stringify({ type: 'join', id: session.id, token })); connections.push(ws);
    return { ws, messages, send: data => ws.send(JSON.stringify(data)) };
  }
  const until = async predicate => { for (let i = 0; i < 100; i++) { if (predicate()) return; await new Promise(r => setTimeout(r, 5)); } assert.fail('Timed out'); };
  return { app, ownerKey, url, origin, session, create, connect, until, events, bridges, advance: ms => { now += ms; } };
}

test('owner authentication and origin required; no capabilities in static HTML', async t => {
  const f = await fixture(t);
  assert.equal((await f.create('wrong')).status, 401);
  assert.equal((await fetch(f.url + '/api/session', { method: 'POST', headers: { authorization: `Bearer ${f.ownerKey}` } })).status, 403);
  const res = await fetch(f.url); const html = await res.text();
  assert.ok(res.headers.get('content-security-policy').includes("frame-ancestors 'none'"));
  assert.ok(!html.includes(f.ownerKey));
  assert.equal((await fetch(f.url + '/input_bridge.py')).status, 404);
});

test('viewer signaling works but viewer cannot inject input, enable control, or stop session', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  const viewer = await f.connect('viewer');
  await f.until(() => host.messages.some(m => m.type === 'peer'));
  viewer.send({ type: 'input', event: { kind: 'text', text: 'forbidden' } });
  viewer.send({ type: 'control', enabled: true }); viewer.send({ type: 'stop' });
  viewer.send({ type: 'signal', signal: { description: { type: 'answer', sdp: 'test' } } });
  await f.until(() => host.messages.some(m => m.type === 'signal'));
  assert.deepEqual(f.events, []);
  assert.equal(host.ws.readyState, WebSocket.OPEN);
});

test('control needs host opt-in; stop revokes all bearer links', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  const controller = await f.connect('controller');
  await f.until(() => controller.messages.some(m => m.type === 'joined'));
  controller.send({ type: 'input', event: { kind: 'click' } });
  host.send({ type: 'control', enabled: true });
  await f.until(() => controller.messages.some(m => m.control === true));
  assert.deepEqual(f.events, ['start']);
  controller.send({ type: 'input', event: { kind: 'click', button: 'left' } });
  await f.until(() => f.events.length === 2);
  host.send({ type: 'stop' });
  await f.until(() => controller.ws.readyState === WebSocket.CLOSED);
  const expired = await f.connect('viewer');
  await f.until(() => expired.ws.readyState === WebSocket.CLOSED);
  assert.ok(f.events.includes('stop'));
});

test('disable during bridge startup cannot enable late control', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  let ready; f.bridges[0].start = () => new Promise(resolve => { ready = resolve; });
  host.send({ type: 'control', enabled: true }); await f.until(() => ready);
  host.send({ type: 'control', enabled: false });
  await new Promise(r => setTimeout(r, 15)); ready();
  await new Promise(r => setTimeout(r, 15));
  assert.ok(!host.messages.some(m => m.control === true));
});

test('only one controller; controller disconnect stops control', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  const a = await f.connect('controller'); await f.until(() => a.messages.some(m => m.type === 'joined'));
  const b = await f.connect('controller'); await f.until(() => b.ws.readyState === WebSocket.CLOSED);
  host.send({ type: 'control', enabled: true }); await f.until(() => a.messages.some(m => m.control === true));
  a.ws.close(); await f.until(() => host.messages.at(-1)?.control === false);
  assert.ok(f.events.includes('stop'));
});

test('new session and expiry invalidate previous sessions', async t => {
  const f = await fixture(t), host = await f.connect('host'); await f.until(() => host.messages.some(m => m.type === 'joined'));
  const current = await (await f.create()).json(); await f.until(() => host.ws.readyState === WebSocket.CLOSED);
  const old = await f.connect('host'); await f.until(() => old.ws.readyState === WebSocket.CLOSED);
  f.advance(4 * 3600_000 + 1);
  const expired = new WebSocket(f.url.replace('http:', 'ws:') + '/signal', { origin: f.origin });
  await new Promise(resolve => expired.once('open', resolve));
  expired.send(JSON.stringify({ type: 'join', id: current.id, token: current.tokens.host }));
  await f.until(() => expired.readyState === WebSocket.CLOSED);
});

test('TURN uses expiring credentials and refuses partial configuration', () => {
  assert.deepEqual(iceServers({}), []);
  assert.throws(() => iceServers({ TURN_URL: 'turn:test:3478' }));
  const [turn] = iceServers({ TURN_URL: 'turn:relay.example:3478', TURN_SECRET: 'private' }, 1000);
  assert.equal(turn.username, '3601:mseries'); assert.ok(turn.credential); assert.notEqual(turn.credential, 'private');
});

test('origin configuration rejects cleartext LAN origins and unknown public origin', () => {
  const ownerKey = randomBytes(32).toString('base64url');
  assert.throws(() => createApp({ ownerKey, env: { MSERIES_WEBRTC_ORIGINS: 'http://192.168.1.1' } }));
  assert.throws(() => createApp({ ownerKey, env: { MSERIES_WEBRTC_PUBLIC_URL: 'https://unknown.example' } }));
});

test('public random-path URL preserves origin isolation', () => {
  const ownerKey = randomBytes(32).toString('base64url');
  const app = createApp({ ownerKey, env: { MSERIES_WEBRTC_ORIGINS: 'https://mdm.stoverparc.org', MSERIES_WEBRTC_PUBLIC_URL: 'https://mdm.stoverparc.org/abcdef123456/' } });
  app.close();
  assert.throws(() => createApp({ ownerKey, env: { MSERIES_WEBRTC_ORIGINS: 'https://mdm.stoverparc.org', MSERIES_WEBRTC_PUBLIC_URL: 'https://mdm.stoverparc.org/no-trailing-slash' } }));
});

test('host disconnect revokes all links and tears down input', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  const viewer = await f.connect('viewer'); await f.until(() => viewer.messages.some(m => m.type === 'joined'));
  host.ws.close(); await f.until(() => viewer.ws.readyState === WebSocket.CLOSED);
  assert.ok(f.events.includes('stop'));
  const replay = await f.connect('host'); await f.until(() => replay.ws.readyState === WebSocket.CLOSED);
});

test('foreign-origin socket upgrades are rejected before authentication', async t => {
  const f = await fixture(t);
  const ws = new WebSocket(f.url.replace('http:', 'ws:') + '/signal', { origin: 'https://untrusted.example' });
  await new Promise(resolve => ws.once('error', resolve));
  assert.notEqual(ws.readyState, WebSocket.OPEN);
});

test('one host, four friends and a phone stay within the peer bound', async t => {
  const f = await fixture(t), host = await f.connect('host');
  await f.until(() => host.messages.some(m => m.type === 'joined'));
  const phone = await f.connect('controller'); await f.until(() => phone.messages.some(m => m.type === 'joined'));
  for (let i = 0; i < 4; i++) { const viewer = await f.connect('viewer'); await f.until(() => viewer.messages.some(m => m.type === 'joined')); }
  const extra = await f.connect('viewer'); await f.until(() => extra.ws.readyState === WebSocket.CLOSED);
});
