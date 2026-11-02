/* Isolated checks with mocked APIs; never touches the working database. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.IPRICE_PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.IPRICE_UI_URL || 'http://127.0.0.1:5188';
async function mount(page, module, component) {
  await page.route(`${base}/review-check`, route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html lang="ru"><meta charset="utf-8"><div id="root"></div><script type="module">
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import RefreshRuntime from '/@react-refresh';
    RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
    window.__vite_plugin_react_preamble_installed__ = true;
    const module = await import('/src/dashboards/${module}');
    window.testModule = module;
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(module.${component}));
  </script></html>` }));
  await page.goto(`${base}/review-check`);
}
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.IPRICE_BROWSER });
  try {
    for (const allowed of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const columns = { code: 'Артикул', name: 'Наименование', retail_net: 'Розница без НДС', retail_gross: 'Розница с НДС', quantity: 'Количество' };
      let config = { region: 'Москва', vat: 22, thresholds: [50000, 300000, 800000], warning_threshold: 2200000,
        characteristics: [], logistics: [], warehouses: [], simple_columns: ['code', 'name', 'retail_net'], full_columns: ['code', 'name', 'retail_net', 'quantity'],
        simple_column_order: Object.keys(columns), full_column_order: Object.keys(columns) };
      let failSave = false;
      await page.route('**/v1/sales-calculator/**', async route => {
        const request = route.request(), path = new URL(request.url()).pathname;
        let data;
        if (path.endsWith('/settings/')) {
          if (request.method() === 'PUT') {
            if (failSave) { await route.fulfill({ status: 400, json: { detail: 'Не удалось сохранить настройки' } }); return; }
            config = request.postDataJSON(); data = config;
          } else data = { config, can_use_calculator: allowed, characteristics: {}, logistics: {}, warehouses: [], simple_columns: columns, full_columns: columns };
        } else if (path.endsWith('/products/')) data = { products: [], region: new URL(request.url()).searchParams.get('region') || config.region, regions: ['Москва', 'Санкт-Петербург'], state: {} };
        else if (path.endsWith('/calculate/')) data = { rows: [], quantity: 0, logistics: {} };
        else data = {};
        await route.fulfill({ json: data });
      });
      await mount(page, 'salesCalculator/SalesCalculatorDashboard.jsx', 'SalesCalculatorDashboard');
      const quick = page.locator('.sc-quick-settings');
      await quick.waitFor();
      assert.equal(await page.getByRole('button', { name: 'Калькулятор', exact: true }).count(), allowed ? 1 : 0);
      await quick.getByLabel('Склад отгрузки — быстрый выбор').selectOption('Санкт-Петербург');
      await page.waitForFunction(() => !document.querySelector('.sc-quick-settings select').disabled);
      await quick.locator('summary').click();
      await quick.getByLabel('Розница с НДС', { exact: true }).check();
      await page.waitForFunction(() => !document.querySelector('.sc-quick-popover fieldset').disabled);
      assert.ok(config.simple_columns.includes('retail_gross'));
      await page.getByRole('button', { name: 'Настройки', exact: true }).click();
      const dialog = page.getByRole('dialog');
      assert.equal(await dialog.getByRole('button', { name: 'Калькулятор', exact: true }).count(), allowed ? 1 : 0);
      assert.equal(await dialog.getByLabel('Склад отгрузки', { exact: true }).inputValue(), 'Санкт-Петербург');
      await dialog.locator('.sc-column-settings summary').click();
      assert.equal(await dialog.getByLabel('Розница с НДС', { exact: true }).isChecked(), true);
      await dialog.getByLabel('Розница без НДС', { exact: true }).uncheck();
      await dialog.getByLabel('Склад отгрузки', { exact: true }).selectOption('Москва');
      await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click();
      await dialog.waitFor({ state: 'detached' });
      await page.waitForFunction(() => document.querySelector('.sc-quick-settings select').value === 'Москва');
      await quick.locator('summary').click();
      assert.equal(await quick.getByLabel('Розница без НДС', { exact: true }).isChecked(), false);
      failSave = true;
      await quick.getByLabel('Розница без НДС', { exact: true }).check();
      await page.getByText('Не удалось сохранить настройки', { exact: true }).waitFor();
      assert.equal(await quick.getByLabel('Розница без НДС', { exact: true }).isChecked(), false);
      failSave = false;
      if (allowed) {
        await page.getByRole('button', { name: 'Калькулятор', exact: true }).click();
        await quick.locator('summary').click();
        assert.equal(await quick.getByLabel('Розница без НДС', { exact: true }).isChecked(), true);
      }
      if (process.env.REVIEW_SCREENSHOTS) await page.screenshot({ path: `${process.env.REVIEW_SCREENSHOTS}/price-${allowed}.png`, fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
      assert.deepEqual(errors, []);
      await page.close();
    }
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const stages = [
      { period: '2026-01-01', dimension_key: 'target', value: 20, dimension_target: 20, previous_year_value: 10, previous_year_dimension_target: 10 },
      { period: '2026-01-01', dimension_key: 'apm', value: 30, previous_year_value: 10 },
      { period: '2026-01-01', dimension_key: 'low_quality', value: 50, dimension_low_quality: 50, previous_year_value: 20, previous_year_dimension_low_quality: 20 },
    ];
    const summary = [{ period: '__range__', dimension_key: '1', dimension_name: 'Источник', value: 100, total: 100, dimension_target: 50, dimension_low_quality: 50, previous_year_value: 40, previous_year_total: 40, previous_year_dimension_target: 20, previous_year_dimension_low_quality: 20 }];
    await page.route('**/v1/bitrix24/**', route => route.fulfill({ json: route.request().url().endsWith('/dashboard/') ? { cards: { total: 120, apm: 30, target: 20, low_quality: 50, in_progress: 20, conversion: 20 / 70 * 100 }, dynamics: { stages, sources: [], managers: [] }, summaries: { sources: summary, managers: summary } } : {} }));
    await mount(page, 'crmAnalytics/CrmAnalyticsDashboard.jsx', 'CrmAnalyticsDashboard');
    await page.locator('.crm-summary-total').first().waitFor();
    assert.deepEqual(await page.locator('.crm-lead-kpis .crm-kpi-card__label > span:first-child').allTextContents(), ['Итого', 'Передано в Селект Маркет', 'Целевые', 'Целевые, включая Селект Маркет', 'Некачественные', 'Конверсия', 'Конверсия, включая Селект Маркет', 'В работе', 'Повторные']);
    assert.equal(await page.locator('.crm-lead-kpis article').nth(3).locator('strong').innerText(), '50');
    assert.equal(await page.locator('.crm-lead-kpis article').nth(6).locator('strong').innerText(), '50,0%');
    const sourceTotal = page.locator('.crm-panel').filter({ has: page.getByRole('heading', { name: 'Динамика по источникам', exact: true }) }).locator('.crm-summary-total');
    assert.equal(await sourceTotal.locator('td').nth(2).locator('strong').innerText(), '50');
    assert.equal(await sourceTotal.locator('td').nth(3).locator('strong').innerText(), '50,0%');
    await page.getByRole('button', { name: 'Менеджеры и качество лидов', exact: true }).click();
    const managerTotal = page.locator('.crm-panel').filter({ has: page.getByRole('heading', { name: 'Динамика по менеджерам', exact: true }) }).locator('.crm-summary-total');
    assert.equal(await managerTotal.locator('td').nth(2).locator('strong').innerText(), '50');
    assert.equal(await managerTotal.locator('td').nth(3).locator('strong').innerText(), '50,0%');
    if (process.env.REVIEW_SCREENSHOTS) await page.screenshot({ path: `${process.env.REVIEW_SCREENSHOTS}/crm-cards.png`, fullPage: true });
    await page.locator('.crm-lead-kpis article').nth(5).getByRole('button').click();
    assert.equal(await page.locator('.crm-conversion-kpis article').first().locator('strong').innerText(), '28,6%');
    await page.locator('.crm-conversion-modal').getByRole('button', { name: 'Закрыть', exact: true }).click();
    await page.locator('.crm-lead-kpis article').nth(6).getByRole('button').click();
    await page.getByRole('heading', { name: 'Динамика конверсии, включая Селект Маркет', exact: true }).waitFor();
    assert.deepEqual(await page.locator('.crm-conversion-kpis article > strong').allTextContents(), ['50,0%', '50,0%', '0,0']);
    if (process.env.REVIEW_SCREENSHOTS) await page.screenshot({ path: `${process.env.REVIEW_SCREENSHOTS}/crm.png`, fullPage: true });
    await page.close();
    console.log('PASS: CRM cards and conversion; calculator visibility; settings synchronization and failed saves.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
