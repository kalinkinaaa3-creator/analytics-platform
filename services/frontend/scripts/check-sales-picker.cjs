/* Local browser regression check; all backend responses are fixtures. */
const assert = require("node:assert/strict");
const { chromium } = require(process.env.SPS_PLAYWRIGHT_PACKAGE || "playwright");
const base = process.env.SPS_UI_URL || "http://127.0.0.1:5179";

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.SPS_BROWSER ? { executablePath: process.env.SPS_BROWSER } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const config = { region: "Тестовый склад", vat: 22, thresholds: [50000, 300000, 800000], warning_threshold: 2200000,
      characteristics: [], logistics: [], warehouses: [], simple_columns: ["name"], full_columns: ["name"] };
    const products = [
      [1, "Ящик красный", "Ящик", "Склад", "Красный", "ПП"],
      [2, "Ящик синий", "Ящик", "Склад", "Синий", "ПЭ"],
      [3, "Бак красный", "Бак", "Сад", "Красный", "ПЭ"],
      [4, "Канистра зелёная", "Канистра", "Сад", "Зелёный", "ПП"],
    ].map(([code, name, nom_view, nom_category, color, material]) => ({ product_key: String(code), code, name,
      name_1c: name, price_list: name, nom_view, nom_category, color, material, characteristics: {}, logistics: {}, stocks: {} }));
    await page.route("**/v1/sales-calculator/**", async route => {
      const path = new URL(route.request().url()).pathname;
      let data;
      if (path.endsWith("/settings/")) data = { config, characteristics: {}, logistics: {}, warehouses: [], simple_columns: { name: "Наименование" }, full_columns: { name: "Наименование" } };
      else if (path.endsWith("/products/")) data = { products, region: config.region, regions: [config.region], state: {}, can_refresh: false };
      else if (path.endsWith("/refresh/")) data = {};
      else if (path.endsWith("/calculate/")) data = { rows: [], quantity: 0, logistics: { weight: 0, pallets: 0 } };
      else throw new Error(`Unexpected API ${path}`);
      await route.fulfill({ json: data });
    });
    await page.route(`${base}/sales-picker-check`, route => route.fulfill({ contentType: "text/html", body: `<!doctype html><html><body><div id="root"></div><script type="module">
      import React from '/node_modules/.vite/deps/react.js';
      import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const {SalesCalculatorDashboard} = await import('/src/dashboards/salesCalculator/SalesCalculatorDashboard.jsx');
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(SalesCalculatorDashboard));
      </script></body></html>` }));
    await page.goto(`${base}/sales-picker-check`);
    const dialog = page.getByRole("dialog", { name: "Выбор товаров", exact: true });
    const filter = name => dialog.locator(".dashboard-filter").filter({ has: page.getByText(name, { exact: true }) });
    async function openFilter(name) {
      const root = filter(name);
      await root.locator(".dashboard-multiselect__control").click();
      return root;
    }
    async function options(name) {
      const root = await openFilter(name);
      const values = await root.locator(".dashboard-multiselect__options label span").allTextContents();
      await root.locator(".dashboard-multiselect__control").click();
      return values;
    }
    async function found(count) { await dialog.getByText(`Найдено: ${count}`, { exact: true }).waitFor(); }
    for (const mode of ["Прайс", "Калькулятор"]) {
      await page.getByRole("button", { name: mode, exact: true }).click();
      await page.getByRole("button", { name: "＋ Добавить товар", exact: true }).click();
      await found(4);
      await dialog.getByRole("textbox", { name: "Поиск товаров" }).fill("ЯЩИК");
      await found(2);
      assert.deepEqual(await options("Вид"), ["Ящик"]);
      const colors = await openFilter("Цвет");
      await colors.getByRole("checkbox", { name: "Красный", exact: true }).check();
      await found(1); // Applied without first closing the dropdown.
      await colors.locator(".dashboard-multiselect__control").click();
      assert.deepEqual(await options("Материал"), ["ПП"]);
      await dialog.getByRole("textbox", { name: "Поиск товаров" }).fill("");
      await found(2);
      assert.deepEqual((await options("Вид")).sort(), ["Бак", "Ящик"].sort());
      const material = await openFilter("Материал");
      await material.getByRole("checkbox", { name: "ПП", exact: true }).check();
      await found(1);
      await material.locator(".dashboard-multiselect__control").click();
      const ownColors = await openFilter("Цвет");
      await ownColors.getByRole("checkbox", { name: "Зелёный", exact: true }).check();
      await found(2); // OR within a facet, AND between facets.
      await dialog.getByRole("button", { name: "Сбросить фильтры", exact: true }).click();
      await found(4);
      await dialog.getByRole("textbox", { name: "Поиск товаров" }).fill("00000000002");
      await found(1);
      assert.deepEqual(await options("Цвет"), ["Синий"]);
      await dialog.getByRole("button", { name: "Сбросить фильтры", exact: true }).click();
      for (const position of [{ x: 18, y: 18 }, { x: 12, y: 12 }, { x: 24, y: 24 }, { x: 3, y: 3 }]) {
        await openFilter("Цвет");
        const close = dialog.getByRole("button", { name: "Закрыть", exact: true });
        const target = await close.evaluate((button, point) => {
          const rect = button.getBoundingClientRect();
          return document.elementFromPoint(rect.left + point.x, rect.top + point.y) === button;
        }, position);
        assert.equal(target, true);
        await close.click({ position });
        await dialog.waitFor({ state: "detached" });
        await page.getByRole("button", { name: "＋ Добавить товар", exact: true }).click();
      }
      await page.keyboard.press("Escape");
      await dialog.waitFor({ state: "detached" });
    }
    await page.getByRole("button", { name: "Настройки", exact: true }).click();
    const settings = page.getByRole("dialog", { name: "Настройки калькулятора" });
    await settings.getByRole("button", { name: "Закрыть", exact: true }).click({ position: { x: 18, y: 18 } });
    await settings.waitFor({ state: "detached" });
    assert.deepEqual(errors, []);
    console.log("Sales picker: dependent facets/search, multi-selection, reset, precise icon/edge clicks in both tabs and settings passed");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
