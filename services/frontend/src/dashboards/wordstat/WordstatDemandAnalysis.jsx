import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Cell, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import "./wordstat_demand.css";

const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const COLORS = ["#536f50", "#73869a", "#b98a3e", "#765f8e", "#3f8a88"];
const STATUS = { growth: "Растут", decline: "Падают", stable: "Без изменений", new: "Новые", missing: "Нет сравнения" };
const TONES = { growth: "#536f50", decline: "#aa584b", stable: "#89939c", new: "#b98a3e", missing: "#89939c" };
const LEVELS = [["feature", "Категории"], ["category", "Подкатегории"], ["phrase", "Запросы"]];
const DEFAULTS = { level: "feature", feature: "", category: "", phrase: "", period_months: 12, end_month: "" };
const number = (v, digits = 0) => v == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(v);
const signed = (v, digits = 1) => {
  if (v == null) return "—";
  const rounded = Math.round(v * 10 ** digits) / 10 ** digits || 0;
  return `${rounded > 0 ? "+" : ""}${number(rounded, digits)}`;
};
const percent = (v) => v == null ? "—" : `${number(v, 1)}%`;
const growth = (item) => item?.status === "new" ? "Новый" : item?.growth_percent == null ? "Нет сравнения" : `${signed(item.growth_percent)}%`;
const dateLabel = (v) => v ? v.split("-").reverse().join(".") : "—";
const monthLabel = (v) => v ? new Date(`${v}-01T12:00:00`).toLocaleDateString("ru-RU", { month: "long", year: "numeric" }) : "—";

function Help({ children }) {
  return <span className="wd-help" tabIndex={0} aria-label={children}>i<span role="tooltip">{children}</span></span>;
}

function Segments({ label, options, value, onChange }) {
  return <div className="wd-control"><span>{label}</span><div className="seo-menu wd-segments"><nav aria-label={label}>{options.map(([key, name]) =>
    <button type="button" key={key} aria-pressed={key === value} className={key === value ? "is-active" : ""} onClick={() => onChange(key)}>{name}</button>,
  )}</nav></div></div>;
}

function Empty({ children = "Нет данных для выбранного периода." }) {
  return <div className="wd-empty" role="status">{children}</div>;
}

function DemandTooltip({ active, payload, period }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return <div className="seo-tooltip wd-tooltip"><strong>{item.name}</strong>
    <p>{dateLabel(period.current_start)} — {dateLabel(period.current_end)}: <b>{number(item.current_volume)}</b></p>
    <p>{dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}: <b>{number(item.previous_volume)}</b></p>
    <p>Изменение: <b>{signed(item.absolute_change, 0)}</b> · {growth(item)}</p>
    <p>Запросов: {number(item.query_count)}</p>
    {item.query_count > 1 && <p>Растут: {percent(item.children?.growth?.share)} · Падают: {percent(item.children?.decline?.share)}</p>}
  </div>;
}

