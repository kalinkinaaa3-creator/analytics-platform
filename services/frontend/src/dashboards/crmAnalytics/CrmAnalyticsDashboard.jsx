import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Bar as RechartsBar, CartesianGrid, Cell, ComposedChart, Legend, Line as RechartsLine, Pie as RechartsPie, PieChart as RechartsPieChart, Rectangle, ResponsiveContainer, Scatter, Tooltip as RechartsTooltip, XAxis, YAxis } from "recharts";

import {
  downloadManagerTrackingTemplate, exportCrmRows, fetchCrmDashboard,
  fetchCrmFilters, fetchCrmRefreshState, fetchCrmRows, refreshCrmAnalytics,
  uploadManagerTracking,
} from "./crmAnalyticsApi";
import "../spinner.css";
import "./crm_analytics.css";

const GROUPS = [["day", "День"], ["week", "Неделя"], ["month", "Месяц"], ["year", "Год"]];
const PREVIOUS_PERIOD_LABELS = { day: "предыдущему дню", week: "предыдущей неделе", month: "предыдущему месяцу", year: "предыдущему году" };
const STAGE_LABELS = { target: "Целевой", apm: "Передано в АйПласт.Маркет", in_progress: "В работе", low_quality: "Некачественный", unknown: "Не определено" };
const SEMANTIC_STATUS_LABELS = { P: "P — в работе", S: "S — целевой", F: "F — некачественный" };
const COLORS = ["#4d6b4a", "#c99845", "#647a8b", "#a85349", "#6f5f87", "#397f83", "#8a704c", "#59645a"];
const UNTRACKED_DEPARTMENT_NAME = "Неотслеживаемые";
const Line = (props) => <RechartsLine {...props} type="monotone" />;
const PieChart = (props) => <RechartsPieChart {...props} width={210} height={210} />;
const Pie = (props) => <RechartsPie {...props} cx="50%" cy="50%" innerRadius={58} outerRadius={94} isAnimationActive={false} />;
const Tooltip = (props) => <RechartsTooltip {...props} shared={false} offset={40} />;

function GlobalSpinner() {
  return <div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>;
}

function Bar(props) {
  const previous = props.stackId === "previous";
  return <RechartsBar {...props} isAnimationActive={false} fillOpacity={previous ? 0.3 : props.fillOpacity} stroke={previous ? props.fill : props.stroke} strokeOpacity={previous ? 0.32 : props.strokeOpacity} />;
}

function CurrentBarShape({ payload, propertyKey, propertyKeys, ...rectangleProps }) {
  const topProperty = [...propertyKeys].reverse().find((key) => Number(payload?.[key] || 0) > 0);
  const displayedTotal = propertyKeys.reduce((sum, key) => sum + Number(payload?.[key] || 0), 0);
  return <g><Rectangle {...rectangleProps} />{topProperty === propertyKey && displayedTotal > 0 && <text className="crm-chart-total" x={rectangleProps.x + rectangleProps.width / 2} y={rectangleProps.y - 9} textAnchor="middle">{number(displayedTotal)}</text>}</g>;
}

