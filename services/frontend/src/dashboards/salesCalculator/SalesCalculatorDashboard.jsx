import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { RefreshInfoTooltip } from "../../components/RefreshInfoTooltip";
import { SalesProductImage } from "./SalesProductImage";
import "./sales_calculator.css";

const ROOT = "/v1/sales-calculator/";
const TYPES = { auto: "Авто", retail: "Розница", small: "Мелкий опт", medium: "Средний опт", large: "Крупный опт" };
const price = value => value == null ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 20 });
const numericColumn = key => key === "code" || key === "quantity" || /_(net|gross)$/.test(key);
const money = (value, digits = 2) => value == null ? "—" : Number(value).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const count = value => value == null ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 3 });
const date = value => value ? new Date(value).toLocaleString("ru-RU") : "Нет данных";
const errorText = error => typeof error.response?.data?.detail === "string" ? error.response.data.detail : Array.isArray(error.response?.data) ? error.response.data.join(". ") : "Не удалось выполнить действие. Попробуйте ещё раз.";
const FILTERS = { name_1c: "Наименование 1С", nom_view: "Вид", nom_category: "Категория", nom_group: "Группа продукции 1С", color: "Цвет", material: "Материал", sam: "САМ", our_offers: "Наши предложения" };
const article = value => value == null ? "—" : String(value).padStart(11, "0");
function priceBand(key, config) {
  const tier = key.replace(/_(net|gross)$/, "");
  const index = ["retail", "small", "medium", "large"].indexOf(tier);
  if (index < 0) return null;
  const bounds = [0, ...config.thresholds];
  return index === 3 ? `Свыше ${count(bounds[index])} руб.` : `${count(bounds[index])}–${count(bounds[index + 1])} руб.`;
}

function Modal({ title, children, onClose, wide = false, personal = false }) {
  const root = useRef(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    root.current?.querySelector("button, input, select")?.focus();
    const key = event => {
      if (event.key === "Escape") closeRef.current();
      if (event.key !== "Tab") return;
      const nodes = [...root.current.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex='0']")].filter(n => n.offsetParent !== null);
      if (!nodes.length) return;
      if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1).focus(); }
      else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0].focus(); }
    };
    document.addEventListener("keydown", key);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", key); previous?.focus(); };
  }, []);
  return createPortal(<div className="sc-overlay" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><section ref={root} role="dialog" aria-modal="true" aria-label={title} className={`sc-modal ${wide ? "sc-modal--wide" : ""}`}><header><div>{personal && <small className="sc-personal-eyebrow">Персональная настройка</small>}<h2>{title}</h2>{personal && <p className="sc-personal-description">Настройки сохраняются персонально для вашей учётной записи и применяются при следующих входах.</p>}</div><button type="button" aria-label="Закрыть" onClick={onClose}>×</button></header>{children}</section></div>, document.body);
}

function LogisticsTooltip() {
  const [position, setPosition] = useState(null);
  const show = event => {
    const rect = event.currentTarget.getBoundingClientRect();
    setPosition({ left: Math.max(12, Math.min(rect.left, window.innerWidth - 332)), top: Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 150)) });
  };
  useEffect(() => {
    const hide = () => setPosition(null);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => { window.removeEventListener("scroll", hide, true); window.removeEventListener("resize", hide); };
  }, []);
  return <><span className="sc-info-icon" tabIndex={0} role="button" aria-label="О расчёте логистики" aria-describedby={position ? "sc-logistics-tooltip" : undefined} onMouseEnter={show} onMouseLeave={() => setPosition(null)} onFocus={show} onBlur={() => setPosition(null)} onClick={show} onKeyDown={e => { if (e.key === "Escape") setPosition(null); if (e.key === "Enter" || e.key === " ") { e.preventDefault(); show(e); } }}><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8" /><path d="M10 9v5" /><circle cx="10" cy="6" r=".7" fill="currentColor" stroke="none" /></svg></span>{position && createPortal(<div id="sc-logistics-tooltip" className="sc-info-tooltip" role="tooltip" style={position}>Расчёт по заполненным данным источника. Для части позиций вес или количество на паллете могут быть не указаны.</div>, document.body)}</>;
}

