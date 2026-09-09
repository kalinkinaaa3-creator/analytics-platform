import { cloneElement, Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Pie, PieChart, Tooltip, XAxis, YAxis } from "recharts";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { CollisionSafeChartLabel } from "../../components/CollisionSafeChartLabel";
import { DateRangePicker } from "../../components/DateRangePicker";
import { downloadContextGoals, exportContextReport, getContextOptions, getContextRefreshState, getContextReport, startContextRefresh, uploadContextGoals } from "../../api/contextAnalyticsApi";
import "../spinner.css";
import "../seoAnalytics/seo_analytics.css";
import "./context_analytics.css";

const COLORS = ["#536f50", "#d8bd86", "#89939c", "#9a625d", "#7d6a92", "#3f8a88", "#a5a99f"];
const METRIC_COLORS = { clicks: "#cb922d", leads: "#587453", cost: "#668a98", cpl: "#9a625d", cr: "#7d6a92" };
const PAGES = [["summary", "Сводно", "Сводные данные", "▤"], ["weekly", "Динамика", "Понедельная динамика", "↝"], ["lead_structure", "Структура лидов", "Структура лидов", "◉"], ["conversions", "Конверсии", "Конверсии по кампаниям", "◎"], ["criteria", "Ключевые слова", "Детализация по ключевым словам", "⌕"], ["demography", "Пол и возраст", "Детализация по полу и возрасту", "♙"], ["devices", "Устройства", "Детализация по устройствам", "◇"], ["calltouch", "Calltouch", "Данные Calltouch", "☎︎"]];
const today = new Date();
const iso = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const defaults = () => ({ date_from: `${today.getFullYear()}-01-01`, date_to: iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)), campaigns: [], campaign_types: [], ad_groups: [], criteria: [], day_types: ["workdays", "weekends"] });
const GROUP_FILTER_PAGES = new Set(["summary", "weekly", "lead_structure", "conversions", "criteria", "demography", "devices"]);
let summaryTablePopupOpen = false;
let leadStructureSelectedGoals = [];
const number = (value, digits = 0) => value === null || value === undefined ? "—" : new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value));
const money = (value) => value === null || value === undefined ? "—" : `${number(value, 2)} ₽`;
const wholeMoney = (value) => value === null || value === undefined ? "—" : `${number(value)} ₽`;
const percent = (value, digits = 2) => value === null || value === undefined ? "—" : `${number(value, digits)}%`;
const formatted = (key, value) => ["cost", "cpc", "cpl"].includes(key) ? money(value) : ["ctr", "cr", "bounce_rate"].includes(key) ? percent(value) : ["avg_impression_position", "avg_click_position"].includes(key) ? number(value, 2) : number(value);
const rubleAxis = (value) => { const amount = Number(value || 0); return Math.abs(amount) >= 1000000 ? `${number(amount / 1000000, 1)} млн ₽` : Math.abs(amount) >= 1000 ? `${number(amount / 1000, 1)} тыс. ₽` : `${number(amount)} ₽`; };
const wholeRubleAxis = (value) => { const amount = Number(value || 0); return Math.abs(amount) >= 1000000 ? `${number(amount / 1000000)} млн ₽` : Math.abs(amount) >= 1000 ? `${number(amount / 1000)} тыс. ₽` : `${number(amount)} ₽`; };
const axisFormatted = (key, value) => ["cost", "cpc", "cpl"].includes(key) ? wholeRubleAxis(value) : ["ctr", "cr", "bounce_rate"].includes(key) ? percent(value, 0) : formatted(key, value);
const cardMoneySize = (value) => { const length = wholeMoney(value).length; return length > 18 ? 14 : length > 15 ? 16 : length > 12 ? 19 : 24; };
const dateLabel = (value) => { const date = new Date(`${String(value).slice(0, 10)}T00:00:00`); return Number.isNaN(date.getTime()) ? String(value || "") : date.toLocaleDateString("ru-RU"); };
const matchesDayMode = (value, modes = []) => { const weekday = value.getDay(); return modes.length !== 1 || (modes[0] === "workdays" ? weekday >= 1 && weekday <= 5 : weekday === 0 || weekday === 6); };
const weekLabel = (value, limit = "") => { const start = new Date(`${String(value).slice(0, 10)}T00:00:00`); if (Number.isNaN(start.getTime())) return String(value || ""); const end = new Date(start); end.setDate(end.getDate() + 6); if (limit) { const maximum = new Date(`${String(limit).slice(0, 10)}T00:00:00`); if (!Number.isNaN(maximum.getTime()) && maximum < end) end.setTime(maximum.getTime()); } return `${start.toLocaleDateString("ru-RU")} — ${end.toLocaleDateString("ru-RU")}`; };
const errorText = (error, fallback) => error?.response?.data?.file || error?.response?.data?.message || error?.response?.data?.detail || fallback;
const save = (blob, name) => { const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url); };

function SafeChartContainer({ children }) {
  const rootRef = useRef(null); const [size, setSize] = useState(null);
  useLayoutEffect(() => { const root = rootRef.current; if (!root) return undefined; const update = (width, height) => { const next = { width: Math.floor(width), height: Math.floor(height) }; if (next.width <= 0 || next.height <= 0) return; setSize((old) => old?.width === next.width && old?.height === next.height ? old : next); }; const measure = () => { const bounds = root.getBoundingClientRect(); update(bounds.width, bounds.height); }; measure(); if (typeof ResizeObserver === "undefined") { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); } const observer = new ResizeObserver(([entry]) => entry && update(entry.contentRect.width, entry.contentRect.height)); observer.observe(root); return () => observer.disconnect(); }, []);
  return <div ref={rootRef} className="seo-safe-chart-container">{size ? cloneElement(children, size) : null}</div>;
}

function Toast({ message, type, close }) {
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(close, 30000); return () => clearTimeout(timer); }, [message, close]);
  return message ? <div className="seo-toast-stack"><div className={`seo-toast seo-toast--${type}`} role={type === "error" ? "alert" : "status"}><span>{message}</span><button type="button" onClick={close}>×</button></div></div> : null;
}

function LoadingBlock() { return <div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>; }

function DayTypeToggle({ value = [], onChange }) {
  const toggle = (key) => { const selected = new Set(value); if (selected.has(key)) { if (selected.size > 1) selected.delete(key); } else selected.add(key); onChange(["workdays", "weekends"].filter((item) => selected.has(item))); };
  return <fieldset className="context-day-types"><legend>Режим</legend><button type="button" className={value.includes("workdays") ? "is-active" : ""} aria-pressed={value.includes("workdays")} onClick={() => toggle("workdays")}>Рабочие</button><button type="button" className={value.includes("weekends") ? "is-active" : ""} aria-pressed={value.includes("weekends")} onClick={() => toggle("weekends")}>Выходные</button></fieldset>;
}

function toggleSeries(setHidden, name) { setHidden((old) => { const next = new Set(old); if (next.has(name)) next.delete(name); else next.add(name); return next; }); }
function InteractiveLegend({ hidden, setHidden, payload, preserveOrder = false }) { return <Legend payload={payload} itemSorter={preserveOrder ? () => 0 : undefined} wrapperStyle={{ cursor: "pointer" }} formatter={(value) => <span className={hidden.has(value) ? "context-legend-hidden" : ""}>{value}</span>} onClick={({ value }) => toggleSeries(setHidden, value)} />; }

function Cards({ summary = {} }) {
  const cards = [["Показы", "impressions"], ["Клики", "clicks"], ["Вернувшиеся", "returning_users"], ["Расход", "cost"], ["Лиды", "leads"], ["CTR", "ctr"], ["CPC", "cpc"], ["CR", "cr"], ["CPL", "cpl"]];
  const help = { returning_users: "Все посетители - Новые посетители по данным Яндекс Метрики.", ctr: "Клики / Показы × 100%", cpc: "Расход / Клики", cr: "Лиды по выбранным целям / Клики × 100%", cpl: "Расход / Лиды по выбранным целям" };
  return <section className="context-kpis">{cards.map(([label, key]) => <article key={key} className={help[key] ? "context-card--has-help" : ""}><span title={help[key] ? undefined : label}>{label}{help[key] && <i className="context-help" tabIndex={0}>i<b role="tooltip">{help[key]}</b></i>}</span><strong className={key === "cost" ? "context-card-value--fit" : ""} style={key === "cost" ? { fontSize: `${cardMoneySize(summary[key])}px` } : undefined} title={key === "cost" ? wholeMoney(summary[key]) : ""}>{key === "cost" ? wholeMoney(summary[key]) : formatted(key, summary[key])}</strong></article>)}</section>;
}