function isoDate(value) { return value.toISOString().slice(0, 10); }
function initialFilters() { const now = new Date(); return { date_start: `${now.getFullYear()}-01-01`, date_end: isoDate(now), department_names: [], manager_ids: [], source_ids: [], semantic_status_ids: [], status_ids: [], exclude_untracked_department: true, group_by: "month" }; }
function number(value, digits = 0) { if (value === null || value === undefined || value === "") return "—"; return new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value)); }
function duration(value) { if (value === null || value === undefined || value === "") return "—"; const seconds = Math.max(0, Math.round(Number(value) * 86400)); if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} мин.`; if (seconds < 86400) return `${Math.max(1, Math.floor(seconds / 3600))} час.`; const days = Math.floor(seconds / 86400); return `${days} дн. ${Math.floor((seconds % 86400) / 3600)} час.`; }
function leadsLabel(value) { const amount = Number(value || 0); const mod100 = Math.abs(amount) % 100; const mod10 = Math.abs(amount) % 10; const word = mod100 >= 11 && mod100 <= 14 ? "лидов" : mod10 === 1 ? "лид" : mod10 >= 2 && mod10 <= 4 ? "лида" : "лидов"; return `${number(amount)} ${word}`; }
function dateTime(value) { if (!value) return "—"; return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)); }
function dateOnly(value) { if (!value) return "—"; return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short" }).format(new Date(value)); }
function periodLabel(value, groupBy) { const d = new Date(`${value}T00:00:00`); if (groupBy === "year") return String(d.getFullYear()); if (groupBy === "month") return new Intl.DateTimeFormat("ru-RU", { month: "short", year: "numeric" }).format(d); return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" }).format(d); }

function MultiSelect({ label, options, selected, valueKey, labelKey, onChange }) {
  const root = useRef(null); const menu = useRef(null); const openRef = useRef(false); const draftRef = useRef(selected); const selectedRef = useRef(selected); const onChangeRef = useRef(onChange); const [open, setOpen] = useState(false); const [draft, setDraft] = useState(selected); const [search, setSearch] = useState(""); const [menuLeft, setMenuLeft] = useState(0);
  useEffect(() => { selectedRef.current = selected; onChangeRef.current = onChange; }, [selected, onChange]);
  const updateDraft = (value) => { draftRef.current = value; setDraft(value); };
  const commit = () => { const current = selectedRef.current; const next = draftRef.current; if (current.length !== next.length || current.some((value, index) => value !== next[index])) onChangeRef.current(next); };
  useEffect(() => { const close = (event) => { if (openRef.current && !root.current?.contains(event.target)) { commit(); openRef.current = false; setOpen(false); setSearch(""); } }; document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close); }, []);
  const visible = options.filter((item) => String(item[labelKey] || item[valueKey]).toLowerCase().includes(search.toLowerCase()));
  useLayoutEffect(() => {
    if (!open) return undefined;
    const position = () => {
      if (!root.current || !menu.current) return;
      const bounds = root.current.getBoundingClientRect(); const width = menu.current.getBoundingClientRect().width; const padding = 12;
      setMenuLeft(bounds.left + width <= window.innerWidth - padding ? 0 : Math.max(padding - bounds.left, bounds.width - width));
    };
    position(); window.addEventListener("resize", position); window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [open, visible.length]);
  const toggle = (value) => updateDraft(draft.includes(value) ? draft.filter((item) => item !== value) : [...draft, value]);
  const selectVisible = () => updateDraft([...new Set([...draft, ...visible.map((item) => item[valueKey])])]);
  const toggleMenu = () => { if (open) { commit(); openRef.current = false; setOpen(false); setSearch(""); } else { updateDraft(selected); openRef.current = true; setOpen(true); } };
  const shownSelection = open ? draft : selected;
  return <div className={`crm-filter${open ? " crm-filter--open" : ""}`} ref={root}><label>{label}</label><button type="button" className="crm-multiselect__control" onClick={toggleMenu}>{shownSelection.length ? `Выбрано: ${shownSelection.length}` : "Все"}<span>⌄</span></button>{open && <div ref={menu} className="crm-multiselect__menu" style={{ left: menuLeft }}><input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск…" /><div className="crm-multiselect__controls"><button type="button" disabled={!visible.length} onClick={selectVisible}>Выбрать найденные</button><button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button></div><div className="crm-multiselect__options">{visible.map((item) => { const value = item[valueKey]; return <label key={String(value)}><input type="checkbox" checked={draft.includes(value)} onChange={() => toggle(value)} /><span>{item[labelKey] || value}</span></label>; })}{!visible.length && <p>Нет значений</p>}</div></div>}</div>;
}

function DateFilter({ label, value, onChange }) {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null); const pendingValue = useRef(value); const closeTimer = useRef(null);
  useEffect(() => () => window.clearTimeout(closeTimer.current), []);
  const commit = (nextValue = pendingValue.current) => { window.clearTimeout(closeTimer.current); if (nextValue !== value) onChange(nextValue); };
  const applyIfClosed = () => { const input = inputRef.current; if (!input) return; const supportsOpen = typeof CSS !== "undefined" && CSS.supports?.("selector(:open)"); if (!supportsOpen) return; try { if (!input.matches(":open")) commit(); } catch { /* onBlur remains the safe fallback */ } };
  const change = (event) => { const nextValue = event.target.value; pendingValue.current = nextValue; setDraft(nextValue); window.clearTimeout(closeTimer.current); closeTimer.current = window.setTimeout(applyIfClosed, 50); };
  return <label className="crm-filter"><span>{label}</span><input ref={inputRef} type="date" value={draft} onChange={change} onBlur={() => commit()} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { window.clearTimeout(closeTimer.current); pendingValue.current = value; setDraft(value); event.currentTarget.blur(); } }} /></label>;
}

function pivot(rows, groupBy, segmentType) {
  const periods = new Map(); const keys = new Map();
  rows.forEach((row) => { const period = String(row.period); const key = String(row.dimension_key); const value = Number(row.value || 0); const previousValue = Number(row.previous_year_value || 0); keys.set(key, STAGE_LABELS[key] || row.dimension_name || key); const item = periods.get(period) || { period, periodLabel: periodLabel(period, groupBy), segmentType, meta: {}, total: 0, previousYearTotal: 0, previousPeriodTotal: 0 }; item[key] = Number(item[key] || 0) + value; item[`${key}__previous`] = Number(item[`${key}__previous`] || 0) + previousValue; item.total += value; item.previousYearTotal = Number(row.previous_year_total || 0); item.previousPeriodTotal = Number(row.previous_period_total || 0); item.meta[key] = row; periods.set(period, item); });
  const data = [...periods.values()].sort((a, b) => a.period.localeCompare(b.period));
  data.forEach((item) => {
    const backendPeriodChange = Object.values(item.meta).find((meta) => meta.period_total_change_percent !== undefined)?.period_total_change_percent;
    item.yearChange = item.previousYearTotal ? (item.total - item.previousYearTotal) * 100 / item.previousYearTotal : null;
    item.periodChange = backendPeriodChange === null || backendPeriodChange === undefined ? null : Number(backendPeriodChange);
  });
  return { data, keys: [...keys.entries()] };
}

function MetricTooltip({ active, payload, segmentType }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  const entries = Object.entries(row.meta || {}).map(([key, meta], index) => ({ key, name: STAGE_LABELS[key] || meta.dimension_name || key, value: Number(meta.value || 0), color: COLORS[index % COLORS.length] })).filter((item) => item.value > 0).sort((a, b) => b.value - a.value);
  const total = entries.reduce((sum, item) => sum + item.value, 0);
  const dimensionTitle = { manager: "Менеджер", source: "Источник", dashboard_status: "Стадия", low_quality_status: "Стадия" }[segmentType || row.segmentType] || "Показатель";
  const change = row.yearChange;
  return <div className="crm-chart-tooltip crm-chart-tooltip--pie"><header className="crm-tooltip-header"><span className="crm-tooltip-calendar" aria-hidden="true">▦</span><div><strong>{row.periodLabel}</strong><small>Период отчёта</small></div><span className={`crm-tooltip-change ${Number(change) < 0 ? "crm-tooltip-change--negative" : "crm-tooltip-change--positive"}`}><b>{change === null ? "—" : `${change > 0 ? "↑ +" : change < 0 ? "↓ " : ""}${number(change, 1)}%`}</b><small>к прошлому году</small></span></header><div className="crm-tooltip-body"><div className="crm-tooltip-breakdown"><div className="crm-tooltip-breakdown__head"><span>{dimensionTitle}</span><span>Доля</span></div>{entries.map((item) => <div className="crm-tooltip-breakdown__row" key={item.key}><i style={{ background: item.color }} /><span title={item.name}>{item.name}</span><b>{number(total ? item.value * 100 / total : 0, 1)}%</b></div>)}</div><div className="crm-tooltip-donut"><PieChart width={300} height={300}><Pie data={entries} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={76} outerRadius={128} paddingAngle={1} cornerRadius={2} stroke="#fff" strokeWidth={3}>{entries.map((item) => <Cell key={item.key} fill={item.color} />)}</Pie><text x="50%" y="46%" textAnchor="middle" dominantBaseline="middle" className="crm-tooltip-pie__total">{number(total)}</text><text x="50%" y="57%" textAnchor="middle" dominantBaseline="middle" className="crm-tooltip-pie__caption">ВСЕГО</text></PieChart></div></div></div>;
}

function DeviationMarker({ cx, cy, payload }) {
  const value = payload?.periodChange;
  if (value === null || value === undefined) return null;
  const positive = Number(value) >= 0;
  const points = positive ? `${cx},${cy - 7} ${cx - 6},${cy + 5} ${cx + 6},${cy + 5}` : `${cx},${cy + 7} ${cx - 6},${cy - 5} ${cx + 6},${cy - 5}`;
  return <g className={positive ? "crm-deviation-marker crm-deviation-marker--positive" : "crm-deviation-marker crm-deviation-marker--negative"}><polygon points={points} /><text x={cx + 10} y={cy + 4}>{positive ? "+" : ""}{number(value, 1)}%</text></g>;
}

function DashboardCards({ cards = {} }) {
  const items = [["Итого", cards.total], ["Целевые", cards.target], ["Конверсия", cards.conversion, "%"], ["Передано в АйПласт.Маркет", cards.apm], ["Некачественные", cards.low_quality], ["В работе", cards.in_progress]];
  return <section className="crm-kpi-cards">{items.map(([label, value, suffix]) => <article key={label}><span>{label}</span><strong>{number(value, suffix ? 1 : 0)}{value !== null && value !== undefined && suffix ? suffix : ""}</strong></article>)}</section>;
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

function ComparisonHeader({ children, comparisonPeriod }) {
  const format = (value) => value ? new Intl.DateTimeFormat("ru-RU").format(new Date(`${value}T00:00:00`)) : "—"; const range = `${format(comparisonPeriod?.date_start)} — ${format(comparisonPeriod?.date_end)}`;
  return <span className="crm-comparison-head" tabIndex={0}><span className="crm-comparison-head__label">{children}</span><i aria-hidden="true">i</i><span className="crm-comparison-head__tooltip" role="tooltip"><b>Аналогичный период</b><span>{range}</span></span></span>;
}

function SummaryTable({ rows, segmentType, chartKeys = [], comparisonPeriod }) {
  const { items, total } = useMemo(() => rangeSummary(rows), [rows]); const quality = ["source", "manager"].includes(segmentType); const showTarget = quality; const label = { dashboard_status: "Стадия", source: "Источник", manager: "Менеджер", low_quality_status: "Причина" }[segmentType] || "Показатель"; const colorByKey = new Map(chartKeys.map(([key], index) => [String(key), COLORS[index % COLORS.length]]));
  const renderRow = (item, index, totalRow = false) => { const share = total.value ? item.value * 100 / total.value : 0; const previousShare = total.previous ? item.previous * 100 / total.previous : 0; const conversionBase = item.target + item.lowQuality; const previousConversionBase = item.previousTarget + item.previousLowQuality; const conversion = conversionBase ? item.target * 100 / conversionBase : null; const previousConversion = previousConversionBase ? item.previousTarget * 100 / previousConversionBase : null; const favorableDecrease = segmentType === "low_quality_status"; return <tr key={item.key} className={totalRow ? "crm-summary-total" : ""}><th scope="row"><span className="crm-summary-name">{!totalRow && <i style={{ background: colorByKey.get(item.key) || "#aeb3ac" }} />}{!totalRow && <b>{index + 1}.</b>}{item.name}</span></th><td><strong>{number(item.value)}</strong></td><td>{number(share, 1)}%</td>{showTarget && <td><span className="crm-summary-value"><strong>{number(item.target)}</strong><InlineDelta current={item.target} previous={item.previousTarget} /></span></td>}{quality ? <><td><span className="crm-summary-value"><strong>{conversion === null ? "—" : `${number(conversion, 1)}%`}</strong><InlineDelta current={conversion} previous={previousConversion} points /></span></td><td><DeltaMetric current={item.value} previous={item.previous} /></td></> : <><td><DeltaMetric current={item.value} previous={item.previous} favorableDecrease={favorableDecrease} /></td><td><DeltaMetric current={share} previous={previousShare} share /></td></>}<td><strong>{number(item.returnCustomers)}</strong></td></tr>; };
  return <div className="crm-summary-wrap"><table><thead><tr><th>{label}</th><th>Количество</th><th>Доля, %</th>{showTarget && <th><ComparisonHeader comparisonPeriod={comparisonPeriod}>Целевые</ComparisonHeader></th>}{quality ? <><th><ComparisonHeader comparisonPeriod={comparisonPeriod}>Конверсия, %</ComparisonHeader></th><th><ComparisonHeader comparisonPeriod={comparisonPeriod}>Δ количества</ComparisonHeader></th></> : <><th><ComparisonHeader comparisonPeriod={comparisonPeriod}>Δ количества</ComparisonHeader></th><th><ComparisonHeader comparisonPeriod={comparisonPeriod}>Δ доли, п.п.</ComparisonHeader></th></>}<th>Вернувшиеся</th></tr></thead><tbody>{renderRow(total, -1, true)}{items.map((item, index) => renderRow(item, index))}</tbody></table></div>;
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

function DynamicsChart({ title, rows, summaryRows, comparisonPeriod, groupBy, segmentType, onOpen }) {
  const [showDeviation, setShowDeviation] = useState(false);
  const limitTop = segmentType !== "dashboard_status";
  const prepared = useMemo(() => limitTop ? topSources(rows) : { visible: rows, otherRows: [], otherKeys: [] }, [rows, limitTop]);
  const chart = useMemo(() => pivot(prepared.visible, groupBy, segmentType), [prepared.visible, groupBy, segmentType]);
  const propertyKeys = useMemo(() => chart.keys.map(([key]) => key), [chart.keys]);
  const deviationLabel = `Отклонение к ${PREVIOUS_PERIOD_LABELS[groupBy]}, %`;
  return <article className="crm-panel"><div className="crm-panel__heading"><h2>{title}</h2><button type="button" className={`crm-panel__deviation-toggle${showDeviation ? " is-active" : ""}`} aria-pressed={showDeviation} onClick={() => setShowDeviation((value) => !value)}><i aria-hidden="true" />{deviationLabel}</button></div><div className="crm-chart"><ResponsiveContainer width="100%" height={340}><ComposedChart data={chart.data} barGap={2} margin={{ top: 28, right: 28, left: 0, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="periodLabel" /><YAxis yAxisId="count" allowDecimals={false} /><YAxis yAxisId="change" hide /><Tooltip offset={52} content={<MetricTooltip />} /><Legend />{chart.keys.map(([key], index) => <Bar yAxisId="count" key={`${key}-previous`} dataKey={`${key}__previous`} legendType="none" stackId="previous" fill={COLORS[index % COLORS.length]} fillOpacity={0.24} />)}{chart.keys.map(([key, label], index) => <Bar yAxisId="count" key={key} dataKey={key} name={label} stackId="current" fill={COLORS[index % COLORS.length]} cursor="pointer" shape={<CurrentBarShape propertyKey={key} propertyKeys={propertyKeys} />} onClick={(entry) => onOpen(segmentType, key, entry?.payload?.period, label, key === "__other__" ? prepared.otherKeys : [])} />)}{showDeviation && <><Line yAxisId="change" dataKey="periodChange" legendType="none" stroke="#9b6a36" strokeWidth={1} strokeDasharray="3 4" dot={false} activeDot={false} connectNulls={false} isAnimationActive={false} /><Scatter yAxisId="change" dataKey="periodChange" legendType="none" shape={<DeviationMarker />} isAnimationActive={false} /></>}</ComposedChart></ResponsiveContainer></div><SummaryTable rows={summaryRows || rows} segmentType={segmentType} chartKeys={chart.keys} comparisonPeriod={comparisonPeriod} /></article>;
}

function DetailModal({ state, rows, loading, onClose, onPage, onSort, onExport }) {
  const tableHeadRef = useRef(null); const [tableHeadHeight, setTableHeadHeight] = useState(52);
  useLayoutEffect(() => { const node = tableHeadRef.current; if (!node) return undefined; const update = () => setTableHeadHeight(Math.ceil(node.getBoundingClientRect().height)); update(); const observer = new ResizeObserver(update); observer.observe(node); return () => observer.disconnect(); }, [state]);
  if (!state) return null;
  const headers = [["lead_id", "ID лида"], ["title", "Наименование лида"], ["company_name", "Наименование контрагента"], ["customer_status", "Статус контрагента"], ["manager_name", "Менеджер"], ["status_name", "Стадия"], ["source_name", "Источник"], ["activity_name", "Мероприятие"], ["source_created_at", "Дата создания"], ["source_updated_at", "Дата изменения"], ["first_processing_at", "Скорость рассчитана по"], ["opportunity", "Сумма, руб"], ["processing_duration_days", "Скорость обработки"]];
  return <div className="crm-modal" role="dialog" aria-modal="false"><div className="crm-modal__card"><div className="crm-modal__header"><div><h2>{state.title}</h2><p>{state.period ? periodLabel(state.period, state.group_by) : "Выбранный период"} · найдено {number(rows.total)}</p></div><div><button type="button" className="crm-action" onClick={onExport}>Экспорт</button><button type="button" className="crm-close" onClick={onClose}>×</button></div></div><div className="crm-table-wrap" style={{ "--crm-detail-header-height": `${tableHeadHeight}px` }}><table><thead ref={tableHeadRef}><tr>{headers.map(([key, label]) => <th key={key}><button type="button" disabled={key === "customer_status"} onClick={() => key !== "customer_status" && onSort(key)}>{label}<i className={state.sort_by === key ? "is-active" : ""}>{state.sort_by === key ? (state.sort_direction === "asc" ? "↑" : "↓") : "↕"}</i></button></th>)}</tr></thead><tbody>{!loading && <tr className="crm-detail-summary"><td>Итого</td><td>{leadsLabel(rows.summary?.total)}</td><td>Вся выборка</td><td>{number(rows.summary?.return_customers)} вернувшихся</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>{number(rows.summary?.opportunity, 0)}</td><td>{duration(rows.summary?.processing_duration_days)}</td></tr>}{!loading && rows.items.map((item) => <tr key={item.lead_id}><td>{item.lead_id}</td><td>{item.title || "—"}</td><td>{item.company_name || "Не указан"}</td><td><small className="crm-customer-badge">{item.is_return_customer === true ? "Вернувшийся" : item.is_return_customer === false ? "Новый" : "Не определён"}</small></td><td>{item.manager_name || "—"}</td><td>{item.status_name || item.status_id || "—"}</td><td>{item.source_name || item.source_id || "—"}</td><td>{item.activity_name || "—"}</td><td>{dateOnly(item.source_created_at)}</td><td title="По данным Bitrix24">{dateOnly(item.source_updated_at)}</td><td>{dateOnly(item.first_processing_at || item.calculated_at)}</td><td>{number(item.opportunity, 0)}</td><td>{duration(item.processing_duration_days)}</td></tr>)}</tbody></table>{loading && <div className="crm-loading">Загрузка данных…</div>}</div><div className="crm-pagination"><button type="button" disabled={state.page <= 1} onClick={() => onPage(state.page - 1)}>Назад</button><span>Страница {rows.page || 1} из {Math.max(rows.pages || 1, 1)}</span><button type="button" disabled={state.page >= rows.pages} onClick={() => onPage(state.page + 1)}>Далее</button></div></div></div>;
}

export function CrmAnalyticsDashboard({ dashboard: meta }) {
  const [activeTab, setActiveTab] = useState("leads"); const [filters, setFilters] = useState(initialFilters); const [options, setOptions] = useState({ departments: [], managers: [], sources: [], semantic_statuses: [], statuses: [] }); const [dashboard, setDashboard] = useState(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [refreshing, setRefreshing] = useState(false); const [uploading, setUploading] = useState(false); const [exporting, setExporting] = useState(false); const [modal, setModal] = useState(null); const [detailRows, setDetailRows] = useState({ items: [], page: 1, pages: 0, total: 0, summary: {} }); const [detailLoading, setDetailLoading] = useState(false); const canEdit = Boolean(meta?.can_edit);
  const load = useCallback(async () => { setLoading(true); setError(""); try { setDashboard(await fetchCrmDashboard(filters)); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить аналитику CRM."); } finally { setLoading(false); } }, [filters]);
  const loadOptions = useCallback(async () => { const result = await fetchCrmFilters(filters); setOptions(result); setRefreshing(Boolean(result.refresh?.running)); }, [filters]);
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => { loadOptions().catch(() => setError("Не удалось загрузить справочники фильтров.")); }, [loadOptions]); useEffect(() => { load(); }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const detailPayload = useCallback((state) => ({ ...filters, segment_type: state.segment_type, segment_key: state.segment_key, segment_keys: state.segment_keys || [], period: state.period, page: state.page, page_size: 50, sort_by: state.sort_by, sort_direction: state.sort_direction }), [filters]);
  const loadDetails = useCallback(async (state) => { setDetailLoading(true); try { setDetailRows(await fetchCrmRows(detailPayload(state))); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить детализацию."); } finally { setDetailLoading(false); } }, [detailPayload]);
  /* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  useEffect(() => { if (modal) { const next = { ...modal, page: 1 }; setModal(next); loadDetails(next); } }, [filters]);
  /* eslint-enable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  function openDetails(segmentType, key, period, title, segmentKeys = []) { const state = { segment_type: segmentType, segment_key: key === "__other__" ? "" : key, segment_keys: segmentKeys, period, title, group_by: filters.group_by, page: 1, sort_by: "source_created_at", sort_direction: "desc" }; setModal(state); loadDetails(state); }
  function updateModal(next) { setModal(next); loadDetails(next); }
  async function refresh() { setError(""); try { await refreshCrmAnalytics(); setRefreshing(true); } catch (e) { if (e.response?.status === 409) setRefreshing(true); else setError(e.response?.data?.detail || "Не удалось запустить обновление."); } }
  useEffect(() => { if (!refreshing) return undefined; const timer = window.setInterval(async () => { try { const state = await fetchCrmRefreshState(); if (!state.running) { setRefreshing(false); if (state.status === "failed") setError(state.error || "Обновление завершилось с ошибкой."); else { await loadOptions(); await load(); } } } catch { /* repeat */ } }, 3000); return () => window.clearInterval(timer); }, [refreshing, load, loadOptions]);
  async function upload(event) { const file = event.target.files?.[0]; if (!file) return; setUploading(true); try { await uploadManagerTracking(file); setRefreshing(true); } catch (e) { setError(e.response?.data?.detail || "Не удалось загрузить перечень менеджеров."); } finally { setUploading(false); event.target.value = ""; } }
  async function exportAll() { setExporting(true); try { await exportCrmRows({ ...filters, page: 1, page_size: 50, sort_by: "source_created_at", sort_direction: "desc" }); } finally { setExporting(false); } }
  const reset = () => setFilters(initialFilters()); const dynamics = dashboard?.dynamics || {}; const summaries = dashboard?.summaries || {}; const comparisonPeriod = dashboard?.comparison_period || {}; const selectedDepartments = filters.department_names.length ? filters.department_names : filters.exclude_untracked_department ? (options.departments || []).map((item) => item.department_name).filter((name) => name && name !== UNTRACKED_DEPARTMENT_NAME) : []; const semanticStatusOptions = (options.semantic_statuses || []).map((item) => ({ ...item, semantic_status_name: SEMANTIC_STATUS_LABELS[item.status_semantic_id] || item.status_semantic_id }));
  return <main className="crm-dashboard"><h1>Аналитика CRM</h1><section className="crm-filters"><div className="crm-filter-actions">{canEdit && <button className="crm-action" type="button" onClick={downloadManagerTrackingTemplate}>Шаблон менеджеров</button>}{canEdit && <label className="crm-action crm-upload">{uploading ? "Загрузка…" : "Загрузить менеджеров"}<input type="file" accept=".xlsx" disabled={uploading || refreshing} onChange={upload} /></label>}{<button className="crm-action" type="button" disabled={refreshing} onClick={refresh} title={options.last_updated_at ? `Данные актуальны на ${dateTime(options.last_updated_at)}` : "Данные ещё не обновлялись"}>{refreshing ? "Обновление…" : "Обновить"}</button>}<button className="crm-action" type="button" disabled={exporting} onClick={exportAll}>{exporting ? "Экспорт…" : "Экспорт"}</button><button className="crm-action" type="button" onClick={reset}>Очистить</button></div><div className="crm-filter-grid"><MultiSelect label="Подразделение" options={options.departments || []} selected={selectedDepartments} valueKey="department_name" labelKey="department_name" onChange={(value) => setFilters((old) => ({ ...old, department_names: value, exclude_untracked_department: !value.includes(UNTRACKED_DEPARTMENT_NAME) }))} /><MultiSelect label="Менеджер" options={options.managers || []} selected={filters.manager_ids} valueKey="manager_id" labelKey="manager_name" onChange={(value) => setFilters((old) => ({ ...old, manager_ids: value }))} /><MultiSelect label="Источник" options={options.sources || []} selected={filters.source_ids} valueKey="source_id" labelKey="source_name" onChange={(value) => setFilters((old) => ({ ...old, source_ids: value }))} /><MultiSelect label="Статус" options={semanticStatusOptions} selected={filters.semantic_status_ids} valueKey="status_semantic_id" labelKey="semantic_status_name" onChange={(value) => setFilters((old) => ({ ...old, semantic_status_ids: value }))} /><MultiSelect label="Стадия" options={options.statuses || []} selected={filters.status_ids} valueKey="status_id" labelKey="status_name" onChange={(value) => setFilters((old) => ({ ...old, status_ids: value }))} /><DateFilter key={`date-start-${filters.date_start}`} label="Дата начала" value={filters.date_start} onChange={(value) => setFilters((old) => ({ ...old, date_start: value }))} /><DateFilter key={`date-end-${filters.date_end}`} label="Дата окончания" value={filters.date_end} onChange={(value) => setFilters((old) => ({ ...old, date_end: value }))} /><div className="crm-filter crm-group-filter"><span>Группировка</span><div>{GROUPS.map(([key, label]) => <button type="button" className={filters.group_by === key ? "active" : ""} key={key} onClick={() => setFilters((old) => ({ ...old, group_by: key }))}>{label}</button>)}</div></div></div></section><DashboardCards cards={dashboard?.cards || {}} /><nav className="crm-tabs"><button type="button" className={activeTab === "leads" ? "active" : ""} onClick={() => setActiveTab("leads")}>Стадии и источники</button><button type="button" className={activeTab === "analytics" ? "active" : ""} onClick={() => setActiveTab("analytics")}>Менеджеры и качество лидов</button></nav>{error && <div className="crm-alert">{error}</div>}{loading ? <GlobalSpinner /> : <section className="crm-chart-grid">{activeTab === "leads" ? <><DynamicsChart key="stages" title="Динамика по стадиям" rows={dynamics.stages || []} summaryRows={summaries.stages || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="dashboard_status" onOpen={openDetails} /><DynamicsChart key="sources" title="Динамика по источникам" rows={dynamics.sources || []} summaryRows={summaries.sources || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="source" onOpen={openDetails} /></> : <><DynamicsChart key="managers" title="Динамика по менеджерам" rows={dynamics.managers || []} summaryRows={summaries.managers || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="manager" onOpen={openDetails} /><DynamicsChart key="low-quality" title="Динамика некачественных лидов" rows={dynamics.low_quality || []} summaryRows={summaries.low_quality || []} comparisonPeriod={comparisonPeriod} groupBy={filters.group_by} segmentType="low_quality_status" onOpen={openDetails} /></>}</section>}<DetailModal state={modal} rows={detailRows} loading={detailLoading} onClose={() => setModal(null)} onPage={(page) => updateModal({ ...modal, page })} onSort={(sortBy) => updateModal({ ...modal, page: 1, sort_by: sortBy, sort_direction: modal.sort_by === sortBy && modal.sort_direction === "asc" ? "desc" : "asc" })} onExport={() => exportCrmRows(detailPayload(modal), "bitrix24_leads_detail.xlsx")} /></main>;
}