function Pagination({ page, pages, pageSize, setPage, setPageSize }) {
  return <div className="sc-pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Назад</button><span>{page} / {pages}</span><button disabled={page === pages} onClick={() => setPage(page + 1)}>Вперёд</button><label>На странице <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>{[12, 24, 48].map(size => <option key={size}>{size}</option>)}</select></label></div>;
}

function Details({ row, field, config, labels, title }) {
  const entries = config[field].filter(k => row[field]?.[k] != null);
  if (!entries.length) return <span className="sc-muted">—</span>;
  return <details><summary>{title || entries.slice(0, 2).map(k => `${labels[k]}: ${row[field][k]}`).join(" · ")}{!title && <span className="sc-more">Подробнее</span>}</summary><dl className="sc-detail-list">{entries.map(k => <div key={k}><dt title={labels[k]}>{labels[k]}</dt><dd title={String(row[field][k])}>{row[field][k]}</dd></div>)}</dl></details>;
}

function StockDetails({ stocks, warehouses }) {
  if (stocks == null) return <p className="sc-muted">Остатки временно недоступны</p>;
  const entries = warehouses.map(name => [name, Number(stocks[name])]).filter(([, value]) => Number.isFinite(value) && value > 0);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return <details className="sc-stock-details"><summary>Остаток: <strong>{count(total)} шт.</strong> · По складам</summary><dl className="sc-detail-list">{entries.map(([name, value]) => <div key={name}><dt title={name}>{name}</dt><dd title={`${count(value)} шт.`}>{count(value)} шт.</dd></div>)}</dl>{!entries.length && <p className="sc-muted">{warehouses.length ? "Нет положительных остатков по выбранным складам" : "Склады не выбраны"}</p>}</details>;
}

function PreferenceSelect({ label, field, choices, draft, setDraft }) {
  const labels = typeof choices[0] === "string" ? Object.fromEntries(choices.map(x => [x, x])) : choices;
  const reverse = Object.fromEntries(Object.entries(labels).map(([key, value]) => [value, key]));
  return <DashboardMultiSelect floating label={label} options={Object.values(labels)} selected={draft[field].map(k => labels[k]).filter(Boolean)} onApply={values => setDraft({ ...draft, [field]: values.map(v => reverse[v]) })} emptyLabel="Не выбрано" />;
}