function Seasonality({ report, chosen, setChosen, selectedPhrase }) {
  const names = useMemo(() => {
    const profiles = report.seasonality || [];
    return profiles.map((p) => ({ ...p, label: `${p.name}${profiles.filter((s) => s.name === p.name).length > 1 ? ` (${p.id.split("\u001f")[0]})` : ""}` }));
  }, [report.seasonality]);
  const focused = selectedPhrase ? names.filter((p) => p.id.split("\u001f").at(-1) === selectedPhrase) : [];
  const defaults = report.items.slice(0, 3).map((item) => item.id);
  const ids = chosen.filter((id) => names.some((p) => p.id === id));
  const selected = focused.length ? focused : names.filter((p) => (ids.length ? ids : defaults).includes(p.id)).slice(0, 5);
  const chart = MONTHS.map((month, i) => Object.assign({ month }, ...selected.map((p, index) => ({ [`s${index}`]: p.coefficients[i] }))));
  const valid = selected.some((p) => p.years.length);
  return <article className="seo-panel wd-season"><header><h3>Сезонный профиль <Help>Месячная частотность делится на среднюю за полный год. Затем коэффициенты усредняются по завершённым годам. Текущий год исключён; период тренда на профиль не влияет.</Help></h3>
    <DashboardMultiSelect label="Показать · до 5 элементов" options={names.map((p) => p.label)} selected={selected.map((p) => p.label)} onApply={(labels) => setChosen(names.filter((p) => labels.includes(p.label)).slice(-5).map((p) => p.id))} /></header>
    {valid ? <><div className="seo-chart wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 310 }}><LineChart data={chart} margin={{ top: 16, right: 20, left: 0, bottom: 8 }}>
      <CartesianGrid strokeDasharray="3 4" vertical={false} /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(v) => number(v, 2)} width={42} domain={["auto", "auto"]} />
      <ReferenceLine y={1} stroke="#89939c" strokeDasharray="5 4" />
      <Tooltip content={({ active, payload, label }) => active && payload?.length ? <div className="seo-tooltip wd-tooltip"><strong>{label}</strong>{payload.map((p) => <p key={p.dataKey}><span style={{ color: p.color }}>{p.name}</span>: <b>{number(p.value, 2)}</b> ({signed((p.value - 1) * 100)}% к среднему)</p>)}</div> : null} /><Legend />
      {selected.map((p, i) => <Line key={p.id} name={p.name} dataKey={`s${i}`} stroke={COLORS[i]} strokeWidth={3.2} dot={{ r: 3.5 }} activeDot={{ r: 5.5 }} connectNulls={false} isAnimationActive={false} />)}
    </LineChart></ResponsiveContainer></div><div className="wd-season-notes">{selected.map((p, i) => {
      const values = p.coefficients.filter((v) => v != null);
      return <div key={p.id}><strong style={{ color: COLORS[i] }}>{p.name}</strong>{values.length ? <><span>Пик: {MONTHS[p.coefficients.indexOf(Math.max(...values))]} ({number(Math.max(...values), 2)}) · Минимум: {MONTHS[p.coefficients.indexOf(Math.min(...values))]} ({number(Math.min(...values), 2)})</span><small>Полные годы: {p.years.join(", ")}{p.years.length < 2 ? " · Недостаточно истории для устойчивой оценки" : ""}</small></> : <span>Недостаточно исторических данных.</span>}</div>;
    })}</div></> : <Empty>Недостаточно исторических данных для расчёта сезонного профиля.</Empty>}
  </article>;
}

function GrowthVolume({ report, onSelect, selectedPhrase }) {
  const comparable = report.items.filter((p) => p.growth_percent != null && p.current_volume != null);
  const points = comparable.slice(0, 500);
  const omitted = report.items.length - comparable.length;
  return <article className="seo-panel"><header><h3>Рост × объём <Help>Объём за выбранные месяцы и изменение к тем же месяцам прошлого года. Вертикальная граница — медиана объёма. Нулевая база не отображается как бесконечный рост.</Help></h3></header>
    <p className="wd-muted">Каждая точка — объект выбранного уровня. Нажмите для детализации.</p>
    {points.length ? <div className="seo-chart wd-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 310 }}><ScatterChart margin={{ top: 12, right: 24, bottom: 28, left: 5 }}>
      <CartesianGrid strokeDasharray="3 4" /><XAxis type="number" dataKey="current_volume" name="Объём" tickFormatter={(v) => Intl.NumberFormat("ru-RU", { notation: "compact" }).format(v)} label={{ value: `Объём спроса (${report.period.period_months} мес.)`, position: "bottom", offset: 10 }} />
      <YAxis type="number" dataKey="growth_percent" name="Изменение" tickFormatter={(v) => `${number(v)}%`} width={65} />
      <ZAxis type="number" dataKey="current_volume" range={[35, 350]} />
      <ReferenceArea y1={-report.neutral_percent} y2={report.neutral_percent} fill="#89939c" fillOpacity={0.12} />
      <ReferenceLine y={0} stroke="#89939c" />{report.median_volume != null && <ReferenceLine x={report.median_volume} stroke="#89939c" strokeDasharray="4 4" />}
      <Tooltip content={<DemandTooltip period={report.period} />} />
      <Scatter data={points} onClick={(point) => onSelect(point.payload || point)} isAnimationActive={false}>{points.map((p) => <Cell key={p.id} fill={TONES[p.status]} fillOpacity={0.75} stroke={selectedPhrase && p.phrase === selectedPhrase ? "#242722" : TONES[p.status]} strokeWidth={selectedPhrase && p.phrase === selectedPhrase ? 3 : 1} />)}</Scatter>
    </ScatterChart></ResponsiveContainer></div> : <Empty>Недостаточно данных для сравнения с прошлым годом.</Empty>}
    <div className="wd-legend">{["growth", "stable", "decline"].map((s) => <span key={s}><i style={{ background: TONES[s] }} />{STATUS[s]}</span>)}</div>
    <p className="wd-muted">Справа сверху — приоритет; слева сверху — потенциал; справа снизу — требует внимания.{comparable.length > 500 && ` Показаны 500 из ${comparable.length} объектов с наибольшим объёмом.`}{omitted > 0 && ` Без точки: ${omitted} (нулевая база или нет данных).`}</p>
  </article>;
}

