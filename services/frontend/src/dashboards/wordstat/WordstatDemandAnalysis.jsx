import { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { FloatingTooltip, Help, LoadingBlock, SelectField } from "./WordstatControls";
import { MONTHS, TONES, LEVELS, number, signed, percent, growth, dateLabel, monthLabel, seriesColor, objectNoun, sortedChanges, defaultSeasonIds, statusDistribution } from "./wordstatDemandUtils";
import "./wordstat_demand.css";

const DEFAULTS = { level: "feature", feature: "", category: "", phrase: "", period_months: 12, end_month: "", scope_ids: [], element_ids: [], comparison: "year_over_year" };
const STATUS = { growth: "\u0414\u043e\u043b\u044f \u0440\u0430\u0441\u0442\u0443\u0449\u0438\u0445", decline: "\u0414\u043e\u043b\u044f \u043f\u0430\u0434\u0430\u044e\u0449\u0438\u0445", stable: "\u0414\u043e\u043b\u044f \u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u044b\u0445" };
function Segments({ label, options, value, onChange, className = "" }) {
  return <div className={`wd-adaptive-control ${className}`}><div className="wd-control wd-expanded-control"><span className="wd-control-label">{label}</span><div className="wd-segments"><nav aria-label={label}>{options.map(([key, name]) => <button type="button" key={key} aria-pressed={key === value} className={key === value ? "is-active" : ""} onClick={() => onChange(key)}>{name}</button>)}</nav></div></div><SelectField className="wd-compact-control" label={label} value={value} onChange={onChange} options={options.map(([key, name]) => ({ value: key, label: name }))} /></div>;
}
function Empty({ children = "Нет данных для выбранного периода." }) { return <div className="wd-empty" role="status">{children}</div>; }

function ChartTooltip({ active, payload, label, coordinate, chartRef, period, seasonal = false }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  const anchor = () => { const box = chartRef.current?.getBoundingClientRect(); return box ? { left: box.left + (coordinate?.x || 0), top: box.top + (coordinate?.y || 0) } : null; };
  return <FloatingTooltip getAnchor={anchor}><strong className="wd-tooltip-title">{seasonal ? label : item.name}</strong>{seasonal ? payload.map((p) => <p className="wd-tooltip-row" key={p.dataKey}><i style={{ background: p.color }} /><span>{p.name}</span><b>{number(p.value, 2)}</b></p>) : <>
    <p>{dateLabel(period.current_start)} — {dateLabel(period.current_end)}: <b>{number(item.current_volume)}</b></p><p>{dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}: <b>{number(item.previous_volume)}</b></p><p>Изменение: <b>{signed(item.absolute_change, 0)}</b> · {growth(item)}</p></>}</FloatingTooltip>;
}

function Seasonality({ report, chosen, setChosen }) {
  const chartRef = useRef(null);
  const names = useMemo(() => {
    const profiles = (report.seasonality || []).filter((p) => { const item = report.items.find((i) => i.id === p.id); return Boolean(item); });
    return profiles.map((p, index) => ({ ...p, color: seriesColor(index), label: `${p.name}${profiles.filter((s) => s.name === p.name).length > 1 ? ` (${p.id.split("\u001f")[0]})` : ""}` }));
  }, [report]);
  const eligible = report.items.filter((p) => names.some((n) => n.id === p.id));
  const selectedYear = report.period?.end_month?.slice(0, 4);
  const publishedMonths = (report.available_months || []).filter((m) => m.startsWith(selectedYear));
  const lastMonth = publishedMonths.length ? Math.max(...publishedMonths.map((m) => Number(m.slice(5)))) : 0;
  const defaults = defaultSeasonIds(eligible.filter((item) => names.some((profile) => profile.id === item.id && profile.coefficients.slice(0, lastMonth).some((value) => value > 0))));
  const selected = names.filter((p) => (chosen === null ? defaults : defaultSeasonIds(eligible.filter((p) => chosen.includes(p.id)))).includes(p.id));
  const chart = MONTHS.slice(0, lastMonth).map((month, i) => Object.assign({ month }, ...selected.map((p, index) => ({ [`s${index}`]: p.coefficients[i] }))));
  const notes = selected.map((p) => ({ ...p, coefficients: p.coefficients.slice(0, lastMonth), values: p.coefficients.slice(0, lastMonth).filter((v) => v != null) })).sort((a, b) => Math.max(-Infinity, ...b.values) - Math.max(-Infinity, ...a.values));
  return <article className="wd-panel wd-visual wd-season"><header><h3>Сезонность <Help>Частотность месяца ÷ средняя месячная частотность года по загруженным месяцам. Для группы — среднее коэффициентов её запросов.</Help></h3><DashboardMultiSelect label="Показать" options={names.map((p) => p.label)} selected={selected.map((p) => p.label)} onApply={(labels) => setChosen(defaultSeasonIds(eligible.filter((p) => names.some((n) => n.id === p.id && labels.includes(n.label)))))} /></header>
    {selected.some((p) => p.years.length) ? <div ref={chartRef} className="wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 300 }}><LineChart data={chart} margin={{ top: 15, right: 34, left: 8, bottom: 5 }}>
      <CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="month" tick={{ fontSize: 12 }} tickMargin={8} height={36} minTickGap={12} padding={{ left: 24, right: 24 }} interval="preserveStartEnd" /><YAxis tick={{ fontSize: 12 }} tickMargin={8} tickFormatter={(v) => number(v, 2)} width="auto" domain={["auto", "auto"]} /><ReferenceLine y={1} stroke="#89939c" strokeDasharray="5 4" />
      <Tooltip content={(props) => <ChartTooltip {...props} chartRef={chartRef} seasonal />} />{selected.map((p, i) => <Line key={p.id} name={p.name} dataKey={`s${i}`} stroke={p.color} strokeWidth={2.5} dot={{ r: 2.5 }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />)}
    </LineChart></ResponsiveContainer></div> : <Empty>Недостаточно исторических данных для выбранных элементов.</Empty>}
    <div className="wd-season-notes" tabIndex={0} aria-label="Максимумы и минимумы сезонного профиля">{notes.map((p) => <div key={p.id}><span className="wd-season-name"><i style={{ background: p.color }} /><strong>{p.name}</strong></span>{p.values.length ? <><span><b>Максимум:</b> {MONTHS[p.coefficients.indexOf(Math.max(...p.values))]} ({number(Math.max(...p.values), 2)})</span><span><b>Минимум:</b> {MONTHS[p.coefficients.indexOf(Math.min(...p.values))]} ({number(Math.min(...p.values), 2)})</span></> : <span>Нет данных за год</span>}</div>)}</div>
  </article>;
}

function GrowthVolume({ report, onSelect, selectedPhrase }) {
  const chartRef = useRef(null);
  const points = report.items.filter((p) => p.growth_percent != null && p.current_volume != null);
  const positive = points.filter((p) => p.growth_percent > 0).sort((a, b) => b.growth_percent - a.growth_percent)[0];
  const negative = points.filter((p) => p.growth_percent < 0).sort((a, b) => a.growth_percent - b.growth_percent)[0];
  const minY = Math.min(0, ...points.map((p) => p.growth_percent));
  const maxY = Math.max(0, ...points.map((p) => p.growth_percent));
  const yGap = Math.max(1, (maxY - minY) * .18);
  const dot = ({ cx, cy, width, payload }) => {
    const radius = Math.max(4, (width || 12) / 2);
    const color = payload.absolute_change > 0 ? TONES.growth : payload.absolute_change < 0 ? TONES.decline : TONES.stable;
    const label = payload.id === positive?.id || payload.id === negative?.id ? `${signed(payload.growth_percent)}%` : null;
    return <g><circle cx={cx} cy={cy} r={radius} fill={color} fillOpacity={.75} stroke={selectedPhrase && selectedPhrase === payload.phrase ? "#242722" : color} />
      {label && <text x={cx} y={cy + (payload.growth_percent > 0 ? -radius - 10 : radius + 17)} textAnchor="middle" className="wd-extreme-label">{label}</text>}</g>;
  };
  return <article className="wd-panel wd-visual wd-growth"><header><h3>Рост × объём <Help>Объём и изменение по выбранным месяцам.</Help></h3><span className="wd-chart-caption">Нажмите на точку для детализации</span></header>
    <div className="wd-axis-caption"><span className="wd-axis-label wd-axis-label--growth">↑ Рост</span><span className="wd-axis-label wd-axis-label--decline">↓ Падение</span></div>
    {points.length ? <div ref={chartRef} className="wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 300 }}><ScatterChart margin={{ top: 18, right: 30, bottom: 12, left: 0 }}>
      <CartesianGrid strokeDasharray="3 4" />
      <XAxis type="number" dataKey="current_volume" name="Количество запросов" domain={[0, (maximum) => Math.max(1, maximum * 1.15)]} padding={{ left: 24, right: 28 }} tick={{ fontSize: 12 }} tickMargin={8} height={36} minTickGap={12} interval="preserveStartEnd" tickFormatter={(v) => Intl.NumberFormat("ru-RU", { notation: "compact" }).format(v)} />
      <YAxis type="number" dataKey="growth_percent" name="Изменение" domain={[minY - yGap, maxY + yGap]} padding={{ top: 24, bottom: 24 }} tick={{ fontSize: 12 }} tickMargin={8} tickFormatter={(v) => `${signed(v)}%`} width="auto" />
      <ZAxis type="number" dataKey="current_volume" range={[70, 650]} /><ReferenceLine y={0} stroke="#89939c" />
      <Tooltip content={(props) => <ChartTooltip {...props} chartRef={chartRef} period={report.period} />} />
      <Scatter data={points} shape={dot} onClick={(point) => onSelect(point.payload || point)} isAnimationActive={false} />
    </ScatterChart></ResponsiveContainer></div> : <Empty>Недостаточно данных для сравнения выбранных периодов.</Empty>}
    <div className="wd-axis-caption wd-axis-caption--x"><span className="wd-axis-label">→ Количество запросов, шт.</span></div>
  </article>;
}

function Ranking({ direction, report, onSelect, selectedPhrase }) {
  const [sort, setSort] = useState({ key: "growth_percent", direction: direction === "growth" ? "desc" : "asc" });
  const rows = sortedChanges(report.items, direction, sort);
  const maximum = Math.max(1, ...rows.map((p) => Math.abs(p.growth_percent || 0)));
  const header = (key, label) => <th aria-sort={sort.key === key ? sort.direction === "asc" ? "ascending" : "descending" : "none"}><button className={`wd-sort ${sort.key === key ? "is-active" : ""}`} type="button" onClick={() => setSort({ key, direction: sort.key === key && sort.direction === "desc" ? "asc" : "desc" })}>{label}<i>{sort.key === key ? sort.direction === "asc" ? "↑" : "↓" : "↕"}</i></button></th>;
  return <article className="wd-panel wd-ranking-panel"><header><h3 style={{ color: TONES[direction] }}>{direction === "growth" ? "Растущие" : "Падающие"}</h3></header><div className="wd-table-wrap wd-scroll"><table className="wd-ranking"><thead><tr><th>Название</th>{header("current_volume", "Количество запросов")}{header("previous_volume", report.period.comparison === "year_over_year" ? "\u041f\u0440\u043e\u0448\u043b\u044b\u0439 \u0433\u043e\u0434" : "\u041f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0438\u0439 \u043f\u0435\u0440\u0438\u043e\u0434")}{header("absolute_change", "Изменение, шт.")}{header("growth_percent", "Изменение, %")}</tr></thead><tbody>{rows.map((p) => <tr key={p.id} className={selectedPhrase && p.phrase === selectedPhrase ? "wd-selected" : ""}><td><button className="wd-link" type="button" onClick={() => onSelect(p)}>{p.name}</button></td><td>{number(p.current_volume)}</td><td>{number(p.previous_volume)}</td><td>{signed(p.absolute_change, 0)}</td><td style={{ color: TONES[direction] }}><div className="wd-data-bar"><i style={{ background: TONES[direction], width: `${Math.abs(p.growth_percent || 0) * 100 / maximum}%` }} /><b>{p.growth_percent == null ? growth(p) : `${signed(p.growth_percent, 0)}%`}</b></div></td></tr>)}</tbody></table>{!rows.length && <Empty>Нет {direction === "growth" ? "растущих" : "падающих"} элементов.</Empty>}</div></article>;
}

function SliceCard({ title, data, type }) {
  const [expanded, setExpanded] = useState(false);
  const items = data.items || [];
  const itemColors = new Map(items.map((item, index) => [item.id, seriesColor(index)]));
  const visibleItems = type === "regions"
    ? (expanded ? [...items].sort((a, b) => (b.share ?? 0) - (a.share ?? 0)) : data.top || [])
    : items;
  const barTotal = Math.max(100, items.reduce((sum, item) => sum + (item.share || 0), 0));
  return <article className="wd-panel wd-slice"><header><h3>{title} </h3>{type === "regions" && items.length > 0 && <button type="button" className="wd-link wd-navigation" onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть" : "Все регионы"}</button>}</header><div className="wd-scroll">{!data.complete ? <>
    <Empty>{{ missing_total: "Общий спрос за выбранный период загружен не полностью: доли пока не рассчитываются.", zero_total: "Общий спрос за выбранный период равен нулю: доли не определены.", missing_slices: "Помесячные данные разреза загружены не полностью." }[data.reason] || "Нет помесячных данных для этого разреза."}</Empty>
    {items.filter((p) => p.missing_months?.length).map((p) => <p className="wd-muted" key={p.id}>{p.name}: нет полного набора запросов за {p.missing_months.slice(0, 3).map(monthLabel).join(", ")}{p.missing_months.length > 3 ? ` и ещё ${p.missing_months.length - 3} мес.` : ""}.</p>)}
  </> : <><div className="wd-stacked">{items.map((p, i) => <i key={p.id} title={`${p.name}: ${percent(p.share)}`} style={{ width: `${p.share * 100 / barTotal}%`, background: seriesColor(i) }} />)}{data.other_share > 0 && <i title="Прочее" style={{ width: `${data.other_share * 100 / barTotal}%`, background: "#aaa" }} />}</div>{visibleItems.map((p) => <div className="wd-slice-row" key={p.id}><span className="wd-slice-name"><i className="wd-slice-dot" aria-hidden="true" style={{ background: itemColors.get(p.id) }} /><span>{p.name}</span></span><b>{percent(p.share)}</b><small style={{ color: p.change_pp > 0 ? TONES.growth : p.change_pp < 0 ? TONES.decline : undefined }}>{signed(p.change_pp)}</small></div>)}</>}</div></article>;
}

export function WordstatDemandAnalysis({ publicToken = null, revision, active = true }) {
  const [filters, setFilters] = useState(DEFAULTS);
  const [state, setState] = useState({ report: null, loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  const [chosen, setChosen] = useState(null);
  const [statusSelection, setStatusSelection] = useState(null);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
    setState((old) => ({ ...old, loading: true, error: "" }));
    const url = publicToken ? `/v1/dashboards/public-group/${publicToken}/wordstat/demand-analysis/` : "/v1/dashboards/wordstat/demand-analysis/";
    api.post(url, Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")), { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { setState({ report: data, loading: false, error: "" }); } })
      .catch((error) => { if (!controller.signal.aborted) setState((old) => ({ ...old, loading: false, error: typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Не удалось загрузить анализ спроса. Повторите попытку." })); });
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [filters, attempt, publicToken, revision, active]);
  const report = state.report, period = report?.period;
  const distribution = statusDistribution(report?.items);
  const update = (next) => { setStatusSelection(null); setChosen(null); setFilters((old) => ({ ...old, ...next })); };
  const selectMany = (ids) => {
    const items = (report?.element_options || []).filter((p) => ids.includes(p.id));
    if (!ids.length) { update({ element_ids: [], phrase: "" }); return; }
    if (filters.level === "feature") update({ scope_ids: ids, element_ids: [], feature: items.length === 1 ? items[0].feature : "", category: "", phrase: "", level: "category" });
    else if (filters.level === "category") update({ scope_ids: ids, element_ids: [], feature: new Set(items.map((p) => p.feature)).size === 1 ? items[0].feature : "", category: items.length === 1 ? items[0].category : "", phrase: "", level: "phrase" });
    else update({ element_ids: ids, phrase: "" });
  };
  const select = (item) => { if (item) selectMany([item.id]); };
  const selectStatus = (status) => {
    const ids = (report.items || []).filter((p) => p.status === status).map((p) => p.id);
    if (!ids.length) return;
    const previous = statusSelection;
    const selected = previous?.status === status;
    setStatusSelection(selected ? null : { status, element_ids: filters.element_ids, phrase: filters.phrase });
    setChosen(null);
    setFilters((old) => ({ ...old, element_ids: selected ? previous.element_ids : ids,
      phrase: selected ? previous.phrase : "" }));
  };
  const elementOptions = (report?.element_options || []);
  const optionLabels = elementOptions.map((p) => ({ ...p, label: elementOptions.some((o) => o.id !== p.id && o.name === p.name) ? `${p.name} (${p.feature})` : p.name }));
  const dateHelp = period ? <><p>Выбранный период: <b>{dateLabel(period.current_start)} — {dateLabel(period.current_end)}</b></p><p>{period.comparison === "previous_period" ? "Предыдущий период" : "Год к году"}: <b>{dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}</b></p></> : "Выберите завершённый месяц.";
  if (!active) return null;
  return <div className="wd-demand" aria-busy={state.loading}>{state.loading && <LoadingBlock />}<section className="wd-filter-panel"><div className="wd-filters">
    <Segments label="Период тренда" className="wd-period-control" options={[1, 3, 6, 12].map((m) => [m, `${m} мес.`])} value={filters.period_months} onChange={(v) => update({ period_months: v })} />
    <SelectField label="По месяц включительно" className="wd-month-control" help={<Help label="Периоды сравнения">{dateHelp}</Help>} value={filters.end_month || period?.end_month || ""} onChange={(v) => update({ end_month: v })} options={(report?.available_months || []).slice().reverse().map((m) => ({ value: m, label: monthLabel(m) }))} />
    <Segments label="Сравнение" className="wd-comparison-control" value={filters.comparison} options={[["year_over_year", "Год к году"], ["previous_period", "Предыдущий период"]]} onChange={(v) => update({ comparison: v })} />
    <Segments label="Уровень детализации" className="wd-level-control" options={LEVELS} value={filters.level} onChange={(v) => update({ level: v, phrase: "", element_ids: [], scope_ids: [], ...(v === "feature" ? { feature: "", category: "" } : v === "category" ? { category: "" } : {}) })} />
    <div className="wd-element-control wd-control"><DashboardMultiSelect label="Перейти к элементу" options={optionLabels.map((p) => p.label)} selected={optionLabels.filter((p) => filters.element_ids.includes(p.id)).map((p) => p.label)} onApply={(labels) => selectMany(optionLabels.filter((p) => labels.includes(p.label)).map((p) => p.id))} /></div>
    <div className="wd-toolbar"><button type="button" onClick={() => update(DEFAULTS)}>Очистить</button></div>
  </div><nav className="wd-breadcrumbs wd-navigation" aria-label="Иерархия спроса"><button type="button" onClick={() => update({ feature: "", category: "", phrase: "", level: "feature", scope_ids: [], element_ids: [] })}>Все категории</button>{filters.feature && <><span>›</span><button type="button" onClick={() => update({ category: "", phrase: "", level: "category", scope_ids: [], element_ids: [] })}>{filters.feature}</button></>}{filters.category && <><span>›</span><button type="button" onClick={() => update({ phrase: "", element_ids: [] })}>{filters.category}</button></>}{filters.phrase && <><span>›</span><button type="button" onClick={() => update({ phrase: "", element_ids: [] })}>{filters.phrase} ×</button></>}</nav></section>
    {state.error && <div className="wd-error" role="alert">{state.error} <button className="wd-link" onClick={() => setAttempt((v) => v + 1)}>Повторить</button></div>}
    {!state.loading && !state.error && !period && <Empty>Нет опубликованных данных для выбранных категорий.</Empty>}
    {!state.error && period && <><div className="wd-overview"><div className="wd-kpis">
      <article className="wd-card wd-traffic-card"><span className="wd-traffic-card-label">Количество запросов </span><strong>{number(report.summary.current_volume)}</strong><em className={report.summary.absolute_change > 0 ? "is-positive" : report.summary.absolute_change < 0 ? "is-negative" : ""}>{growth(report.summary)} {period.comparison === "year_over_year" ? "\u043a \u043f\u0440\u043e\u0448\u043b\u043e\u043c\u0443 \u0433\u043e\u0434\u0443" : "\u043a \u043f\u0440\u043e\u0448\u043b\u043e\u043c\u0443 \u043f\u0435\u0440\u0438\u043e\u0434\u0443"}</em></article>
      {["growth", "decline", "stable"].map((s) => <article className="wd-card wd-traffic-card" key={s}><span className="wd-traffic-card-label">{STATUS[s]}{s === "stable" && <> (изменение ±{number(report.neutral_percent)}%) <Help>Стабильные элементы: изменение в пределах ±{number(report.neutral_percent)}% включительно.</Help></>}</span><strong style={{ color: TONES[s] }}>{percent(distribution[s]?.share)}</strong><em><button type="button" className="wd-link wd-count-link" aria-pressed={statusSelection?.status === s} disabled={!distribution[s]?.count} onClick={() => selectStatus(s)}>{number(distribution[s]?.count)} {objectNoun(distribution[s]?.count, filters.level)}</button> · по объёму: {percent(distribution[s]?.volume_share)}</em></article>)}
    </div><div className="wd-slices"><SliceCard title="Регионы" data={report.regions} type="regions" /><SliceCard title="Устройства" data={report.devices} type="devices" /></div></div><div className="wd-report-grid"><Seasonality report={report} chosen={chosen} setChosen={setChosen} /><GrowthVolume report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="growth" report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="decline" report={report} onSelect={select} selectedPhrase={filters.phrase} /></div></>}
  </div>;
}
