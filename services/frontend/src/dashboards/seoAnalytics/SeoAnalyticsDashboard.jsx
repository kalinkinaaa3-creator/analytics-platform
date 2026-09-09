import { cloneElement, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Legend, Line, LineChart,
  Pie, PieChart, Tooltip, XAxis, YAxis,
} from "recharts";

import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { CollisionSafeChartLabel } from "../../components/CollisionSafeChartLabel";
import {
  downloadSeoConfiguration, exportSeoReport, getSeoFilterOptions, getSeoRefreshState,
  getSeoReport, startSeoRefresh, uploadSeoConfiguration,
} from "../../api/seoAnalyticsApi";
import { SeoMonthRangePicker } from "./SeoMonthRangePicker";
import "../spinner.css";
import "./seo_analytics.css";


const PAGE_CONFIG = [
  ["visits", "Визиты", "Визиты из поисковых систем", "trend", "Анализ органического трафика, источников, аудитории и устройств."],
  ["new-visitors", "Новые", "Новые посетители из поисковых систем", "users", "Динамика и структура новой аудитории по полу, возрасту и регионам."],
  ["returning-visitors", "Вернувшиеся", "Вернувшиеся посетители из поисковых систем", "return", "Повторные посетители, возвратность и глубина просмотра."],
  ["search-phrases", "Фразы", "Поисковые фразы", "search", "Брендовые, небрендовые и неопределённые поисковые запросы."],
  ["traffic-change", "Изменение трафика", "Изменение трафика из поисковых систем", "pulse", "Сравнение органического трафика и анализ динамики."],
  ["conversions", "Все конверсии", "Все конверсии", "target", "Достижения целей и конверсия по всем целевым действиям."],
  ["unique-conversions", "Уникальные конверсии", "Уникальные конверсии", "unique", "Уникальные пользователи, совершившие целевые действия."],
  ["landing-pages", "Страницы входа", "Популярные страницы входа", "pages", "Популярные страницы входа и поведение пользователей."],
  ["calltouch", "Calltouch", "Данные Calltouch", "phone", "Данные о звонках будут доступны после подключения Calltouch."],
  ["positions", "Позиции", "Позиции в поисковых системах", "position", "Позиции сайта в Google и Яндексе после подключения сервиса."],
  ["competitors", "Конкуренты", "Конкуренты", "competitors", "Сравнение видимости и поискового трафика с конкурентами."],
];

const PAGE_TITLES = Object.fromEntries(PAGE_CONFIG.map(([key, , title]) => [key, title]));
let conversionSelectedGoals = [];
let uniqueConversionSelectedGoals = [];
const COLORS = ["#536f50", "#73869a", "#b98a3e", "#765f8e", "#aa584b", "#3f8a88", "#9aa197"];
const REGION_COLORS = ["#496846", "#c18b32", "#657f99", "#7e638f", "#a7574e", "#388783", "#8b955f", "#b06f38", "#596b79", "#89939c"];
const COLOR_MAP = { Google: "#536f50", "Яндекс": "#d69b32", "Остальные": "#89939c", "Брендовые": "#657f99", "Небрендовые": "#c18b32", "Брендовые запросы": "#657f99", "Небрендовые запросы": "#c18b32", "Не определено": "#89939c", "Мужской": "#536f50", "Женский": "#d8bd86" };
const GENDER_ORDER = ["Мужской", "Женский", "Не определено"];


