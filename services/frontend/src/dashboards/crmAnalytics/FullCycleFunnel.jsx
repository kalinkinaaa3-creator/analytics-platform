import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell } from "recharts";

import { ResponsiveContainer } from "./CrmAnalyticsDashboard";

const COLORS = ["#647a8b", "#8a704c", "#6f5f87", "#397f83", "#a85349"];
const number = (value, digits = 0) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const share = (a, b) => b ? a * 100 / b : null;
function entityNoun(count, unit) { const forms = unit === "leads" ? ["лид", "лида", "лидов"] : ["сделка", "сделки", "сделок"]; const n = Math.abs(count); return forms[n % 100 >= 11 && n % 100 <= 14 ? 2 : n % 10 === 1 ? 0 : n % 10 >= 2 && n % 10 <= 4 ? 1 : 2]; }
function AnimatedCount({ value }) {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    const start = performance.now(); let frame;
    const animate = (now) => { const progress = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : Math.min(1, (now - start) / 450); setShown(Math.round(value * progress)); if (progress < 1) frame = requestAnimationFrame(animate); };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return number(shown);
}

function FunnelStages({ stages, color = "#506f4e", onSelect, compact = false }) {
  const [hovered, setHovered] = useState(null);
  const maximum = Math.max(1, ...stages.map((s) => s.count));
  const width = (count) => Math.max(24, 330 * Math.sqrt(count / maximum));
  return <div className={`crm-funnel-stages${compact ? " is-compact" : ""}`}>
    <svg viewBox={`0 0 660 ${stages.length * 88}`} role="group" aria-label="Этапы воронки">
      {stages.map((stage, index) => { const next = stages[index + 1]; const previous = stages[index - 1]; const top = width(stage.count); const bottom = next ? width(next.count) : Math.max(18, top * .82); const y = index * 88; const lost = stage.loss_to_next ?? null; const path = `M ${330 - top / 2} ${y + 2} L ${330 + top / 2} ${y + 2} L ${330 + bottom / 2} ${y + 81} L ${330 - bottom / 2} ${y + 81} Z`;
        const activate = (event) => { const rect = event.currentTarget.getBoundingClientRect(); setHovered({ stage, previous, next, left: Math.min(rect.right + 8, window.innerWidth - 300), top: Math.min(Math.max(12, rect.top), window.innerHeight - 240) }); };
        return <g key={stage.key} role="button" tabIndex={0} aria-label={`${stage.name}: ${stage.count}`} className={`crm-funnel-stage${hovered && hovered.stage.key !== stage.key ? " is-muted" : ""}`} style={{ "--stage-delay": `${Math.min(index, 8) * 12}ms` }} onMouseEnter={activate} onMouseLeave={() => setHovered(null)} onFocus={activate} onBlur={() => setHovered(null)} onClick={() => onSelect(stage)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(stage); } }}>
          <path d={path} style={{ d: `path("${path}")` }} fill={stage.color || color} fillOpacity={Math.min(.6, .15 + index * .035)} stroke={stage.color || color} strokeOpacity=".4" />
          {stage.zone && <text x="330" y={y + 10} textAnchor="middle" className="crm-funnel-zone">{stage.zone}</text>}<text x="330" y={y + 23} textAnchor="middle" className="crm-funnel-stage-name">{stage.name.length > 40 ? `${stage.name.slice(0, 38)}…` : stage.name}</text>
          <text x="330" y={y + 48} textAnchor="middle" className="crm-funnel-count"><AnimatedCount value={stage.count} /></text>
          <text x="330" y={y + 68} textAnchor="middle">{number(stage.share, 1)}% от лидов</text>
          {!compact && previous && <text x="570" y={y + 39} textAnchor="middle" className="crm-funnel-side">{number((stage.unit === previous.unit ? stage.transition_share : share(stage.count, previous.count)), 1)}%<tspan x="570" dy="17">{stage.unit === previous.unit ? "от предыдущего" : "сделки / лиды"}</tspan></text>}
          {!compact && lost != null && stage.unit === next.unit && <text x="80" y={y + 39} textAnchor="middle" className="crm-funnel-side">{lost < 0 ? `+${number(-lost)}` : `−${number(lost)}`}<tspan x="80" dy="17">{lost < 0 ? "пропуски этапов" : "не дошли далее"}</tspan></text>}
        </g>;
      })}
    </svg>
    {hovered && createPortal(<aside role="tooltip" className="crm-funnel-tooltip" style={{ left: Math.max(10, hovered.left), top: hovered.top }}><strong>{hovered.stage.name}</strong><span>{number(hovered.stage.count)} {entityNoun(hovered.stage.count, hovered.stage.unit)}</span><span>{number(hovered.stage.share, 1)}% от исходных лидов</span>{hovered.previous && <span>{number((hovered.stage.unit === hovered.previous.unit ? hovered.stage.transition_share : share(hovered.stage.count, hovered.previous.count)), 1)}% от предыдущего этапа</span>}{hovered.next && hovered.stage.unit === hovered.next.unit && hovered.stage.loss_to_next != null && <span>Не дошли далее: {number(hovered.stage.loss_to_next)} · {number(share(hovered.stage.loss_to_next, hovered.stage.count), 1)}%</span>}<span>Среднее время: {number(hovered.stage.days, 1)} дн.</span><span>Сумма: {number(hovered.stage.amount)} ₽</span><small>По фактическим посещениям из истории. Пропущенные этапы не достраиваются.</small></aside>, document.body)}
  </div>;
}

