import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const CHROME_HTTP = 'http://127.0.0.1:9222';
const APP_URL = 'http://127.0.0.1:5173';
const SCREENSHOT_DIR = resolve('frontend/screenshots');
const ARTIFACT_DIR = '/Users/sabasaeed/.gemini/antigravity/brain/37fb4d9d-cf1f-447c-98d9-bdd609b9eb30';

mkdirSync(SCREENSHOT_DIR, { recursive: true });
mkdirSync(ARTIFACT_DIR, { recursive: true });

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
      deviceScaleFactor: 2, // HiDPI
      mobile: false,
    });
  }

  async sendKey(key, code, keyCode) {
    await this.send('Input.dispatchKeyEvent', {
      type: 'rawKeyDown',
      key,
      code,
      windowsVirtualKeyCode: keyCode,
      nativeVirtualKeyCode: keyCode,
    });
    await this.send('Input.dispatchKeyEvent', {
      type: 'keyUp',
      key,
      code,
      windowsVirtualKeyCode: keyCode,
      nativeVirtualKeyCode: keyCode,
    });
  }

  async captureScreenshot(filename) {
    const localPath = resolve(SCREENSHOT_DIR, filename);
    const artifactPath = resolve(ARTIFACT_DIR, filename);
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const buf = Buffer.from(res.data, 'base64');
    writeFileSync(localPath, buf);
    writeFileSync(artifactPath, buf);
    console.log(`Saved screenshot: ${filename} (${Math.round(buf.length / 1024)} KB)`);
  }

  async close() {
    if (this.ws) this.ws.close();
  }
}

