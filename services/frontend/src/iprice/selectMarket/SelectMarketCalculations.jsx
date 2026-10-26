import { ProductImage } from "./ProductImage";
import { Pager } from "./ui/Pager";
import { fmtMoney, fmtPct, fmtDate, fmtDateTime, countText } from "./archiveFormat";
import { useLocation, useNavigate } from "react-router-dom";
import { Term } from "./ui/Term";
import { SelectMarketCompare } from "./SelectMarketCompare";
import { issues } from "./issueLabels";
import { useCallback, useEffect, useRef, useState } from "react";
import { useConfirm } from "./ui/useConfirm";
import { createPortal } from "react-dom";
import { Button, Drawer, PageHead, Panel } from "./ui/primitives";
import { SelectMarketOverview } from "./SelectMarketOverview";
import { api } from "../../api/client";
import { ParameterEditor, PriceEditor, SnapshotHistory } from "./SelectMarketEdits";
import { MarketAnalysis, ProductDetails } from "./SelectMarketAnalysis";
import { SelectMarketFilters } from "./SelectMarketFilters";
import { errorText } from "./format";
import { ZonePicker } from "./ZonePicker";
import Icon from "./ui/Icon";
import { ZoneTag } from "./ZoneTag";

const root = "/v1/select-market/iprice/snapshots/";
const status = { building: "Расчёт выполняется", success: "Рассчитано", failed: "Ошибка расчёта", warning: "Предупреждение", error: "Ошибка строки" };
const money = value => fmtMoney(value);
function versionLabel(version, latestId) {
  if (version.status === "building") return "Считается…";
  if (version.status === "failed") return "Ошибка расчёта";
  if (version.is_active) return "Действует";
  if (version.was_active) return "Действовал";
  return version.id === latestId ? "Ждёт проверки" : "Архив";
}


function CalculationStatus({ row }) {
  const states = { success: ["green", "Готово", "check"], warning: ["amber", "Есть замечание", null], error: ["red", "Нет цены", "alert"] };
  const [tone, baseLabel, icon] = states[row.calculation_status] || ["gray", status[row.calculation_status] || row.calculation_status, null];
  const label = row.calculation_status === "error" && row.effective_approved_rrp_median != null ? "Не во всех регионах" : baseLabel;
  const reasons = [...new Set([...(row.error_codes || []), ...(row.warning_codes || [])])].map(code => issues[code] || code).join("; ");
  return <span className={`ip-tag ${tone}`} title={reasons || label} tabIndex={reasons ? 0 : undefined} aria-label={reasons ? `${label}: ${reasons}` : label}>{icon ? <Icon name={icon} size={12} /> : <span className="dot" />}{label}</span>;
}

