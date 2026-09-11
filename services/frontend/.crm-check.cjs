const { chromium } = require(process.env.TEMP + '/crm-preferences-browser/node_modules/playwright-core');
const assert = require('node:assert/strict');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let saved, saveRelease, reloadRelease, dealRequests = 0, failSave = false;
    let saveGate = new Promise(resolve => { saveRelease = resolve; });
    let reloadGate = new Promise(resolve => { reloadRelease = resolve; });
    let rows = [
      { manager_id: 1, manager_name: 'Alpha', crm_department_name: 'Sales', display_name: 'Sales', selected: true },
      { manager_id: 2, manager_name: 'Beta', crm_department_name: 'Sales', display_name: 'Sales', selected: false },
      { manager_id: 3, manager_name: 'Gamma', crm_department_name: 'Support', display_name: 'Support', selected: true },
    ];
    await page.route('**/api/v1/bitrix24/**', async route => {
      const path = new URL(route.request().url()).pathname;
      const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' };
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      let body = {};
      if (path.endsWith('department-preferences/')) {
        if (route.request().method() === 'POST') {
          if (failSave) return route.fulfill({ status: 500, headers, json: { detail: 'Save failed for test' } });
          saved = route.request().postDataJSON().rows;
          await saveGate;
          rows = saved;
        }
        body = { options: rows };
      } else if (path.includes('/deals/')) {
        dealRequests++;
        if (saved) await reloadGate;
        body = path.endsWith('/filters/') ? { departments: [], managers: [], categories: [], stages: [], sources: [], results: [] } : { cards: { total: saved ? 2 : 99 }, rows: [], summary: {}, snapshot: 'test' };
      } else if (path.endsWith('/filters/')) {
        body = { departments: [], managers: [], sources: [], projects: [], statuses: [], semantic_statuses: [] };
      } else {
        body = { cards: { total: 3 }, dynamics: {}, summaries: {} };
      }
      await route.fulfill({ headers, json: body });
    });
    await page.goto('http://127.0.0.1:5193/.crm-check.html?section=deals');
    await page.waitForFunction(() => ![...document.querySelectorAll('.global-spinner-overlay')].some(el => el.getClientRects().length));
    await page.getByRole('button', { name: 'Отслеживать подразделения' }).click();
    const dialog = page.getByRole('dialog', { name: '' }).filter({ has: page.getByText('Отслеживаемые менеджеры', { exact: true }) });
    await dialog.waitFor();
    assert.match(await dialog.locator('footer').innerText(), /Выбрано: 2 из 3/);
    await dialog.getByText('Alpha', { exact: true }).click();
    assert.equal(await dialog.getByRole('checkbox', { name: 'Alpha', exact: true }).isChecked(), true);
    await dialog.getByText('Менеджер', { exact: true }).click();
    assert.equal(await dialog.getByRole('checkbox', { name: 'Beta', exact: true }).isChecked(), false);
    await dialog.getByRole('checkbox', { name: 'Alpha', exact: true }).uncheck();
    assert.match(await dialog.locator('footer').innerText(), /Выбрано: 1 из 3/);
    await dialog.getByRole('button', { name: 'Показать выбранных', exact: true }).click();
    assert.equal(await dialog.locator('.crm-preference-row').count(), 1);
    await dialog.getByRole('button', { name: 'Показать всех', exact: true }).click();
    await dialog.locator('.crm-preference-head > div').nth(1).locator('.crm-multiselect__control').click();
    await dialog.locator('.crm-multiselect__options').getByRole('checkbox').first().check();
    await dialog.getByText('Отслеживаемые менеджеры', { exact: true }).click();
    assert.equal(await dialog.locator('.crm-preference-row').count(), 2);
    await dialog.getByRole('checkbox', { name: 'Выбрать всех отображаемых менеджеров', exact: true }).check();
    assert.match(await dialog.locator('footer').innerText(), /Выбрано: 3 из 3/);
    await dialog.getByRole('checkbox', { name: 'Выбрать всех отображаемых менеджеров', exact: true }).uncheck();
    assert.match(await dialog.locator('footer').innerText(), /Выбрано: 1 из 3/);
    const beforeSave = dealRequests;
    await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await page.locator('body > .global-spinner-overlay').waitFor({ state: 'visible' });
    await page.waitForTimeout(100);
    assert.equal(saved.find(row => row.manager_id === 3).selected, true);
    saveRelease();
    await dialog.waitFor({ state: 'hidden' });
    console.log('AFTER SAVE', await page.locator('body').innerText(), 'REQUESTS', dealRequests, beforeSave);
    await page.waitForFunction(() => [...document.querySelectorAll('.global-spinner-overlay')].some(el => el.getClientRects().length));
    assert.ok(dealRequests > beforeSave);
    reloadRelease();
    await page.waitForFunction(() => ![...document.querySelectorAll('.global-spinner-overlay')].some(el => el.getClientRects().length));
    assert.ok(dealRequests >= beforeSave + 6);
    await page.getByRole('button', { name: 'Отслеживать подразделения' }).click();
    failSave = true;
    await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await dialog.getByRole('alert').waitFor();
    assert.equal(await dialog.getByRole('alert').innerText(), 'Save failed for test');
    assert.equal(await dialog.locator('.crm-preference-row').count(), 3);
    assert.deepEqual(errors, []);
    console.log('PASS: count, checkbox-only clicks, selected-only view, filtered bulk selection, save spinner, deal reload, save-error recovery; no browser errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
