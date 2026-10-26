import { ProductImage } from "./ProductImage";
import { fmtPct, fmtMoney, fmtDate, countText } from "./archiveFormat";
import { Pager } from "./ui/Pager";
import { useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button, Panel, PageHead } from "./ui/primitives";
import { SelectMarketFilters } from "./SelectMarketFilters";
import Icon from "./ui/Icon";
import { ProductDetails } from "./SelectMarketAnalysis";
import { errorText } from "./format";

const types = [["all", "Все товары"], ["changed", "С изменениями"], ["final_rrp_increased", "Цена выросла"], ["final_rrp_decreased", "Цена снизилась"], ["price_increased", "Цена в прайсе выросла"], ["price_decreased", "Цена в прайсе снизилась"], ["added", "Новые товары"], ["removed", "Выбывшие товары"], ["new_error", "Потеряли цену"], ["resolved_error", "Получили цену"], ["status_changed", "Сменили статус"]];
function readScope(snapshotId, baseId) {
  try {
    const value = JSON.parse(new URLSearchParams(window.location.hash.slice(1)).get("compare_scope") || "{}");
    if (!value || String(value.snapshotId) !== String(snapshotId) || String(value.baseId) !== String(baseId)) return {};
    return {
      mode: value.mode === "regions" ? "regions" : "products",
      type: types.some(([key]) => key === value.type) ? value.type : "changed",
      search: typeof value.search === "string" ? value.search.slice(0, 200) : "",
      page: Number.isInteger(value.page) && value.page > 0 ? value.page : 1,
      filters: value.filters && typeof value.filters === "object" && !Array.isArray(value.filters) ? Object.fromEntries(Object.entries(value.filters).filter(([, items]) => Array.isArray(items) && items.every(item => typeof item === "string"))) : {},
    };
  } catch { return {}; }
}

