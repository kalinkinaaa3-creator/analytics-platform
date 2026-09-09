import { createPortal } from "react-dom";
import { cloneElement, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Bar as RechartsBar, CartesianGrid, Cell, ComposedChart as RechartsComposedChart, Legend, Line as RechartsLine, Pie as RechartsPie, PieChart as RechartsPieChart, Rectangle, ReferenceArea as RechartsReferenceArea, Scatter, Tooltip as RechartsTooltip, XAxis, YAxis as RechartsYAxis } from "recharts";

import {
  downloadManagerTrackingTemplate, exportCrmRows, fetchCrmDashboard,
  fetchCrmFilters, fetchCrmRefreshState, fetchCrmRows, refreshCrmAnalytics,
  uploadManagerTracking,
} from "./crmAnalyticsApi";
import { DateRangePicker } from "../../components/DateRangePicker";
import { useDropdownPosition } from "../../components/useDropdownPosition";
import "../spinner.css";
import "./crm_analytics.css";

const GROUPS = [["day", "День"], ["week", "Неделя"], ["month", "Месяц"], ["year", "Год"]];
const PREVIOUS_PERIOD_LABELS = { day: "предыдущему дню", week: "предыдущей неделе", month: "предыдущему месяцу", year: "предыдущему году" };
const STAGE_LABELS = { target: "Целевой", apm: "Передано в Селект Маркет", in_progress: "В работе", low_quality: "Некачественный", unknown: "Не определено" };
const SEMANTIC_STATUS_LABELS = { P: "В работе/Назначен", S: "Целевой", F: "Некачественный" };
const COLORS = ["#4d6b4a", "#c99845", "#647a8b", "#a85349", "#6f5f87", "#397f83", "#8a704c", "#59645a"];
const FALLBACK_COLOR = "#aeb3ac";
function chartColor(key, index) { return String(key) === "__other__" ? FALLBACK_COLOR : COLORS[index % COLORS.length]; }
const UNTRACKED_DEPARTMENT_NAME = "Неотслеживаемые";
let conversionDifferenceAreas = [];
export function ResponsiveContainer({ width = "100%", height = "100%", children, ...props }) {
  const root = useRef(null); const [size, setSize] = useState(null);
  useLayoutEffect(() => { const node = root.current; if (!node) return undefined; const measure = () => { const bounds = node.getBoundingClientRect(); const nextWidth = Math.floor(bounds.width); const nextHeight = Math.floor(bounds.height); setSize((current) => nextWidth > 0 && nextHeight > 0 && (current?.width !== nextWidth || current?.height !== nextHeight) ? { width: nextWidth, height: nextHeight } : current); }; const frame = window.requestAnimationFrame(measure); const observer = new ResizeObserver(measure); observer.observe(node); return () => { window.cancelAnimationFrame(frame); observer.disconnect(); }; }, []);
  return <div ref={root} className="crm-responsive-chart" style={{ width, height }} {...props}>{size && cloneElement(children, size)}</div>;
}
const ComposedChart = ({ margin, data, width, ...props }) => { const chartMargin = { ...margin, right: Math.min(Number(margin?.right ?? 8), 8) }; const chartWidth = Number(width || 0); const measuredData = Array.isArray(data) ? data.map((item) => ({ ...item, _chartPlotWidth: Math.max(chartWidth - Number(chartMargin.left || 0) - Number(chartMargin.right || 0) - 96, 1), _chartRightEdge: Math.max(chartWidth - Number(chartMargin.right || 0) - 6, 1) })) : data; return <RechartsComposedChart {...props} width={width} data={measuredData} margin={chartMargin} />; };
const YAxis = ({ yAxisId, tickFormatter, ...props }) => yAxisId === "change" ? <RechartsYAxis {...props} yAxisId={yAxisId} hide width={0} /> : <RechartsYAxis {...props} yAxisId={yAxisId} tickFormatter={tickFormatter} />;

function showSpacedLabel(index, count, labelWidth, plotWidth = 700) {
  if (count <= 1) return true;
  const spacing = Math.max(Number(plotWidth || 0) / (count - 1), 1);
  const stride = Math.max(1, Math.ceil(labelWidth / spacing));
  return Number(index || 0) % stride === 0;
}

function ConversionValueLabel({ x, y, value, color, offsetY, index, viewBox }) {
  if (value === null || value === undefined) return null;
  const labelWidth = `${number(value, 0)}%`.length * 7 + 6;
  if (!showSpacedLabel(index, conversionDifferenceAreas.length, labelWidth, viewBox?.width || 1200)) return null;
  return <text className="crm-conversion-value-label" x={x} y={y + offsetY} textAnchor="middle" fill={color}>{number(value, 0)}%</text>;
}

const Area = (props) => { if (props.hide || props.dataKey === "negativeRange") return null; if (props.dataKey !== "positiveRange") return null; return <>{conversionDifferenceAreas.slice(0, -1).map((item, index) => { const next = conversionDifferenceAreas[index + 1]; const lower = Math.min(item.conversion, item.previousConversion); const upper = Math.max(item.conversion, item.previousConversion); if (lower === upper) return null; return <RechartsReferenceArea key={`${item.period}-${next.period}`} yAxisId="conversion" x1={item.periodLabel} x2={next.periodLabel} y1={lower} y2={upper} fill={item.conversion > item.previousConversion ? "#6f986b" : "#c87569"} fillOpacity={0.22} strokeOpacity={0} ifOverflow="hidden" />; })}</>; };
const Line = (props) => { const conversionLine = ["conversion", "previousConversion"].includes(props.dataKey); const currentConversion = props.dataKey === "conversion"; const label = currentConversion ? <ConversionValueLabel color="#3f653e" offsetY={-11} /> : props.dataKey === "previousConversion" ? false : props.label; const name = currentConversion ? "Заданный период" : props.dataKey === "previousConversion" ? "Сравнение с аналогичным периодом" : props.name; const dot = conversionLine && props.dot && typeof props.dot === "object" ? { ...props.dot, r: currentConversion ? 5 : 4 } : props.dot; const activeDot = currentConversion ? { ...(typeof props.activeDot === "object" ? props.activeDot : {}), r: 7 } : props.activeDot; return <RechartsLine {...props} name={name} strokeWidth={currentConversion ? 4 : props.dataKey === "previousConversion" ? 3 : props.strokeWidth} dot={dot} activeDot={activeDot} type={conversionLine ? "stepAfter" : "monotone"} label={label} />; };
const PieChart = (props) => <RechartsPieChart {...props} width={210} height={210} />;
const Pie = (props) => <RechartsPie {...props} cx="50%" cy="50%" innerRadius={58} outerRadius={94} isAnimationActive={false} />;
const BaseTooltip = (props) => <RechartsTooltip {...props} shared={false} offset={84} />;
const LeftChartTooltip = ({ colorByKey, hiddenKeys, ...props }) => <BaseTooltip {...props} content={<RightPlacedMetricTooltip colorByKey={colorByKey} hiddenKeys={hiddenKeys} />} reverseDirection={{ x: false, y: false }} allowEscapeViewBox={{ x: true, y: false }} />;
const RightChartTooltip = ({ colorByKey, hiddenKeys, ...props }) => <BaseTooltip {...props} content={<LeftPlacedMetricTooltip colorByKey={colorByKey} hiddenKeys={hiddenKeys} />} reverseDirection={{ x: false, y: false }} allowEscapeViewBox={{ x: true, y: false }} />;

export function GlobalSpinner() {
  return <div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>;
}

function Bar(props) {
  const previous = props.stackId === "previous";
  return <RechartsBar {...props} isAnimationActive={false} fillOpacity={previous ? 0.3 : props.fillOpacity} stroke={previous ? props.fill : props.stroke} strokeOpacity={previous ? 0.32 : props.strokeOpacity} />;
}

