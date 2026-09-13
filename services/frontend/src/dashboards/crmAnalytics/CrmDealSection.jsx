import { DetailTableColumns } from "./DetailTableColumns";
import { SummaryTableFrame } from "./SummaryTableFrame";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { DateRangePicker } from "../../components/DateRangePicker";
import { MultiSelect, DynamicsChart, FormulaHeader, periodLabel, DetailDateTime, GlobalSpinner, ConversionModal, CrmToast, DeltaMetric, InlineDelta } from "./CrmAnalyticsDashboard";
import { crmSectionRequest, exportCrmSection } from "./crmDealApi";

const GROUPS = [["day", "День"], ["week", "Неделя"], ["month", "Месяц"], ["year", "Год"]];
const RESULTS = [{ id: "S", name: "Успешные" }, { id: "F", name: "Проигранные" }, { id: "P", name: "В работе" }];
const UNTRACKED = "Неотслеживаемые";
const format = (value, digits = 0) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const dealsLabel = (value) => { const count = Number(value || 0); const absolute = Math.abs(count); const lastTwo = absolute % 100; const last = absolute % 10; const word = lastTwo >= 11 && lastTwo <= 14 ? "сделок" : last === 1 ? "сделка" : last >= 2 && last <= 4 ? "сделки" : "сделок"; return `${format(count)} ${word}`; };
function defaults() { const now = new Date(); const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); return { date_start: `${now.getFullYear()}-01-01`, date_end: local, department_names: [], manager_ids: [], source_ids: [], category_ids: [0, 2, 5], stage_keys: [], results: [], exclude_untracked_department: true, use_personal_departments: true, group_by: "month", lead_link: "all" }; }

function Cards({ items }) {
  return <section className="crm-kpi-cards">{items.map((item) => <article key={item.label}><div className="crm-kpi-card__label"><span>{item.label}</span>{item.help && <span className="crm-kpi-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{item.help}</span></span>}</div><div className="crm-kpi-card__value"><strong>{format(item.value, item.digits || 0)}{item.value != null && item.suffix}</strong>{item.share != null && <small className="crm-kpi-share">{format(item.share, 1)}%{item.shareHelp && <span className="crm-kpi-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">{item.shareHelp}</span></span>}</small>}{item.action && <button type="button" className="crm-kpi-trend-button" onClick={item.action} aria-label="Показать динамику конверсии" title="Показать динамику конверсии"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18V6M5 18h14" /><path d="m7.5 14 3.2-3.2 2.6 2.1 4.2-5" /><circle cx="7.5" cy="14" r=".75" /><circle cx="10.7" cy="10.8" r=".75" /><circle cx="13.3" cy="12.9" r=".75" /><circle cx="17.5" cy="7.9" r=".75" /></svg></button>}</div>{item.delta != null && <small>{item.delta > 0 ? "+" : ""}{format(item.delta, 1)} {item.suffix === "%" ? "п.п." : "ед."} к прошлому году</small>}</article>)}</section>;
}