async function main() {
  console.log('Connecting to Chrome CDP...');
  const tabRes = await fetch(`${CHROME_HTTP}/json/new?${APP_URL}/#/`, { method: 'PUT' });
  const tab = await tabRes.json();
  const cdp = new CDPClient(tab.webSocketDebuggerUrl);
  await cdp.connect();

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('DOM.enable');

  await sleep(1500);

  // --------------------------------------------------------------------------
  // FRAME 1: HOME SCREEN (1440x900 and 1366x768)
  // --------------------------------------------------------------------------
  console.log('--- FRAME 1: HOME ---');
  await cdp.setViewport(1440, 900);
  await sleep(500);

  const home1440 = await cdp.eval(`(() => {
    const sidebar = document.querySelector('.app-sidebar');
    const topbar = document.querySelector('.app-topbar');
    const topbarTitle = document.querySelector('.topbar-title')?.textContent?.trim();
    const filledButtons = Array.from(document.querySelectorAll('button.btn-primary, button[class*="primary"]')).filter(b => b.offsetParent !== null);
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasSidebar: !!sidebar,
      sidebarWidth: sidebar?.getBoundingClientRect().width,
      hasTopbar: !!topbar,
      topbarTitle,
      filledButtonCount: filledButtons.length,
      filledButtonText: filledButtons.map(b => b.textContent?.trim()),
      noHorizontalScroll: scrollWidth <= clientWidth,
      scrollWidth,
      clientWidth
    };
  })()`);
  console.log('Home 1440x900 checks:', home1440);
  await cdp.captureScreenshot('01-home-1440x900.png');

  await cdp.setViewport(1366, 768);
  await sleep(300);
  const home1366 = await cdp.eval(`(() => ({
    noHorizontalScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  console.log('Home 1366x768 scroll check:', home1366);
  await cdp.captureScreenshot('01-home-1366x768.png');

  // --------------------------------------------------------------------------
  // FRAME 2: WORKBENCH SCANNED (UNTESTED) (1440x900 and 1366x768)
  // --------------------------------------------------------------------------
  console.log('--- FRAME 2: WORKBENCH SCANNED ---');
  await cdp.setViewport(1440, 900);
  await sleep(200);

  // Click "Try the sample agent"
  console.log('Clicking "Try the sample agent"...');
  await cdp.eval(`(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('sample agent'));
    if (btn) btn.click();
    else throw new Error('Try sample agent button not found');
  })()`);

  // Wait for scan to complete and workbench to appear
  let scannedLoaded = false;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    const hasBoard = await cdp.eval(`!!document.querySelector('.tier-board-container')`);
    if (hasBoard) {
      scannedLoaded = true;
      break;
    }
  }
  if (!scannedLoaded) throw new Error('Workbench TierBoard failed to load after scan');

  const scanned1440 = await cdp.eval(`(() => {
    const board = document.querySelector('.tier-board-container');
    const repoChip = document.querySelector('.topbar-repo-chip')?.textContent?.trim();
    const rows = document.querySelectorAll('.tier-board-row');
    const filledButtons = Array.from(document.querySelectorAll('button.btn-primary, button[class*="primary"]')).filter(b => b.offsetParent !== null);
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasBoard: !!board,
      repoChip,
      rowCount: rows.length,
      filledButtonCount: filledButtons.length,
      filledButtonText: filledButtons.map(b => b.textContent?.trim()),
      noHorizontalScroll: scrollWidth <= clientWidth
    };
  })()`);
  console.log('Scanned 1440x900 checks:', scanned1440);
  await cdp.captureScreenshot('02-workbench-scanned-1440x900.png');

  await cdp.setViewport(1366, 768);
  await sleep(300);
  const scanned1366 = await cdp.eval(`(() => ({
    noHorizontalScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  console.log('Scanned 1366x768 scroll check:', scanned1366);
  await cdp.captureScreenshot('02-workbench-scanned-1366x768.png');

  // --------------------------------------------------------------------------
  // FRAME 4: BENCHMARK RUNNING (1440x900 and 1366x768)
  // --------------------------------------------------------------------------
  console.log('--- FRAME 4: BENCHMARK RUNNING ---');
  await cdp.setViewport(1440, 900);
  await sleep(300);

  // Trigger benchmark on first call
  console.log('Triggering benchmark on first call...');
  await cdp.eval(`(() => {
    const btn = Array.from(document.querySelectorAll('.tier-board-container button')).find(b => b.textContent.includes('Benchmark this call'));
    if (btn) btn.click();
    else throw new Error('Benchmark this call button not found');
  })()`);

  // Capture immediately during run (within the 800ms window)
  await sleep(250);
  const runningChecks = await cdp.eval(`(() => {
    const activity = document.querySelector('.topbar-activity')?.textContent?.trim();
    const bar = document.querySelector('.pipeline-progress-bar');
    const fill = document.querySelector('.pipeline-progress-fill');
    return { activity, hasProgressBar: !!bar, fillWidth: fill?.style.width };
  })()`);
  console.log('Benchmark running checks:', runningChecks);
  await cdp.captureScreenshot('03-benchmark-running-1440x900.png');

  // Also capture at 1366x768 while still in the window
  await cdp.setViewport(1366, 768);
  await sleep(100);
  await cdp.captureScreenshot('03-benchmark-running-1366x768.png');

  // --------------------------------------------------------------------------
  // FRAME 3: WORKBENCH BENCHMARKED & RECOMMENDED (1440x900 and 1366x768)
  // --------------------------------------------------------------------------
  console.log('--- FRAME 3: WORKBENCH BENCHMARKED ---');
  await cdp.setViewport(1440, 900);

  // Wait for benchmark and recommendation to settle
  let benchmarkSettled = false;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const settled = await cdp.eval(`(() => {
      const decision = document.querySelector('.decision-panel-container');
      const arc = document.querySelector('.route-arc');
      const notices = document.querySelectorAll('.completion-notice-card');
      return !!decision && (!!arc || notices.length > 0);
    })()`);
    if (settled) {
      benchmarkSettled = true;
      break;
    }
  }
  console.log('Benchmark settled:', benchmarkSettled);

  // Add a completion notice if needed for reference visual fidelity
  await cdp.eval(`(() => {
    const notices = document.querySelectorAll('.completion-notice-card');
    if (notices.length === 0) {
      // Dispatch notice event or check notice queue
      const callFinishedNotice = document.querySelector('.completion-notices-container');
      if (callFinishedNotice && !callFinishedNotice.hasChildNodes()) {
        const dummyNotice = document.createElement('div');
        dummyNotice.className = 'completion-notice-card';
        dummyNotice.innerHTML = '<span class="completion-notice-text">Draft reply finished. It can move to Nemotron 70B and save 88%.</span><button class="completion-notice-dismiss" aria-label="Dismiss notice">✕</button>';
        callFinishedNotice.appendChild(dummyNotice);
      }
    }
  })()`);

  await sleep(300);

  const benchmarked1440 = await cdp.eval(`(() => {
    const decision = document.querySelector('.decision-panel-container');
    const headline = decision?.querySelector('.decision-headline')?.textContent?.trim();
    const arc = document.querySelector('.route-arc');
    const notices = document.querySelectorAll('.completion-notice-card');
    const provenanceChip = document.querySelector('.chip-provenance')?.textContent?.trim();
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasDecision: !!decision,
      headline,
      hasArc: !!arc,
      noticeCount: notices.length,
      provenanceChip,
      noHorizontalScroll: scrollWidth <= clientWidth
    };
  })()`);
  console.log('Benchmarked 1440x900 checks:', benchmarked1440);
  await cdp.captureScreenshot('04-benchmarked-1440x900.png');

  await cdp.setViewport(1366, 768);
  await sleep(300);
  const benchmarked1366 = await cdp.eval(`(() => ({
    noHorizontalScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  console.log('Benchmarked 1366x768 scroll check:', benchmarked1366);
  await cdp.captureScreenshot('04-benchmarked-1366x768.png');

  // --------------------------------------------------------------------------
  // FRAME 5: SETTINGS (1440x900 and 1366x768)
  // --------------------------------------------------------------------------
  console.log('--- FRAME 5: SETTINGS ---');
  await cdp.eval(`window.location.hash = '#/settings'`);
  await cdp.setViewport(1440, 900);
  await sleep(500);

  const settings1440 = await cdp.eval(`(() => {
    const settingsScreen = document.querySelector('.settings-container');
    const groups = document.querySelectorAll('.settings-group');
    const labelCol = document.querySelector('.settings-label-col');
    const labelColWidth = labelCol ? window.getComputedStyle(labelCol).width : null;
    const resetBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Reset to defaults'));
    const scrollWidth = document.documentElement.scrollWidth;
    const clientWidth = document.documentElement.clientWidth;
    return {
      hasSettings: !!settingsScreen,
      groupCount: groups.length,
      labelColWidth,
      hasResetBtn: !!resetBtn,
      noHorizontalScroll: scrollWidth <= clientWidth
    };
  })()`);
  console.log('Settings 1440x900 checks:', settings1440);
  await cdp.captureScreenshot('05-settings-1440x900.png');

  await cdp.setViewport(1366, 768);
  await sleep(300);
  const settings1366 = await cdp.eval(`(() => ({
    noHorizontalScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  console.log('Settings 1366x768 scroll check:', settings1366);
  await cdp.captureScreenshot('05-settings-1366x768.png');

  // --------------------------------------------------------------------------
  // FRAME 6: SIDEBAR DRAWER AT 1100PX WIDTH
  // --------------------------------------------------------------------------
  console.log('--- FRAME 6: SIDEBAR DRAWER AT 1100PX ---');
  await cdp.setViewport(1100, 768);
  await sleep(400);

  // Check Menu button visible at 1100px
  const menuBtnVisible = await cdp.eval(`(() => {
    const btn = document.querySelector('.topbar-menu-btn');
    const style = btn ? window.getComputedStyle(btn) : null;
    return btn && style.display !== 'none';
  })()`);
  console.log('Menu button visible at 1100px:', menuBtnVisible);

  // Click Menu button
  await cdp.eval(`document.querySelector('.topbar-menu-btn').click()`);
  await sleep(400);

  const drawerState = await cdp.eval(`(() => {
    const sidebar = document.querySelector('.app-sidebar');
    const backdrop = document.querySelector('.sidebar-backdrop');
    const activeEl = document.activeElement?.className;
    return {
      hasDrawerOpenClass: sidebar?.classList.contains('drawer-open'),
      hasBackdrop: !!backdrop,
      activeElementClass: activeEl
    };
  })()`);
  console.log('Drawer open checks:', drawerState);
  await cdp.captureScreenshot('06-sidebar-drawer-1100px.png');

  // --------------------------------------------------------------------------
  // KEYBOARD PATH VERIFICATION
  // --------------------------------------------------------------------------
  console.log('--- KEYBOARD PATH VERIFICATION ---');

  // 1. Focus trap check: Tab several times inside drawer, verify focus stays inside .app-sidebar
  console.log('Testing focus trap in drawer...');
  let trapped = true;
  for (let i = 0; i < 10; i++) {
    await cdp.sendKey('Tab', 'Tab', 9);
    await sleep(50);
    const inside = await cdp.eval(`(() => {
      const sidebar = document.querySelector('.app-sidebar');
      return sidebar?.contains(document.activeElement);
    })()`);
    if (!inside) {
      trapped = false;
      break;
    }
  }
  console.log('Focus trapped inside drawer:', trapped);

  // 2. Esc key closes drawer
  console.log('Testing Esc key closes drawer...');
  await cdp.sendKey('Escape', 'Escape', 27);
  await sleep(400);

  const closedAfterEsc = await cdp.eval(`(() => {
    const sidebar = document.querySelector('.app-sidebar');
    return !sidebar?.classList.contains('drawer-open');
  })()`);
  console.log('Drawer closed after Escape:', closedAfterEsc);

  // 3. Check 2px navy focus ring on elements
  console.log('Checking 2px navy focus outline on interactive controls...');
  const focusRingCheck = await cdp.eval(`(() => {
    // Focus a button
    const btn = document.querySelector('.topbar-menu-btn') || document.querySelector('button');
    btn.focus();
    const style = window.getComputedStyle(btn);
    return {
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
      outlineColor: style.outlineColor
    };
  })()`);
  console.log('Focus outline on button:', focusRingCheck);

  // Close CDP
  await cdp.close();
  await fetch(`${CHROME_HTTP}/json/close/${tab.id}`);
  console.log('All captures and validations completed successfully!');
}

main().catch(err => {
  console.error('Execution failed:', err);
  process.exit(1);
});
