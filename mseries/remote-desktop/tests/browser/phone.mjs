// Headless phone-browser test: drives the real web client in Chrome with
// mobile emulation and touch. Requires playwright-core on NODE_PATH and a
// Chrome/Chromium with H.264 decode (set CHROME=/path). Prints one JSON line.
//
//   node phone.mjs <invite-link> <mode>
//     mode "pair"    : connect, wait for approval, verify video + view-only toast
//     mode "control" : same, then tap/drag/type once the owner granted control
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');

const [link, mode = 'pair'] = process.argv.slice(2);
const chrome = process.env.CHROME || '/usr/bin/google-chrome';
const log = (...a) => process.stderr.write(a.join(' ') + '\n');

const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

const out = { ok: false };
try {
  await page.goto(link);
  await page.waitForSelector('#btn-connect:not([hidden])', { timeout: 5000 });
  out.hashCleared = !(await page.evaluate(() => location.hash));
  await page.fill('#device-name', 'Headless Pixel');
  await page.click('#btn-connect');
  await page.waitForSelector('#screen-wait:not([hidden])', { timeout: 5000 });
  out.sawWaitScreen = true;
  await page.waitForSelector('#screen-stream:not([hidden])', { timeout: 30000 });

  // Wait for decoded video, then read the frame counter strip off a canvas.
  await page.waitForFunction(() => { const v = document.getElementById('video'); return v && v.videoWidth > 0 && v.readyState >= 2; }, null, { timeout: 20000 });
  const readCounter = () => page.evaluate(() => {
    const v = document.getElementById('video');
    const c = document.createElement('canvas'); c.width = v.videoWidth; c.height = v.videoHeight;
    const g = c.getContext('2d'); g.drawImage(v, 0, 0);
    const cell = Math.floor(c.width / 16); let n = 0;
    for (let b = 0; b < 16; b++) { const px = g.getImageData(b * cell + (cell >> 1), 12, 1, 1).data; n = (n << 1) | (px[0] > 125 ? 1 : 0); }
    return { n, w: v.videoWidth, h: v.videoHeight };
  });
  const samples = [];
  for (let i = 0; i < 4; i++) { samples.push(await readCounter()); await page.waitForTimeout(400); }
  out.size = [samples[0].w, samples[0].h];
  out.counters = samples.map((s) => s.n);
  out.advancing = samples.every((s, i) => i === 0 || s.n > samples[i - 1].n);
  out.chip = await page.textContent('#chip');

  // Touch: a tap in view-only must be refused with a visible explanation.
  const box = await page.locator('#surface').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  if (mode === 'pair') {
    await page.touchscreen.tap(cx, cy);
    await page.waitForSelector('#toast:not([hidden])', { timeout: 3000 });
    out.viewOnlyToast = (await page.textContent('#toast')).includes('View only');
  } else {
    await page.waitForFunction(() => document.getElementById('chip').textContent === 'Controlling', null, { timeout: 15000 });
    out.chipAfter = await page.textContent('#chip');
    await page.touchscreen.tap(cx, cy);                        // click
    await page.waitForTimeout(150);
    // Drag with one finger: relative motion.
    const cdp = await context.newCDPSession(page);
    const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
    await touch('touchStart', [[cx, cy]]);
    for (let i = 1; i <= 8; i++) { await touch('touchMove', [[cx + i * 12, cy + i * 6]]); await page.waitForTimeout(16); }
    await touch('touchEnd', []);
    // Two-finger tap = right click.
    await touch('touchStart', [[cx - 20, cy], [cx + 20, cy]]);
    await page.waitForTimeout(60);
    await touch('touchEnd', []);
    // Typing through the on-screen keyboard path.
    await page.evaluate(() => document.getElementById('kb').dispatchEvent(new InputEvent('beforeinput', { inputType: 'insertText', data: 'hi', cancelable: true, bubbles: true })));
    await page.click('#btn-keys');
    await page.click('[data-key="Escape"]');
    await page.waitForTimeout(400);
  }
  out.errors = errors;
  out.ok = true;
} catch (e) {
  out.error = String(e);
  out.errors = errors;
  try { await page.screenshot({ path: process.env.FAIL_SHOT || '/tmp/phone-fail.png' }); } catch { /* ignore */ }
}
console.log(JSON.stringify(out));
await browser.close();
process.exit(out.ok ? 0 : 1);
