import { Term } from "./ui/Term";
import { ProductImage } from "./ProductImage";
import { fmtNumber, fmtPct, fmtMoney } from "./archiveFormat";
import { Pager } from "./ui/Pager";
import { PriceLadder } from "./PriceLadder";
import { ZoneSettings } from "./PriceZones";
import { ZoneTag } from "./ZoneTag";
import { issues } from "./issueLabels";
import { CompetitorCard, SelectionModal } from "./CompetitorCard";
import { saveCompetitorSelection } from "./competitorSelection";
import { useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { useConfirm } from "./ui/useConfirm";
import { api } from "../../api/client";
import { errorText } from "./format";
import { Corridor } from "./Corridor";
import { Panel, Tabs, Button, Drawer } from "./ui/primitives";
import Icon from "./ui/Icon";
import { ParameterEditor, PriceEditor } from "./SelectMarketEdits";
import { SelectMarketFilters } from "./SelectMarketFilters";
import { ZonePicker } from "./ZonePicker";

const root = "/v1/select-market/iprice/snapshots/";
const zones = { below_market: "Ниже рынка", in_market: "В рынке", above_market: "Выше рынка", critical_above: "Критически выше рынка", no_market_data: "Нет данных рынка" };
function readMarketScope(snapshotId) {
  try {
    const value = JSON.parse(new URLSearchParams(window.location.hash.slice(1)).get("market_scope") || "{}");
    if (!value || String(value.snapshotId) !== String(snapshotId)) return {};
    const hierarchy = value.hierarchy === "classification" ? "classification" : "1c";
    const path = {};
    for (const key of hierarchy === "1c" ? ["group_1", "group_2", "group_3", "group_4"] : ["category", "subcategory", "subcategory_type"]) {
      if (typeof value.path?.[key] !== "string") break;
      path[key] = value.path[key];
    }
    return {
      hierarchy, path, comparison: value.comparison === "" ? "" : "groups",
      page: Number.isInteger(value.page) && value.page > 0 ? value.page : 1,
      ordering: ["-product_count", "median_deviation_percent", "-median_deviation_percent"].includes(value.ordering) ? value.ordering : "-product_count",
      search: typeof value.search === "string" ? value.search.slice(0, 200) : "",
      zone: typeof value.zone === "string" ? value.zone.split(",").filter(key => Object.hasOwn(zones, key)).join(",") : "",
      filters: value.filters && typeof value.filters === "object" && !Array.isArray(value.filters) ? Object.fromEntries(Object.entries(value.filters).filter(([, items]) => Array.isArray(items) && items.every(item => typeof item === "string"))) : {},
    };
  } catch { return {}; }
}

export function MarketAnalysis({ snapshotId, canEdit, canEditPrice, onSaved, initialZone = "", onOpenList }) {
  const navigate = useNavigate();
  const [product, setProduct] = useState(null);
  const [selection, setSelection] = useState({ key: "", codes: [], all: false });
  const productRequest = useRef(null);
  const [openingProduct, setOpeningProduct] = useState(false);
  useEffect(() => () => productRequest.current?.abort(), []);
  async function openProduct(productId) {
    productRequest.current?.abort();
    const controller = new AbortController();
    productRequest.current = controller;
    setOpeningProduct(true);
    setError("");
    try {
      const { data } = await api.get(`${root}${snapshotId}/rows/`, { params: { product_id: productId }, signal: controller.signal });
      if (controller.signal.aborted) return;
      if (data.rows[0]) setProduct(data.rows[0]);
      else setError("Товар отсутствует в выбранном расчёте.");
    } catch (err) { if (!controller.signal.aborted) setError(errorText(err)); }
    finally { if (!controller.signal.aborted) setOpeningProduct(false); }
  }
  const [initial] = useState(() => readMarketScope(snapshotId));
  const [zone, setZone] = useState(initial.zone ?? initialZone);
  const [search, setSearch] = useState(initial.search || "");
  const [query, setQuery] = useState(initial.search || "");
  const [ordering, setOrdering] = useState(initial.ordering || "-product_count");
  const [comparison, setComparison] = useState(initial.comparison ?? "groups");
  const [page, setPage] = useState(initial.page || 1);
  useEffect(() => { if (search === query) return; const timer = setTimeout(() => { setQuery(search); setPage(1); }, 300); return () => clearTimeout(timer); }, [search, query]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [path, setPath] = useState(initial.path || {});
  const [refresh, setRefresh] = useState(0);
  const [hierarchy, setHierarchy] = useState(initial.hierarchy || "1c");
  const [filters, setFilters] = useState(initial.filters || {});
  const filtersKey = JSON.stringify(filters);
  const marketView = !comparison || comparison === "groups";
  const grouped = comparison === "groups";
  const pathKey = JSON.stringify(path);
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const encoded = JSON.stringify({ snapshotId, zone, search: query, ordering, comparison, page, hierarchy, path: JSON.parse(pathKey), filters: JSON.parse(filtersKey) });
    if (params.get("market_scope") === encoded) return;
    params.set("market_scope", encoded);
    navigate({ pathname: window.location.pathname, search: window.location.search, hash: `#${params}` }, { replace: true, state: window.history.state?.usr });
  }, [snapshotId, zone, query, ordering, comparison, page, hierarchy, pathKey, filtersKey, navigate]);
  const queryKey = `${snapshotId}-${comparison}-${page}-${pathKey}-${refresh}-${hierarchy}-${filtersKey}-${zone}-${query}-${ordering}`;
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/analysis/`, { params: { page, search: query, ordering, filters: filtersKey, zone: marketView ? zone : undefined, comparison_id: grouped ? undefined : comparison || undefined,
      ...(grouped ? { view: "groups", hierarchy, drill_level: (hierarchy === "1c" ? ["root", "group_1", "group_2", "group_3", "group_4"] : ["root", "category", "subcategory", "subcategory_type"])[Object.keys(JSON.parse(pathKey)).length], ...JSON.parse(pathKey) } : { view: "region_groups" }) }, signal: controller.signal })
      .then(response => {
        const next = response.data;
        if (grouped && next.next_level && next.results.length === 1 && next.results[0].key === "__empty__") {
          setPath(current => ({ ...current, [next.next_level]: "__empty__" })); setPage(1);
        }
        setData({ ...next, queryKey }); setError("");
      })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить сравнение."); });
    return () => controller.abort();
  }, [snapshotId, comparison, page, queryKey, grouped, pathKey, hierarchy, marketView, filtersKey, zone, query, ordering]);
  const selectionKey = JSON.stringify([snapshotId, comparison, pathKey, hierarchy, filtersKey, zone, query]);
  const selectedCodes = selection.key === selectionKey ? selection.codes : [];
  const allSelected = selection.key === selectionKey && selection.all;
  const allFilters = { ...filters, ...Object.fromEntries(Object.entries(path).map(([key, value]) => [key, [value]])) };
  const ready = data?.queryKey === queryKey;
  const pages = data?.total_pages ?? data?.pagination?.pages ?? 1;
  const sum = ready ? data.summary : null;
  const colors = { below_market: "var(--blue-500)", in_market: "var(--green-600)", above_market: "var(--orange-400)", critical_above: "var(--red-600)", no_market_data: "var(--gray-300)" };
  const bar = (items = []) => <div className="ip-bar">{items.filter(z => z.count > 0).map(z => <span key={z.key} style={{ width: `${z.percent}%`, background: colors[z.key] }} title={`${zones[z.key]}: ${z.count}`} />)}</div>;
  if (product) return <section className="ip-stack"><nav className="ip-crumbs"><Button variant="ghost" icon="chevLeft" onClick={() => setProduct(null)}>К рынку</Button></nav><ProductDetails key={product.id} snapshotId={snapshotId} productId={product.product_id} region={product} canEdit={canEdit} canEditPrice={canEditPrice} onSaved={onSaved} onOpenProduct={openProduct} /></section>;
  return <section className="ip-stack sm-market-page"><h3 className="sr-only">Рынок и изменения цен</h3>
    <Panel><div className="ip-stack sm-panel-body">
      <div className="ip-row between"><div className="ip-seg" role="group" aria-label="Разрез"><button aria-pressed={grouped} onClick={() => { setComparison("groups"); setPath({}); setPage(1); }}>По группам товаров</button><button aria-pressed={comparison === ""} onClick={() => { setComparison(""); setPath({}); setPage(1); }}>По регионам</button></div>
        </div>
      <div className="ip-affix" style={{ width: 300, maxWidth: "100%" }}><span className="pre"><Icon name="search" size={16} /></span><input className="ip-input" type="search" aria-label="Найти товар на рынке" placeholder="Код 1С или название" value={search} onChange={e => setSearch(e.target.value)} /></div>
      {marketView && <ZonePicker value={zone} onChange={value => { setZone(value); setPage(1); }} />}
      <SelectMarketFilters snapshotId={snapshotId} mode={grouped ? "products" : "regions"} zone={marketView ? zone : ""} comparisonId={marketView ? undefined : comparison} search={query} filters={filters} onChange={value => { setFilters(value); setPath({}); setPage(1); }} />
      <div className="ip-row sm-market-controls">{grouped && <label>Группировка<select className="ip-select" aria-label="Группировка" value={hierarchy} onChange={event => { setHierarchy(event.target.value); setPath({}); setPage(1); }}><option value="1c">Группы 1С</option><option value="classification">Классификация iPrice</option></select></label>}
      </div>
    </div></Panel>
    {error && <p role="alert">{error}</p>}
    {openingProduct && <p role="status" className="sm-iprice-loading">Загружаем карточку…</p>}
    {!ready && !error && <p role="status" className="sm-iprice-loading">Загружаем сравнение…</p>}
    {sum && marketView && <div className="ip-grid k4">{[
      ["Товаров", sum.total_products, "В выбранной области"],
      ["Разница с рынком", sum.median_deviation_percent == null ? "—" : fmtPct(sum.median_deviation_percent, { percent: true, sign: true }), "Середина по товарам; минус значит дешевле"],
      ["Типичная новая цена", fmtMoney(sum.median_final_rrp), `Сейчас ${fmtMoney(sum.median_retail_price)}`],
      ["Без цены", sum.calculation_errors, "Не хватило исходных данных"],
    ].map(([label, value, sub]) => <div className="ip-kpi" key={label}><span className="l">{label}</span><span className="v">{value ?? "—"}</span><span className="d">{sub}</span></div>)}</div>}
    {ready && <Panel>
      <div className="ip-panel-head">{(allSelected || selectedCodes.length > 0) && canEdit && <ParameterEditor snapshotId={snapshotId} onSaved={onSaved} buttonTitle={allSelected ? "Изменить все товары выборки" : undefined} selectionCount={allSelected ? null : selectedCodes.length} listScope={{ mode: "products", filters: allSelected ? allFilters : { code_1c: selectedCodes }, search: allSelected ? query : "", zone: allSelected ? zone : "", problems_only: false }} />}{grouped && onOpenList && <Button size="s" icon="table" onClick={() => onOpenList({ zone, search: query, filters: { ...filters, ...Object.fromEntries(Object.entries(path).map(([key, value]) => [key, [value]])) } })}>Товары в таблице</Button>}<nav className="ip-crumbs" aria-label="Уровень">{grouped ? <><Button size="s" variant="ghost" disabled={!Object.values(path).some(value => value !== "__empty__")} onClick={() => { setPath({}); setPage(1); }}>Все группы</Button>{Object.entries(path).map(([key, value], i, entries) => {
        if (value === "__empty__") return null;
        const current = !entries.slice(i + 1).some(([, next]) => next !== "__empty__");
        return <span className="ip-row" style={{ gap: 6, flexWrap: "nowrap" }} key={key}><Icon name="chev" size={12} /><Button size="s" variant="ghost" disabled={current} aria-current={current ? "page" : undefined} onClick={() => { setPath(Object.fromEntries(entries.slice(0, i + 1))); setPage(1); }}>{value}</Button></span>;
      })}</> : <b>{comparison ? "Изменения между расчётами" : "Цены по регионам"}</b>}</nav></div>
      {sum?.zones && marketView && <div className="sm-zone-summary">{bar(sum.zones)}</div>}
      {((grouped && data.next_level) || !grouped) ? <div className="ip-tree"><div className="ip-zonebar-row head"><span>Группа</span><span className="num">Товаров</span><span>Распределение по цветам</span><button className="ip-linkbtn num" onClick={() => { setOrdering(ordering === "-median_deviation_percent" ? "median_deviation_percent" : "-median_deviation_percent"); setPage(1); }}>Разница с рынком ↕</button><span className="num">Доля сравнения</span></div>
        {data.results.map(item => <div className="ip-zonebar-row" key={item.key || item.id}><span className="ip-row"><button className="link" onClick={() => { if (grouped) { setPath({ ...path, [data.next_level]: item.key }); setPage(1); } else onOpenList?.({ mode: "regions", zone, search: query, filters: { ...filters, sale_region: [item.key] } }); }}>{item.label}</button>{grouped && onOpenList && <Button size="s" variant="ghost" icon="table" aria-label={`Открыть «${item.label}» в списке цен`} onClick={() => onOpenList({ zone, search: query, filters: { ...filters, ...Object.fromEntries(Object.entries({ ...path, [data.next_level]: item.key }).map(([k, v]) => [k, [v]])) } })} />}</span><span className="num">{item.product_count ?? "—"}</span>{bar(item.zones)}<span className="num">{fmtPct(item.median_deviation_percent, { percent: true, sign: true })}</span><span className="num">{fmtPct(item.market_coverage_percent, { percent: true, digits: 0 })}</span></div>)}
      </div> : <div className="sm-iprice-table"><table className="ip-table"><thead><tr>{["Фото", ...(canEdit ? ["Выбор"] : []), "Товар", ...(grouped ? [] : ["Регион"]), !marketView ? "Было" : "Сейчас", "Новая цена", !marketView ? "Изменение" : "У конкурентов", ...(marketView ? ["Зона"] : [])].map(label => <th key={label}>{label === "Выбор" ? <label className="ip-row small"><input type="checkbox" aria-label="Выбрать все товары выборки" checked={allSelected} ref={node => { if (node) node.indeterminate = !allSelected && selectedCodes.length > 0; }} onChange={event => setSelection({ key: selectionKey, codes: [], all: event.target.checked })} />Все товары</label> : label}</th>)}</tr></thead><tbody>{data.results.map((item, i) => {
        const row = !marketView ? item.comparison || item.base : item;
        const changes = { added: "Добавлена", removed: "Удалена", changed: "Изменена", unchanged: "Без изменений" };
        return <tr key={row.id ?? `${row.code_1c}-${row.sale_region}-${i}`}><td><ProductImage src={row.image} name={row.nom} /></td>{canEdit && <td><input type="checkbox" aria-label={`Выбрать ${row.code_1c}`} disabled={allSelected} checked={allSelected || selectedCodes.includes(row.code_1c)} onChange={event => setSelection({ key: selectionKey, all: false, codes: event.target.checked ? [...new Set([...selectedCodes, row.code_1c])] : selectedCodes.filter(code => code !== row.code_1c) })} /></td>}<td><button className="ip-linkbtn sm-product-name" onClick={() => openProduct(row.snapshot_product_id || row.id)}>{row.nom}</button><span className="sub">{row.code_1c}</span></td>{!grouped && <td>{row.sale_region || "—"}</td>}
          <td className="num">{fmtMoney(!marketView ? item.base?.effective_approved_rrp : row.retail_price ?? row.median_retail_price ?? row.current_retail_median)}</td><td className="num"><b>{fmtMoney(!marketView ? item.comparison?.effective_approved_rrp : row.final_rrp ?? row.median_final_rrp ?? row.effective_approved_rrp_median)}</b></td>
          <td className={marketView ? "num" : undefined}>{!marketView ? changes[item.change_type] || item.change_type : fmtMoney(row.market_price ?? row.median_market_price ?? row.competitor_rrp_median)}</td>
          {marketView && <td><span className={`sm-iprice-tag sm-iprice-tag--${row.zone}`}>{zones[row.zone] || row.zone || "—"}</span></td>}</tr>;
      })}</tbody></table></div>}
      {!data.results.length && <div className="ip-empty"><b>Строк нет</b><span>Измените фильтры или выберите другой расчёт.</span></div>}
      <Pager page={data?.pagination?.page || page} totalPages={pages} count={data?.pagination?.count} pageSize={data?.pagination?.page_size || 50} onPage={setPage} disabled={!ready} />
    </Panel>}
    <ZoneSettings canEdit={canEdit} onSaved={() => setRefresh(value => value + 1)} />
  </section>;
}

export function ProductDetails(props) {
  const [trail, setTrail] = useState([]);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  async function openRelated(productId) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setOpening(true); setError("");
    try {
      const { data } = await api.get(`${root}${props.snapshotId}/rows/`, { params: { product_id: productId }, signal: controller.signal });
      if (controller.signal.aborted) return;
      const row = data.rows.find(item => String(item.product_id) === String(productId));
      if (!row) throw new Error("Товар отсутствует в выбранном расчёте.");
      setTrail(items => [...items, row]);
    } catch (err) { if (!controller.signal.aborted) setError(errorText(err)); }
    finally { if (!controller.signal.aborted) setOpening(false); }
  }
  function back() {
    request.current?.abort(); setOpening(false); setError("");
    setTrail(items => items.slice(0, -1));
  }
  return <>{opening && <p role="status" className="sm-iprice-loading">Загружаем карточку…</p>}{error && <p role="alert">{error}</p>}
    <div hidden={trail.length > 0}><ProductDetailsBody {...props} onOpenProduct={openRelated} /></div>
    {trail.map((row, index) => <div key={`${index}-${row.id}`} hidden={index !== trail.length - 1}><ProductDetailsBody {...props} productId={row.product_id} region={row} onOpenProduct={openRelated} onBack={back} backLabel="Вернуться к товару" /></div>)}
  </>;
}

function ProductDetailsBody({ snapshotId, productId, region: initialRegion, canEdit, canEditPrice, onSaved, onOpenProduct, onBack, backLabel = "Цены" }) {
  const [competitorTarget, setCompetitorTarget] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [counts, setCounts] = useState({ own: null, market: null });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("regions");
  const [region, setRegion] = useState(initialRegion);
  const [regions, setRegions] = useState(null);
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/`, { signal: controller.signal }).then(r => setData(r.data))
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить карточку."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  useEffect(() => {
    const controller = new AbortController();
    async function loadRegions() {
      const collected = [];
      let page = 1, pages;
      do {
        const { data: response } = await api.get(`${root}${snapshotId}/rows/`, { params: { product_id: productId, page }, signal: controller.signal });
        collected.push(...response.rows.filter(row => row.product_id === productId));
        pages = response.pages; page++;
      } while (page <= pages && !controller.signal.aborted);
      if (!controller.signal.aborted) setRegions(collected);
    }
    loadRegions().catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить регионы товара. Показан выбранный регион."); });
    return () => controller.abort();
  }, [snapshotId, productId, initialRegion.snapshot_product__code_1c]);
  const costs = [["product_cost", "Закупочная цена", "Без НДС, за месяц расчёта"],
    ["logistics_unit", "Доставка на единицу", region.include_transport ? "Транспортные расходы учитываются" : "Транспортные расходы выключены"],
    ["cost_with_logistics", "Закупка с доставкой", "Основа расчёта цены"],
    ["regional_competitor_rrp_median", "Цена конкурентов в регионе", "Середина цен пригодных аналогов"],
    ["preliminary_rrp", "Цена по правилам компании", "С учётом коэффициента аналога или маржи эксклюзива"],
    ["minimum_price", "Нижняя граница", "Защита минимальной маржи"],
    ["calculated_rrp", "Цена по расчёту", "Округлена до целого рубля"],
    ["final", "Новая цена", "С учётом подтверждённой ручной цены"]];
  return <section className="ip-stack sm-product-page">{error && <p role="alert">{error}</p>}{data ? <>
    <nav className="ip-crumbs" aria-label="Путь товара">{onBack && <button className="ip-linkbtn" onClick={onBack}>{backLabel}</button>}{[data.category, data.subcategory, data.subcategory_type].filter(Boolean).map((label, i) => <span className="ip-row" style={{ gap: 6 }} key={i}>{(onBack || i > 0) && <Icon name="chev" size={12} />}<span>{label}</span></span>)}</nav>
    <div className="ip-row"><div className="ip-thumb"><ProductImage src={data.image} name={data.nom} /></div><div><h1>{data.nom}</h1><div className="ip-row small muted"><span className="mono">код 1С {data.code}</span><span className="ip-tag outline">{data.method === "analog" ? "По рынку" : "Эксклюзив"}</span>{data.assortment_matrix_status && <span className="ip-tag gray"><Term title="САМ" text="Место товара в ассортиментной матрице компании. Например, «2. Активный / складская программа»: товары, которые компания держит в наличии без перерывов.">САМ: {data.assortment_matrix_status}</Term></span>}{[data.material, data.color, data.modification].filter(Boolean).map((v, i) => <span className="ip-tag gray" key={i}>{v}</span>)}{data.url && /^https?:\/\//i.test(data.url) && <a href={data.url} target="_blank" rel="noreferrer">карточка на нашем сайте</a>}</div></div></div>
    {!![...(data.error_codes || []), ...(data.warning_codes || [])].length && <div role="alert" className={`ip-alert ${data.error_codes?.length ? "error" : "warning"}`}><div className="body"><b>{data.error_codes?.length ? "iPrice посчитал цену не во всех регионах" : "iPrice посчитал цену с замечанием"}</b><span>{[...new Set([...(data.error_codes || []), ...(data.warning_codes || [])])].map(c => issues[c] || c).join(". ")}</span></div></div>}
    <div className="ip-story">
      <div className="cell"><span className="l">Сейчас в прайсе</span><strong className="v">{fmtMoney(data.current_retail_median)}</strong></div><Icon name="chev" className="arrow" />
      <div className="cell main"><span className="l">Новая цена</span><strong className="v">{fmtMoney(data.effective_approved_rrp_median)}</strong><span className={`d ${Number(data.current_retail_median) > 0 && Number(data.effective_approved_rrp_median) > Number(data.current_retail_median) * 1.1 ? "ip-jump" : ""}`}>{Number(data.current_retail_median) > 0 && data.effective_approved_rrp_median != null ? Math.abs(Number(data.effective_approved_rrp_median) / Number(data.current_retail_median) - 1) < 0.0005 ? "как в прайсе" : `${Number(data.effective_approved_rrp_median) > Number(data.current_retail_median) ? "дороже" : "дешевле"} на ${fmtPct(Math.abs(Number(data.effective_approved_rrp_median) / Number(data.current_retail_median) - 1))}${Number(data.effective_approved_rrp_median) > Number(data.current_retail_median) * 1.1 ? ": резкий рост" : ""}` : "—"}</span></div>
      <div className="sep" /><div className="cell"><span className="l">У конкурентов</span><strong className="v">{fmtMoney(data.competitor_rrp_median)}</strong><span className="d">от {fmtMoney(data.competitor_rrp_min)} до {fmtMoney(data.competitor_rrp_max)}</span></div>
      <div className="cell"><span className="l">К рынку</span><ZoneTag zone={data.zone} percent={Number(data.competitor_rrp_median) > 0 && data.effective_approved_rrp_median != null ? (Number(data.effective_approved_rrp_median) / Number(data.competitor_rrp_median) - 1) * 100 : null} /></div>
      <p className="foot">Показаны медианы цен по регионам без НДС. Ниже — расчёт выбранного региона. Ручные цены: {(regions || []).filter(r => r.effective.approval_source === "manual").length} регионов.</p>
    </div>
    <Tabs value={tab} onChange={setTab} items={[["regions", "Цены по регионам"], ["competitors", `Конкуренты · ${data.competitors.length}`], ["market", `Рынок категории · ${counts.market ?? "…"}`], ["own", `Наша линейка · ${counts.own ?? "…"}`]]} />
    {tab === "regions" && <>
      <Panel title="Цены по регионам" sub="Строка региона показывает ниже коридор и расчёт цены."><div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Регион продажи</th><th className="num">У конкурентов</th><th className="num">Сейчас</th><th className="num">Новая цена</th><th className="num">Маржа</th><th>К рынку</th><th /></tr></thead><tbody>{(regions?.length ? regions : [initialRegion]).map(row => <tr key={row.id} tabIndex={0} className={`is-clickable ${row.id === region.id ? "is-sel" : ""}`} onClick={event => { if (!event.target.closest("button, a, input, label")) setRegion(row); }} onKeyDown={event => { if (event.key === "Enter" && event.target === event.currentTarget) setRegion(row); }}><td><Button variant="ghost" size="s" onClick={() => setRegion(row)}>{row.sale_region}</Button></td><td className="num">{fmtMoney(row.regional_competitor_rrp_median)}</td><td className="num">{fmtMoney(row.current_retail)}</td><td className="num"><b>{fmtMoney(row.effective.rrp)}</b><span className="sub">{fmtMoney(row.effective_gross?.rrp)} с НДС</span><span className="ip-tag blue" title={row.effective.approval_comment || ""}>{row.effective.approval_source === "manual" ? "Цена сотрудника" : "Расчёт iPrice"}</span></td><td className="num">{Number(row.effective.rrp) > 0 && row.cost_with_logistics != null ? fmtPct(1 - Number(row.cost_with_logistics) / Number(row.effective.rrp), { digits: 0 }) : "—"}</td><td><ZoneTag zone={row.zone} percent={Number(row.regional_competitor_rrp_median) > 0 && row.effective.rrp != null ? (Number(row.effective.rrp) / Number(row.regional_competitor_rrp_median) - 1) * 100 : null} /></td><td>{canEditPrice && row.calculation_status !== "error" && <Button size="s" onClick={() => { setRegion(row); setEditing(true); }}>Изменить</Button>}</td></tr>)}</tbody></table></div></Panel>
      {!![...(region.error_codes || []), ...(region.warning_codes || [])].length && <p role="status">{[...new Set([...(region.error_codes || []), ...(region.warning_codes || [])])].map(c => issues[c] || c).join(". ")}</p>}
      <Panel title={region.sale_region} sub="Коридор цены: закупочная стоимость, нижняя граница, рынок и новая цена" actions={canEditPrice && region.calculation_status !== "error" && <Button variant="accent" icon="edit" onClick={() => setEditing(true)}>Своя цена</Button>}><div className="sm-panel-body"><Corridor region={{ ...region, effective_approved_rrp: region.effective.rrp }} /></div></Panel>
      <div className="ip-grid k2"><Panel title="Расчёт цены" sub="Шаги от закупочной стоимости до новой цены">
        <ol className="ip-explain sm-panel-body">{costs.map(([key, title, hint], i) => <li className={key === "final" ? "st final" : "st"} key={key}><span className="n">{i + 1}</span><div><b>{title}</b><p className="small muted">{hint}</p></div><strong className="v">{fmtMoney(key === "final" ? region.effective.rrp : region[key])}</strong></li>)}</ol>
      </Panel><Panel title="Цены для разных покупателей" sub="Оптовые цены рассчитаны по скидкам выбранного региона"><div className="sm-panel-body"><PriceLadder region={region} />
        <dl className="sm-product-params">{[["base_analog", "Коэффициент аналога"], ["base_exclusive", "Маржа эксклюзива"], ["minimum_margin", "Минимальная маржа"], ["quantity_eurotruck", "Количество в еврофуре (справочно)"]].map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{region[key] == null ? "—" : ["base_exclusive", "minimum_margin"].includes(key) ? fmtPct(region[key]) : fmtNumber(region[key], key === "base_analog" ? 6 : 0)}</dd></div>)}</dl>
      </div></Panel></div>
      {canEdit && <ParameterEditor key={`parameters-${region.id}`} snapshotId={snapshotId} row={region} onSaved={onSaved} />}
    </>}
    {tab === "competitors" && <Panel title="Конкуренты в расчёте" sub="Пригодные цены и регионы аналогов" actions={<Button size="s" variant="ghost" onClick={() => setShowHistory(true)}>История и состав аналогов</Button>}><div className="ip-stack sm-panel-body">
      {!data.competitors.length && <div className="ip-empty"><b>Данных конкурентов нет</b></div>}
      <div className="ip-cards">{(data.competitor_cards || []).map(card => <CompetitorCard key={card.group_key} card={card} editable={canEdit} onChangeMode={(item, mode) => setCompetitorTarget({ card: item, mode })} />)}</div>
      {competitorTarget && <SelectionModal target={competitorTarget} snapshotId={snapshotId} productId={productId} revision={data.edit_revision} onClose={() => setCompetitorTarget(null)} onSaved={onSaved} />}
    </div></Panel>}
    <div hidden={tab !== "market"}><MarketAssortment snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} onCount={value => setCounts(current => ({ ...current, market: value }))} onHistory={() => setShowHistory(true)} /></div>
    <Drawer open={showHistory} onClose={() => setShowHistory(false)} title="История и состав аналогов"><CompetitorEditor expanded snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} /></Drawer>
    <div hidden={tab !== "own"}><OwnAssortment snapshotId={snapshotId} productId={productId} onOpenProduct={onOpenProduct} onCount={value => setCounts(current => ({ ...current, own: value }))} /></div>
    <Drawer open={editing} onClose={() => setEditing(false)} title={`Цена: ${region.sale_region}`} sub={data.nom}><PriceEditor key={region.id} snapshotId={snapshotId} row={region} onSaved={onSaved} /></Drawer>
  </> : !error && <p role="status" className="sm-iprice-loading">Загружаем карточку…</p>}</section>;
}

