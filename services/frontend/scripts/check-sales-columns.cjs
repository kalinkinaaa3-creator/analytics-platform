/* Isolated browser check: no requests to the working backend. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.IPRICE_PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.IPRICE_UI_URL || 'http://127.0.0.1:5188';
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.IPRICE_BROWSER });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let config = { region: 'Москва', vat: 22, thresholds: [50000, 300000, 800000], warning_threshold: 2200000,
      characteristics: [], logistics: [], warehouses: [], simple_columns: ['image', 'code', 'name'], full_columns: ['image', 'code', 'name'],
      simple_column_order: ['image', 'code', 'name'], full_column_order: ['image', 'code', 'name'] };
    const columns = { image: 'Изображение', code: 'Артикул', name: 'Номенклатура прайс-листа' };
    const products = [1, 2].map(id => ({ product_key: String(id), code: id, name: `Товар ${id}`, characteristics: {}, logistics: {}, stocks: {} }));
    let pending, fail = false;
    await page.route('**/v1/sales-calculator/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      let data;
      if (path.endsWith('/settings/')) {
        if (request.method() === 'PUT') { config = request.postDataJSON(); data = config; }
        else data = { config, characteristics: {}, logistics: {}, warehouses: [], simple_columns: columns, full_columns: columns };
      } else if (path.endsWith('/products/')) data = { products, region: 'Москва', regions: ['Москва'], state: {} };
      else if (path.endsWith('/refresh/')) data = {};
      else if (path.endsWith('/calculate/')) {
        const items = request.postDataJSON().items;
        if (items.length) await new Promise(resolve => { pending = resolve; });
        if (fail) { await route.fulfill({ status: 500, json: { detail: 'Ошибка проверки' } }); return; }
        data = { rows: [], quantity: items.length, logistics: { weight: 0, pallets: 0 } };
      } else throw new Error(path);
      await route.fulfill({ json: data });
    });
    await page.route(`${base}/sales-check`, route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><div id="root"></div><script type="module">
      import React from '/node_modules/.vite/deps/react.js';
      import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const {SalesCalculatorDashboard} = await import('/src/dashboards/salesCalculator/SalesCalculatorDashboard.jsx');
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(SalesCalculatorDashboard));
    </script>` }));
    await page.goto(`${base}/sales-check`);
    await page.locator('.global-spinner-overlay').waitFor({ state: 'detached' });
    await page.getByRole('button', { name: /Настройки/ }).click();
    await page.locator('.sc-column-settings summary').click();
    const settings = page.locator('.sc-column-settings');
    await settings.getByLabel('Артикул', { exact: true }).uncheck();
    await settings.getByLabel('Артикул', { exact: true }).check();
    await settings.locator('li').nth(2).locator('.sc-column-handle').dragTo(settings.locator('li').nth(0));
    await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    assert.deepEqual(config.simple_columns, ['name', 'image', 'code']);
    assert.deepEqual(config.full_columns, ['image', 'code', 'name']);
    await page.reload();
    await page.locator('.global-spinner-overlay').waitFor({ state: 'detached' });
    for (const id of [1, 2]) {
      await page.getByRole('button', { name: /Добавить товар/ }).click();
      await page.getByLabel(`Выбрать Товар ${id}`, { exact: true }).check();
      await page.getByRole('button', { name: 'Добавить выбранные', exact: true }).click();
      await page.getByText('Добавляем товары в расчёт…', { exact: true }).waitFor();
      await page.waitForFunction(() => document.querySelector('.global-spinner-overlay'));
      while (!pending) await page.waitForTimeout(20);
      fail = id === 2;
      pending(); pending = null;
      await page.locator('.global-spinner-overlay').waitFor({ state: 'detached' });
    }
    await page.getByText('Ошибка проверки', { exact: true }).waitFor();
    const headers = await page.locator('.sc-table th').allTextContents();
    assert.deepEqual(headers.slice(1), ['Номенклатура прайс-листа', '№', 'Изображение', 'Артикул']);
    assert.deepEqual(errors, []);
    console.log('Commercial price: drag order, saved preferences, add spinner success/error passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
