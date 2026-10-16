import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { ParameterEditor, PriceEditor, SnapshotHistory } from "./SelectMarketEdits";
import { MarketAnalysis, ProductDetails } from "./SelectMarketAnalysis";
import { SelectMarketFilters } from "./SelectMarketFilters";
import { errorText } from "./format";

const root = "/v1/select-market/iprice/snapshots/";
const status = { building: "Расчёт выполняется", success: "Рассчитано", failed: "Ошибка расчёта", warning: "Предупреждение", error: "Ошибка строки" };
const issues = { MISSING_PRODUCT_COST: "Нет себестоимости за месяц расчёта", MISSING_NOMENCLATURE_PRICE: "Нет позиции в выбранном прайсе", MISSING_TRANSPORT_COST: "Нет стоимости перевозки", MISSING_QUANTITY_EUROTRUCK: "Не указана вместимость еврофуры", MISSING_DEPARTURE_DISCOUNT: "Не заданы скидки", MISSING_CALCULATION_CONFIG: "Нет параметров расчёта" };
Object.assign(issues, { INVALID_PURCHASE_COST: "Не задана корректная закупочная цена", INVALID_LOGISTICS_UNIT: "Не заданы корректные расходы на доставку", MISSING_WEBSITE_PRODUCT: "Товар отсутствует на сайте", MISSING_CLASSIFICATION: "Товар не классифицирован", REAPPROVAL_REQUIRED: "После изменения параметров требуется повторное согласование цены" });
Object.assign(issues, { INVALID_BASE_ANALOG: "Не задан корректный коэффициент аналога", INVALID_BASE_EXCLUSIVE: "Не задана корректная маржа эксклюзива", INVALID_MINIMUM_MARGIN: "Не задана корректная минимальная маржа", INVALID_SMALL: "Не задана корректная скидка мелкого опта", INVALID_MEDIUM: "Не задана корректная скидка среднего опта", INVALID_LARGE: "Не задана корректная скидка крупного опта", NON_POSITIVE_PRICE: "Расчётная цена должна быть больше нуля" });
const money = value => value == null ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

