import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  downloadLeadGenerationPlan, exportLeadGenerationReport, getLeadGenerationRefreshInfo,
  getLeadGenerationReport, getLeadGenerationSources, saveLeadGenerationSources,
  uploadLeadGenerationPlan,
} from "../../api/leadGenerationApi";
import { RefreshInfoTooltip } from "../../components/RefreshInfoTooltip";
import { LeadGenerationWeekRangePicker } from "./LeadGenerationWeekRangePicker";
import "../spinner.css";
import "./lead_generation_clean.css";


const PLAN_COLUMNS = [
  ["week_start", "Неделя", "period"], ["budget_vat", "Бюджет ЯндексДирект, руб", "money", "plan"],
  ["target_lead_price", "Средняя цена целевого лида, руб", "money", "plan"], ["planned_target_leads", "Количество целевых лидов, шт", "number", "plan", "Плановое количество целевых лидов из загруженного плана"],
  ["average_revenue_per_lead", "Средняя выручка на лид, руб", "money", "potential", "План выручки ÷ Плановое количество целевых лидов"],
  ["revenue_plan", "Потенциал выручки, руб", "money", "potential"], ["budget_revenue_share", "Доля от выручки, %", "percent", "potential", "Бюджет ÷ Потенциал выручки × 100%"],
  ["direct_cost", "Расходы, руб", "money", "direct"], ["cost_delta", "Дельта расхода, руб", "money", "direct", "Плановый бюджет − Фактические расходы"],
  ["total_leads", "Общее количество лидов, шт", "number", "fact"], ["target_leads", "Целевые лиды, шт", "number", "fact", "Целевые лиды с учётом выбранного режима Селект Маркета"],
  ["non_target_leads", "Нецелевые лиды, шт", "number", "fact", "Лиды категории F, исключая Селект Маркет"], ["unprocessed_leads", "Необработанные лиды, шт", "number", "fact", "Лиды категории P"],
  ["target_conversion", "Конверсия «в целевые», %", "percent", "fact", "Целевые лиды ÷ Общее количество лидов × 100%"], ["target_delta", "Дельта количества целевых лидов, шт", "number", "fact", "Фактические целевые лиды − Плановые целевые лиды"],
  ["actual_target_cpl", "Фактическая средняя цена целевого лида, руб", "money", "control", "Расходы ÷ Фактические целевые лиды"], ["target_cpl_delta", "Дельта цены целевого лида, руб", "money", "control", "Плановая цена целевого лида − Фактическая цена целевого лида"],
  ["lead_opportunity", "Сумма лидов, руб", "money", "crm-revenue"],
  ["successful_deal_amount", "Сумма успешных сделок итого, руб", "money", "crm-revenue"],
];

const SOURCE_COLUMNS = [
  ["week_start", "Неделя", "period"], ["planned_target_leads", "Количество целевых лидов, шт", "number", "source-plan"],
  ["total_leads", "Общее количество лидов, шт", "number", "source-fact"], ["target_leads", "Целевые лиды, шт", "number", "source-fact", "Целевые лиды с учётом выбранного режима Селект Маркета"],
  ["non_target_leads", "Нецелевые лиды, шт", "number", "source-fact"], ["unprocessed_leads", "Необработанные лиды, шт", "number", "source-fact"], ["target_conversion", "CR «в целевые», %", "percent", "source-fact", "Целевые лиды ÷ Общее количество лидов × 100%"],
  ["target_delta", "Дельта целевых лидов, шт", "number", "source-control", "Фактические целевые − Плановые целевые"], ["target_deviation", "Отклонение, %", "percent", "source-control", "(Фактические целевые − Плановые целевые) ÷ Плановые целевые × 100%"],
  ["associated_target_leads", "Ассоциированные", "number", "source-target", "Сумма целевых лидов по выбранным источникам"], ["associated_share", "Доля, %", "percent", "source-target", "Ассоциированные ÷ Все целевые лиды × 100%"],
  ["other_target_leads", "Прочие источники", "number", "source-target"], ["other_share", "Доля прочих, %", "percent", "source-target", "Целевые лиды прочих источников ÷ Все целевые лиды × 100%"],
];

