import { useCallback, useEffect, useRef, useState } from "react";
import { Line, LineChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { DateRangePicker } from "../../components/DateRangePicker";
import { MultiSelect, DynamicsChart, FormulaHeader, GlobalSpinner, ResponsiveContainer } from "./CrmAnalyticsDashboard";
import { crmSectionRequest, exportCrmSection } from "./crmDealApi";
import { FullCycleFunnel } from "./FullCycleFunnel";

const GROUPS = [["day", "День"], ["week", "Неделя"], ["month", "Месяц"], ["year", "Год"]];
const RESULTS = [{ id: "S", name: "Успешные" }, { id: "F", name: "Проигранные" }, { id: "P", name: "В работе" }];
const UNTRACKED = "Неотслеживаемые";
const format = (value, digits = 0) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const dateTime = (value) => value ? new Date(value).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" }) : "—";
function defaults(full = false) { const now = new Date(); const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); return { date_start: `${now.getFullYear()}-01-01`, date_end: local, department_names: [], manager_ids: [], source_ids: [], category_ids: [0, 2, 5], stage_keys: [], results: [], exclude_untracked_department: true, ...(full ? {} : { group_by: "month" }) }; }

function Cards({ items }) {
  return <section className="crm-kpi-cards">{items.map((item) => <article key={item.label}><div className="crm-kpi-card__label"><span>{item.label}</span>{item.help && <span className="crm-kpi-help" tabIndex={0}><i>i</i><span role="tooltip">{item.help}</span></span>}</div><div className="crm-kpi-card__value"><strong>{format(item.value, item.digits || 0)}{item.value != null && item.suffix}</strong>{item.share != null && <small className="crm-kpi-share">{format(item.share, 1)}%</small>}{item.action && <button type="button" className="crm-action" onClick={item.action} aria-label="Динамика конверсии">↗</button>}</div>{item.delta != null && <small>{item.delta > 0 ? "+" : ""}{format(item.delta, 1)} {item.suffix === "%" ? "п.п." : "дн."} к прошлому году</small>}</article>)}</section>;
}

const TABLE_COLUMNS = {
  stages: [["total", "Количество"], ["share", "Доля, %"], ["amount", "Сумма, ₽"], ["conversion", "Конверсия, %"], ["delta_count", "Δ количества"], ["delta_share", "Δ доли, п.п."], ["stage_days", "Ср. время, дней"]],
  results: [["total", "Количество"], ["share", "Доля, %"], ["amount", "Сумма, ₽"], ["average_check", "Средний чек, ₽"], ["cycle_days", "Средний цикл, дней"], ["delta_count", "Δ количества"], ["delta_amount", "Δ суммы, ₽"]],
  managers: [["total", "Сделок"], ["share", "Доля, %"], ["amount", "Сумма, ₽"], ["success", "Успешных"], ["conversion", "Конверсия, %"], ["average_check", "Средний чек, ₽"], ["delta_amount", "Δ суммы, ₽"]],
  "loss-reasons": [["total", "Количество"], ["share", "Доля, %"], ["amount", "Сумма потерь, ₽"], ["delta_count", "Δ количества"], ["delta_share", "Δ доли, п.п."], ["delta_amount", "Δ суммы, ₽"]],
};

