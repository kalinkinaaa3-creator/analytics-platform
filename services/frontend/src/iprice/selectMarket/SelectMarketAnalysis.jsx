import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { priceText, errorText } from "./format";
import { Corridor } from "./Corridor";
import { SelectMarketFilters } from "./SelectMarketFilters";

const root = "/v1/select-market/iprice/snapshots/";
const zones = { below_market: "Ниже рынка", in_market: "В рынке", above_market: "Выше рынка", critical_above: "Критически выше рынка", no_market_data: "Нет данных рынка" };
export function MarketAnalysis({ snapshotId, versions, canEdit }) {
  const [comparison, setComparison] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [path, setPath] = useState({});
  const [refresh, setRefresh] = useState(0);
  const [hierarchy, setHierarchy] = useState("1c");
  const [filters, setFilters] = useState({});
  const filtersKey = JSON.stringify(filters);
  const marketView = !comparison || comparison === "groups";
  const grouped = comparison === "groups";
  const pathKey = JSON.stringify(path);
  const queryKey = `${snapshotId}-${comparison}-${page}-${pathKey}-${refresh}-${hierarchy}-${filtersKey}`;
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/analysis/`, { params: { page, filters: filtersKey, comparison_id: grouped ? undefined : comparison || undefined,
      ...(grouped ? { view: "groups", hierarchy, drill_level: (hierarchy === "1c" ? ["root", "group_1", "group_2", "group_3", "group_4"] : ["root", "category", "subcategory", "subcategory_type"])[Object.keys(JSON.parse(pathKey)).length], ...JSON.parse(pathKey) } : {}) }, signal: controller.signal })
      .then(response => { setData({ ...response.data, queryKey }); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить сравнение."); });
    return () => controller.abort();
  }, [snapshotId, comparison, page, queryKey, grouped, pathKey, hierarchy, marketView, filtersKey]);
  const ready = data?.queryKey === queryKey;
  const pages = data?.total_pages ?? data?.pagination?.pages ?? 1;
  return <section><h3>Рынок и изменения цен</h3>
    <SelectMarketFilters snapshotId={snapshotId} comparisonId={marketView ? undefined : comparison} search="" filters={filters} onChange={value => { setFilters(value); setPath({}); setPage(1); }} />
    {!marketView && <p>Фильтры используют данные выбранной версии расчёта. Для удалённых строк используются данные сравниваемой старой версии.</p>}
    {grouped && <label>Группировка<select aria-label="Группировка" value={hierarchy} onChange={event => { setHierarchy(event.target.value); setPath({}); setPage(1); }}><option value="1c">Группы 1С</option><option value="classification">Классификация iPrice</option></select></label>}
    <label>Сравнение<select value={comparison} onChange={e => { setComparison(e.target.value); setPath({}); setPage(1); }}><option value="">С ценами конкурентов</option><option value="groups">По группам товаров</option>{versions.filter(version => version.status === "success" && String(version.id) !== String(snapshotId)).map(version => <option key={version.id} value={version.id}>С версией №{version.version_number} за {version.calculation_date}</option>)}</select></label>
    {canEdit && <ZoneEditor onSaved={() => setRefresh(value => value + 1)} />}
    {error && <p role="alert">{error}</p>}
    {!ready && !error && <p role="status">Загружаем сравнение…</p>}
    {ready && <>
      {(!comparison || grouped) && <p>Зона рынка определяется по текущей цене из загруженного прайса. Нижний порог: {priceText(data.price_zones.below_market_percent)}%, верхний: {priceText(data.price_zones.above_market_percent)}%, критический: {priceText(data.price_zones.critical_percent)}%. Итоговая РРЦ показана отдельно.</p>}
      {grouped ? <><button onClick={() => { setPath({}); setPage(1); }}>Все группы</button><p>{Object.values(path).join(" → ")}</p><div className="sm-iprice-table"><table><thead><tr>{["Группа / товар", "Количество товаров", "Текущая цена (медиана)", "Итоговая РРЦ (медиана)", "Рынок (медиана)"].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{data.results.map(item => <tr key={item.key || item.id}><td>{data.next_level ? <button onClick={() => { setPath({ ...path, [data.next_level]: item.key }); setPage(1); }}>{item.label}</button> : item.nom}</td><td>{item.product_count ?? 1}</td><td>{priceText(item.median_retail_price)}</td><td>{priceText(item.median_final_rrp)}</td><td>{priceText(item.median_market_price)}</td></tr>)}</tbody></table></div></> : <div className="sm-iprice-table"><table><thead><tr>{["Код 1С", "Номенклатура", "Регион", comparison ? "Было" : "Текущая цена", "Итоговая РРЦ", comparison ? "Изменение" : "Рынок", ...(comparison ? [] : ["Зона"])].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{data.results.map((item, i) => {
          const row = comparison ? item.comparison || item.base : item;
          const changes = { added: "Добавлена", removed: "Удалена", changed: "Изменена", unchanged: "Без изменений" };
          return <tr key={i}><td>{row.code_1c}</td><td>{row.nom}</td><td>{row.sale_region}</td>
            <td className="sm-number">{priceText(comparison ? item.base?.effective_approved_rrp : row.retail_price)}</td>
            <td className="sm-number">{priceText(comparison ? item.comparison?.effective_approved_rrp : row.final_rrp)}</td>
            <td>{comparison ? changes[item.change_type] || item.change_type : priceText(row.market_price)}</td>
            {!comparison && <td>{zones[row.zone] || row.zone}</td>}</tr>;
        })}</tbody></table></div>}
      {!data.results.length && <p>Строк нет.</p>}
      <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</button> {page} / {pages} <button disabled={page >= pages} onClick={() => setPage(page + 1)}>Далее</button>
    </>}
  </section>;
}

function ZoneEditor({ onSaved }) {
  const [values, setValues] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get('/v1/select-market/iprice/price-zones/', { signal: controller.signal }).then(({ data }) => setValues(data))
      .catch(err => { if (err.code !== "ERR_CANCELED") setMessage("Не удалось загрузить пороги."); });
    return () => controller.abort();
  }, []);
  async function save(event) {
    event.preventDefault(); if (busy) return; setBusy(true); setMessage("");
    try {
      await api.post('/v1/select-market/iprice/price-zones/', values);
      setMessage("Пороги сохранены."); onSaved();
    } catch { setMessage("Проверьте пороги: нижний ≤ 0, верхний ≥ 0, критический больше верхнего."); }
    finally { setBusy(false); }
  }
  return <details><summary>Настроить зоны рынка</summary><p>Доли: 0,03 = 3%. Пороги меняют оценку рынка, цены не пересчитываются.</p>{values && <form onSubmit={save}>{[["below_market_threshold", "Нижний порог"], ["above_market_threshold", "Верхний порог"], ["critical_threshold", "Критический порог"]].map(([key, label]) => <label key={key}>{label}<input type="number" step="0.000001" required disabled={busy} value={values[key]} onChange={event => setValues({ ...values, [key]: event.target.value })} /></label>)}<button disabled={busy}>Сохранить пороги</button></form>}{message && <p role="status">{message}</p>}</details>;
}

export function ProductDetails({ snapshotId, productId, region, canEdit, onSaved }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/`, { signal: controller.signal }).then(r => setData(r.data))
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить карточку."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  return <section>{error && <p role="alert">{error}</p>}{data ? <>
    <h3>{data.nom} · {data.code}</h3><p>Метод для региона: {Number(region.regional_competitor_rrp_median) > 0 ? "По аналогам" : "Эксклюзив — от закупочной стоимости"}.</p>
    <h4>{region.sale_region}</h4>
    <Corridor region={{ ...region, effective_approved_rrp: region.effective.rrp }} />
    <p>Учитывать транспортные расходы: {region.include_transport ? "Да" : "Нет"}. Все затраты ниже указаны без НДС.</p>
    <dl>{[["product_cost", "Закупочная цена"], ["quantity_eurotruck", "Количество в еврофуре (справочно)"], ["logistics_unit", "Учтённая доставка на единицу"], ["cost_with_logistics", "Закупка с доставкой"], ["base_analog", "Коэффициент аналога"], ["base_exclusive", "Маржа эксклюзива (доля)"], ["minimum_margin", "Минимальная маржа (доля)"], ["preliminary_rrp", "Предварительная РРЦ"], ["minimum_price", "Минимальная цена"], ["calculated_rrp", "Расчётная РРЦ"]].map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{priceText(region[key])}</dd></div>)}</dl>
    <p>Прайс за {region.nomenclature_price_date || "—"}, себестоимость за {region.product_cost_month || "—"}.</p>
    <h4>Итоговые цены, руб.</h4><table><thead><tr><th>Тип цены</th><th>Без НДС</th><th>С НДС 22%</th></tr></thead><tbody>{[["rrp", "Розница"], ["small", "Мелкий опт"], ["medium", "Средний опт"], ["large", "Крупный опт"]].map(([key, title]) => <tr key={key}><td>{title}</td><td>{priceText(region.effective[key])}</td><td>{priceText(region.effective_gross?.[key])}</td></tr>)}</tbody></table>
    <h3>Конкуренты в расчёте</h3>{!data.competitors.length && <p>Данных конкурентов нет.</p>}
    {data.competitors.map(item => <p key={item.id}>{item.source} · {priceText(item.competitor_final_price_max)} руб. без НДС · дата: {item.competitor_price_date || "—"} · регионы: {item.applicable_regions.join(", ") || "—"} {/^https?:\/\//i.test(item.url || "") && <a href={item.url} target="_blank" rel="noopener noreferrer">Посмотреть</a>}</p>)}
    <CompetitorEditor snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} />
  </> : !error && <p role="status">Загружаем карточку…</p>}</section>;
}