function CompetitorEditor({ snapshotId, productId, canEdit, onSaved, expanded = false }) {
  const [confirm, confirmation] = useConfirm();
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
    if (!await confirm("Изменить состав аналогов и пересчитать товар? Ручные цены этого товара потребуется подтвердить заново.")) return;
    setBusy(true); setError("");
    try {
      await saveCompetitorSelection({ snapshotId, productId, keys: [id], mode, reason, revision: data.edit_revision });
      onSaved();
    } catch (err) { setError(errorText(err, "Не удалось изменить состав аналогов.")); }
    finally { setBusy(false); }
  }
  const names = { auto: "Авто", include: "Включён вручную", exclude: "Исключён" };
  return <details className="sm-competitor-editor" open={expanded || undefined}><summary>Состав аналогов и история</summary><div className="sm-competitor-editor-body">{confirmation}
    <p>Доступны активные позиции конкурентов с той же классификацией. Изменение пересчитывает товар и требует повторного подтверждения ручных цен.</p>
    {error && <p role="alert">{error}</p>}
    {data && <>
      {canEdit && data.editable && <label className="ip-field">Причина изменения аналогов<input className="ip-input" value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></label>}
      {!data.items.length && <div className="ip-empty"><b>Нет подходящих позиций</b><span>Проверьте наличие активной классификации товара и конкурентов.</span></div>}
      {data.items.map(item => <div className="sm-competitor-editor-item" key={item.id}><p>{item.source} · {/^https?:\/\//i.test(item.url || "") ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a> : item.url} · {names[item.mode]} {item.used_in_snapshot && <span className="ip-tag green">Учтён в расчёте</span>}
        </p>{canEdit && data.editable && <select className="ip-select" aria-label={`Участие аналога ${item.id}`} value={item.mode} disabled={busy || !reason.trim() || data.page !== page} onChange={e => change(item.id, e.target.value)}>{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</div>)}
      <Pager page={page} totalPages={data.pages} count={data.count} pageSize={50} onPage={setPage} disabled={busy} />
      <h4>Последние 50 изменений</h4>{data.changes.map(item => <p key={item.id}>Аналог {item.override__product_key_competitor} · {names[item.selection_mode]} · {item.changed_by__username} · {new Date(item.date_add).toLocaleString("ru-RU")} · {item.reason}</p>)}
    </>}
  </div></details>;
}

function OwnAssortment({ snapshotId, productId, onOpenProduct, onCount }) {
  const countCallback = useRef(onCount);
  useEffect(() => { countCallback.current = onCount; }, [onCount]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/own/`, { signal: controller.signal }).then(r => { setData(r.data); countCallback.current(r.data.results.length); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить собственную линейку."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  return <Panel title="Наша линейка" sub="Проверьте порядок цен внутри линейки: ведро на 20 л должно стоить дороже ведра на 10 л."><div className="sm-own-assortment">
    {error && <p role="alert">{error}</p>}{!data && !error && <p className="sm-iprice-loading" role="status">Загружаем линейку…</p>}
    {data?.unavailable_reason && <p role="status">{data.unavailable_reason}</p>}
    {data && !data.results.length && !data.unavailable_reason && <div className="ip-empty"><b>Других товаров этой классификации нет</b></div>}
    <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Товар</th><th>Подкатегория</th><th>Свойства</th><th>Способ расчёта</th><th className="num">У конкурентов <Term icon title="У конкурентов" text="Медиана пригодных цен конкурентов." /></th><th className="num">Новая цена <Term icon title="Новая цена" text="Итоговая цена с учётом подтверждённой ручной цены." /></th></tr></thead><tbody>{data?.results.map(item => <tr key={item.snapshot_product_id}><td><button className="ip-linkbtn sm-own-product-name" onClick={() => onOpenProduct?.(item.snapshot_product_id)}>{item.name}</button><span className="sub">{item.code_1c}</span></td><td>{item.subcategory_type || "—"}</td><td>{[item.material, item.color, item.modification].filter(Boolean).join(", ") || "—"}</td><td><span className="ip-tag outline"><Icon name={item.pricing_method === "analog" ? "compare" : "wallet"} size={12} />{item.pricing_method === "analog" ? "По рынку" : "Эксклюзив"}</span></td><td className="num">{fmtMoney(item.market_price)}</td><td className="num">{fmtMoney(item.final_price)}</td></tr>)}</tbody></table></div>
  </div></Panel>;
}

function MarketAssortment({ snapshotId, productId, canEdit, onSaved, onCount, onHistory }) {
  const countCallback = useRef(onCount);
  useEffect(() => { countCallback.current = onCount; }, [onCount]);
  const [target, setTarget] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [onlyFree, setOnlyFree] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/market/`, { signal: controller.signal }).then(r => { setData(r.data); countCallback.current(r.data.counts.cards); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить рынок категории."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  const cards = (data?.results || []).filter(card => !onlyFree || !card.is_used_in_snapshot);
  return <Panel title="Рынок категории" sub="Активная классификация конкурентов; цены отбираются на дату расчёта. Эти карточки сами по себе не добавляют аналог в расчёт." actions={<div className="ip-row"><Button size="s" variant="ghost" onClick={onHistory}>История и состав аналогов</Button><label className="ip-check small"><input type="checkbox" checked={onlyFree} onChange={e => setOnlyFree(e.target.checked)} />Только неучтённые</label></div>}>
    <div className="ip-stack sm-panel-body">{error && <p role="alert">{error}</p>}{!data && !error && <p className="sm-iprice-loading" role="status">Загружаем рынок категории…</p>}{data?.unavailable_reason && <p>{data.unavailable_reason}</p>}
      {data && <p className="small muted">Всего карточек: {data.counts.cards} · учтены в расчёте: {data.counts.used_in_snapshot ?? 0}</p>}
      {data && !cards.length && !data.unavailable_reason && <div className="ip-empty"><b>Нет товаров для выбранного отбора</b></div>}
      <div className="ip-cards">{cards.map(card => <CompetitorCard key={JSON.stringify(card.group_key)} card={card} editable={canEdit && data.editable} onChangeMode={(card, mode) => setTarget({ card, mode })} />)}</div>
      {target && <SelectionModal target={target} snapshotId={snapshotId} productId={productId} revision={data.edit_revision} onClose={() => setTarget(null)} onSaved={onSaved} />}
    </div>
  </Panel>;
}
