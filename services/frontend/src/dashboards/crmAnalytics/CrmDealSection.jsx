import { useCallback, useEffect, useRef, useState } from "react";
import { DateRangePicker } from "../../components/DateRangePicker";
import { MultiSelect, DynamicsChart, FormulaHeader, GlobalSpinner, ConversionModal, CrmToast, DeltaMetric, InlineDelta } from "./CrmAnalyticsDashboard";
import { crmSectionRequest, exportCrmSection } from "./crmDealApi";
import { FullCycleFunnel } from "./FullCycleFunnel";

const GROUPS = [["day", "День"], ["week", "Неделя"], ["month", "Месяц"], ["year", "Год"]];
const RESULTS = [{ id: "S", name: "Успешные" }, { id: "F", name: "Проигранные" }, { id: "P", name: "В работе" }];
const UNTRACKED = "Неотслеживаемые";
const format = (value, digits = 0) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const dateTime = (value) => value ? new Date(value).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" }) : "—";
function defaults(full = false) { const now = new Date(); const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); return { date_start: `${now.getFullYear()}-01-01`, date_end: local, department_names: [], manager_ids: [], source_ids: [], category_ids: [0, 2, 5], stage_keys: [], results: [], exclude_untracked_department: true, ...(full ? {} : { group_by: "month" }) }; }

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
  const renderRow = (row, total = false) => { const previousCount = Number(row.total || 0) - Number(row.delta_count || 0); const previousShare = row.delta_share == null || row.share == null ? null : Number(row.share) - Number(row.delta_share); const repeatShare = row.total ? Number(row.return_customers || 0) * 100 / Number(row.total) : null; return <tr key={total ? "total" : row.key} className={total ? "crm-summary-total" : ""}><th><button type="button" className="crm-text-link" onClick={() => onSelect(row.key)}>{row.name}</button></th><td><strong>{format(row.total)}</strong></td><td>{row.share == null ? "—" : `${format(row.share, 1)}%`}</td>{quality && <><td><span className="crm-summary-value"><strong>{format(row.success)}</strong><InlineDelta current={row.success} previous={row.previous_success} /></span></td><td><span className="crm-summary-value"><strong>{row.conversion == null ? "—" : `${format(row.conversion, 1)}%`}</strong><InlineDelta current={row.conversion} previous={row.previous_conversion} points /></span></td></>}<td><DeltaMetric current={row.total} previous={previousCount} favorableDecrease={kind === "loss-reasons"} /></td>{!quality && <td><DeltaMetric current={row.share} previous={previousShare} share favorableDecrease={kind === "loss-reasons"} /></td>}<td><span className="crm-summary-value crm-return-customer-value"><strong>{format(row.return_customers)}</strong><small>{repeatShare == null ? "—" : `${format(repeatShare, 1)}%`}</small></span></td></tr>; };
  const firstHeader = kind === "stages" ? "Стадия" : kind === "managers" ? "Менеджер" : kind === "results" ? "Статус" : kind === "sources" ? "Источник" : "Причина";
  return <div className="crm-summary-wrap"><table><thead><tr><th>{firstHeader}</th><th>Количество</th><th><FormulaHeader formulas={[shareFormula]}>Доля, %</FormulaHeader></th>{quality && <><th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={successFormulas}>Успешные</FormulaHeader></th><th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={conversionFormulas}>Конверсия, %</FormulaHeader></th></>}<th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={quantityDeltaFormulas}>Δ количества</FormulaHeader></th>{!quality && <th><FormulaHeader comparisonPeriod={comparisonPeriod} formulas={[shareDeltaFormula]}>Δ доли, п.п.</FormulaHeader></th>}<th><FormulaHeader formulas={[repeatFormula]}>Повторные</FormulaHeader></th></tr></thead><tbody>{report.total && renderRow(report.total, true)}{rows.flatMap((row) => {
    const header = kind === "stages" && lastCategory !== row.category_id;
    lastCategory = row.category_id;
    const closed = collapsed.has(row.category_id);
    return [header && <tr className="crm-category-row" key={`category-${row.category_id}`}><th colSpan={quality ? 7 : 6}><button type="button" aria-expanded={!closed} onClick={() => setCollapsed((old) => { const next = new Set(old); if (next.has(row.category_id)) next.delete(row.category_id); else next.add(row.category_id); return next; })}>{closed ? "▸" : "▾"} {categories.find((c) => c.category_id === row.category_id)?.name || row.category_id}</button></th></tr>, !closed && renderRow(row)];
  })}</tbody></table></div>;
}