export function SelectMarketCompare({ snapshotId, baseId, onBack, exportAction }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [initial] = useState(() => readScope(snapshotId, baseId));
  const [mode, setMode] = useState(initial.mode || "products");
  const [type, setType] = useState(initial.type || "changed");
  const [search, setSearch] = useState(initial.search || "");
  const [filters, setFilters] = useState(initial.filters || {});
  const [page, setPage] = useState(initial.page || 1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loadedProduct, setProduct] = useState(null);
  const address = new URLSearchParams(location.hash.slice(1));
  const productId = address.get("compare_product") || "";
  const productSnapshot = address.get("compare_snapshot") || "";
  const productRegion = address.get("compare_region") || "";
  const productKey = JSON.stringify([snapshotId, baseId, productSnapshot, productId, productRegion]);
  const product = loadedProduct?.key === productKey ? loadedProduct : null;
  function openProduct(id, productId, region = "") {
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (productId) { params.set("compare_product", String(productId)); params.set("compare_snapshot", String(id)); }
    else { params.delete("compare_product"); params.delete("compare_snapshot"); }
    if (productId && region) params.set("compare_region", region); else params.delete("compare_region");
    navigate({ pathname: location.pathname, search: location.search, hash: `#${params}` }, { state: location.state });
  }
  useEffect(() => {
    if (!/^[1-9][0-9]*$/.test(productId) || ![String(snapshotId), String(baseId)].includes(productSnapshot)) return;
    const controller = new AbortController();
    api.get(`/v1/select-market/iprice/snapshots/${productSnapshot}/rows/`, { params: { product_id: productId }, signal: controller.signal }).then(({ data }) => {
      const row = productRegion ? data.rows.find(item => item.sale_region === productRegion) : data.rows[0];
      if (row) { setProduct({ key: productKey, snapshotId: productSnapshot, row }); setError(""); }
      else setError("Товар или регион отсутствуют в выбранной версии расчёта.");
    }).catch(e => { if (e.code !== "ERR_CANCELED") setError(errorText(e)); });
    return () => controller.abort();
  }, [snapshotId, baseId, productId, productSnapshot, productRegion, productKey]);
  const key = JSON.stringify({ mode, type, search, filters, page, snapshotId, baseId });
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (params.get("compare_scope") === key) return;
    params.set("compare_scope", key);
    navigate({ pathname: window.location.pathname, search: window.location.search, hash: `#${params}` }, { replace: true, state: window.history.state?.usr });
  }, [key, navigate]);
  useEffect(() => {
    if (!baseId || String(baseId) === String(snapshotId)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => api.get(`/v1/select-market/iprice/snapshots/${snapshotId}/analysis/`, {
      params: { comparison_id: baseId, mode, change_type: type, search, filters: JSON.stringify(filters), page }, signal: controller.signal,
    }).then(r => { setData({ ...r.data, key }); setError(""); }).catch(e => { if (e.code !== "ERR_CANCELED") setError(errorText(e)); }), 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, snapshotId, baseId, mode, type, search, filters, page]);
  async function open(item) {
    const value = item.comparison || item.base;
    const id = item.comparison ? snapshotId : baseId;
    const productId = mode === "products" ? value.id : value.snapshot_product_id;
    if (!productId) { setError("В строке сравнения отсутствует идентификатор товара."); return; }
    openProduct(id, productId, mode === "regions" ? value.sale_region : "");
  }
  if (!baseId || String(baseId) === String(snapshotId)) return <Button onClick={onBack}>Выберите два разных расчёта для сравнения</Button>;
  if (product) return <><div className="ip-crumbs"><Button variant="ghost" icon="chevLeft" onClick={() => openProduct(null, null)}>К сравнению</Button></div><ProductDetails key={`${product.snapshotId}-${product.row.id}`} snapshotId={product.snapshotId} productId={product.row.product_id} region={product.row} canEdit={false} canEditPrice={false} onOpenProduct={id => openProduct(product.snapshotId, id)} /></>;
  const ready = data?.key === key;
  const finalField = mode === "products" ? "effective_approved_rrp_median" : "effective_approved_rrp";
  const currentField = mode === "products" ? "current_retail_median" : "current_retail";
  const summary = ready ? data.summary : null;
  const versionName = (value, id) => value?.calculation_date ? `расчёт от ${fmtDate(value.calculation_date)} · №${value.version_number ?? id}` : `версия ${id}`;
  const title = summary?.final_rrp_increased != null && summary?.final_rrp_decreased != null
    ? `Изменения: ${countText(summary.final_rrp_increased, "цена выросла", "цены выросли", "цен выросли")}, ${countText(summary.final_rrp_decreased, "снизилась", "снизились", "снизились")}` : "Изменения между расчётами";
  return <><nav className="ip-crumbs"><Button variant="ghost" icon="chevLeft" onClick={onBack}>К расчётам</Button><Icon name="chev" size={12} /><span>Изменения</span></nav>
    <PageHead title={title} text={`Было: ${versionName(ready && data.base_snapshot, baseId)}. Стало: ${versionName(ready && data.comparison_snapshot, snapshotId)}. При изменении старая цена зачёркнута, новая стоит рядом.`} actions={<>{exportAction}<div className="ip-seg" role="group" aria-label="Уровень сравнения">{[["products", "Товары"], ["regions", "Товары по регионам"]].map(([value, label]) => <button key={value} aria-pressed={mode === value} onClick={() => { setMode(value); setFilters({}); setPage(1); }}>{label}</button>)}</div></>} />
    <Panel><div className="ip-stack sm-panel-body">
      <div className="ip-filters">{types.map(([value, label]) => <button className={`ip-chip ${type === value ? "on" : ""}`} key={value} aria-pressed={type === value} onClick={() => { setType(value); setPage(1); }}>{label}{data?.summary && <span className="small quiet">{data.summary[({ all: "total", new_error: "new_errors", resolved_error: "resolved_errors" })[value] || value] ?? "—"}</span>}</button>)}</div>
      <div className="ip-affix" style={{ width: 300, maxWidth: "100%" }}><span className="pre"><Icon name="search" size={16} /></span><input className="ip-input" type="search" aria-label="Найти товар в сравнении" placeholder="Код 1С или название" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} /></div>
      <SelectMarketFilters snapshotId={snapshotId} comparisonId={baseId} mode={mode} search={search} filters={filters} onChange={value => { setFilters(value); setPage(1); }} />
    </div>
    {error && <p role="alert">{error}</p>}{!ready && !error && <p className="sm-iprice-loading">Загружаем сравнение…</p>}
    {ready && <><div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Фото</th><th>Товар</th><th>Изменение</th><th className="num">Цена: было → стало</th><th className="num">Цена в прайсе</th><th>Статус</th><th>Поменялось</th><th className="num">У конкурентов</th></tr></thead><tbody>{data.results.map(item => {
      const row = item.comparison || item.base;
      return <tr key={item.key}><td><ProductImage src={row.image} name={row.nom} /></td><td><button className="ip-linkbtn sm-product-name" onClick={() => open(item)}>{row.nom}</button><span className="sub">{row.code_1c} {row.sale_region}</span></td><td>{({ added: "Новый", removed: "Выбывший", changed: "Изменён", unchanged: "Без изменений" })[item.change_type]}</td><td className="num"><PriceChange before={item.base?.[finalField]} after={item.comparison?.[finalField]} /></td><td className="num"><PriceChange before={item.base?.[currentField]} after={item.comparison?.[currentField]} /></td><td>{item.base?.calculation_status !== item.comparison?.calculation_status ? <>{statusLabel(item.base?.calculation_status)} → <b>{statusLabel(item.comparison?.calculation_status)}</b></> : statusLabel(row.calculation_status)}</td><td><div className="ip-row">{(item.changed_fields || []).slice(0, 4).map(field => <span className="ip-tag gray" key={field}>{fieldLabels[field] || "Другие параметры"}</span>)}{item.has_new_error && <span className="ip-tag red">потерял цену</span>}{item.has_resolved_error && <span className="ip-tag green">получил цену</span>}</div></td><td className="num">{fmtMoney(row[mode === "products" ? "competitor_rrp_median" : "regional_competitor_rrp_median"])}</td></tr>;
    })}</tbody></table></div>{!data.results.length && <p className="ip-empty">Изменений такого типа нет.</p>}<Pager page={data.page || page} totalPages={data.total_pages} count={data.filtered_count} pageSize={50} onPage={setPage} /></>}
  </Panel></>;
}

