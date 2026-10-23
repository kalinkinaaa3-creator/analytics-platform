import { issues } from "./issueLabels";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button, Panel } from "./ui/primitives";

export function SelectMarketHealth() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [level, setLevel] = useState("");
  const [section, setSection] = useState("");
  const [code, setCode] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const requestKey = JSON.stringify({ revision, level, section, code, search, page });
  const ready = data?.requestKey === requestKey;
  const toggle = (value, key) => { const list = value ? value.split(",") : []; return (list.includes(key) ? list.filter(v => v !== key) : [...list, key]).join(","); };
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => api.get('/v1/select-market/iprice/health/', { params: { level, section, code, search, page }, signal: controller.signal }).then(r => { setData({ ...r.data, requestKey }); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось проверить данные."); }), 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [revision, level, section, code, search, page, requestKey]);
  return <div className="ip-stack">
    <div className="ip-grid k4">{[
      ["Мешает расчёту", data?.summary?.errors ?? "—", "эти товары требуют исправления", "error"],
      ["Проверьте", data?.summary?.warnings ?? "—", "точность расчёта под вопросом", "warning"],
      ["Проверки источников без замечаний", data?.price_date ? `${data.source_checks.filter(c => !c.count).length} из ${data.source_checks.length}` : "—", "покрытие прайса исходными данными", ""],
      ["Частое замечание", data?.issues?.length ? Math.max(...data.issues.map(i => i.count)) : "—", data?.issues?.length ? issues[[...data.issues].sort((a, b) => b.count - a.count)[0].code] || [...data.issues].sort((a, b) => b.count - a.count)[0].code : "расчётных замечаний нет", ""],
    ].map(([label, value, sub, severity]) => <button key={label} className="ip-kpi" onClick={() => { setLevel(severity); setPage(1); }}><span className="l">{label}</span><span className="v">{value}</span><span className="d">{sub}</span></button>)}</div>
    <Panel><div className="ip-stack sm-panel-body">
      <div className="ip-row between"><div className="ip-row"><div className="ip-seg">{[["", "Все"], ["error", "Мешает расчёту"], ["warning", "Проверьте"]].map(([key, label]) => <button key={key} aria-pressed={level === key} onClick={() => { setLevel(key); setPage(1); }}>{label}</button>)}</div><input className="ip-input" style={{width:280}} aria-label="Найти замечание" placeholder="Код 1С, регион, текст" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} /></div><Button icon="refresh" onClick={() => { setData(null); setError(""); setRevision(v => v + 1); }}>Проверить заново</Button></div>
      <div className="ip-filters"><span className="small muted">Разделы:</span>{[["sources", "Исходные данные"], ["snapshot", "Последний расчёт"]].map(([key,label]) => <button className={`ip-chip ${section.split(",").includes(key) ? "on" : ""}`} key={key} aria-pressed={section.split(",").includes(key)} onClick={() => { setSection(toggle(section, key)); setPage(1); }}>{label}</button>)}</div>
      <div className="ip-filters"><span className="small muted">Типы:</span>{data?.filter_codes?.map(key => <button className={`ip-chip ${code.split(",").includes(key) ? "on" : ""}`} key={key} aria-pressed={code.split(",").includes(key)} onClick={() => { setCode(toggle(code, key)); setPage(1); }}>{issues[key] || ({ purchase: "Закупочная цена", delivery: "Доставка", retail: "Розничная цена" })[key] || key}</button>)}</div>
      {data && <p className="small muted">{data.price_date ? `Прайс за ${data.price_date}.` : "Полный прайс пока не загружен."} {data.snapshot ? `Расчёт №${data.snapshot.version} за ${data.snapshot.date}.` : "Успешного расчёта пока нет. Проверки расчётных параметров появятся после его выполнения."}</p>}
      {error && <p role="alert">{error}</p>}{!ready && !error && <p role="status" className="sm-iprice-loading">Проверяем данные…</p>}
    </div>
    <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Важность</th><th>Замечание</th><th>Раздел и товар</th><th>Исправление</th></tr></thead><tbody>{(ready ? data?.results : [])?.map(item => <tr key={item.id}><td><span className={`ip-tag ${item.severity === "error" ? "red" : "amber"}`}>{item.severity === "error" ? "Мешает расчёту" : "Проверьте"}</span></td><td>{issues[item.code] || item.message || item.code}</td><td>{item.nom}<span className="sub">{item.code_1c} · {item.region}</span><span className="sub">{item.section === "sources" ? "Исходные данные" : "Последний расчёт"}</span></td><td>{item.fix}</td></tr>)}</tbody></table></div>
    {ready && data?.count === 0 && <p className="ip-empty">Замечаний по выбранным условиям нет.</p>}
    <div className="ip-row sm-panel-body"><Button disabled={!ready || page <= 1} onClick={() => setPage(page - 1)}>Назад</Button><span>{data?.page || page} / {data?.pages || 1}</span><Button disabled={!ready || page >= (data.pages || 1)} onClick={() => setPage(page + 1)}>Далее</Button></div></Panel>
  </div>;
}