function DealSummaryTable({ report, kind, onSelect, categories, comparisonPeriod }) {
  const [collapsed, setCollapsed] = useState(() => new Set());
  const rows = [...(report.summary || [])];
  const quality = ["sources", "managers"].includes(kind);
  const shareFormula = "Доля = Количество по строке / Итого по таблице × 100%.";
  const quantityDeltaFormulas = ["Δ количества = Количество текущего периода − Количество аналогичного периода прошлого года.", "Изменение, % = Δ количества / Количество прошлого года × 100%."];
  const shareDeltaFormula = "Δ доли, п.п. = Доля текущего периода − Доля аналогичного периода прошлого года.";
  const successFormulas = ["Успешные = количество успешных сделок по строке.", "Изменение, % = (Успешные текущего периода − Успешные прошлого периода) / Успешные прошлого периода × 100%."];
  const conversionFormulas = ["Конверсия = Успешные / (Успешные + Проигранные) × 100%.", "Изменение, п.п. = Конверсия текущего периода − Конверсия прошлого года."];
  const repeatFormula = "Доля повторных сделок рассчитывается от общего количества сделок.";
  let lastCategory = null;
  const renderRow = (row, total = false) => { const previousCount = Number(row.total || 0) - Number(row.delta_count || 0); const previousShare = row.delta_share == null || row.share == null ? null : Number(row.share) - Number(row.delta_share); const repeatShare = row.total ? Number(row.return_customers || 0) * 100 / Number(row.total) : null; return <tr key={total ? "total" : row.key} className={total ? "crm-summary-total" : ""}><th><button type="button" className="crm-text-link" title={row.name} onClick={() => onSelect(row.key)}>{row.name}</button></th><td><strong>{format(row.total)}</strong></td><td>{row.share == null ? "—" : `${format(row.share, 1)}%`}</td>{quality && <><td><span className="crm-summary-value"><strong>{format(row.success)}</strong><InlineDelta current={row.success} previous={row.previous_success} /></span></td><td><span className="crm-summary-value"><strong>{row.conversion == null ? "—" : `${format(row.conversion, 1)}%`}</strong><InlineDelta current={row.conversion} previous={row.previous_conversion} points /></span></td></>}<td><DeltaMetric current={row.total} previous={previousCount} favorableDecrease={kind === "loss-reasons"} /></td>{!quality && <td><DeltaMetric current={row.share} previous={previousShare} share favorableDecrease={kind === "loss-reasons"} /></td>}<td><span className="crm-summary-value crm-return-customer-value"><strong>{format(row.return_customers)}</strong><small>{repeatShare == null ? "—" : `${format(repeatShare, 1)}%`}</small></span></td></tr>; };
  const firstHeader = kind === "managers" ? "Менеджер" : kind === "results" ? "Статус" : kind === "sources" ? "Источник" : "Стадия";
  return <SummaryTableFrame><table><thead><tr><th>{firstHeader}</th><th>Количество</th><th><FormulaHeader formulas={[shareFormula]}>Доля, %</FormulaHeader></th>{quality && <><th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={successFormulas}>Успешные</FormulaHeader></th><th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={conversionFormulas}>Конверсия, %</FormulaHeader></th></>}<th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={quantityDeltaFormulas}>Δ количества</FormulaHeader></th>{!quality && <th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={[shareDeltaFormula]}>Δ доли, п.п.</FormulaHeader></th>}<th><FormulaHeader formulas={[repeatFormula]}>Повторные</FormulaHeader></th></tr></thead><tbody>{report.total && renderRow(report.total, true)}{rows.flatMap((row) => {
    const header = kind === "stages" && lastCategory !== row.category_id;
    lastCategory = row.category_id;
    const closed = collapsed.has(row.category_id);
    return [header && <tr className="crm-category-row" key={`category-${row.category_id}`}><th colSpan={quality ? 7 : 6}><button type="button" aria-expanded={!closed} onClick={() => setCollapsed((old) => { const next = new Set(old); if (next.has(row.category_id)) next.delete(row.category_id); else next.add(row.category_id); return next; })}>{closed ? "▸" : "▾"} {categories.find((c) => c.category_id === row.category_id)?.name || row.category_id}</button></th></tr>, !closed && renderRow(row)];
  })}</tbody></table></SummaryTableFrame>;
}

const DEAL_DETAIL_COLUMNS = [["deal_id", "ID сделки"], ["lead_id", "ID лида"], ["title", "Наименование сделки"], ["is_return_customer", "Повторная сделка"], ["deal_type_name", "Тип"], ["manager_name", "Менеджер"], ["department_name", "Подразделение"], ["category_name", "Воронка"], ["stage_name", "Стадия"], ["source_name", "Источник"], ["activity_name", "Мероприятие"], ["source_created_at", "Дата создания"], ["speed_calculated_at", "Скорость рассчитана по"], ["amount", "Сумма, руб"], ["processing_duration_days", "Скорость обработки"]];
const humanDuration = (days) => { if (days == null) return "—"; const seconds = Math.max(0, Math.round(Number(days) * 86400)); const wholeDays = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); return wholeDays ? `${wholeDays} дн. ${hours} час.` : hours ? `${hours} час.` : `${Math.max(1, Math.round(seconds / 60))} мин.`; };
const periodCaption = (start, end) => `${new Date(`${start}T00:00:00`).toLocaleDateString("ru-RU")} — ${new Date(`${end}T00:00:00`).toLocaleDateString("ru-RU")}`;