const DEAL_DETAIL_COLUMNS = [["deal_id", "ID сделки"], ["lead_id", "ID лида"], ["title", "Наименование сделки"], ["is_return_customer", "Повторная сделка"], ["deal_type_name", "Тип"], ["manager_name", "Менеджер"], ["department_name", "Подразделение"], ["category_name", "Воронка"], ["stage_name", "Стадия"], ["source_name", "Источник"], ["activity_name", "Мероприятие"], ["source_created_at", "Дата создания"], ["speed_calculated_at", "Скорость рассчитана по"], ["amount", "Сумма, руб"], ["processing_duration_days", "Скорость обработки"]];
const FULL_DETAIL_COLUMNS = [["lead_title", "Лид"], ["lead_created_at", "Создан лид"], ["deal_id", "ID сделки"], ["lead_id", "ID лида"], ["title", "Сделка"], ["manager_name", "Менеджер"], ["department_name", "Подразделение"], ["category_name", "Воронка"], ["stage_name", "Стадия"], ["source_created_at", "Создана сделка"], ["closed_at", "Завершена по истории"], ["amount", "Сумма, руб"], ["full_cycle_days", "Полный цикл, дней"], ["selected_stage_days", "Дней на выбранном этапе"], ["link_state", "Связь"]];
const humanDuration = (days) => { if (days == null) return "—"; const seconds = Math.max(0, Math.round(Number(days) * 86400)); const wholeDays = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); return wholeDays ? `${wholeDays} дн. ${hours} час.` : hours ? `${hours} час.` : `${Math.max(1, Math.round(seconds / 60))} мин.`; };
const periodCaption = (start, end) => `${new Date(`${start}T00:00:00`).toLocaleDateString("ru-RU")} — ${new Date(`${end}T00:00:00`).toLocaleDateString("ru-RU")}`;
function Details({ state, data, busy, onClose, onChange, onExport, section, filters }) {
  if (!state) return null;
  const dealMode = section === "deals";
  const columns = dealMode ? DEAL_DETAIL_COLUMNS : FULL_DETAIL_COLUMNS;
  const speedHelp = ["Завершённая сделка: (дата входа в текущую финальную стадию − дата создания сделки) / 86 400 сек.", "Сделка в работе: (дата расчёта − дата создания сделки) / 86 400 сек.", "В строке «Итого» показывается средняя скорость обработки выбранных сделок."];
  const displayValue = (row, key) => {
    if (key === "is_return_customer") return <small className="crm-customer-badge">{row[key] ? "Повторная" : "Новая"}</small>;
    if (key === "deal_type_name") return <small className="crm-customer-badge">{row[key] || "Не указан"}</small>;
    if (key === "speed_calculated_at") return dateTime(row[key]);
    if (key === "processing_duration_days") return humanDuration(row[key]);
    if (key.endsWith("_at")) return dateTime(row[key]);
    if (key === "amount") return format(row[key], 0);
    if (typeof row[key] === "number") return format(row[key], key.endsWith("days") ? 1 : 0);
    return row[key] || "—";
  };
  return <div className="crm-modal" role="dialog" aria-modal="false" aria-label={state.title}><div className="crm-modal__card"><div className="crm-modal__header"><div><h2>{state.title}</h2><p>{periodCaption(filters.date_start, filters.date_end)} · найдено {format(data.total)}</p></div><div><button className="crm-action" onClick={onExport}>Экспорт</button><button type="button" className="crm-close" onClick={onClose} aria-label="Закрыть">×</button></div></div><div className="crm-table-wrap"><table><thead><tr>{columns.map(([key, label]) => <th key={key}><button type="button" onClick={() => onChange({ ...state, page: 1, sort_by: key, sort_direction: state.sort_by === (key) && state.sort_direction === "desc" ? "asc" : "desc" })}>{key === "processing_duration_days" ? <FormulaHeader formulas={speedHelp}>{label}</FormulaHeader> : label}<i className={state.sort_by === key ? "is-active" : ""}>{state.sort_by === key ? (state.sort_direction === "asc" ? "↑" : "↓") : "↕"}</i></button></th>)}</tr></thead><tbody>{dealMode && !busy && <tr className="crm-detail-summary"><td>Итого</td><td>—</td><td>{format(data.summary?.total)} сделок</td><td>{format(data.summary?.return_customers)} повторных</td>{Array.from({ length: 9 }, (_, index) => <td key={index}>—</td>)}<td>{format(data.summary?.amount)}</td><td>{humanDuration(data.summary?.processing_duration_days)}</td></tr>}{!busy && (data.items || []).map((row, index) => <tr key={`${row.lead_id}-${row.deal_id}-${index}`}>{columns.map(([key]) => <td key={key}>{displayValue(row, key)}</td>)}</tr>)}</tbody></table>{busy && <div className="crm-loading">Загрузка данных…</div>}</div><div className="crm-pagination"><button type="button" disabled={busy || state.page <= 1} onClick={() => onChange({ ...state, page: state.page - 1 })}>Назад</button><span>Страница {state.page} из {data.pages || 1}</span><button type="button" disabled={busy || state.page >= (data.pages || 1)} onClick={() => onChange({ ...state, page: state.page + 1 })}>Далее</button></div></div></div>;
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
          const parts = full ? ["funnel", "managers"] : ["results", "sources", "managers", "loss-reasons"];
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
  const exportRows = async (detail = false) => { setExporting(true); try { const filename = section === "deals" ? (detail ? "bitrix24_deals_detail.xlsx" : "bitrix24_deals_generation.xlsx") : null; await exportCrmSection(section, { ...filters, tab, ...(detail ? modal : {}) }, filename); } catch { setError("Не удалось выгрузить Excel."); } finally { setExporting(false); } };
  const cards = report?.cards || {};
  const previous = report?.previous || {};
  const percent = (value) => cards.total ? value * 100 / cards.total : null;
  const cardItems = full ? [
    { label: "Лиды", value: cards.leads }, { label: "Связанные сделки", value: cards.deals },
    ...[["lead_to_deal", "Лид → сделка", "Лиды хотя бы с одной связанной сделкой / исходные лиды × 100%. Лид считается один раз."], ["deal_to_success", "Сделка → успех", "Успешные связанные сделки / все связанные сделки × 100%."], ["lead_to_success", "Лид → успешная сделка", "Успешные связанные сделки / исходные лиды × 100%. При нескольких сделках на лид показатель может превышать 100%."]].map(([key, label, help]) => ({ label, help, value: cards[key], suffix: "%", digits: 1, delta: cards[key] == null || previous[key] == null ? null : cards[key] - previous[key] })),
    { label: "Средний полный цикл", value: cards.full_cycle_days, suffix: " дн.", digits: 1, help: "Среднее время от создания лида до успешного завершения каждой связанной сделки по истории стадий.", delta: cards.full_cycle_days == null || previous.full_cycle_days == null ? null : cards.full_cycle_days - previous.full_cycle_days },
  ] : [{ label: "Итого", value: cards.total }, { label: "Успешные", value: cards.success, share: percent(cards.success), shareHelp: "Доля = Успешные сделки / Общее количество сделок × 100%." }, { label: "Проигранные", value: cards.lost, share: percent(cards.lost), shareHelp: "Доля = Проигранные сделки / Общее количество сделок × 100%." }, { label: "Конверсия", value: cards.conversion, suffix: "%", digits: 1, help: "Успешные / (Успешные + Проигранные) × 100%.", action: () => setConversion(true) }, { label: "В работе", value: cards.in_progress, share: percent(cards.in_progress), shareHelp: "Доля = Сделки в работе / Общее количество сделок × 100%." }, { label: "Сумма сделок", value: cards.amount, suffix: " ₽" }, { label: "Успешные сделки", value: cards.success_amount, suffix: " ₽" }, { label: "Повторные", value: cards.return_customers, share: percent(cards.return_customers), help: "Доля повторных сделок рассчитывается от общего количества сделок" }];
  const selectedDepartments = filters.department_names.length ? filters.department_names : filters.exclude_untracked_department ? options.departments.map((d) => d.department_name).filter((d) => d !== UNTRACKED) : [];
  const kinds = tab === "funnel" ? [["results", "Динамика по статусам"], ["sources", "Динамика по источникам"]] : [["managers", "Динамика по менеджерам"], ["loss-reasons", "Динамика проигранных сделок"]];
  if (!active) return null;
  if (loading) return <GlobalSpinner />;
  return <main className="crm-dashboard crm-deal-section"><section className="crm-filters"><div className="crm-filter-actions"><button className="crm-action" disabled={exporting || loading} onClick={() => exportRows()}>Экспорт</button><button className="crm-action" onClick={() => change(defaults(full))}>Очистить</button></div><div className="crm-filter-grid">
    <MultiSelect label="Подразделение" options={options.departments} selected={selectedDepartments} valueKey="department_name" labelKey="department_name" onChange={(value) => change({ department_names: value, manager_ids: [], exclude_untracked_department: !value.includes(UNTRACKED) })} />
    <MultiSelect label="Менеджер" options={options.managers} selected={filters.manager_ids} valueKey="manager_id" labelKey="manager_name" onChange={(value) => change({ manager_ids: value })} />
    <MultiSelect label="Источник" options={options.sources} selected={filters.source_ids} valueKey="source_id" labelKey="source_name" onChange={(value) => change({ source_ids: value })} />
    <MultiSelect label="Воронка" options={options.categories} selected={filters.category_ids} valueKey="category_id" labelKey="name" onChange={(value) => change({ category_ids: value, stage_keys: [] })} />
    {!full && <><MultiSelect label="Статус" options={RESULTS} selected={filters.results} valueKey="id" labelKey="name" onChange={(value) => change({ results: value })} /><MultiSelect label="Стадия" options={options.stages.map((s) => ({ ...s, label: `${s.category_name} · ${s.name}` }))} selected={filters.stage_keys} valueKey="key" labelKey="label" onChange={(value) => change({ stage_keys: value })} /></>}
    <DateRangePicker start={filters.date_start} end={filters.date_end} onChange={({ start, end }) => change({ date_start: start, date_end: end })} />
    {!full && <div className="crm-filter crm-group-filter"><span>Группировка</span><div>{GROUPS.map(([key, label]) => <button key={key} className={filters.group_by === key ? "active" : ""} onClick={() => change({ group_by: key })}>{label}</button>)}</div></div>}
  </div></section>{full && <p className="crm-cohort-note"><FormulaHeader formulas={["Период определяется датой создания лида. Последующие события учитываются независимо от даты наступления.", "При выборе воронок остаются лиды с их сделками и лиды без сделок. Менеджер и подразделение относятся к лиду."]}>Когорта по дате создания лида</FormulaHeader></p>}
    {error && <div className="crm-toast-stack" aria-live="polite"><CrmToast message={error} onClose={() => setError("")} /></div>}{report && <><Cards items={cardItems} />{cards.missing_history > 0 && <p className="crm-cohort-note">Есть записи без истории стадий: {format(cards.missing_history)}. Неизвестные даты и длительности показаны прочерком.</p>}{full ? <><FullCycleFunnel report={report} onOpen={open} dateEnd={filters.date_end} />{report.standalone > 0 && <p className="crm-cohort-note"><button className="crm-text-link" onClick={() => open("standalone", "", null, "Сделки без лида")}>Сделки без лида: {format(report.standalone)}</button> (включая удалённые и ненайденные лиды) — отдельно по дате создания сделки, вне лидовой когорты.</p>}</> : <><nav className="crm-tabs"><button className={tab === "funnel" ? "active" : ""} onClick={() => setTab("funnel")}>Статусы и источники сделок</button><button className={tab === "managers" ? "active" : ""} onClick={() => setTab("managers")}>Менеджеры и эффективность сделок</button></nav>{cards.total ? <section className="crm-chart-grid">{kinds.map(([kind, title]) => <DynamicsChart key={kind} title={title} rows={report[kind]?.rows || []} groupBy={filters.group_by} segmentType={kind} dimensionOrder={kind === "stages" || kind === "results" ? (report[kind]?.summary || []).map((row) => row.key) : undefined} onOpen={open} summaryContent={<DealSummaryTable kind={kind} report={report[kind] || {}} categories={options.categories} comparisonPeriod={report[kind]?.comparison_period} onSelect={(key) => open(kind, key, null, title)} />} />)}</section> : <p className="crm-empty">По выбранным условиям сделки не найдены</p>}</> }</>}
    {(loading || exporting) && <GlobalSpinner />}{conversion && <ConversionModal open rows={report?.results?.rows || []} groupBy={filters.group_by} dateStart={filters.date_start} dateEnd={filters.date_end} onClose={() => setConversion(false)} />}<Details section={section} filters={filters} state={modal} data={details} busy={detailLoading} onClose={() => setModal(null)} onChange={setModal} onExport={() => exportRows(true)} />
  </main>;
}