function Ranking({ direction, report, onSelect, selectedPhrase }) {
  const [sort, setSort] = useState("percent");
  const [limit, setLimit] = useState(10);
  const rows = report.items.filter((p) => p.status === direction && (sort !== "percent" || p.previous_volume >= report.minimum_base))
    .sort((a, b) => direction === "growth" ? (sort === "percent" ? b.growth_percent - a.growth_percent : b.absolute_change - a.absolute_change) : (sort === "percent" ? a.growth_percent - b.growth_percent : a.absolute_change - b.absolute_change)).slice(0, limit);
  const maximum = Math.max(1, ...rows.map((p) => Math.abs(sort === "percent" ? p.growth_percent : p.absolute_change)));
  return <article className="seo-panel"><header><h3 style={{ color: TONES[direction] }}>Топ-{limit} {direction === "growth" ? "растущих" : "падающих"} <Help>Процентный рейтинг исключает объекты с базой ниже настроенного порога. Абсолютный рейтинг показывает вклад в изменение спроса.</Help></h3></header>
    <div className="wd-ranking-controls"><Segments label="Сортировка" options={[["percent", "По изменению, %"], ["absolute", "По изменению, абс."]]} value={sort} onChange={setSort} /><label>Показать <select aria-label={`Количество ${direction === "growth" ? "растущих" : "падающих"}`} className="dashboard-multiselect__control" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>{[5, 10, 20].map((v) => <option key={v}>{v}</option>)}</select></label></div>
    <div className="seo-table-wrap"><table className="seo-table wd-ranking"><thead><tr><th>#</th><th>Название</th><th>Объём<br />({report.period.period_months} мес.)</th><th>Изменение, абс.</th><th>Изменение, %</th></tr></thead><tbody>{rows.map((p, i) => <tr key={p.id} className={selectedPhrase && p.phrase === selectedPhrase ? "wd-selected" : ""}>
      <td>{i + 1}</td><td><button className="wd-link" type="button" onClick={() => onSelect(p)}>{p.name}</button></td><td>{number(p.current_volume)}</td><td>{signed(p.absolute_change, 0)}</td><td style={{ color: TONES[direction] }}><div className="wd-data-bar"><i style={{ background: TONES[direction], width: `${Math.abs(sort === "percent" ? p.growth_percent : p.absolute_change) * 100 / maximum}%` }} /><b>{growth(p)}</b></div></td>
    </tr>)}</tbody></table></div>{!rows.length && <Empty>Нет объектов, соответствующих условиям рейтинга.</Empty>}
    {sort === "percent" && <p className="wd-muted">Минимальная база: {number(report.minimum_base)}. Нейтральная зона: ±{number(report.neutral_percent)}%.</p>}
  </article>;
}

