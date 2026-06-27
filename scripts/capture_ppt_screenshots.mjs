import { spawn } from 'node:child_process';
import { mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const chromePath = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const outputDir = 'C:/Users/User/Desktop/ppt_asset_v1';
const baseUrl = 'http://127.0.0.1:3000';
const width = 1600;
const height = 900;
const port = 9333;
const userDataDir = path.join(tmpdir(), `ppt-shot-${Date.now()}`);

await mkdir(userDataDir, { recursive: true });

const chrome = spawn(chromePath, [
  '--headless=new',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${userDataDir}`,
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  '--hide-scrollbars',
  `--window-size=${width},${height}`,
  'about:blank',
], { stdio: 'ignore' });

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function waitForChrome() {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      return await fetchJson(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' });
    } catch {
      await sleep(250);
    }
  }
  throw new Error('Chrome DevTools endpoint did not start.');
}

const target = await waitForChrome();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
  ws.addEventListener('error', reject, { once: true });
});

let nextId = 1;
const pending = new Map();
const events = new Map();

ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
    return;
  }
  const listeners = events.get(message.method);
  if (listeners) listeners.splice(0).forEach((resolve) => resolve(message.params));
});

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function waitForEvent(method) {
  return new Promise((resolve) => {
    const listeners = events.get(method) || [];
    listeners.push(resolve);
    events.set(method, listeners);
  });
}

async function navigate(url) {
  const loaded = waitForEvent('Page.loadEventFired');
  await send('Page.navigate', { url });
  await loaded;
  await sleep(1400);
}

async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result.value;
}

async function save(name, scrollY = 0) {
  await evaluate(`window.scrollTo(0, ${Math.max(0, Math.floor(scrollY))}); undefined`);
  await sleep(600);
  const screenshot = await send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(outputDir, name), Buffer.from(screenshot.data, 'base64'));
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });

  await navigate(`${baseUrl}/rating-trends`);
  const positions = await evaluate(`(() => {
    const topOf = (selector, offset = 100) => {
      const element = document.querySelector(selector);
      if (!element) return 0;
      const rect = element.getBoundingClientRect();
      return Math.max(0, Math.floor(rect.top + window.scrollY - offset));
    };
    return {
      chart: topOf('.ratingChartPanel', 90),
      decision: topOf('.ratingDecisionPanel', 120),
      report: topOf('.ratingReportPanel', 100)
    };
  })()`);

  await save('09a_rating_risk_overview_16x9.png', 0);
  await save('09b_rating_risk_chart_and_ai_report_16x9.png', positions.chart);
  await save('09c_rating_risk_classification_threshold_16x9.png', positions.decision);
  await save('09d_rating_risk_ai_report_panel_16x9.png', positions.report);

  await navigate(`${baseUrl}/reports`);
  await save('10_ai_report_generation_ui_16x9.png', 0);

  console.log(JSON.stringify({ outputDir, positions, size: `${width}x${height}` }, null, 2));
} finally {
  ws.close();
  chrome.kill();
  await sleep(500);
  await rm(userDataDir, { recursive: true, force: true }).catch(() => undefined);
}
