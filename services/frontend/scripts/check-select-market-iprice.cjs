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
    let drillProducts = false;
    let manyImports = false, manyCards = false, emptyCards = false;
    let zoneSaves = 0;
    let priceZones = { below_market_threshold: "-0.03", above_market_threshold: "0.03", critical_threshold: "0.1" };
    const version = { id: 1, version_number: 1, calculation_date: '2026-10-14', status: 'success', is_current: true, is_active: false, was_active: false };
    const row = { id: 1, product_id: 1, snapshot_product__code_1c: '00-А', snapshot_product__nom: 'Тестовый ящик', snapshot_product__image: 'https://images.example.test/product.svg',
      sale_region: 'СПБ', departure: 'Завод', current_retail: '100', cost_with_logistics: '60', minimum_price: '70',
      calculated_rrp: '110', regional_competitor_rrp_median: '105', regional_competitor_rrp_min: '90', regional_competitor_rrp_max: '120',
      calculation_status: 'warning', error_codes: [], warning_codes: ['MISSING_WEBSITE_PRODUCT', 'MISSING_CLASSIFICATION', 'REAPPROVAL_REQUIRED'] };
    await page.route('https://images.example.test/**', route => route.fulfill({contentType:'image/svg+xml', body:'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="blue"/></svg>'}));
    await page.route('**/v1/select-market/iprice/**' , async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      let body;
      if (path.endsWith('/status/')) body = { can_edit: canEdit, imports: manyImports ? Array.from({length:20}, (_,i)=>({id:i+1,kind:"product_cost",filename:"cost-"+i+".xlsx",created_at:new Date(2026,9,23,12,i).toISOString()})) : [], price_imports: [], parsers_enabled: false, run: null, queue: [] };
      else if (path.endsWith('/health/')) body = { price_date: null, source_checks: [], snapshot: null, issues: [] };
      else if (path.endsWith('/own/')) body = { counts: { cards: 1 }, results: [{ snapshot_product_id: 3, code_1c: 'OWN', name: 'Другой товар линейки', price: 123, final_price: 123, regional_prices: [{ region: 'СПБ', price: 123, final_price: 123 }] }] };
      else if (path.endsWith('/market/')) body = { editable: true, edit_revision: editRevision, counts: { cards: 1, used_in_snapshot: 1 }, results: [{ group_key: ['tt', 2], competitor_product_keys: Array.from({ length: marketSize }, (_, i) => i + 2), selection_mode: 'auto', source: 'tt', name: 'Карточка рынка', price: 105, regional_entries: [{region:'СПБ',price:105,urls:['https://example.test/spb']},{region:'Москва',price:115,urls:['https://example.test/moscow']}], regions: ['СПБ'], is_used_in_snapshot: true }] };
      else if (path.endsWith('/price-zones/')) {
        if (request.method() === 'POST') {
          priceZones = request.postDataJSON();
          assert.deepEqual(priceZones, {below_market_threshold: "-0.040000", above_market_threshold: "0.030000", critical_threshold: "0.120000"});
          zoneSaves++;
        }
        body = priceZones;
      }
      else if (path.endsWith('/snapshots/')) body = [{ ...version, is_active: approved, was_active: approved, edit_revision: editRevision }, { ...version, id: 2, version_number: 0, calculation_date: '2026-10-13', is_current: false }];
      else if (path.endsWith('/filters/')) body = { group_2: ['Торговый ассортимент'], is_classified: ['true'] };
      else if (path.endsWith('/rows/')) {
        if (failRowsOnce) { failRowsOnce = false; await route.fulfill({ status: 503, json: { detail: 'Временная ошибка строк' } }); return; }
        const first = { ...row, effective: { rrp: manualPrice || '110', approval_revision: manualPrice ? 1 : 0, approval_source: manualPrice ? 'manual' : 'calculated' } };
        body = { rows: twoRows ? [first, { ...first, id: 2, snapshot_product__code_1c: 'SECOND', snapshot_product__nom: 'Второй ящик' }] : [first], page: 1, pages: 1, count: twoRows ? 2 : 1 };
        if (new URL(request.url()).searchParams.get('product_id') === '3') body = { rows: [{ ...first, id: 3, product_id: 3, snapshot_product__code_1c: 'OWN', snapshot_product__nom: 'Другой товар линейки' }], page: 1, pages: 1, count: 1 };
        if (new URL(request.url()).searchParams.get('mode') === 'products') body = { rows: [{ product_id: 1, regions: [first], summary: { current_retail_median: '100', effective_approved_rrp_median: manualPrice || '110', competitor_rrp_median: '105', competitor_count: 1, pricing_method: 'analog', calculation_status: 'warning', error_codes: [], warning_codes: row.warning_codes, zone: 'below_market' } }], page: 1, pages: 1, count: 1 };
      }
      else if (path.endsWith('/price-file/') && request.method() === 'POST') { await route.fulfill({ status: 400, json: { file: ['В файле не заполнен код товара.'] } }); return; }
      else if (path.endsWith('/history/') && new URL(request.url()).searchParams.has('parameter_change_id')) {
        const page = Number(new URL(request.url()).searchParams.get('page') || 1);
        body = { available: true, page, pages: 2, count: 26,
          results: Array.from({length: page === 1 ? 25 : 1}, (_, i) => ({id:(page-1)*25+i, name:`History product ${(page-1)*25+i}`, code_1c:`H-${(page-1)*25+i}`, regions:['Москва']})) };
      }
      else if (path.endsWith('/history/')) body = {
        activations: [{ at: '2026-10-24T10:00:00Z', username: 'reviewer@example.test', action: 'deactivate', previous_snapshot_ids: [2] }],
        approvals: [{ id: 1, snapshot_region__snapshot_product__code_1c: '00-А', snapshot_region__sale_region: 'СПБ', approved_rrp: '150', approved_by__username: 'reviewer@example.test', approved_at: '2026-10-24T09:00:00Z', comment: 'Длинная причина согласования цены для проверки переноса строк. '.repeat(8), is_current: false }],
        parameter_changes: [
          { id: 1, targets:{available:true,count:1,first:{id:1,name:'Исторический товар',code_1c:'H-ONE',regions:['Москва','Казань']}}, created_at: '2026-10-24T09:00:00Z', user__username: null, status: 'success', changes: { minimum_margin: '0.20', include_transport: false, logistics_unit: '12.34' } },
          { id: 2, targets:{available:true,count:26}, created_at: '2026-10-24T08:00:00Z', user__username: 'reviewer@example.test', status: 'pending', changes: { coefficients: { base_analog: '1.050000' }, discounts: { small: '0.04' } } },
        ], page: 1, pages: 1, count: 1,
      };
      else if (path.endsWith('/approval/') && request.method() === 'GET') { const price = new URL(request.url()).searchParams.get('price'); body = { price, prices: { rrp: price, small: price, medium: price, large: price }, gross: { rrp: price, small: price, medium: price, large: price }, margin: 0.4, valid: true }; }
      else if (path.endsWith('/approval/')) { const data = request.postDataJSON(); assert.equal(data.expected_revision, 0); assert.equal(data.comment, 'Причина проверки'); manualPrice = data.approved_rrp; editRevision++; body = { revision: 1 }; }
      else if (path.endsWith('/parameters/')) { const data = request.postDataJSON(); parameterCalls++; assert.equal(data.coefficients.minimum_margin, "0.200000"); assert.deepEqual(data.delivery, { include_transport: true, logistics_unit: '12.34' }); assert.deepEqual(data.filters, {}); assert.deepEqual(data.list_scope, { mode: 'regions', zone: '', problems_only: false }); if (!data.preview) { assert.equal(data.reason, 'Group price review'); assert.equal(data.expected_revision, editRevision); assert.equal(data.expected_scope, "a".repeat(64)); assert.equal(data.expected_manual_signature, "b".repeat(64)); assert.deepEqual(data.preserve_manual_row_ids, []); editRevision++; } body = { affected: { products: 3, regions: 3, routes: 3, scope_signature: "a".repeat(64), manual_signature: "b".repeat(64),
        manual_prices: [1,2,3].map(id => { const decision = {id,price:"150",user:"reviewer@example.test",at:"2026-10-24T09:00:00Z",version:id === 3 ? 1 : 2}; return {row_id:id,product_id:id,code_1c:"MANUAL-"+id,name:"Manual product "+id,region:"Region",current:id === 3 ? null : decision,latest:decision}; }) }, edit_revision: editRevision }; }
      else if (path.endsWith('/activate/')) { assert.equal(request.postDataJSON().expected_revision, editRevision); approved = true; body = { id: 1, is_active: true }; }
      else if (path.endsWith('/products/3/')) body = { code: 'OWN', nom: 'Другой товар линейки', method: 'exclusive', competitors: [] };
      else if (path.endsWith('/products/1/')) body = { code: '00-А', nom: 'Тестовый ящик', method: 'exclusive', category: 'Ящики', subcategory: 'Пищевые', subcategory_type: 'С крышкой', assortment_matrix_status: '3. Под заказ / заказная позиция', competitors: [] };
      else if (path.endsWith('/competitors/')) {
        if (request.method() === 'POST') { assert.equal(request.postDataJSON().expected_revision, editRevision); competitorChanges++; editRevision++; body = {}; }
        else body = { page: 1, pages: 1, edit_revision: editRevision, editable: true, changes: [], items: [{ id: 2, source: 'tt', url: 'https://example.test/competitor', mode: 'auto' }] };
      }
      else if (drillProducts && path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'groups') {
        const leaf = new URL(request.url()).searchParams.get('drill_level') === 'category';
        body = { next_level: leaf ? null : 'category', results: leaf ? [{id:1, code_1c:'00-А', nom:'Тестовый ящик', image:row.snapshot_product__image, median_final_rrp:150}] : [{key:'__empty__',label:'Не указано',product_count:1}], pagination:{page:1,pages:1,count:1,page_size:50} };
      }
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'groups') body = { results: [{ key: 'Ящики', label: 'Ящики', product_count: 1, median_final_rrp: '150', median_retail_price: '100', median_market_price: '105' }], next_level: 'category', pagination: { page: 1, pages: 1, count: 1, page_size: 50 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('view') === 'region_groups') body = { results: [{ key: 'СПБ', label: 'СПБ', product_count: 2, zones: [{key:'below_market',count:2,percent:100}], median_deviation_percent: -5, market_coverage_percent: 100 }], pagination: {page:1,pages:1,count:1,page_size:50} };
      else if (path.endsWith('/analysis/') && new URL(request.url()).searchParams.get('comparison_id')) body = { results: [{ base: { id: 1, snapshot_product_id: 1, code_1c: 'OLD', nom: 'Удалённый товар', sale_region: 'СПБ', effective_approved_rrp: '100' }, comparison: null, change_type: 'removed', key: 'removed-OLD' }], page: 1, total_pages: 1, filtered_count: 1 };
      else if (path.endsWith('/analysis/')) body = { results: [{ code_1c: '00-А', nom: row.snapshot_product__nom, sale_region: 'СПБ', departure: 'Завод', final_rrp: manualPrice, retail_price: '100', market_price: '105', zone: 'below_market' }], pagination: { page: 1, pages: 1, count: 1, page_size: 50 }, price_zones: { below_market_percent: -3, above_market_percent: 3, critical_percent: 10 } };
      else throw new Error(`Unexpected request: ${path}`);
      if (path.endsWith('/analysis/') && !new URL(request.url()).searchParams.get('comparison_id')) {
        body.summary = { total_products: 2, market_coverage_percent: 100, median_deviation_percent: -4.76, median_final_rrp: 110, median_retail_price: 100, median_market_price: 105, calculation_errors: 0, zones: [{key:'below_market', count:2, percent:100}] };
      }
      if (path.endsWith('/market/') && competitorChanges) body.results = body.results.map(card => ({...card, selection_mode:'exclude', is_used_in_snapshot:false}));
      if (manyCards && (path.endsWith('/market/') || path.endsWith('/own/'))) {
        body.results = Array.from({length:61}, (_,i)=>({...body.results[0], group_key:['test',i], snapshot_product_id:i+3, name:'Товар '+i, color:i%2?'красный':'синий', material:'PE/PP', modification:i%2?'С крышкой':'Без крышки'}));
        body.counts.cards=61;
      }
      if (emptyCards && (path.endsWith('/market/') || path.endsWith('/own/'))) { body.results=[]; body.counts={cards:0}; }
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
    await page.waitForFunction(() => {
      const heading = document.querySelector('#sm-help-about');
      const body = heading.closest('.ip-drawer-body');
      return heading.getBoundingClientRect().top >= body.getBoundingClientRect().top && body.scrollTop === 0;
    });
    assert.equal(await drawer.locator('.ip-help-zones .ip-tag[class*="z-"] .ip-i').count(), 5);
    assert.match(await drawer.innerText(), /В форме маржа и скидки вводятся в процентах/);
    await capture('current-help');
    await page.keyboard.press('Escape');
    assert.equal(await helpButton.evaluate(el => el === document.activeElement), true);
    await helpButton.click();
    await page.getByRole('dialog', { name: 'Справка', exact: true }).getByRole('button', { name: 'Закрыть', exact: true }).click();
    await page.getByRole('link', { name: 'Данные', exact: true }).click();
    await page.locator('.sm-iprice-source-grid .ip-panel').first().waitFor();
    assert.equal(await page.locator('.sm-iprice-source-grid').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 3);
    await capture('current-data');
    const uploadRows = await page.locator('.sm-iprice-source-grid .ip-drop').evaluateAll(elements => elements.map(el => el.getBoundingClientRect().top));
    assert.ok(Math.abs(uploadRows[0] - uploadRows[1]) < 2 && Math.abs(uploadRows[1] - uploadRows[2]) < 2, 'Upload controls must align within each row');
    await page.getByRole('tab', { name: 'Цены конкурентов', exact: true }).click();
    await page.getByRole('heading', { name: 'Сбор цен конкурентов', exact: true }).waitFor();
    assert.ok(await page.getByText('Ещё не собирали', { exact: true }).evaluate(el => el.getBoundingClientRect().width < el.parentElement.getBoundingClientRect().width / 2), 'Parser status must be a compact badge');
    await capture('current-parser');
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
    await page.getByRole('button', { name: 'По товарам', exact: true }).click();
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
    const formats = await page.evaluate(async () => {
      const { priceText } = await import('/src/iprice/selectMarket/format.js');
      const { fmtPct } = await import('/src/iprice/selectMarket/archiveFormat.js');
      return [priceText('1234.5'), priceText(null), priceText(''), fmtPct(0.125), fmtPct(-0.125, { sign: true }), fmtPct(0.4545, { digits: 0 })];
    });
    assert.deepEqual(formats, ['1\u00a0234,50', '—', '—', '12,5\u00a0%', '−12,5\u00a0%', '45\u00a0%']);
    const pager = page.locator('.sm-price-panel .ip-pager');
    await pager.getByText('Показаны 1–2 из 2', { exact: true }).waitFor();
    assert.equal(await pager.getByRole('button', {name:'Назад',exact:true}).isDisabled(), true);
    assert.equal(await pager.getByRole('button', {name:'Вперёд',exact:true}).isDisabled(), true);
    assert.equal(await pager.getByRole('button', {name:'1',exact:true}).getAttribute('aria-current'), 'true');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).waitFor();
    const cardAddress = new URLSearchParams(new URL(page.url()).hash.slice(1));
    assert.equal(cardAddress.get('snapshot'), '1');
    assert.equal(cardAddress.get('product'), '1');
    assert.equal(cardAddress.get('p_mode'), 'regions');
    await page.reload();
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).waitFor();
    await page.goBack();
    await page.getByRole('button', { name: 'По регионам', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'По регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.goForward();
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).waitFor();
    await page.getByText('САМ: 3. Под заказ / заказная позиция', { exact: true }).waitFor();
    const samTag = page.getByText('САМ: 3. Под заказ / заказная позиция', { exact: true });
    assert.equal(await samTag.evaluate(el => !!el.closest('.ip-tag')), true);
    await samTag.hover();
    await page.getByRole('tooltip').filter({hasText:'2. Активный / складская программа'}).waitFor();
    assert.match(await page.getByRole('navigation', {name:'Путь товара'}).innerText(), /Цены.*Ящики.*Пищевые.*С крышкой/s);
    await page.locator('h1').last().hover();

    await capture('current-product');
    await page.getByRole('tab', { name: /^Наша линейка ·/ }).click();
    await page.getByRole('button', { name: 'Другой товар линейки', exact: true }).waitFor();
    await page.getByRole('tab', {name:'Наша линейка · 1',exact:true}).waitFor();
    await capture('current-own-assortment');
    await page.getByRole('tab', {name:'Рынок категории · 1',exact:true}).waitFor();
    assert.equal(await page.getByRole('button', {name:'Другой товар линейки',exact:true}).evaluate(el => getComputedStyle(el).textAlign), 'left');
    await page.getByRole('button', {name:'Другой товар линейки',exact:true}).click();
    await page.getByRole('heading', {name:'Другой товар линейки',exact:true}).waitFor();
    await page.getByRole('button', {name:'Вернуться к товару',exact:true}).click();
    await page.getByRole('heading', {name:'Тестовый ящик',exact:true}).waitFor();
    assert.equal(await page.getByRole('tab',{name:'Наша линейка · 1',exact:true}).getAttribute('aria-selected'), 'true');

    await page.getByRole('tab', { name: /^Рынок категории ·/ }).click();
    await page.getByRole('heading', { name: 'Карточка рынка', exact: true }).waitFor();
    const aligned = await page.evaluate(() => {
      const card = document.querySelector('.sm-competitor-card');
      const clones = [1, 2].map(n => {
        const copy = card.cloneNode(true);
        copy.querySelector('.ip-card-title').textContent = 'Long product name '.repeat(n * 5);
        card.parentElement.append(copy);
        return copy;
      });
      const cards = [card, ...clones];
      const positions = ['.ip-props', '.price', '.sm-competitor-card-actions'].map(selector => cards.map(el => el.querySelector(selector).getBoundingClientRect().top));
      const overflow = cards.some(el => el.scrollWidth > el.clientWidth + 1 || [...el.querySelectorAll('.ip-seg button')].some(button => {
        const range = document.createRange(); range.selectNodeContents(button);
        return range.getBoundingClientRect().bottom > button.getBoundingClientRect().bottom + 1;
      }));
      clones.forEach(el => el.remove());
      return { positions, overflow };
    });
    for (const positions of aligned.positions) assert.ok(Math.max(...positions) - Math.min(...positions) < 2, 'Card sections must align despite different title lengths');
    assert.equal(aligned.overflow, false, 'Card controls must fit the card');
    await page.getByRole('button', { name: 'Не учитывать', exact: true }).click();
    const selection = page.getByRole('dialog', { name: 'Не учитывать цену этого товара?', exact: true });
    await selection.waitFor();
    assert.equal(await selection.getByRole('button', { name: 'Сохранить и пересчитать', exact: true }).isDisabled(), true);
    await selection.getByLabel('Причина', { exact: true }).fill('Проверка окна без сохранения');
    assert.equal(await selection.getByRole('button', { name: 'Сохранить и пересчитать', exact: true }).isDisabled(), false);
    await selection.getByRole('button', { name: 'Отмена', exact: true }).click();
    marketSize = 51;
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).click();
    await page.getByRole('button', { name: 'Тестовый ящик', exact: true }).click();
    await page.getByRole('tab', { name: /^Рынок категории ·/ }).click();
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
    await page.getByText('Настройки параметров расчета', { exact: true }).click();
    let positionEditor = page.getByRole('dialog', { name: 'Настройки параметров расчета', exact: true });
    assert.equal(await positionEditor.getByLabel('Код 1С', { exact: true }).inputValue(), '00-А');
    await positionEditor.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('99');
    await page.keyboard.press('Escape');
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).click();
    await page.getByRole('button', { name: 'Второй ящик', exact: true }).click();
    await page.getByText('Настройки параметров расчета', { exact: true }).click();
    positionEditor = page.getByRole('dialog', { name: 'Настройки параметров расчета', exact: true });
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
    await page.getByRole('tab', { name: /^Рынок категории/ }).click();
    await page.getByRole('button', { name: 'История учёта', exact: true }).click();
    await page.getByRole('heading', {name:'Последние 50 изменений',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Участие аналога 2').count(),0);
    await page.getByRole('dialog',{name:'История учёта',exact:true}).getByRole('button',{name:'Закрыть',exact:true}).click();
    await page.getByRole('button', {name:'Не учитывать',exact:true}).click();
    await page.getByLabel('Причина', {exact:true}).fill('Проверка аналога');
    await page.getByRole('button',{name:'Сохранить и пересчитать',exact:true}).click();
    await page.waitForFunction(() => !document.querySelector('dialog[open]'));
    assert.equal(await page.getByRole('tab', {name:/^Рынок категории/}).getAttribute('aria-selected'), 'true');
    await page.getByText('Исключён',{exact:true}).waitFor();
    await page.getByRole('navigation', { name: 'Путь товара' }).getByRole('button', { name: 'Цены', exact: true }).click();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByRole('button', { name: 'Своя цена', exact: true }).waitFor();
    assert.equal(competitorChanges, 1);
    await page.getByRole('button', { name: 'Своя цена', exact: true }).click();
    await page.getByRole('heading', { name: 'История цены', exact: true }).waitFor();
    assert.equal(await page.getByLabel('Причина', { exact: true }).evaluate(el => getComputedStyle(el).minHeight), '64px');
    await capture('current-price-editor');
    await page.getByRole('heading',{name:'История цены',exact:true}).scrollIntoViewIfNeeded();
    assert.equal(await page.getByRole('heading',{name:'История цены',exact:true}).evaluate(el => !!(el.closest('section').previousElementSibling?.matches('details'))), true);
    await capture('current-price-history');
    const numericPrice = page.getByLabel('Ваша цена');
    await numericPrice.focus();
    const priceBeforeWheel = await numericPrice.inputValue();
    await numericPrice.hover();
    await page.mouse.wheel(0, 120);
    await page.waitForFunction(() => document.activeElement?.type !== 'number');
    assert.equal(await numericPrice.inputValue(), priceBeforeWheel, 'Scrolling must not change a focused numeric value');
    assert.equal(await numericPrice.evaluate(el => getComputedStyle(el).appearance), 'textfield');
    const priceDialog = page.getByRole('dialog', { name: 'Цена: СПБ', exact: true });
    await page.getByLabel('Причина', { exact: true }).fill('Причина проверки');
    await page.waitForFunction(() => !document.querySelector('dialog[open] button[type="submit"]').disabled);
    const ladder = priceDialog.getByRole('table', { name: 'Цены по ступеням', exact: true });
    const ladderNode = await ladder.elementHandle();
    const reasonTop = await priceDialog.getByLabel('Причина', { exact: true }).evaluate(el => el.getBoundingClientRect().top);
    let releasePreview;
    const previewGate = new Promise(resolve => { releasePreview = resolve; });
    const previewUrl = '**/rows/1/approval/?price=151';
    await page.route(previewUrl, async route => {
      await previewGate;
      await route.fulfill({ json: { price: '151', prices: { rrp: '151', small: '151', medium: '151', large: '151' }, gross: {}, margin: 0.4, valid: true } });
    });
    const previewRequest = page.waitForRequest(r => r.url().includes('/approval/?price=151'));
    await page.getByLabel('Ваша цена').fill('151');
    await previewRequest;
    assert.equal(await ladderNode.evaluate(el => el.isConnected), true, 'Price ladder must not unmount while preview loads');
    assert.equal(await page.getByRole('button', { name: 'Сохранить цену' }).isDisabled(), true);
    assert.match(await priceDialog.innerText(), /Показан предыдущий результат/);
    assert.ok(Math.abs(await priceDialog.getByLabel('Причина', { exact: true }).evaluate(el => el.getBoundingClientRect().top) - reasonTop) < 2, 'Reason field must stay in place while typing');
    releasePreview();
    await page.waitForFunction(() => !document.querySelector('dialog[open] button[type="submit"]').disabled);
    await page.unroute(previewUrl);
    await page.getByLabel('Ваша цена').fill('');
    assert.equal(await ladderNode.evaluate(el => el.isConnected), true);
    assert.equal(await page.getByRole('button', { name: 'Сохранить цену' }).isDisabled(), true);
    await page.getByLabel('Ваша цена').fill('150');
    await page.getByLabel('Причина', { exact: true }).fill('Причина проверки');
    await page.getByRole('button', { name: 'Сохранить цену' }).click();
    await page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/rows/'));
    assert.equal(await priceDialog.isVisible(), true);
    await priceDialog.getByRole('button', {name:'Закрыть',exact:true}).click();
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByText('Ручная цена', { exact: true }).waitFor();
    await page.getByText('Настройки параметров расчета', { exact: true }).click();
    await page.getByLabel('Минимальная маржа', { exact: true }).fill('100');
    assert.equal(await page.getByRole('button', {name:'Проверить выбор',exact:true}).isDisabled(), true);
    await page.getByLabel('Минимальная маржа', { exact: true }).fill('20');
    await page.getByLabel('Учитывать транспортные расходы', { exact: true }).selectOption('on');
    await page.getByLabel('Доставка на единицу, руб. без НДС', { exact: true }).fill('12.34');
    await page.getByRole('button', { name: 'Проверить выбор' }).click();
    await page.getByRole('button', { name: 'Применить и пересчитать' }).waitFor();
    await capture('current-parameters');
    assert.equal(await page.getByRole('button', { name: 'Применить и пересчитать' }).isDisabled(), true);
    await page.getByLabel('Причина изменения', { exact: true }).fill('   ');
    assert.equal(await page.getByRole('button', { name: 'Применить и пересчитать' }).isDisabled(), true);
    await page.getByLabel('Причина изменения', { exact: true }).fill('  Group price review  ');
    const manualChoices = page.locator('.sm-manual-prices');
    assert.equal(await manualChoices.getAttribute('open'),null);
    await manualChoices.locator('summary').click();
    const allManual = page.getByRole('checkbox', {name:'Сохранить все действующие ручные цены',exact:true});
    assert.equal(await allManual.isChecked(),true);
    await allManual.uncheck();
    const firstManual = page.getByRole('checkbox', {name:'Сохранить · Код 1С: MANUAL-1 · Region',exact:true});
    await firstManual.check();
    assert.equal(await firstManual.isChecked(),true);
    assert.equal(await page.getByRole('checkbox', {name:'Сохранить · Код 1С: MANUAL-2 · Region',exact:true}).isChecked(),false);
    await firstManual.uncheck();
    assert.equal(await manualChoices.getByText('Manual product 3',{exact:true}).count(),0);
    assert.ok(await manualChoices.locator('.sm-manual-check').first().evaluate(label => {
      const box = label.querySelector('input').getBoundingClientRect();
      const text = label.querySelector('span').getBoundingClientRect();
      return box.right <= text.left && Math.abs(box.top - text.top) < 8;
    }));
    await manualChoices.locator('summary').click();
    assert.equal(await manualChoices.getAttribute('open'),null);
    await page.getByRole('button', { name: 'Применить и пересчитать' }).click();
    await page.getByRole('dialog', { name: 'Подтверждение действия' }).getByRole('button', { name: 'Подтвердить', exact: true }).click();
    await page.waitForFunction(() => !document.body.textContent.includes('Товаров: 1, региональных строк: 1.'));
    assert.equal(parameterCalls, 2);
    await page.getByRole('dialog', {name:'Настройки параметров расчета',exact:true}).getByRole('button',{name:'Закрыть',exact:true}).click();
    await page.getByRole('link', { name: 'Рынок', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await capture('current-market-groups');
    await page.getByRole('button',{name:'Пороги цветов',exact:true}).click();
    await page.getByLabel('Синий: дешевле рынка, разница меньше', {exact:true}).fill('-4');
    await page.getByLabel('Красный: риск, разница больше', {exact:true}).fill('2');
    assert.equal(await page.getByRole('button', {name:'Сохранить пороги',exact:true}).isDisabled(), true);
    await page.getByLabel('Красный: риск, разница больше', {exact:true}).fill('12');
    await page.getByRole('button', {name:'Сохранить пороги',exact:true}).click();
    await page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/analysis/'));
    assert.equal(zoneSaves, 1);
    assert.match(await page.getByRole('button', {name:'Ниже рынка',exact:true}).getAttribute('title'), /-4/);
    await capture('current-zone-settings');
    await page.getByRole('dialog',{name:'Пороги цветов',exact:true}).getByRole('button',{name:'Закрыть',exact:true}).click();

    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.locator('.sm-market-page').getByRole('button', { name: 'СПБ', exact: true }).waitFor();
    const savedMarket = { comparison: new URLSearchParams(new URL(page.url()).hash.slice(1)).get('m_comparison') };
    assert.equal(savedMarket.comparison, '');
    await page.reload();
    await page.locator('.sm-market-page').getByRole('button', { name: 'СПБ', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'По регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await capture('current-market');
    await page.getByRole('button', { name: 'По товарам', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    assert.equal(await page.getByRole('group', { name: 'Группировка', exact: true }).getByRole('button', { name: 'Классификация iPrice', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('group', { name: 'Группировка', exact: true }).getByRole('button', { name: 'Классификация iPrice', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    await page.getByRole('group', { name: 'Группировка', exact: true }).getByRole('button', { name: 'Группы 1С', exact: true }).click();
    await page.getByRole('button', { name: 'Ящики', exact: true }).waitFor();
    const marketPanel = page.getByRole('heading', { name: 'Рынок и изменения цен', exact: true }).locator('..');
    await marketPanel.getByRole('button', { name: /^Группа 1:/ }).click();
    const filteredComparison = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/analysis/') && url.searchParams.get('view') === 'groups' && JSON.parse(url.searchParams.get('filters') || '{}').group_2?.includes('Торговый ассортимент');
    });
    await marketPanel.getByRole('checkbox', { name: 'Торговый ассортимент', exact: true }).check();
    await marketPanel.getByRole('button', { name: 'Готово', exact: true }).click();
    await filteredComparison;
    const clearGroup = marketPanel.getByRole('button', { name: 'Сбросить «Группа 1»', exact: true });
    assert.equal(await clearGroup.evaluate(el => {
      const reset = el.getBoundingClientRect();
      const chip = el.parentElement.querySelector('.ip-chip').getBoundingClientRect();
      return reset.left >= chip.left && reset.right <= chip.right && reset.top >= chip.top && reset.bottom <= chip.bottom;
    }), true, 'Reset control must sit inside the selected filter pill');
    await clearGroup.focus();
    await page.keyboard.press('Enter');
    await marketPanel.getByRole('button', { name: 'Группа 1: все', exact: true }).waitFor();
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
    await page.getByRole('button', { name: 'По регионам', exact: true }).click();
    await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).click();
    await compareRegionsRequest;
    await page.reload();
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('button', { name: 'По регионам', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).click();
    await page.getByRole('button', { name: 'К сравнению', exact: true }).waitFor();
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('snapshot'), '2');
    await page.reload();
    await page.getByRole('button', { name: 'К сравнению', exact: true }).waitFor();
    await page.goBack();
    await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Выбывшие товары', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Удалённый товар', exact: true }).waitFor();
    await capture('current-comparison');
    assert.equal(await page.locator('.ip-page-head').filter({ has: page.getByRole('group', { name: 'Уровень сравнения', exact: true }) }).count(), 1);
    await page.getByText(/Было: версия 2. Стало: версия 1/).waitFor();
    // Another editor changes this version while the current user views old data.
    editRevision++;
    await page.getByRole('button', { name: 'Обновить расчёт', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Расчёты', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Утвердить внутри системы' }).isDisabled(), true);
    await capture('current-versions');
    assert.equal(await page.locator('.sm-version-history').count(), 0);
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
    assert.equal(await page.getByText('Настройки параметров расчета', { exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Скачать Excel', exact: true }).count(), 0);

    version.status = 'success'; canEdit = true; approved = false;
    await page.reload();
    await page.getByRole('link', {name:'Цены',exact:true}).click();
    await page.getByRole('button', {name:'Тестовый ящик',exact:true}).waitFor();
    for (let i=1;i<=3;i++) await page.getByRole('button',{name:new RegExp('^Группа '+i+':')}).waitFor();
    await page.locator('.sm-price-panel .iprice-product-image-trigger').first().hover();
    await page.locator('.iprice-product-image-preview--positioned').waitFor();
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).click();
    await page.getByRole('navigation',{name:'Путь товара'}).getByRole('button',{name:'Цены',exact:true}).waitFor();
    await page.getByRole('link',{name:'Главная',exact:true}).click();
    await page.getByRole('link',{name:'Цены',exact:true}).click();
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).waitFor();
    assert.equal(await page.getByRole('navigation',{name:'Путь товара'}).getByRole('button',{name:'Цены',exact:true}).count(),0);
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).has('product'),false);
    drillProducts = true;
    await page.getByRole('link',{name:'Рынок',exact:true}).click();
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).waitFor();
    assert.equal(await page.locator('.sm-market-page th').allTextContents().then(values=>values.includes('Регион')),false);
    assert.equal(await page.locator('.ip-crumbs').innerText().then(text=>text.includes('__empty__')),false);
    assert.equal(await page.getByRole('checkbox',{name:'Выбрать все товары выборки',exact:true}).count(),0);
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).click();
    await page.getByRole('tab',{name:'Цены по регионам',exact:true}).waitFor();
    assert.equal(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('suc'),'prices');
    await page.getByRole('button',{name:'К рынку',exact:true}).click();
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).waitFor();
    await capture('current-market-products');
    manyImports = true;
    await page.reload();
    await page.getByRole('link',{name:'Данные',exact:true}).click();
    await page.getByRole('tab',{name:'Проверка данных',exact:true}).click();
    const importsPanel = page.locator('.ip-panel').filter({has:page.getByRole('heading',{name:'Последние загрузки файлов',exact:true})});
    await importsPanel.locator('li').first().waitFor();
    assert.equal(await importsPanel.locator('li').count(),1);

    manyCards = true;
    await page.getByRole('link',{name:'Цены',exact:true}).click();
    await page.getByRole('button',{name:'Тестовый ящик',exact:true}).click();
    await page.getByRole('tab',{name:'Наша линейка · 61',exact:true}).click();
    await page.locator('select[aria-label="Строк на странице"]:visible').selectOption('25');
    assert.equal(await page.locator('.sm-own-card:visible').count(),25);
    await page.getByRole('button',{name:'Вперёд',exact:true}).click();
    await page.getByRole('button',{name:'Товар 25',exact:true}).waitFor();
    await page.getByRole('button',{name:'Цвет: все',exact:true}).click();
    await page.getByRole('checkbox',{name:'красный',exact:true}).check();
    await page.getByRole('button',{name:'Готово',exact:true}).click();
    assert.equal(await page.locator('.sm-own-card:visible').count(),25);
    await page.getByText('Показаны 1–25 из 30',{exact:true}).waitFor();
    await capture('current-own-cards');
    await page.getByRole('tab',{name:'Рынок категории · 61',exact:true}).click();
    await page.locator('select[aria-label="Строк на странице"]:visible').selectOption('25');
    assert.equal(await page.locator('.sm-competitor-card:visible').count(),25);
    await page.getByRole('button',{name:'Цвет: все',exact:true}).click();
    await page.getByRole('checkbox',{name:'синий',exact:true}).check();
    await page.getByRole('button',{name:'Готово',exact:true}).click();
    await page.getByText('Показаны 1–25 из 31',{exact:true}).waitFor();
    await capture('current-market-cards');
    await page.locator('.sm-competitor-card:visible .sm-color-swatch').first().hover();
    await page.getByRole('tooltip').filter({hasText:'синий'}).waitFor();

    // Regional table links, shared empty state and card alignment are visible behavior.
    await page.locator('.sm-competitor-card:visible summary').first().click();
    const regional = page.locator('.sm-competitor-card:visible').first();
    await regional.getByRole('cell',{name:'Москва',exact:true}).waitFor();
    assert.equal(await regional.getByRole('link',{name:'На сайте конкурента',exact:true}).last().getAttribute('href'),'https://example.test/moscow');
    await capture('current-regional-card');
    await page.getByRole('tab',{name:/^Наша линейка/}).click();
    assert.equal(await page.getByRole('button',{name:'Открыть товар',exact:true}).count(),0);
    const ownAlignment = await page.evaluate(() => {
      const card=document.querySelector('.sm-own-card');
      const copy=card.cloneNode(true);
      copy.querySelector('.sm-own-product-name').textContent='Длинное название товара '.repeat(15);
      card.after(copy);
      const points=[card,copy].map(el=>el.querySelector('.price').getBoundingClientRect().top);
      copy.remove(); return Math.abs(points[0]-points[1]);
    });
    assert.ok(ownAlignment < 2);
    await page.getByRole('tab',{name:'Цены по регионам',exact:true}).click();
    await page.getByRole('button',{name:'Настройки параметров расчета',exact:true}).click();
    const history=page.getByRole('heading',{name:'История изменений параметров',exact:true});
    await history.scrollIntoViewIfNeeded();
    await page.getByRole('dialog').getByText('Система',{exact:true}).waitFor();
    await page.getByRole('dialog').getByText('Код 1С: H-ONE · Москва, Казань',{exact:true}).waitFor();
    assert.equal(await page.getByRole('dialog').getByText('Исторический товар',{exact:true}).count(),0);
    const targets = page.getByRole('dialog').locator('.sm-history-targets');
    await targets.locator('summary').click();
    await targets.getByText('Код 1С: H-0 · Москва',{exact:true}).waitFor();
    await targets.getByRole('button',{name:'2',exact:true}).click();
    await targets.getByText('Код 1С: H-25 · Москва',{exact:true}).waitFor();
    assert.equal(await targets.locator('li').count(),1);
    const originalViewport = page.viewportSize();
    await page.setViewportSize({width:390,height:844});
    await targets.scrollIntoViewIfNeeded();
    assert.ok(await targets.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
    assert.ok(await targets.locator('.ip-pager').evaluate(el => el.scrollWidth <= el.clientWidth + 1));
    await targets.locator('summary').click();
    assert.equal(await targets.getAttribute('open'),null);
    await page.setViewportSize(originalViewport);
    await capture('current-parameter-history');
    await page.getByRole('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
    emptyCards=true;
    await page.reload();
    await page.getByRole('tab',{name:/^Рынок категории/}).click();
    await page.locator('.sm-product-page .ip-empty:visible').getByText('Данных конкурентов нет',{exact:true}).waitFor();
    assert.equal(await page.locator('.sm-product-page .ip-filters:visible').count(),0);
    assert.equal(await page.getByText('Нет товаров для выбранных фильтров',{exact:true}).count(),0);
    await page.getByRole('tab',{name:/^Наша линейка/}).click();
    await page.getByText('Других товаров этой классификации нет',{exact:true}).waitFor();
    assert.equal(await page.locator('.sm-product-page .ip-filters:visible').count(),0);
    await page.getByRole('tab',{name:/^Конкуренты/}).click();
    await page.locator('.sm-product-page .ip-empty:visible').getByText('Данных конкурентов нет',{exact:true}).waitFor();
    assert.equal(await page.getByText('Нет товаров для выбранных фильтров',{exact:true}).count(),0);
        assert.deepEqual(errors, []);
    console.log('Select Market iPrice React: price edit, parameter preview/apply, market, activation and viewer rights passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
