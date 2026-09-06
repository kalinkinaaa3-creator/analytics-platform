import { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { FloatingTooltip, Help, LoadingBlock, SelectField } from "./WordstatControls";
import { MONTHS, TONES, LEVELS, number, signed, percent, growth, dateLabel, monthLabel, seriesColor, objectNoun, sortedChanges, isParentSummary, defaultSeasonIds } from "./wordstatDemandUtils";
import "./wordstat_demand.css";

const DEFAULTS = { level: "feature", feature: "", category: "", phrase: "", period_months: 12, end_month: "", comparison: "year_over_year" };
const STATUS = { growth: "Растут", decline: "Падают", stable: "Без изменений" };
function Segments({ label, options, value, onChange, className = "" }) {
  return <div className={`wd-adaptive-control ${className}`}><div className="wd-control wd-expanded-control"><span className="wd-control-label">{label}</span><div className="seo-menu wd-segments"><nav aria-label={label}>{options.map(([key, name]) => <button type="button" key={key} aria-pressed={key === value} className={key === value ? "is-active" : ""} onClick={() => onChange(key)}>{name}</button>)}</nav></div></div><SelectField className="wd-compact-control" label={label} value={value} onChange={onChange} options={options.map(([key, name]) => ({ value: key, label: name }))} /></div>;
}
function Empty({ children = "Нет данных для выбранного периода." }) { return <div className="wd-empty" role="status">{children}</div>; }

function ChartTooltip({ active, payload, label, coordinate, chartRef, period, seasonal = false }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  const anchor = () => { const box = chartRef.current?.getBoundingClientRect(); return box ? { left: box.left + (coordinate?.x || 0), top: box.top + (coordinate?.y || 0) } : null; };
  return <FloatingTooltip getAnchor={anchor}><strong className="wd-tooltip-title">{seasonal ? label : item.name}</strong>{seasonal ? payload.map((p) => <p className="wd-tooltip-row" key={p.dataKey}><i style={{ background: p.color }} /><span>{p.name}</span><b>{number(p.value, 2)}</b></p>) : <>
    <p>{dateLabel(period.current_start)} — {dateLabel(period.current_end)}: <b>{number(item.current_volume)}</b></p><p>{dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}: <b>{number(item.previous_volume)}</b></p><p>Изменение: <b>{signed(item.absolute_change, 0)}</b> · {growth(item)}</p></>}</FloatingTooltip>;
}

function Seasonality({ report, chosen, setChosen, selectedPhrase }) {
  const chartRef = useRef(null);
  const names = useMemo(() => {
    const profiles = (report.seasonality || []).filter((p) => { const item = report.items.find((i) => i.id === p.id); return item && !isParentSummary(item, report.context); });
    return profiles.map((p, index) => ({ ...p, color: seriesColor(index), label: `${p.name}${profiles.filter((s) => s.name === p.name).length > 1 ? ` (${p.id.split("\u001f")[0]})` : ""}` }));
  }, [report]);
  const defaults = defaultSeasonIds(report.items.filter((p) => names.some((n) => n.id === p.id)), selectedPhrase);
  const selected = names.filter((p) => (chosen === null ? defaults : chosen).includes(p.id));
  const chart = MONTHS.map((month, i) => Object.assign({ month }, ...selected.map((p, index) => ({ [`s${index}`]: p.coefficients[i] }))));
  const notes = selected.map((p) => ({ ...p, values: p.coefficients.filter((v) => v != null) })).sort((a, b) => Math.max(-Infinity, ...b.values) - Math.max(-Infinity, ...a.values));
  return <article className="seo-panel wd-visual wd-season"><header><h3>Сезонный профиль <Help>Месячная частотность делится на среднюю за полный год. Коэффициенты усредняются по завершённым годам. Текущий год исключён.</Help></h3><DashboardMultiSelect label="Показать" options={names.map((p) => p.label)} selected={selected.map((p) => p.label)} onApply={(labels) => setChosen(names.filter((p) => labels.includes(p.label)).map((p) => p.id))} /></header>
    {selected.some((p) => p.years.length) ? <div ref={chartRef} className="seo-chart wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 300 }}><LineChart data={chart} margin={{ top: 15, right: 16, left: 0, bottom: 5 }}>
      <CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="month" tick={{ fontSize: 10 }} minTickGap={10} /><YAxis tickFormatter={(v) => number(v, 2)} width={42} domain={["auto", "auto"]} /><ReferenceLine y={1} stroke="#89939c" strokeDasharray="5 4" />
      <Tooltip content={(props) => <ChartTooltip {...props} chartRef={chartRef} seasonal />} />{selected.map((p, i) => <Line key={p.id} name={p.name} dataKey={`s${i}`} stroke={p.color} strokeWidth={2.5} dot={{ r: 2.5 }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />)}
    </LineChart></ResponsiveContainer></div> : <Empty>Недостаточно исторических данных для выбранных элементов.</Empty>}
    <div className="wd-season-notes" tabIndex={0} aria-label="Максимумы и минимумы сезонного профиля">{notes.map((p) => <div key={p.id}><span className="wd-season-name"><i style={{ background: p.color }} /><strong>{p.name}</strong></span>{p.values.length ? <><span><b>Максимум:</b> {MONTHS[p.coefficients.indexOf(Math.max(...p.values))]} ({number(Math.max(...p.values), 2)})</span><span><b>Минимум:</b> {MONTHS[p.coefficients.indexOf(Math.min(...p.values))]} ({number(Math.min(...p.values), 2)})</span></> : <span>Нет полных лет</span>}</div>)}</div>
  </article>;
}

function GrowthVolume({ report, onSelect, selectedPhrase }) {
  const chartRef = useRef(null);
  const points = report.items.filter((p) => p.growth_percent != null && p.current_volume != null);
  return <article className="seo-panel wd-visual wd-growth"><header><h3>Рост × объём <Help>Объём и изменение по выбранным месяцам.</Help></h3><span className="wd-chart-caption">Каждая точка — объект выбранного уровня. Нажмите для детализации.</span></header>
    {points.length ? <div ref={chartRef} className="seo-chart wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 300 }}><ScatterChart margin={{ top: 18, right: 18, bottom: 34, left: 0 }}>
      <CartesianGrid strokeDasharray="3 4" /><XAxis type="number" dataKey="current_volume" name="Количество запросов" tickFormatter={(v) => Intl.NumberFormat("ru-RU", { notation: "compact" }).format(v)} label={{ value: "→ Количество запросов, шт.", position: "bottom", offset: 14, fontSize: 11 }} /><YAxis type="number" dataKey="growth_percent" name="Изменение" tick={{ fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? "↑ Рост " : v < 0 ? "↓ Падение " : ""}${number(Math.abs(v))}%`} width={105} /><ZAxis type="number" dataKey="current_volume" range={[35, 350]} /><ReferenceLine y={0} stroke="#89939c" />
      <Tooltip content={(props) => <ChartTooltip {...props} chartRef={chartRef} period={report.period} />} /><Scatter data={points} onClick={(point) => onSelect(point.payload || point)} isAnimationActive={false}>{points.map((p) => { const color = p.absolute_change > 0 ? TONES.growth : p.absolute_change < 0 ? TONES.decline : TONES.stable; return <Cell key={p.id} fill={color} fillOpacity={0.75} stroke={selectedPhrase && p.phrase === selectedPhrase ? "#242722" : color} strokeWidth={selectedPhrase && p.phrase === selectedPhrase ? 3 : 1} />; })}</Scatter>
    </ScatterChart></ResponsiveContainer></div> : <Empty>Недостаточно данных для сравнения выбранных периодов.</Empty>}
  </article>;
}

function Ranking({ direction, report, onSelect, selectedPhrase }) {
  const [sort, setSort] = useState({ key: "growth_percent", direction: direction === "growth" ? "desc" : "asc" });
  const rows = sortedChanges(report.items, direction, sort);
  const maximum = Math.max(1, ...rows.map((p) => Math.abs(p.growth_percent || 0)));
  const header = (key, label) => <th aria-sort={sort.key === key ? sort.direction === "asc" ? "ascending" : "descending" : "none"}><button className={`wd-sort ${sort.key === key ? "is-active" : ""}`} type="button" onClick={() => setSort({ key, direction: sort.key === key && sort.direction === "desc" ? "asc" : "desc" })}>{label}<i>{sort.key === key ? sort.direction === "asc" ? "↑" : "↓" : "↕"}</i></button></th>;
  return <article className="seo-panel wd-ranking-panel"><header><h3 style={{ color: TONES[direction] }}>{direction === "growth" ? "Растущие" : "Падающие"}</h3></header><div className="seo-table-wrap wd-scroll"><table className="seo-table wd-ranking"><thead><tr><th>Название</th>{header("current_volume", "Количество запросов")}{header("absolute_change", "Изменение, шт.")}{header("growth_percent", "Изменение, %")}</tr></thead><tbody>{rows.map((p) => <tr key={p.id} className={selectedPhrase && p.phrase === selectedPhrase ? "wd-selected" : ""}><td><button className="wd-link" type="button" onClick={() => onSelect(p)}>{p.name}</button></td><td>{number(p.current_volume)}</td><td>{signed(p.absolute_change, 0)}</td><td style={{ color: TONES[direction] }}><div className="wd-data-bar"><i style={{ background: TONES[direction], width: `${Math.abs(p.growth_percent || 0) * 100 / maximum}%` }} /><b>{growth(p)}</b></div></td></tr>)}</tbody></table>{!rows.length && <Empty>Нет {direction === "growth" ? "растущих" : "падающих"} элементов.</Empty>}</div></article>;
}

function SliceCard({ title, data, type }) {
  const [expanded, setExpanded] = useState(false);
  const items = data.items || [];
  return <article className="seo-panel wd-slice"><header><h3>{title} <Help>Структура спроса за выбранный период.</Help></h3>{type === "regions" && items.length > 0 && <button type="button" className="wd-link wd-navigation" onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть" : "Все регионы"}</button>}</header><div className="wd-scroll">{!data.complete || !data.consistent ? <>
    <Empty>{{ missing_total: "Общий спрос за выбранный период загружен не полностью: доли пока не рассчитываются.", zero_total: "Общий спрос за выбранный период равен нулю: доли не определены.", missing_slices: "Помесячные данные разреза загружены не полностью.", inconsistent: "Сумма разрезов превышает общий спрос. Требуется сверка исходных данных." }[data.reason] || "Нет помесячных данных для этого разреза."}</Empty>
    {items.filter((p) => p.missing_months?.length).map((p) => <p className="wd-muted" key={p.id}>{p.name}: нет полного набора запросов за {p.missing_months.slice(0, 3).map(monthLabel).join(", ")}{p.missing_months.length > 3 ? ` и ещё ${p.missing_months.length - 3} мес.` : ""}.</p>)}
  </> : <><div className="wd-stacked">{items.map((p, i) => <i key={p.id} title={`${p.name}: ${percent(p.share)}`} style={{ width: `${p.share}%`, background: seriesColor(i) }} />)}{data.other_share > 0 && <i title="Прочее" style={{ width: `${data.other_share}%`, background: "#aaa" }} />}</div>{(type === "regions" && !expanded ? data.top : items).map((p) => <div className="wd-slice-row" key={p.id}><span>{p.name}</span><b>{percent(p.share)}</b><small style={{ color: p.change_pp > 0 ? TONES.growth : p.change_pp < 0 ? TONES.decline : undefined }}>{signed(p.change_pp)}</small></div>)}</>}</div></article>;
}

export function WordstatDemandAnalysis({ publicToken = null, revision, active = true }) {
  const [filters, setFilters] = useState(DEFAULTS);
  const [state, setState] = useState({ report: null, loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  const [chosen, setChosen] = useState(null);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState((old) => ({ ...old, loading: true, error: "" })); // eslint-disable-line react-hooks/set-state-in-effect
    const url = publicToken ? `/v1/dashboards/public-group/${publicToken}/wordstat/demand-analysis/` : "/v1/dashboards/wordstat/demand-analysis/";
    api.get(url, { params: Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")), signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setState({ report: data, loading: false, error: "" }); })
      .catch((error) => { if (!controller.signal.aborted) setState((old) => ({ ...old, loading: false, error: typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Не удалось загрузить анализ спроса. Повторите попытку." })); });
    return () => controller.abort();
  }, [filters, attempt, publicToken, revision, active]);
  const report = state.report, period = report?.period;
  const update = (next) => { setChosen(null); setFilters((old) => ({ ...old, ...next })); };
  const select = (item) => {
    if (!item) return;
    if (filters.level === "feature") update({ feature: item.feature, category: "", phrase: "", level: "category" });
    else if (filters.level === "category") update({ feature: item.feature, category: item.category, phrase: "", level: "phrase" });
    else update({ phrase: item.phrase === filters.phrase ? "" : item.phrase });
  };
  const dateHelp = period ? <><p>Выбранный период: <b>{dateLabel(period.current_start)} — {dateLabel(period.current_end)}</b></p><p>{period.comparison === "previous_period" ? "Предыдущий период" : "Год к году"}: <b>{dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}</b></p></> : "Выберите завершённый месяц.";
  if (!active) return null;
  return <div className="wd-demand" aria-busy={state.loading}>{state.loading && <LoadingBlock />}<section className="seo-filters"><div className="wd-filters">
    <Segments label="Период тренда" className="wd-period-control" options={[1, 3, 6, 12].map((m) => [m, `${m} мес.`])} value={filters.period_months} onChange={(v) => update({ period_months: v })} />
    <SelectField label="По месяц включительно" className="wd-month-control" help={<Help label="Периоды сравнения">{dateHelp}</Help>} value={filters.end_month || period?.end_month || ""} onChange={(v) => update({ end_month: v })} options={(report?.available_months || []).slice().reverse().map((m) => ({ value: m, label: `${monthLabel(m)}${report.month_coverage?.[m] === "partial" ? " · неполные данные" : report.month_coverage?.[m] === "missing" ? " · нет данных" : ""}` }))} />
    <SelectField label="Сравнение" className="wd-comparison-control" value={filters.comparison} options={[{ value: "year_over_year", label: "Год к году" }, { value: "previous_period", label: "Предыдущий период" }]} onChange={(v) => update({ comparison: v })} />
    <Segments label="Уровень детализации" className="wd-level-control" options={LEVELS} value={filters.level} onChange={(v) => update({ level: v, phrase: "", ...(v === "feature" ? { feature: "", category: "" } : v === "category" ? { category: "" } : {}) })} />
    <SelectField label="Перейти к элементу" className="wd-element-control" value={report?.items?.find((p) => p.phrase && p.phrase === filters.phrase)?.id || ""} options={(report?.items || []).filter((p) => !isParentSummary(p, report.context)).map((item) => ({ value: item.id, label: `${item.name}${filters.level === "category" && !filters.feature ? ` · ${item.feature}` : ""}` }))} onChange={(v) => select(report.items.find((item) => item.id === v))} />
    <div className="seo-toolbar"><button type="button" onClick={() => { setChosen(null); setFilters(DEFAULTS); }}>Очистить</button></div>
  </div><nav className="wd-breadcrumbs wd-navigation" aria-label="Иерархия спроса"><button type="button" onClick={() => update({ feature: "", category: "", phrase: "", level: "feature" })}>Все категории</button>{filters.feature && <><span>›</span><button type="button" onClick={() => update({ category: "", phrase: "", level: "category" })}>{filters.feature}</button></>}{filters.category && <><span>›</span><button type="button" onClick={() => update({ phrase: "" })}>{filters.category}</button></>}{filters.phrase && <><span>›</span><button type="button" onClick={() => update({ phrase: "" })}>{filters.phrase} ×</button></>}</nav></section>
    {state.error && <div className="wd-error" role="alert">{state.error} <button className="wd-link" onClick={() => setAttempt((v) => v + 1)}>Повторить</button></div>}
    {!state.error && period && <><div className="wd-overview"><div className="wd-kpis">
      <article className="seo-card seo-traffic-card"><span className="seo-traffic-card-label">Количество запросов <Help>Сумма частотностей запросов за выбранный период.</Help></span><strong>{number(report.summary.current_volume)}</strong><em className={report.summary.absolute_change > 0 ? "is-positive" : report.summary.absolute_change < 0 ? "is-negative" : ""}>{growth(report.summary)} к прошлому периоду</em></article>
      {["growth", "decline", "stable"].map((s) => <article className="seo-card seo-traffic-card" key={s}><span className="seo-traffic-card-label">{STATUS[s]} <Help>Доля элементов выбранного уровня. Нейтральная зона карточек: ±{number(report.neutral_percent)}%. Нулевая база и пропуски учитываются отдельно.</Help></span><strong style={{ color: TONES[s] }}>{percent(report.summary.distribution?.[s]?.share)}</strong><em>{number(report.summary.distribution?.[s]?.count)} {objectNoun(report.summary.distribution?.[s]?.count, filters.level)} · по объёму: {percent(report.summary.distribution?.[s]?.volume_share)}</em></article>)}
    </div><div className="wd-slices"><SliceCard title="Регионы" data={report.regions} type="regions" /><SliceCard title="Устройства" data={report.devices} type="devices" /></div></div><div className="seo-report-grid"><Seasonality report={report} chosen={chosen} setChosen={setChosen} selectedPhrase={filters.phrase} /><GrowthVolume report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="growth" report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="decline" report={report} onSelect={select} selectedPhrase={filters.phrase} /></div></>}
  </div>;
}