function CalculationRows({ id, canEdit, canEditParameters, onSaved, initialScope = {}, onScopeChange }) {
  const [mode, setMode] = useState(initialScope.mode || "products");
  const [ordering, setOrdering] = useState(initialScope.ordering || "nom");
  const [zone, setZone] = useState(initialScope.zone || "");
  const [problemsOnly, setProblemsOnly] = useState(initialScope.problemsOnly || false);
  const [page, setPage] = useState(initialScope.page || 1);
  const [pageSize, setPageSize] = useState(() => { try { const stored = Number(initialScope.pageSize || sessionStorage.getItem("select-market-iprice-page-size")); return [25, 50, 100].includes(stored) ? stored : 50; } catch { return 50; } });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState(initialScope.search || "");
  const [query, setQuery] = useState(initialScope.search || "");
  const [filters, setFilters] = useState(initialScope.filters || {});
  const serializedFilters = JSON.stringify(filters);
  useEffect(() => {
    onScopeChange?.({ snapshotId: id, mode, zone, ordering, problemsOnly, page, pageSize, search: query, filters: JSON.parse(serializedFilters) });
  }, [id, mode, zone, ordering, problemsOnly, page, pageSize, query, serializedFilters, onScopeChange]);
  const [editing, setEditing] = useState(null);
  const [loadedProduct, storeProduct] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const address = new URLSearchParams(location.hash.slice(1));
  const productAddress = address.get("product") || "";
  const rowAddress = address.get("row") || "";
  const product = loadedProduct?.address === `${id}:${productAddress}:${rowAddress}` ? loadedProduct.row : null;
  function setProduct(row) {
    const params = new URLSearchParams(location.hash.slice(1));
    params.set("snapshot", String(id));
    if (row) { params.set("product", String(row.product_id)); if (row.id != null) params.set("row", String(row.id)); else params.delete("row"); }
    else { params.delete("product"); params.delete("row"); }
    navigate({ pathname: location.pathname, search: location.search, hash: `#${params}` }, { state: location.state });
  }
  useEffect(() => {
    if (!/^[1-9][0-9]*$/.test(productAddress)) return;
    const controller = new AbortController();
    api.get(`${root}${id}/rows/`, { params: { product_id: productAddress }, signal: controller.signal }).then(({ data }) => {
      const row = rowAddress ? data.rows.find(item => String(item.id) === rowAddress) : data.rows[0];
      if (row) { storeProduct({ address: `${id}:${productAddress}:${rowAddress}`, row }); setError(""); }
      else setError("Товар или региональная строка отсутствуют в выбранном расчёте.");
    }).catch(err => { if (err.code !== "ERR_CANCELED") setError(errorText(err)); });
    return () => controller.abort();
  }, [id, productAddress, rowAddress]);
  const [retry, setRetry] = useState(0);
  function openProduct(productId) { setProduct({ product_id: productId }); }
  useEffect(() => {
    if (search === query) return;
    const timer = setTimeout(() => { setQuery(search); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [search, query]);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${id}/rows/`, { params: { page, page_size: pageSize, search: query, filters: serializedFilters, mode, zone, ordering, problems_only: problemsOnly }, signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.page !== page) setPage(data.page);
      setResult({ ...data, query, filters: serializedFilters, mode, zone, problemsOnly, ordering, pageSize }); setError("");
    }).catch(err => { if (err.code !== "ERR_CANCELED") setError(errorText(err, "Не удалось загрузить строки расчёта.")); });
    return () => controller.abort();
  }, [id, page, query, serializedFilters, retry, mode, zone, problemsOnly, ordering, pageSize]);
  const loading = !result || result.pageSize !== pageSize || result.page !== page || result.query !== query || result.filters !== serializedFilters || result.mode !== mode || result.zone !== zone || result.problemsOnly !== problemsOnly || result.ordering !== ordering;
  const rowNavigation = row => ({
    className: "is-clickable", tabIndex: 0,
    onClick: event => { if (!event.target.closest("button, a, input, label, select")) setProduct(row); },
    onKeyDown: event => { if (event.key === "Enter" && event.target === event.currentTarget) setProduct(row); },
  });
  const heading = (key, label) => <th className={["market", "current", "final", "deviation", "margin"].includes(key) ? "num" : undefined} aria-sort={ordering.replace("-", "") === key ? ordering.startsWith("-") ? "descending" : "ascending" : "none"}><span className="th-in"><button className="sort" onClick={() => { setOrdering(ordering === key ? "-" + key : key); setPage(1); }}>{label} {ordering === key ? "↑" : ordering === "-" + key ? "↓" : "↕"}</button>{({deviation: "Отклонение новой итоговой цены от медианы цен конкурентов.", margin: "Доля новой цены, остающаяся после закупки и включённой доставки.", market: "Медиана пригодных цен конкурентов.", current: "Текущая цена из загруженного прайса без НДС.", final: "Итоговая цена с учётом ручного согласования. Для товара — медиана по регионам."})[key] && <Term icon title={label} text={({deviation: "Отклонение новой итоговой цены от медианы цен конкурентов.", margin: "Доля новой цены, остающаяся после закупки и включённой доставки.", market: "Медиана пригодных цен конкурентов.", current: "Текущая цена из загруженного прайса без НДС.", final: "Итоговая цена с учётом ручного согласования. Для товара — медиана по регионам."})[key]} />}</span></th>;
  if (product) return <div className="ip-stack">
    {error && <p role="alert">{error}</p>}<ProductDetails key={`details-${product.id}`} snapshotId={id} productId={product.product_id} onBack={() => setProduct(null)} region={product} canEdit={canEditParameters} canEditPrice={canEdit} onSaved={onSaved} onOpenProduct={openProduct} />
  </div>;
  return <div className="ip-panel sm-price-panel" aria-busy={loading}>
    {canEditParameters && document.getElementById("sm-list-parameters") && createPortal(<ParameterEditor snapshotId={id} onSaved={onSaved} listScope={{ filters, search: query, mode, zone, problems_only: problemsOnly }} />, document.getElementById("sm-list-parameters"))}
    <div className="ip-stack" style={{ padding: 16, gap: 12 }}><div className="ip-row between"><div className="ip-row"><div className="ip-seg" role="group" aria-label="Представление цен">{[["products", "Товары"], ["regions", "По регионам"]].map(([key, label]) => <button key={key} aria-pressed={mode === key} onClick={() => { setMode(key); setOrdering("nom"); setPage(1); setEditing(null); }}>{label}</button>)}</div><div className="ip-affix" style={{ width: 320, maxWidth: "100%" }}><span className="pre"><Icon name="search" size={16} /></span><input className="ip-input" type="search" aria-label="Найти товар" placeholder="Код 1С или название" value={search} onChange={e => setSearch(e.target.value)} maxLength={200} /></div></div><div className="ip-seg" role="group" aria-label="Фильтр по статусу">{[[false, "Все"], [true, "Только с проблемами"]].map(([value, label]) => <button key={label} aria-pressed={problemsOnly === value} onClick={() => { setProblemsOnly(value); setPage(1); setEditing(null); }}>{label}</button>)}</div></div>
      <ZonePicker value={zone} onChange={value => { setZone(value); setPage(1); setEditing(null); }} />
      <SelectMarketFilters snapshotId={id} search={query} mode={mode} zone={zone} problemsOnly={problemsOnly} filters={filters} onChange={value => { setFilters(value); setPage(1); setEditing(null); setProduct(null); }} />
    </div>
    {error && <p role="alert">{error} <button onClick={() => { setError(""); setRetry(value => value + 1); }}>Повторить загрузку строк</button></p>}
    {loading ? !error && <p role="status" className="sm-iprice-loading">Загружаем строки…</p> : <>
      <p className="small muted">{result.count} {mode === "products" ? "товаров" : "региональных строк"} · цены без НДС, если не указано иное · НДС 22%</p>
      {mode === "products" ? <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Фото</th>{heading("nom", "Товар")}{heading("market", "У конкурентов")}{heading("current", "Сейчас")}{heading("final", "Новая цена")}{heading("deviation", "К рынку")}{heading("status", "Статус")}</tr></thead><tbody>{result.rows.map(item => {
        const first = item.regions[0];
        const sum = item.summary;
        const current = Number(sum.current_retail_median), next = Number(sum.effective_approved_rrp_median), market = Number(sum.competitor_rrp_median);
        const delta = market > 0 && sum.effective_approved_rrp_median != null ? (next / market - 1) * 100 : null;
        return <tr key={item.product_id} {...rowNavigation(first)}><td><ProductImage src={first.snapshot_product__image} name={first.snapshot_product__nom} /></td><td><button className="ip-linkbtn sm-product-name" onClick={() => setProduct(first)}>{first.snapshot_product__nom}</button><span className="sub">{first.snapshot_product__code_1c} · {sum.pricing_method === "analog" ? "по рынку" : "эксклюзив"}</span></td><td className="num">{money(sum.competitor_rrp_median)}<span className="sub">{countText(sum.competitor_count, "конкурент", "конкурента", "конкурентов")}</span></td><td className="num">{money(sum.current_retail_median)}</td><td className="num"><span className="ip-newprice"><b>{money(sum.effective_approved_rrp_median)}</b><span className="chg">{current > 0 && sum.effective_approved_rrp_median != null ? `${next >= current ? "↑" : "↓"} ${fmtPct(Math.abs(next / current - 1))}` : "—"}</span></span></td><td><ZoneTag zone={sum.zone} percent={delta} /></td><td><CalculationStatus row={sum} /></td></tr>;
      })}</tbody></table></div> : <>
      <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Фото</th>{heading("nom", "Товар")}{heading("sale_region", "Регион продажи")}{heading("market", "У конкурентов")}{heading("final", "Новая цена")}{heading("margin", "Маржа")}{heading("deviation", "К рынку")}<th><span className="sr-only">Действия</span></th></tr></thead>
        <tbody>{result.rows.map(row => {
          const market = Number(row.regional_competitor_rrp_median);
          const current = Number(row.current_retail);
          const next = Number(row.effective.rrp);
          const delta = market > 0 && row.effective.rrp != null ? (next / market - 1) * 100 : null;
          return <tr key={`row-${row.id}`} {...rowNavigation(row)}><td><ProductImage src={row.snapshot_product__image} name={row.snapshot_product__nom} /></td><td><button className="ip-linkbtn sm-product-name" onClick={() => setProduct(row)}>{row.snapshot_product__nom}</button><span className="sub">{row.snapshot_product__code_1c}</span></td>
          <td><b>{row.sale_region}</b><span className="sub"><CalculationStatus row={row} /></span></td>
          <td className="num">{money(row.regional_competitor_rrp_median)}</td>
          <td className="num"><span className="ip-newprice"><b>{money(row.effective.rrp)}</b><span className="chg">{current > 0 && row.effective.rrp != null ? `${next >= current ? "↑" : "↓"} ${fmtPct(Math.abs(next / current - 1))}` : "—"}</span></span><span className="sub">Сейчас {money(row.current_retail)}</span><span className="sub">{money(row.effective_gross?.rrp)} с НДС</span>{row.effective.approval_source === "manual" && <span className="ip-tag orange">Ручная цена</span>}</td>
          <td className="num">{next > 0 && row.cost_with_logistics != null ? fmtPct((next - Number(row.cost_with_logistics)) / next, { digits: 0 }) : "—"}</td>
          <td><ZoneTag zone={row.zone} percent={delta} /></td>
          <td>{canEdit && row.calculation_status !== "error" ? <Button size="s" icon="edit" aria-label="Своя цена" onClick={() => setEditing(row)} /> : <Button variant="ghost" size="s" icon="eye" aria-label="Расчёт цены" onClick={() => setProduct(row)} />}</td></tr>;
        })}</tbody></table></div></>}
      {!result.count && <p className="sm-iprice-empty">Региональные строки отсутствуют.</p>}
      <Pager page={page} totalPages={result.pages} count={result.count} pageSize={pageSize} onPage={value => { setEditing(null); setProduct(null); setPage(value); }} onPageSize={value => { setPageSize(value); setPage(1); try { sessionStorage.setItem("select-market-iprice-page-size", String(value)); } catch { /* Optional browser preference. */ } }} />
      <Drawer open={!!editing && canEdit} onClose={() => setEditing(null)} title={editing ? `Цена: ${editing.sale_region}` : "Своя цена"} sub={editing?.snapshot_product__nom || ""}>{editing && <PriceEditor key={editing.id} snapshotId={id} row={editing} onSaved={onSaved} />}</Drawer>
    </>}
  </div>;
}

function readPriceScope() {
    try {
      const value = JSON.parse(new URLSearchParams(window.location.hash.slice(1)).get("price_scope") || "{}");
      if (!value || typeof value !== "object" || Array.isArray(value)) return {};
      return {
        snapshotId: typeof value.snapshotId === "string" ? value.snapshotId : "",
        mode: value.mode === "regions" ? "regions" : "products",
        page: Number.isInteger(value.page) && value.page > 0 ? value.page : 1,
        pageSize: [25, 50, 100].includes(value.pageSize) ? value.pageSize : 50,
        ordering: typeof value.ordering === "string" && /^-?(nom|market|current|final|status|sale_region|deviation|margin)$/.test(value.ordering) ? value.ordering : "nom",
        problemsOnly: value.problemsOnly === true,
        zone: typeof value.zone === "string" ? value.zone.split(",").filter(item => ["below_market", "in_market", "above_market", "critical_above", "no_market_data"].includes(item)).join(",") : "",
        search: typeof value.search === "string" ? value.search.slice(0, 200) : "",
        filters: value.filters && typeof value.filters === "object" && !Array.isArray(value.filters)
          ? Object.fromEntries(Object.entries(value.filters).filter(([, items]) => Array.isArray(items) && items.every(item => typeof item === "string"))) : {},
      };
    } catch { return {}; }
}

export function SelectMarketCalculations({ navigationRevision = 0, canEdit, view = "prices", onNavigate, onHelp, sourceState }) {
  const navigate = useNavigate();
  const [priceScope, setPriceScope] = useState(readPriceScope);
  const [restoration, setRestoration] = useState(0);
  const lastNavigation = useRef(navigationRevision);
  useEffect(() => {
    if (lastNavigation.current === navigationRevision) return;
    lastNavigation.current = navigationRevision;
    setPriceScope({});
    setRestoration(value => value + 1);
  }, [navigationRevision]);
  useEffect(() => {
    function restore() { setPriceScope(readPriceScope()); setRestoration(value => value + 1); }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  const rememberScope = useCallback(scope => {
    setPriceScope(scope);
    const params = new URLSearchParams(window.location.hash.slice(1));
    const encoded = JSON.stringify(scope);
    if (params.get("price_scope") === encoded) return;
    params.set("price_scope", encoded);
    navigate({ pathname: window.location.pathname, search: window.location.search, hash: `#${params}` }, { replace: true, state: window.history.state?.usr });
  }, [navigate]);
  const [confirm, confirmation] = useConfirm();
  const [versions, setVersions] = useState(null);
  const [compareFrom, setCompareFrom] = useState("");
  const [compareTo, setCompareTo] = useState("");

  const initialZone = "";
  const [revision, setRevision] = useState(0);
  const [reviewedRevision, setReviewedRevision] = useState(0);
  const location = useLocation();
  const rawComparison = new URLSearchParams(location.hash.slice(1)).get("compare_from") || "";
  const initialComparison = /^[1-9][0-9]*$/.test(rawComparison) ? rawComparison : "";
  function setInitialComparison(value) {
    const params = new URLSearchParams(window.location.hash.slice(1));
    params.set("compare_from", value);
    navigate({ pathname: window.location.pathname, search: window.location.search, hash: `#${params}` }, { replace: true, state: window.history.state?.usr });
  }
  const requestedSnapshot = new URLSearchParams(location.hash.slice(1)).get("snapshot") || "";
  const initialSnapshot = /^[1-9][0-9]*$/.test(requestedSnapshot) ? requestedSnapshot : "";
  const selected = initialSnapshot;
  const setSelected = useCallback(value => {
    loadedSnapshot.current = value;
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (value) params.set("snapshot", value); else params.delete("snapshot");
    params.delete("product"); params.delete("row");
    navigate({ pathname: window.location.pathname, search: window.location.search, hash: `#${params}` }, { replace: true, state: window.history.state?.usr });
  }, [navigate]);
  const selectedRef = useRef(initialSnapshot);
  const loadedSnapshot = useRef("");
  useEffect(() => {
    selectedRef.current = initialSnapshot;
  }, [initialSnapshot]);
  const [error, setError] = useState("");
  const [versionsError, setVersionsError] = useState("");
  const [day, setDay] = useState(() => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()));
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [activating, setActivating] = useState(false);
  const activationPending = useRef(false);
  const downloading = useRef(false);
  const [message, setMessage] = useState("");
  const submitting = useRef(false);
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const { data } = await api.get(root, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setVersions(data); setVersionsError("");
          if (selectedRef.current && loadedSnapshot.current !== selectedRef.current) {
            const linkedVersion = data.find(version => String(version.id) === selectedRef.current);
            if (linkedVersion) {
              loadedSnapshot.current = selectedRef.current;
              setReviewedRevision(linkedVersion.edit_revision || 0);
            }
          }
          if (!selectedRef.current) {
            const initial = data.find(v => v.is_active) || data.find(v => v.status === "success");
            if (initial) { selectedRef.current = String(initial.id); setSelected(String(initial.id)); setReviewedRevision(initial.edit_revision || 0); }
          }
        }
      } catch (err) {
        if (err.code !== "ERR_CANCELED") setVersionsError("Не удалось загрузить версии расчётов. Повторяем автоматически.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { alive.current = false; controller.abort(); clearTimeout(timer); };
  }, [setSelected]);
  async function start(event) {
    event.preventDefault();
    if (submitting.current) return;
    if (!await confirm(`Посчитать цены на ${day}? Будет создана новая версия; утверждённые цены не изменятся.`)) return;
    submitting.current = true; setStarting(true); setError(""); setMessage("");
    try {
      const { data } = await api.post("/v1/select-market/iprice/calculations/start/", { calculation_date: day });
      if (alive.current) { setMessage(`Расчёт №${data.id} зарегистрирован. Статус обновится автоматически.`); selectedRef.current = ""; setSelected(""); }
    } catch (err) {
      if (alive.current) setError(errorText(err, "Не удалось запустить расчёт."));
    } finally {
      submitting.current = false;
      if (alive.current) setStarting(false);
    }
  }
  const building = versions?.some(version => version.status === "building");
  const selectedVersion = versions?.find(version => String(version.id) === selected);
  const historicalRoutes = !!selectedVersion?.historical_routes;
  const stale = !!selectedVersion && (selectedVersion.edit_revision || 0) !== reviewedRevision;
  const editable = canEdit && !building && !historicalRoutes && !stale && selectedVersion?.status === "success"
    && selectedVersion.is_current && !selectedVersion.was_active && !selectedVersion.is_active;
  const editableParameters = editable && versions.find(version => version.status === "success")?.id === selectedVersion.id;
  function changed() {
    if (!alive.current || selectedRef.current !== selected) return;
    setRevision(value => value + 1);
    setReviewedRevision(reviewedRevision + 1);
    setVersions(current => current.map(version => String(version.id) === selected
      ? { ...version, edit_revision: Math.max(version.edit_revision || 0, reviewedRevision + 1) } : version));
  }
  async function activate() {
    if (!selectedVersion || stale || activationPending.current) return;
    activationPending.current = true; setActivating(true); setError(""); setMessage("");
    try {
      const { data } = await api.get(`${root}${selectedVersion.id}/analysis/`, { params: { view: "groups", hierarchy: "1c", drill_level: "root" } });
      if (!alive.current || selectedRef.current !== selected) return;
      const summary = data.summary;
      if (!summary) throw new Error("Не удалось получить сводку расчёта для утверждения.");
      const risky = summary.zones?.find(zone => zone.key === "critical_above")?.count;
      if (!await confirm(<div className="ip-stack"><p>Утвердить версию №{selectedVersion.version_number} за {fmtDate(selectedVersion.calculation_date)} внутри системы? Она заменит активную версию. Отправки в 1С не будет.</p><ul className="ip-checklist"><li className={risky > 0 ? "bad" : "ok"}><Icon name={risky > 0 ? "alert" : "check"} /><b>{risky ?? "—"}</b> товаров критически выше рынка</li><li className={summary.calculation_errors > 0 ? "bad" : "ok"}><Icon name={summary.calculation_errors > 0 ? "alert" : "check"} /><b>{summary.calculation_errors ?? "—"}</b> товаров без цены</li></ul></div>)) return;
      if (!alive.current || selectedRef.current !== selected) return;
      await api.post(`${root}${selectedVersion.id}/activate/`, { expected_revision: reviewedRevision });
      if (alive.current) {
        setVersions(current => current.map(version => ({ ...version, is_active: version.id === selectedVersion.id, was_active: version.was_active || version.id === selectedVersion.id })));
        setRevision(value => value + 1);
        setMessage(`Версия №${selectedVersion.version_number} утверждена внутри системы.`);
      }
    } catch (err) {
      if (alive.current) setError(errorText(err, "Не удалось утвердить версию."));
    } finally {
      activationPending.current = false;
      if (alive.current) setActivating(false);
    }
  }
  async function download(target = selectedVersion) {
    if (!target || downloading.current) return;
    downloading.current = true; setExporting(true); setError("");
    try {
      const { data } = await api.get(`${root}${target.id}/export/`, { responseType: "blob" });
      if (!alive.current) return;
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `select_market_iprice_v${target.version_number}_${target.calculation_date}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      if (alive.current) setError("Не удалось подготовить Excel. Проверьте состояние выбранной версии.");
    } finally {
      downloading.current = false;
      if (alive.current) setExporting(false);
    }
  }
  async function deactivate() {
    if (!selectedVersion || activationPending.current) return;
    if (!await confirm(`Снять утверждение версии №${selectedVersion.version_number}? Активной версии не будет до следующего утверждения.`)) return;
    activationPending.current = true; setActivating(true); setError("");
    try {
      await api.delete(`${root}${selectedVersion.id}/activate/`);
      if (alive.current) {
        setVersions(current => current.map(version => version.id === selectedVersion.id ? { ...version, is_active: false } : version));
        setRevision(value => value + 1);
        setMessage("Утверждение снято. История и цены версии сохранены.");
      }
    } catch (err) {
      if (alive.current) setError(errorText(err, "Не удалось снять утверждение."));
    } finally {
      activationPending.current = false;
      if (alive.current) setActivating(false);
    }
  }
  const activationActions = <div className="ip-row">{canEdit && !historicalRoutes && selectedVersion?.status === "success" && selectedVersion.is_current && <Button variant="primary" disabled={activating || building || stale || selectedVersion.is_active} onClick={activate}>{selectedVersion.is_active ? "Версия утверждена" : activating ? "Проверяем и утверждаем…" : "Утвердить внутри системы"}</Button>}{canEdit && selectedVersion?.is_active && <Button variant="danger" disabled={activating} onClick={deactivate}>Снять утверждение</Button>}</div>;
  const parameterAction = editableParameters && view === "prices" && <span id="sm-list-parameters" />;
  const picker = !!versions?.length && <select className="ip-select ip-select-version" aria-label="Последние 50 версий" disabled={activating || starting || exporting || view === "compare"} value={selected} onChange={event => { selectedRef.current = event.target.value; setSelected(event.target.value); setError(""); setMessage(""); setReviewedRevision(versions.find(version => String(version.id) === event.target.value)?.edit_revision || 0); }}><option value="">Выберите версию</option>{versions.map(version => <option key={version.id} value={version.id}>Расчёт №{version.version_number} · {fmtDate(version.calculation_date)} · {versionLabel(version, versions.find(item => item.status === "success")?.id)}</option>)}</select>;
  const slot = document.getElementById("sm-iprice-version-slot");
  return <div className="sm-calculation-pages ip-stack" hidden={view === "data"}>
    {confirmation}
    {slot && view !== "data" && view !== "versions" && createPortal(picker, slot)}
    {view !== "compare" && <PageHead title={{ home: "Главная", prices: "Цены", market: "Рынок", versions: "Расчёты", compare: "Изменения между расчётами" }[view]} text={{ home: "Следующий шаг, товары для проверки и состояние данных.", prices: "Проверьте цены товаров по регионам. Откройте товар, чтобы увидеть расчёт и аналоги.", market: "Разница наших цен с ценами конкурентов по группам товаров и регионам.", versions: "Сохранённые расчёты, утверждение и история изменений. Цены автоматически в 1С не передаются." }[view]} onHelp={onHelp} actions={<>{parameterAction}{selectedVersion?.status === "success" && view !== "home" && <Button icon="download" disabled={exporting} onClick={() => download()}>{exporting ? "Готовим документ…" : "Скачать Excel"}</Button>}</>} />}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}{versionsError && <p role="alert">{versionsError}</p>}
    {versions && selected && !selectedVersion && <p role="alert">Версия из ссылки отсутствует среди доступных последних 50 расчётов. Выберите версию из списка.</p>}
    {!versions && !versionsError && <p role="status" className="sm-iprice-loading">Загружаем версии…</p>}
    {view === "home" && versions && <SelectMarketOverview key={`overview-${selected}-${revision}`} snapshot={selectedVersion} activeSnapshot={versions.find(v => v.is_active)} onCompare={() => { const active = versions.find(v => v.is_active); if (active) { setInitialComparison(String(active.id)); onNavigate("compare"); } }} sourceState={sourceState} onNavigate={onNavigate} onHelp={onHelp} onZone={zone => { setPriceScope({ zone, snapshotId: selected }); onNavigate("prices"); }} />}
    {view === "versions" && <>
      <div className="ip-grid k2"><Panel title="Новый расчёт" sub="iPrice возьмёт загруженные данные и последние цены конкурентов. Утверждённая версия не изменится.">
        <form className="sm-iprice-toolbar sm-panel-body" onSubmit={start}><label>Дата расчёта<input type="date" value={day} required disabled={starting || building || !canEdit} onChange={event => setDay(event.target.value)} /></label>
        {canEdit ? <Button variant="primary" icon="play" type="submit" disabled={!versions || starting || building}>{starting ? "Запускаем…" : building ? "Расчёт выполняется" : "Посчитать цены"}</Button> : <span className="small muted">Расчёт запускают сотрудники с правом редактирования.</span>}</form>
      </Panel><Panel title="Изменения между расчётами" sub="Товары с новой ценой, новые и выбывшие товары."><div className="ip-stack sm-panel-body"><div className="ip-grid k2">
        <label className="ip-field">Старый<select className="ip-select" aria-label="Старый расчёт" value={compareFrom} onChange={e => setCompareFrom(e.target.value)}><option value="">Выберите расчёт</option>{versions?.filter(v => v.status === "success").map(v => <option key={v.id} value={v.id}>{fmtDate(v.calculation_date)} · №{v.version_number}</option>)}</select></label>
        <label className="ip-field">Новый<select className="ip-select" aria-label="Новый расчёт" value={compareTo} onChange={e => setCompareTo(e.target.value)}><option value="">Выберите расчёт</option>{versions?.filter(v => v.status === "success").map(v => <option key={v.id} value={v.id}>{fmtDate(v.calculation_date)} · №{v.version_number}</option>)}</select></label>
        </div><div className="ip-row" style={{ justifyContent: "flex-end" }}><Button icon="compare" disabled={!compareFrom || !compareTo || compareFrom === compareTo} onClick={() => { selectedRef.current = compareTo; setSelected(compareTo); setReviewedRevision(versions.find(v => String(v.id) === compareTo)?.edit_revision || 0); setInitialComparison(compareFrom); onNavigate("compare"); }}>Показать изменения</Button></div></div></Panel></div>
      <Panel title="Все расчёты" sub="Утверждение действует внутри системы. Автоматической отправки цен в 1С нет."><div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Расчёт</th><th>Состояние</th><th>Запуск</th><th className="num">Товаров</th><th className="num">Цен по регионам</th><th className="num">Без цены</th><th /></tr></thead><tbody>{versions?.map(version => <tr key={`version-${version.id}`} className={String(version.id) === selected ? "selected" : ""}><td>{fmtDate(version.calculation_date)}<span className="sub">№{version.version_number}{!version.is_current && " · есть новее за эту дату"}</span></td><td><span className={`ip-tag ${version.is_active ? "orange" : version.status === "failed" ? "red" : "gray"}`}>{versionLabel(version, versions.find(item => item.status === "success")?.id)}</span>{version.error && <span className="sub">{version.error}</span>}</td><td>{version.created_by__username || "—"}<span className="sub">{version.created_at ? fmtDateTime(version.created_at) : "—"}</span></td><td className="num">{version.products_count ?? "—"}</td><td className="num">{version.regions_count ?? "—"}</td><td className="num">{version.errors_count ?? "—"}</td><td><div className="ip-row"><Button size="s" onClick={() => { selectedRef.current = String(version.id); setSelected(String(version.id)); setReviewedRevision(version.edit_revision || 0); }}>{String(version.id) === selected ? "Выбран" : "Открыть"}</Button>{version.status === "success" && <Button size="s" variant="ghost" icon="download" aria-label="Скачать цены версии" disabled={exporting} onClick={() => download(version)} />}{String(version.id) === selected && activationActions}{version.status === "success" && <Button variant="ghost" size="s" icon="table" onClick={() => { selectedRef.current = String(version.id); setSelected(String(version.id)); setReviewedRevision(version.edit_revision || 0); onNavigate("prices"); }}>Цены</Button>}</div></td></tr>)}</tbody></table></div></Panel>
      {versions?.length === 0 && <div className="ip-empty"><b>Расчётов пока нет</b><span>Загрузите данные и посчитайте цены.</span></div>}
    </>}
    {stale && <p role="alert">Расчёт изменён другим пользователем. Обновите и проверьте данные перед утверждением. <button onClick={() => { setReviewedRevision(selectedVersion.edit_revision || 0); setRevision(value => value + 1); }}>Обновить расчёт</button></p>}
    {historicalRoutes && <p role="status">Историческая версия с маршрутами: доступны просмотр и выгрузка. Для изменения цен создайте новый расчёт.</p>}

    {selected && view === "prices" && selectedVersion?.status === "success" && <CalculationRows key={`rows-${selected}-${selectedVersion.status}-${revision}-${restoration}`} id={selected} initialScope={priceScope.snapshotId === selected ? priceScope : {}} onScopeChange={rememberScope} canEdit={editable} canEditParameters={editableParameters} onSaved={changed} />}
    {selected && view === "compare" && <SelectMarketCompare key={`compare-${selected}-${initialComparison}-${restoration}`} snapshotId={selected} baseId={initialComparison} exportAction={selectedVersion?.status === "success" ? <Button icon="download" disabled={exporting} onClick={() => download()}>{exporting ? "Готовим документ…" : "Скачать Excel"}</Button> : null} onBack={() => onNavigate("versions")} />}
    {selected && view === "market" && selectedVersion?.status === "success" && <MarketAnalysis key={`market-${selected}-${revision}-${restoration}`} snapshotId={selected} canEdit={editableParameters} canEditPrice={editable} onSaved={changed} initialZone={initialZone} onOpenList={scope => { setPriceScope({ ...scope, snapshotId: selected }); onNavigate("prices"); }} />}
    {selected && view === "versions" && <SnapshotHistory key={`history-${selected}-${revision}`} snapshotId={selected} />}
  </div>;
}
