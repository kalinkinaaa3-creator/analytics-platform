import { fmtDate } from "./archiveFormat";
import { issues } from "./issueLabels";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button, Panel } from "./ui/primitives";
import Icon from "./ui/Icon";
import { priceText } from "./format";

export function SelectMarketOverview({ snapshot, activeSnapshot, sourceState, onNavigate, onHelp, onZone, onCompare }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [welcome, setWelcome] = useState(() => { try { return sessionStorage.getItem("select-market-iprice-welcome-hidden") !== "1"; } catch { return true; } });
  const activeId = activeSnapshot?.id;
  const snapshotId = snapshot?.id;
  const snapshotStatus = snapshot?.status;
  const [comparison, setComparison] = useState(null);
  const [comparisonError, setComparisonError] = useState("");
  useEffect(() => {
    if (!activeId || !snapshotId || activeId === snapshotId || snapshotStatus !== "success") return;
    const controller = new AbortController();
    api.get(`/v1/select-market/iprice/snapshots/${snapshotId}/analysis/`, { params: { comparison_id: activeId, mode: "products", change_type: "changed" }, signal: controller.signal })
      .then(r => { setComparison(r.data.summary); setComparisonError(""); }).catch(e => { if (e.code !== "ERR_CANCELED") setComparisonError("Не удалось получить сводку изменений. Откройте сравнение расчётов."); });
    return () => controller.abort();
  }, [activeId, snapshotId, snapshotStatus]);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get('/v1/select-market/iprice/health/', { signal: controller.signal }).then(r => setHealth(r.data))
      .catch(e => { if (e.code !== "ERR_CANCELED") setHealthError("Проверка данных не загрузилась."); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (snapshot?.status !== "success") return;
    const controller = new AbortController();
    api.get(`/v1/select-market/iprice/snapshots/${snapshot.id}/analysis/`, { params: { view: "groups", hierarchy: "1c", drill_level: "root" }, signal: controller.signal })
      .then(({ data }) => setSummary(data.summary)).catch(e => { if (e.code !== "ERR_CANCELED") setError("Сводка не загрузилась. Откройте раздел «Рынок» или обновите страницу."); });
    return () => controller.abort();
  }, [snapshot?.id, snapshot?.status]);
  const hasFiles = sourceState.imports.length || sourceState.price_imports.length;
  const ready = snapshot?.status === "success";
  const parserRunning = sourceState.run && !["success", "failed", "cancelled"].includes(sourceState.run.status);
  const stage = ready ? snapshot.is_active ? 4 : 3 : snapshot ? 2 : !hasFiles ? 0 : !sourceState.run ? 1 : 2;
  const zones = summary?.zones;
  const waiting = ready && !snapshot.is_active;
  const compareAvailable = waiting && activeSnapshot && activeSnapshot.id !== snapshot.id;
  const dateText = value => value ? new Date(value).toLocaleDateString("ru-RU") : "—";
  const healthRows = [...(health?.source_checks || []).filter(c => c.count > 0).map(c => ({ key: c.key, label: c.label, count: c.count, tone: "red" })), ...(health?.issues || []).map(c => ({ key: `${c.severity}-${c.code}`, label: issues[c.code] || c.code, count: c.count, tone: c.severity === "error" ? "red" : "amber" }))];
  const count = key => Array.isArray(zones) ? zones.find(z => z.key === key || z.code === key)?.count : zones?.[key]?.count ?? zones?.[key];
  return <>
    {snapshot?.status === "failed" && <div className="ip-alert error"><div className="body"><b>Расчёт завершился с ошибкой</b><span>{snapshot.error || "Откройте расчёты и проверьте исходные данные."}</span></div><Button onClick={() => onNavigate("versions")}>К расчётам</Button></div>}
    {snapshot?.status === "building" && <div className="ip-alert info"><div className="body"><b>iPrice считает новые цены</b><span>Сводка появится после завершения. Страница обновляется автоматически.</span></div></div>}
    {parserRunning && <div className="ip-alert info"><div className="body"><b>iPrice собирает цены конкурентов</b><span>Перед новым расчётом дождитесь завершения сбора.</span></div><Button onClick={() => onNavigate("data", "parser")}>Состояние сбора</Button></div>}
    {welcome && <section className="ip-welcome compact" aria-label="Знакомство с iPrice"><div className="ip-welcome-text"><h2>iPrice считает цены. Вы проверяете и утверждаете расчёт</h2><p>Цена складывается из закупочной стоимости с доставкой, цен конкурентов в регионе и правил компании.</p><div className="ip-row"><Button variant="primary" onClick={() => { setWelcome(false); try { sessionStorage.setItem("select-market-iprice-welcome-hidden", "1"); } catch { /* Storage may be disabled. */ } }}>Начать работу</Button><Button variant="ghost" icon="help" onClick={onHelp}>Открыть справку</Button></div></div></section>}
    {!parserRunning && snapshot?.status !== "building" && <section className="ip-next"><div className="ip-next-badge"><Icon name={waiting ? "bolt" : ready ? "check" : "data"} /></div><div className="ip-next-body"><div className="ip-next-kicker">Следующий шаг</div><h2>{ready ? snapshot.is_active ? "Расчёт утверждён" : comparison ? `Расчёт от ${dateText(snapshot.calculation_date)}: выросло цен — ${comparison.final_rrp_increased ?? 0}, снизилось — ${comparison.final_rrp_decreased ?? 0}` : "Проверьте новые цены" : "Подготовьте данные и посчитайте цены"}</h2><p>{ready ? `${activeSnapshot ? `Внутри системы утверждён расчёт от ${dateText(activeSnapshot.calculation_date)}. ` : "Утверждённых цен пока нет. "}Посмотрите изменения, проверьте спорные цены и утвердите версию. Отправки в 1С нет.` : "Загрузите прайс и закупочные цены, обновите цены конкурентов, затем запустите расчёт."}</p>{comparisonError && <p role="status">{comparisonError}</p>}</div><div className="ip-next-act">{compareAvailable && <Button variant="accent" icon="compare" onClick={onCompare}>1. Изменения</Button>}<Button variant={compareAvailable ? "secondary" : "accent"} icon="table" onClick={() => onNavigate(ready ? "prices" : "data")}>{ready ? `${compareAvailable ? "2." : "1."} Новые цены` : "Загрузить данные"}</Button><Button variant="ghost" className="on-dark" onClick={() => onNavigate("versions")}>{compareAvailable ? "3. Утверждение" : "К расчётам"}</Button></div></section>}
    <div className="ip-panel ip-cycle">{[["Данные", health ? `Ошибок: ${health.summary?.errors ?? "—"}, замечаний: ${health.summary?.warnings ?? "—"}` : "Проверяем источники", "data"], ["Конкуренты", parserRunning ? "Сбор выполняется" : sourceState.run?.status === "success" ? `Собраны ${dateText(sourceState.run.finished_at)}` : sourceState.run?.status === "failed" ? "Сбор завершился с ошибкой" : "Ещё не собирали", "data"], ["Расчёт", snapshot ? `от ${dateText(snapshot.calculation_date)}` : "Ещё нет", "versions"], ["Проверка", waiting ? "Ожидает проверки" : "Цены и замечания", "prices"], ["Утверждение", activeSnapshot ? `от ${dateText(activeSnapshot.calculation_date)}` : "Нет утверждённой версии", "versions"]].map(([title, sub, view], i) => <a key={title} className={`ip-step ${i < stage ? "done" : i === stage ? "cur" : ""}`} href={`#iprice-${view}`} onClick={e => { e.preventDefault(); onNavigate(view, i === 1 ? "parser" : undefined); }}><span className="n">{i + 1}</span><div><b>{title}</b><span className="s">{sub}</span></div></a>)}</div>
    {error && <p role="alert">{error}</p>}
    {ready ? <><div><h2 className="ip-h2">Товары для проверки</h2><p className="muted small">Расчёт за {snapshot.calculation_date}. Сводка по всему расчёту.</p></div><div className="ip-grid k4">{[["critical_above", "Критически выше рынка", "bad", "alert"], ["above_market", "Выше рынка", "warn", "up"], ["below_market", "Ниже рынка", "", "down"], ["no_market_data", "Нет данных рынка", "", "info"]].map(([key, title, tone, icon]) => <button type="button" key={key} className={`ip-kpi ip-attn ${tone ? `is-${tone}` : ""}`} disabled={count(key) == null || count(key) === 0} onClick={() => onZone(key)}><span className="v"><Icon name={icon} size={18} />{count(key) ?? "—"}</span><span className="l">{title}</span><span className="go">{count(key) === 0 ? "Таких нет" : "Открыть список"}<Icon name="chev" size={14} /></span></button>)}</div>
      <div className="ip-grid k2"><Panel title="Итог расчёта" sub={`Расчёт за ${fmtDate(snapshot.calculation_date)}`} actions={<Button variant="ghost" size="s" onClick={() => onNavigate("market")}>Подробнее</Button>}><ul className="ip-facts sm-panel-body"><li><Icon name="tag" /><span>Типичная текущая цена: <b>{priceText(summary?.median_retail_price)}</b>; итоговая РРЦ: <b>{priceText(summary?.median_final_rrp)}</b> руб. без НДС.</span></li><li><Icon name="compare" /><span>Цена конкурентов (медиана): <b>{priceText(summary?.median_market_price)}</b> руб.</span></li><li><Icon name="alert" /><span>Ошибки расчёта: <b>{summary?.calculation_errors ?? "—"}</b>. Причины указаны у товаров.</span></li></ul></Panel>
      <Panel title="Проверка данных" sub="Источники и последний успешный расчёт"><div className="ip-stack sm-panel-body">{healthError && <p role="alert">{healthError}</p>}{health ? <>{healthRows.map(item => <button type="button" key={item.key} className="ip-row between ip-health-row ip-linkbtn" onClick={() => onNavigate("data", "health")}><span>{item.label}</span><span className={`ip-tag ${item.tone}`}>{item.count}</span></button>)}<p>Мешают расчёту: <b>{health.summary?.errors ?? "—"}</b>. Требуют проверки: <b>{health.summary?.warnings ?? "—"}</b>.</p>{!health.price_date && <p>Полный прайс ещё не загружен.</p>}{!health.snapshot && <p>Проверка расчётных параметров появится после расчёта.</p>}</> : !healthError && <p>Проверяем данные…</p>}<Button onClick={() => onNavigate("data", "health")}>Открыть замечания</Button></div></Panel></div>
    </> : <Panel><div className="ip-empty"><b>{snapshot?.status === "building" ? "iPrice считает цены" : snapshot?.status === "failed" ? "Расчёт не завершён" : "Расчётов пока нет"}</b><span>Сводка появится после завершения расчёта.</span></div></Panel>}
  </>;
}