export function FullCycleFunnel({ report, onOpen, dateEnd }) {
  const [selected, setSelected] = useState(null);
  const [changing, setChanging] = useState(false);
  const transitionTimer = useRef(null);
  useEffect(() => () => clearTimeout(transitionTimer.current), []);
  const choose = (category) => {
    clearTimeout(transitionTimer.current);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setSelected(category); return; }
    setChanging(true);
    transitionTimer.current = setTimeout(() => { setSelected(category); setChanging(false); }, 180);
  };
  const [now] = useState(() => Date.now());
  const branches = report.funnel?.branches || [];
  const expanded = branches.find((b) => b.category_id === selected) || (branches.length === 1 ? branches[0] : null);
  const combined = expanded ? [...(report.funnel?.lead_stages || []).map((stage) => ({ ...stage, part: "lead-stage" })), ...expanded.stages.map((stage, index) => ({ ...stage, key: `deal|${stage.key}`, sourceKey: stage.key, part: "deal-stage", zone: index === 0 ? expanded.name : null, color: COLORS[branches.indexOf(expanded) % COLORS.length] }))] : [];
  const cards = report.cards;
  const outcomes = [{ name: "Успешно", value: cards.success || 0, color: "#506f4e" }, { name: "Проиграно", value: cards.lost || 0, color: "#a85349" }, { name: "В работе", value: cards.in_progress || 0, color: "#647a8b" }];
  const immature = cards.full_cycle_days && (now - new Date(`${dateEnd}T23:59:59`).getTime()) / 86400000 < cards.full_cycle_days;
  if (!cards.leads) return <p className="crm-empty">Для выбранных условий не найдены связанные лиды и сделки.</p>;
  return <>
    {immature && <p className="crm-cohort-note">Данные за последние {Math.ceil(cards.full_cycle_days)} дней могут содержать незавершённые циклы. Оценка по среднему полному циклу ({cards.completed_cycles} завершений с известной датой).</p>}
    <article className={`crm-panel crm-full-cycle${changing ? " is-changing" : ""}`}><header className="crm-panel__heading"><h2>Лид → сделка → успешное закрытие</h2>{selected != null && branches.length > 1 && <button className="crm-action" onClick={() => choose(null)}>Все ветки</button>}</header><p className="crm-cohort-note">Лид считается один раз, связанные сделки — каждая отдельно. {number(cards.converted_leads)} лидов → {number(cards.deals)} сделок. Этапы отражают фактическую историю, поэтому при пропусках их количество может возрастать.</p>
      {expanded ? <section className="crm-funnel-expanded"><FunnelStages stages={combined} onSelect={(s) => onOpen(s.part, s.sourceKey || s.key, null, s.name, [], s.part === "deal-stage" ? expanded.category_id : null)} /></section> : <><div className="crm-funnel-leads"><h3>Лиды</h3><FunnelStages stages={report.funnel.lead_stages} onSelect={(s) => onOpen("lead-stage", s.key, null, s.name)} /></div><div className="crm-funnel-junction" aria-hidden="true" /><div className="crm-funnel-branches">{branches.map((branch, index) => <section key={branch.category_id} style={{ "--branch-color": COLORS[index % COLORS.length] }}><button className="crm-funnel-branch-title" onClick={() => choose(branch.category_id)}><strong>{branch.name}</strong><span>{number(branch.leads)} лидов → {number(branch.count)} сделок → {number(branch.success)} успешных</span><small>{number(branch.share, 1)}% сделок · раскрыть</small></button><FunnelStages stages={branch.stages} compact color={COLORS[index % COLORS.length]} onSelect={(s) => onOpen("deal-stage", s.key, null, `${branch.name} · ${s.name}`, [], branch.category_id)} /></section>)}</div></>}
    </article>
    <section className="crm-chart-grid"><article className="crm-panel crm-cohort-panel"><h2>Динамика сквозной воронки</h2><div className="crm-chart"><ResponsiveContainer width="100%" height={340}><LineChart data={report.dynamics?.rows || []} margin={{ top: 20, right: 24, left: 8, bottom: 12 }}><CartesianGrid strokeDasharray="3 4" /><XAxis dataKey="period" /><YAxis allowDecimals={false} /><Tooltip /><Legend />{[["leads", "Лиды", "#506f4e"], ["target", "Целевые", "#8a704c"], ["deals", "Созданные сделки", "#647a8b"], ["success", "Успешные сделки", "#397f83"]].map(([key, name, color]) => <Line key={key} dataKey={key} name={name} stroke={color} strokeWidth={2} />)}</LineChart></ResponsiveContainer></div></article>
      <article className="crm-panel crm-cohort-panel"><h2>Исход сделок</h2><ResponsiveContainer width="100%" height={340}><PieChart><Pie isAnimationActive={false} data={outcomes} dataKey="value" nameKey="name" innerRadius={75} outerRadius={115}>{outcomes.map((r) => <Cell key={r.name} fill={r.color} />)}</Pie><Tooltip /><Legend /></PieChart></ResponsiveContainer></article></section>
    <article className="crm-panel crm-cohort-panel"><h2>Менеджеры по сквозной конверсии</h2><div className="crm-summary-wrap"><table><thead><tr><th>Менеджер лида</th>{["Лиды", "Сделки", "Успешно", "Лид → сделка, %", "Лид → успех, %"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>{(report.managers?.rows || []).map((row) => <tr key={row.manager_id || "none"}><th>{row.name || "Менеджер не назначен"}</th>{["leads", "deals", "success", "lead_to_deal", "lead_to_success"].map((key) => <td key={key}>{number(row[key], key.startsWith("lead_to") ? 1 : 0)}</td>)}</tr>)}</tbody></table></div></article>
  </>;
}