function ChartTooltip({ active, payload = [], label, daily = false, periodEnd = "", valueFormatter = null }) {
  if (!active || !payload.length) return null;
  const shownLabel = label ? (daily ? dateLabel(label) : weekLabel(label, periodEnd)) : payload[0]?.name;
  return <div className="seo-tooltip"><strong>{shownLabel}</strong>{payload.filter((item) => item.value !== undefined && item.value !== null).sort((a, b) => Number(b.value) - Number(a.value)).map((item) => <div key={`${item.dataKey}-${item.name}`}><i style={{ background: item.color || item.fill }} /><span>{item.name}</span><b>{valueFormatter ? valueFormatter(item.value, item) : formatted(item.dataKey, item.value)}</b></div>)}</div>;
}

function mark(rows, key) {
  if (!rows.length) return rows;
  const normalizedRows = rows.map((row) => ({ ...row, [key]: row[key] === null || row[key] === undefined || !Number.isFinite(Number(row[key])) ? 0 : Number(row[key]) }));
  const values = normalizedRows.map((row, index) => ({ index, value: row[key] }));
  const minimum = values.reduce((result, item) => item.value < result.value ? item : result);
  const maximum = values.reduce((result, item) => item.value > result.value ? item : result);
  const indexes = new Set([values[0].index, values[values.length - 1].index, minimum.index, maximum.index]);
  return normalizedRows.map((row, index) => ({ ...row, marked: indexes.has(index) }));
}

function Point({ cx, cy, payload, dataKey, color, showAll = false }) {
  const rawValue = payload?.[dataKey];
  if (rawValue === null || rawValue === undefined || !Number.isFinite(Number(rawValue)) || !Number.isFinite(Number(cx)) || !Number.isFinite(Number(cy))) return null;
  const shown = ["cost", "cpl"].includes(dataKey) ? rubleAxis(payload[dataKey]) : formatted(dataKey, payload[dataKey]);
  return <g><circle cx={cx} cy={cy} r={payload.marked || showAll ? 4 : 3} fill="#fff" stroke={color} strokeWidth="2" />{(payload.marked || showAll) && <CollisionSafeChartLabel x={cx} y={Number(cy) - 11} className={showAll ? "context-point-label context-point-label--large" : "context-point-label"}>{shown}</CollisionSafeChartLabel>}</g>;
}

function TopBarLabel({ x, y, width, value, metric }) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  const shown = metric === "cpl" ? rubleAxis(value) : formatted(metric, value);
  return <CollisionSafeChartLabel x={Number(x) + Number(width) / 2} y={Number(y) - 5} className="context-bar-label">{shown}</CollisionSafeChartLabel>;
}