function Details({ state, data, busy, onClose, onChange, onExport, filters }) {
  const tableHeadRef = useRef(null); const [tableHeadHeight, setTableHeadHeight] = useState(52);
  useLayoutEffect(() => { const node = tableHeadRef.current; if (!node) return undefined; const update = () => setTableHeadHeight(Math.ceil(node.getBoundingClientRect().height)); update(); const observer = new ResizeObserver(update); observer.observe(node); return () => observer.disconnect(); }, [state]);
  if (!state) return null;
  const columns = DEAL_DETAIL_COLUMNS;
  const speedHelp = ["Завершённая сделка: (дата перехода в текущую финальную стадию − дата создания сделки) / 86 400 сек.", "Сделка в работе: (дата расчёта − дата создания сделки) / 86 400 сек.", "В строке «Итого» показывается средняя скорость обработки выбранных сделок."];
  const displayValue = (row, key) => {
    if (key === "title") return <span className="crm-detail-title" title={row[key] || ""}>{row[key] || "—"}</span>;
    if (key === "is_return_customer") return <small className="crm-customer-badge">{row[key] ? "Повторная" : "Новая"}</small>;
    if (key === "deal_type_name") return <small className="crm-customer-badge">{row[key] || "Не указан"}</small>;
    if (key === "speed_calculated_at") return <DetailDateTime value={row[key]} />;
    if (key === "processing_duration_days") return humanDuration(row[key]);
    if (key.endsWith("_at")) return <DetailDateTime value={row[key]} />;
    if (key === "amount") return format(row[key], 0);
    if (typeof row[key] === "number") return format(row[key], key.endsWith("days") ? 1 : 0);
    return row[key] || "—";
  };
  return <div className="crm-modal crm-modal--deal-details" role="dialog" aria-modal="false" aria-label={state.title}><div className="crm-modal__card"><div className="crm-modal__header"><div><h2>{state.title}</h2><p>{state.period ? periodLabel(state.period, filters.group_by) : periodCaption(filters.date_start, filters.date_end)} · найдено {format(data.total)}</p></div><div><button className="crm-action" onClick={onExport}>Экспорт</button><button type="button" className="crm-close" onClick={onClose} aria-label="Закрыть">×</button></div></div><div className="crm-table-wrap" style={{ "--crm-detail-header-height": `${tableHeadHeight}px` }}><table><DetailTableColumns columns={columns} /><thead ref={tableHeadRef}><tr>{columns.map(([key, label]) => <th key={key}><button type="button" onClick={() => onChange({ ...state, page: 1, sort_by: key, sort_direction: state.sort_by === (key) && state.sort_direction === "desc" ? "asc" : "desc" })}>{key === "processing_duration_days" ? <FormulaHeader formulas={speedHelp}>{label}</FormulaHeader> : label}<i className={state.sort_by === key ? "is-active" : ""}>{state.sort_by === key ? (state.sort_direction === "asc" ? "↑" : "↓") : "↕"}</i></button></th>)}</tr></thead><tbody>{!busy && <tr className="crm-detail-summary"><td>Итого</td><td>—</td><td>{dealsLabel(data.summary?.total)}</td><td>{format(data.summary?.return_customers)} повторных</td>{Array.from({ length: 9 }, (_, index) => <td key={index}>—</td>)}<td>{format(data.summary?.amount)}</td><td>{humanDuration(data.summary?.processing_duration_days)}</td></tr>}{!busy && (data.items || []).map((row, index) => <tr key={`${row.lead_id}-${row.deal_id}-${index}`}>{columns.map(([key]) => <td key={key}>{displayValue(row, key)}</td>)}</tr>)}</tbody></table>{busy && <div className="crm-loading">Загрузка данных…</div>}</div><div className="crm-pagination"><button type="button" disabled={busy || state.page <= 1} onClick={() => onChange({ ...state, page: state.page - 1 })}>Назад</button><span>Страница {state.page} из {data.pages || 1}</span><button type="button" disabled={busy || state.page >= (data.pages || 1)} onClick={() => onChange({ ...state, page: state.page + 1 })}>Далее</button></div></div></div>;
}