function DealSummaryTable({ report, kind, onSelect, categories }) {
  const [sort, setSort] = useState(null);
  const [collapsed, setCollapsed] = useState(() => new Set());
  const columns = TABLE_COLUMNS[kind];
  const rows = [...(report.summary || [])];
  if (sort && kind !== "stages") rows.sort((a, b) => (Number(a[sort.key] || 0) - Number(b[sort.key] || 0)) * sort.direction);
  let lastCategory = null;
  const renderRow = (row, total = false) => <tr key={total ? "total" : row.key} className={total ? "crm-summary-total" : ""}><th><button type="button" className="crm-text-link" onClick={() => onSelect(row.key)}>{row.name}</button></th>{columns.map(([key]) => <td key={key}>{format(row[key], ["share", "conversion", "delta_share", "stage_days", "cycle_days"].includes(key) ? 1 : 0)}</td>)}</tr>;
  return <div className="crm-summary-wrap"><table><thead><tr><th>{kind === "stages" ? "Стадия" : kind === "managers" ? "Менеджер" : kind === "results" ? "Результат" : "Причина"}</th>{columns.map(([key, label]) => <th key={key}><button type="button" onClick={() => setSort((old) => ({ key, direction: old?.key === key ? -old.direction : -1 }))}>{label}</button></th>)}</tr></thead><tbody>{report.total && renderRow(report.total, true)}{rows.flatMap((row) => {
    const header = kind === "stages" && lastCategory !== row.category_id;
    lastCategory = row.category_id;
    const closed = collapsed.has(row.category_id);
    return [header && <tr className="crm-category-row" key={`category-${row.category_id}`}><th colSpan={columns.length + 1}><button type="button" aria-expanded={!closed} onClick={() => setCollapsed((old) => { const next = new Set(old); if (next.has(row.category_id)) next.delete(row.category_id); else next.add(row.category_id); return next; })}>{closed ? "▸" : "▾"} {categories.find((c) => c.category_id === row.category_id)?.name || row.category_id}</button></th></tr>, !closed && renderRow(row)];
  })}</tbody></table></div>;
}

const DETAIL_COLUMNS = [["deal_id", "ID сделки"], ["lead_id", "ID лида"], ["title", "Сделка"], ["manager_name", "Менеджер"], ["department_name", "Подразделение"], ["category_name", "Воронка"], ["stage_name", "Стадия"], ["source_created_at", "Создана"], ["closed_at", "Завершена по истории"], ["stage_days", "Дней на стадии"], ["cycle_days", "Цикл, дней"], ["amount", "Сумма, ₽"]];
function Details({ state, data, busy, onClose, onChange, onExport, section }) {
  if (!state) return null;
  const columns = section === "full-cycle" ? [["lead_title", "Лид"], ["lead_created_at", "Создан лид"], ...DETAIL_COLUMNS, ["full_cycle_days", "Полный цикл, дней"], ["selected_stage_days", "Дней на выбранном этапе"], ["link_state", "Связь"]] : DETAIL_COLUMNS;
  return <div className="crm-modal" role="dialog" aria-label={state.title}><div className="crm-modal__card"><header className="crm-modal__header"><div><h2>{state.title}</h2><p>Найдено: {format(data.total)}</p></div><div><button className="crm-action" onClick={onExport}>Экспорт</button><button className="crm-action" onClick={onClose}>Закрыть</button></div></header>{busy ? <p>Загрузка…</p> : <div className="crm-table-wrap"><table><thead><tr>{columns.map(([key, label]) => <th key={key}><button onClick={() => onChange({ ...state, page: 1, sort_by: key, sort_direction: state.sort_by === key && state.sort_direction === "desc" ? "asc" : "desc" })}>{label}</button></th>)}</tr></thead><tbody>{(data.items || []).map((row, index) => <tr key={`${row.lead_id}-${row.deal_id}-${index}`}>{columns.map(([key]) => <td key={key}>{key.endsWith("_at") ? dateTime(row[key]) : typeof row[key] === "number" ? format(row[key], key.endsWith("days") ? 1 : 0) : row[key] || "—"}</td>)}</tr>)}</tbody></table></div>}<footer className="crm-detail-pagination"><button className="crm-action" disabled={busy || state.page <= 1} onClick={() => onChange({ ...state, page: state.page - 1 })}>Назад</button><span>{state.page} / {data.pages || 1}</span><button className="crm-action" disabled={busy || state.page >= (data.pages || 1)} onClick={() => onChange({ ...state, page: state.page + 1 })}>Далее</button></footer></div></div>;
}

