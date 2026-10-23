/* Local React smoke test. Backend/external source requests are fixtures only. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.IPRICE_PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.IPRICE_UI_URL || 'http://127.0.0.1:5188';

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.IPRICE_BROWSER ? { executablePath: process.env.IPRICE_BROWSER } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
    page.on('console', m => { if (m.type() === 'error' && /same key|unique.*key/i.test(m.text())) errors.push(m.text()); });
    let canEdit = true, manualPrice = null, parameterCalls = 0, approved = false, editRevision = 0, competitorChanges = 0;
    let failRowsOnce = false, twoRows = true;
    let marketSize = 1;
    let zoneSaves = 0;
    let priceZones = { below_market_threshold: "-0.03", above_market_threshold: "0.03", critical_threshold: "0.1" };
    const version = { id: 1, version_number: 1, calculation_date: '2026-10-14', status: 'success', is_current: true, is_active: false, was_active: false };
    const row = { id: 1, product_id: 1, snapshot_product__code_1c: '00-А', snapshot_product__nom: 'Тестовый ящик',
      sale_region: 'СПБ', departure: 'Завод', current_retail: '100', cost_with_logistics: '60', minimum_price: '70',
      calculated_rrp: '110', regional_competitor_rrp_median: '105', regional_competitor_rrp_min: '90', regional_competitor_rrp_max: '120',
      calculation_status: 'warning', error_codes: [], warning_codes: ['MISSING_WEBSITE_PRODUCT', 'MISSING_CLASSIFICATION', 'REAPPROVAL_REQUIRED'] };
    await page.route('**/v1/select-market/iprice/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      let body;
      if (path.endsWith('/status/')) body = { can_edit: canEdit, imports: [], price_imports: [], parsers_enabled: false, run: null, queue: [] };
      else if (path.endsWith('/health/')) body = { price_date: null, source_checks: [], snapshot: null, issues: [] };
      else if (path.endsWith('/own/')) body = { counts: { cards: 1 }, results: [{ snapshot_product_id: 3, code_1c: 'OWN', name: 'Другой товар линейки', price: 123, regional_prices: [{ region: 'СПБ', price: 123 }] }] };
      else if (path.endsWith('/market/')) body = { editable: true, edit_revision: editRevision, counts: { cards: 1, used_in_snapshot: 1 }, results: [{ group_key: ['tt', 2], competitor_product_keys: Array.from({ length: marketSize }, (_, i) => i + 2), selection_mode: 'auto', source: 'tt', name: 'Карточка рынка', price: 105, regions: ['СПБ'], is_used_in_snapshot: true }] };
      else if (path.endsWith('/price-zones/')) {
        if (request.method() === 'POST') {
          priceZones = request.postDataJSON();
          assert.deepEqual(priceZones, {below_market_threshold: "-0.040000", above_market_threshold: "0.030000", critical_threshold: "0.120000"});
          zoneSaves++;
        }
        body = priceZones;
      }
      else if (path.endsWith('/snapshots/')) body = [{ ...version, is_active: approved, was_active: approved, edit_revision: editRevision }, { ...version, id: 2, version_number: 0, calculation_date: '2026-10-13', is_current: false }];
      else if (path.endsWith('/filters/')) body = { group_1: ['Торговый ассортимент'], is_classified: ['true'] };
      else if (path.endsWith('/rows/')) {
        if (failRowsOnce) { failRowsOnce = false; await route.fulfill({ status: 503, json: { detail: 'Временная ошибка строк' } }); return; }
        const first = { ...row, effective: { rrp: manualPrice || '110', approval_revision: manualPrice ? 1 : 0, approval_source: manualPrice ? 'manual' : 'calculated' } };
        body = { rows: twoRows ? [first, { ...first, id: 2, snapshot_product__code_1c: 'SECOND', snapshot_product__nom: 'Второй ящик' }] : [first], page: 1, pages: 1, count: twoRows ? 2 : 1 };
        if (new URL(request.url()).searchParams.get('mode') === 'products') body = { rows: [{ product_id: 1, regions: [first], summary: { current_retail_median: '100', effective_approved_rrp_median: manualPrice || '110', competitor_rrp_median: '105', competitor_count: 1, pricing_method: 'analog', calculation_status: 'warning', error_codes: [], warning_codes: row.warning_codes, zone: 'below_market' } }], page: 1, pages: 1, count: 1 };
      }
      else if (path.endsWith('/price-file/') && request.method() === 'POST') { await route.fulfill({ status: 400, json: { file: ['В файле не заполнен код товара.'] } }); return; }
      else if (path.endsWith('/history/')) body = { activations: [], approvals: [], parameter_changes: [], page: 1, pages: 1 };
      else if (path.endsWith('/approval/') && request.method() === 'GET') { const price = new URL(request.url()).searchParams.get('price'); body = { price, prices: { rrp: price, small: price, medium: price, large: price }, gross: { rrp: price, small: price, medium: price, large: price }, margin: 0.4, valid: true }; }
      else if (path.endsWith('/approval/')) { const data = request.postDataJSON(); assert.equal(data.expected_revision, 0); assert.equal(data.comment, 'Причина проверки'); manualPrice = data.approved_rrp; editRevision++; body = { revision: 1 }; }
      else if (path.endsWith('/parameters/')) { const data = request.postDataJSON(); parameterCalls++; assert.equal(data.coefficients.minimum_margin, "0.200000"); assert.deepEqual(data.delivery, { include_transport: true, logistics_unit: '12.34' }); assert.deepEqual(data.filters, {}); assert.deepEqual(data.list_scope, { mode: 'regions', zone: '', problems_only: false }); if (!data.preview) { assert.equal(data.expected_revision, editRevision); assert.equal(data.expected_scope, "a".repeat(64)); editRevision++; } body = { affected: { products: 1, regions: 1, routes: 1, scope_signature: "a".repeat(64) }, edit_revision: editRevision }; }
      else if (path.endsWith('/activate/')) { assert.equal(request.postDataJSON().expected_revision, editRevision); approved = true; body = { id: 1, is_active: true }; }
      else if (path.endsWith('/products/1/')) body = { code: '00-А', nom: 'Тестовый ящик', method: 'exclusive', competitors: [] };
      else if (path.endsWith('/competitors/')) {
        if (request.method() === 'POST') { assert.equal(request.postDataJSON().expected_revision, editRevision); competitorChanges++; editRevision++; body = {}; }
        else body = { page: 1, pages: 1, edit_revision: editRevision, editable: true, changes: [], items: [{ id: 2, source: 'tt', url: 'https://example.test/competitor', mode: 'auto' }] };
      }
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'groups') body = { results: [{ key: 'Ящики', label: 'Ящики', product_count: 1, median_final_rrp: '150', median_retail_price: '100', median_market_price: '105' }], next_level: 'category', pagination: { page: 1, pages: 1 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'region_groups') body = { results: [{ key: 'СПБ', label: 'СПБ', product_count: 2, zones: [{key:'below_market',count:2,percent:100}], median_deviation_percent: -5, market_coverage_percent: 100 }], pagination: {page:1,pages:1} };
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('comparison_id')) body = { results: [{ base: { id: 1, snapshot_product_id: 1, code_1c: 'OLD', nom: 'Удалённый товар', sale_region: 'СПБ', effective_approved_rrp: '100' }, comparison: null, change_type: 'removed', key: 'removed-OLD' }], page: 1, total_pages: 1 };
      else if (path.endsWith('/analysis/')) body = { results: [{ code_1c: '00-А', nom: row.snapshot_product__nom, sale_region: 'СПБ', departure: 'Завод', final_rrp: manualPrice, retail_price: '100', market_price: '105', zone: 'below_market' }], pagination: { page: 1, pages: 1 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else throw new Error(`Unexpected request: ${path}`);
      if (path.endsWith('/analysis/') && !new URL(request.url()).searchParams.get('comparison_id')) {
        body.summary = { total_products: 2, median_deviation_percent: -4.76, median_final_rrp: 110, median_retail_price: 100, median_market_price: 105, calculation_errors: 0, zones: [{key:'below_market', count:2, percent:100}] };
      }
      await route.fulfill({ json: body });
    });
    await page.route(`${base}/iprice-check*`, route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><style>body{margin:0}</style></head><body><div class="app-shell sm-workspace"><div id="root"></div></div><script type="module">
      import '/src/index.css';
      import '/src/organizations/select-market.css';
      import React from '/node_modules/.vite/deps/react.js';
      import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const { SelectMarketIPrice } = await import('/src/iprice/selectMarket/SelectMarketIPrice.jsx');
      const componentSource = await (await fetch('/src/iprice/selectMarket/SelectMarketIPrice.jsx')).text();
      const routerModule = componentSource.match(/from ["']([^"']*react-router-dom[^"']*)["']/)[1];
      const { BrowserRouter } = await import(routerModule);
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(BrowserRouter, null, React.createElement(SelectMarketIPrice, { dashboard: {name: 'iPrice'} })));
    </script></body></html>` }));
    const capture = async name => {
      if (process.env.IPRICE_SCREENSHOT_DIR) {
        await page.evaluate(async () => { await document.fonts.ready; await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {}))); });
        await page.screenshot({ path: require('node:path').join(process.env.IPRICE_SCREENSHOT_DIR, name + '.png'), fullPage: true });
      }
    };
    await page.goto(`${base}/iprice-check?context=keep#suc=data&data=health`);
    await page.locator('.ip-nav a.active[href*="suc=data"]').waitFor();
    await page.locator('.ip-nav a[href*="suc=market"]').click();
    assert.equal(new URL(page.url()).searchParams.get('context'), 'keep');
    await page.goBack();
    await page.locator('.ip-nav a.active[href*="suc=data"]').waitFor();
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('data'), 'health');
    await page.goForward();
    await page.locator('.ip-nav a.active[href*="suc=market"]').waitFor();
    await page.goto(`${base}/iprice-check?context=keep#suc=home&data=uploads`);
    await page.locator('.ip-welcome').waitFor();
    await capture('current-home');
    const homeZoneRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/rows/') && new URL(r.url()).searchParams.get('zone') === 'below_market');
    await page.locator('.ip-attn').filter({ hasText: 'Ниже рынка' }).click();
    await homeZoneRequest;
    await page.getByRole('button', { name: 'Все зоны', exact: true }).click();
    await page.getByRole('link', { name: 'Главная', exact: true }).click();

    const helpButton = page.getByRole('button', { name: 'Справка', exact: true });
    await helpButton.click();
    await page.getByRole('dialog', { name: 'Справка', exact: true }).waitFor();
    assert.equal(await page.locator('.ip-help-three > div').count(), 3);
    const drawer = page.getByRole('dialog', { name: 'Справка', exact: true }).locator('.ip-drawer');
    assert.equal(await drawer.evaluate(el => Math.round(el.getBoundingClientRect().width)), 560);
    assert.equal(await drawer.locator('.ip-drawer-head').evaluate(el => getComputedStyle(el).padding), '20px 24px 12px');
    await capture('current-help');
    await page.keyboard.press('Escape');
    assert.equal(await helpButton.evaluate(el => el === document.activeElement), true);
    await helpButton.click();
    await page.getByRole('dialog', { name: 'Справка', exact: true }).getByRole('button', { name: 'Закрыть', exact: true }).click();
    await page.getByRole('link', { name: 'Данные', exact: true }).click();
    await page.locator('.sm-iprice-source-grid .ip-panel').first().waitFor();
    assert.equal(await page.locator('.sm-iprice-source-grid').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 2);
    await capture('current-data');
    await page.getByRole('tab', { name: 'Проверка данных', exact: true }).click();
    await page.getByText('Полный прайс пока не загружен.', { exact: false }).waitFor();
    await capture('current-health');
    failRowsOnce = true;
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByText('Временная ошибка строк', { exact: false }).waitFor();
    assert.equal(await page.getByText('Загружаем строки…', { exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Повторить загрузку строк', exact: true }).click();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    const productModeRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/rows/') && new URL(r.url()).searchParams.get('mode') === 'products');
    await page.getByRole('button', { name: 'Товары', exact: true }).click();
    await productModeRequest;
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).waitFor();
    const zoneRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/rows/') && new URL(r.url()).searchParams.get('zone') === 'below_market');
    const zoneFacets = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/filters/') && new URL(r.url()).searchParams.get('zone') === 'below_market' && new URL(r.url()).searchParams.get('mode') === 'products');
    await page.getByRole('button', { name: 'Ниже рынка', exact: true }).click();
    await zoneRequest;
    await zoneFacets;
    const problemsRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/rows/') && new URL(r.url()).searchParams.get('problems_only') === 'true');
    await page.getByRole('button', { name: 'Только с проблемами', exact: true }).click();
    await problemsRequest;
    await page.getByRole('button', { name: 'Все', exact: true }).click();
    await page.getByRole('button', { name: 'Все зоны', exact: true }).click();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByRole('button', { name: 'Ещё фильтры', exact: true }).click();
    await page.getByRole('dialog', { name: 'Фильтры', exact: true }).waitFor();
    await capture('current-filters');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).waitFor();
    const cardAddress = new URLSearchParams(new URL(page.url()).hash.slice(1));
    assert.equal(cardAddress.get('snapshot'), '1');
    assert.equal(cardAddress.get('product'), '1');
    assert.equal(JSON.parse(cardAddress.get('price_scope')).mode, 'regions');
    await page.reload();
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).waitFor();
    await page.goBack();
    await page.getByRole('button', { name: 'По регионам', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'По регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.goForward();
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).waitFor();
    await capture('current-product');
    await page.getByRole('tab', { name: 'Наша линейка', exact: true }).click();
    await page.getByRole('button', { name: 'Другой товар линейки', exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Рынок категории', exact: true }).click();
    await page.getByRole('heading', { name: 'Карточка рынка', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Не учитывать', exact: true }).click();
    const selection = page.getByRole('dialog', { name: 'Не учитывать цену этого товара?', exact: true });
    await selection.waitFor();
    assert.equal(await selection.getByRole('button', { name: 'Сохранить и пересчитать', exact: true }).isDisabled(), true);
    await selection.getByLabel('Причина', { exact: true }).fill('Проверка окна без сохранения');
    assert.equal(await selection.getByRole('button', { name: 'Сохранить и пересчитать', exact: true }).isDisabled(), false);
    await selection.getByRole('button', { name: 'Отмена', exact: true }).click();
    marketSize = 51;
    await page.getByRole('tab', { name: 'Цены по регионам', exact: true }).click();
    await page.getByRole('tab', { name: 'Рынок категории', exact: true }).click();
    await page.getByRole('button', { name: 'Не учитывать', exact: true }).click();
    await selection.getByText('В карточке больше 50 региональных позиций.', { exact: false }).waitFor();
    await selection.getByLabel('Причина', { exact: true }).fill('Не должно отправляться частями');
    assert.equal(await selection.getByRole('button', { name: 'Сохранить и пересчитать', exact: true }).isDisabled(), true);
    assert.equal(competitorChanges, 0);
    await selection.getByRole('button', { name: 'Отмена', exact: true }).click();
    marketSize = 1;
    await page.getByLabel('Только неучтённые').check();
    assert.equal(await page.getByRole('heading', { name: 'Карточка рынка', exact: true }).count(), 0);
    await page.getByRole('tab', { name: 'Цены по регионам', exact: true }).click();
    await page.getByText('Параметры позиции и доставка', { exact: true }).click();
    let positionEditor = page.getByRole('dialog', { name: 'Параметры позиции и доставка', exact: true });
    assert.equal(await positionEditor.getByLabel('Код 1С', { exact: true }).inputValue(), '00-А');
    await positionEditor.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('99');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
    await page.getByRole('button', { name: 'Второй ящик', exact: true }).click();
    await page.getByText('Параметры позиции и доставка', { exact: true }).click();
    positionEditor = page.getByRole('dialog', { name: 'Параметры позиции и доставка', exact: true });
    assert.equal(await positionEditor.getByLabel('Код 1С', { exact: true }).inputValue(), 'SECOND');
    assert.equal(await positionEditor.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).inputValue(), '');
    twoRows = false;
    await page.reload();
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByTitle(/Товар отсутствует на сайте.*Товар не классифицирован/).waitFor();
    await page.getByTitle(/После изменения параметров требуется повторное согласование цены/).waitFor();
    if (process.env.IPRICE_SCREENSHOT_DIR) {
      const path = require('node:path');
      await page.screenshot({ path: path.join(process.env.IPRICE_SCREENSHOT_DIR, 'select-market-desktop.png'), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.locator('.sm-iprice-table tbody tr').first().evaluate(element => element.getBoundingClientRect().height < 500), true, 'Mobile table must keep readable columns');
      await page.screenshot({ path: path.join(process.env.IPRICE_SCREENSHOT_DIR, 'select-market-mobile.png'), fullPage: true });
      assert.equal(await page.locator('.sm-iprice-table').evaluate(el => el.scrollWidth >= el.clientWidth), true);
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByRole('tab', { name: /^Конкуренты/ }).click();
    await page.getByText('Состав аналогов и история', { exact: true }).click();
    await page.getByLabel('Причина изменения аналогов').fill('Проверка аналога');
    await page.getByLabel('Участие аналога 2').selectOption('exclude');
    await page.getByRole('dialog', { name: 'Подтверждение действия' }).getByRole('button', { name: 'Подтвердить', exact: true }).click();
    await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByRole('button', { name: 'Своя цена', exact: true }).waitFor();
    assert.equal(competitorChanges, 1);
    await page.getByRole('button', { name: 'Своя цена', exact: true }).click();
    await page.getByRole('heading', { name: 'История цены', exact: true }).waitFor();
    await page.getByLabel('Своя РРЦ').fill('150');
    await page.getByLabel('Причина', { exact: true }).fill('Причина проверки');
    await page.getByRole('button', { name: 'Сохранить цену' }).click();
    await page.getByRole('dialog', { name: 'Своя цена', exact: true }).waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByText('Ручная цена', { exact: true }).waitFor();
    await page.getByText('Правила для списка', { exact: true }).click();
    await page.getByLabel('Минимальная маржа', { exact: true }).fill('100');
    assert.equal(await page.getByRole('button', {name:'Проверить выбор',exact:true}).isDisabled(), true);
    await page.getByLabel('Минимальная маржа', { exact: true }).fill('20');
    await page.getByLabel('Учитывать транспортные расходы', { exact: true }).selectOption('on');
    await page.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('12.34');
    await page.getByRole('button', { name: 'Проверить выбор' }).click();
    await page.getByRole('button', { name: 'Применить и пересчитать' }).click();
    await page.getByRole('dialog', { name: 'Подтверждение действия' }).getByRole('button', { name: 'Подтвердить', exact: true }).click();
    await page.waitForFunction(() => !document.body.textContent.includes('Товаров: 1, региональных строк: 1.'));
    assert.equal(parameterCalls, 2);
    await page.getByRole('link', { name: 'Рынок', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await capture('current-market-groups');
    await page.locator('.ip-advanced > summary').filter({hasText:'Пороги цветов'}).click();
    await page.getByLabel('Синий: дешевле рынка, разница меньше', {exact:true}).fill('-4');
    await page.getByLabel('Красный: риск, разница больше', {exact:true}).fill('2');
    assert.equal(await page.getByRole('button', {name:'Сохранить пороги',exact:true}).isDisabled(), true);
    await page.getByLabel('Красный: риск, разница больше', {exact:true}).fill('12');
    await page.getByRole('button', {name:'Сохранить пороги',exact:true}).click();
    await page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/analysis/'));
    assert.equal(zoneSaves, 1);
    assert.match(await page.getByRole('button', {name:'Ниже рынка',exact:true}).getAttribute('title'), /-4/);
    await capture('current-zone-settings');

    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.locator('.sm-market-page').getByRole('button', { name: 'СПБ', exact: true }).waitFor();
    const savedMarket = JSON.parse(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('market_scope'));
    assert.equal(savedMarket.comparison, '');
    await page.reload();
    await page.locator('.sm-market-page').getByRole('button', { name: 'СПБ', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'По регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await capture('current-market');
    await page.getByRole('button', { name: 'По группам товаров', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    assert.equal(await page.getByLabel('Группировка', { exact: true }).inputValue(), '1c');
    await page.getByLabel('Группировка', { exact: true }).selectOption('classification');
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await page.getByLabel('Группировка', { exact: true }).selectOption('1c');
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    const marketPanel = page.getByRole('heading', { name: 'Рынок и изменения цен', exact: true }).locator('..');
    await marketPanel.getByRole('button', { name: /^Группа 1:/ }).click();
    const filteredComparison = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/analysis/') && url.searchParams.get('view') === 'groups' && JSON.parse(url.searchParams.get('filters') || '{}').group_1?.includes('Торговый ассортимент');
    });
    await marketPanel.getByRole('checkbox', { name: 'Торговый ассортимент', exact: true }).check();
    await marketPanel.getByRole('button', { name: 'Готово', exact: true }).click();
    await filteredComparison;
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.locator('.sm-market-page').getByRole('button', { name: 'СПБ', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Расчёты', exact: true }).click();
    await page.getByLabel('Старый расчёт', { exact: true }).selectOption('2');
    await page.getByLabel('Новый расчёт', { exact: true }).selectOption('1');
    const compareProductsRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/analysis/') && new URL(r.url()).searchParams.get('comparison_id') === '2' && new URL(r.url()).searchParams.get('mode') === 'products');
    await page.getByRole('button', { name: 'Показать изменения', exact: true }).click();
    await compareProductsRequest;
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('compare_from'), '2');
    const restoredComparison = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/snapshots/1/analysis/') && new URL(r.url()).searchParams.get('comparison_id') === '2');
    await page.reload();
    await restoredComparison;
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).waitFor();
    const compareRegionsRequest = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/analysis/') && new URL(r.url()).searchParams.get('mode') === 'regions' && new URL(r.url()).searchParams.get('change_type') === 'removed');
    await page.getByRole('button', { name: 'Товары по регионам', exact: true }).click();
    await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).click();
    await compareRegionsRequest;
    await page.reload();
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('button', { name: 'Товары по регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).click();
    await page.getByRole('button', { name: 'К сравнению', exact: true }).waitFor();
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('compare_snapshot'), '2');
    await page.reload();
    await page.getByRole('button', { name: 'К сравнению', exact: true }).waitFor();
    await page.goBack();
    await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).waitFor();
    await capture('current-comparison');
    // Another editor changes this version while the current user views old data.
    editRevision++;
    await page.getByRole('button', { name: 'Обновить расчёт', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Расчёты', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Утвердить внутри системы' }).isDisabled(), true);
    await capture('current-versions');
    await page.getByRole('button', { name: 'Обновить расчёт', exact: true }).click();
    await page.getByRole('button', { name: 'Утвердить внутри системы' }).click();
    await page.getByRole('dialog', { name: 'Подтверждение действия' }).getByRole('button', { name: 'Подтвердить', exact: true }).click();
    await page.getByRole('button', { name: 'Версия утверждена', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    canEdit = false;
    await page.reload();
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    assert.equal(await page.getByRole('button', { name: 'Рассчитать цены', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Скачать Excel', exact: true }).waitFor();
    canEdit = true;
    approved = false;
    version.historical_routes = true;
    await page.reload();
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    await page.getByText('Историческая версия с маршрутами: доступны просмотр и выгрузка. Для изменения цен создайте новый расчёт.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Скачать Excel', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Утвердить внутри системы', exact: true }).count(), 0);
    await page.getByRole('link', { name: 'Данные', exact: true }).click();
    await page.getByRole('tab', { name: 'Файлы', exact: true }).click();
    await page.getByLabel('Дата полного прайса', { exact: true }).fill('2026-10-15');
    const priceCard = page.locator('.sm-iprice-source-grid .ip-panel').first();
    await priceCard.locator('input[type=file]').setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('fixture') });
    await page.getByText('В файле не заполнен код товара.', { exact: true }).waitFor();
    version.historical_routes = false;
    version.status = 'building';
    await page.reload();
    await page.getByRole('link', { name: 'Цены', exact: true }).click();
    await page.getByLabel('Последние 50 версий').selectOption('1');
    assert.equal(await page.getByRole('button', { name: 'Своя цена', exact: true }).count(), 0);
    assert.equal(await page.getByText('Правила для списка', { exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Скачать Excel', exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('Select Market iPrice React: price edit, parameter preview/apply, market, activation and viewer rights passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