const statusLabel = value => ({ success: "Готово", warning: "Есть замечание", error: "Нет цены" })[value] || "—";
function PriceChange({ before, after }) {
  const changed = before != null && after != null && Number(before) !== Number(after);
  return <><span className="ip-row">{changed ? <del className="muted">{fmtMoney(before)}</del> : <span>{fmtMoney(before)}</span>}<span>→</span>{changed || (before == null && after != null) ? <b>{fmtMoney(after)}</b> : <span>{fmtMoney(after)}</span>}</span>{changed && Number(before) > 0 && <span className="sub">{fmtPct(Number(after) / Number(before) - 1, { sign: true })}</span>}</>;
}

const fieldLabels = {
  code_1c: "Код 1С", nom: "Название", nom_hier_code: "Код иерархии", nom_hier: "Иерархия",
  nom_view: "Вид", nom_category: "Категория 1С", nom_group: "Группа 1С", sale_region: "Регион",
  product_cost_month: "Месяц закупочной цены", nomenclature_price_date: "Дата прайса",
  quantity_eurotruck: "Количество в еврофуре", include_transport: "Учёт доставки",
  entered_logistics_unit: "Введённая доставка", assortment_matrix_status: "САМ",
  competitor_rrp_min: "Минимальная цена конкурентов", competitor_rrp_max: "Максимальная цена конкурентов",
  regional_competitor_count: "Число конкурентов в регионе",
  regional_competitor_rrp_min: "Минимальная цена конкурентов в регионе",
  regional_competitor_rrp_max: "Максимальная цена конкурентов в регионе",
  current_retail_min: "Минимальная цена прайса", current_retail_max: "Максимальная цена прайса",
  current_vs_competitor_amount: "Разница с рынком, руб.", current_vs_competitor_percent: "Разница с рынком, %",
  current_vs_approved_amount: "Изменение цены, руб.", current_vs_calculated_percent: "Изменение цены, %",
  preliminary_rrp: "Предварительная цена", minimum_price: "Нижняя граница",
  default_approved_rrp: "Цена без ручной корректировки", margin_current: "Текущая маржа", margin_calculated: "Расчётная маржа",
  base_analog_median: "Коэффициент аналога", base_exclusive_median: "Маржа без конкурентов",
  minimum_margin_median: "Минимальная маржа",
  ...Object.fromEntries(["small", "medium", "large", "distr", "distr_1"].flatMap((key, i) => {
    const label = ["Малый опт", "Средний опт", "Крупный опт", "Дистрибьютор", "Дистрибьютор 1"][i];
    return [[`discount_${key}`, `Скидка: ${label}`], [`discount_${key}_median`, `Скидка: ${label}`], [`effective_${key}_median`, `Новая цена: ${label}`], [`effective_${key}`, `Новая цена: ${label}`], [`current_${key}`, `Прайс: ${label}`], [`calculated_${key}`, `Расчёт: ${label}`]];
  })) ,
  category: "Категория", subcategory: "Подкатегория", subcategory_type: "Тип подкатегории",
  material: "Материал", color: "Цвет", modification: "Модификация", item_type: "Тип позиции",
  group_1: "Группа 1", group_2: "Группа 2", group_3: "Группа 3", group_4: "Группа 4",
  pricing_method: "Способ расчёта",
  calculation_status: "Готовность",
  competitor_count: "Число конкурентов",
  competitor_rrp_median: "Цена у конкурентов",
  regional_competitor_rrp_median: "Цена у конкурентов в регионе",
  current_retail_median: "Цена в прайсе",
  current_retail: "Цена в прайсе",
  effective_approved_rrp_median: "Новая цена",
  effective_approved_rrp: "Новая цена",
  calculated_rrp: "Цена по расчёту",
  cost_with_logistics: "Закупочная цена с доставкой",
  product_cost: "Закупочная цена",
  logistics_unit: "Доставка за штуку",
  base_analog: "Положение к рынку",
  base_exclusive: "Маржа для товаров без конкурентов",
  minimum_margin: "Минимальная маржа",
  error_codes: "Причины без цены",
  warning_codes: "Замечания",
};