export function CrmDealSection({ section, active, tab = "funnel", onTabChange = () => {}, resetToken = 0 }) {
  const [filters, setFilters] = useState(defaults);
  const setTab = onTabChange;
  const [options, setOptions] = useState({ categories: [], stages: [], managers: [], departments: [], sources: [], results: RESULTS });
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
  const reportScope = useRef(null);
  const previousResetToken = useRef(resetToken);
  useEffect(() => { if (previousResetToken.current === resetToken) return; previousResetToken.current = resetToken; setFilters(defaults()); setModal(null); setConversion(false); }, [resetToken]);
  const requestKey = JSON.stringify([section, filters, version, resetToken]);
  const scopeKey = JSON.stringify([section, filters, resetToken]);
  const loading = settledKey !== requestKey;
  useEffect(() => { const receive = (event) => { if (event.detail?.dashboard === "CRMAnalytics" && !["running", "failed"].includes(event.detail.status)) setVersion((old) => old + 1); }; window.addEventListener("dashboard:updated", receive); return () => window.removeEventListener("dashboard:updated", receive); }, []);
  useEffect(() => {
    if (!active || settledKey === requestKey) return undefined;
    const controller = new AbortController(); const request = ++generation.current;
    const load = async () => {
      setError("");
      try {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            const result = await crmSectionRequest(section, "report", filters, controller.signal);
            if (request === generation.current && !controller.signal.aborted) {
              reportScope.current = scopeKey;
              setOptions(result.options);
              setReport(result);
            }
            break;
          } catch (e) {
            if (e.response?.status !== 409 || attempt > 0 || controller.signal.aborted) throw e;
            await new Promise((resolve) => setTimeout(resolve, 300));
            if (controller.signal.aborted) return;
          }
        }
      } catch (e) { if (!controller.signal.aborted) { if (e.response?.status !== 409 || reportScope.current !== scopeKey) setReport(null); setError(e.response?.data?.detail || "Не удалось загрузить отчёт CRM."); } }
      finally { if (!controller.signal.aborted) setSettledKey(requestKey); }
    };
    const timer = setTimeout(load, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [section, active, filters, version, requestKey, settledKey, scopeKey]);
  useEffect(() => {
    if (!modal || !active) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(async () => { setDetailLoading(true); try { const result = await crmSectionRequest(section, "rows", { ...filters, ...modal }, controller.signal); if (!controller.signal.aborted) setDetails(result); } catch (e) { if (!controller.signal.aborted) { setDetails({ items: [] }); setError(e.response?.data?.detail || "Не удалось загрузить строки."); } } finally { if (!controller.signal.aborted) setDetailLoading(false); } }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [modal, section, filters, active, version]);
  const change = (patch) => { setFilters((old) => ({ ...old, ...patch })); setModal((old) => old ? { ...old, page: 1 } : old); };
  const open = useCallback((kind, key = "", period = null, title = "Сделки", keys = [], category = null) => { setDetails({ items: [] }); setDetailLoading(true); setModal({ segment_type: kind, segment_key: key, segment_keys: keys, period: period || null, title, detail_category_id: category, page: 1, sort_by: "source_created_at", sort_direction: "desc" }); }, []);
  const exportRows = async (detail = false) => { setExporting(true); try { const filename = section === "deals" ? (detail ? "bitrix24_deals_detail.xlsx" : "bitrix24_deals_generation.xlsx") : null; await exportCrmSection(section, { ...filters, tab, ...(detail ? modal : {}) }, filename); } catch { setError("Не удалось выгрузить Excel."); } finally { setExporting(false); } };
  const cards = report?.cards || {};
  const percent = (value) => cards.total ? value * 100 / cards.total : null;
  const cardItems = [{ label: "Итого", value: cards.total }, { label: "Успешные", value: cards.success, share: percent(cards.success), shareHelp: "Доля = Успешные сделки / Общее количество сделок × 100%." }, { label: "Проигранные", value: cards.lost, share: percent(cards.lost), shareHelp: "Доля = Проигранные сделки / Общее количество сделок × 100%." }, { label: "Конверсия", value: cards.conversion, suffix: "%", digits: 1, help: "Успешные / (Успешные + Проигранные) × 100%.", action: () => setConversion(true) }, { label: "В работе", value: cards.in_progress, share: percent(cards.in_progress), shareHelp: "Доля = Сделки в работе / Общее количество сделок × 100%." }, { label: "Сумма сделок", value: cards.amount, suffix: " ₽" }, { label: "Успешные сделки", value: cards.success_amount, suffix: " ₽" }, { label: "Повторные", value: cards.return_customers, share: percent(cards.return_customers), help: "Доля повторных сделок рассчитывается от общего количества сделок" }];
  const selectedDepartments = filters.department_names.length ? filters.department_names : filters.use_personal_departments ? (options.default_department_names || []) : filters.exclude_untracked_department ? options.departments.map((d) => d.department_name).filter((d) => d !== UNTRACKED) : [];
  const departmentLabels = new Map((options.department_preferences || []).map((item) => [item.filter_department_name, item.display_name]));
  const departmentOptions = options.departments.map((item) => ({ ...item, display_name: departmentLabels.get(item.department_name) || item.department_name }));
  const kinds = tab === "funnel" ? [["results", "Динамика по статусам"], ["sources", "Динамика по источникам"]] : [["managers", "Динамика по менеджерам"], ["loss-reasons", "Динамика проигранных сделок"]];
  if (!active) return null;
  if (loading && !report) return <GlobalSpinner />;
  return <main className="crm-dashboard crm-deal-section"><section className="crm-filters"><div className="crm-filter-actions"><button className="crm-action" disabled={exporting || loading} onClick={() => exportRows()}>Экспорт</button><button className="crm-action" onClick={() => change(defaults())}>Очистить</button></div><div className="crm-filter-grid">
    <MultiSelect label="Подразделение" options={departmentOptions} selected={selectedDepartments} emptyLabel={filters.use_personal_departments ? "Не выбрано" : "Все"} valueKey="department_name" labelKey="display_name" onChange={(value) => change({ department_names: value, manager_ids: [], use_personal_departments: false, exclude_untracked_department: !value.includes(UNTRACKED) })} />
    <MultiSelect label="Менеджер" options={options.managers} selected={filters.manager_ids} valueKey="manager_id" labelKey="manager_name" onChange={(value) => change({ manager_ids: value, use_personal_departments: false })} />
    <MultiSelect label="Источник" options={options.sources} selected={filters.source_ids} valueKey="source_id" labelKey="source_name" onChange={(value) => change({ source_ids: value })} />
    <MultiSelect label="Воронка" options={options.categories} selected={filters.category_ids} valueKey="category_id" labelKey="name" onChange={(value) => change({ category_ids: value, stage_keys: [] })} />
    <MultiSelect label="Статус" options={options.results ?? RESULTS} selected={filters.results} valueKey="id" labelKey="name" onChange={(value) => change({ results: value })} /><MultiSelect label="Стадия" options={options.stages.map((s) => ({ ...s, label: `${s.category_name} · ${s.name}` }))} selected={filters.stage_keys} valueKey="key" labelKey="label" onChange={(value) => change({ stage_keys: value })} />
    <DateRangePicker start={filters.date_start} end={filters.date_end} onChange={({ start, end }) => change({ date_start: start, date_end: end })} />
    <div className="crm-filter crm-group-filter"><span>Группировка</span><div>{GROUPS.map(([key, label]) => <button key={key} className={filters.group_by === key ? "active" : ""} onClick={() => change({ group_by: key })}>{label}</button>)}</div></div>
    <div className="crm-filter crm-group-filter crm-lead-link-filter"><span>Связь с лидом</span><div><button type="button" className={filters.lead_link === "all" ? "active" : ""} onClick={() => change({ lead_link: "all" })}>Все сделки</button><button type="button" className={filters.lead_link === "linked" ? "active" : ""} onClick={() => change({ lead_link: "linked" })}>Из лидов <span className="crm-filter-help" tabIndex={0}><i aria-hidden="true">i</i><span role="tooltip">Только сделки, имеющие прямую связь с лидом</span></span></button></div></div>
  </div></section>
    {error && <div className="crm-toast-stack" aria-live="polite"><CrmToast message={error} onClose={() => setError("")} /></div>}{report && <><Cards items={cardItems} />{cards.missing_history > 0 && <p className="crm-cohort-note">Есть записи без истории стадий: {format(cards.missing_history)}. Неизвестные даты и длительности показаны прочерком.</p>}<nav className="crm-tabs"><button className={tab === "funnel" ? "active" : ""} onClick={() => setTab("funnel")}>Статусы и источники сделок</button><button className={tab === "managers" ? "active" : ""} onClick={() => setTab("managers")}>Менеджеры и эффективность сделок</button></nav>{cards.total ? <section className="crm-chart-grid">{kinds.map(([kind, title], index) => <DynamicsChart key={kind} title={title} rows={report[kind]?.rows || []} groupBy={filters.group_by} segmentType={kind} tooltipSide={index === 0 ? "right" : "left"} dimensionOrder={kind === "stages" || kind === "results" ? (report[kind]?.summary || []).map((row) => row.key) : undefined} onOpen={open} summaryContent={<DealSummaryTable kind={kind} report={report[kind] || {}} categories={options.categories} comparisonPeriod={report[kind]?.comparison_period} onSelect={(key) => open(kind, key, null, title)} />} />)}</section> : <p className="crm-empty">По выбранным условиям сделки не найдены</p>}</>}
    {(loading || exporting) && <GlobalSpinner />}{conversion && <ConversionModal open rows={report?.results?.rows || []} groupBy={filters.group_by} dateStart={filters.date_start} dateEnd={filters.date_end} onClose={() => setConversion(false)} />}<Details filters={filters} state={modal} data={details} busy={detailLoading} onClose={() => setModal(null)} onChange={setModal} onExport={() => exportRows(true)} />
  </main>;
}
