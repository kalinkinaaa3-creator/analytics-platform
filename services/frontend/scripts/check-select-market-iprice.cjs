/* Local React smoke test. Backend/external source requests are fixtures only. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.IPRICE_PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.IPRICE_UI_URL || 'http://127.0.0.1:5188';

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.IPRICE_BROWSER ? { executablePath: process.env.IPRICE_BROWSER } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let canEdit = true, manualPrice = null, parameterCalls = 0, approved = false, editRevision = 0, competitorChanges = 0;
    let failRowsOnce = true, twoRows = true;
    const version = { id: 1, version_number: 1, calculation_date: '2026-10-14', status: 'success', is_current: true, is_active: false, was_active: false };
    const row = { id: 1, product_id: 1, snapshot_product__code_1c: '00-А', snapshot_product__nom: 'Тестовый ящик',
      sale_region: 'СПБ', departure: 'Завод', current_retail: '100', cost_with_logistics: '60', minimum_price: '70',
      calculated_rrp: '110', regional_competitor_rrp_median: '105', regional_competitor_rrp_min: '90', regional_competitor_rrp_max: '120',
      calculation_status: 'warning', error_codes: [], warning_codes: ['MISSING_WEBSITE_PRODUCT', 'MISSING_CLASSIFICATION', 'REAPPROVAL_REQUIRED'] };
    await page.route('**/v1/select-market/iprice/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      let body;
      if (path.endsWith('/status/')) body = { can_edit: canEdit, imports: [], price_imports: [], parsers_enabled: false, run: null, queue: [] };
      else if (path.endsWith('/price-zones/')) body = { below_market_threshold: '-0.03', above_market_threshold: '0.03', critical_threshold: '0.1' };
      else if (path.endsWith('/snapshots/')) body = [{ ...version, is_active: approved, was_active: approved, edit_revision: editRevision }, { ...version, id: 2, version_number: 0, calculation_date: '2026-10-13', is_current: false }];
      else if (path.endsWith('/filters/')) body = { group_1: ['Торговый ассортимент'], is_classified: ['true'] };
      else if (path.endsWith('/rows/')) {
        if (failRowsOnce) { failRowsOnce = false; await route.fulfill({ status: 503, json: { detail: 'Временная ошибка строк' } }); return; }
        const first = { ...row, effective: { rrp: manualPrice || '110', approval_revision: manualPrice ? 1 : 0, approval_source: manualPrice ? 'manual' : 'calculated' } };
        body = { rows: twoRows ? [first, { ...first, id: 2, snapshot_product__code_1c: 'SECOND', snapshot_product__nom: 'Второй ящик' }] : [first], page: 1, pages: 1, count: twoRows ? 2 : 1 };
      }
      else if (path.endsWith('/price-file/') && request.method() === 'POST') { await route.fulfill({ status: 400, json: { file: ['В файле не заполнен код товара.'] } }); return; }
      else if (path.endsWith('/history/')) body = { activations: [], approvals: [], parameter_changes: [], page: 1, pages: 1 };
      else if (path.endsWith('/approval/')) { const data = request.postDataJSON(); assert.equal(data.expected_revision, 0); assert.equal(data.comment, 'Причина проверки'); manualPrice = data.approved_rrp; editRevision++; body = { revision: 1 }; }
      else if (path.endsWith('/parameters/')) { const data = request.postDataJSON(); parameterCalls++; assert.deepEqual(data.delivery, { include_transport: true, logistics_unit: '12.34' }); assert.deepEqual(data.filters, { code_1c: ['00-А'] }); if (!data.preview) { assert.equal(data.expected_revision, editRevision); editRevision++; } body = { affected: { products: 1, regions: 1, routes: 1 }, edit_revision: editRevision }; }
      else if (path.endsWith('/activate/')) { assert.equal(request.postDataJSON().expected_revision, editRevision); approved = true; body = { id: 1, is_active: true }; }
      else if (path.endsWith('/products/1/')) body = { code: '00-А', nom: 'Тестовый ящик', method: 'exclusive', competitors: [] };
      else if (path.endsWith('/competitors/')) {
        if (request.method() === 'POST') { assert.equal(request.postDataJSON().expected_revision, editRevision); competitorChanges++; editRevision++; body = {}; }
        else body = { page: 1, pages: 1, edit_revision: editRevision, editable: true, changes: [], items: [{ id: 2, source: 'tt', url: 'https://example.test/competitor', mode: 'auto' }] };
      }
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'groups') body = { results: [{ key: 'Ящики', label: 'Ящики', product_count: 1, median_final_rrp: '150', median_retail_price: '100', median_market_price: '105' }], next_level: 'category', pagination: { page: 1, pages: 1 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('comparison_id')) body = { results: [{ base: { code_1c: 'OLD', nom: 'Удалённый товар', sale_region: 'СПБ', effective_approved_rrp: '100' }, comparison: null, change_type: 'removed' }], page: 1, total_pages: 1 };
      else if (path.endsWith('/analysis/')) body = { results: [{ code_1c: '00-А', nom: row.snapshot_product__nom, sale_region: 'СПБ', departure: 'Завод', final_rrp: manualPrice, retail_price: '100', market_price: '105', zone: 'below_market' }], pagination: { page: 1, pages: 1 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else throw new Error(`Unexpected request: ${path}`);
      await route.fulfill({ json: body });
    });
    await page.route(`${base}/iprice-check`, route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><body><div class="app-shell sm-workspace"><div id="root"></div></div><script type="module">
      import React from '/node_modules/.vite/deps/react.js';
      import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const { SelectMarketIPrice } = await import('/src/iprice/selectMarket/SelectMarketIPrice.jsx');
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(SelectMarketIPrice, { dashboard: {name: 'iPrice'} }));
    </script></body></html>` }));
    await page.goto(`${base}/iprice-check`);
    await page.locator('.sm-iprice-help-trigger').click();
    assert.equal(await page.locator('dialog').evaluate(el => el.open), true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog').evaluate(el => el.open), false);
    assert.equal(await page.locator('.sm-iprice-help-trigger').evaluate(el => el === document.activeElement), true);
    await page.locator('.sm-iprice-help-trigger').click();
    await page.locator('dialog header button').click();
    await page.locator('.sm-iprice-nav button').nth(4).click();
    await page.locator('.sm-iprice-source-card').first().waitFor();
    assert.equal(await page.locator('.sm-iprice-source-card').evaluateAll(cards => {
      const rows = new Map();
      for (const card of cards) {
        const top = Math.round(card.getBoundingClientRect().top);
        const levels = ['.sm-iprice-source-download', '.sm-iprice-source-upload'].map(sel => card.querySelector(sel).getBoundingClientRect().top);
        if (rows.has(top) && levels.some((v, i) => Math.abs(v - rows.get(top)[i]) > 1)) return false;
        rows.set(top, levels);
      }
      return true;
    }), true, 'Source actions align within each grid row');
    await page.locator('.sm-iprice-nav button').first().click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByText('Временная ошибка строк', { exact: false }).waitFor();
    assert.equal(await page.getByText('Загружаем строки…', { exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Повторить загрузку строк', exact: true }).click();
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByText('Параметры позиции и доставка', { exact: true }).click();
    let positionEditor = page.getByText('Параметры позиции и доставка', { exact: true }).locator('..');
    assert.equal(await positionEditor.getByLabel('Код 1С', { exact: true }).inputValue(), '00-А');
    await positionEditor.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('99');
    await page.getByRole('button', { name: 'Второй ящик', exact: true }).click();
    await page.getByText('Параметры позиции и доставка', { exact: true }).click();
    positionEditor = page.getByText('Параметры позиции и доставка', { exact: true }).locator('..');
    assert.equal(await positionEditor.getByLabel('Код 1С', { exact: true }).inputValue(), 'SECOND');
    assert.equal(await positionEditor.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).inputValue(), '');
    twoRows = false;
    await page.reload();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByText('Товар отсутствует на сайте', { exact: true }).waitFor();
    await page.getByText('Товар не классифицирован', { exact: true }).waitFor();
    await page.getByText('После изменения параметров требуется повторное согласование цены', { exact: true }).waitFor();
    if (process.env.IPRICE_SCREENSHOT_DIR) {
      const path = require('node:path');
      await page.screenshot({ path: path.join(process.env.IPRICE_SCREENSHOT_DIR, 'select-market-desktop.png'), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.locator('.sm-iprice-table tbody tr').first().evaluate(element => element.getBoundingClientRect().height < 500), true, 'Mobile table must keep readable columns');
      await page.screenshot({ path: path.join(process.env.IPRICE_SCREENSHOT_DIR, 'select-market-mobile.png'), fullPage: true });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, 'Page must not overflow on mobile');
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByText('Состав аналогов и история', { exact: true }).click();
    await page.getByLabel('Причина изменения аналогов').fill('Проверка аналога');
    page.once('dialog', dialog => dialog.accept());
    await page.getByLabel('Участие аналога 2').selectOption('exclude');
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'Своя цена', exact: true }).waitFor();
    assert.equal(competitorChanges, 1);
    await page.getByRole('button', { name: 'Своя цена', exact: true }).click();
    await page.getByLabel('Своя РРЦ').fill('150');
    await page.getByLabel('Причина', { exact: true }).fill('Причина проверки');
    await page.getByRole('button', { name: 'Сохранить цену' }).click();
    await page.getByText('Ручная цена', { exact: true }).waitFor();
    await page.getByText('Изменить параметры выбранных товаров', { exact: true }).click();
    await page.getByLabel('Код 1С', { exact: true }).fill('00-А');
    await page.getByLabel('Минимальная маржа (доля)').fill('0.2');
    await page.getByLabel('Учитывать транспортные расходы', { exact: true }).selectOption('on');
    await page.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('12.34');
    await page.getByRole('button', { name: 'Проверить выбор' }).click();
    await page.getByRole('button', { name: 'Применить и пересчитать' }).click();
    await page.waitForFunction(() => !document.body.textContent.includes('Товаров: 1, региональных строк: 1.'));
    assert.equal(parameterCalls, 2);
    await page.getByRole('button', { name: 'Рынок и изменения', exact: true }).click();
    await page.getByText('Ниже рынка', { exact: true }).waitFor();
    await page.getByLabel(/^Сравнение/).selectOption('groups');
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    assert.equal(await page.getByLabel('Группировка', { exact: true }).inputValue(), '1c');
    await page.getByLabel('Группировка', { exact: true }).selectOption('classification');
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await page.getByLabel('Группировка', { exact: true }).selectOption('1c');
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await page.getByLabel(/^Сравнение/).selectOption('2');
    await page.getByText('Удалённый товар', { exact: true }).waitFor();
    const marketPanel = page.getByRole('heading', { name: 'Рынок и изменения цен', exact: true }).locator('..');
    await marketPanel.getByText('Группы 1С и классификация', { exact: true }).click();
    const groupControl = marketPanel.locator('.dashboard-filter').filter({ has: page.getByText('Группа 1', { exact: true }) }).locator('button.dashboard-multiselect__control');
    await groupControl.click();
    await marketPanel.getByRole('checkbox', { name: 'Торговый ассортимент', exact: true }).check();
    const filteredComparison = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/analysis/') && url.searchParams.get('comparison_id') === '2' && JSON.parse(url.searchParams.get('filters') || '{}').group_1?.includes('Торговый ассортимент');
    });
    await groupControl.click();
    await filteredComparison;
    await page.getByText('Удалённый товар', { exact: true }).waitFor();
    await page.getByLabel(/^Сравнение/).selectOption('');
    await page.getByText('Ниже рынка', { exact: true }).waitFor();
    // Another editor changes this version while the current user views old data.
    editRevision++;
    await page.getByRole('button', { name: 'Обновить расчёт', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Утвердить внутри системы' }).isDisabled(), true);
    await page.getByRole('button', { name: 'Обновить расчёт', exact: true }).click();
    await page.getByText('Ниже рынка', { exact: true }).waitFor();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Утвердить внутри системы' }).click();
    await page.getByRole('button', { name: 'Версия утверждена', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Цены', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    canEdit = false;
    await page.reload();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    assert.equal(await page.getByRole('button', { name: 'Рассчитать цены', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Скачать Excel', exact: true }).waitFor();
    canEdit = true;
    approved = false;
    version.historical_routes = true;
    await page.reload();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByText('Историческая версия с маршрутами: доступны просмотр и выгрузка. Для изменения цен создайте новый расчёт.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Скачать Excel', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Утвердить внутри системы', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Исходные данные', exact: true }).click();
    await page.getByLabel('Дата полного прайса', { exact: true }).fill('2026-10-15');
    const priceCard = page.getByRole('heading', { name: 'Прайс', exact: true }).locator('xpath=ancestor::article');
    await priceCard.locator('input[type=file]').setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('fixture') });
    await page.getByText('В файле не заполнен код товара.', { exact: true }).waitFor();
    version.historical_routes = false;
    version.status = 'building';
    await page.reload();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    assert.equal(await page.getByText('Изменить параметры выбранных товаров', { exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Скачать Excel', exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('Select Market iPrice React: price edit, parameter preview/apply, market, activation and viewer rights passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