function CompetitorEditor({ snapshotId, productId, canEdit, onSaved }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/competitors/`, { params: { page }, signal: controller.signal }).then(r => { setData(r.data); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить состав аналогов."); });
    return () => controller.abort();
  }, [snapshotId, productId, page]);
  async function change(id, mode) {
    if (busy || !reason.trim()) return;
    if (!window.confirm("Изменить состав аналогов и пересчитать товар? Ручные цены этого товара потребуется подтвердить заново.")) return;
    setBusy(true); setError("");
    try {
      await api.post(`${root}${snapshotId}/products/${productId}/competitors/`, { competitor_product_keys: [id], selection_mode: mode, reason, expected_revision: data.edit_revision });
      onSaved();
    } catch (err) { setError(errorText(err, "Не удалось изменить состав аналогов.")); }
    finally { setBusy(false); }
  }
  const names = { auto: "Авто", include: "Включён вручную", exclude: "Исключён" };
  return <details><summary>Состав аналогов и история</summary>
    <p>Доступны активные позиции конкурентов с той же классификацией. Изменение пересчитывает товар и требует повторного подтверждения ручных цен.</p>
    {error && <p role="alert">{error}</p>}
    {data && <>
      {canEdit && data.editable && <label>Причина изменения аналогов<input value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></label>}
      {data.items.map(item => <p key={item.id}>{item.source} · {/^https?:\/\//i.test(item.url || "") ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a> : item.url} · {names[item.mode]}
        {canEdit && data.editable && <select aria-label={`Участие аналога ${item.id}`} value={item.mode} disabled={busy || !reason.trim() || data.page !== page} onChange={e => change(item.id, e.target.value)}>{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</p>)}
      <button disabled={page <= 1 || busy} onClick={() => setPage(page - 1)}>Назад</button> {page} / {data.pages} <button disabled={page >= data.pages || busy} onClick={() => setPage(page + 1)}>Далее</button>
      <h4>Последние 50 изменений</h4>{data.changes.map(item => <p key={item.id}>Аналог {item.override__product_key_competitor} · {names[item.selection_mode]} · {item.changed_by__username} · {new Date(item.date_add).toLocaleString("ru-RU")} · {item.reason}</p>)}
    </>}
  </details>;
}
