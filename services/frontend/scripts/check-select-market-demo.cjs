/* Compare computed component styles with the supplied archive, under platform CSS. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const postcss = require('postcss');
const { chromium } = require(process.env.IPRICE_PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.IPRICE_UI_URL || 'http://127.0.0.1:5188';
const archive = path.resolve(__dirname, '../../../iprice-frontend.zip');
const original = execFileSync('python', ['-X', 'utf8', '-c', 'import sys,zipfile;sys.stdout.write(zipfile.ZipFile(sys.argv[1]).read("iprice/src/iprice/styles/iprice.css").decode())', archive], { encoding: 'utf8' });
const scoped = postcss.parse(original.replace(/\.ip(?![\w-])/g, '.sm-iprice'));
scoped.walkRules(rule => {
  if (rule.parent.type === 'atrule' && /keyframes$/.test(rule.parent.name)) return;
  rule.selectors = rule.selectors.map(s => s.includes('.sm-iprice') ? s : ':where(.sm-iprice) ' + s);
});
assert.equal(fs.readFileSync(path.resolve(__dirname, '../src/iprice/selectMarket/demo.css'), 'utf8').replace(/\r\n/g, '\n'), scoped.toString().replace(/\r\n/g, '\n'), 'Archive CSS must differ only by module scoping');
const sample = `<div class="ip-main"><div class="ip-page-head"><div><h1 data-s="h1">Page</h1><p data-s="description">Description</p></div></div>
  <div class="ip-row"><button class="ip-btn primary" data-s="primary">Action</button><button class="ip-btn secondary" data-s="secondary">Action</button><button class="ip-btn ghost s" data-s="ghost">Action</button><button class="ip-chip" data-s="chip">Category: all</button></div>
  <input class="ip-input" data-s="input" value="Sample"><select class="ip-select" data-s="select"><option>Sample</option></select>
  <div class="ip-tabs"><button aria-selected="true" data-s="tab">Tab</button></div>
  <div class="ip-panel" data-s="panel"><div class="ip-panel-head" data-s="panelhead"><div class="ip-panel-title"><h2 data-s="h2">Panel</h2><p>Details</p></div></div>
  <table class="ip-table"><thead><tr><th data-s="th">Product</th></tr></thead><tbody><tr><td data-s="td">Sample</td></tr></tbody></table></div>
  <div class="ip-pop" style="position:static"><label class="opt" data-s="option"><input type="checkbox"><span class="lbl">Value</span></label></div>
  <div class="ip-drawer"><div class="ip-drawer-head" data-s="drawerhead"><h2>Help</h2></div><div class="ip-drawer-body" data-s="drawerbody">Content</div></div></div>`;
const props = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'color', 'backgroundColor', 'padding', 'borderColor', 'borderWidth', 'borderRadius', 'boxShadow'];
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.IPRICE_BROWSER ? { executablePath: process.env.IPRICE_BROWSER } : {}) });
  try {
    const results = [];
    for (const reference of [true, false]) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      await page.route(`${base}/demo-style-check`, route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><style>body{margin:0}</style>${reference ? `<style>${original}</style>` : ''}</head><body><div class="${reference ? 'ip' : 'sm-iprice sm-system-page'}">${sample}</div><button id="outside">Platform control</button><script type="module">
        import '/src/index.css'; import '/src/organizations/select-market.css';
        ${reference ? '' : "import '/src/iprice/selectMarket/demo.css'; import '/src/iprice/selectMarket/selectMarketIPrice.css';"}
        window.stylesReady = true;
      </script></body></html>` }));
      await page.goto(`${base}/demo-style-check`);
      await page.waitForFunction(() => window.stylesReady);
      await page.evaluate(async () => { await document.fonts.ready; await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {}))); });
      results.push(await page.evaluate(properties => Object.fromEntries([...document.querySelectorAll('[data-s], #outside')].map(el => {
        const css = getComputedStyle(el); return [el.dataset.s || 'outside', Object.fromEntries(properties.map(p => [p, css[p]]))];
      })), props));
      await page.close();
    }
    assert.deepEqual(results[1], results[0], 'Component styles must match the archive; platform control must remain unchanged');
    console.log('Select Market demo: archive CSS unchanged except scope; computed styles match; no leakage outside module.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