const GROUPS = {
  "revenue-1c": "Выручка 1С",
  "crm-revenue": "Выручка CRM",
  plan: "План лидогенерации", potential: "Планирование потенциала выручки", direct: "Факт ЯндексДирект", fact: "Фактическая статистика по лидам", control: "Контроль показателей целевых лидов",
  "source-plan": "План лидогенерации", "source-fact": "Фактическая статистика по лидам", "source-control": "Контроль показателей целевых лидов", "source-target": "Количество целевых лидов",
};
const GROUP_COLORS = { "revenue-1c":"#36554a", "crm-revenue":"#3e4d3c", period:"#4a5c47", plan:"#4a5c47", "source-plan":"#4a5c47", potential:"#36554a", direct:"#3d4f5e", fact:"#424355", "source-fact":"#424355", control:"#5e423e", "source-control":"#5e423e", "source-target":"#2e4a4c" };
const SOURCE_GROUP_COLORS = ["#3e4d3c", "#5e5445", "#405464", "#6b3a35", "#433e4b", "#354f52", "#5c4f3b", "#4e5a50"];
const SIGNED_METRICS = new Set(["cost_delta", "target_delta", "target_cpl_delta", "target_deviation"]);
const POSITIVE_METRICS = new Set(["target_leads", "target_conversion", "lead_opportunity", "successful_deal_amount"]);
const NEGATIVE_METRICS = new Set(["non_target_leads", "unprocessed_leads"]);
const UNFORMATTED_METRICS = new Set(["target_lead_price", "average_revenue_per_lead", "budget_revenue_share", "target_conversion", "actual_target_cpl", "associated_share", "other_share", "conversion"]);
const BAR_COLORS = {
  plan:"rgba(92,112,86,.20)", potential:"rgba(154,119,58,.20)", direct:"rgba(74,111,137,.20)",
  fact:"rgba(103,105,91,.18)", control:"rgba(113,83,79,.18)", target:"rgba(56,123,72,.22)",
  negative:"rgba(177,70,61,.20)", warning:"rgba(197,139,41,.22)", associated:"rgba(48,124,128,.20)",
};
const number = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : new Intl.NumberFormat("ru-RU", { minimumFractionDigits:digits, maximumFractionDigits:digits }).format(Number(value));
const money = (value) => value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : `${number(value)} ₽`;
const percent = (value) => value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : `${number(value, 1)}%`;
const format = (value, type) => type === "money" ? money(value) : type === "percent" ? percent(value) : type === "period" ? `${new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU")} — ${new Date(new Date(`${value}T00:00:00`).getTime() + 6 * 86400000).toLocaleDateString("ru-RU")}` : number(value);
const download = (blob, name) => { const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url); };