function DealConversion({ report, close }) {
  if (!report) return null;
  const periods = new Map();
  (report.rows || []).forEach((row) => { const entry = periods.get(row.period) || { period: row.period, success: 0, lost: 0, oldSuccess: 0, oldLost: 0 }; entry.success += row.dimension_target || 0; entry.lost += row.dimension_low_quality || 0; entry.oldSuccess += row.previous_year_dimension_target || 0; entry.oldLost += row.previous_year_dimension_low_quality || 0; periods.set(row.period, entry); });
  const rows = [...periods.values()].map((row) => ({ ...row, conversion: row.success + row.lost ? row.success * 100 / (row.success + row.lost) : null, previous: row.oldSuccess + row.oldLost ? row.oldSuccess * 100 / (row.oldSuccess + row.oldLost) : null }));
  return <div className="crm-modal crm-conversion-modal" role="dialog" aria-label="Конверсия сделок"><div className="crm-modal__card"><header className="crm-modal__header"><h2>Конверсия сделок</h2><button className="crm-action" onClick={close}>Закрыть</button></header><p>Успешные / (Успешные + Проигранные) × 100%. Сделки в работе не включаются.</p><ResponsiveContainer width="100%" height={360}><LineChart data={rows} margin={{ top: 20, right: 24, bottom: 20, left: 8 }}><CartesianGrid strokeDasharray="3 4" /><XAxis dataKey="period" /><YAxis unit="%" /><Tooltip formatter={(v) => `${format(v, 1)}%`} /><Legend /><Line name="Заданный период" dataKey="conversion" stroke="#506f4e" strokeWidth={3} connectNulls={false} /><Line name="Прошлый год" dataKey="previous" stroke="#8f879c" strokeDasharray="6 5" connectNulls={false} /></LineChart></ResponsiveContainer></div></div>;
}