function CurrentBarShape({ payload, propertyKey, propertyKeys, ...rectangleProps }) {
  const topProperty = [...propertyKeys].reverse().find((key) => Number(payload?.[key] || 0) > 0);
  const displayedTotal = propertyKeys.reduce((sum, key) => sum + Number(payload?.[key] || 0), 0);
  const labelWidth = number(displayedTotal).length * 7 + 8; const availableWidth = Math.max(Number(rectangleProps.width || 0) * 2.2, 1); const stride = Math.max(1, Math.ceil(labelWidth / availableWidth)); const showLabel = Number(payload?._labelIndex || 0) % stride === 0;
  return <g><Rectangle {...rectangleProps} />{topProperty === propertyKey && displayedTotal > 0 && showLabel && <text className="crm-chart-total" x={rectangleProps.x + rectangleProps.width / 2} y={rectangleProps.y - 9} textAnchor="middle">{number(displayedTotal)}</text>}</g>;
}

function PreviousBarShape({ payload, propertyKey, propertyKeys, ...rectangleProps }) {
  const topProperty = [...propertyKeys].reverse().find((key) => Number(payload?.[`${key}__previous`] || 0) > 0);
  const displayedTotal = propertyKeys.reduce((sum, key) => sum + Number(payload?.[`${key}__previous`] || 0), 0);
  const labelWidth = number(displayedTotal).length * 7 + 8; const availableWidth = Math.max(Number(rectangleProps.width || 0) * 2.2, 1); const stride = Math.max(1, Math.ceil(labelWidth / availableWidth)); const showLabel = Number(payload?._labelIndex || 0) % stride === 0;
  return <g><Rectangle {...rectangleProps} />{topProperty === propertyKey && displayedTotal > 0 && showLabel && <text className="crm-chart-total crm-chart-total--previous" x={rectangleProps.x + rectangleProps.width / 2} y={rectangleProps.y - 9} textAnchor="middle">{number(displayedTotal)}</text>}</g>;
}

function ToggleLegend({ payload = [], items = null, hiddenKeys, onToggle }) {
  const entries = items || payload.map((entry) => ({ key: String(entry.dataKey), label: entry.value, color: entry.color }));
  return <div className="crm-toggle-legend">{entries.map((entry) => { const key = String(entry.key); const hidden = hiddenKeys.has(key); return <button type="button" key={key} className={hidden ? "is-hidden" : ""} aria-pressed={!hidden} onClick={() => onToggle(key)}><i style={{ background: entry.color }} />{entry.label}</button>; })}</div>;
}