function MetricChart({ title, metric, rows = [], onPeriod, compact = false, daily = false, periodEnd = "", showAll = false }) {
  const color = METRIC_COLORS[metric];
  return <article className="seo-panel context-visual"><header><h3>{title}</h3></header><div className={`context-chart ${compact ? "context-chart--compact" : ""}`}><SafeChartContainer><AreaChart data={mark(rows, metric)} onClick={(state) => state?.activeLabel && onPeriod?.(state.activeLabel)} margin={{ top: showAll ? 38 : 24, right: 20, bottom: 0, left: 3 }}><defs><linearGradient id={`context-${metric}-${daily ? "day" : "week"}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".35" /><stop offset="1" stopColor={color} stopOpacity=".03" /></linearGradient></defs><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="period" minTickGap={daily ? 8 : 32} tickFormatter={dateLabel} /><YAxis tickFormatter={(value) => axisFormatted(metric, value)} /><Tooltip content={<ChartTooltip daily={daily} periodEnd={periodEnd} />} /><Area dataKey={metric} name={title} stroke={color} strokeWidth={3} fill={`url(#context-${metric}-${daily ? "day" : "week"})`} dot={(props) => <Point {...props} dataKey={metric} color={color} showAll={showAll} />} activeDot={{ r: 5 }} /></AreaChart></SafeChartContainer></div></article>;
}

function CombinedDynamicsTooltip({ active, label, rows, metrics, periodEnd = "" }) {
  if (!active || !label) return null;
  const row = rows.find((item) => String(item.period) === String(label));
  if (!row) return null;
  return <div className="seo-tooltip context-combined-tooltip"><strong>{weekLabel(label, periodEnd)}</strong>{metrics.map(([title, metric]) => <div key={metric}><i style={{ background: METRIC_COLORS[metric] }} /><span>{title}</span><b>{formatted(metric, row[metric])}</b></div>)}</div>;
}

function FloatingDynamicsTooltip({ hover, rows, metrics, periodEnd }) {
  const tooltipRef = useRef(null);
  const [position, setPosition] = useState({ left: hover?.x || 0, top: hover?.y || 0 });
  useLayoutEffect(() => {
    if (!hover || !tooltipRef.current) return;
    const box = tooltipRef.current.getBoundingClientRect();
    const gap = 14;
    const padding = 10;
    const left = hover.x + gap + box.width <= window.innerWidth - padding ? hover.x + gap : hover.x - gap - box.width;
    const top = hover.y + gap + box.height <= window.innerHeight - padding ? hover.y + gap : hover.y - gap - box.height;
    setPosition({ left: Math.max(padding, Math.min(left, window.innerWidth - box.width - padding)), top: Math.max(padding, Math.min(top, window.innerHeight - box.height - padding)) });
  }, [hover]);
  if (!hover?.label) return null;
  return createPortal(<div ref={tooltipRef} className="context-floating-dynamics-tooltip" style={position}><CombinedDynamicsTooltip active label={hover.label} rows={rows} metrics={metrics} periodEnd={periodEnd} /></div>, document.body);
}

function UnifiedDynamics({ rows = [], metrics, periodEnd = "", onPeriod, syncId }) {
  const [hover, setHover] = useState(null);
  const summary = syncId === "context-summary-dynamics";
  return <article className="seo-panel context-dynamics-stack">{metrics.map(([title, metric], index) => {
    const last = index === metrics.length - 1;
    const color = METRIC_COLORS[metric];
    return <section className="context-dynamics-row" key={metric} onMouseMove={(event) => setHover((old) => ({ metric, label: old?.metric === metric ? old.label : "", x: event.clientX, y: event.clientY }))} onMouseLeave={() => setHover(null)}><header><h3>{title}</h3></header><div className="context-dynamics-chart"><SafeChartContainer><AreaChart data={mark(rows, metric)} syncId={syncId} onMouseMove={(state) => state?.activeLabel && setHover((old) => ({ metric, label: state.activeLabel, x: old?.x || 0, y: old?.y || 0 }))} onClick={(state) => state?.activeLabel && onPeriod?.(title, metric, state.activeLabel)} margin={{ top: 24, right: 52, bottom: 14, left: summary ? 10 : 3 }}><defs><linearGradient id={`${syncId}-${metric}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".3" /><stop offset="1" stopColor={color} stopOpacity=".025" /></linearGradient></defs><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="period" tickFormatter={dateLabel} minTickGap={32} hide={!last} /><YAxis width={summary ? 72 : 60} tickFormatter={(value) => axisFormatted(metric, value)} /><Tooltip content={() => null} /><Area dataKey={metric} name={title} stroke={color} strokeWidth={2.5} fill={`url(#${syncId}-${metric})`} dot={(props) => <Point {...props} dataKey={metric} color={color} />} activeDot={{ r: 4 }} /></AreaChart></SafeChartContainer></div></section>;
  })}<FloatingDynamicsTooltip hover={hover} rows={rows} metrics={metrics} periodEnd={periodEnd} /></article>;
}

function Empty() { return <article className="seo-panel seo-panel--wide context-empty">Нет данных за выбранный период</article>; }

function DayModal({ state, close }) {
  useEffect(() => { if (!state) return undefined; const escape = (event) => event.key === "Escape" && close(); document.addEventListener("keydown", escape); return () => document.removeEventListener("keydown", escape); }, [state, close]);
  if (!state) return null;
  return <div className="context-day-modal" role="dialog"><div className="crm-modal__card"><div className="crm-modal__header context-day-modal__header"><div><small>Детализация недели</small><h2>{state.title} по дням</h2><p>{state.periodLabel}</p></div><button type="button" className="crm-close" onClick={close} aria-label="Закрыть">×</button></div><div className="context-day-modal__body">{state.loading ? <div className="context-loading"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных…</div></div></div> : state.error ? <div className="context-day-modal__error">{state.error}</div> : state.rows.length ? <MetricChart title={state.title} metric={state.metric} rows={state.rows} daily showAll /> : <Empty />}</div></div></div>;
}

function TablePopup({ report, close }) {
  const [loading, setLoading] = useState(false);
  useEffect(() => { const escape = (event) => event.key === "Escape" && close(); document.addEventListener("keydown", escape); return () => document.removeEventListener("keydown", escape); }, [close]);
  useEffect(() => { const update = (event) => setLoading(Boolean(event.detail)); window.addEventListener("context:summary-popup-loading", update); return () => window.removeEventListener("context:summary-popup-loading", update); }, []);
  return <section className="context-table-popup" role="dialog" aria-label="Данные по кампаниям и группам"><div className="context-table-popup__card"><button type="button" className="crm-close" onClick={close} aria-label="Закрыть">×</button><SimpleTable page="summary" report={report} popup />{loading && <div className="context-popup-loading"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>}</div></section>;
}

function Summary({ report, openDays }) {
  const [tableOpen, setTableOpen] = useState(false);
  const openTable = () => { summaryTablePopupOpen = true; setTableOpen(true); };
  const closeTable = () => { summaryTablePopupOpen = false; setTableOpen(false); };
  const metrics = [["Клики", "clicks"], ["Лиды", "leads"], ["Расход", "cost"], ["CPL", "cpl"]];
  return <><section className="context-summary-layout"><SimpleTable page="summary" report={report} onExpand={openTable} /><UnifiedDynamics rows={report.weekly || []} metrics={metrics} periodEnd={report?.filters?.date_to} syncId="context-summary-dynamics" onPeriod={(title, metric, period) => openDays(title, metric, period)} /></section>{tableOpen && <TablePopup report={report} close={closeTable} />}</>;
}

function Change({ value }) {
  if (value === null) return "—";
  const up = value >= 0;
  return <span className={`context-change ${up ? "is-up" : "is-down"}`}><i>{up ? "▲" : "▼"}</i>{percent(Math.abs(value))}<b style={{ width: `${Math.min(Math.abs(value), 100) / 2}%`, [up ? "left" : "right"]: "50%" }} /></span>;
}

function sortRows(rows, sort, getter = (row, key) => row[key]) {
  if (!sort.key) return rows;
  return rows.map((row, index) => ({ row, index })).sort((left, right) => {
    const rawA = getter(left.row, sort.key); const rawB = getter(right.row, sort.key);
    const a = Number(rawA); const b = Number(rawB);
    const aValid = rawA !== null && rawA !== undefined && Number.isFinite(a); const bValid = rawB !== null && rawB !== undefined && Number.isFinite(b);
    let result;
    if (aValid && bValid) result = a - b;
    else if (aValid !== bValid) result = aValid ? -1 : 1;
    else result = String(rawA ?? "").localeCompare(String(rawB ?? ""), "ru", { numeric: true, sensitivity: "base" });
    return result === 0 ? left.index - right.index : result * (sort.direction === "asc" ? 1 : -1);
  }).map(({ row }) => row);
}

function SortHeader({ label, sortKey, sort, setSort, className = "", marker = null, defaultDirection = "asc", master = null }) {
  const active = sort.key === sortKey;
  const toggle = () => setSort((old) => old.key === sortKey ? { key: sortKey, direction: old.direction === "desc" ? "asc" : "desc" } : { key: sortKey, direction: defaultDirection });
  return <th className={className}><div className="context-head-actions">{master}<button type="button" className={`context-sort ${active ? "is-active" : ""}`} onClick={toggle}>{marker}{label}<i className="context-sort-arrow">{active ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}</i></button></div></th>;
}
const NumericSortHeader = (props) => <SortHeader {...props} defaultDirection="desc" />;
const PlainHeader = ({ label, master = null }) => <th><div className="context-head-actions">{master}<span>{label}</span></div></th>;
function SummaryHeaderHelp({ children }) {
  const anchorRef = useRef(null);
  const tooltipRef = useRef(null);
  const [position, setPosition] = useState(null);
  const place = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const bounds = anchor.getBoundingClientRect();
    const width = Math.min(300, Math.max(180, window.innerWidth - 20));
    setPosition({ left: Math.max(10, Math.min(bounds.left + bounds.width / 2 - width / 2, window.innerWidth - width - 10)), top: bounds.bottom + 8, width });
  }, []);
  useLayoutEffect(() => {
    if (!position || !tooltipRef.current || !anchorRef.current) return;
    const anchor = anchorRef.current.getBoundingClientRect();
    const tooltip = tooltipRef.current.getBoundingClientRect();
    if (tooltip.bottom <= window.innerHeight - 10 || anchor.top - tooltip.height - 8 < 10) return;
    const top = anchor.top - tooltip.height - 8;
    if (Math.abs(position.top - top) > 1) setPosition((old) => ({ ...old, top }));
  }, [position]);
  useEffect(() => {
    if (!position) return undefined;
    const update = () => place();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => { window.removeEventListener("scroll", update, true); window.removeEventListener("resize", update); };
  }, [position, place]);
  const open = (event) => { event.stopPropagation(); place(); };
  const close = () => setPosition(null);
  return <><i ref={anchorRef} className="context-help context-table-help" tabIndex={0} onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close} onClick={(event) => event.stopPropagation()}>i</i>{position && createPortal(<span ref={tooltipRef} className="context-table-help-tooltip" role="tooltip" style={position}>{children}</span>, document.body)}</>;
}

function WeeklyPage({ report, openDays }) {
  const [sort, setSort] = useState({ key: "period", direction: "desc" });
  const source = report.weekly || [];
  const rows = source.map((row, index) => ({ ...row, leadDelta: index ? (row.leads - source[index - 1].leads) * 100 / (source[index - 1].leads || 1) : null, cplDelta: index ? ((row.cpl || 0) - (source[index - 1].cpl || 0)) * 100 / (source[index - 1].cpl || 1) : null }));
  if (!rows.length) return <Empty />;
  const sortedRows = sortRows(rows, sort);
  const totalLeads = rows.reduce((sum, row) => sum + Number(row.leads || 0), 0); const totalCost = rows.reduce((sum, row) => sum + Number(row.cost || 0), 0);
  const metrics = [["Лиды", "leads"], ["CPL", "cpl"], ["CR", "cr"]];
  return <section className="context-week-layout"><article className="seo-panel context-week-table"><div><table><thead><tr><SortHeader label="Неделя" sortKey="period" sort={sort} setSort={setSort} /><NumericSortHeader label="Лиды" sortKey="leads" sort={sort} setSort={setSort} /><NumericSortHeader className="context-growth-column" label="Прирост лидов, %" sortKey="leadDelta" sort={sort} setSort={setSort} /><NumericSortHeader label="CPL" sortKey="cpl" sort={sort} setSort={setSort} /><NumericSortHeader className="context-growth-column" label="Прирост CPL, %" sortKey="cplDelta" sort={sort} setSort={setSort} /></tr></thead><tbody>{sortedRows.map((row) => <tr key={row.period}><td><button type="button" onClick={() => openDays("Лиды", "leads", row.period)}>{weekLabel(row.period)}</button></td><td>{number(row.leads)}</td><td className="context-growth-column"><Change value={row.leadDelta} /></td><td>{money(row.cpl)}</td><td className="context-growth-column"><Change value={row.cplDelta} /></td></tr>)}<tr className="context-grand-total"><td>Итого</td><td>{number(totalLeads)}</td><td /><td>{money(totalLeads ? totalCost / totalLeads : null)}</td><td /></tr></tbody></table></div></article><UnifiedDynamics rows={rows} metrics={metrics} periodEnd={report?.filters?.date_to} syncId="context-weekly-dynamics" onPeriod={(title, metric, period) => openDays(title, metric, period)} /></section>;
}

const LABELS = { campaign_name: "Кампания", campaign: "Кампания", ad_group_name: "Группа объявлений", ad_group: "Группа объявлений", criterion: "Ключевая фраза", criterion_type: "Тип условия", impressions: "Показы", clicks: "Клики", cost: "Расход", visits: "Визиты", leads: "Лиды", ctr: "CTR", cpc: "CPC", bounce_rate: "Отказы, %", avg_impression_position: "Ср. поз. показа", avg_click_position: "Ср. поз. клика", cr: "CR", cpl: "CPL", id: "ID цели", name: "Цель" };
const METRICS = ["impressions", "clicks", "cost", "visits", "bounces", "bounce_sessions", "position_impressions", "position_clicks", "leads"];
function aggregateRows(rows) { const result = Object.fromEntries(METRICS.map((key) => [key, rows.reduce((sum, row) => sum + Number(row[key] || 0), 0)])); result.ctr = result.impressions ? result.clicks * 100 / result.impressions : null; result.cpc = result.clicks ? result.cost / result.clicks : null; result.bounce_rate = result.bounce_sessions ? result.bounces * 100 / result.bounce_sessions : null; result.avg_impression_position = result.position_impressions ? rows.reduce((sum, row) => sum + Number(row.avg_impression_position || 0) * Number(row.position_impressions || 0), 0) / result.position_impressions : null; result.avg_click_position = result.position_clicks ? rows.reduce((sum, row) => sum + Number(row.avg_click_position || 0) * Number(row.position_clicks || 0), 0) / result.position_clicks : null; result.cr = result.clicks ? result.leads * 100 / result.clicks : null; result.cpl = result.leads ? result.cost / result.leads : null; return result; }
function TreeToggle({ open, onClick, all = false }) { return <button type="button" className="context-tree-toggle" onClick={onClick} title={open ? (all ? "Свернуть все" : "Свернуть") : (all ? "Раскрыть все" : "Раскрыть")} aria-expanded={open}>{open ? "[-]" : "[+]"}</button>; }
function SimpleTable({ page, report, onExpand = null, popup = false }) {
  const [sort, setSort] = useState(() => ["criteria", "summary"].includes(page) ? { key: "leads", direction: "desc" } : { key: "", direction: "desc" });
  const [expanded, setExpanded] = useState(() => new Set());
  const [tablePage, setTablePage] = useState(1);
  const rows = ["summary", "weekly"].includes(page) ? report.campaigns || [] : page === "conversions" ? report.goals || [] : report.rows || [];
  useEffect(() => { setTablePage(1); }, [report, sort.key, sort.direction]);
  if (!rows.length) return <Empty />;
  const campaignKey = page === "criteria" ? "campaign" : "campaign_name"; const groupKey = page === "criteria" ? "ad_group" : "ad_group_name";
  const metricColumns = (page === "criteria" ? ["criterion", "impressions", "clicks", "ctr", "cpc", "cost", "leads", "cpl", "cr"] : ["impressions", "clicks", "ctr", "cpc", "bounce_rate", "avg_impression_position", "avg_click_position", "cost", "visits", "leads", "cr", "cpl"]).filter((key) => rows.some((row) => key in row));
  const grouped = new Map(); rows.forEach((row) => { const name = row[campaignKey] || "Не определено"; const key = page === "criteria" ? `${row.campaign_id ?? "unknown"}:${name}` : String(name); if (!grouped.has(key)) grouped.set(key, { key, name, rows: [] }); grouped.get(key).rows.push(row); });
  let campaigns = [...grouped.values()].map((item) => ({ ...item, ...aggregateRows(item.rows), [campaignKey]: item.name }));
  campaigns = sortRows(campaigns, sort).map((campaign) => ({ ...campaign, rows: sortRows(campaign.rows, sort) }));
  const pageSize = page === "criteria" ? 20 : campaigns.length || 1;
  const pageCount = Math.max(1, Math.ceil(campaigns.length / pageSize));
  const currentPage = Math.min(tablePage, pageCount);
  const visibleCampaigns = campaigns.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const allOpen = visibleCampaigns.length > 0 && visibleCampaigns.every((campaign) => expanded.has(campaign.key));
  const toggleAll = () => setExpanded((old) => { const next = new Set(old); visibleCampaigns.forEach((campaign) => { if (allOpen) next.delete(campaign.key); else next.add(campaign.key); }); return next; });
  const toggle = (key) => setExpanded((old) => { const next = new Set(old); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const display = (key, value) => key === "criterion" && value === "---autotargeting" ? "Автотаргетинг" : typeof value === "number" ? formatted(key, value) : value;
  const total = page === "criteria" ? report.summary || aggregateRows(rows) : aggregateRows(rows);
  const headerHelp = {
    bounce_rate: <>Отказы, % = Количество отказов ÷ Визиты × 100%.<span>Количество отказов в итоговом расчёте: <strong>{number(total.bounces)}</strong></span></>,
    avg_impression_position: <>Средняя позиция показа = сумма (Средняя позиция строки × Применимые показы строки) ÷ Количество применимых показов.</>,
    avg_click_position: <>Средняя позиция клика = сумма (Средняя позиция строки × Применимые клики строки) ÷ Количество применимых кликов.</>,
  };
  const metricColumnClass = (key) => ["avg_impression_position", "avg_click_position"].includes(key) ? "context-position-column" : key === "bounce_rate" ? "context-bounce-column" : "";
  const columnLabel = (key) => key === "avg_impression_position" ? <span className="context-position-heading"><span>Ср. поз.</span><span>показа</span></span> : key === "avg_click_position" ? <span className="context-position-heading"><span>Ср. поз.</span><span>клика</span></span> : LABELS[key] || key;
  const headerLabel = (key) => <>{columnLabel(key)}{headerHelp[key] && <SummaryHeaderHelp>{headerHelp[key]}</SummaryHeaderHelp>}</>;
  const cellClass = (key) => [key === "criterion" ? "context-ellipsis-cell" : "", metricColumnClass(key)].filter(Boolean).join(" ");
  return <article className={`seo-panel seo-panel--wide context-table context-tree-table ${popup ? "context-table--popup" : ""} ${page === "criteria" ? "context-table--tall context-criteria-table" : ""}`}><header><h3>{page === "criteria" ? "Ключевые слова" : "Данные"}</h3>{onExpand && <button type="button" className="context-table-expand" onClick={onExpand} title="Открыть таблицу полностью" aria-label="Открыть таблицу полностью">↗</button>}</header><div><table><thead><tr><SortHeader label="Кампания" sortKey={campaignKey} sort={sort} setSort={setSort} master={<TreeToggle all open={allOpen} onClick={toggleAll} />} /><PlainHeader label="Группа объявлений" />{metricColumns.map((key) => key === "criterion" ? <PlainHeader key={key} label={LABELS[key]} /> : typeof rows.find((row) => row[key] !== null && row[key] !== undefined)?.[key] === "number" ? <NumericSortHeader key={key} className={metricColumnClass(key)} label={headerLabel(key)} sortKey={key} sort={sort} setSort={setSort} /> : <SortHeader key={key} className={metricColumnClass(key)} label={headerLabel(key)} sortKey={key} sort={sort} setSort={setSort} />)}</tr></thead><tbody>{visibleCampaigns.map((campaign) => <Fragment key={campaign.key}><tr className="context-campaign-row"><td><TreeToggle open={expanded.has(campaign.key)} onClick={() => toggle(campaign.key)} /><span title={campaign.name}>{campaign.name}</span></td><td />{metricColumns.map((key) => <td key={key} className={cellClass(key)}>{typeof campaign[key] === "number" ? formatted(key, campaign[key]) : ""}</td>)}</tr>{expanded.has(campaign.key) && campaign.rows.map((row, index) => <tr className="context-group-row" key={`${campaign.key}-${row[groupKey]}-${row.criterion || index}`}><td>{["summary", "criteria"].includes(page) && <span className="context-repeated-campaign" title={campaign.name}>{campaign.name}</span>}</td><td><span title={row[groupKey]}>{row[groupKey]}</span></td>{metricColumns.map((key) => <td key={key} className={cellClass(key)} title={String(display(key, row[key]) ?? "")}>{display(key, row[key])}</td>)}</tr>)}</Fragment>)}<tr className="context-grand-total"><td>Итого</td><td />{metricColumns.map((key) => <td key={key} className={cellClass(key)}>{typeof total[key] === "number" ? formatted(key, total[key]) : ""}</td>)}</tr></tbody></table></div>{page === "criteria" && pageCount > 1 && <div className="context-pagination"><button type="button" disabled={currentPage <= 1} onClick={() => setTablePage(currentPage - 1)}>Назад</button><span>Страница {currentPage} из {pageCount}</span><button type="button" disabled={currentPage >= pageCount} onClick={() => setTablePage(currentPage + 1)}>Далее</button></div>}</article>;
}

function goalData(report) {
  const values = new Map((report.goals || []).map((row) => [String(row.id), Number(row.leads || 0)]));
  return (report.configured_goals || report.goals || []).map((goal, index) => ({
    ...goal, leads: values.get(String(goal.id)) || 0, color: COLORS[index % COLORS.length],
  }));
}

function GoalCards({ goals }) {
  const total = goals.reduce((sum, goal) => sum + goal.leads, 0);
  return <section className="context-goal-cards"><article><span title="Все лиды">Все лиды</span><strong>{number(total)}</strong></article>{goals.map((goal) => <article key={goal.id} style={{ "--context-color": goal.color }}><span title={goal.name}>{goal.name}</span><strong>{number(goal.leads)}</strong></article>)}</section>;
}

function hierarchy(report, goals) {
  const campaigns = new Map();
  for (const row of report.campaign_groups || []) {
    const key = String(row.campaign_id);
    if (!campaigns.has(key)) campaigns.set(key, { campaign_id: row.campaign_id, campaign_name: row.campaign_name, clicks: 0, cost: 0, leads: 0, goals: Object.fromEntries(goals.map((goal) => [String(goal.id), 0])), groups: [] });
    const campaign = campaigns.get(key);
    const groupGoals = row.goals || {}; const groupLeads = goals.reduce((sum, goal) => sum + Number(groupGoals[String(goal.id)] || 0), 0);
    const group = { ...row, goals: groupGoals, leads: groupLeads, cr: row.clicks ? groupLeads * 100 / Number(row.clicks) : null, cpl: groupLeads ? Number(row.cost || 0) / groupLeads : null };
    campaign.groups.push(group);
    campaign.clicks += Number(group.clicks || 0); campaign.cost += Number(group.cost || 0); campaign.leads += groupLeads;
    goals.forEach((goal) => { campaign.goals[String(goal.id)] += Number(group.goals[String(goal.id)] || 0); });
  }
  return [...campaigns.values()].map((campaign) => ({ ...campaign, cr: campaign.clicks ? campaign.leads * 100 / campaign.clicks : null, cpl: campaign.leads ? campaign.cost / campaign.leads : null }));
}

function GoalMatrixTooltip({ state, goals }) {
  const tooltipRef = useRef(null);
  const [position, setPosition] = useState({ left: state?.x || 0, top: state?.y || 0 });
  useLayoutEffect(() => {
    if (!state || !tooltipRef.current) return;
    const box = tooltipRef.current.getBoundingClientRect();
    const gap = 14;
    const padding = 10;
    const preferredLeft = state.x + gap + box.width <= window.innerWidth - padding
      ? state.x + gap
      : state.x - gap - box.width;
    const preferredTop = state.y + gap + box.height <= window.innerHeight - padding
      ? state.y + gap
      : state.y - gap - box.height;
    setPosition({
      left: Math.max(padding, Math.min(preferredLeft, window.innerWidth - box.width - padding)),
      top: Math.max(padding, Math.min(preferredTop, window.innerHeight - box.height - padding)),
    });
  }, [state]);
  if (!state) return null;
  const values = goals.map((goal, index) => ({ ...goal, value: Number(state.row.goals?.[String(goal.id)] || 0), sourceIndex: index }))
    .sort((left, right) => right.value - left.value || left.sourceIndex - right.sourceIndex);
  const total = values.reduce((sum, goal) => sum + goal.value, 0);
  return createPortal(<aside ref={tooltipRef} className="context-goal-row-tooltip" style={position}><strong title={state.name}>{state.name}</strong><div>{values.map((goal) => <span key={goal.id}><i style={{ background: goal.color }} /><em title={goal.name}>{goal.name}</em><b>{number(goal.value)}</b><small>{percent(total ? goal.value * 100 / total : 0)}</small></span>)}</div><footer><em>Все цели</em><b>{number(total)}</b><small>{percent(total ? 100 : 0)}</small></footer></aside>, document.body);
}

function LeadHierarchyTable({ report, goals, matrix = false }) {
  const [sort, setSort] = useState({ key: "leads", direction: "desc" });
  const [expanded, setExpanded] = useState(() => new Set());
  const [rowTooltip, setRowTooltip] = useState(null);
  const [selectedGoalNames, setSelectedGoalNamesState] = useState(() => matrix ? [] : leadStructureSelectedGoals);
  const setSelectedGoalNames = (value) => { leadStructureSelectedGoals = value; setSelectedGoalNamesState(value); };
  useEffect(() => {
    if (matrix) return undefined;
    const clearGoalFilter = () => setSelectedGoalNames([]);
    window.addEventListener("context:clear-filters", clearGoalFilter);
    return () => window.removeEventListener("context:clear-filters", clearGoalFilter);
  }, [matrix]);
  const activeGoals = matrix || !selectedGoalNames.length ? goals : goals.filter((goal) => selectedGoalNames.includes(goal.name));
  const campaigns = hierarchy(report, activeGoals);
  const total = { clicks: 0, cost: 0, leads: 0, goals: Object.fromEntries(activeGoals.map((goal) => [String(goal.id), 0])) };
  campaigns.forEach((campaign) => { total.clicks += campaign.clicks; total.cost += campaign.cost; total.leads += campaign.leads; activeGoals.forEach((goal) => { total.goals[String(goal.id)] += campaign.goals[String(goal.id)]; }); });
  total.cr = total.clicks ? total.leads * 100 / total.clicks : null; total.cpl = total.leads ? total.cost / total.leads : null;
  if (!campaigns.length) return <Empty />;
  const getValue = (row, key) => key.startsWith("goal:") ? row.goals[String(key.slice(5))] : row[key];
  const sortedCampaigns = sortRows(campaigns, sort, getValue).map((campaign) => ({ ...campaign, groups: sortRows(campaign.groups, sort, getValue) }));
  const allOpen = sortedCampaigns.length > 0 && sortedCampaigns.every((campaign) => expanded.has(String(campaign.campaign_id)));
  const toggleAll = () => setExpanded(allOpen ? new Set() : new Set(sortedCampaigns.map((campaign) => String(campaign.campaign_id))));
  const toggle = (key) => setExpanded((old) => { const next = new Set(old); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const showRowTooltip = (event, row, name) => { if (!matrix) return; setRowTooltip({ row, name, x: event.clientX, y: event.clientY }); };
  const values = (row) => matrix ? <>{goals.map((goal) => { const value = Number(row.goals[String(goal.id)] || 0); const share = row.leads ? Math.min(100, value * 100 / Number(row.leads)) : 0; return <td key={goal.id} className="context-goal-share-cell" style={{ "--goal-share": `${share}%`, "--goal-share-color": `${goal.color}33` }}>{number(value)}</td>; })}<td className="context-total-column">{number(row.leads)}</td></> : <><td>{number(row.leads)}</td><td>{percent(row.cr)}</td><td>{money(row.cpl)}</td></>;
  return <article className={`seo-panel context-lead-table ${matrix ? "context-lead-table--matrix" : ""}`}>{!matrix && <header className="context-lead-table__header"><h3>Лиды по кампаниям</h3><div className="context-goal-filter"><DashboardMultiSelect label="Цели" options={goals.map((goal) => goal.name)} selected={selectedGoalNames} onApply={setSelectedGoalNames} /></div></header>}<div><table><thead><tr><SortHeader label="Кампания" sortKey="campaign_name" sort={sort} setSort={setSort} master={<TreeToggle all open={allOpen} onClick={toggleAll} />} /><PlainHeader label="Группа объявлений" />{matrix ? <>{goals.map((goal) => <NumericSortHeader key={goal.id} label={goal.name} sortKey={`goal:${goal.id}`} sort={sort} setSort={setSort} marker={<span className="context-goal-marker" style={{ background: goal.color }} />} />)}<NumericSortHeader label="Все лиды" sortKey="leads" sort={sort} setSort={setSort} className="context-total-column" /></> : <><NumericSortHeader label="Лиды" sortKey="leads" sort={sort} setSort={setSort} /><NumericSortHeader label="CR" sortKey="cr" sort={sort} setSort={setSort} /><NumericSortHeader label="CPL" sortKey="cpl" sort={sort} setSort={setSort} /></>}</tr></thead><tbody>{sortedCampaigns.map((campaign) => { const key = String(campaign.campaign_id); return <Fragment key={key}><tr className="context-campaign-row" onMouseEnter={(event) => showRowTooltip(event, campaign, campaign.campaign_name)} onMouseMove={(event) => showRowTooltip(event, campaign, campaign.campaign_name)} onMouseLeave={() => setRowTooltip(null)}><td><TreeToggle open={expanded.has(key)} onClick={() => toggle(key)} /><span title={matrix ? undefined : campaign.campaign_name}>{campaign.campaign_name}</span></td><td />{values(campaign)}</tr>{expanded.has(key) && campaign.groups.map((group) => <tr key={`${group.campaign_id}-${group.ad_group_id}`} className="context-group-row" onMouseEnter={(event) => showRowTooltip(event, group, group.ad_group_name || `Группа ${group.ad_group_id}`)} onMouseMove={(event) => showRowTooltip(event, group, group.ad_group_name || `Группа ${group.ad_group_id}`)} onMouseLeave={() => setRowTooltip(null)}><td><span className="context-repeated-campaign" title={campaign.campaign_name}>{campaign.campaign_name}</span></td><td><span title={matrix ? undefined : group.ad_group_name}>{group.ad_group_name || `Группа ${group.ad_group_id}`}</span></td>{values(group)}</tr>)}</Fragment>; })}<tr className="context-grand-total"><td>Итого</td><td />{values(total)}</tr></tbody></table></div><GoalMatrixTooltip state={matrix ? rowTooltip : null} goals={goals} /></article>;
}

function LeadStructure({ report }) {
  const goals = goalData(report); const sortedGoals = [...goals].sort((left, right) => Number(right.leads || 0) - Number(left.leads || 0)); const [hidden, setHidden] = useState(() => new Set()); const visible = sortedGoals.filter((goal) => !hidden.has(goal.name)); const total = visible.reduce((sum, goal) => sum + goal.leads, 0);
  if (!goals.length) return <Empty />;
  return <><GoalCards goals={goals} /><section className="context-lead-structure"><LeadHierarchyTable report={report} goals={goals} /><article className="seo-panel context-donut"><header><h3>Типы лидов</h3></header><div className="context-donut-content"><div className="context-chart"><SafeChartContainer><PieChart>{visible.length ? <Pie data={visible} dataKey="leads" nameKey="name" innerRadius={0} outerRadius="76%">{visible.map((goal) => <Cell key={goal.id} fill={goal.color} />)}</Pie> : null}<Tooltip content={<ChartTooltip percentage />} /></PieChart></SafeChartContainer></div><div className="context-donut-legend">{sortedGoals.map((goal) => { const share = total && !hidden.has(goal.name) ? goal.leads * 100 / total : 0; return <button type="button" className={hidden.has(goal.name) ? "is-hidden" : ""} key={goal.id} onClick={() => toggleSeries(setHidden, goal.name)}><i style={{ background: goal.color }} /><span title={goal.name}>{goal.name}</span><div className="context-region-track"><i style={{ width: `${share}%`, background: goal.color }} /></div><b>{number(goal.leads)}</b><em>{percent(share)}</em></button>; })}</div></div></article></section></>;
}

function Conversions({ report }) {
  const goals = goalData(report);
  if (!goals.length) return <Empty />;
  return <><GoalCards goals={goals} /><LeadHierarchyTable report={report} goals={goals} matrix /></>;
}

const DEVICE_NAMES = { DESKTOP: "ПК", MOBILE: "Смартфоны", TABLET: "Планшеты", UNKNOWN: "Не определено" };
const DEVICE_COLORS = { "ПК": COLORS[0], "Смартфоны": COLORS[1], "Планшеты": COLORS[2], "Не определено": COLORS[3] };
function Devices({ rows = [] }) {
  const data = rows.map((row) => { const device = DEVICE_NAMES[String(row.device).toUpperCase()] || row.device; return { ...row, device, color: DEVICE_COLORS[device] || COLORS[4] }; });
  if (!data.length) return <Empty />;
  const pie = (title, key) => <RankedPie title={title} rows={data.map((row) => ({ name: row.device, value: Number(row[key] || 0), color: row.color }))} />;
  const bars = (title, key) => { const chartRows = data.filter((row) => row[key] !== null && row[key] !== undefined && Number(row[key]) > 0).sort((a, b) => Number(a[key]) - Number(b[key])); return <DeviceBar title={title} metric={key} rows={chartRows} />; };
  return <section className="context-breakdown-grid">{pie("Клики", "clicks")}{pie("Лиды", "leads")}{bars("CPL", "cpl")}{bars("CR", "cr")}</section>;
}

function RankedPie({ title, rows }) {
  const [hidden, setHidden] = useState(() => new Set()); const all = rows.filter((row) => row.value > 0).sort((a, b) => b.value - a.value).map((row, index) => ({ ...row, color: row.color || COLORS[index % COLORS.length] })); const visible = all.filter((row) => !hidden.has(row.name)); const total = visible.reduce((sum, row) => sum + row.value, 0);
  return <article className="seo-panel context-visual context-ranked-pie"><header><h3>{title}</h3></header><div className="context-donut-content"><div className="context-chart"><SafeChartContainer><PieChart>{visible.length ? <Pie data={visible} dataKey="value" nameKey="name" outerRadius="74%">{visible.map((row) => <Cell key={row.name} fill={row.color} />)}</Pie> : null}<Tooltip content={<ChartTooltip percentage />} /></PieChart></SafeChartContainer></div><div className="context-donut-legend">{all.map((row) => { const share = total && !hidden.has(row.name) ? row.value * 100 / total : 0; return <button type="button" className={hidden.has(row.name) ? "is-hidden" : ""} key={row.name} onClick={() => toggleSeries(setHidden, row.name)}><i style={{ background: row.color }} /><span title={row.name}>{row.name}</span><div className="context-region-track"><i style={{ width: `${share}%`, background: row.color }} /></div><b>{number(row.value)}</b><em>{percent(share)}</em></button>; })}</div></div></article>;
}

function DeviceBar({ title, metric, rows }) {
  return <article className="seo-panel context-visual"><header><h3>{title}</h3></header><div className="context-chart"><SafeChartContainer><BarChart data={rows} margin={{ top: 34, right: 24, left: 10 }}><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="device" /><YAxis tickFormatter={(value) => metric === "cpl" ? wholeRubleAxis(value) : percent(value, 0)} /><Tooltip content={<ChartTooltip />} /><Bar dataKey={metric} name={title} radius={[4,4,0,0]}>{rows.map((row) => <Cell key={row.device} fill={row.color} />)}<LabelList dataKey={metric} content={<TopBarLabel metric={metric} />} /></Bar></BarChart></SafeChartContainer></div></article>;
}

function Demography({ rows = [] }) {
  const ages = ["AGE_18_24", "AGE_25_34", "AGE_35_44", "AGE_45_54", "AGE_55", "UNKNOWN"];
  const ageNames = { AGE_18_24: "18–24 года", AGE_25_34: "25–34 года", AGE_35_44: "35–44 года", AGE_45_54: "45–54 года", AGE_55: "55 лет и старше", UNKNOWN: "Не определено" };
  const genderNames = { GENDER_FEMALE: "Женский", GENDER_MALE: "Мужской", UNKNOWN: "Не определено" };
  const normalized = rows.map((row) => ({ ...row, genderName: genderNames[String(row.gender).toUpperCase()] || row.gender }));
  const availableGenders = new Set(normalized.map((row) => row.genderName));
  const genders = ["Мужской", "Женский", "Не определено"].filter((gender) => availableGenders.has(gender));
  const data = ages.map((age) => ({ age: ageNames[age], ...Object.fromEntries(normalized.filter((row) => String(row.age).toUpperCase() === age).map((row) => [row.genderName, row])) })).filter((row) => genders.some((gender) => row[gender]));
  if (!data.length) return <Empty />;
  const chart = (title, key) => <DemographyChart title={title} metric={key} data={data} genders={genders} />;
  return <section className="context-breakdown-grid">{chart("Клики", "clicks")}{chart("Лиды", "leads")}{chart("CPL", "cpl")}{chart("CR", "cr")}</section>;
}

function DemographyChart({ title, metric, data, genders }) {
  const [hidden, setHidden] = useState(() => new Set());
  const valueFormat = (value) => metric === "cpl" ? money(value) : metric === "cr" ? percent(value) : number(value);
  const chartRows = data.map((row) => { const values = Object.fromEntries(genders.map((gender) => [gender, Number(row[gender]?.[metric] || 0)])); const total = Object.values(values).reduce((sum, value) => sum + value, 0); return { age: row.age, ...Object.fromEntries(genders.map((gender) => [gender, total ? values[gender] * 100 / total : 0])), ...Object.fromEntries(genders.map((gender, index) => [`raw_${index}`, values[gender]])) }; });
  const tooltip = ({ active, payload = [], label }) => active && payload.length ? <div className="seo-tooltip"><strong>{label}</strong>{[...payload].sort((a, b) => genders.indexOf(a.dataKey) - genders.indexOf(b.dataKey)).map((item) => { const index = genders.indexOf(item.dataKey); const value = item.payload?.[`raw_${index}`]; const shown = ["clicks", "leads"].includes(metric) ? `${valueFormat(value)} · ${percent(item.value)}` : valueFormat(value); return <div key={item.dataKey}><i style={{ background: item.color || item.fill }} /><span>{item.name}</span><b>{shown}</b></div>; })}</div> : null;
  const label = (gender) => ({ x, y, width, height, value }) => { const shown = valueFormat(value); const requiredWidth = Math.max(30, shown.length * 6.7 + 10); if (Number(value) <= 0 || Number(width) < requiredWidth || Number(height) < 15) return null; return <text x={Number(x) + Number(width) / 2} y={Number(y) + Number(height) / 2} dy=".35em" textAnchor="middle" className={`context-bar-percent ${gender === "Женский" ? "context-bar-percent--dark" : ""}`}>{shown}</text>; };
  const legendPayload = genders.map((value, index) => ({ value, type: "rect", color: COLORS[index % COLORS.length] }));
  return <article className="seo-panel context-visual"><header><h3>{title}</h3></header><div className="context-chart"><SafeChartContainer><BarChart data={chartRows} layout="vertical" margin={{ top: 10, right: 28, left: 20, bottom: 8 }}><CartesianGrid strokeDasharray="3 4" horizontal={false} /><XAxis type="number" domain={[0,100]} ticks={[0,25,50,75,100]} tickFormatter={(value) => `${number(value)}%`} /><YAxis type="category" dataKey="age" width={108} interval={0} /><Tooltip content={tooltip} /><InteractiveLegend hidden={hidden} setHidden={setHidden} payload={legendPayload} preserveOrder />{genders.map((gender, index) => <Bar key={gender} dataKey={gender} hide={hidden.has(gender)} stackId="total" fill={COLORS[index % COLORS.length]} radius={[0,3,3,0]}><LabelList dataKey={`raw_${index}`} content={label(gender)} /></Bar>)}</BarChart></SafeChartContainer></div></article>;
}

export function ContextAnalyticsDashboard({ dashboard }) {
  const canEdit = Boolean(dashboard?.can_edit);
  const [page, setPage] = useState("home"); const [filters, setFiltersState] = useState(defaults); const [options, setOptions] = useState({ options: {} }); const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [running, setRunning] = useState(false); const [version, setVersion] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false); const [settingsOpen, setSettingsOpen] = useState(false); const [uploading, setUploading] = useState(false); const [exporting, setExporting] = useState(false); const [dayModal, setDayModal] = useState(null);
  const menuRef = useRef(null); const settingsRef = useRef(null); const uploadRef = useRef(null); const dayRequestRef = useRef(0); const loadOptions = useCallback(async () => setOptions(await getContextOptions()), []); const closeError = useCallback(() => setError(""), []); const closeNotice = useCallback(() => setNotice(""), []); const closeModal = useCallback(() => { dayRequestRef.current += 1; setDayModal(null); }, []);
  const setFilters = useCallback((nextFilters) => {
    if (typeof nextFilters !== "function") window.dispatchEvent(new Event("context:clear-filters"));
    setFiltersState(nextFilters);
  }, []);
  useEffect(() => { const timer = setTimeout(() => { loadOptions().catch((requestError) => setError(errorText(requestError, "Не удалось загрузить фильтры."))); getContextRefreshState().then((state) => setRunning(Boolean(state.running))).catch(() => {}); }, 0); return () => clearTimeout(timer); }, [loadOptions]);
  useEffect(() => { const close = (event) => { if (menuRef.current && !menuRef.current.contains(event.target)) setMenuOpen(false); if (settingsRef.current && !settingsRef.current.contains(event.target)) setSettingsOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, []);
  useEffect(() => { const receive = (event) => { const message = event.detail || {}; if (message.dashboard !== "ContextAnalytics") return; setRunning(message.status === "running"); if (message.status === "failed") setError(message.error || "Обновление завершилось с ошибкой."); else if (message.status !== "running") { setVersion((value) => value + 1); loadOptions(); } }; window.addEventListener("dashboard:updated", receive); return () => window.removeEventListener("dashboard:updated", receive); }, [loadOptions]);
  useEffect(() => { if (!running) return undefined; const timer = setInterval(async () => { try { const state = await getContextRefreshState(); if (!state.running) { setRunning(false); if (state.status === "failed") setError(state.error || "Обновление завершилось с ошибкой."); else { setVersion((value) => value + 1); await loadOptions(); } } } catch { /* retry */ } }, 5000); return () => clearInterval(timer); }, [running, loadOptions]);
  const activeFilters = { ...filters, ad_groups: GROUP_FILTER_PAGES.has(page) ? filters.ad_groups : [], criteria: page === "criteria" ? filters.criteria : [] };
  const filtersKey = JSON.stringify(activeFilters);
  useEffect(() => { if (["home", "calltouch"].includes(page)) return undefined; let active = true; const timer = setTimeout(() => { getContextOptions(JSON.parse(filtersKey)).then((payload) => active && setOptions(payload)).catch((requestError) => active && setError(errorText(requestError, "Не удалось обновить зависимые фильтры."))); }, 120); return () => { active = false; clearTimeout(timer); }; }, [page, filtersKey, version]);
  useEffect(() => { if (["home", "calltouch"].includes(page)) return undefined; let active = true; const timer = setTimeout(() => { const popupLoading = page === "summary" && summaryTablePopupOpen; if (popupLoading) window.dispatchEvent(new CustomEvent("context:summary-popup-loading", { detail: true })); else setLoading(true); setError(""); getContextReport(page, JSON.parse(filtersKey)).then((data) => active && setReport(data)).catch((requestError) => active && setError(errorText(requestError, "Не удалось загрузить отчёт."))).finally(() => { if (active) { setLoading(false); if (popupLoading) window.dispatchEvent(new CustomEvent("context:summary-popup-loading", { detail: false })); } }); }, 0); return () => { active = false; clearTimeout(timer); }; }, [page, filtersKey, version]);
  const campaignOptions = useMemo(() => (options.options?.campaigns || []).map((item) => ({ value: String(item.id), label: `${item.name} · ${item.id}` })), [options]);
  const groupOptions = useMemo(() => [...new Map((options.options?.ad_groups || []).map((item) => { const value = String(item.id); const name = String(item.name || "").trim() || `Группа ${value}`; return [name, { value, label: name }]; })).values()], [options]);
  const criterionOptions = useMemo(() => (options.options?.criteria || []).map((item) => ({ value: String(item.id), label: item.name || `Условие ${item.id}` })), [options]);
  const selectedCampaignNames = campaignOptions.filter((item) => filters.campaigns.includes(item.value)).map((item) => item.label);
  const selectedGroupNames = groupOptions.filter((item) => filters.ad_groups.includes(item.value)).map((item) => item.label);
  const selectedCriterionNames = criterionOptions.filter((item) => filters.criteria.includes(item.value)).map((item) => item.label);
  const navigate = (next) => {
    if (next === page) {
      setMenuOpen(false);
      return;
    }
    summaryTablePopupOpen = false;
    leadStructureSelectedGoals = [];
    setFilters(defaults());
    setPage(next);
    setMenuOpen(false);
    setReport(null);
  };
  const movePage = (step) => { const index = PAGES.findIndex(([key]) => key === page); if (index < 0) return; navigate(PAGES[(index + step + PAGES.length) % PAGES.length][0]); };
  const openDays = async (title, metric, period) => { const requestId = dayRequestRef.current + 1; dayRequestRef.current = requestId; const start = new Date(`${String(period).slice(0, 10)}T00:00:00`); const end = new Date(start); end.setDate(end.getDate() + 6); const dateTo = iso(end) > activeFilters.date_to ? activeFilters.date_to : iso(end); const context = { title, metric, period, periodLabel: weekLabel(period, dateTo), rows: [] }; setDayModal({ ...context, loading: true }); try { const data = await getContextReport(page, { ...activeFilters, date_from: String(period).slice(0, 10), date_to: dateTo, granularity: "day" }); const loaded = new Map((data.weekly || []).map((row) => [String(row.period).slice(0, 10), row])); const rows = []; for (const cursor = new Date(start); cursor <= new Date(`${dateTo}T00:00:00`); cursor.setDate(cursor.getDate() + 1)) { if (!matchesDayMode(cursor, activeFilters.day_types)) continue; const day = iso(cursor); rows.push(loaded.get(day) || { period: day, [metric]: 0 }); } if (dayRequestRef.current === requestId) setDayModal({ ...context, loading: false, rows }); } catch (requestError) { if (dayRequestRef.current === requestId) setDayModal({ ...context, loading: false, error: errorText(requestError, "Не удалось загрузить данные по дням.") }); } };
  useEffect(() => { if (dayModal?.period) openDays(dayModal.title, dayModal.metric, dayModal.period); }, [filtersKey]); // Reapply usable top filters to the open drill-down.
  const upload = async (event) => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return; setUploading(true); try { const result = await uploadContextGoals(file); setNotice(`Настройка применена: ${result.goals} целей.`); setVersion((value) => value + 1); } catch (requestError) { setError(errorText(requestError, "Не удалось загрузить цели.")); } finally { setUploading(false); } };
  const doExport = async () => { setExporting(true); try { save(await exportContextReport(page, activeFilters), `context_${page}.xlsx`); } catch (requestError) { setError(errorText(requestError, "Не удалось сформировать Excel-выгрузку.")); } finally { setExporting(false); } };
  const refresh = async () => { try { await startContextRefresh(); setRunning(true); } catch (requestError) { setError(errorText(requestError, "Не удалось запустить обновление.")); } };
  const toast = error ? <Toast message={error} type="error" close={closeError} /> : <Toast message={notice} type="success" close={closeNotice} />;
  const lastUpdated = report?.meta?.last_updated ? new Date(report.meta.last_updated).toLocaleString("ru-RU", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  if (page === "home") return <main className="seo-dashboard seo-dashboard--home context-dashboard"><section ref={settingsRef} className={`seo-home-settings ${settingsOpen ? "is-open" : ""}`}><button type="button" className="seo-home-settings-toggle" onClick={() => setSettingsOpen((value) => !value)}>⋯</button><div className="seo-action-buttons"><button type="button" disabled={!canEdit || uploading} onClick={async () => { try { save(await downloadContextGoals(), "analytics_goals.xlsx"); } catch (requestError) { setError(errorText(requestError, "Не удалось скачать шаблон.")); } }}>Шаблон целей</button><button type="button" disabled={!canEdit || uploading} onClick={() => uploadRef.current?.click()}>{uploading ? "Загрузка…" : "Загрузить цели"}</button><input ref={uploadRef} hidden type="file" accept=".xlsx" onChange={upload} /></div></section>{toast}<section className="seo-home"><div className="seo-tiles">{PAGES.map(([key, short, title, icon]) => <button type="button" key={key} title={title} className={key === "calltouch" ? "is-planned" : ""} onClick={() => navigate(key)}><span className="seo-page-icon">{icon}</span><span><strong>{short}</strong></span><i>→</i>{key === "calltouch" && <em>Скоро</em>}</button>)}</div></section></main>;
  return <main className={`seo-dashboard context-dashboard context-dashboard--${page}`}><section ref={menuRef} className={`seo-menu ${menuOpen ? "is-open" : ""}`}><div className="seo-menu-controls"><button type="button" className="seo-menu-arrow" onClick={() => movePage(-1)} title="Предыдущая вкладка" aria-label="Предыдущая вкладка">‹</button><button type="button" className="seo-menu-toggle" onClick={() => setMenuOpen((value) => !value)}>⋯</button><button type="button" className="seo-menu-arrow" onClick={() => movePage(1)} title="Следующая вкладка" aria-label="Следующая вкладка">›</button></div><nav><button type="button" onClick={() => navigate("home")}>Обзор</button>{PAGES.map(([key, short, title]) => <button type="button" key={key} title={title} className={page === key ? "is-active" : ""} onClick={() => navigate(key)}>{short}{key === "calltouch" && <em>Скоро</em>}</button>)}</nav></section>{toast}{page === "calltouch" ? <section className="seo-planned-empty" /> : <><section className="seo-page-heading"><h2>{PAGES.find(([key]) => key === page)?.[2]}</h2></section><section className="seo-filters"><div className="seo-toolbar"><button type="button" disabled={exporting} onClick={doExport}>{exporting ? "Экспорт…" : "Экспорт"}</button><button type="button" disabled={running} title={`Данные актуальны на: ${lastUpdated}`} onClick={refresh}>{running ? "Обновление…" : "Обновить"}</button><button type="button" onClick={() => setFilters(defaults())}>Очистить</button></div><div className="seo-filter-grid"><DashboardMultiSelect label="Название кампании" options={campaignOptions.map((item) => item.label)} selected={selectedCampaignNames} onApply={(names) => setFilters((old) => ({ ...old, campaigns: campaignOptions.filter((item) => names.includes(item.label)).map((item) => item.value) }))} /><DashboardMultiSelect label="Тип кампании" options={options.options?.campaign_types || []} selected={filters.campaign_types} onApply={(value) => setFilters((old) => ({ ...old, campaign_types: value }))} />{GROUP_FILTER_PAGES.has(page) && <DashboardMultiSelect label="Группа объявлений" options={groupOptions.map((item) => item.label)} selected={selectedGroupNames} onApply={(names) => setFilters((old) => ({ ...old, ad_groups: groupOptions.filter((item) => names.includes(item.label)).map((item) => item.value) }))} />}{page === "criteria" && <DashboardMultiSelect label="Ключевая фраза" options={criterionOptions.map((item) => item.label)} selected={selectedCriterionNames} onApply={(names) => setFilters((old) => ({ ...old, criteria: criterionOptions.filter((item) => names.includes(item.label)).map((item) => item.value) }))} />}<DayTypeToggle value={filters.day_types} onChange={(value) => setFilters((old) => ({ ...old, day_types: value }))} /><DateRangePicker start={filters.date_from} end={filters.date_to} resetRange={{ start: defaults().date_from, end: defaults().date_to }} onChange={({ start, end }) => setFilters((old) => ({ ...old, date_from: start, date_to: end }))} /></div></section>{loading ? <LoadingBlock /> : report && <>{!["lead_structure", "conversions"].includes(page) && <Cards summary={report.summary} />}{page === "summary" && <Summary report={report} openDays={openDays} />}{page === "weekly" && <WeeklyPage report={report} openDays={openDays} />}{page === "lead_structure" && <LeadStructure report={report} />}{page === "conversions" && <Conversions report={report} />}{page === "criteria" && <SimpleTable page={page} report={report} />}{page === "devices" && <Devices rows={report.rows} />}{page === "demography" && <Demography rows={report.rows} />}</>}</>}<DayModal state={dayModal} close={closeModal} /></main>;
}