function CalculationRows({ id, canEdit, canEditParameters, onSaved }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({});
  const serializedFilters = JSON.stringify(filters);
  const [editing, setEditing] = useState(null);
  const [product, setProduct] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${id}/rows/`, { params: { page, search: query, filters: serializedFilters }, signal: controller.signal }).then(({ data }) => {
      setResult({ ...data, query, filters: serializedFilters }); setError("");
    }).catch(err => { if (err.code !== "ERR_CANCELED") setError(errorText(err, "Не удалось загрузить строки расчёта.")); });
    return () => controller.abort();
  }, [id, page, query, serializedFilters, retry]);
  const loading = !result || result.page !== page || result.query !== query || result.filters !== serializedFilters;
  return <div aria-busy={loading}>
    <SelectMarketFilters snapshotId={id} search={query} filters={filters} onChange={value => { setFilters(value); setPage(1); setEditing(null); setProduct(null); }} />
    <form onSubmit={event => { event.preventDefault(); setPage(1); setEditing(null); setProduct(null); setQuery(search); }}><label>Поиск по коду или наименованию<input value={search} onChange={event => setSearch(event.target.value)} maxLength={200} /></label><button>Найти</button></form>
    {error && <p role="alert">{error} <button onClick={() => { setError(""); setRetry(value => value + 1); }}>Повторить загрузку строк</button></p>}
    {loading ? !error && <p role="status">Загружаем строки…</p> : <>
      <p>Строк: {result.count}. Суммы в рублях. НДС — 22%. Статус версии «Рассчитано» не исключает ошибок отдельных строк.</p>
      <div className="sm-iprice-table"><table><thead><tr>{["Код 1С", "Номенклатура", "Регион", "Текущая розница без НДС", "Закупка с доставкой без НДС", "Расчётная РРЦ без НДС", "Итоговая РРЦ без НДС", "Итоговая РРЦ с НДС", "Состояние"].map(title => <th key={title}>{title}</th>)}</tr></thead>
        <tbody>{result.rows.map(row => <tr key={row.id}><td>{row.snapshot_product__code_1c}</td><td><button onClick={() => setProduct(row)}>{row.snapshot_product__nom}</button></td><td>{row.sale_region}</td>
          <td className="sm-number">{money(row.current_retail)}</td><td className="sm-number">{money(row.cost_with_logistics)}</td><td className="sm-number">{money(row.calculated_rrp)}</td>
          <td className="sm-number">{money(row.effective.rrp)}{row.effective.approval_source === "manual" && <div>Ручная цена</div>}{canEdit && row.calculation_status !== "error" && <button onClick={() => setEditing(row)}>Своя цена</button>}</td>
          <td className="sm-number">{money(row.effective_gross?.rrp)}</td>
          <td>{status[row.calculation_status] || row.calculation_status}{[...row.error_codes, ...row.warning_codes].map(code => <div key={code}>{issues[code] || code}</div>)}</td></tr>)}</tbody></table></div>
      {!result.count && <p>Региональные строки отсутствуют.</p>}
      <nav aria-label="Страницы расчёта"><button disabled={page === 1} onClick={() => { setEditing(null); setProduct(null); setPage(page - 1); }}>Назад</button> <span>{page} / {result.pages}</span> <button disabled={page >= result.pages} onClick={() => { setEditing(null); setProduct(null); setPage(page + 1); }}>Далее</button></nav>
      {editing && canEdit && <section><h3>{editing.snapshot_product__nom} · {editing.sale_region}</h3><button onClick={() => setEditing(null)}>Закрыть редактор</button><PriceEditor key={editing.id} snapshotId={id} row={editing} onSaved={onSaved} /></section>}
      {product && <section><button onClick={() => setProduct(null)}>Закрыть карточку</button><ProductDetails key={product.id} snapshotId={id} productId={product.product_id} region={product} canEdit={canEditParameters} onSaved={onSaved} />{canEditParameters && <ParameterEditor key={product.id} snapshotId={id} row={product} onSaved={onSaved} />}</section>}
    </>}
  </div>;
}

export function SelectMarketCalculations({ canEdit, view = "prices" }) {
  const [versions, setVersions] = useState(null);
  const [revision, setRevision] = useState(0);
  const [reviewedRevision, setReviewedRevision] = useState(0);
  const [selected, setSelected] = useState("");
  const selectedRef = useRef("");
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
        if (!controller.signal.aborted) { setVersions(data); setVersionsError(""); }
      } catch (err) {
        if (err.code !== "ERR_CANCELED") setVersionsError("Не удалось загрузить версии расчётов. Повторяем автоматически.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { alive.current = false; controller.abort(); clearTimeout(timer); };
  }, []);
  async function start(event) {
    event.preventDefault();
    if (submitting.current) return;
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
    if (!window.confirm(`Утвердить версию №${selectedVersion.version_number} за ${selectedVersion.calculation_date} внутри системы? Она заменит активную версию. Отправки в 1С не будет.`)) return;
    activationPending.current = true; setActivating(true); setError(""); setMessage("");
    try {
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
  async function download() {
    if (!selectedVersion || downloading.current) return;
    downloading.current = true; setExporting(true); setError("");
    try {
      const { data } = await api.get(`${root}${selectedVersion.id}/export/`, { responseType: "blob" });
      if (!alive.current) return;
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `select_market_iprice_v${selectedVersion.version_number}_${selectedVersion.calculation_date}.xlsx`;
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
    if (!window.confirm(`Снять утверждение версии №${selectedVersion.version_number}? Активной версии не будет до следующего утверждения.`)) return;
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
  return <article className="sm-iprice-card" hidden={view === "data"}><h2>{view === "home" ? "Работа с ценами" : view === "market" ? "Сравнение цен" : "Сохранённые расчёты"}</h2>
    {view === "home" && <p>Загрузите исходные данные, обновите сайт и конкурентов, рассчитайте цены. Проверьте ошибки и итоговые цены, затем утвердите версию и скачайте Excel. Цены автоматически в 1С не передаются.</p>}
    {canEdit && <form onSubmit={start}><label>Дата расчёта<input type="date" value={day} required disabled={starting || building} onChange={event => setDay(event.target.value)} /></label>
      <button type="submit" disabled={!versions || starting || building}>{starting ? "Запускаем…" : building ? "Расчёт выполняется" : "Рассчитать цены"}</button></form>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    {versionsError && <p role="alert">{versionsError}</p>}
    {!versions && !versionsError && <p role="status">Загружаем версии…</p>}
    {versions?.length === 0 && <p>Сохранённых расчётов пока нет.</p>}
    {!!versions?.length && <label>Последние 50 версий<select disabled={activating || starting || exporting} value={selected} onChange={event => { selectedRef.current = event.target.value; setSelected(event.target.value); setError(""); setMessage(""); setReviewedRevision(versions.find(version => String(version.id) === event.target.value)?.edit_revision || 0); }}><option value="">Выберите версию</option>{versions.map(version => <option key={version.id} value={version.id}>№{version.version_number} · {version.calculation_date} · {status[version.status] || version.status}{version.is_active ? " · Активная" : ""}</option>)}</select></label>}
    {stale && <p role="alert">Расчёт изменён другим пользователем. Обновите и проверьте данные перед утверждением. <button onClick={() => { setReviewedRevision(selectedVersion.edit_revision || 0); setRevision(value => value + 1); }}>Обновить расчёт</button></p>}
    {selectedVersion?.status === "success" && <div><button disabled={exporting} onClick={download}>{exporting ? "Готовим документ…" : "Скачать Excel"}</button><p>Выгрузка выбранного расчёта включает ошибки строк. Скачивание не утверждает версию и не отправляет цены в 1С.</p></div>}
    {historicalRoutes && <p role="status">Историческая версия с маршрутами: доступны просмотр и выгрузка. Для изменения цен создайте новый расчёт.</p>}
    {canEdit && !historicalRoutes && selectedVersion?.status === "success" && selectedVersion.is_current && <button disabled={activating || building || stale || selectedVersion.is_active} onClick={activate}>{selectedVersion.is_active ? "Версия утверждена" : activating ? "Проверяем и утверждаем…" : "Утвердить внутри системы"}</button>}
    {canEdit && selectedVersion?.is_active && <button disabled={activating} onClick={deactivate}>Снять утверждение</button>}
    {editableParameters && <ParameterEditor key={`${selected}-${revision}`} snapshotId={selected} onSaved={changed} />}
    {selected && view !== "market" && view !== "versions" && selectedVersion?.status === "success" && <CalculationRows key={`${selected}-${selectedVersion?.status}-${revision}`} id={selected} canEdit={editable} canEditParameters={editableParameters} onSaved={changed} />}
    {selected && view === "market" && selectedVersion?.status === "success" && <MarketAnalysis key={`${selected}-${revision}`} snapshotId={selected} versions={versions} canEdit={canEdit} />}
    {selected && view === "versions" && <SnapshotHistory key={`${selected}-${revision}`} snapshotId={selected} />}
  </article>;
}
