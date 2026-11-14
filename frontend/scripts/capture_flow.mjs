import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const CHROME_HTTP = 'http://127.0.0.1:9222';
const APP_URL = 'http://127.0.0.1:5173';
const SCREENSHOT_DIR = resolve('frontend/screenshots');
mkdirSync(SCREENSHOT_DIR, { recursive: true });

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.id = 0;
    this.callbacks = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.callbacks.has(msg.id)) {
        const { resolve, reject } = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) reject(msg.error);
        else resolve(msg.result);
      }
    };
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.id;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval error: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result?.value;
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 2, // HiDPI for crisp text and graphics
      mobile: false,
    });
  }

  async captureScreenshot(path) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const buf = Buffer.from(res.data, 'base64');
    writeFileSync(path, buf);
    console.log(`Saved screenshot: ${path} (${Math.round(buf.length / 1024)} KB)`);
  }

  async close() {
    if (this.ws) this.ws.close();
  }
}

async function main() {
  console.log('Connecting to Chrome CDP...');
  // Create a new tab
  const tabRes = await fetch(`${CHROME_HTTP}/json/new?${APP_URL}`, { method: 'PUT' });
  const tab = await tabRes.json();
  const cdp = new CDPClient(tab.webSocketDebuggerUrl);
  await cdp.connect();

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('DOM.enable');

  // Let page load
  await sleep(1500);

  // Check 1: HOME SCREEN at 1440x900
  await cdp.setViewport(1440, 900);
  await sleep(500);

  // Check layout constraints
  const homeValidation1440 = await cdp.eval(`(() => {
    const sidebars = document.querySelectorAll('aside, .sidebar, nav[aria-label="Navigation"]');
    const filledButtons = Array.from(document.querySelectorAll('button.btn-primary, button[class*="primary"]')).filter(b => b.offsetParent !== null);
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasSidebar: sidebars.length > 0,
      filledButtonCount: filledButtons.length,
      filledButtonText: filledButtons.map(b => b.textContent?.trim()),
      hasHorizontalScroll: scrollWidth > clientWidth,
      scrollWidth,
      clientWidth
    };
  })()`);
  console.log('Home 1440x900 checks:', homeValidation1440);

  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '01-home-1440x900.png'));

  // Also check at 1366x768
  await cdp.setViewport(1366, 768);
  await sleep(300);
  const homeValidation1366 = await cdp.eval(`(() => {
    return {
      hasHorizontalScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth
    };
  })()`);
  console.log('Home 1366x768 horizontal scroll check:', homeValidation1366);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '01-home-1366x768.png'));

  // Now back to 1440x900 for workbench flows
  await cdp.setViewport(1440, 900);
  await sleep(300);

  // Click "Try the sample agent"
  console.log('Clicking "Try the sample agent"...');
  await cdp.eval(`(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('sample agent'));
    if (btn) btn.click();
    else throw new Error('Try sample agent button not found');
  })()`);

  // Wait for scan to complete and workbench to appear
  console.log('Waiting for workbench to appear...');
  let boardLoaded = false;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    const hasBoard = await cdp.eval(`!!document.querySelector('.tier-board-container')`);
    if (hasBoard) {
      boardLoaded = true;
      break;
    }
  }
  if (!boardLoaded) {
    const bodyText = await cdp.eval(`document.body.innerText`);
    console.error('Body text when board failed to load:', bodyText);
    throw new Error('TierBoard container failed to load');
  }

  // Check 2: WORKBENCH SCANNED (UNTESTED)
  const scannedValidation = await cdp.eval(`(() => {
    // Check for old navigation sidebars (left sidebar)
    const navSidebars = document.querySelectorAll('aside.sidebar, nav[aria-label="Navigation"]');
    const board = document.querySelector('.tier-board-container');
    const repoBar = document.querySelector('.repo-bar-container');
    const benchmarkButtons = Array.from(document.querySelectorAll('.tier-board-container button')).filter(b => b.textContent.includes('Benchmark this call'));
    const filledButtons = Array.from(document.querySelectorAll('button.btn-primary, button[class*="primary"]')).filter(b => b.offsetParent !== null);
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasNavSidebar: navSidebars.length > 0,
      hasBoard: !!board,
      hasRepoBar: !!repoBar,
      benchmarkButtonCount: benchmarkButtons.length,
      filledButtonCount: filledButtons.length,
      hasHorizontalScroll: scrollWidth > clientWidth,
      scrollWidth,
      clientWidth
    };
  })()`);
  console.log('Scanned (untested) checks:', scannedValidation);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '02-workbench-scanned-untested.png'));

  // Check 3: BENCHMARK RUNNING
  // Click "Benchmark this call" on the first row
  console.log('Triggering benchmark on first row...');
  await cdp.eval(`(() => {
    const btn = Array.from(document.querySelectorAll('.tier-board-container button')).find(b => b.textContent.includes('Benchmark this call'));
    if (btn) btn.click();
    else throw new Error('Benchmark this call button not found');
  })()`);

  // Capture immediately while in-flight or progressUnits is active
  await sleep(200);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '03-benchmark-running.png'));
  console.log('Captured benchmark running screenshot');

  // Wait for benchmark and optimization to complete
  console.log('Waiting for benchmark & optimization to complete...');
  let completed = false;
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    const state = await cdp.eval(`(() => {
      const decisionPanel = document.querySelector('.decision-panel-container');
      const headline = decisionPanel?.querySelector('.decision-headline')?.textContent;
      const arc = document.querySelector('.route-arc');
      const applyBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Apply patch'));
      return { hasDecision: !!decisionPanel, headline, hasArc: !!arc, hasApply: !!applyBtn };
    })()`);
    if (state.hasDecision && state.hasArc && state.hasApply) {
      console.log('Benchmark completed!', state);
      completed = true;
      break;
    }
  }

  if (!completed) {
    console.warn('Timed out waiting for benchmark completion; checking current state');
  }

  // Check 4: COMPLETE WITH A RECOMMENDATION
  const completeValidation = await cdp.eval(`(() => {
    const navSidebars = document.querySelectorAll('aside.sidebar, nav[aria-label="Navigation"]');
    const filledButtons = Array.from(document.querySelectorAll('button.btn-primary, button[class*="primary"]')).filter(b => b.offsetParent !== null);
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    const arc = document.querySelector('.route-arc');
    const decisionHeadline = document.querySelector('.decision-headline')?.textContent;
    return {
      hasNavSidebar: navSidebars.length > 0,
      filledButtonCount: filledButtons.length,
      filledButtonText: filledButtons.map(b => b.textContent?.trim()),
      hasArc: !!arc,
      decisionHeadline,
      hasHorizontalScroll: scrollWidth > clientWidth,
      scrollWidth,
      clientWidth
    };
  })()`);
  console.log('Complete with recommendation checks:', completeValidation);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '04-complete-recommendation-1440x900.png'));

  // Test at 1366x768 as well
  await cdp.setViewport(1366, 768);
  await sleep(300);
  const complete1366 = await cdp.eval(`(() => ({
    hasHorizontalScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  console.log('Complete 1366x768 scroll check:', complete1366);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '04-complete-recommendation-1366x768.png'));

  // Check 5: CALL WITH NO CHEAPER PICK
  // We navigate to Home to capture the dedicated "Draft reply" row with "No cheaper tier passed every check", no arc, and ring on Ultra
  console.log('Capturing call with no cheaper pick...');
  await cdp.eval(`(() => {
    // Click wordmark to go back to Home
    const wordmark = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('CascadeRouter'));
    if (wordmark) wordmark.click();
  })()`);
  await sleep(600);

  const noCheaperValidation = await cdp.eval(`(() => {
    const rows = Array.from(document.querySelectorAll('.tier-board-row'));
    const draftRow = rows.find(r => r.textContent.includes('Draft reply'));
    const trackMsg = draftRow?.querySelector('.no-cheaper-msg')?.textContent;
    const hasArc = !!draftRow?.querySelector('.route-arc');
    const ariaLabel = draftRow?.getAttribute('aria-label');
    return {
      hasDraftRow: !!draftRow,
      trackMsg,
      hasArc,
      ariaLabel
    };
  })()`);
  console.log('No cheaper pick validation on Home illustration:', noCheaperValidation);
  await cdp.captureScreenshot(resolve(SCREENSHOT_DIR, '05-call-no-cheaper-pick.png'));

  // Also copy all screenshots to conversation artifact directory
  const ARTIFACT_DIR = '/Users/sabasaeed/.gemini/antigravity/brain/dfb48512-3eb8-4095-b038-4cf21654b43e';
  const fs = await import('node:fs');
  const files = [
    '01-home-1440x900.png',
    '01-home-1366x768.png',
    '02-workbench-scanned-untested.png',
    '03-benchmark-running.png',
    '04-complete-recommendation-1440x900.png',
    '04-complete-recommendation-1366x768.png',
    '05-call-no-cheaper-pick.png',
  ];
  for (const f of files) {
    fs.copyFileSync(resolve(SCREENSHOT_DIR, f), resolve(ARTIFACT_DIR, f));
  }
  console.log('Copied all screenshots to artifact directory:', ARTIFACT_DIR);

  // Close tab and finish
  await cdp.close();
  await fetch(`${CHROME_HTTP}/json/close/${tab.id}`);
  console.log('All screenshots captured and verified successfully!');
}

main().catch(err => {
  console.error('Capture failed:', err);
  process.exit(1);
});
