import { PriceLadder } from "./PriceLadder";
import { ZoneSettings } from "./PriceZones";
import { ZoneTag } from "./ZoneTag";
import { issues } from "./issueLabels";
import { CompetitorCard, SelectionModal } from "./CompetitorCard";
import { saveCompetitorSelection } from "./competitorSelection";
import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useConfirm } from "./ui/useConfirm";
import { api } from "../../api/client";
import { priceText, errorText } from "./format";
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

export function MarketAnalysis({ snapshotId, canEdit, initialZone = "", onOpenList }) {
  const navigate = useNavigate();
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
      .then(response => { setData({ ...response.data, queryKey }); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить сравнение."); });
    return () => controller.abort();
  }, [snapshotId, comparison, page, queryKey, grouped, pathKey, hierarchy, marketView, filtersKey, zone, query, ordering]);
  const ready = data?.queryKey === queryKey;
  const pages = data?.total_pages ?? data?.pagination?.pages ?? 1;
  const sum = ready ? data.summary : null;
  const colors = { below_market: "#25466a", in_market: "#2e7d5b", above_market: "#f39f63", critical_above: "#b23b3b", no_market_data: "#c3ccd6" };
  const bar = (items = []) => <div className="ip-bar">{items.filter(z => z.count > 0).map(z => <span key={z.key} style={{ width: `${z.percent}%`, background: colors[z.key] }} title={`${zones[z.key]}: ${z.count}`} />)}</div>;
  return <section className="ip-stack sm-market-page"><h3 className="sr-only">Рынок и изменения цен</h3>
    <Panel><div className="ip-stack sm-panel-body">
      <div className="ip-row between"><div className="ip-seg" role="group" aria-label="Разрез"><button aria-pressed={grouped} onClick={() => { setComparison("groups"); setPath({}); setPage(1); }}>По группам товаров</button><button aria-pressed={comparison === ""} onClick={() => { setComparison(""); setPath({}); setPage(1); }}>По регионам</button></div>
        </div>
      <div className="ip-affix" style={{ width: 300, maxWidth: "100%" }}><span className="pre"><Icon name="search" size={16} /></span><input className="ip-input" type="search" aria-label="Найти товар на рынке" placeholder="Название или код 1С" value={search} onChange={e => setSearch(e.target.value)} /></div>
      {marketView && <ZonePicker value={zone} onChange={value => { setZone(value); setPage(1); }} />}
      <SelectMarketFilters snapshotId={snapshotId} mode={grouped ? "products" : "regions"} zone={marketView ? zone : ""} comparisonId={marketView ? undefined : comparison} search={query} filters={filters} onChange={value => { setFilters(value); setPath({}); setPage(1); }} />
      <div className="ip-row sm-market-controls">{grouped && <label>Группировка<select className="ip-select" aria-label="Группировка" value={hierarchy} onChange={event => { setHierarchy(event.target.value); setPath({}); setPage(1); }}><option value="1c">Группы 1С</option><option value="classification">Классификация iPrice</option></select></label>}
      </div>
    </div></Panel>
    {error && <p role="alert">{error}</p>}
    {!ready && !error && <p role="status" className="sm-iprice-loading">Загружаем сравнение…</p>}
    {sum && marketView && <div className="ip-grid k4">{[
      ["Товаров", sum.total_products, "В выбранной области"],
      ["Разница с рынком", sum.median_deviation_percent == null ? "—" : `${priceText(sum.median_deviation_percent)}%`, "Середина по товарам; минус значит дешевле"],
      ["Типичная новая цена", priceText(sum.median_final_rrp), `Сейчас ${priceText(sum.median_retail_price)}`],
      ["Без цены", sum.calculation_errors, "Не хватило исходных данных"],
    ].map(([label, value, sub]) => <div className="ip-kpi" key={label}><span className="l">{label}</span><span className="v">{value ?? "—"}</span><span className="d">{sub}</span></div>)}</div>}
    {ready && <Panel>
      <div className="ip-panel-head">{grouped && onOpenList && <Button size="s" icon="table" onClick={() => onOpenList({ zone, search: query, filters: { ...filters, ...Object.fromEntries(Object.entries(path).map(([key, value]) => [key, [value]])) } })}>Товары в таблице</Button>}<nav className="ip-crumbs" aria-label="Уровень">{grouped ? <><Button size="s" variant="ghost" onClick={() => { setPath({}); setPage(1); }}>Все группы</Button>{Object.entries(path).map(([key, value], i) => <Button key={key} size="s" variant="ghost" onClick={() => { setPath(Object.fromEntries(Object.entries(path).slice(0, i + 1))); setPage(1); }}>› {value}</Button>)}</> : <b>{comparison ? "Изменения между расчётами" : "Цены по регионам"}</b>}</nav></div>
      {sum?.zones && marketView && <div className="sm-zone-summary">{bar(sum.zones)}</div>}
      {((grouped && data.next_level) || !grouped) ? <div className="ip-tree"><div className="ip-zonebar-row head"><span>Группа</span><span className="num">Товаров</span><span>Распределение по цветам</span><button className="ip-linkbtn num" onClick={() => { setOrdering(ordering === "-median_deviation_percent" ? "median_deviation_percent" : "-median_deviation_percent"); setPage(1); }}>Разница с рынком ↕</button><span className="num">Доля сравнения</span></div>
        {data.results.map(item => <div className="ip-zonebar-row" key={item.key || item.id}><span className="ip-row"><button className="link" onClick={() => { if (grouped) { setPath({ ...path, [data.next_level]: item.key }); setPage(1); } else onOpenList?.({ mode: "regions", zone, search: query, filters: { ...filters, sale_region: [item.key] } }); }}>{item.label}</button>{grouped && onOpenList && <Button size="s" variant="ghost" icon="table" aria-label={`Открыть «${item.label}» в списке цен`} onClick={() => onOpenList({ zone, search: query, filters: { ...filters, ...Object.fromEntries(Object.entries({ ...path, [data.next_level]: item.key }).map(([k, v]) => [k, [v]])) } })} />}</span><span className="num">{item.product_count ?? "—"}</span>{bar(item.zones)}<span className="num">{priceText(item.median_deviation_percent)}%</span><span className="num">{priceText(item.market_coverage_percent)}%</span></div>)}
      </div> : <div className="sm-iprice-table"><table className="ip-table"><thead><tr>{["Товар", "Регион", !marketView ? "Было" : "Сейчас", "Новая цена", !marketView ? "Изменение" : "У конкурентов", ...(marketView ? ["Зона"] : [])].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{data.results.map((item, i) => {
        const row = !marketView ? item.comparison || item.base : item;
        const changes = { added: "Добавлена", removed: "Удалена", changed: "Изменена", unchanged: "Без изменений" };
        return <tr key={row.id ?? `${row.code_1c}-${row.sale_region}-${i}`}><td><span className="name">{row.nom}</span><span className="sub">{row.code_1c}</span></td><td>{row.sale_region || "—"}</td>
          <td className="num">{priceText(!marketView ? item.base?.effective_approved_rrp : row.retail_price ?? row.median_retail_price ?? row.current_retail_median)}</td><td className="num"><b>{priceText(!marketView ? item.comparison?.effective_approved_rrp : row.final_rrp ?? row.median_final_rrp ?? row.effective_approved_rrp_median)}</b></td>
          <td className={marketView ? "num" : undefined}>{!marketView ? changes[item.change_type] || item.change_type : priceText(row.market_price ?? row.median_market_price ?? row.competitor_rrp_median)}</td>
          {marketView && <td><span className={`sm-iprice-tag sm-iprice-tag--${row.zone}`}>{zones[row.zone] || row.zone || "—"}</span></td>}</tr>;
      })}</tbody></table></div>}
      {!data.results.length && <div className="ip-empty"><b>Строк нет</b><span>Измените фильтры или выберите другой расчёт.</span></div>}
      <div className="ip-row sm-pager"><Button size="s" disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</Button><span className="small muted">{page} / {pages}</span><Button size="s" disabled={page >= pages} onClick={() => setPage(page + 1)}>Далее</Button></div>
    </Panel>}
    <ZoneSettings canEdit={canEdit} onSaved={() => setRefresh(value => value + 1)} />
  </section>;
}

export function ProductDetails({ snapshotId, productId, region: initialRegion, canEdit, canEditPrice, onSaved, onOpenProduct }) {
  const [competitorTarget, setCompetitorTarget] = useState(null);
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
    <nav className="ip-crumbs">{[data.category, data.subcategory, data.subcategory_type].filter(Boolean).map((label, i) => <span key={i}>{i > 0 && "› "}{label}</span>)}</nav>
    <div className="ip-row"><div className="ip-thumb">{/^https?:\/\//i.test(data.image || "") ? <img src={data.image} alt={data.nom} /> : <Icon name="box" />}</div><div><h1>{data.nom}</h1><div className="ip-row small muted"><span className="mono">код 1С {data.code}</span><span className="ip-tag outline">{data.method === "analog" ? "По рынку" : "Эксклюзив"}</span>{[data.material, data.color, data.modification].filter(Boolean).map((v, i) => <span className="ip-tag gray" key={i}>{v}</span>)}{data.url && /^https?:\/\//i.test(data.url) && <a href={data.url} target="_blank" rel="noreferrer">карточка на нашем сайте</a>}</div></div></div>
    {!![...(data.error_codes || []), ...(data.warning_codes || [])].length && <div role="alert" className={`ip-alert ${data.error_codes?.length ? "error" : "warning"}`}><div className="body"><b>{data.error_codes?.length ? "iPrice посчитал цену не во всех регионах" : "iPrice посчитал цену с замечанием"}</b><span>{[...new Set([...(data.error_codes || []), ...(data.warning_codes || [])])].map(c => issues[c] || c).join(". ")}</span></div></div>}
    <div className="ip-story">
      <div className="cell"><span className="l">Сейчас в прайсе</span><strong className="v">{priceText(data.current_retail_median)} ₽</strong></div><Icon name="chev" className="arrow" />
      <div className="cell main"><span className="l">Новая цена</span><strong className="v">{priceText(data.effective_approved_rrp_median)} ₽</strong><span className="d">{Number(data.current_retail_median) > 0 && data.effective_approved_rrp_median != null ? `${priceText((Number(data.effective_approved_rrp_median) / Number(data.current_retail_median) - 1) * 100)}%` : "—"}</span></div>
      <div className="sep" /><div className="cell"><span className="l">У конкурентов</span><strong className="v">{priceText(data.competitor_rrp_median)} ₽</strong><span className="d">от {priceText(data.competitor_rrp_min)} до {priceText(data.competitor_rrp_max)}</span></div>
      <div className="cell"><span className="l">К рынку</span><ZoneTag zone={data.zone} percent={Number(data.competitor_rrp_median) > 0 && data.effective_approved_rrp_median != null ? (Number(data.effective_approved_rrp_median) / Number(data.competitor_rrp_median) - 1) * 100 : null} /></div>
      <p className="foot">Показаны медианы цен по регионам без НДС. Ниже — расчёт выбранного региона. Ручные цены: {(regions || []).filter(r => r.effective.approval_source === "manual").length} регионов.</p>
    </div>
    <Tabs value={tab} onChange={setTab} items={[["regions", "Цены по регионам"], ["competitors", `Конкуренты · ${data.competitors.length}`], ["market", "Рынок категории"], ["own", "Наша линейка"]]} />
    {tab === "regions" && <>
      <Panel title="Цены по регионам" sub="Строка региона показывает ниже коридор и расчёт цены."><div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Регион продажи</th><th className="num">У конкурентов</th><th className="num">Сейчас</th><th className="num">Новая цена</th><th className="num">Маржа</th><th>К рынку</th><th /></tr></thead><tbody>{(regions?.length ? regions : [initialRegion]).map(row => <tr key={row.id} className={row.id === region.id ? "is-sel" : ""}><td><Button variant="ghost" size="s" onClick={() => setRegion(row)}>{row.sale_region}</Button></td><td className="num">{priceText(row.regional_competitor_rrp_median)}</td><td className="num">{priceText(row.current_retail)}</td><td className="num"><b>{priceText(row.effective.rrp)}</b><span className="sub">{priceText(row.effective_gross?.rrp)} с НДС</span><span className="ip-tag blue" title={row.effective.approval_comment || ""}>{row.effective.approval_source === "manual" ? "Цена сотрудника" : "Расчёт iPrice"}</span></td><td className="num">{Number(row.effective.rrp) > 0 && row.cost_with_logistics != null ? ((1 - Number(row.cost_with_logistics) / Number(row.effective.rrp)) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + "%" : "—"}</td><td><ZoneTag zone={row.zone} percent={Number(row.regional_competitor_rrp_median) > 0 && row.effective.rrp != null ? (Number(row.effective.rrp) / Number(row.regional_competitor_rrp_median) - 1) * 100 : null} /></td><td>{canEditPrice && row.calculation_status !== "error" && <Button size="s" onClick={() => { setRegion(row); setEditing(true); }}>Изменить</Button>}</td></tr>)}</tbody></table></div></Panel>
      {!![...(region.error_codes || []), ...(region.warning_codes || [])].length && <p role="status">{[...new Set([...(region.error_codes || []), ...(region.warning_codes || [])])].map(c => issues[c] || c).join(". ")}</p>}
      <Panel title={region.sale_region} sub="Коридор цены: закупочная стоимость, нижняя граница, рынок и новая цена" actions={canEditPrice && region.calculation_status !== "error" && <Button variant="accent" icon="edit" onClick={() => setEditing(true)}>Своя цена</Button>}><div className="sm-panel-body"><Corridor region={{ ...region, effective_approved_rrp: region.effective.rrp }} /></div></Panel>
      <div className="ip-grid k2"><Panel title="Расчёт цены" sub="Шаги от закупочной стоимости до новой цены">
        <ol className="ip-explain sm-panel-body">{costs.map(([key, title, hint], i) => <li className={key === "final" ? "st final" : "st"} key={key}><span className="n">{i + 1}</span><div><b>{title}</b><p className="small muted">{hint}</p></div><strong className="v">{priceText(key === "final" ? region.effective.rrp : region[key])} ₽</strong></li>)}</ol>
      </Panel><Panel title="Цены для разных покупателей" sub="Оптовые цены рассчитаны по скидкам выбранного региона"><div className="sm-panel-body"><PriceLadder region={region} />
        <dl className="sm-product-params">{[["base_analog", "Коэффициент аналога"], ["base_exclusive", "Маржа эксклюзива"], ["minimum_margin", "Минимальная маржа"], ["quantity_eurotruck", "Количество в еврофуре (справочно)"]].map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{region[key] == null ? "—" : ["base_exclusive", "minimum_margin"].includes(key) ? `${(Number(region[key]) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%` : priceText(region[key])}</dd></div>)}</dl>
      </div></Panel></div>
      {canEdit && <ParameterEditor key={`parameters-${region.id}`} snapshotId={snapshotId} row={region} onSaved={onSaved} />}
    </>}
    {tab === "competitors" && <Panel title="Конкуренты в расчёте" sub="Пригодные цены и регионы аналогов"><div className="ip-stack sm-panel-body">
      {!data.competitors.length && <div className="ip-empty"><b>Данных конкурентов нет</b></div>}
      <div className="ip-cards">{(data.competitor_cards || []).map(card => <CompetitorCard key={card.group_key} card={card} editable={canEdit} onChangeMode={(item, mode) => setCompetitorTarget({ card: item, mode })} />)}</div>
      {competitorTarget && <SelectionModal target={competitorTarget} snapshotId={snapshotId} productId={productId} revision={data.edit_revision} onClose={() => setCompetitorTarget(null)} onSaved={onSaved} />}
      <CompetitorEditor snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} />
    </div></Panel>}
    {tab === "market" && <><MarketAssortment snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} /><Panel title="Настроить участие в расчёте"><div className="sm-panel-body"><CompetitorEditor expanded snapshotId={snapshotId} productId={productId} canEdit={canEdit} onSaved={onSaved} /></div></Panel></>}
    {tab === "own" && <OwnAssortment snapshotId={snapshotId} productId={productId} onOpenProduct={onOpenProduct} />}
    <Drawer open={editing} onClose={() => setEditing(false)} title="Своя цена" sub={`${data.nom} · ${region.sale_region}`}><PriceEditor key={region.id} snapshotId={snapshotId} row={region} onSaved={onSaved} /></Drawer>
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
  return <details open={expanded || undefined}><summary>Состав аналогов и история</summary>{confirmation}
    <p>Доступны активные позиции конкурентов с той же классификацией. Изменение пересчитывает товар и требует повторного подтверждения ручных цен.</p>
    {error && <p role="alert">{error}</p>}
    {data && <>
      {canEdit && data.editable && <label>Причина изменения аналогов<input value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></label>}
      {!data.items.length && <div className="ip-empty"><b>Нет подходящих позиций</b><span>Проверьте наличие активной классификации товара и конкурентов.</span></div>}
      {data.items.map(item => <p key={item.id}>{item.source} · {/^https?:\/\//i.test(item.url || "") ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a> : item.url} · {names[item.mode]} {item.used_in_snapshot && <span className="ip-tag green">Учтён в расчёте</span>}
        {canEdit && data.editable && <select aria-label={`Участие аналога ${item.id}`} value={item.mode} disabled={busy || !reason.trim() || data.page !== page} onChange={e => change(item.id, e.target.value)}>{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</p>)}
      <button disabled={page <= 1 || busy} onClick={() => setPage(page - 1)}>Назад</button> {page} / {data.pages} <button disabled={page >= data.pages || busy} onClick={() => setPage(page + 1)}>Далее</button>
      <h4>Последние 50 изменений</h4>{data.changes.map(item => <p key={item.id}>Аналог {item.override__product_key_competitor} · {names[item.selection_mode]} · {item.changed_by__username} · {new Date(item.date_add).toLocaleString("ru-RU")} · {item.reason}</p>)}
    </>}
  </details>;
}

function OwnAssortment({ snapshotId, productId, onOpenProduct }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/own/`, { signal: controller.signal }).then(r => setData(r.data))
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить собственную линейку."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  return <Panel title="Наша линейка" sub="Товары выбранного расчёта с той же классификацией. Цены без НДС."><div className="sm-panel-body">
    {error && <p role="alert">{error}</p>}{!data && !error && <p className="sm-iprice-loading" role="status">Загружаем линейку…</p>}
    {data?.unavailable_reason && <p role="status">{data.unavailable_reason}</p>}
    {data && !data.results.length && !data.unavailable_reason && <div className="ip-empty"><b>Других товаров этой классификации нет</b></div>}
    <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Товар</th><th>Подкатегория</th><th>Свойства</th><th>Способ расчёта</th><th className="num">У конкурентов</th><th className="num">Новая цена</th></tr></thead><tbody>{data?.results.map(item => <tr key={item.snapshot_product_id}><td><button className="ip-linkbtn" onClick={() => onOpenProduct?.(item.snapshot_product_id)}>{item.name}</button><span className="sub">{item.code_1c}</span></td><td>{item.subcategory_type || "—"}</td><td>{[item.material, item.color, item.modification].filter(Boolean).join(", ") || "—"}</td><td>{item.pricing_method === "analog" ? "По рынку" : "Эксклюзив"}</td><td className="num">{priceText(item.market_price)}</td><td className="num">{priceText(item.final_price)}</td></tr>)}</tbody></table></div>
  </div></Panel>;
}

function MarketAssortment({ snapshotId, productId, canEdit, onSaved }) {
  const [target, setTarget] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [onlyFree, setOnlyFree] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/products/${productId}/market/`, { signal: controller.signal }).then(r => setData(r.data))
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить рынок категории."); });
    return () => controller.abort();
  }, [snapshotId, productId]);
  const cards = (data?.results || []).filter(card => !onlyFree || !card.is_used_in_snapshot);
  return <Panel title="Рынок категории" sub="Активная классификация конкурентов; цены отбираются на дату расчёта. Эти карточки сами по себе не добавляют аналог в расчёт." actions={<label className="ip-check small"><input type="checkbox" checked={onlyFree} onChange={e => setOnlyFree(e.target.checked)} />Только неучтённые</label>}>
    <div className="ip-stack sm-panel-body">{error && <p role="alert">{error}</p>}{!data && !error && <p className="sm-iprice-loading" role="status">Загружаем рынок категории…</p>}{data?.unavailable_reason && <p>{data.unavailable_reason}</p>}
      {data && <p className="small muted">Всего карточек: {data.counts.cards} · учтены в расчёте: {data.counts.used_in_snapshot ?? 0}</p>}
      {data && !cards.length && !data.unavailable_reason && <div className="ip-empty"><b>Нет товаров для выбранного отбора</b></div>}
      <div className="ip-cards">{cards.map(card => <CompetitorCard key={JSON.stringify(card.group_key)} card={card} editable={canEdit && data.editable} onChangeMode={(card, mode) => setTarget({ card, mode })} />)}</div>
      {target && <SelectionModal target={target} snapshotId={snapshotId} productId={productId} revision={data.edit_revision} onClose={() => setTarget(null)} onSaved={onSaved} />}
    </div>
  </Panel>;
}