function isoDate(value) { return value.toISOString().slice(0, 10); }
function initialFilters() { const now = new Date(); return { date_start: `${now.getFullYear()}-01-01`, date_end: isoDate(now), department_names: [], manager_ids: [], source_ids: [], project_ids: [], semantic_status_ids: [], status_ids: [], exclude_untracked_department: true, group_by: "month" }; }
function number(value, digits = 0) { if (value === null || value === undefined || value === "") return "—"; return new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value)); }
function duration(value) { if (value === null || value === undefined || value === "") return "—"; const seconds = Math.max(0, Math.round(Number(value) * 86400)); if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} мин.`; if (seconds < 86400) return `${Math.max(1, Math.floor(seconds / 3600))} час.`; const days = Math.floor(seconds / 86400); return `${days} дн. ${Math.floor((seconds % 86400) / 3600)} час.`; }
function leadsLabel(value) { const amount = Number(value || 0); const mod100 = Math.abs(amount) % 100; const mod10 = Math.abs(amount) % 10; const word = mod100 >= 11 && mod100 <= 14 ? "лидов" : mod10 === 1 ? "лид" : mod10 >= 2 && mod10 <= 4 ? "лида" : "лидов"; return `${number(amount)} ${word}`; }
function dateTime(value) { if (!value) return "—"; return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)); }
function detailDateTime(value) { if (!value) return "—"; return new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(value)).replace(", ", " "); }
function periodLabel(value, groupBy) { const d = new Date(`${value}T00:00:00`); if (groupBy === "year") return String(d.getFullYear()); if (groupBy === "month") return new Intl.DateTimeFormat("ru-RU", { month: "short", year: "numeric" }).format(d).replace(/\s*г\.$/u, ""); return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" }).format(d); }
function monthAxisTicks(rows = []) { const labels = rows.map((row) => row.periodLabel).filter(Boolean); const count = Math.min(labels.length, 10); if (count < 2) return labels; return [...new Set(Array.from({ length: count }, (_, index) => labels[Math.round(index * (labels.length - 1) / (count - 1))]))]; }
function weekRangeLabel(value) { const start = new Date(`${value}T00:00:00`); const end = new Date(start); end.setDate(start.getDate() + 6); const day = (date) => String(date.getDate()).padStart(2, "0"); const month = (date) => String(date.getMonth() + 1).padStart(2, "0"); if (start.getFullYear() !== end.getFullYear()) return `${day(start)}.${month(start)}.${start.getFullYear()}–${day(end)}.${month(end)}.${end.getFullYear()}`; if (start.getMonth() !== end.getMonth()) return `${day(start)}.${month(start)}–${day(end)}.${month(end)}.${end.getFullYear()}`; return `${day(start)}–${day(end)}.${month(end)}.${end.getFullYear()}`; }
function previousComparisonDate(value, groupBy) { if (!value) return null; const source = new Date(`${value}T00:00:00Z`); if (groupBy !== "week") { const targetYear = source.getUTCFullYear() - 1; const day = source.getUTCMonth() === 1 && source.getUTCDate() === 29 ? 28 : source.getUTCDate(); return `${targetYear}-${String(source.getUTCMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`; } const weekday = source.getUTCDay() || 7; const thursday = new Date(source); thursday.setUTCDate(source.getUTCDate() + 4 - weekday); const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1)); const week = Math.ceil((((thursday - yearStart) / 86400000) + 1) / 7); const targetYear = thursday.getUTCFullYear() - 1; const december28 = new Date(Date.UTC(targetYear, 11, 28)); const lastThursday = new Date(december28); lastThursday.setUTCDate(december28.getUTCDate() + 4 - (december28.getUTCDay() || 7)); const lastWeek = Math.ceil((((lastThursday - new Date(Date.UTC(lastThursday.getUTCFullYear(), 0, 1))) / 86400000) + 1) / 7); const january4 = new Date(Date.UTC(targetYear, 0, 4)); const firstMonday = new Date(january4); firstMonday.setUTCDate(january4.getUTCDate() - ((january4.getUTCDay() || 7) - 1)); firstMonday.setUTCDate(firstMonday.getUTCDate() + (Math.min(week, lastWeek) - 1) * 7 + weekday - 1); return firstMonday.toISOString().slice(0, 10); }

export function MultiSelect({ label, options, selected, valueKey, labelKey, onChange }) {
  const root = useRef(null); const menu = useRef(null); const openRef = useRef(false); const draftRef = useRef(selected); const selectedRef = useRef(selected); const onChangeRef = useRef(onChange); const [open, setOpen] = useState(false); const [draft, setDraft] = useState(selected); const [search, setSearch] = useState("");
  useEffect(() => { selectedRef.current = selected; onChangeRef.current = onChange; }, [selected, onChange]);
  const updateDraft = (value) => { draftRef.current = value; setDraft(value); };
  const commit = () => { const current = selectedRef.current; const next = draftRef.current; if (current.length !== next.length || current.some((value, index) => value !== next[index])) onChangeRef.current(next); };
  useEffect(() => { const close = (event) => { if (openRef.current && !root.current?.contains(event.target)) { commit(); openRef.current = false; setOpen(false); setSearch(""); } }; document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close); }, []);
  const visible = options.filter((item) => String(item[labelKey] || item[valueKey]).toLowerCase().includes(search.toLowerCase()));
  const { menuStyle, resetPosition } = useDropdownPosition({ open, rootRef: root, menuRef: menu, contentKey: `${visible.length}:${search}` });
  const toggle = (value) => updateDraft(draft.includes(value) ? draft.filter((item) => item !== value) : [...draft, value]);
  const selectVisible = () => updateDraft([...new Set([...draft, ...visible.map((item) => item[valueKey])])]);
  const toggleMenu = () => { if (open) { commit(); openRef.current = false; setOpen(false); setSearch(""); } else { updateDraft(selected); resetPosition(); openRef.current = true; setOpen(true); } };
  const shownSelection = open ? draft : selected;
  return <div className={`crm-filter${open ? " crm-filter--open" : ""}`} ref={root}><label>{label}</label><button type="button" className="crm-multiselect__control" onClick={toggleMenu}>{shownSelection.length ? `Выбрано: ${shownSelection.length}` : "Все"}<span>⌄</span></button>{open && <div ref={menu} className="crm-multiselect__menu" style={menuStyle}><input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск…" /><div className="crm-multiselect__controls"><button type="button" disabled={!visible.length} onClick={selectVisible}>Выбрать найденные</button><button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button></div><div className="crm-multiselect__options">{visible.map((item) => { const value = item[valueKey]; return <label key={String(value)}><input type="checkbox" checked={draft.includes(value)} onChange={() => toggle(value)} /><span>{item[labelKey] || value}</span></label>; })}{!visible.length && <p>Нет значений</p>}</div></div>}</div>;
}

function pivot(rows, groupBy, segmentType) {
  const periods = new Map(); const keys = new Map();
  rows.forEach((row) => { const period = String(row.period); const key = String(row.dimension_key); const value = Number(row.value || 0); const previousValue = Number(row.previous_year_value || 0); keys.set(key, STAGE_LABELS[key] || row.dimension_name || key); const item = periods.get(period) || { period, periodLabel: periodLabel(period, groupBy), tooltipPeriodLabel: groupBy === "week" ? weekRangeLabel(period) : periodLabel(period, groupBy), segmentType, meta: {}, total: 0, previousYearTotal: 0, previousPeriodTotal: 0 }; item[key] = Number(item[key] || 0) + value; item[`${key}__previous`] = Number(item[`${key}__previous`] || 0) + previousValue; item.total += value; item.previousYearTotal = Number(row.previous_year_total || 0); item.previousPeriodTotal = Number(row.previous_period_total || 0); item.meta[key] = row; periods.set(period, item); });
  const data = [...periods.values()].sort((a, b) => a.period.localeCompare(b.period));
  data.forEach((item, index) => {
    item._labelIndex = index; item._labelCount = data.length;
    const backendPeriodChange = Object.values(item.meta).find((meta) => meta.period_total_change_percent !== undefined)?.period_total_change_percent;
    item.yearChange = item.previousYearTotal ? (item.total - item.previousYearTotal) * 100 / item.previousYearTotal : null;
    item.periodChange = backendPeriodChange === null || backendPeriodChange === undefined ? null : Number(backendPeriodChange);
  });
  return { data, keys: [...keys.entries()] };
}

function MetricTooltip({ active, payload, segmentType, colorByKey, hiddenKeys = new Set() }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  const entries = Object.entries(row.meta || {}).map(([key, meta]) => ({ key, name: STAGE_LABELS[key] || meta.dimension_name || key, value: Number(meta.value || 0), color: colorByKey?.get(String(key)) || FALLBACK_COLOR })).filter((item) => item.value > 0 && !hiddenKeys.has(String(item.key))).sort((a, b) => b.value - a.value);
  const total = entries.reduce((sum, item) => sum + item.value, 0);
  const dimensionTitle = { manager: "Менеджер", source: "Источник", dashboard_status: "Стадия", low_quality_status: "Стадия" }[segmentType || row.segmentType] || "Показатель";
  const change = row.yearChange;
  return <div className="crm-chart-tooltip crm-chart-tooltip--pie"><header className="crm-tooltip-header"><span className="crm-tooltip-calendar" aria-hidden="true">▦</span><div><strong>{row.tooltipPeriodLabel || row.periodLabel}</strong><small>Период отчёта</small></div><span className={`crm-tooltip-change ${Number(change) < 0 ? "crm-tooltip-change--negative" : "crm-tooltip-change--positive"}`}><b>{change === null ? "—" : `${change > 0 ? "↑ +" : change < 0 ? "↓ " : ""}${number(change, 1)}%`}</b><small>к прошлому году</small></span></header><div className="crm-tooltip-body"><div className="crm-tooltip-breakdown"><div className="crm-tooltip-breakdown__head"><span>{dimensionTitle}</span><span>Доля</span></div>{entries.map((item) => <div className="crm-tooltip-breakdown__row" key={item.key}><i style={{ background: item.color }} /><span title={item.name}>{item.name}</span><b>{number(total ? item.value * 100 / total : 0, 1)}%</b></div>)}</div><div className="crm-tooltip-donut"><PieChart width={300} height={300}><Pie data={entries} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={76} outerRadius={128} paddingAngle={1} cornerRadius={2} stroke="#fff" strokeWidth={3}>{entries.map((item) => <Cell key={item.key} fill={item.color} />)}</Pie><text x="50%" y="46%" textAnchor="middle" dominantBaseline="middle" className="crm-tooltip-pie__total">{number(total)}</text><text x="50%" y="57%" textAnchor="middle" dominantBaseline="middle" className="crm-tooltip-pie__caption">ВСЕГО</text></PieChart></div></div></div>;
}

function LeftPlacedMetricTooltip(props) {
  return <div className="crm-tooltip-force-left"><MetricTooltip {...props} /></div>;
}

function RightPlacedMetricTooltip(props) {
  return <div className="crm-tooltip-force-right"><MetricTooltip {...props} /></div>;
}

function DeviationMarker({ cx, cy, payload, index }) {
  const value = payload?.periodChange;
  if (value === null || value === undefined) return null;
  const label = `${Number(value) >= 0 ? "+" : ""}${number(value, 0)}%`;
  const textWidth = label.length * 8.5; const labelWidth = textWidth + 54;
  if (!showSpacedLabel(index, Number(payload?._labelCount || 0), labelWidth, Number(payload?._chartPlotWidth || 700))) return null;
  const positive = Number(value) >= 0;
  const openLeft = cx + 18 + textWidth + 7 > Number(payload?._chartRightEdge || Number.POSITIVE_INFINITY);
  const textX = openLeft ? cx - 18 : cx + 18; const textAnchor = openLeft ? "end" : "start";
  const points = positive ? `${cx},${cy - 7} ${cx - 6},${cy + 5} ${cx + 6},${cy + 5}` : `${cx},${cy + 7} ${cx - 6},${cy - 5} ${cx + 6},${cy - 5}`;
  return <g className={positive ? "crm-deviation-marker crm-deviation-marker--positive" : "crm-deviation-marker crm-deviation-marker--negative"}><polygon points={points} /><text x={textX} y={cy + 4} textAnchor={textAnchor}>{label}</text></g>;
}

function DashboardCards({ cards = {}, onOpenConversion }) {
  const total = Number(cards.total || 0); const totalExcludingApm = cards.total_excluding_apm === undefined ? Math.max(total - Number(cards.apm || 0), 0) : Number(cards.total_excluding_apm || 0); const share = (value, base = total) => base ? Number(value || 0) * 100 / base : null;
  const items = [
    { label: "Итого", value: cards.total },
    { label: "Передано в Селект Маркет", value: cards.apm, share: share(cards.apm), shareHelp: "Доля = Передано в Селект Маркет / Общее количество лидов × 100%." },
    { label: "Итого, исключая Селект Маркет", value: totalExcludingApm },
    { label: "Целевые", value: cards.target, share: share(cards.target, totalExcludingApm), shareHelp: "Доля целевых = Целевые лиды / Итого, исключая Селект Маркет × 100%." },
    { label: "Некачественные", value: cards.low_quality, share: share(cards.low_quality, totalExcludingApm), shareHelp: "Доля некачественных = Некачественные лиды / Итого, исключая Селект Маркет × 100%." },
    { label: "Конверсия", value: cards.conversion, suffix: "%", help: "Конверсия = Целевые / (Целевые + Некачественные) × 100%. Лиды в работе и переданные в Селект Маркет не участвуют.", action: onOpenConversion },
    { label: "В работе", value: cards.in_progress },
    { label: "Повторные", value: cards.return_customers, share: share(cards.return_customers), help: "Доля повторных обращений рассчитывается от общего количества лидов" },
  ];
  return <section className="crm-kpi-cards">{items.map((item) => <article key={item.label}><div className="crm-kpi-card__label"><span>{item.label}</span>{item.help && <span className="crm-kpi-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{item.help}</span></span>}</div><div className="crm-kpi-card__value"><strong>{number(item.value, item.suffix ? 1 : 0)}{item.value !== null && item.value !== undefined && item.suffix ? item.suffix : ""}</strong>{item.share !== undefined && <small className="crm-kpi-share">{item.share === null ? "—" : `${number(item.share, 1)}%`}{item.shareHelp && <span className="crm-kpi-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{item.shareHelp}</span></span>}</small>}{item.action && <button type="button" className="crm-kpi-trend-button" onClick={item.action} aria-label="Открыть динамику конверсии" title="Открыть динамику конверсии"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18V6M5 18h14" /><path d="m7.5 14 3.2-3.2 2.6 2.1 4.2-5" /><circle cx="7.5" cy="14" r=".75" /><circle cx="10.7" cy="10.8" r=".75" /><circle cx="13.3" cy="12.9" r=".75" /><circle cx="17.5" cy="7.9" r=".75" /></svg></button>}</div></article>)}</section>;
}

function rangeSummary(rows) {
  const values = new Map(); const periodTotals = new Map();
  rows.forEach((row) => {
    const key = String(row.dimension_key); const period = String(row.period);
    const item = values.get(key) || { key, name: STAGE_LABELS[key] || row.dimension_name || key, value: 0, previous: 0, target: 0, previousTarget: 0, lowQuality: 0, previousLowQuality: 0, returnCustomers: 0 };
    item.value += Number(row.value || 0); item.previous += Number(row.previous_year_value || 0); item.target += Number(row.dimension_target || 0); item.previousTarget += Number(row.previous_year_dimension_target || 0); item.lowQuality += Number(row.dimension_low_quality || 0); item.previousLowQuality += Number(row.previous_year_dimension_low_quality || 0); item.returnCustomers += Number(row.return_customer_value || 0); values.set(key, item);
    if (!periodTotals.has(period)) periodTotals.set(period, { value: Number(row.total || 0), previous: Number(row.previous_year_total || 0) });
  });
  const total = [...periodTotals.values()].reduce((result, item) => ({ ...result, value: result.value + item.value, previous: result.previous + item.previous }), { key: "__total__", name: "Итого", value: 0, previous: 0, target: 0, previousTarget: 0, lowQuality: 0, previousLowQuality: 0, returnCustomers: 0 });
  for (const item of values.values()) { total.target += item.target; total.previousTarget += item.previousTarget; total.lowQuality += item.lowQuality; total.previousLowQuality += item.previousLowQuality; total.returnCustomers += item.returnCustomers; }
  return { items: [...values.values()].sort((a, b) => b.value - a.value || a.name.localeCompare(b.name, "ru")), total };
}

function DeltaMetric({ current, previous, share = false, favorableDecrease = false }) {
  const difference = Number(current || 0) - Number(previous || 0); const percent = previous ? difference * 100 / previous : null; const direction = difference > 0 ? "↑" : difference < 0 ? "↓" : "→"; const className = difference > 0 ? "crm-positive" : difference < 0 ? "crm-negative" : "";
  const semanticClassName = favorableDecrease ? (difference > 0 ? "crm-negative" : difference < 0 ? "crm-positive" : "") : className;
  return <span className={`crm-summary-delta ${semanticClassName}`}><strong>{direction} {difference > 0 ? "+" : ""}{number(difference, share ? 1 : 0)}</strong>{!share && <small>{percent === null ? "—" : `${percent > 0 ? "+" : ""}${number(percent, 1)}%`}</small>}</span>;
}

function InlineDelta({ current, previous, points = false }) {
  if (current === null || current === undefined || previous === null || previous === undefined) return null;
  const difference = Number(current) - Number(previous); const value = points ? difference : (Number(previous) ? difference * 100 / Number(previous) : null); if (value === null) return <small className="crm-inline-delta">—</small>; const direction = value > 0 ? "↑" : value < 0 ? "↓" : "→"; const className = value > 0 ? "crm-positive" : value < 0 ? "crm-negative" : "";
  return <small className={`crm-inline-delta ${className}`}>{direction} {value > 0 ? "+" : ""}{number(value, 1)}{points ? "" : "%"}</small>;
}

export function FormulaHeader({ children, formulas = [], comparisonPeriod = null }) {
  const format = (value) => value ? new Intl.DateTimeFormat("ru-RU").format(new Date(`${value}T00:00:00`)) : "—"; const range = `${format(comparisonPeriod?.date_start)} — ${format(comparisonPeriod?.date_end)}`;
  return <span className="crm-comparison-head" tabIndex={0}><span className="crm-comparison-head__label">{children}</span><i aria-hidden="true">i</i><span className="crm-comparison-head__tooltip" role="tooltip">{comparisonPeriod && <><b>Сравнение с аналогичным периодом</b><span>{range}</span></>}{formulas.map((formula, index) => <span className="crm-formula-line" key={index}>{formula}</span>)}</span></span>;
}

function ComparisonHeader({ children, comparisonPeriod, formulas = [] }) {
  return <FormulaHeader comparisonPeriod={comparisonPeriod} formulas={formulas}>{children}</FormulaHeader>;
}

function ReturnCustomerHeader() {
  return <span className="crm-comparison-head" tabIndex={0}><span className="crm-comparison-head__label">Повторные</span><i aria-hidden="true">i</i><span className="crm-comparison-head__tooltip" role="tooltip"><span>Доля повторных обращений рассчитывается от общего количества лидов</span></span></span>;
}

function SummaryTable({ rows, segmentType, chartKeys = [], comparisonPeriod }) {
  const { items, total } = useMemo(() => rangeSummary(rows), [rows]); const quality = ["source", "manager"].includes(segmentType); const showTarget = quality; const label = { dashboard_status: "Стадия", source: "Источник", manager: "Менеджер", low_quality_status: "Причина" }[segmentType] || "Показатель"; const colorByKey = useMemo(() => new Map(chartKeys.map(([key], index) => [String(key), chartColor(key, index)])), [chartKeys]);
  const renderRow = (item, index, totalRow = false) => { const share = total.value ? item.value * 100 / total.value : 0; const previousShare = total.previous ? item.previous * 100 / total.previous : 0; const conversionBase = item.target + item.lowQuality; const previousConversionBase = item.previousTarget + item.previousLowQuality; const conversion = conversionBase ? item.target * 100 / conversionBase : null; const previousConversion = previousConversionBase ? item.previousTarget * 100 / previousConversionBase : null; const returnCustomerShare = item.value ? item.returnCustomers * 100 / item.value : null; const favorableDecrease = segmentType === "low_quality_status"; return <tr key={item.key} className={totalRow ? "crm-summary-total" : ""}><th scope="row"><span className="crm-summary-name">{!totalRow && <i style={{ background: colorByKey.get(String(item.key)) || FALLBACK_COLOR }} />}{!totalRow && <b>{index + 1}.</b>}{item.name}</span></th><td><strong>{number(item.value)}</strong></td><td>{number(share, 1)}%</td>{showTarget && <td><span className="crm-summary-value"><strong>{number(item.target)}</strong><InlineDelta current={item.target} previous={item.previousTarget} /></span></td>}{quality ? <><td><span className="crm-summary-value"><strong>{conversion === null ? "—" : `${number(conversion, 1)}%`}</strong><InlineDelta current={conversion} previous={previousConversion} points /></span></td><td><DeltaMetric current={item.value} previous={item.previous} /></td></> : <><td><DeltaMetric current={item.value} previous={item.previous} favorableDecrease={favorableDecrease} /></td><td><DeltaMetric current={share} previous={previousShare} share /></td></>}<td><span className="crm-summary-value crm-return-customer-value"><strong>{number(item.returnCustomers)}</strong><small>{returnCustomerShare === null ? "—" : `${number(returnCustomerShare, 1)}%`}</small></span></td></tr>; };
  const shareFormula = "Доля = Количество по строке / Итого по таблице × 100%.";
  const quantityDeltaFormulas = ["Δ количества = Количество текущего периода − Количество аналогичного периода прошлого года.", "Изменение, % = Δ количества / Количество прошлого года × 100%."];
  const shareDeltaFormula = "Δ доли, п.п. = Доля текущего периода − Доля аналогичного периода прошлого года.";
  const targetFormulas = ["Целевые = количество целевых лидов по строке.", "Изменение, % = (Целевые текущего периода − Целевые прошлого года) / Целевые прошлого года × 100%."];
  const conversionFormulas = ["Конверсия = Целевые / (Целевые + Некачественные) × 100%.", "Изменение, п.п. = Конверсия текущего периода − Конверсия прошлого года."];
  return <div className="crm-summary-wrap"><table><thead><tr><th>{label}</th><th>Количество</th><th><FormulaHeader formulas={[shareFormula]}>Доля, %</FormulaHeader></th>{showTarget && <th><ComparisonHeader comparisonPeriod={comparisonPeriod} formulas={targetFormulas}>Целевые</ComparisonHeader></th>}{quality ? <><th><ComparisonHeader comparisonPeriod={comparisonPeriod} formulas={conversionFormulas}>Конверсия, %</ComparisonHeader></th><th><ComparisonHeader comparisonPeriod={comparisonPeriod} formulas={quantityDeltaFormulas}>Δ количества</ComparisonHeader></th></> : <><th><ComparisonHeader comparisonPeriod={comparisonPeriod} formulas={quantityDeltaFormulas}>Δ количества</ComparisonHeader></th><th><ComparisonHeader comparisonPeriod={comparisonPeriod} formulas={[shareDeltaFormula]}>Δ доли, п.п.</ComparisonHeader></th></>}<th><ReturnCustomerHeader /></th></tr></thead><tbody>{renderRow(total, -1, true)}{items.map((item, index) => renderRow(item, index))}</tbody></table></div>;
}

function topSources(rows) {
  const totals = new Map();
  rows.forEach((row) => totals.set(String(row.dimension_key), (totals.get(String(row.dimension_key)) || 0) + Number(row.value || 0)));
  const topKeys = new Set([...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([key]) => key));
  const top = rows.filter((row) => topKeys.has(String(row.dimension_key)));
  const otherRows = rows.filter((row) => !topKeys.has(String(row.dimension_key)));
  const grouped = new Map();
  otherRows.forEach((row) => {
    const period = String(row.period); const item = grouped.get(period) || { ...row, dimension_key: "__other__", dimension_name: "Остальные", value: 0, previous_year_value: 0, return_customer_value: 0, previous_year_return_customer_value: 0, dimension_target: 0, dimension_low_quality: 0, previous_year_dimension_target: 0, previous_year_dimension_low_quality: 0, share: 0 };
    item.value += Number(row.value || 0); item.previous_year_value += Number(row.previous_year_value || 0); item.return_customer_value += Number(row.return_customer_value || 0); item.previous_year_return_customer_value += Number(row.previous_year_return_customer_value || 0); item.dimension_target += Number(row.dimension_target || 0); item.dimension_low_quality += Number(row.dimension_low_quality || 0); item.previous_year_dimension_target += Number(row.previous_year_dimension_target || 0); item.previous_year_dimension_low_quality += Number(row.previous_year_dimension_low_quality || 0); item.share += Number(row.share || 0); grouped.set(period, item);
  });
  return { visible: [...top, ...grouped.values()], otherRows, otherKeys: [...new Set(otherRows.map((row) => String(row.dimension_key)))] };
}

export function DynamicsChart({ title, rows, summaryRows, comparisonPeriod, groupBy, segmentType, onOpen, summaryContent, dimensionOrder }) {
  const [showDeviation, setShowDeviation] = useState(false);
  const [hiddenKeys, setHiddenKeys] = useState(() => new Set());
  const limitTop = !["dashboard_status", "stages", "results"].includes(segmentType);
  const prepared = useMemo(() => limitTop ? topSources(rows) : { visible: rows, otherRows: [], otherKeys: [] }, [rows, limitTop]);
  const chart = useMemo(() => {
    const result = pivot(prepared.visible, groupBy, segmentType);
    if (dimensionOrder) result.keys.sort((a, b) => dimensionOrder.indexOf(a[0]) - dimensionOrder.indexOf(b[0]));
    return result;
  }, [prepared.visible, groupBy, segmentType, dimensionOrder]);
  const propertyKeys = useMemo(() => chart.keys.map(([key]) => key), [chart.keys]);
  const visiblePropertyKeys = useMemo(() => propertyKeys.filter((key) => !hiddenKeys.has(String(key))), [propertyKeys, hiddenKeys]);
  const colorByKey = useMemo(() => new Map(chart.keys.map(([key], index) => [String(key), chartColor(key, index)])), [chart.keys]);
  const legendItems = useMemo(() => chart.keys.map(([key, label]) => ({ key: String(key), label, color: colorByKey.get(String(key)) || FALLBACK_COLOR })), [chart.keys, colorByKey]);
  const deviationLabel = `Отклонение к ${PREVIOUS_PERIOD_LABELS[groupBy]}, %`;
  const rightPanel = ["source", "low_quality_status", "results", "loss-reasons"].includes(segmentType);
  const Tooltip = rightPanel ? RightChartTooltip : LeftChartTooltip;
  const toggleKey = (key) => setHiddenKeys((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  return <article className="crm-panel"><div className="crm-panel__heading"><h2>{title}</h2><button type="button" className={`crm-panel__deviation-toggle${showDeviation ? " is-active" : ""}`} aria-pressed={showDeviation} onClick={() => setShowDeviation((value) => !value)}><i aria-hidden="true" />{deviationLabel}</button></div><div className="crm-chart"><ResponsiveContainer width="100%" height={340}><ComposedChart data={chart.data} barGap={2} margin={{ top: 28, right: 68, left: 8, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="periodLabel" ticks={groupBy === "month" ? monthAxisTicks(chart.data) : undefined} interval={groupBy === "month" ? "preserveStartEnd" : undefined} minTickGap={groupBy === "month" ? 10 : undefined} tickLine={false} axisLine={{ stroke: "#aeb7aa" }} /><YAxis yAxisId="count" className="crm-chart-axis crm-chart-axis--left" orientation="left" allowDecimals={false} tickLine={false} axisLine={{ stroke: "#aeb7aa" }} tick={{ fill: "#687066", fontSize: 11 }} width={48} /><YAxis yAxisId="change" className="crm-chart-axis crm-chart-axis--right" orientation="right" tickFormatter={(value) => `${number(value, 1)}%`} tickLine={false} axisLine={{ stroke: "#c2a37f" }} tick={{ fill: "#8a6741", fontSize: 11 }} width={58} /><Tooltip offset={52} colorByKey={colorByKey} hiddenKeys={hiddenKeys} /><Legend content={<ToggleLegend items={legendItems} hiddenKeys={hiddenKeys} onToggle={toggleKey} />} />{chart.keys.map(([key]) => <Bar yAxisId="count" key={`${key}-previous`} dataKey={`${key}__previous`} legendType="none" stackId="previous" hide={hiddenKeys.has(String(key))} fill={colorByKey.get(String(key)) || FALLBACK_COLOR} fillOpacity={0.24} shape={<PreviousBarShape propertyKey={key} propertyKeys={visiblePropertyKeys} />} />)}{chart.keys.map(([key, label]) => <Bar yAxisId="count" key={key} dataKey={key} name={label} stackId="current" hide={hiddenKeys.has(String(key))} fill={colorByKey.get(String(key)) || FALLBACK_COLOR} cursor="pointer" shape={<CurrentBarShape propertyKey={key} propertyKeys={visiblePropertyKeys} />} onClick={(entry) => onOpen(segmentType, key, entry?.payload?.period, label, key === "__other__" ? prepared.otherKeys : [])} />)}{showDeviation && <><Line yAxisId="change" dataKey="periodChange" legendType="none" stroke="#9b6a36" strokeWidth={1} strokeDasharray="3 4" dot={false} activeDot={false} connectNulls={false} isAnimationActive={false} /><Scatter yAxisId="change" dataKey="periodChange" legendType="none" shape={<DeviationMarker />} isAnimationActive={false} /></>}</ComposedChart></ResponsiveContainer></div>{summaryContent ?? <SummaryTable rows={summaryRows || rows} segmentType={segmentType} chartKeys={chart.keys} comparisonPeriod={comparisonPeriod} />}</article>;
}

function groupedPeriods(dateStart, dateEnd, groupBy) {
  if (!dateStart || !dateEnd) return [];
  const cursor = new Date(`${dateStart}T00:00:00Z`); const end = new Date(`${dateEnd}T00:00:00Z`);
  if (groupBy === "week") cursor.setUTCDate(cursor.getUTCDate() - ((cursor.getUTCDay() || 7) - 1));
  if (groupBy === "month") cursor.setUTCDate(1);
  if (groupBy === "year") { cursor.setUTCMonth(0); cursor.setUTCDate(1); }
  const result = [];
  while (cursor <= end) { result.push(cursor.toISOString().slice(0, 10)); if (groupBy === "day") cursor.setUTCDate(cursor.getUTCDate() + 1); else if (groupBy === "week") cursor.setUTCDate(cursor.getUTCDate() + 7); else if (groupBy === "month") cursor.setUTCMonth(cursor.getUTCMonth() + 1); else cursor.setUTCFullYear(cursor.getUTCFullYear() + 1); }
  return result;
}

function conversionDynamics(rows, groupBy, dateStart, dateEnd) {
  const periods = new Map();
  groupedPeriods(dateStart, dateEnd, groupBy).forEach((period) => periods.set(period, { period, periodLabel: periodLabel(period, groupBy), tooltipPeriodLabel: groupBy === "week" ? weekRangeLabel(period) : periodLabel(period, groupBy), target: 0, lowQuality: 0, previousTarget: 0, previousLowQuality: 0 }));
  rows.forEach((row) => {
    const period = String(row.period); const item = periods.get(period) || { period, periodLabel: periodLabel(period, groupBy), tooltipPeriodLabel: groupBy === "week" ? weekRangeLabel(period) : periodLabel(period, groupBy), target: 0, lowQuality: 0, previousTarget: 0, previousLowQuality: 0 };
    item.target += Number(row.dimension_target || 0); item.lowQuality += Number(row.dimension_low_quality || 0); item.previousTarget += Number(row.previous_year_dimension_target || 0); item.previousLowQuality += Number(row.previous_year_dimension_low_quality || 0); periods.set(period, item);
  });
  const data = [...periods.values()].sort((a, b) => a.period.localeCompare(b.period));
  data.forEach((item) => { const comparisonPeriod = previousComparisonDate(item.period, groupBy); const base = item.target + item.lowQuality; const previousBase = item.previousTarget + item.previousLowQuality; item.comparisonTooltipPeriodLabel = groupBy === "week" ? weekRangeLabel(comparisonPeriod) : periodLabel(comparisonPeriod, groupBy); item.conversion = base ? item.target * 100 / base : 0; item.previousConversion = previousBase ? item.previousTarget * 100 / previousBase : 0; item.delta = item.conversion - item.previousConversion; item.comparisonRange = [Math.min(item.conversion, item.previousConversion), Math.max(item.conversion, item.previousConversion)]; item.positiveRange = item.comparisonRange; item.negativeRange = item.comparisonRange; });
  conversionDifferenceAreas = data;
  const totals = data.reduce((result, item) => ({ target: result.target + item.target, lowQuality: result.lowQuality + item.lowQuality, previousTarget: result.previousTarget + item.previousTarget, previousLowQuality: result.previousLowQuality + item.previousLowQuality }), { target: 0, lowQuality: 0, previousTarget: 0, previousLowQuality: 0 });
  const base = totals.target + totals.lowQuality; const previousBase = totals.previousTarget + totals.previousLowQuality; const conversion = base ? totals.target * 100 / base : null; const previousConversion = previousBase ? totals.previousTarget * 100 / previousBase : null;
  return { data, totals, conversion, previousConversion, delta: conversion === null || previousConversion === null ? null : conversion - previousConversion };
}

function conversionDomain(data) {
  const values = data.flatMap((item) => [item.conversion, item.previousConversion]).filter((value) => value !== null && Number.isFinite(value));
  if (!values.length) return [0, 100];
  let minimum = Math.max(0, Math.floor((Math.min(...values) - 5) / 5) * 5); let maximum = Math.min(100, Math.ceil((Math.max(...values) + 5) / 5) * 5);
  if (maximum - minimum < 10) { minimum = Math.max(0, minimum - 5); maximum = Math.min(100, maximum + 5); }
  return [minimum, maximum];
}

function ConversionTooltip({ active, payload, hiddenKeys = new Set() }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return <div className="crm-conversion-tooltip"><strong>Конверсия</strong>{!hiddenKeys.has("conversion") && <div><span>{row.tooltipPeriodLabel || row.periodLabel}</span><b>{row.conversion === null ? "—" : `${number(row.conversion, 0)}%`}</b></div>}{!hiddenKeys.has("previousConversion") && <div><span>{row.comparisonTooltipPeriodLabel}</span><b>{row.previousConversion === null ? "—" : `${number(row.previousConversion, 0)}%`}</b></div>}{!hiddenKeys.has("conversion") && !hiddenKeys.has("previousConversion") && <div><span>Изменение</span><b className={Number(row.delta) < 0 ? "crm-negative" : "crm-positive"}>{row.delta === null ? "—" : `${row.delta > 0 ? "+" : ""}${number(row.delta, 0)}`}</b></div>}</div>;
}

function ConversionModal({ open, rows, groupBy, dateStart, dateEnd, onClose }) {
  const dynamics = useMemo(() => conversionDynamics(rows, groupBy, dateStart, dateEnd), [rows, groupBy, dateStart, dateEnd]); const domain = useMemo(() => conversionDomain(dynamics.data), [dynamics.data]);
  const [hiddenKeys, setHiddenKeys] = useState(() => new Set());
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (event.key === "Escape") onClose(); }; document.addEventListener("keydown", close); return () => document.removeEventListener("keydown", close); }, [open, onClose]);
  if (!open) return null;
  const formatDate = (value) => value ? new Intl.DateTimeFormat("ru-RU").format(new Date(`${value}T00:00:00`)) : "—";
  const currentRange = `${formatDate(dateStart)} — ${formatDate(dateEnd)}`;
  const comparisonRange = `${formatDate(previousComparisonDate(dateStart, groupBy))} — ${formatDate(previousComparisonDate(dateEnd, groupBy))}`;
  const cards = [
    { label: "Конверсия", value: dynamics.conversion, suffix: "%" },
    { label: "Аналогичный период", value: dynamics.previousConversion, suffix: "%", help: comparisonRange },
    { label: "Изменение", value: dynamics.delta, signed: true },
  ];
  const toggleKey = (key) => setHiddenKeys((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const hideComparison = hiddenKeys.has("conversion") || hiddenKeys.has("previousConversion");
  const legendItems = [{ key: "previousConversion", label: comparisonRange, color: "#8f879c" }, { key: "conversion", label: currentRange, color: "#506f4e" }];
  return <div className="crm-modal crm-conversion-modal" role="dialog" aria-modal="false" aria-label="Динамика конверсии"><div className="crm-modal__card"><div className="crm-modal__header"><div><h2>Динамика конверсии</h2><p>{currentRange} · группировка: {GROUPS.find(([key]) => key === groupBy)?.[1]?.toLowerCase()}</p></div><div><button type="button" className="crm-close" onClick={onClose} aria-label="Закрыть">×</button></div></div><section className="crm-conversion-kpis">{cards.map((card) => <article key={card.label}><span>{card.label}{card.help && <span className="crm-conversion-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{card.help}</span></span>}</span><strong className={card.signed && Number(card.value) < 0 ? "crm-negative" : card.signed && Number(card.value) >= 0 ? "crm-positive" : ""}>{card.value === null ? "—" : `${card.signed && card.value > 0 ? "+" : ""}${number(card.value, 1)}${card.suffix || ""}`}</strong></article>)}</section><div className="crm-conversion-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={dynamics.data} margin={{ top: 28, right: 72, left: 8, bottom: 8 }}><CartesianGrid stroke="#dfe4dc" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="periodLabel" ticks={groupBy === "month" ? monthAxisTicks(dynamics.data) : undefined} interval={groupBy === "month" ? "preserveStartEnd" : undefined} minTickGap={groupBy === "month" ? 10 : undefined} padding={{ left: 24, right: 28 }} tickLine={false} axisLine={{ stroke: "#aeb7aa" }} /><YAxis yAxisId="conversion" className="crm-chart-axis crm-chart-axis--left" orientation="left" domain={domain} tickFormatter={(value) => `${number(value)}%`} tickLine={false} axisLine={{ stroke: "#7f927b" }} tick={{ fill: "#596555", fontSize: 11 }} width={54} /><RechartsTooltip content={<ConversionTooltip groupBy={groupBy} hiddenKeys={hiddenKeys} />} /><Legend content={<ToggleLegend items={legendItems} hiddenKeys={hiddenKeys} onToggle={toggleKey} />} /><Area yAxisId="conversion" dataKey="positiveRange" hide={hideComparison} legendType="none" stroke="none" fill="#1f4e5f" fillOpacity={0.22} connectNulls={false} isAnimationActive={false} /><Area yAxisId="conversion" dataKey="negativeRange" hide={hideComparison} legendType="none" stroke="none" fill="#c87569" fillOpacity={0.2} connectNulls={false} isAnimationActive={false} /><Line yAxisId="conversion" dataKey="previousConversion" hide={hiddenKeys.has("previousConversion")} name={comparisonRange} stroke="#8f879c" strokeWidth={2} strokeDasharray="6 5" dot={{ r: 3, fill: "#fff", strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} /><Line yAxisId="conversion" dataKey="conversion" hide={hiddenKeys.has("conversion")} name={currentRange} stroke="#506f4e" strokeWidth={3} dot={{ r: 4, fill: "#fff", strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls={false} isAnimationActive={false} /></ComposedChart></ResponsiveContainer></div></div></div>;
}

function DetailModal({ state, rows, loading, onClose, onPage, onSort, onExport }) {
  const tableHeadRef = useRef(null); const [tableHeadHeight, setTableHeadHeight] = useState(52);
  useLayoutEffect(() => { const node = tableHeadRef.current; if (!node) return undefined; const update = () => setTableHeadHeight(Math.ceil(node.getBoundingClientRect().height)); update(); const observer = new ResizeObserver(update); observer.observe(node); return () => observer.disconnect(); }, [state]);
  if (!state) return null;
  const speedFormulas = ["Завершённый лид: (дата перехода в текущую финальную стадию − дата создания лида) / 86 400 сек.", "Лид в работе: (дата расчёта − дата создания лида) / 86 400 сек.", "В строке «Итого» показывается средняя скорость обработки выбранных лидов."];
  const headers = [["lead_id", "ID лида"], ["title", "Наименование лида"], ["company_name", "Наименование контрагента"], ["customer_status", "Повторное обращение"], ["manager_name", "Менеджер"], ["department_name", "Подразделение"], ["status_name", "Стадия"], ["source_name", "Источник"], ["activity_name", "Мероприятие"], ["source_created_at", "Дата создания"], ["first_processing_at", "Скорость рассчитана по"], ["opportunity", "Сумма, руб"], ["processing_duration_days", "Скорость обработки", speedFormulas]];
  return <div className="crm-modal" role="dialog" aria-modal="false"><div className="crm-modal__card"><div className="crm-modal__header"><div><h2>{state.title}</h2><p>{state.period ? periodLabel(state.period, state.group_by) : "Выбранный период"} · найдено {number(rows.total)}</p></div><div><button type="button" className="crm-action" onClick={onExport}>Экспорт</button><button type="button" className="crm-close" onClick={onClose}>×</button></div></div><div className="crm-table-wrap" style={{ "--crm-detail-header-height": `${tableHeadHeight}px` }}><table><thead ref={tableHeadRef}><tr>{headers.map(([key, label, formulas]) => <th key={key}><button type="button" disabled={key === "customer_status"} onClick={() => key !== "customer_status" && onSort(key)}>{formulas ? <FormulaHeader formulas={formulas}>{label}</FormulaHeader> : label}<i className={state.sort_by === key ? "is-active" : ""}>{state.sort_by === key ? (state.sort_direction === "asc" ? "↑" : "↓") : "↕"}</i></button></th>)}</tr></thead><tbody>{!loading && <tr className="crm-detail-summary"><td>Итого</td><td>{leadsLabel(rows.summary?.total)}</td><td>Вся выборка</td><td>{number(rows.summary?.return_customers)} повторных</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>{number(rows.summary?.opportunity, 0)}</td><td>{duration(rows.summary?.processing_duration_days)}</td></tr>}{!loading && rows.items.map((item) => <tr key={item.lead_id}><td>{item.lead_id}</td><td>{item.title || "—"}</td><td>{item.company_name || "Не указан"}</td><td><small className="crm-customer-badge">{item.is_return_customer === true ? "Повторный" : item.is_return_customer === false ? "Новый" : "Не определён"}</small></td><td>{item.manager_name || "—"}</td><td>{item.department_name || "—"}</td><td>{item.status_name || item.status_id || "—"}</td><td>{item.source_name || item.source_id || "—"}</td><td>{item.activity_name || "—"}</td><td>{detailDateTime(item.source_created_at)}</td><td>{detailDateTime(item.first_processing_at || item.calculated_at)}</td><td>{number(item.opportunity, 0)}</td><td>{duration(item.processing_duration_days)}</td></tr>)}</tbody></table>{loading && <div className="crm-loading">Загрузка данных…</div>}</div><div className="crm-pagination"><button type="button" disabled={state.page <= 1} onClick={() => onPage(state.page - 1)}>Назад</button><span>Страница {rows.page || 1} из {Math.max(rows.pages || 1, 1)}</span><button type="button" disabled={state.page >= rows.pages} onClick={() => onPage(state.page + 1)}>Далее</button></div></div></div>;
}

export function CrmAnalyticsDashboard({ dashboard: meta, toolbarTarget = null, embedded = false, tab = null, onTabChange }) {
  const [localTab, setLocalTab] = useState("leads"); const [filters, setFilters] = useState(initialFilters); const [options, setOptions] = useState({ departments: [], managers: [], sources: [], projects: [], semantic_statuses: [], statuses: [] }); const [dashboard, setDashboard] = useState(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [refreshing, setRefreshing] = useState(false); const [uploading, setUploading] = useState(false); const [exporting, setExporting] = useState(false); const [modal, setModal] = useState(null); const [conversionOpen, setConversionOpen] = useState(false); const [detailRows, setDetailRows] = useState({ items: [], page: 1, pages: 0, total: 0, summary: {} }); const [detailLoading, setDetailLoading] = useState(false); const canEdit = Boolean(meta?.can_edit);
  const activeTab = tab || localTab;
  const setActiveTab = (value) => { setLocalTab(value); onTabChange?.(value); };
  const load = useCallback(async () => { setLoading(true); setDashboard(null); setError(""); try { setDashboard(await fetchCrmDashboard(filters)); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить аналитику CRM."); } finally { setLoading(false); } }, [filters]);
  const loadOptions = useCallback(async () => { const result = await fetchCrmFilters(filters); setOptions(result); setRefreshing(Boolean(result.refresh?.running)); }, [filters]);
  useEffect(() => {
    const updated = (event) => {
      const message = event.detail || {};
      if (message.dashboard !== "CRMAnalytics") return;
      setRefreshing(message.status === "running");
      if (message.status === "running" || message.status === "failed") return;
      load();
      loadOptions().catch(() => setError("Не удалось обновить сведения об обновлении CRM."));
    };
    window.addEventListener("dashboard:updated", updated);
    return () => window.removeEventListener("dashboard:updated", updated);
  }, [load, loadOptions]);
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => { loadOptions().catch(() => setError("Не удалось загрузить справочники фильтров.")); }, [loadOptions]); useEffect(() => { load(); }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const detailPayload = useCallback((state) => ({ ...filters, segment_type: state.segment_type, segment_key: state.segment_key, segment_keys: state.segment_keys || [], period: state.period, page: state.page, page_size: 50, sort_by: state.sort_by, sort_direction: state.sort_direction }), [filters]);
  const loadDetails = useCallback(async (state) => { setDetailLoading(true); setError(""); try { setDetailRows(await fetchCrmRows(detailPayload(state))); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить детализацию."); } finally { setDetailLoading(false); } }, [detailPayload]);
  /* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  useEffect(() => { if (modal) { const next = { ...modal, page: 1 }; setModal(next); loadDetails(next); } }, [filters]);
  /* eslint-enable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  function openDetails(segmentType, key, period, title, segmentKeys = []) { const state = { segment_type: segmentType, segment_key: key === "__other__" ? "" : key, segment_keys: segmentKeys, period, title, group_by: filters.group_by, page: 1, sort_by: "source_created_at", sort_direction: "desc" }; setConversionOpen(false); setModal(state); loadDetails(state); }
  function updateModal(next) { setModal(next); loadDetails(next); }
  async function refresh() { setError(""); try { await refreshCrmAnalytics(); setRefreshing(true); } catch (e) { if (e.response?.status === 409) setRefreshing(true); else setError(e.response?.data?.detail || "Не удалось запустить обновление."); } }
  useEffect(() => { if (!refreshing) return undefined; const timer = window.setInterval(async () => { try { const state = await fetchCrmRefreshState(); if (!state.running) { setRefreshing(false); if (state.status === "failed") setError(state.error || "Обновление завершилось с ошибкой."); else { await loadOptions(); await load(); } } } catch { /* repeat */ } }, 3000); return () => window.clearInterval(timer); }, [refreshing, load, loadOptions]);
  async function upload(event) { const file = event.target.files?.[0]; if (!file) return; setUploading(true); try { await uploadManagerTracking(file); setRefreshing(true); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить перечень менеджеров."); } finally { setUploading(false); event.target.value = ""; } }
  async function exportAll() { setExporting(true); try { await exportCrmRows({ ...filters, page: 1, page_size: 50, sort_by: "source_created_at", sort_direction: "desc" }); } finally { setExporting(false); } }
  const reset = () => setFilters(initialFilters()); const dynamics = dashboard?.dynamics || {}; const summaries = dashboard?.summaries || {}; const comparisonPeriod = dashboard?.comparison_period || {}; const selectedDepartments = filters.department_names.length ? filters.department_names : filters.exclude_untracked_department ? (options.departments || []).map((item) => item.department_name).filter((name) => name && name !== UNTRACKED_DEPARTMENT_NAME) : []; const sourceOptions = (options.sources || []).map((item) => ({ ...item, source_name: item.source_name || item.source_id || "Источник не указан" })); const semanticStatusOptions = (options.semantic_statuses || []).map((item) => ({ ...item, semantic_status_name: SEMANTIC_STATUS_LABELS[item.status_semantic_id] || item.status_semantic_id })); const statusOptions = (options.statuses || []).map((item) => ({ ...item, status_name: item.status_name || item.status_id || "Стадия не указана" }));
  const toolbarActions = <>{canEdit && <button className="crm-action" type="button" onClick={downloadManagerTrackingTemplate}>Шаблон менеджеров</button>}{canEdit && <label className="crm-action crm-upload">{uploading ? "Загрузка…" : "Загрузить менеджеров"}<input type="file" accept=".xlsx" disabled={uploading || refreshing} onChange={upload} /></label>}{<button className="crm-action" type="button" disabled={refreshing} onClick={refresh} title={options.last_updated_at ? `Данные актуальны на ${dateTime(options.last_updated_at)}` : "Данные ещё не обновлялись"}>{refreshing ? "Обновление…" : "Обновить"}</button>}</>;
  return <main className="crm-dashboard">{!embedded && <h1>Аналитика CRM</h1>}<section className="crm-filters"><div className="crm-filter-actions">{toolbarTarget ? createPortal(toolbarActions, toolbarTarget) : toolbarActions}<button className="crm-action" type="button" disabled={exporting} onClick={exportAll}>{exporting ? "Экспорт…" : "Экспорт"}</button><button className="crm-action" type="button" onClick={reset}>Очистить</button></div><div className="crm-filter-grid"><MultiSelect label="Подразделение" options={options.departments || []} selected={selectedDepartments} valueKey="department_name" labelKey="department_name" onChange={(value) => setFilters((old) => ({ ...old, department_names: value, exclude_untracked_department: !value.includes(UNTRACKED_DEPARTMENT_NAME) }))} /><MultiSelect label="Менеджер" options={options.managers || []} selected={filters.manager_ids} valueKey="manager_id" labelKey="manager_name" onChange={(value) => setFilters((old) => ({ ...old, manager_ids: value }))} /><MultiSelect label="Источник" options={sourceOptions} selected={filters.source_ids} valueKey="source_id" labelKey="source_name" onChange={(value) => setFilters((old) => ({ ...old, source_ids: value }))} /><MultiSelect label="Статус" options={semanticStatusOptions} selected={filters.semantic_status_ids} valueKey="status_semantic_id" labelKey="semantic_status_name" onChange={(value) => setFilters((old) => ({ ...old, semantic_status_ids: value }))} /><MultiSelect label="Стадия" options={statusOptions} selected={filters.status_ids} valueKey="status_id" labelKey="status_name" onChange={(value) => setFilters((old) => ({ ...old, status_ids: value }))} /><DateRangePicker key={`${filters.date_start}:${filters.date_end}`} start={filters.date_start} end={filters.date_end} onChange={({ start, end }) => setFilters((old) => ({ ...old, date_start: start, date_end: end }))} /><div className="crm-filter crm-group-filter"><span>Группировка</span><div>{GROUPS.map(([key, label]) => <button type="button" className={filters.group_by === key ? "active" : ""} key={key} onClick={() => setFilters((old) => ({ ...old, group_by: key }))}>{label}</button>)}</div></div></div></section><DashboardCards cards={dashboard?.cards || {}} onOpenConversion={() => { setModal(null); setConversionOpen(true); }} /><nav className="crm-tabs"><button type="button" className={activeTab === "leads" ? "active" : ""} onClick={() => setActiveTab("leads")}>Стадии и источники лидов</button><button type="button" className={activeTab === "analytics" ? "active" : ""} onClick={() => setActiveTab("analytics")}>Менеджеры и качество лидов</button></nav>{error && <div className="crm-alert">{error}</div>}{loading ? <GlobalSpinner /> : <section className="crm-chart-grid">{activeTab === "leads" ? <><DynamicsChart key="stages" title="Динамика по стадиям" rows={dynamics.stages || []} summaryRows={summaries.stages || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="dashboard_status" onOpen={openDetails} /><DynamicsChart key="sources" title="Динамика по источникам" rows={dynamics.sources || []} summaryRows={summaries.sources || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="source" onOpen={openDetails} /></> : <><DynamicsChart key="managers" title="Динамика по менеджерам" rows={dynamics.managers || []} summaryRows={summaries.managers || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="manager" onOpen={openDetails} /><DynamicsChart key="low-quality" title="Динамика некачественных лидов" rows={dynamics.low_quality || []} summaryRows={summaries.low_quality || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="low_quality_status" onOpen={openDetails} /></>}</section>}<ConversionModal open={conversionOpen} rows={dynamics.stages || []} groupBy={filters.group_by} dateStart={filters.date_start} dateEnd={filters.date_end} onClose={() => setConversionOpen(false)} /><DetailModal state={modal} rows={detailRows} loading={detailLoading} onClose={() => setModal(null)} onPage={(page) => updateModal({ ...modal, page })} onSort={(sortBy) => updateModal({ ...modal, page: 1, sort_by: sortBy, sort_direction: modal.sort_by === sortBy && modal.sort_direction === "asc" ? "desc" : "asc" })} onExport={() => exportCrmRows(detailPayload(modal), "bitrix24_leads_detail.xlsx")} /></main>;
}