function defaultFilters() { const now = new Date(); const dateFrom = `${now.getFullYear() - 3}-01-01`; const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate(); const dateTo = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`; return { date_from: dateFrom, date_to: dateTo, device: [], search_engine: [], region: [], robotness: [], phrase_type: [], product_category: [], query_group: [], landing_limit: 20 }; }
function number(value, digits = 0) { return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value || 0)); }
function percent(value, digits = 1) { return `${number(value, digits)}%`; }
function engineName(value) { const normalized = String(value || "Не определено").toLowerCase(); return normalized.includes("google") ? "Google" : normalized.includes("яндекс") || normalized.includes("yandex") ? "Яндекс" : "Остальные"; }
function genderName(value) { const normalized = String(value || "").toLowerCase(); return normalized.includes("жен") || normalized.includes("female") ? "Женский" : normalized.includes("муж") || normalized === "male" || normalized.includes("gender_male") ? "Мужской" : "Не определено"; }
function periodLabel(value) { const match = String(value || "").match(/(\d{4})-(\d{2})/); if (!match) return value; return new Date(Number(match[1]), Number(match[2]) - 1, 1).toLocaleString("ru-RU", { month: "short", year: "numeric" }).replace(/\s*г\.$/u, ""); }
function monthAxisTicks(rows = []) { const periods = rows.map((row) => row.period).filter(Boolean); const count = Math.min(periods.length, 10); if (count < 2) return periods; return [...new Set(Array.from({ length: count }, (_, index) => periods[Math.round(index * (periods.length - 1) / (count - 1))]))]; }
function landingRangeColor(value, maximum) { const ratio = maximum ? Number(value || 0) / maximum : 0; if (ratio >= .75) return "#355f43"; if (ratio >= .5) return "#527a6b"; if (ratio >= .25) return "#80976d"; return "#b49a58"; }
function shortenedUrl(value, limit = 68) { const url = String(value || ""); return url.length > limit ? `${url.slice(0, limit - 1)}…` : url; }
function saveBlob(blob, name) { const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url); }
function toggleSeries(setHidden, value) { setHidden((old) => { const next = new Set(old); if (next.has(value)) next.delete(value); else next.add(value); return next; }); }
function InteractiveLegend({ hidden, setHidden, payload, preserveOrder = false }) { return <Legend payload={payload} itemSorter={preserveOrder ? () => 0 : undefined} wrapperStyle={{ cursor: "pointer" }} formatter={(value) => <span className={hidden.has(value) ? "seo-legend-hidden" : ""}>{value}</span>} onClick={({ value }) => toggleSeries(setHidden, value)} />; }
function ChartTooltip({ active, payload = [], label, percentage = false, total = 0, digits = 0, formatLabel }) { if (!active || !payload.length) return null; const shownLabel = label ? (formatLabel ? formatLabel(label) : label) : payload[0]?.payload?.name; return <div className="seo-tooltip"><strong>{shownLabel}</strong>{payload.filter((item) => item.value !== undefined).map((item) => <div key={`${item.name}-${item.dataKey}`}><i style={{ background: item.color || item.fill }} /><span>{item.name || "Значение"}</span><b>{percentage ? percent(total ? Number(item.value) * 100 / total : item.value) : number(item.value, digits)}</b></div>)}</div>; }
function useHiddenSeries(initial = []) { return useState(() => new Set(initial)); }
function AgeAxisTick({ x, y, payload, horizontal = false }) { const full = String(payload?.value || ""); const limit = horizontal ? 12 : 15; const label = full.length > limit ? `${full.slice(0, limit - 1).trimEnd()}…` : full; return <g transform={`translate(${x},${y})`} className="seo-age-axis-tick"><title>{full}</title><text x={horizontal ? 0 : -8} y={horizontal ? 14 : 4} textAnchor={horizontal ? "middle" : "end"}>{label}</text></g>; }
function SmartLineLabel({ x, y, value, index = 0, total = 0, percentage = false, digits = 0, values = null, includeFirst = false }) { if (value === null || value === undefined || !Number.isFinite(Number(value))) return null; if (values) { const finite = values.map((item, itemIndex) => ({ value: Number(item), index: itemIndex })).filter((item) => Number.isFinite(item.value)); if (!finite.length) return null; const selected = new Set([finite.at(-1).index, finite.reduce((best, item) => item.value < best.value ? item : best).index, finite.reduce((best, item) => item.value > best.value ? item : best).index]); if (includeFirst) selected.add(finite[0].index); if (!selected.has(index)) return null; } else { const step = total <= 12 ? 1 : total <= 24 ? 2 : total <= 40 ? 3 : 4; if (index !== 0 && index !== total - 1 && index % step !== 0) return null; } return <CollisionSafeChartLabel x={x} y={Number(y) - 11} className="seo-line-value">{percentage ? percent(value, 1) : number(value, digits)}</CollisionSafeChartLabel>; }
function SignificantBarLabel({ x, y, width, value, index = 0, values = [] }) { if (!Number.isFinite(Number(value))) return null; const finite = values.map((item, itemIndex) => ({ value:Number(item), index:itemIndex })).filter((item) => Number.isFinite(item.value)); if (!finite.length) return null; const selected = new Set([finite[0].index, finite.at(-1).index, finite.reduce((best,item) => item.value < best.value ? item : best).index, finite.reduce((best,item) => item.value > best.value ? item : best).index]); if (!selected.has(index)) return null; return <CollisionSafeChartLabel x={Number(x) + Number(width) / 2} y={Number(y) - 5} className="seo-line-value">{number(value)}</CollisionSafeChartLabel>; }
function SafeChartContainer({ children }) { const rootRef = useRef(null); const [size, setSize] = useState(null); useLayoutEffect(() => { const root = rootRef.current; if (!root) return undefined; const update = (width, height) => { const nextWidth = Math.floor(width); const nextHeight = Math.floor(height); if (nextWidth <= 0 || nextHeight <= 0) return; setSize((old) => old?.width === nextWidth && old?.height === nextHeight ? old : { width: nextWidth, height: nextHeight }); }; const measure = () => { const bounds = root.getBoundingClientRect(); update(bounds.width, bounds.height); }; measure(); if (typeof ResizeObserver === "undefined") { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); } const observer = new ResizeObserver(([entry]) => { if (entry) update(entry.contentRect.width, entry.contentRect.height); }); observer.observe(root); return () => observer.disconnect(); }, []); return <div ref={rootRef} className="seo-safe-chart-container">{size ? cloneElement(children, { width: size.width, height: size.height }) : null}</div>; }


function PageIcon({ kind }) {
  const glyphs = { trend: "➤", users: "♙", return: "↶", search: "⌕", pulse: "↝", target: "◎", unique: "◇", pages: "▤", phone: "☎︎", position: "⌖", competitors: "◫" };
  return <span className="seo-page-icon" aria-hidden="true">{glyphs[kind] || "·"}</span>;
}


function SeoFilter({ label, options, selected, onApply }) {
  const names = useMemo(() => options.map((item) => item.name), [options]);
  return <DashboardMultiSelect label={label} options={names} selected={selected} onApply={onApply} />;
}


function LoadingBlock() { return <div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>; }


function seoMessageText(value, fallback = "Произошла ошибка.") {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) return value.map((item) => seoMessageText(item, "")).filter(Boolean).join(" ") || fallback;
  if (value && typeof value === "object") {
    for (const key of ["message", "detail", "file", "errors"]) {
      if (value[key]) return seoMessageText(value[key], fallback);
    }
    const combined = Object.values(value).map((item) => seoMessageText(item, "")).filter(Boolean).join(" ");
    if (combined) return combined;
  }
  return fallback;
}


function SeoToast({ message, type = "success", onClose }) {
  const text = seoMessageText(message, type === "error" ? "Произошла ошибка." : "Операция выполнена.");
  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(onClose, 30000);
    return () => window.clearTimeout(timer);
  }, [message, type, onClose]);
  if (!message) return null;
  return <div className={`seo-toast seo-toast--${type}`} role={type === "error" ? "alert" : "status"}><span>{text}</span><button type="button" aria-label="Закрыть уведомление" onClick={onClose}>×</button></div>;
}


function SeoToastStack({ error, notice, warnings = [], clearError, clearNotice }) {
  const [dismissedWarnings, setDismissedWarnings] = useState(() => new Set());
  const warningKey = warnings.map((item) => seoMessageText(item, "")).join("|");
  const visibleWarnings = warnings.map((warning, index) => ({ warning, index })).filter(({ index }) => !dismissedWarnings.has(index));
  if (!error && !notice && !visibleWarnings.length) return null;
  return <div className="seo-toast-stack" aria-live="polite">{error && <SeoToast message={error} type="error" onClose={clearError} />}{notice && <SeoToast message={notice} onClose={clearNotice} />}{visibleWarnings.map(({ warning, index }) => <SeoToast key={`${warningKey}-${index}`} message={warning} type="warning" onClose={() => setDismissedWarnings((current) => new Set(current).add(index))} />)}</div>;
}


function FloatingHelp({ children, label = "Пояснение расчёта" }) {
  const anchorRef = useRef(null);
  const [position, setPosition] = useState(null);
  const open = () => {
    const bounds = anchorRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const width = Math.min(310, window.innerWidth - 24);
    const left = Math.max(12, Math.min(bounds.left + bounds.width / 2 - width / 2, window.innerWidth - width - 12));
    const above = bounds.top > 180;
    setPosition({ left, width, top: above ? bounds.top - 10 : bounds.bottom + 10, above });
  };
  const close = () => setPosition(null);
  return <><span ref={anchorRef} className="seo-floating-help" tabIndex={0} role="button" aria-label={label} onClick={(event) => event.stopPropagation()} onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close}>i</span>{position && createPortal(<span className={`seo-floating-help-tooltip${position.above ? " is-above" : ""}`} role="tooltip" style={{ left:position.left, top:position.top, width:position.width }}>{children}</span>, document.body)}</>;
}


function LandingTrack({ url, visits, share, maximum }) {
  const anchorRef = useRef(null);
  const [position, setPosition] = useState(null);
  const open = () => {
    const bounds = anchorRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const width = Math.min(310, window.innerWidth - 24);
    const left = Math.max(12, Math.min(bounds.left + bounds.width / 2 - width / 2, window.innerWidth - width - 12));
    const above = window.innerHeight - bounds.bottom < 135 && bounds.top > 135;
    setPosition({ left, width, top: above ? bounds.top - 9 : bounds.bottom + 9, above });
  };
  const close = () => setPosition(null);
  return <><div ref={anchorRef} className="seo-landing-track" tabIndex={0} onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close}><i style={{ width: `${visits * 100 / maximum}%`, background: landingRangeColor(visits, maximum) }} /></div>{position && createPortal(<span className={`seo-landing-track-tooltip seo-landing-track-tooltip--floating${position.above ? " is-above" : ""}`} role="tooltip" style={{ left:position.left, top:position.top, width:position.width }}><b title={url}>{shortenedUrl(url)}</b><em><span>Визиты</span><strong>{number(visits)}</strong></em><em><span>Доля</span><strong>{percent(share)}</strong></em></span>, document.body)}</>;
}


function MetricCard({ label, value, format = "number", hint, help }) {
  const shown = value === null || value === undefined ? "—" : format === "percent" ? percent(value) : format === "decimal" ? number(value, 2) : number(value);
  return <article className={`seo-card${help ? " seo-card--has-help" : ""}`} title={hint || ""}><span className="seo-card-label"><span>{label}</span>{help && <span className="seo-card-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{help}</span></span>}</span><strong>{shown}</strong></article>;
}


function Cards({ page, cards = {} }) {
  if (page === "conversions") return null;
  if (page === "unique-conversions") return null;
  if (page === "traffic-change") return null;
  if (!Object.keys(cards).length) return null;
  const depthVisits = Number(cards.visits || 0);
  const pageviews = Number(cards.pageviews ?? (Number(cards.page_depth || 0) * depthVisits));
  const shareHelp = <><span>Рассчитывается от показателя «Посетители за период».</span><b className="seo-card-help-detail">Посетители за период: <strong>{number(cards.users)}</strong></b></>;
  const pageDepthHelp = <><span>Глубина просмотра = общее количество просмотров страниц ÷ общее количество визитов. За выбранный период суммы делятся друг на друга; месячные значения не усредняются.</span><b className="seo-card-help-detail">Просмотры страниц: <strong>{number(pageviews)}</strong><br />Визиты: <strong>{number(depthVisits)}</strong></b></>;
  const visible = page === "new-visitors" ? [["users", "Посетители за период"], ["page_depth", "Глубина просмотра", "decimal", pageDepthHelp], ["new_users", "Новые посетители"], ["new_share", "Доля новых", "percent", shareHelp]] : page === "returning-visitors" ? [["users", "Посетители за период"], ["page_depth", "Глубина просмотра", "decimal", pageDepthHelp], ["returned_users", "Вернувшиеся"], ["returned_share", "Доля вернувшихся", "percent", shareHelp]] : [["visits", "Визиты за период"], ["page_depth", "Глубина просмотра", "decimal", pageDepthHelp], ["new_users", "Новые посетители"], ["new_share", "Доля новых", "percent", shareHelp]];
  return <div className="seo-cards">{visible.map(([key, label, format, help]) => <MetricCard key={key} label={label} value={cards[key]} format={format} help={help} />)}</div>;
}


function TrafficSummaryCard({ label, value, previous, comparisonLabel, previousLabel, previousPeriod, formula }) {
  const change = Number(previous) ? (Number(value || 0) / Number(previous) - 1) * 100 : null;
  return <article className="seo-card seo-traffic-card"><span className="seo-traffic-card-label">{label} <FloatingHelp>{formula}</FloatingHelp></span><div><strong>{number(value)}</strong>{change === null ? <em>— {comparisonLabel}</em> : <em className={change > 0 ? "is-positive" : change < 0 ? "is-negative" : ""}><i aria-hidden="true">{change > 0 ? "▲" : change < 0 ? "▼" : "•"}</i> {percent(Math.abs(change))} {comparisonLabel}</em>}</div><small><span className="seo-traffic-period-hint" tabIndex={0} data-tooltip={`Период: ${previousPeriod || "нет данных"}`}>{previousLabel} <i aria-hidden="true">i</i></span>: <b>{number(previous)}</b></small></article>;
}


function TrafficSummaryCards({ cards = {}, series = [], comparison = [], baseline = [] }) {
  const periods = trafficTotals(series).map((row) => row.period).filter(Boolean).sort();
  const comparisonPeriods = trafficTotals(comparison).map((row) => row.period).filter(Boolean).sort();
  const currentPeriod = periods.at(-1) || "";
  const previousMonthPeriod = periods.at(-2) || trafficTotals(baseline).map((row) => row.period).filter(Boolean).sort().at(-1) || "";
  const previousYear = currentPeriod ? String(Number(currentPeriod.slice(0, 4)) - 1) : "";
  const currentYearPeriods = periods.filter((period) => period.startsWith(currentPeriod.slice(0, 4)));
  const previousYearPeriods = comparisonPeriods.filter((period) => period.startsWith(previousYear));
  const currentYearPeriod = currentYearPeriods.length ? `${periodLabel(currentYearPeriods[0])} — ${periodLabel(currentYearPeriods.at(-1))}` : currentPeriod.slice(0, 4);
  const previousYearPeriod = previousYearPeriods.length ? `${periodLabel(previousYearPeriods[0])} — ${periodLabel(previousYearPeriods.at(-1))}` : previousYear;
  return <div className="seo-traffic-cards"><TrafficSummaryCard label={`Визиты · текущий месяц · ${periodLabel(currentPeriod)}`} value={cards.current_month} previous={cards.previous_month} comparisonLabel="к прошлому месяцу" previousLabel="Прошлый месяц" previousPeriod={periodLabel(previousMonthPeriod)} formula="Изменение к прошлому месяцу = (Визиты текущего месяца − Визиты прошлого месяца) ÷ Визиты прошлого месяца × 100%." /><TrafficSummaryCard label={`Визиты · текущий год · ${currentYearPeriod}`} value={cards.current_period} previous={cards.previous_year_period} comparisonLabel="к прошлому году" previousLabel="Прошлый год" previousPeriod={previousYearPeriod} formula="Изменение к прошлому году = (Визиты текущего периода − Визиты аналогичного периода прошлого года) ÷ Визиты аналогичного периода прошлого года × 100%." /></div>;
}


function flattenSeries(series = [], metric = "visits", normalizeNames = true) {
  const rows = new Map();
  series.forEach((item) => (item.points || []).forEach((point) => { const row = rows.get(point.period) || { period: point.period }; const name = normalizeNames ? engineName(item.name) : item.name; row[name] = Number(row[name] || 0) + Number(point[metric] || 0); rows.set(point.period, row); }));
  return [...rows.values()];
}


function groupEngineSeries(series = [], selectedEngines = []) {
  if (selectedEngines.length) return series;
  const groups = new Map();
  series.forEach((item) => {
    const name = engineName(item.name);
    const group = groups.get(name) || new Map();
    (item.points || []).forEach((point) => {
      const merged = group.get(point.period) || { period: point.period };
      Object.entries(point).forEach(([key, value]) => {
        if (key !== "period" && !["new_share", "returned_share", "page_depth"].includes(key) && typeof value === "number") merged[key] = Number(merged[key] || 0) + value;
      });
      merged.__pageviews = Number(merged.__pageviews || 0) + Number(point.page_depth || 0) * Number(point.visits || 0);
      group.set(point.period, merged);
    });
    groups.set(name, group);
  });
  return [...groups].map(([name, points]) => ({ key: name, name, points: [...points.values()].map((point) => ({ ...point, new_share: point.users ? Number(point.new_users || 0) * 100 / point.users : 0, returned_share: point.users ? Number(point.returned_users || 0) * 100 / point.users : 0, page_depth: point.visits ? point.__pageviews / point.visits : 0 })).sort((a, b) => a.period.localeCompare(b.period)) }));
}


function SeriesChart({ title, series, metric = "visits", normalizeNames = true, sparseLabels = false, includeFirstLabel = false, defaultHiddenNames = [] }) {
  const data = flattenSeries(series, metric, normalizeNames); const names = [...new Set(series.map((item) => item.name))]; const [hidden, setHidden] = useState(() => new Set([...(names.includes("Остальные") ? ["Остальные"] : []), ...defaultHiddenNames]));
  const percentage = metric.endsWith("_share");
  return <article className="seo-panel"><header><h3>{title}</h3></header><div className="seo-chart"><SafeChartContainer><LineChart data={data} margin={{ top: 34, right: 30, bottom: 8, left: 4 }}><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="period" ticks={monthAxisTicks(data)} tickFormatter={periodLabel} tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={10} /><YAxis tick={{ fontSize: 11 }} width={48} tickFormatter={(value) => percentage ? `${number(value)}%` : number(value)} /><Tooltip content={<ChartTooltip percentage={percentage} digits={metric === "page_depth" ? 2 : 0} formatLabel={periodLabel} />} /><InteractiveLegend hidden={hidden} setHidden={setHidden} />{names.map((name, index) => <Line key={name} type="monotone" dataKey={name} name={name} hide={hidden.has(name)} stroke={COLOR_MAP[name] || COLORS[index % COLORS.length]} strokeWidth={3.2} dot={{ r: 3.5 }} activeDot={{ r: 5.5 }} label={<SmartLineLabel total={data.length} seriesIndex={index} percentage={percentage} digits={metric === "page_depth" ? 2 : 0} values={sparseLabels ? data.map((row) => row[name]) : null} includeFirst={includeFirstLabel} />} />)}</LineChart></SafeChartContainer></div></article>;
}


function RegionPie({ rows = [], title, metric, selectedRegions = [] }) {
  const allRegions = rows.map((row) => ({ name: row.dimensions?.[0]?.name || "Не определено", value: Number(row[metric] || 0) })).filter((row) => row.value > 0).sort((a, b) => b.value - a.value);
  const data = selectedRegions.length || allRegions.length <= 10 ? allRegions : [...allRegions.slice(0, 9), { name: "Остальные", value: allRegions.slice(9).reduce((sum, row) => sum + row.value, 0) }];
  const total = data.reduce((sum, row) => sum + row.value, 0);
  return <article className="seo-panel seo-panel--regions"><header><h3>{title}</h3></header><div className="seo-region-layout"><div className="seo-chart seo-region-pie"><SafeChartContainer><PieChart>{data.length ? <Pie data={data} dataKey="value" nameKey="name" outerRadius="76%" label={false}>{data.map((row, index) => <Cell key={row.name} fill={REGION_COLORS[index % REGION_COLORS.length]} />)}</Pie> : <text x="50%" y="50%" textAnchor="middle" className="seo-pie-empty">Нет данных</text>}<Tooltip content={<ChartTooltip percentage total={total} />} /></PieChart></SafeChartContainer></div><div className="seo-region-ranking">{data.map((row, index) => { const share = total ? row.value * 100 / total : 0; return <div className="seo-region-row seo-region-row--ranked" key={row.name}><i className="seo-region-rank">{index + 1}</i><span title={row.name}>{row.name}</span><div className="seo-region-track"><i style={{ width: `${share}%`, background: REGION_COLORS[index % REGION_COLORS.length] }} /></div><b>{number(row.value)}</b><strong>{percent(share)}</strong></div>; })}</div></div></article>;
}


function ageRank(value) { const normalized = String(value || "").toLowerCase().replace(/[‑–—]/g, "-").replace(/ё/g, "е"); if (normalized.includes("младше 18") || normalized.includes("менее 18")) return 0; if (normalized.includes("18-24")) return 1; if (normalized.includes("25-34")) return 2; if (normalized.includes("35-44")) return 3; if (normalized.includes("45-54")) return 4; if (normalized.includes("55") && (normalized.includes("старше") || normalized.includes("и более") || normalized.includes("+"))) return 5; if (normalized.includes("не определено") || normalized.includes("неизвест")) return 6; return 7; }
function DemographicsGenderChart({ rows = [], title, metric, percentStack = false }) {
  const shareMetric = metric === "new_share" || metric === "returned_share"; const [hidden, setHidden] = useHiddenSeries(shareMetric ? ["Не определено"] : []); const grouped = new Map(); rows.forEach((row) => { const age = row.dimensions?.[0]?.name || "Не определено"; const gender = genderName(row.dimensions?.[1]?.name); const item = grouped.get(age) || { age, Мужской: 0, Женский: 0, "Не определено": 0, Мужской_users: 0, Женский_users: 0, "Не определено_users": 0, Мужской_new: 0, Женский_new: 0, "Не определено_new": 0 }; if (shareMetric) { item[`${gender}_users`] += Number(row.users || 0); item[`${gender}_new`] += Number(row.new_users || 0); } else { const value = metric === "returned_users" ? Math.max(0, Number(row.users || 0) - Number(row.new_users || 0)) : Number(row[metric] || 0); item[gender] += value; } grouped.set(age, item); }); const data = [...grouped.values()].sort((a, b) => ageRank(a.age) - ageRank(b.age)); const genders = GENDER_ORDER.filter((gender) => data.some((row) => Number(row[gender]) > 0 || Number(row[`${gender}_users`]) > 0)); if (shareMetric) data.forEach((row) => genders.forEach((gender) => { const users = row[`${gender}_users`]; const newUsers = row[`${gender}_new`]; row[gender] = users ? (metric === "new_share" ? newUsers : Math.max(0, users - newUsers)) * 100 / users : 0; })); if (percentStack) data.forEach((row) => { const total = genders.reduce((sum, gender) => sum + Number(row[gender] || 0), 0); genders.forEach((gender) => { row[gender] = total ? row[gender] * 100 / total : 0; }); });
  const percentageMetric = percentStack || metric.endsWith("_share");
  return <article className="seo-panel"><header><h3>{title}</h3></header><div className="seo-chart"><SafeChartContainer><BarChart data={data} layout="vertical" margin={{ top: 10, right: 28, left: 20, bottom: 8 }}><CartesianGrid strokeDasharray="3 4" horizontal={false} /><XAxis type="number" domain={percentageMetric ? [0, 100] : undefined} ticks={percentageMetric ? [0, 25, 50, 75, 100] : undefined} tickFormatter={(value) => percentageMetric ? `${number(value)}%` : number(value)} /><YAxis type="category" dataKey="age" width={108} interval={0} tick={<AgeAxisTick />} /><Tooltip content={<ChartTooltip percentage={percentageMetric} />} /><InteractiveLegend hidden={hidden} setHidden={setHidden} preserveOrder />{genders.map((name) => <Bar key={name} dataKey={name} hide={hidden.has(name)} stackId={percentStack ? "total" : undefined} fill={COLOR_MAP[name]} radius={[0, 3, 3, 0]}>{percentStack && <LabelList dataKey={name} position="center" className={`seo-bar-percent seo-bar-percent--${name === "Женский" ? "female" : "male"}`} formatter={(value) => value >= 10 ? percent(value, 0) : ""} />}</Bar>)}</BarChart></SafeChartContainer></div></article>;
}


function LandingPagesChart({ rows = [], summary = {}, limit = 20, onLimitChange }) {
  const listRef = useRef(null);
  const [listScrollable, setListScrollable] = useState(false);
  const maximum = Math.max(...rows.map((row) => Number(row.visits || 0)), 1);
  const totalVisits = Number(summary.total_visits || rows[0]?.total_visits || 0);
  const selectedVisitsFallback = rows.reduce((sum, row) => sum + Number(row.visits || 0), 0);
  const selectedVisits = Number(summary.selected_visits ?? summary.top20_visits ?? selectedVisitsFallback);
  const selectedShare = totalVisits ? selectedVisits * 100 / totalVisits : Number(summary.selected_share ?? summary.top20_share ?? 0);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return undefined;
    const update = () => {
      const rowsHeight = Array.from(list.children).reduce((height, row) => height + row.getBoundingClientRect().height, 0);
      const scrollable = rowsHeight - list.clientHeight > 1;
      if (!scrollable) list.scrollTop = 0;
      setListScrollable(scrollable);
    };
    list.scrollTop = 0;
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const observer = new ResizeObserver(update);
    observer.observe(list);
    return () => observer.disconnect();
  }, [rows, limit]);
  return <article className="seo-panel seo-panel--landing-pages"><div className="seo-landing-sticky"><header><h3>Топ-<select aria-label="Количество страниц" value={limit} onChange={(event) => onLimitChange(Number(event.target.value))}>{[10, 20, 30, 50, 100].map((value) => <option key={value} value={value}>{value}</option>)}</select> страниц входа</h3></header><div className="seo-landing-head"><span>Страница</span><i /><b>Визиты</b><strong><span>Доля</span> <FloatingHelp>Доля страницы = Визиты страницы ÷ Общее количество визитов × 100%.<b>Общее количество визитов: <strong>{number(totalVisits)}</strong></b></FloatingHelp></strong></div></div><div ref={listRef} className={`seo-landing-list${listScrollable ? " is-scrollable" : ""}`}>{rows.map((row, index) => { const url = row.start_url || row.dimensions?.[0]?.name || ""; const visits = Number(row.visits || 0); const share = totalVisits ? visits * 100 / totalVisits : 0; return <div className="seo-landing-row" key={url || index}><span className="seo-landing-rank">{index + 1}</span><a className="seo-landing-url" href={url} target="_blank" rel="noreferrer" title={url}>{url}</a><LandingTrack url={url} visits={visits} share={share} maximum={maximum} /><b>{number(visits)}</b><strong>{percent(share)}</strong></div>; })}</div><footer className="seo-landing-summary"><span>Итого</span><i /><b>{number(selectedVisits)}</b><strong className="seo-landing-summary-share"><span>{percent(selectedShare)}</span><FloatingHelp>Итоговая доля = Визиты страниц из выбранного топа ÷ Общее количество визитов × 100%.<b>Визиты по топу: <strong>{number(selectedVisits)}</strong><br />Общее количество визитов: <strong>{number(totalVisits)}</strong></b></FloatingHelp></strong></footer></article>;
}


function PhraseStructure({ series = [] }) {
  const data = series.map((item) => ({ name: item.name, value: (item.points || []).reduce((sum, point) => sum + Number(point.visits || 0), 0) })).filter((row) => row.value > 0).sort((a, b) => b.value - a.value); const total = data.reduce((sum, row) => sum + row.value, 0);
  return <article className="seo-panel seo-panel--regions seo-panel--phrases"><header><h3>Структура визитов по типу поисковой фразы</h3></header><div className="seo-region-layout"><div className="seo-chart seo-region-pie"><SafeChartContainer><PieChart>{data.length ? <Pie data={data} dataKey="value" nameKey="name" innerRadius={0} outerRadius="75%" label={false}>{data.map((row) => <Cell key={row.name} fill={COLOR_MAP[row.name] || COLOR_MAP["Не определено"]} />)}</Pie> : <text x="50%" y="50%" textAnchor="middle" className="seo-pie-empty">Нет данных</text>}<Tooltip content={<ChartTooltip percentage total={total} />} /></PieChart></SafeChartContainer></div><div className="seo-region-ranking">{data.map((row) => { const share = total ? row.value * 100 / total : 0; return <div className="seo-region-row" key={row.name}><span title={row.name}>{row.name}</span><div className="seo-region-track"><i style={{ width:`${share}%`, background:COLOR_MAP[row.name] || COLOR_MAP["Не определено"] }} /></div><b>{number(row.value)}</b><strong>{percent(share)}</strong></div>; })}</div></div></article>;
}


function trafficTotals(series = []) { const totals = new Map(); series.forEach((item) => (item.points || []).forEach((point) => totals.set(point.period, Number(totals.get(point.period) || 0) + Number(point.visits || 0)))); return [...totals].map(([period, visits]) => ({ period, visits })); }
function periodParts(period) { const match = String(period).match(/(\d{4})-(\d{2})/); return match ? { year: match[1], month: Number(match[2]) } : { year: String(period), month: 1 }; }

function TrafficDeltaChart({ series = [], comparison = [], baseline = [], yearly = false }) { const [hidden, setHidden] = useState(() => new Set(series.some((item) => item.name === "Остальные") ? ["Остальные"] : [])); const rows = new Map(); const names = new Set(); const comparisonByName = new Map(comparison.map((item) => [item.name, item.points || []])); const baselineByName = new Map(baseline.map((item) => [item.name, Number(item.points?.at(-1)?.visits || 0)])); series.forEach((item) => { const name = item.name || "Не определено"; names.add(name); const values = new Map([...(comparisonByName.get(item.name) || []), ...(item.points || [])].map((point) => { const part = periodParts(point.period); return [`${part.year}-${part.month}`, Number(point.visits || 0)]; })); (item.points || []).forEach((point, index, points) => { const part = periodParts(point.period); const previous = yearly ? values.get(`${Number(part.year) - 1}-${part.month}`) : index === 0 ? baselineByName.get(name) : Number(points[index - 1]?.visits || 0); const row = rows.get(point.period) || { period: point.period }; const change = previous ? (Number(point.visits || 0) / previous - 1) * 100 : null; if (change !== null) row[name] = change; rows.set(point.period, row); }); }); const chartRows = [...rows.values()]; return <article className={`seo-panel ${yearly ? "seo-traffic-yearly" : "seo-traffic-monthly"}`}><header><h3>{yearly ? "Изменение визитов по отношению к прошлому году" : "Изменение визитов по отношению к прошлому месяцу"}</h3></header><div className="seo-chart"><SafeChartContainer><LineChart data={chartRows} margin={{ top: 34, right: 30, bottom: 8, left: 4 }}><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="period" ticks={monthAxisTicks(chartRows)} tickFormatter={periodLabel} interval="preserveStartEnd" minTickGap={10} /><YAxis tickFormatter={(value) => `${number(value)}%`} /><Tooltip content={<ChartTooltip percentage formatLabel={periodLabel} />} /><InteractiveLegend hidden={hidden} setHidden={setHidden} />{[...names].map((name, index) => <Line key={name} dataKey={name} hide={hidden.has(name)} stroke={COLOR_MAP[name] || COLORS[index % COLORS.length]} strokeWidth={3.2} dot={{ r: 3.5 }} activeDot={{ r: 5.5 }} label={<SmartLineLabel total={chartRows.length} seriesIndex={index} percentage values={chartRows.map((row) => row[name])} />} />)}</LineChart></SafeChartContainer></div></article>; }

function TrafficMatrix({ series = [], comparison = [], baseline = [] }) {
  const [comparisonMode, setComparisonMode] = useState("month");
  useEffect(() => { const reset = () => setComparisonMode("month"); window.addEventListener("seo:clear-filters", reset); return () => window.removeEventListener("seo:clear-filters", reset); }, []);
  const data = trafficTotals(series);
  const comparisonData = trafficTotals(comparison);
  const baselineData = trafficTotals(baseline);
  const lookup = new Map([...comparisonData, ...baselineData, ...data].map((item) => [item.period, Number(item.visits || 0)]));
  const years = [...new Set(data.map((row) => periodParts(row.period).year))].sort();
  const today = new Date();
  const rows = Array.from({ length: 12 }, (_, index) => {
    const month = index + 1;
    const row = { month: new Date(2026, index, 1).toLocaleString("ru-RU", { month: "long" }) };
    years.forEach((year) => {
      const future = Number(year) > today.getFullYear() || (Number(year) === today.getFullYear() && month > today.getMonth() + 1);
      const period = `${year}-${String(month).padStart(2, "0")}-01`;
      const value = data.find((item) => item.period === period)?.visits;
      const previousPeriod = comparisonMode === "year"
        ? `${Number(year) - 1}-${String(month).padStart(2, "0")}-01`
        : month === 1 ? `${Number(year) - 1}-12-01` : `${year}-${String(month - 1).padStart(2, "0")}-01`;
      const previous = lookup.get(previousPeriod);
      row[year] = future ? null : value === undefined ? 0 : Number(value);
      row[`${year}_change`] = !future && Number(previous) > 0 ? (row[year] / previous - 1) * 100 : null;
    });
    return row;
  });
  const changeTitle = comparisonMode === "month" ? "К прош. месяцу" : "К прош. году";
  return <article className="seo-panel seo-traffic-matrix"><header><h3>Визиты по годам и месяцам с изменением</h3><div className="seo-traffic-matrix-toggle" role="group" aria-label="Период сравнения"><button type="button" className={comparisonMode === "month" ? "is-active" : ""} aria-pressed={comparisonMode === "month"} onClick={() => setComparisonMode("month")}>К прошлому месяцу <FloatingHelp>Изменение = (Визиты месяца − Визиты предыдущего месяца) ÷ Визиты предыдущего месяца × 100%.</FloatingHelp></button><button type="button" className={comparisonMode === "year" ? "is-active" : ""} aria-pressed={comparisonMode === "year"} onClick={() => setComparisonMode("year")}>К прошлому году <FloatingHelp>Изменение = (Визиты месяца − Визиты того же месяца прошлого года) ÷ Визиты того же месяца прошлого года × 100%.</FloatingHelp></button></div></header><div className="seo-table-wrap"><table className="seo-table"><thead><tr><th rowSpan="2">Месяц</th>{years.map((year) => <th key={year} colSpan="2">{year}</th>)}</tr><tr>{years.flatMap((year) => [<th key={`${year}-v`}>Визиты</th>, <th key={`${year}-c`}>{changeTitle}</th>])}</tr></thead><tbody>{rows.map((row) => <tr key={row.month}><td>{row.month}</td>{years.flatMap((year) => { const change = row[`${year}_change`]; const available = row[year] !== null && change !== null; const width = available ? Math.min(Math.abs(change), 100) / 2 : 0; return [<td key={`${year}-v`}>{row[year] === null ? "" : number(row[year])}</td>, <td key={`${year}-c`} className={`seo-traffic-change-cell ${available ? "has-change" : ""} ${change > 0 ? "is-positive" : change < 0 ? "is-negative" : ""}`}>{available && <><i className={change < 0 ? "is-negative" : "is-positive"} style={{ width: `${width}%` }} /><span className="seo-traffic-change-value"><span aria-hidden="true">{change > 0 ? "▲" : change < 0 ? "▼" : ""}</span> {percent(change)}</span></>}</td>]; })}</tr>)}</tbody></table></div></article>;
}

function TrafficYearsChart({ series = [] }) { const data = trafficTotals(series); const rows = new Map(); const years = new Set(); data.forEach((item) => { const { year, month } = periodParts(item.period); years.add(year); const row = rows.get(month) || { month: new Date(2026, month - 1, 1).toLocaleString("ru-RU", { month: "short" }) }; row[year] = item.visits; rows.set(month, row); }); const sortedYears = [...years].sort(); const [hidden, setHidden] = useState(() => new Set(sortedYears.slice(0, -2))); const chartRows = [...rows.values()]; return <article className="seo-panel seo-traffic-years"><header><h3>Визиты по годам и месяцам</h3></header><div className="seo-chart"><SafeChartContainer><LineChart data={chartRows} margin={{ top:34, right:30, bottom:8, left:4 }}><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="month" interval="preserveStartEnd" minTickGap={42} /><YAxis /><Tooltip content={<ChartTooltip />} /><InteractiveLegend hidden={hidden} setHidden={setHidden} />{sortedYears.map((year, index) => <Line key={year} dataKey={year} hide={hidden.has(year)} stroke={COLORS[index % COLORS.length]} strokeWidth={3.2} dot={{ r:3.5 }} activeDot={{ r:5.5 }} label={<SmartLineLabel total={chartRows.length} seriesIndex={index} values={chartRows.map((row) => row[year])} />} />)}</LineChart></SafeChartContainer></div></article>; }


function ConversionCards({ cards = {}, goals = [] }) {
  const denominator = Number(cards.denominator || 0);
  const items = [{ id: "all", name: "Все цели", value: Number(cards.total || 0), conversion: Number(cards.conversion || 0) }, ...goals.map((goal) => ({ ...goal, value: Number(goal.value || 0), conversion: denominator ? Number(goal.value || 0) * 100 / denominator : 0 }))];
  return <section className="seo-unique-kpis seo-conversion-kpis">{items.map((item, index) => <article className={index === 0 ? "is-total" : ""} style={{ "--goal-color": index === 0 ? "#75866e" : COLORS[(index - 1) % COLORS.length] }} key={item.id}><span title={item.name}>{item.name}</span><strong>{number(item.value)}</strong><footer><span>Конверсия <FloatingHelp>{index === 0 ? "Сумма достижений всех активных целей ÷ визиты × 100%." : "Достижения выбранной цели ÷ визиты × 100%."}<b>Визиты за период: <strong>{number(denominator)}</strong></b></FloatingHelp></span><b>{percent(item.conversion)}</b></footer></article>)}</section>;
}


function ConversionTooltip({ active, payload = [], label, goals = [] }) {
  if (!active || !payload.length) return null;
  const colors = new Map(goals.map((goal, index) => [goal.name, COLORS[index % COLORS.length]]));
  const goalRows = payload.filter((item) => colors.has(item.name) && item.value !== undefined).sort((a, b) => Number(b.value) - Number(a.value));
  const conversion = payload.find((item) => item.dataKey === "conversion");
  return <div className="seo-tooltip"><strong>{periodLabel(label)}</strong>{conversion?.value !== undefined && <div><i style={{ background: "#a66a35" }} /><span>Конверсия</span><b>{percent(conversion.value)}</b></div>}{goalRows.map((item) => <div key={item.name}><i style={{ background: colors.get(item.name) }} /><span>{item.name}</span><b>{number(item.value)}</b></div>)}</div>;
}


function ConversionChart({ data = [], goals = [], selectedGoals = [], onGoalChange }) {
  const [hidden, setHidden] = useHiddenSeries();
  const rowsByPeriod = new Map();
  data.forEach((series) => (series.points || []).forEach((point) => { const row = rowsByPeriod.get(point.period) || { period: point.period, denominator: Number(point.denominator || 0) }; row.denominator = Math.max(row.denominator, Number(point.denominator || 0)); goals.forEach((goal) => { row[goal.name] = Number(row[goal.name] || 0) + Number(point[String(goal.id)] || 0); }); if (point.unique_total !== undefined) row.unique_total = Number(point.unique_total || 0); rowsByPeriod.set(point.period, row); }));
  const rows = [...rowsByPeriod.values()].sort((a, b) => a.period.localeCompare(b.period));
  const selectedIds = new Set(selectedGoals.map(String));
  const visibleGoals = selectedIds.size ? goals.filter((goal) => selectedIds.has(String(goal.id))) : goals;
  const activeGoals = visibleGoals.filter((goal) => !hidden.has(goal.name));
  rows.forEach((row) => { row.displayed_value = activeGoals.reduce((sum, goal) => sum + Number(row[goal.name] || 0), 0); row.conversion = row.denominator ? row.displayed_value * 100 / row.denominator : 0; });
  const displayedValues = rows.map((row) => row.displayed_value);
  const selectedNames = visibleGoals.length === goals.length ? [] : visibleGoals.map((goal) => goal.name);
  const changeGoals = (names) => { onGoalChange(goals.filter((goal) => names.includes(goal.name)).map((goal) => String(goal.id))); setHidden((current) => new Set(current.has("Конверсия") ? ["Конверсия"] : [])); };
  return <article className="seo-panel seo-panel--wide seo-conversion-panel"><header><h3>Цели и конверсии</h3><div className="seo-goal-filter"><DashboardMultiSelect label="Цели" options={goals.map((goal) => goal.name)} selected={selectedNames} onApply={changeGoals} /></div></header><div className="seo-conversion-layout"><div className="seo-chart seo-chart--large seo-conversion-chart"><button type="button" className={`seo-conversion-line-key${hidden.has("Конверсия") ? " is-hidden" : ""}`} onClick={() => toggleSeries(setHidden, "Конверсия")} aria-pressed={!hidden.has("Конверсия")}><i />Конверсия</button><SafeChartContainer><ComposedChart data={rows} margin={{ top: 32, right: 18, bottom: 8, left: 4 }}><defs>{goals.map((goal, index) => { const color = COLORS[index % COLORS.length]; return <linearGradient id={`seo-goal-gradient-${index}`} key={goal.id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".76" /><stop offset="24%" stopColor={color} stopOpacity=".88" /><stop offset="68%" stopColor={color} stopOpacity=".98" /><stop offset="100%" stopColor={color} /></linearGradient>; })}</defs><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="period" ticks={monthAxisTicks(rows)} tickFormatter={periodLabel} interval="preserveStartEnd" minTickGap={10} /><YAxis yAxisId="value" /><YAxis yAxisId="percent" orientation="right" tickFormatter={(value) => `${number(value)}%`} /><Tooltip content={<ConversionTooltip goals={goals} />} position={{ y: -88 }} allowEscapeViewBox={{ x: false, y: true }} offset={14} wrapperStyle={{ zIndex: 1000 }} /><InteractiveLegend hidden={hidden} setHidden={setHidden} />{visibleGoals.map((goal) => { const index = goals.findIndex((item) => String(item.id) === String(goal.id)); return <Bar className="seo-goal-bar" yAxisId="value" key={goal.id} dataKey={goal.name} hide={hidden.has(goal.name)} stackId="goals" fill={`url(#seo-goal-gradient-${index})`} stroke={COLORS[index % COLORS.length]} strokeWidth={0.7} />; })}<Line yAxisId="value" dataKey="displayed_value" name="Итого" stroke="transparent" dot={false} activeDot={false} legendType="none" label={<SmartLineLabel total={rows.length} values={displayedValues} includeFirst />} /><Line yAxisId="percent" type="monotone" dataKey="conversion" name="Конверсия" legendType="none" hide={hidden.has("Конверсия")} stroke="#a66a35" strokeWidth={3.2} dot={{ r:3.5 }} activeDot={{ r:5.5 }} /></ComposedChart></SafeChartContainer></div></div></article>;
}


function ConversionsSection({ report = {} }) { const goals = report.cards?.goals || []; const [selectedGoals, setSelectedGoalsState] = useState(conversionSelectedGoals); const setSelectedGoals = (value) => { conversionSelectedGoals = value; setSelectedGoalsState(value); }; useEffect(() => { const reset = () => setSelectedGoals([]); window.addEventListener("seo:clear-filters", reset); return () => window.removeEventListener("seo:clear-filters", reset); }, []); return <><ConversionCards cards={report.cards || {}} goals={goals} /><div className="seo-report-grid seo-conversion-grid"><ConversionChart data={report.charts?.dynamics || []} goals={goals} selectedGoals={selectedGoals} onGoalChange={setSelectedGoals} /></div></>; }


function GoalDemographics({ rows = [], goals = [], selectedGoals = [] }) {
  const [hidden, setHidden] = useHiddenSeries(); const selectedIds = new Set(selectedGoals.map(String)); const visibleGoals = selectedIds.size ? goals.filter((goal) => selectedIds.has(String(goal.id))) : goals; const grouped = new Map(); rows.forEach((row) => { const age = row.dimensions?.[0]?.name || "Не определено"; const gender = genderName(row.dimensions?.[1]?.name); const item = grouped.get(age) || { age, Мужской: 0, Женский: 0, "Не определено": 0 }; const value = visibleGoals.reduce((sum, goal) => sum + Number(row[String(goal.id)] || 0), 0); item[gender] += value; grouped.set(age, item); }); const data = [...grouped.values()].sort((a, b) => ageRank(a.age) - ageRank(b.age)); const genders = GENDER_ORDER.filter((gender) => data.some((row) => Number(row[gender]) > 0));
  return <article className="seo-panel seo-panel--wide seo-unique-demographics"><header><h3>Уникальные конверсии по полу и возрасту</h3></header><div className="seo-chart seo-chart--large"><SafeChartContainer><BarChart data={data} margin={{ top: 28, right: 30, bottom: 20, left: 10 }}><CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis type="category" dataKey="age" height={38} interval={0} tick={<AgeAxisTick horizontal />} /><YAxis type="number" /><Tooltip content={<ChartTooltip />} /><InteractiveLegend hidden={hidden} setHidden={setHidden} preserveOrder />{genders.map((name, index) => <Bar key={name} dataKey={name} hide={hidden.has(name)} fill={COLOR_MAP[name]} radius={[4, 4, 0, 0]}><LabelList dataKey={name} content={<SignificantBarLabel values={data.map((row) => row[name])} seriesIndex={index} />} /></Bar>)}</BarChart></SafeChartContainer></div></article>;
}


function UniqueConversionCards({ cards = {} }) { const denominator = Number(cards.denominator || 0); const items = [{ id:"all", name:"Все цели", value:Number(cards.total || 0), conversion:Number(cards.conversion || 0) }, ...(cards.goals || []).map((goal) => ({ ...goal, conversion:denominator ? Number(goal.value || 0) * 100 / denominator : 0 }))]; return <section className="seo-unique-kpis">{items.map((item, index) => <article className={index === 0 ? "is-total" : ""} key={item.id}><span title={item.name}>{item.name}</span><strong>{number(item.value)}</strong><footer><span>Конверсия <FloatingHelp>{index === 0 ? "Сумма пользователей, достигших каждой активной цели ÷ посетители × 100%." : "Пользователи, достигшие выбранной цели ÷ посетители × 100%."}<b>Посетители за период: <strong>{number(denominator)}</strong></b></FloatingHelp></span><b>{percent(item.conversion)}</b></footer></article>)}</section>; }


function uniqueGoalValue(point, goals, selectedGoals) { const selectedIds = new Set(selectedGoals.map(String)); const visibleGoals = selectedIds.size ? goals.filter((goal) => selectedIds.has(String(goal.id))) : goals; return visibleGoals.reduce((sum, goal) => sum + Number(point[String(goal.id)] || 0), 0); }


function UniqueGoalsByYear({ data = [], goals = [], selectedGoals, onGoalChange, filters = {} }) { const points = data.flatMap((series) => series.points || []); const rows = new Map(); const years = new Set(); points.forEach((point) => { const { year, month } = periodParts(point.period); years.add(year); const row = rows.get(month) || { month, monthLabel:new Date(2026,month-1,1).toLocaleString("ru-RU",{ month:"short" }) }; row[year] = uniqueGoalValue(point, goals, selectedGoals); row[`${year}_denominator`] = Number(point.denominator || 0); rows.set(month, row); }); const sortedYears = [...years].sort(); const [hidden, setHidden] = useState(() => new Set(sortedYears.slice(0,-2))); const chartRows = [...rows.values()].sort((a,b) => a.month-b.month); const lastPeriod = [...points].map((point) => point.period).filter(Boolean).sort().at(-1); const lastMonth = periodParts(lastPeriod || "").month; const firstMonth = Math.max(1, Number(String(filters.date_from || "").slice(5,7)) || 1); const comparisonRows = sortedYears.map((year,index) => { const periodRows = chartRows.filter((row) => row.month >= firstMonth && row.month <= lastMonth); const value = periodRows.reduce((sum,row) => sum + Number(row[year] || 0),0); const denominator = periodRows.reduce((sum,row) => sum + Number(row[`${year}_denominator`] || 0),0); return { year, value, conversion:denominator ? value * 100 / denominator : 0, color:COLORS[index % COLORS.length] }; }).sort((a,b) => Number(b.year)-Number(a.year)); const maximum = Math.max(...comparisonRows.map((row) => row.value),1); const rangeLabel = `${new Date(2026,firstMonth-1,1).toLocaleString("ru-RU",{month:"long"})} — ${new Date(2026,lastMonth-1,1).toLocaleString("ru-RU",{month:"long"})}`; const selectedIds = new Set(selectedGoals.map(String)); const selectedNames = selectedIds.size ? goals.filter((goal) => selectedIds.has(String(goal.id))).map((goal) => goal.name) : []; const changeGoals = (names) => onGoalChange(goals.filter((goal) => names.includes(goal.name)).map((goal) => String(goal.id))); return <article className="seo-panel seo-panel--wide seo-unique-goals"><header><h3>Достижение целей</h3><div className="seo-goal-filter"><DashboardMultiSelect label="Цели" options={goals.map((goal) => goal.name)} selected={selectedNames} onApply={changeGoals} /></div></header><div className="seo-unique-goals-layout"><div className="seo-chart seo-chart--large"><SafeChartContainer><LineChart data={chartRows} margin={{top:34,right:24,bottom:8,left:4}}><CartesianGrid strokeDasharray="3 4" vertical={false}/><XAxis dataKey="monthLabel" interval={0}/><YAxis/><Tooltip content={<ChartTooltip/>}/><InteractiveLegend hidden={hidden} setHidden={setHidden}/>{sortedYears.map((year,index) => <Line key={year} dataKey={year} hide={hidden.has(year)} stroke={COLORS[index % COLORS.length]} strokeWidth={3.2} dot={{r:3.5}} activeDot={{r:5.5}} label={<SmartLineLabel total={chartRows.length} seriesIndex={index} values={chartRows.map((row) => row[year])} includeFirst />} />)}</LineChart></SafeChartContainer></div><aside><h4>{rangeLabel}</h4>{comparisonRows.map((row) => <div key={row.year}><span><i style={{background:row.color}}/>{row.year}</span><b>{number(row.value)} <small>{percent(row.conversion)}</small></b><em><i style={{width:`${row.value * 100 / maximum}%`,background:row.color}}/></em></div>)}</aside></div></article>; }


function UniqueConversionsSection({ report = {}, filters = {} }) { const goals = report.cards?.goals || []; const [selectedGoals,setSelectedGoalsState] = useState(uniqueConversionSelectedGoals); const setSelectedGoals = (value) => { uniqueConversionSelectedGoals = value; setSelectedGoalsState(value); }; useEffect(() => { const reset = () => setSelectedGoals([]); window.addEventListener("seo:clear-filters", reset); return () => window.removeEventListener("seo:clear-filters", reset); }, []); return <><UniqueConversionCards cards={report.cards || {}}/><div className="seo-report-grid seo-unique-grid"><UniqueGoalsByYear data={report.charts?.dynamics || []} goals={goals} selectedGoals={selectedGoals} onGoalChange={setSelectedGoals} filters={filters}/><GoalDemographics rows={report.charts?.demographics || []} goals={goals} selectedGoals={selectedGoals}/></div></>; }


function ReportContent({ page, report, filters = {}, onLandingLimitChange }) {
  if (report?.availability) return <div className="seo-placeholder"><span>◌</span><h2>{PAGE_TITLES[page]}</h2><p>{report.message}</p></div>;
  const charts = report?.charts || {}; const tables = report?.tables || {}; const selectedEngines = filters.search_engine || []; const normalizeEngines = selectedEngines.length === 0;
  if (page === "search-phrases") { const engines = groupEngineSeries(charts.engines || [], selectedEngines); return <><Cards page="visits" cards={report.cards} /><div className="seo-report-grid"><SeriesChart title="Визиты по поисковым системам" series={engines} metric="visits" normalizeNames={normalizeEngines} sparseLabels includeFirstLabel /><SeriesChart title="Визиты по типу фраз" series={charts.phrase_types || []} metric="visits" normalizeNames={false} sparseLabels includeFirstLabel defaultHiddenNames={["Не определено"]} /><SeriesChart title="Новые посетители по типу фраз" series={charts.phrase_types || []} metric="new_users" normalizeNames={false} sparseLabels includeFirstLabel defaultHiddenNames={["Не определено"]} /><PhraseStructure series={charts.phrase_types || []} /></div></>; }
  if (page === "traffic-change") { const traffic = groupEngineSeries(charts.traffic || [], selectedEngines); const comparison = groupEngineSeries(charts.comparison || [], selectedEngines); const previousMonth = groupEngineSeries(charts.previous_month || [], selectedEngines); return <div className="seo-traffic-layout"><TrafficSummaryCards cards={report.cards} series={traffic} comparison={comparison} baseline={previousMonth} /><TrafficDeltaChart series={traffic} comparison={comparison} baseline={previousMonth} /><TrafficMatrix series={traffic} comparison={comparison} baseline={previousMonth} /><TrafficDeltaChart series={traffic} comparison={comparison} yearly /><TrafficYearsChart series={traffic} /></div>; }
  if (page === "conversions") return <ConversionsSection report={report} />;
  if (page === "unique-conversions") return <UniqueConversionsSection report={report} filters={filters} />;
  if (page === "landing-pages") return <div className="seo-report-grid seo-report-grid--landing"><LandingPagesChart rows={tables.landing_pages || []} summary={charts.summary || report.cards || {}} limit={Number(filters.landing_limit || 20)} onLimitChange={onLandingLimitChange} /></div>;
  const audienceMetric = page === "new-visitors" ? "new_users" : page === "returning-visitors" ? "returned_users" : "visits";
  const shareMetric = page === "new-visitors" ? "new_share" : page === "returning-visitors" ? "returned_share" : "page_depth";
  const firstTitle = page === "new-visitors" ? "Новые посетители" : page === "returning-visitors" ? "Вернувшиеся посетители" : "Визиты по поисковым системам";
  const secondTitle = page === "new-visitors" ? "Доля новых посетителей" : page === "returning-visitors" ? "Доля вернувшихся посетителей" : "Глубина просмотра";
  const firstDemographics = page === "new-visitors" ? "Новые посетители по полу и возрасту" : page === "returning-visitors" ? "Вернувшиеся посетители по полу и возрасту" : "Визиты по полу и возрасту";
  const secondDemographics = page === "new-visitors" ? "Доля новых посетителей по полу и возрасту" : page === "returning-visitors" ? "Доля вернувшихся посетителей по полу и возрасту" : "Визиты по областям";
  const dynamics = groupEngineSeries(charts.dynamics || [], selectedEngines);
  return <><Cards page={page} cards={report.cards} /><div className="seo-report-grid"><SeriesChart title={firstTitle} series={dynamics} metric={audienceMetric} normalizeNames={normalizeEngines} sparseLabels /><SeriesChart title={secondTitle} series={dynamics} metric={shareMetric} normalizeNames={normalizeEngines} sparseLabels />{page === "visits" ? <><DemographicsGenderChart title={firstDemographics} rows={charts.demographics || []} metric="visits" percentStack /><RegionPie rows={charts.regions || []} title={secondDemographics} metric="visits" selectedRegions={filters.region || []} /></> : <><DemographicsGenderChart title={firstDemographics} rows={charts.demographics || []} metric={audienceMetric} percentStack /><DemographicsGenderChart title={secondDemographics} rows={charts.demographics || []} metric={shareMetric} /></>}</div></>;
}


export function SeoAnalyticsDashboard({ dashboard }) {
  const canEdit = Boolean(dashboard?.can_edit);
  const [page, setPage] = useState("home"); const [optionsState, setOptionsState] = useState({ options: {}, configured: true });
  const [filtersByPage, setFiltersByPage] = useState({}); const filters = filtersByPage[page] || defaultFilters();
  const [report, setReport] = useState(null); const [loading, setLoading] = useState(false); const [exporting, setExporting] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [uploading, setUploading] = useState(""); const [refreshState, setRefreshState] = useState({ running: false }); const [reportVersion, setReportVersion] = useState(0); const [menuOpen, setMenuOpen] = useState(false); const [actionsOpen, setActionsOpen] = useState(false); const goalsUploadRef = useRef(null); const brandsUploadRef = useRef(null); const menuRef = useRef(null); const settingsRef = useRef(null); const refreshRunningRef = useRef(false);

  const loadOptions = useCallback(async () => { try { setOptionsState(await getSeoFilterOptions()); } catch (requestError) { setError(requestError.response?.data?.detail || "Не удалось загрузить фильтры SEO."); } }, []);
  const loadState = useCallback(async () => { try { const next = await getSeoRefreshState(); if (refreshRunningRef.current && !next.running) { if (next.status === "failed") setError(next.error || "Обновление SEO завершилось с ошибкой."); else { setReportVersion((value) => value + 1); loadOptions(); } } refreshRunningRef.current = next.running; setRefreshState(next); } catch { /* dashboard data remains available */ } }, [loadOptions]);
  useEffect(() => { const timer = setTimeout(() => { loadOptions(); loadState(); }, 0); return () => clearTimeout(timer); }, [loadOptions, loadState]);
  useEffect(() => { if (!refreshState.running) return undefined; const timer = setInterval(loadState, 5000); return () => clearInterval(timer); }, [loadState, refreshState.running]);
  useEffect(() => { if (!notice) return undefined; const timer = window.setTimeout(() => setNotice(""), 30000); return () => window.clearTimeout(timer); }, [notice]);
  useEffect(() => { const close = (event) => { if (menuRef.current && !menuRef.current.contains(event.target)) setMenuOpen(false); if (settingsRef.current && !settingsRef.current.contains(event.target)) setActionsOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, []);
  useEffect(() => { const receive = (event) => { const message = event.detail || {}; if (message.dashboard !== "SEOAnalytics") return; if (message.status === "running") { refreshRunningRef.current = true; setRefreshState({ running: true, status: "running" }); return; } refreshRunningRef.current = false; setRefreshState({ running: false, status: message.status }); if (message.status === "failed") setError(message.error || "Обновление SEO завершилось с ошибкой."); else { setReportVersion((value) => value + 1); loadOptions(); } }; window.addEventListener("dashboard:updated", receive); return () => window.removeEventListener("dashboard:updated", receive); }, [loadOptions]);
  const filtersKey = JSON.stringify(filters);
  useEffect(() => { if (page === "home") return undefined; let active = true; const timer = setTimeout(() => { getSeoFilterOptions(page, JSON.parse(filtersKey)).then((payload) => active && setOptionsState(payload)).catch((requestError) => active && setError(requestError.response?.data?.detail || "Не удалось обновить зависимые фильтры SEO.")); }, 120); return () => { active = false; clearTimeout(timer); }; }, [page, filtersKey, reportVersion]);
  useEffect(() => { if (page === "home") return undefined; let active = true; const requestedFilters = JSON.parse(filtersKey); const timer = setTimeout(() => { setLoading(true); setError(""); getSeoReport(page, requestedFilters).then((payload) => { if (active) setReport(payload); }).catch((requestError) => { if (active) { setReport(requestError.response?.data || null); setError(requestError.response?.data?.message || "Не удалось загрузить раздел SEO-аналитики."); } }).finally(() => { if (active) setLoading(false); }); }, 0); return () => { active = false; clearTimeout(timer); }; }, [page, filtersKey, reportVersion]);

  const update = (changes) => { const resetKeys = Object.keys(defaultFilters()); if (resetKeys.every((key) => Object.prototype.hasOwnProperty.call(changes, key))) window.dispatchEvent(new Event("seo:clear-filters")); setFiltersByPage((old) => ({ ...old, [page]: { ...(old[page] || defaultFilters()), ...changes } })); };
  const navigate = (nextPage) => {
    if (nextPage === page) {
      setMenuOpen(false);
      return;
    }
    conversionSelectedGoals = [];
    uniqueConversionSelectedGoals = [];
    window.dispatchEvent(new Event("seo:clear-filters"));
    setFiltersByPage((old) => ({ ...old, [page]: defaultFilters(), [nextPage]: defaultFilters() }));
    setPage(nextPage);
    setMenuOpen(false);
    setReport(null);
  };
  const movePage = (step) => { const index = PAGE_CONFIG.findIndex(([key]) => key === page); if (index < 0) return; navigate(PAGE_CONFIG[(index + step + PAGE_CONFIG.length) % PAGE_CONFIG.length][0]); };
  const option = (name) => optionsState.options?.[name] || [];
  const filterSet = page === "search-phrases" ? ["search_engine", "robotness", "phrase_type"] : ["conversions", "unique-conversions"].includes(page) ? ["device", "search_engine", "region", "phrase_type"] : page === "landing-pages" ? ["device", "search_engine", "region"] : ["device", "search_engine", "region", "robotness"];
  const labels = { device: "Тип устройства", search_engine: "Поисковая система", region: "Область", robotness: "Роботность", phrase_type: "Тип фразы" };
  const optionKeys = { device: "devices", search_engine: "search_engines", region: "regions", robotness: "robotness", phrase_type: "phrase_types" };

  const exportReport = async () => { if (exporting) return; setExporting(true); setError(""); try { saveBlob(await exportSeoReport(page, filters), `seo_${page}.xlsx`); } catch { setError("Не удалось сформировать Excel-выгрузку."); } finally { setExporting(false); } };
  const template = async (kind) => { try { saveBlob(await downloadSeoConfiguration(kind), kind === "goals" ? "seo_goals.xlsx" : "seo_brand_masks.xlsx"); } catch { setError(kind === "goals" ? "Не удалось скачать шаблон целей." : "Не удалось скачать шаблон брендовых масок."); } };
  const upload = async (kind, event) => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return; setUploading(kind); setNotice(""); setError(""); try { const result = await uploadSeoConfiguration(kind, file); setNotice(kind === "goals" ? `Настройка отображения применена: ${result.goals} целей.` : `Применено брендовых масок: ${result.brand_masks}. Совпавшие поисковые фразы отнесены к брендовым, остальные — к небрендовым.`); await loadOptions(); setReportVersion((value) => value + 1); } catch (requestError) { setNotice(requestError.response?.data?.file || "Не удалось загрузить настройки."); } finally { setUploading(""); } };
  const refresh = async () => { try { await startSeoRefresh(page, filters); refreshRunningRef.current = true; setRefreshState({ running: true }); } catch (requestError) { setError(requestError.response?.data?.message || "Не удалось запустить обновление."); } };

  const lastUpdated = report?.meta?.last_updated ? new Date(report.meta.last_updated).toLocaleString("ru-RU", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  const planned = ["calltouch", "positions", "competitors"];
  const qualityWarnings = [report?.meta?.warning, ...(report?.warnings || []), ...(report?.quality || []).flatMap((item) => [item?.sampled ? `Данные Метрики семплированы${item.sample_share ? `: использовано ${percent(Number(item.sample_share) * 100)}` : "."}` : "", item?.data_lag ? `Задержка данных Метрики: ${item.data_lag} сек.` : ""])].filter(Boolean);
  const toastStack = <SeoToastStack key={qualityWarnings.map((item) => seoMessageText(item, "")).join("|")} error={error} notice={notice} warnings={qualityWarnings} clearError={() => setError("")} clearNotice={() => setNotice("")} />;
  if (page === "home") return <main className="seo-dashboard seo-dashboard--home"><section ref={settingsRef} className={`seo-home-settings ${actionsOpen ? "is-open" : ""}`}><button type="button" className="seo-home-settings-toggle" aria-label="Настройки SEO" aria-expanded={actionsOpen} onClick={() => setActionsOpen((value) => !value)}>⋯</button><div className="seo-action-buttons"><button type="button" disabled={!canEdit || !!uploading} onClick={() => template("goals")}>Шаблон целей</button><button type="button" className={uploading === "goals" ? "is-loading" : ""} disabled={!canEdit || !!uploading} onClick={() => goalsUploadRef.current?.click()}>{uploading === "goals" ? "Загрузка целей..." : "Загрузить цели"}</button><button type="button" disabled={!canEdit || !!uploading} onClick={() => template("brand-masks")}>Шаблон масок</button><button type="button" className={uploading === "brand-masks" ? "is-loading" : ""} disabled={!canEdit || !!uploading} onClick={() => brandsUploadRef.current?.click()}>{uploading === "brand-masks" ? "Загрузка масок..." : "Загрузить маски"}</button><input ref={goalsUploadRef} type="file" accept=".xlsx" hidden onChange={(event) => upload("goals", event)} /><input ref={brandsUploadRef} type="file" accept=".xlsx" hidden onChange={(event) => upload("brand-masks", event)} /></div></section>{toastStack}<section className="seo-home"><div className="seo-tiles">{PAGE_CONFIG.map(([key, short, , kind]) => { const unavailable = planned.includes(key); return <button type="button" key={key} className={unavailable ? "is-planned" : ""} onClick={() => navigate(key)}><PageIcon kind={kind} /><span><strong>{short}</strong></span><i>→</i>{unavailable && <em>Скоро</em>}</button>; })}</div></section></main>;

  return <main className="seo-dashboard">
    <section ref={menuRef} className={`seo-menu ${menuOpen ? "is-open" : ""}`}><div className="seo-menu-controls"><button type="button" className="seo-menu-arrow" onClick={() => movePage(-1)} title="Предыдущая вкладка" aria-label="Предыдущая вкладка">‹</button><button type="button" className="seo-menu-toggle" aria-label="Открыть меню разделов" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)}>⋯</button><button type="button" className="seo-menu-arrow" onClick={() => movePage(1)} title="Следующая вкладка" aria-label="Следующая вкладка">›</button></div><nav><button type="button" onClick={() => navigate("home")}>Обзор</button>{PAGE_CONFIG.map(([key, short, title]) => <button type="button" key={key} className={page === key ? "is-active" : ""} title={title} onClick={() => navigate(key)}>{short}{planned.includes(key) && <em>Скоро</em>}</button>)}</nav></section>
    {!planned.includes(page) && <section className="seo-page-heading"><h2>{PAGE_TITLES[page]}</h2></section>}
    {toastStack}{planned.includes(page) ? <section className="seo-planned-empty" /> : <><section className="seo-filters"><div className="seo-toolbar"><button type="button" className={exporting ? "is-loading" : ""} disabled={exporting} aria-busy={exporting} onClick={exportReport}>{exporting ? "Экспорт..." : "Экспорт"}</button><button type="button" disabled={refreshState.running} title={`Данные актуальны на: ${lastUpdated}`} onClick={refresh}>{refreshState.running ? "Обновление…" : "Обновить"}</button><button type="button" onClick={() => update(defaultFilters())}>Очистить</button></div><div className="seo-filter-grid">{filterSet.map((key) => <SeoFilter key={key} label={labels[key]} options={option(optionKeys[key])} selected={filters[key] || []} onApply={(value) => update({ [key]: value })} />)}<SeoMonthRangePicker start={filters.date_from} end={filters.date_to} minMonth={optionsState.options?.data_range?.min_month || "2022-01-01"} maxMonth={refreshState.running ? defaultFilters().date_to : optionsState.options?.data_range?.max_month || defaultFilters().date_to} resetRange={{ start: defaultFilters().date_from, end: defaultFilters().date_to }} onChange={({ start, end }) => update({ date_from: start, date_to: end })} /></div></section>{loading ? <LoadingBlock /> : <ReportContent page={page} report={report || {}} filters={filters} onLandingLimitChange={(value) => update({ landing_limit: value })} />}</>}
  </main>;
}