function SliceCard({ title, data, type }) {
  const [expanded, setExpanded] = useState(false);
  const items = data.items || [];
  const mobile = items.filter((p) => ["phone", "tablet"].includes(p.id));
  const mobileShare = mobile.length === 2 && mobile.every((p) => p.share != null) ? mobile.reduce((sum, p) => sum + p.share, 0) : null;
  const mobileChange = mobile.length === 2 && mobile.every((p) => p.change_pp != null) ? mobile.reduce((sum, p) => sum + p.change_pp, 0) : null;
  const mobileParent = mobile.length === 2 && mobile.every((p) => p.difference_vs_parent_pp != null) ? mobile.reduce((sum, p) => sum + p.difference_vs_parent_pp, 0) : null;
  return <article className="seo-panel wd-slice"><header><h3>{title} <Help>Структура спроса за выбранный период. Изменение доли показывается в процентных пунктах. Карточка описывает текущий контекст и не фильтрует графики.</Help></h3>{type === "regions" && items.length > 0 && <button className="wd-link" onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть" : "Все регионы"}</button>}</header>
    {!data.complete || !data.consistent ? <>
      <Empty>{{ missing_total: "Общий спрос за выбранный период загружен не полностью: доли пока не рассчитываются.", zero_total: "Общий спрос за выбранный период равен нулю: доли не определены.", missing_slices: "Помесячные данные разреза загружены не полностью.", inconsistent: "Сумма разрезов превышает общий спрос. Требуется сверка исходных данных." }[data.reason] || "Нет помесячных данных для этого разреза."}</Empty>
      {items.filter((p) => p.missing_months?.length).map((p) => <p className="wd-muted" key={p.id}>{p.name}: нет полного набора запросов за {p.missing_months.slice(0, 3).map(monthLabel).join(", ")}{p.missing_months.length > 3 ? ` и ещё ${p.missing_months.length - 3} мес.` : ""}.</p>)}
    </> : <>
      <p>{type === "devices" ? "Основное устройство" : "Лидер по спросу"}: <b>{data.leader?.name}</b> · {percent(data.leader?.share)}</p>
      {type === "devices" && <div className="wd-stacked">{items.map((p, i) => <i key={p.id} title={`${p.name}: ${percent(p.share)}`} style={{ width: `${p.share}%`, background: COLORS[i] }} />)}{data.other_share > 0 && <i title="Прочее" style={{ width: `${data.other_share}%`, background: "#aaa" }} />}</div>}
      {(type === "regions" && !expanded ? data.top : items).map((p) => <div className="wd-slice-row" key={p.id}><span>{p.name}</span><b>{percent(p.share)}</b><small>{signed(p.change_pp)} п.п.</small></div>)}
      {type === "regions" ? <><p>Топ-3: <b>{percent(data.top3_share)}</b> общего спроса</p>{data.fastest_growing && <p>Быстрее всего растёт: <b>{data.fastest_growing.name}</b> {growth(data.fastest_growing)}</p>}</> : <><p>Мобильные: <b>{percent(mobileShare)}</b> · {signed(mobileChange)} п.п. <small>(телефоны + планшеты)</small></p>{mobileParent != null && <p>Доля мобильных: {signed(mobileParent)} п.п. к родительскому уровню</p>}</>}
      {data.leader?.difference_vs_parent_pp != null && <p>{data.leader.name}: {signed(data.leader.difference_vs_parent_pp)} п.п. к родительскому уровню</p>}
      {data.other_share >= 0.05 && <small>Прочее: {percent(data.other_share)}</small>}
    </>}
  </article>;
}

export function WordstatDemandAnalysis({ publicToken = null, revision, active = true }) {
  const [filters, setFilters] = useState(DEFAULTS);
  const [state, setState] = useState({ report: null, loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  const [chosen, setChosen] = useState([]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    // Retain controls and panel dimensions while a new context is loading.
    setState((old) => ({ ...old, loading: true, error: "" })); // eslint-disable-line react-hooks/set-state-in-effect
    const url = publicToken ? `/v1/dashboards/public-group/${publicToken}/wordstat/demand-analysis/` : "/v1/dashboards/wordstat/demand-analysis/";
    api.get(url, { params: Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")), signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setState({ report: data, loading: false, error: "" }); })
      .catch((error) => { if (!controller.signal.aborted) setState((old) => ({ ...old, loading: false, error: typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Не удалось загрузить анализ спроса. Повторите попытку." })); });
    return () => controller.abort();
  }, [filters, attempt, publicToken, revision, active]);
  const report = state.report;
  const update = (next) => setFilters((old) => ({ ...old, ...next }));
  const select = (item) => {
    setChosen([]);
    if (filters.level === "feature") update({ feature: item.feature, category: "", phrase: "", level: "category" });
    else if (filters.level === "category") update({ feature: item.feature, category: item.category, phrase: "", level: "phrase" });
    else update({ phrase: item.phrase === filters.phrase ? "" : item.phrase });
  };
  const period = report?.period;
  if (!active) return null;
  return <div className="wd-demand">
    <section className="seo-filters"><div className="seo-toolbar"><button type="button" onClick={() => { setChosen([]); setFilters(DEFAULTS); }}>Очистить</button></div>
      <nav className="wd-breadcrumbs" aria-label="Иерархия спроса"><button onClick={() => update({ feature: "", category: "", phrase: "", level: "feature" })}>Все категории</button>{filters.feature && <><span>›</span><button onClick={() => update({ category: "", phrase: "", level: "category" })}>{filters.feature}</button></>}{filters.category && <><span>›</span><button onClick={() => update({ phrase: "", level: "phrase" })}>{filters.category}</button></>}{filters.phrase && <><span>›</span><button onClick={() => update({ phrase: "" })}>{filters.phrase} ×</button></>}</nav>
      <div className="wd-filters"><Segments label="Период тренда" options={[1, 3, 6, 12].map((m) => [m, `${m} мес.`])} value={filters.period_months} onChange={(v) => update({ period_months: v })} />
        <label className="wd-control">По месяц включительно<select className="dashboard-multiselect__control" aria-label="Конечный месяц" value={filters.end_month || report?.period?.end_month || ""} onChange={(e) => update({ end_month: e.target.value })}><option value="" disabled>Нет завершённых месяцев</option>{report?.available_months?.slice().reverse().map((m) => <option key={m} value={m}>{monthLabel(m)}{report.month_coverage?.[m] === "partial" ? " · неполные данные" : report.month_coverage?.[m] === "missing" ? " · нет данных" : ""}</option>)}</select></label>
        <Segments label="Уровень детализации" options={LEVELS} value={filters.level} onChange={(v) => { setChosen([]); update({ level: v, phrase: "", ...(v === "feature" ? { feature: "", category: "" } : v === "category" ? { category: "" } : {}) }); }} />
        <DashboardMultiSelect label="Категория" options={report?.options?.features || []} selected={filters.feature ? [filters.feature] : []} onApply={(values) => { setChosen([]); update({ feature: values.at(-1) || "", category: "", phrase: "", level: values.length ? "category" : "feature" }); }} />
      </div>
      {!!report?.items?.length && <label className="wd-control wd-drill-select">Перейти к элементу<select className="dashboard-multiselect__control" aria-label="Перейти к элементу" value="" disabled={state.loading} onChange={(e) => select(report.items.find((item) => item.id === e.target.value))}><option value="">Выберите категорию, подкатегорию или запрос</option>{report.items.map((item) => <option key={item.id} value={item.id}>{item.name}{filters.level === "category" && !filters.feature ? ` · ${item.feature}` : ""}</option>)}</select></label>}
      {period && <p className="wd-period">{dateLabel(period.current_start)} — {dateLabel(period.current_end)} <span>vs</span> {dateLabel(period.previous_start)} — {dateLabel(period.previous_end)}</p>}
      <p className="wd-muted">{report?.latest_month ? `Последний полностью загруженный месяц в выборке: ${monthLabel(report.latest_month)}. ` : "Нет полностью загруженных месяцев в выборке. "}Текущий незавершённый месяц исключён из расчётов.</p>
    </section>
    {state.error && <div className="wd-error" role="alert">{state.error} <button className="wd-link" onClick={() => setAttempt((v) => v + 1)}>Повторить</button></div>}
    <div aria-busy={state.loading}>{state.loading ? <div className="wd-skeleton" role="status" aria-label="Загрузка анализа спроса"><div /><div /><div /><div /></div> : !state.error && (period ? <>
      <div className="wd-overview"><div className="wd-kpis"><article className="seo-card"><span className="seo-card-label">Объектов в выборке</span><strong>{number(report.summary.count)}</strong><small>{LEVELS.find(([v]) => v === filters.level)?.[1]}</small></article>
        <article className="seo-card"><span className="seo-card-label">Объём спроса · {period.period_months} мес.</span><strong>{number(report.summary.current_volume)}</strong><small style={{ color: TONES[report.summary.status] }}>{growth(report.summary)}</small></article>
        {["growth", "decline", "stable"].map((s) => <article className="seo-card" key={s}><span className="seo-card-label">{STATUS[s]} <Help>Доля объектов текущего уровня. Объекты без данных и с нулевой базой учитываются отдельно.</Help></span><strong style={{ color: TONES[s] }}>{percent(report.summary.distribution?.[s]?.share)}</strong><small>{number(report.summary.distribution?.[s]?.count)} объектов · по объёму: {percent(report.summary.distribution?.[s]?.volume_share)}</small></article>)}
      </div><SliceCard title="Регионы IPLAST" data={report.regions} type="regions" /><SliceCard title="Устройства" data={report.devices} type="devices" /></div>
      {(report.summary.distribution?.new?.count > 0 || report.summary.distribution?.missing?.count > 0) && <p className="wd-muted">Нулевая база («Новый»): {number(report.summary.distribution.new.count)} · Недостаточно данных для сравнения: {number(report.summary.distribution.missing.count)}</p>}
      <div className="seo-report-grid"><Seasonality report={report} chosen={chosen} setChosen={(value) => { setChosen(value); if (filters.phrase) update({ phrase: "" }); }} selectedPhrase={filters.phrase} /><GrowthVolume report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="growth" report={report} onSelect={select} selectedPhrase={filters.phrase} /><Ranking direction="decline" report={report} onSelect={select} selectedPhrase={filters.phrase} /></div>
    </> : <Empty />)}</div>
  </div>;
}