export function CrmDealSection({ section, active, tab = "funnel", onTabChange = () => {} }) {
  const full = section === "full-cycle";
  const [filters, setFilters] = useState(() => defaults(full));
  const setTab = onTabChange;
  const [options, setOptions] = useState({ categories: [], stages: [], managers: [], departments: [], sources: [] });
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [settledKey, setSettledKey] = useState(null);
  const [version, setVersion] = useState(0);
  const [modal, setModal] = useState(null);
  const [details, setDetails] = useState({ items: [] });
  const [detailLoading, setDetailLoading] = useState(false);
  const [conversion, setConversion] = useState(false);
  const [exporting, setExporting] = useState(false);
  const generation = useRef(0);
  const requestKey = JSON.stringify([section, filters, version]);
  const loading = settledKey !== requestKey;
  useEffect(() => { const receive = (event) => { if (event.detail?.dashboard === "CRMAnalytics" && !["running", "failed"].includes(event.detail.status)) setVersion((old) => old + 1); }; window.addEventListener("dashboard:updated", receive); return () => window.removeEventListener("dashboard:updated", receive); }, []);
  useEffect(() => {
    if (!active || settledKey === requestKey) return undefined;
    const controller = new AbortController(); const request = ++generation.current;
    const load = async () => {
      setError("");
      try {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          const [summary, opts] = await Promise.all([crmSectionRequest(section, "summary", filters, controller.signal), crmSectionRequest(section, "filters", filters, controller.signal)]);
          const parts = full ? ["funnel", "managers"] : ["stages", "results", "managers", "loss-reasons"];
          const values = await Promise.all(parts.map((part) => crmSectionRequest(section, part, filters, controller.signal)));
          if (summary.snapshot && [opts, ...values].some((value) => value.snapshot !== summary.snapshot)) {
            if (attempt === 0) continue;
            throw new Error("CRM snapshot changed");
          }
          if (request === generation.current && !controller.signal.aborted) { setOptions(opts); setReport({ ...summary, ...Object.fromEntries(parts.map((part, index) => [part, values[index]])) }); }
          break;
        }
      } catch (e) { if (!controller.signal.aborted) { setReport(null); setError(e.response?.data?.detail || "Не удалось загрузить отчёт CRM."); } }
      finally { if (!controller.signal.aborted) setSettledKey(requestKey); }
    };
    const timer = setTimeout(load, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [section, active, filters, full, version, requestKey, settledKey]);
  useEffect(() => {
    if (!modal || !active) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(async () => { setDetailLoading(true); try { const result = await crmSectionRequest(section, "rows", { ...filters, ...modal }, controller.signal); if (!controller.signal.aborted) setDetails(result); } catch (e) { if (!controller.signal.aborted) { setDetails({ items: [] }); setError(e.response?.data?.detail || "Не удалось загрузить строки."); } } finally { if (!controller.signal.aborted) setDetailLoading(false); } }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [modal, section, filters, active, version]);
  const change = (patch) => { setModal(null); setConversion(false); setFilters((old) => ({ ...old, ...patch })); };
  const open = useCallback((kind, key = "", period = null, title = "Сделки", keys = [], category = null) => { setDetails({ items: [] }); setDetailLoading(true); setModal({ segment_type: kind, segment_key: key, segment_keys: keys, period: period || null, title, detail_category_id: category, page: 1, sort_by: "source_created_at", sort_direction: "desc" }); }, []);
  const exportRows = async (detail = false) => { setExporting(true); try { await exportCrmSection(section, { ...filters, tab, ...(detail ? modal : {}) }); } catch { setError("Не удалось выгрузить Excel."); } finally { setExporting(false); } };
  const cards = report?.cards || {};
  const previous = report?.previous || {};
  const percent = (value) => cards.total ? value * 100 / cards.total : null;
  const cardItems = full ? [
    { label: "Лиды", value: cards.leads }, { label: "Связанные сделки", value: cards.deals },
    ...[["lead_to_deal", "Лид → сделка", "Лиды хотя бы с одной связанной сделкой / исходные лиды × 100%. Лид считается один раз."], ["deal_to_success", "Сделка → успех", "Успешные связанные сделки / все связанные сделки × 100%."], ["lead_to_success", "Лид → успешная сделка", "Успешные связанные сделки / исходные лиды × 100%. При нескольких сделках на лид показатель может превышать 100%."]].map(([key, label, help]) => ({ label, help, value: cards[key], suffix: "%", digits: 1, delta: cards[key] == null || previous[key] == null ? null : cards[key] - previous[key] })),
    { label: "Средний полный цикл", value: cards.full_cycle_days, suffix: " дн.", digits: 1, help: "Среднее время от создания лида до успешного завершения каждой связанной сделки по истории стадий.", delta: cards.full_cycle_days == null || previous.full_cycle_days == null ? null : cards.full_cycle_days - previous.full_cycle_days },
  ] : [{ label: "Итого", value: cards.total }, { label: "Успешные", value: cards.success, share: percent(cards.success) }, { label: "Проигранные", value: cards.lost, share: percent(cards.lost) }, { label: "Конверсия", value: cards.conversion, suffix: "%", digits: 1, help: "Успешные / (Успешные + Проигранные) × 100%.", action: () => setConversion(true) }, { label: "В работе", value: cards.in_progress, share: percent(cards.in_progress) }, { label: "Сумма сделок", value: cards.amount, suffix: " ₽" }, { label: "Успешные сделки", value: cards.success_amount, suffix: " ₽" }, { label: "Средний чек", value: cards.average_check, suffix: " ₽", help: "Сумма успешных сделок / количество успешных сделок." }];
  const selectedDepartments = filters.department_names.length ? filters.department_names : filters.exclude_untracked_department ? options.departments.map((d) => d.department_name).filter((d) => d !== UNTRACKED) : [];
  const kinds = tab === "funnel" ? [["stages", "Динамика по стадиям"], ["results", "Динамика результатов"]] : [["managers", "Динамика по менеджерам"], ["loss-reasons", "Динамика проигранных сделок"]];
  if (!active) return null;
  if (loading) return <GlobalSpinner />;
  return <main className="crm-dashboard crm-deal-section"><section className="crm-filters"><div className="crm-filter-actions"><button className="crm-action" disabled={exporting || loading} onClick={() => exportRows()}>Экспорт</button><button className="crm-action" onClick={() => change(defaults(full))}>Очистить</button></div><div className="crm-filter-grid">
    <MultiSelect label="Подразделение" options={options.departments} selected={selectedDepartments} valueKey="department_name" labelKey="department_name" onChange={(value) => change({ department_names: value, manager_ids: [], exclude_untracked_department: !value.includes(UNTRACKED) })} />
    <MultiSelect label="Менеджер" options={options.managers} selected={filters.manager_ids} valueKey="manager_id" labelKey="manager_name" onChange={(value) => change({ manager_ids: value })} />
    {full && <MultiSelect label="Источник" options={options.sources} selected={filters.source_ids} valueKey="source_id" labelKey="source_name" onChange={(value) => change({ source_ids: value })} />}
    <MultiSelect label="Воронка" options={options.categories} selected={filters.category_ids} valueKey="category_id" labelKey="name" onChange={(value) => change({ category_ids: value, stage_keys: [] })} />
    {!full && <><MultiSelect label="Статус" options={RESULTS} selected={filters.results} valueKey="id" labelKey="name" onChange={(value) => change({ results: value })} /><MultiSelect label="Стадия" options={options.stages.map((s) => ({ ...s, label: `${s.category_name} · ${s.name}` }))} selected={filters.stage_keys} valueKey="key" labelKey="label" onChange={(value) => change({ stage_keys: value })} /></>}
    <DateRangePicker start={filters.date_start} end={filters.date_end} onChange={({ start, end }) => change({ date_start: start, date_end: end })} />
    {!full && <div className="crm-filter crm-group-filter"><span>Группировка</span><div>{GROUPS.map(([key, label]) => <button key={key} className={filters.group_by === key ? "active" : ""} onClick={() => change({ group_by: key })}>{label}</button>)}</div></div>}
  </div></section>{full && <p className="crm-cohort-note"><FormulaHeader formulas={["Период определяется датой создания лида. Последующие события учитываются независимо от даты наступления.", "При выборе воронок остаются лиды с их сделками и лиды без сделок. Менеджер и подразделение относятся к лиду."]}>Когорта по дате создания лида</FormulaHeader></p>}
    {error && <div className="crm-alert">{error}</div>}{report && <><Cards items={cardItems} />{!full && cards.without_lead > 0 && <p className="crm-cohort-note"><button className="crm-text-link" onClick={() => open("standalone", "", null, "Сделки без лида")}>Сделки без лида: {format(cards.without_lead)}</button></p>}{cards.missing_history > 0 && <p className="crm-cohort-note">Есть записи без истории стадий: {format(cards.missing_history)}. Неизвестные даты и длительности показаны прочерком.</p>}{full ? <><FullCycleFunnel report={report} onOpen={open} dateEnd={filters.date_end} />{report.standalone > 0 && <p className="crm-cohort-note"><button className="crm-text-link" onClick={() => open("standalone", "", null, "Сделки без лида")}>Сделки без лида: {format(report.standalone)}</button> (включая удалённые и ненайденные лиды) — отдельно по дате создания сделки, вне лидовой когорты.</p>}</> : <><nav className="crm-tabs"><button className={tab === "funnel" ? "active" : ""} onClick={() => setTab("funnel")}>Стадии и результаты сделок</button><button className={tab === "managers" ? "active" : ""} onClick={() => setTab("managers")}>Менеджеры и эффективность сделок</button></nav>{cards.total ? <section className="crm-chart-grid">{kinds.map(([kind, title]) => <DynamicsChart key={kind} title={title} rows={report[kind]?.rows || []} groupBy={filters.group_by} segmentType={kind} dimensionOrder={kind === "stages" || kind === "results" ? (report[kind]?.summary || []).map((row) => row.key) : undefined} onOpen={open} summaryContent={<DealSummaryTable kind={kind} report={report[kind] || {}} categories={options.categories} onSelect={(key) => open(kind, key, null, title)} />} />)}</section> : <p className="crm-empty">По выбранным условиям сделки не найдены</p>}</> }</>}
    {(loading || exporting) && <GlobalSpinner />}{conversion && <DealConversion report={report?.results} close={() => setConversion(false)} />}<Details section={section} state={modal} data={details} busy={detailLoading} onClose={() => setModal(null)} onChange={setModal} onExport={() => exportRows(true)} />
  </main>;
}