function currentMonday() { const now = new Date(); const day = now.getDay() || 7; now.setDate(now.getDate() - day + 1); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`; }

function Help({ children }) {
  const anchorRef = useRef(null);
  const [position, setPosition] = useState(null);
  const place = useCallback(() => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(300, window.innerWidth - 24);
    const left = Math.min(Math.max(rect.left + rect.width / 2 - width / 2, 12), window.innerWidth - width - 12);
    const showAbove = window.innerHeight - rect.bottom < 150 && rect.top > 150;
    setPosition({ left, top:showAbove ? rect.top - 8 : rect.bottom + 8, width, showAbove });
  }, []);
  useEffect(() => {
    if (!position) return undefined;
    const reposition = () => place();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [place, position]);
  return <><span ref={anchorRef} className="leadgen-help" tabIndex={0} onMouseEnter={place} onMouseLeave={() => setPosition(null)} onFocus={place} onBlur={() => setPosition(null)}>i</span>{position && createPortal(<span className={`leadgen-help-tooltip${position.showAbove ? " is-above" : ""}`} role="tooltip" style={{ left:position.left, top:position.top, width:position.width }}>{children}</span>, document.body)}</>;
}
function GroupChevron({ direction }) { return <svg viewBox="0 0 16 16" aria-hidden="true"><path d={direction === "left" ? "M10 3 5 8l5 5" : "m6 3 5 5-5 5"} /></svg>; }
function LoadingBlock() { return <div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>; }
function notificationText(message) { return typeof message === "string" ? message : message ? Object.values(message).flat().join(" ") : ""; }
function LeadgenToast({ message, type, clear }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => clear(""), 30000);
    return () => window.clearTimeout(timer);
  }, [clear, message]);
  if (!message) return null;
  return <div className={`leadgen-toast leadgen-toast--${type}`} role={type === "error" ? "alert" : "status"}><span>{notificationText(message)}</span><button type="button" aria-label="Закрыть уведомление" onClick={() => clear("")}>×</button></div>;
}

function totalRow(rows, page, sources) {
  const sum = (key) => rows.reduce((result, row) => result + Number(row[key] || 0), 0);
  const total = Object.fromEntries((page === "plan" ? PLAN_COLUMNS : SOURCE_COLUMNS).map(([key]) => [key, key === "week_start" ? "Итого" : sum(key)]));
  if (page === "plan") {
    total.target_lead_price = total.planned_target_leads ? total.budget_vat / total.planned_target_leads : null;
    total.average_revenue_per_lead = total.planned_target_leads ? total.revenue_plan / total.planned_target_leads : null;
    total.budget_revenue_share = total.revenue_plan ? total.budget_vat * 100 / total.revenue_plan : null;
    total.cost_delta = total.budget_vat - total.direct_cost; total.target_conversion = total.total_leads ? total.target_leads * 100 / total.total_leads : null;
    total.target_delta = total.target_leads - total.planned_target_leads; total.actual_target_cpl = total.target_leads ? total.direct_cost / total.target_leads : null; total.target_cpl_delta = total.actual_target_cpl === null ? null : total.target_lead_price - total.actual_target_cpl;
  } else {
    total.target_conversion = total.total_leads ? total.target_leads * 100 / total.total_leads : null; total.target_delta = total.target_leads - total.planned_target_leads; total.target_deviation = total.planned_target_leads ? total.target_delta * 100 / total.planned_target_leads : null;
    total.associated_share = total.target_leads ? total.associated_target_leads * 100 / total.target_leads : null; total.other_share = total.target_leads ? total.other_target_leads * 100 / total.target_leads : null;
    total.sources = {}; sources.forEach((source) => { const sourceTotal = rows.reduce((sumValue, row) => sumValue + Number(row.sources?.[source.id]?.total || 0), 0); const sourceTarget = rows.reduce((sumValue, row) => sumValue + Number(row.sources?.[source.id]?.target || 0), 0); total.sources[source.id] = { total:sourceTotal, target:sourceTarget, conversion:sourceTotal ? sourceTarget * 100 / sourceTotal : null }; });
  }
  return total;
}

function metricKey(column) { return column[0].includes(":") ? column[0].split(":")[1] : column[0]; }
function sentimentClass(column, rawValue) {
  const key = metricKey(column); const numeric = Number(rawValue);
  if (UNFORMATTED_METRICS.has(key)) return "";
  if (!Number.isFinite(numeric) || !numeric) return "";
  if (SIGNED_METRICS.has(key)) return numeric > 0 ? "is-positive" : "is-negative";
  if (POSITIVE_METRICS.has(key)) return "is-positive";
  if (NEGATIVE_METRICS.has(key)) return "is-negative";
  return "";
}
function visualColor(column, rawValue) {
  const key = metricKey(column); const group = column[3] || "period"; const numeric = Number(rawValue);
  if (SIGNED_METRICS.has(key)) return numeric < 0 ? BAR_COLORS.negative : BAR_COLORS.target;
  if (key === "non_target_leads") return BAR_COLORS.negative;
  if (key === "unprocessed_leads") return BAR_COLORS.warning;
  if (POSITIVE_METRICS.has(key)) return BAR_COLORS.target;
  if (["associated_target_leads", "associated_share", "other_target_leads", "other_share"].includes(key)) return BAR_COLORS.associated;
  if (group.startsWith("dynamic:")) return key === "total" ? BAR_COLORS.fact : BAR_COLORS.target;
  if (group.includes("plan")) return BAR_COLORS.plan;
  return BAR_COLORS[group] || BAR_COLORS.fact;
}
function visualMode(column) {
  const key = metricKey(column);
  return column[2] === "percent" || SIGNED_METRICS.has(key) || ["target_lead_price", "average_revenue_per_lead", "actual_target_cpl"].includes(key) ? "heat" : "bar";
}

function DataTable({ page, rows, sources, revenueDirections = [], dealFunnels = [], potentialOpen, setPotentialOpen }) {
  const [revenueOpen, setRevenueOpen] = useState(false);
  const orderedSources = useMemo(() => [...sources].sort((left, right) => {
    if (left.id === "__other__") return 1;
    if (right.id === "__other__") return -1;
    const leadTotal = (source) => rows.reduce((sum, row) => sum + Number(row.sources?.[source.id]?.total || 0), 0);
    return leadTotal(right) - leadTotal(left) || String(left.name).localeCompare(String(right.name), "ru");
  }), [rows, sources]);
  const revenueColumns = [["revenue_1c_total", "Выручка итого, руб", "money", "revenue-1c"],
    ...(revenueOpen ? revenueDirections.map((item) => [item.key, item.name, "money", "revenue-1c", null, item.is_other]) : [])];
  const dealColumns = dealFunnels.map((item) => [item.key, item.name, "money", "crm-revenue"]);
  const base = page === "plan" ? PLAN_COLUMNS.flatMap((column) => column[0] === "lead_opportunity" ? [...revenueColumns, column] : column[0] === "successful_deal_amount" ? [column, ...dealColumns] : [column]) : SOURCE_COLUMNS;
  const columns = base.filter((column) => potentialOpen || column[3] !== "potential");
  const dynamic = page === "sources" ? orderedSources.flatMap((source) => [[`${source.id}:total`, "Общее, шт", "number", `dynamic:${source.id}`], [`${source.id}:target`, "Целевые, шт", "number", `dynamic:${source.id}`, "Целевые лиды с учётом выбранного режима Селект Маркета."], [`${source.id}:conversion`, "CR «в целевые», %", "percent", `dynamic:${source.id}`]]) : [];
  const allColumns = [...columns, ...dynamic];
  const [sort, setSort] = useState({ key:"week_start", direction:"desc" });
  const sorted = useMemo(() => [...rows].sort((a, b) => { const getter = (row) => sort.key.includes(":") ? row.sources?.[sort.key.split(":")[0]]?.[sort.key.split(":")[1]] : row[sort.key]; const left = getter(a), right = getter(b); const result = sort.key === "week_start" ? String(left).localeCompare(String(right)) : Number(left || 0) - Number(right || 0); return result * (sort.direction === "asc" ? 1 : -1); }), [rows, sort]);
  const total = totalRow(rows, page, orderedSources);
  if (page === "plan") for (const [key] of [...revenueColumns, ...dealColumns]) total[key] = rows.reduce((sum, row) => sum + Number(row[key] || 0), 0);
  const groupRuns = []; allColumns.forEach((column) => { const group = column[3] || "period"; const name = group.startsWith("dynamic:") ? orderedSources.find((source) => source.id === group.slice(8))?.name : GROUPS[group]; const last = groupRuns.at(-1); if (last?.key === group) last.count += 1; else groupRuns.push({ key:group, name:name || "", count:1 }); });
  const value = (row, column) => column[0].includes(":") ? row.sources?.[column[0].split(":")[0]]?.[column[0].split(":")[1]] : row[column[0]];
  const cellClass = (column, index) => {
    const group = column[3] || "period";
    const previousGroup = index ? allColumns[index - 1][3] || "period" : null;
    return `${group !== previousGroup && index ? "group-start " : ""}format-${column[2]}`;
  };
  const maxima = Object.fromEntries(allColumns.map((column) => [column[0], Math.max(0, ...rows.map((row) => Math.abs(Number(value(row, column)) || 0)))]));
  const visualStyle = (row, column) => {
    if (column[2] === "period" || column[5] || UNFORMATTED_METRICS.has(metricKey(column))) return null;
    const numeric = Number(value(row, column)); const maximum = maxima[column[0]];
    if (!Number.isFinite(numeric) || !maximum || numeric === 0) return null;
    const strength = Math.min(1, Math.abs(numeric) / maximum);
    return {
      mode:visualMode(column),
      style:{ "--leadgen-visual-color":visualColor(column, numeric), "--leadgen-visual-width":`${strength * 100}%`, "--leadgen-visual-opacity":String(.42 + strength * .48) },
    };
  };
  const toggle = (key) => setSort((old) => old.key === key ? { key, direction:old.direction === "asc" ? "desc" : "asc" } : { key, direction:"desc" });
  const groupColor = (group, index) => group.key.startsWith("dynamic:") ? SOURCE_GROUP_COLORS[index % SOURCE_GROUP_COLORS.length] : GROUP_COLORS[group.key] || GROUP_COLORS.period;
  const columnColor = (column) => { const group = column[3] || "period"; if (!group.startsWith("dynamic:")) return GROUP_COLORS[group] || GROUP_COLORS.period; const sourceIndex = Math.max(0, sources.findIndex((source) => source.id === group.slice(8))); return SOURCE_GROUP_COLORS[sourceIndex % SOURCE_GROUP_COLORS.length]; };
  return <div className="leadgen-table-shell"><table className="leadgen-table"><thead><tr className="leadgen-group-head">{groupRuns.map((group, index) => <th key={group.key} colSpan={group.count} className={`group-${group.key.replace(":", "-")}`} style={{ "--leadgen-group-color":groupColor(group, index) }}>{group.name}{group.key === "revenue-1c" && <button className="leadgen-group-toggle" type="button" aria-expanded={revenueOpen} onClick={() => setRevenueOpen((value) => !value)} aria-label={revenueOpen ? "Скрыть направления выручки" : "Показать направления выручки"}><GroupChevron direction={revenueOpen ? "left" : "right"} /></button>}{group.key === "potential" && <button className="leadgen-group-toggle" type="button" onClick={() => setPotentialOpen(false)} aria-label="Скрыть планирование потенциала" title="Скрыть планирование потенциала"><GroupChevron direction="left" /></button>}{group.key === "plan" && !potentialOpen && <button className="leadgen-group-toggle" type="button" onClick={() => setPotentialOpen(true)} aria-label="Показать планирование потенциала" title="Показать планирование потенциала"><GroupChevron direction="right" /></button>}</th>)}</tr><tr>{allColumns.map((column, index) => <th key={column[0]} className={`column-${column[3] || "period"} ${cellClass(column, index)}`} style={{ "--leadgen-column-color":columnColor(column) }}><button type="button" onClick={() => toggle(column[0])}>{column[1]} <i>{sort.key === column[0] ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}</i></button>{column[4] && <Help>{column[4]}</Help>}</th>)}</tr></thead><tbody>{sorted.map((row) => <tr key={row.week_start}>{allColumns.map((column, index) => { const visual = visualStyle(row, column); return <td key={column[0]} style={visual?.style} className={`${cellClass(column, index)}${visual ? ` has-value-${visual.mode}` : ""} ${sentimentClass(column, value(row, column))}`}><span className="leadgen-cell-value">{format(value(row, column), column[2])}</span></td>; })}</tr>)}</tbody><tfoot><tr>{allColumns.map((column, index) => <td key={column[0]} className={`${cellClass(column, index)} ${sentimentClass(column, value(total, column))}`}>{column[0] === "week_start" ? "Итого" : format(value(total, column), column[2])}</td>)}</tr></tfoot></table></div>;
}

function SourceSettings({ options, selected, onSave, onClose }) { const [draft, setDraft] = useState(selected); const toggle = (id) => setDraft((old) => old.includes(id) ? old.filter((item) => item !== id) : [...old, id]); return <div className="leadgen-modal" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section role="dialog" aria-modal="true"><header><div><small>Персональная настройка</small><h3>Источники в таблице</h3></div><button type="button" onClick={onClose}>×</button></header><p>Выбранные источники выводятся отдельными блоками. Остальные объединяются в «Прочие источники».</p><div>{options.map((option) => <label key={option.id}><input type="checkbox" checked={draft.includes(option.id)} onChange={() => toggle(option.id)} /><span>{option.name}</span></label>)}</div><footer><button type="button" onClick={onClose}>Отмена</button><button type="button" onClick={() => onSave(draft)}>Сохранить</button></footer></section></div>; }

export function LeadGenerationDashboard({ dashboard }) {
  const [page, setPage] = useState("plan"); const [filters, setFilters] = useState({ week_from:"2024-12-30", week_to:currentMonday(), include_select_market:true }); const [report, setReport] = useState({ rows:[], sources:[] }); const [sourceConfig, setSourceConfig] = useState({ options:[], selected:[] }); const [settingsOpen, setSettingsOpen] = useState(false); const [potentialOpen, setPotentialOpen] = useState(true); const [loading, setLoading] = useState(true); const [working, setWorking] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [refreshInfo, setRefreshInfo] = useState(null); const fileRef = useRef(null); const requestRef = useRef(0);
  const load = useCallback(async () => { const request = ++requestRef.current; setLoading(true); setError(""); try { const next = await getLeadGenerationReport(page, filters); if (request === requestRef.current) setReport(next); } catch (reason) { if (request === requestRef.current) setError(reason.response?.data?.period || reason.response?.data?.detail || "Не удалось загрузить отчёт."); } finally { if (request === requestRef.current) setLoading(false); } }, [page, filters]);
  const loadMetadata = useCallback(async () => { try { const [sources, refresh] = await Promise.all([getLeadGenerationSources(), getLeadGenerationRefreshInfo()]); setSourceConfig(sources); setRefreshInfo(refresh); } catch (reason) { setError(reason.response?.data?.detail || "Не удалось загрузить сведения об источниках."); } }, []);
  useEffect(() => { const timer = window.setTimeout(load, 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { const timer = window.setTimeout(loadMetadata, 0); return () => window.clearTimeout(timer); }, [loadMetadata]);
  useEffect(() => { const updated = (event) => { if (event.detail?.dashboard === "LeadGeneration") { load(); loadMetadata(); } }; window.addEventListener("dashboard:updated", updated); return () => window.removeEventListener("dashboard:updated", updated); }, [load, loadMetadata]);
  const action = async (callback, success) => { setWorking(true); setError(""); setMessage(""); try { const result = await callback(); if (success) setMessage(success(result)); } catch (reason) { const payload = reason.response?.data; setError(payload?.file || payload?.detail || "Операция не выполнена."); } finally { setWorking(false); } };
  const upload = (file) => action(async () => { const result = await uploadLeadGenerationPlan(file); await load(); return result; }, (result) => `Загружено ${result.loaded} строк: добавлено ${result.created}, обновлено ${result.updated}.`);
  const saveSources = (ids) => action(async () => { await saveLeadGenerationSources(ids); const config = await getLeadGenerationSources(); setSourceConfig(config); setSettingsOpen(false); await load(); return config; }, () => "Настройка источников сохранена.");
  const reset = () => setFilters({ week_from:"2024-12-30", week_to:currentMonday(), include_select_market:true });
  const last = (state) => state?.last_success_at ? new Date(state.last_success_at).toLocaleString("ru-RU") : "нет успешного обновления";
  const tooltipSections = [{ title:"Актуальность источников", content:<><span>CRM: {last(refreshInfo?.bitrix)}</span><br /><span>Яндекс Директ: {last(refreshInfo?.direct)}</span></> }, { title:"Витрина лидогенерации", content:<><span>Опубликована: {last(refreshInfo?.mart)}</span><br /></> }, { title:"Расписание", content:<><span>CRM: пн–сб в 03:10 и 15:10 МСК; вс выполняется дополнительная сверка последних лидов.</span><br /><span>Яндекс Директ: ежедневно в 06:50 МСК. Ручные обновления обоих источников также запускают пересборку витрины.</span></> }];
  return <main className="leadgen-dashboard"><header className="leadgen-title"><h1>Лидогенерация <RefreshInfoTooltip sections={tooltipSections}><button type="button" className="dashboard-refresh-info" aria-label="Информация об обновлении данных">i</button></RefreshInfoTooltip></h1></header><section className="leadgen-tabs"><button type="button" className={page === "plan" ? "is-active" : ""} onClick={() => setPage("plan")}>План</button><button type="button" className={page === "sources" ? "is-active" : ""} onClick={() => setPage("sources")}>Источники</button></section><section className="leadgen-controls"><LeadGenerationWeekRangePicker start={filters.week_from} end={filters.week_to} resetRange={{ start:"2024-12-30", end:currentMonday() }} onChange={({ start, end }) => setFilters((old) => ({ ...old, week_from:start, week_to:end }))} /><div className="leadgen-market-toggle"><span>Целевые лиды</span><button type="button" className={filters.include_select_market ? "is-active" : ""} onClick={() => setFilters((old) => ({ ...old, include_select_market:true }))}>С Селект Маркетом</button><button type="button" className={!filters.include_select_market ? "is-active" : ""} onClick={() => setFilters((old) => ({ ...old, include_select_market:false }))}>Без Селект Маркета</button></div>{page === "sources" && <button type="button" className="leadgen-source-button" onClick={() => setSettingsOpen(true)}>Отслеживать источники</button>}<div className="leadgen-actions"><button type="button" disabled={working} onClick={() => action(async () => download(await downloadLeadGenerationPlan(), "lead_generation_plan.xlsx"))}>Выгрузить текущий план</button>{dashboard?.can_edit && <><button type="button" disabled={working} onClick={() => fileRef.current?.click()}>Загрузить план</button><input ref={fileRef} type="file" accept=".xlsx" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) upload(file); event.target.value = ""; }} /></>}<button type="button" disabled={working} onClick={() => action(async () => download(await exportLeadGenerationReport(page, filters), `lead_generation_${page}.xlsx`))}>Экспорт</button><button type="button" disabled={working} onClick={reset}>Очистить</button></div></section><div className="leadgen-toast-stack" aria-live="polite"><LeadgenToast message={error} type="error" clear={setError} /><LeadgenToast message={message} type="success" clear={setMessage} /></div><DataTable key={page} page={page} rows={report.rows || []} sources={report.sources || []} revenueDirections={report.revenue_directions || []} dealFunnels={report.deal_funnels || []} potentialOpen={potentialOpen} setPotentialOpen={setPotentialOpen} />{(loading || working) && <LoadingBlock />}{settingsOpen && <SourceSettings options={sourceConfig.options || []} selected={sourceConfig.selected || []} onSave={saveSources} onClose={() => setSettingsOpen(false)} />}</main>;
}