function Settings({ metadata, config, regions, onSave, onClose }) {
  const [draft, setDraft] = useState(config);
  const [tab, setTab] = useState("simple");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const field = (name, value) => setDraft({ ...draft, [name]: value });
  async function save() {
    setBusy(true); setError("");
    try { const { data } = await api.put(ROOT + "settings/", draft); onSave(data); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <Modal personal title="Настройки калькулятора" onClose={onClose}><div className="sc-modal-body">
    {error && <div role="alert" className="sc-notice sc-error">{error}</div>}
    <section><h3>Основные настройки</h3><div className="sc-settings-grid">
      <label>Регион продажи<select value={draft.region} onChange={e => field("region", e.target.value)}><option value="">Выберите регион</option>{regions.map(r => <option key={r}>{r}</option>)}</select></label>
      <label>НДС<select value={draft.vat} onChange={e => field("vat", Number(e.target.value))}><option value={22}>22%</option><option value={0}>0%</option></select></label>
    </div></section>
    <section><h3>Характеристики и логистика</h3><p className="sc-muted">Выбранный набор используется на экране и в Excel / PDF.</p><div className="sc-settings-grid"><PreferenceSelect label="Характеристики" field="characteristics" choices={metadata.characteristics} draft={draft} setDraft={setDraft} /><PreferenceSelect label="Логистика" field="logistics" choices={metadata.logistics} draft={draft} setDraft={setDraft} /></div></section>
    <section><h3>Склады для остатков</h3><p className="sc-muted">Остатки отображаются справочно по каждому складу.</p><PreferenceSelect label="Склады" field="warehouses" choices={metadata.warehouses} draft={draft} setDraft={setDraft} /></section>
    <section><h3>Пороги типов цен · без НДС</h3><div className="sc-settings-grid">{["Розница → Мелкий опт", "Мелкий → Средний опт", "Средний → Крупный опт"].map((label, i) => <label key={label}>{label}, руб.<input type="number" min="0" value={draft.thresholds[i]} onChange={e => field("thresholds", draft.thresholds.map((x, j) => i === j ? e.target.value : x))} /></label>)}<label>Порог предупреждения, руб.<input type="number" value={draft.warning_threshold} onChange={e => field("warning_threshold", e.target.value)} /></label></div><p className="sc-muted">Переход только при строгом превышении.</p></section>
    <section><h3>Столбцы таблицы и выгрузки</h3><div className="sc-tabs"><button className={tab === "simple" ? "is-active" : ""} onClick={() => setTab("simple")}>Прайс</button><button className={tab === "full" ? "is-active" : ""} onClick={() => setTab("full")}>Калькулятор</button></div><PreferenceSelect label="Столбцы" field={tab + "_columns"} choices={metadata[tab + "_columns"]} draft={draft} setDraft={setDraft} /></section>
  </div><footer><button onClick={onClose} disabled={busy}>Отмена</button><button className="sc-primary" onClick={save} disabled={busy}>{busy ? "Сохранение…" : "Сохранить"}</button></footer></Modal>;
}

function ProductPicker({ products, items, config, metadata, onAdd, onClose }) {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState(() => new Set(items.map(x => String(x.product_key))));
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const normalized = query.trim().toLocaleLowerCase("ru");
  const visible = useMemo(() => products.filter(p => (!normalized || [article(p.code), p.name_1c, p.name, p.price_list].some(x => String(x || "").toLocaleLowerCase("ru").includes(normalized))) && Object.entries(filters).every(([k, values]) => !values.length || values.includes(p[k]))).sort((a, b) => sort === "code" ? a.code - b.code : String(a.name || a.name_1c || "").localeCompare(String(b.name || b.name_1c || ""), "ru")), [products, normalized, filters, sort]);
  const pages = Math.max(1, Math.ceil(visible.length / pageSize));
  const currentPage = Math.min(page, pages);
  const toggle = key => setSelected(old => { const next = new Set(old); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  return <Modal title="Выбор товаров" onClose={onClose} wide><div className="sc-modal-body"><input className="sc-search" placeholder="Поиск по артикулу, наименованию 1С, наименованию на сайте или номенклатуре прайс-листа" aria-label="Поиск товаров" value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} /><div className="sc-picker-filters">{Object.entries(FILTERS).map(([key, label]) => <DashboardMultiSelect floating key={key} label={label} options={[...new Set(products.map(p => p[key]).filter(Boolean))].sort()} selected={filters[key] || []} onApply={value => { setFilters({ ...filters, [key]: value }); setPage(1); }} />)}</div>
    <div className="sc-toolbar"><span>Найдено: {visible.length}</span><div className="sc-toolbar-right"><label><input type="checkbox" checked={!!visible.length && visible.every(p => selected.has(String(p.product_key)))} onChange={e => setSelected(old => { const next = new Set(old); visible.forEach(p => e.target.checked ? next.add(String(p.product_key)) : next.delete(String(p.product_key))); return next; })} /> Выбрать найденные</label><select value={sort} onChange={e => setSort(e.target.value)} aria-label="Сортировка"><option value="name">По наименованию</option><option value="code">По коду 1С</option></select><button onClick={() => { setFilters({}); setQuery(""); setPage(1); }}>Сбросить фильтры</button></div></div>
    <div className="sc-products">{visible.slice((currentPage - 1) * pageSize, currentPage * pageSize).map(p => <article key={p.product_key} className={selected.has(String(p.product_key)) ? "is-selected" : ""}><label className="sc-product-check"><input aria-label={`Выбрать ${p.name || p.code}`} type="checkbox" checked={selected.has(String(p.product_key))} onChange={() => toggle(String(p.product_key))} /></label>{p.image ? <SalesProductImage src={p.image} caption={p.name || p.name_1c} /> : <div className="sc-no-photo">Нет фото</div>}<h3>{p.name || p.name_1c}</h3>{p.url && <a className="sc-product-link" href={p.url} target="_blank" rel="noreferrer">Посмотреть на сайте</a>}<div className="sc-muted">Артикул: {article(p.code)}</div><div className="sc-muted">{p.characteristics?.dimensions} {p.characteristics?.weight ? ` · ${p.characteristics.weight} кг` : ""}</div><div className="sc-product-details"><Details row={p} field="characteristics" title="Характеристики" config={config} labels={metadata.characteristics} /><Details row={p} field="logistics" title="Логистика" config={config} labels={metadata.logistics} /></div><StockDetails stocks={p.stocks} warehouses={config.warehouses} /><button className={selected.has(String(p.product_key)) ? "sc-primary" : ""} onClick={() => toggle(String(p.product_key))}>{selected.has(String(p.product_key)) ? "Выбрано" : "Добавить"}</button></article>)}</div>
    {!visible.length && <p className="sc-empty">Товары не найдены. Измените поиск или фильтры.</p>}
  </div><Pagination page={currentPage} pages={pages} pageSize={pageSize} setPage={setPage} setPageSize={setPageSize} /><footer><span>Выбрано: {selected.size}</span><button onClick={onClose}>Отмена</button><button className="sc-primary" onClick={() => onAdd([...selected])}>Добавить выбранные</button></footer></Modal>;
}

export function SalesCalculatorDashboard() {
  const dashboardRef = useRef(null);
  useEffect(() => {
    const element = dashboardRef.current;
    const fit = () => element?.style.setProperty("--sc-height", `${Math.max(320, window.innerHeight - element.getBoundingClientRect().top - 12)}px`);
    fit();
    const observer = new ResizeObserver(fit);
    if (element?.parentElement) observer.observe(element.parentElement);
    window.addEventListener("resize", fit);
    return () => { observer.disconnect(); window.removeEventListener("resize", fit); };
  }, []);
  const [metadata, setMetadata] = useState(null);
  const [config, setConfig] = useState(null);
  const [catalog, setCatalog] = useState({ products: [], regions: [], region: "" });
  const [state, setState] = useState({});
  const [items, setItems] = useState([]);
  const [mode, setMode] = useState("simple");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visibleItems = items.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const [modal, setModal] = useState(null);
  const [result, setResult] = useState(null);
  const [resultIdentity, setResultIdentity] = useState("");
  const [notice, setNotice] = useState(null);
  const setMessage = useCallback((text, kind = "success") => setNotice(text ? { text, kind } : null), []);
  const message = notice?.text;
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 30000);
    return () => clearTimeout(timer);
  }, [notice]);
  const [calcError, setCalcError] = useState("");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkType, setBulkType] = useState("auto");
  const catalogSequence = useRef(0);
  const wasRunning = useRef(false);
  const publishedAt = useRef(null);
  const regionRef = useRef("");
  const calculationIdentity = JSON.stringify([items, config, catalog]);
  const calculating = busy || resultIdentity !== calculationIdentity;
  async function loadCatalog(region = "") {
    const sequence = ++catalogSequence.current;
    const { data } = await api.get(ROOT + "products/", { params: { region } });
    if (sequence !== catalogSequence.current) return;
    setCatalog(data); regionRef.current = data.region; setState(data.state);
    publishedAt.current = data.state.finished_at || null;
  }
  useEffect(() => {
    let active = true;
    api.get(ROOT + "settings/").then(({ data }) => { if (active) { setMetadata(data); setConfig(data.config); loadCatalog(data.config.region).catch(e => setMessage(errorText(e), "error")); } }).catch(e => setMessage(errorText(e), "error"));
    return () => { active = false; catalogSequence.current = -1; };
  }, [setMessage]);
  useEffect(() => {
    let active = true;
    const timer = setInterval(async () => {
      try {
        const { data } = await api.get(ROOT + "refresh/");
        if (!active) return;
        setState(data);
        if (!data.running && (wasRunning.current || (data.finished_at && data.finished_at !== publishedAt.current))) {
          setMessage(data.status === "success" ? (data.error || "Коммерческий прайс обновлён") : data.error, data.status !== "success" ? "error" : data.error ? "warning" : "success");
          await loadCatalog(regionRef.current);
        }
        wasRunning.current = data.running;
      } catch { /* Existing report remains visible during a short network outage. */ }
    }, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [setMessage]);
  useEffect(() => {
    let active = true;
    if (!config || !catalog.region) return;
    const timer = setTimeout(async () => {
      setBusy(true); setCalcError("");
      try {
        const { data } = await api.post(ROOT + "calculate/", { items, region: catalog.region });
        if (active) { setResult(data); setResultIdentity(calculationIdentity); }
      } catch (e) { if (active) { setCalcError(errorText(e)); setResult(null); } }
      finally { if (active) setBusy(false); }
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [items, config, catalog, calculationIdentity]);
  const productsByKey = useMemo(() => new Map(catalog.products.map(p => [String(p.product_key), p])), [catalog.products]);
  const resultsByKey = useMemo(() => new Map((result?.rows || []).map(p => [String(p.product_key), p])), [result]);
  function updateItem(key, changes) { setItems(old => old.map(i => String(i.product_key) === String(key) ? { ...i, ...changes } : i)); }
  function add(keys) {
    setItems(old => { const have = new Set(old.map(i => String(i.product_key))); return [...old, ...keys.filter(k => !have.has(k)).map(k => ({ product_key: k, quantity: 1, price_type: "auto" }))]; });
    setModal(null);
  }
  async function refresh() {
    try { const { data } = await api.post(ROOT + "refresh/"); wasRunning.current = true; setState(data); setMessage("Обновляем прайс 1С и остатки…"); }
    catch (e) { if (e.response?.status === 409) { setState(e.response.data); wasRunning.current = true; setMessage("Обновление уже выполняется", "warning"); } else setMessage(errorText(e), "error"); }
  }
  async function exportFile(format) {
    setExporting(true);
    try {
      const { data } = await api.post(ROOT + "export/", { items, region: catalog.region, mode, format }, { responseType: "blob", timeout: 600000 });
      const url = URL.createObjectURL(data); const link = document.createElement("a"); link.href = url; link.download = `${mode === "simple" ? "Прайс" : "Предложение"}.${format}`; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) {
      let detail;
      try { const body = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()) : e.response?.data; detail = typeof body?.detail === "string" ? body.detail : Array.isArray(body) ? body.join(". ") : null; } catch { /* Non-JSON proxy errors use the fallback below. */ }
      setMessage(detail || `Не удалось подготовить ${format.toUpperCase()}${e.response?.status ? ` (HTTP ${e.response.status})` : ""}. Повторите загрузку; если ошибка сохранится, передайте администратору время запроса.`, "error");
    }
    finally { setExporting(false); }
  }
  const columns = (config?.[mode + "_columns"] || []).filter(key => key !== "product_key");
  function cell(key, item, row, calculated) {
    if (key === "name") return row.price_list_name || row.name || "—";
    if (key === "code") return article(row.code);
    if (key === "image") return row.image ? <SalesProductImage className="sc-table-image" src={row.image} caption={row.name || row.name_1c} /> : "—";
    if (key === "quantity") return <input className="sc-quantity" aria-label={`Количество ${row.name}`} type="number" min="0.001" step="any" value={item.quantity} onChange={e => updateItem(item.product_key, { quantity: e.target.value })} />;
    if (key === "price_type") return <select aria-label={`Тип цены ${row.name}`} value={item.price_type} onChange={e => updateItem(item.product_key, { price_type: e.target.value })}>{Object.entries(TYPES).map(([value, label]) => <option key={value} value={value}>{label}{value === "auto" && result ? ` · ${TYPES[result.automatic_type]}` : ""}</option>)}</select>;
    if (key === "characteristics" || key === "logistics") return <Details row={row} field={key} config={config} labels={metadata[key]} />;
    if (key === "url") return row.url ? <a href={row.url} target="_blank" rel="noreferrer">Посмотреть</a> : "—";
    if (key.startsWith("sum_")) return money(calculated?.[key]);
    if (key.startsWith("unit_") || key.endsWith("_net") || key.endsWith("_gross")) return price(calculated?.[key]);
    return row[key] || "—";
  }
  return <div ref={dashboardRef} className="sc-dashboard" data-dashboard-type="commercial-price"><header className="sc-topbar"><div><h1>Коммерческий прайс</h1></div><nav><button onClick={() => setModal("settings")} disabled={!config}>Настройки</button><RefreshInfoTooltip sections={[{ title: "Прайс 1С", content: date(state.price_updated_at) }, { title: "Остатки", content: date(state.stock_updated_at) }]}><button onClick={refresh} disabled={state.running || !catalog.can_refresh}>{state.running ? "Обновление…" : "Обновить"}</button></RefreshInfoTooltip></nav></header>
    {message && <div className="sc-toast-stack"><div className={`sc-toast sc-toast--${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}><span>{message}</span><button aria-label="Закрыть уведомление" onClick={() => setMessage("")}>×</button></div></div>}
    {catalog.stale && <div className="sc-notice">Показан последний доступный прайс. Данные за сегодня ещё не обновлены.</div>}
    <div className="sc-toolbar"><div className="sc-tabs"><button className={mode === "simple" ? "is-active" : ""} onClick={() => setMode("simple")}>Прайс</button><button className={mode === "full" ? "is-active" : ""} onClick={() => setMode("full")}>Калькулятор</button></div><span className="sc-region">Регион: {catalog.region || "не выбран"} · НДС {config?.vat ?? 22}%</span></div>
    {!config ? <p>Загрузка настроек…</p> : <div className="sc-workspace"><section className="sc-panel sc-composition"><h2>Состав расчёта</h2><div className="sc-toolbar"><button className="sc-primary" onClick={() => setModal("products")} disabled={!catalog.products.length}>＋ Добавить товар</button><button onClick={() => { setItems([]); setSelected(new Set()); }} disabled={!items.length}>Очистить</button><div className="sc-toolbar-right">{mode === "full" && <button title="Изменить тип цен вручную для выбранных позиций" onClick={() => { setSelectionMode(!selectionMode); setSelected(new Set()); }}>{selectionMode ? "Завершить выбор" : "Выбрать позиции"}</button>}{mode === "full" && selectionMode && <><select aria-label="Тип цены для выбранных" value={bulkType} onChange={e => setBulkType(e.target.value)}>{Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><button disabled={!selected.size} onClick={() => setItems(old => old.map(i => selected.has(String(i.product_key)) ? { ...i, price_type: bulkType } : i))}>Применить к выбранным</button></>}</div></div>
      {calcError && <div className="sc-notice sc-error" role="alert">{calcError}</div>}
      {!items.length ? <div className="sc-empty"><h3>Добавьте товары в расчёт</h3><p>Выберите продукцию, чтобы посмотреть цены или рассчитать заказ.</p>{!catalog.products.length && <p>Витрина пока пуста. Обновите прайс или обратитесь к администратору.</p>}</div> : <div className="sc-table-scroll" aria-busy={calculating}><table className="sc-table"><thead><tr><th className="sc-remove-cell" aria-label="Удаление" />{mode === "full" && selectionMode && <th><input type="checkbox" aria-label="Выбрать все позиции" checked={!!items.length && items.every(i => selected.has(String(i.product_key)))} onChange={e => setSelected(e.target.checked ? new Set(items.map(i => String(i.product_key))) : new Set())} /></th>}{columns.map(k => <th key={k} className={(k === "name" || k === "name_1c") ? "sc-name-cell" : undefined}>{k === "code" ? "Артикул" : metadata[mode + "_columns"][k]}{mode === "simple" && priceBand(k, config) && <small className="sc-price-band">{priceBand(k, config)}</small>}</th>)}</tr></thead><tbody>{visibleItems.map(item => { const key = String(item.product_key); const row = productsByKey.get(key); const calculated = resultsByKey.get(key); return <tr key={key}><td className="sc-remove-cell"><button aria-label="Удалить товар" onClick={() => setItems(old => old.filter(i => String(i.product_key) !== key))}>×</button></td>{mode === "full" && selectionMode && <td><input type="checkbox" aria-label={`Выбрать ${row?.name || key}`} checked={selected.has(key)} onChange={() => setSelected(old => { const next = new Set(old); if (next.has(key)) next.delete(key); else next.add(key); return next; })} /></td>}{row ? columns.map(k => <td key={k} className={numericColumn(k) ? "sc-numeric-cell" : (k === "name" || k === "name_1c") ? "sc-name-cell" : undefined}>{cell(k, item, row, calculated)}</td>) : <td colSpan={columns.length}>Товар {key} недоступен в этом регионе</td>}</tr>; })}</tbody></table></div>}
      {!!items.length && <Pagination page={currentPage} pages={pages} pageSize={pageSize} setPage={setPage} setPageSize={setPageSize} />}
    </section><aside className="sc-panel sc-summary"><h2>{mode === "full" ? "Итоги расчёта" : "Выбранные товары"}</h2><div className="sc-counts"><div>Позиций<strong>{items.length}</strong>товаров</div><div>Количество<strong>{result ? count(result.quantity) : "—"}</strong>шт.</div></div>{mode === "full" && result && <><dl><div><dt>Сумма без НДС</dt><dd>{money(result.net)}</dd></div><div><dt>НДС ({config.vat}%)</dt><dd>{money(result.vat)}</dd></div><div className="sc-total"><dt>Итого с НДС</dt><dd>{money(result.gross)}</dd></div></dl><section><h3>Ценовой уровень</h3><strong>{result.manual ? "Ручной режим" : TYPES[result.automatic_type]}</strong>{result.manual && <p>Расчётный тип: {TYPES[result.automatic_type]}</p>}{result.next_type && <p className="sc-muted">До уровня «{TYPES[result.next_type]}»: {money(result.next_gap)}{Number(result.next_gap) === 0 ? " — переход при превышении порога" : ""}</p>}</section>{result.warning && <div className="sc-notice">Сумма превышает стандартный диапазон прайс-листа {money(config.warning_threshold)} руб.</div>}</>}{result && <section><h3 className="sc-logistics-title">Логистика справочно <LogisticsTooltip /></h3><dl><div><dt>Общий вес, кг</dt><dd>{money(result.logistics.weight, 0)}{result.logistics_missing?.weight > 0 && <small className="sc-partial">Без данных: {result.logistics_missing.weight} поз.</small>}</dd></div><div><dt>Паллето-мест</dt><dd>{count(result.logistics.pallets)}{result.logistics_missing?.pallets > 0 && <small className="sc-partial">Без данных: {result.logistics_missing.pallets} поз.</small>}</dd></div></dl></section>}<section><h3>Экспорт</h3><div className="sc-toolbar"><button className="sc-primary" disabled={exporting || calculating || !result?.rows.length || !columns.length} onClick={() => exportFile("xlsx")}>Excel</button><button disabled={exporting || calculating || !result?.rows.length || !columns.length} onClick={() => exportFile("pdf")}>PDF</button></div>{exporting && <p role="status">Готовим документ и фотографии…</p>}</section></aside></div>}
    {modal === "settings" && <Settings metadata={metadata} config={{ ...config, region: catalog.region || config.region }} regions={catalog.regions} onClose={() => setModal(null)} onSave={data => { setConfig(data); setModal(null); loadCatalog(data.region).catch(e => setMessage(errorText(e), "error")); }} />}
    {modal === "products" && <ProductPicker metadata={metadata} products={catalog.products} items={items} config={config} onAdd={add} onClose={() => setModal(null)} />}
  </div>;
}
