import { Pager } from "./ui/Pager";
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
  const requestKey = JSON.stringify({ revision });
  const ready = data?.requestKey === requestKey;
  const toggle = (value, key) => { const list = value ? value.split(",") : []; return (list.includes(key) ? list.filter(v => v !== key) : [...list, key]).join(","); };
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => api.get('/v1/select-market/iprice/health/', { params: { all_results: true }, signal: controller.signal }).then(r => { setData({ ...r.data, requestKey }); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось проверить данные."); }), 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [revision, requestKey]);
  const query = search.trim().toLocaleLowerCase();
  const selected = (data?.results || []).filter(item =>
    (!level || item.severity === level) && (!section || section.split(",").includes(item.section)) &&
    (!code || code.split(",").includes(item.code)) &&
    (!query || Object.values(item).map(value => String(value ?? "")).join(" ").toLocaleLowerCase().includes(query)));
  const pages = Math.max(1, Math.ceil(selected.length / 50));
  const currentPage = Math.min(page, pages);
  return <div className="ip-stack sm-health">
    <div className="ip-grid k4">{[
      ["Мешает расчёту", data?.summary?.errors ?? "—", "эти товары требуют исправления", "error"],
      ["Проверьте", data?.summary?.warnings ?? "—", "точность расчёта под вопросом", "warning"],
      ["Проверки источников без замечаний", data?.price_date ? `${data.source_checks.filter(c => !c.count).length} из ${data.source_checks.length}` : "—", "Закупочная цена, доставка, розничная цена, классификация, параметры расчёта и цены аналогов", ""],
      ["Частое замечание", data?.issues?.length ? Math.max(...data.issues.map(i => i.count)) : "—", data?.issues?.length ? issues[[...data.issues].sort((a, b) => b.count - a.count)[0].code] || [...data.issues].sort((a, b) => b.count - a.count)[0].code : "расчётных замечаний нет", ""],
    ].map(([label, value, sub, severity]) => <button key={label} className="ip-kpi" onClick={() => { setLevel(severity); setPage(1); }}><span className="l">{label}</span><span className="v">{value}</span><span className="d">{sub}</span></button>)}</div>
    <Panel><div className="ip-stack sm-panel-body">
      <div className="ip-row between"><div className="ip-row"><div className="ip-seg">{[["", "Все"], ["error", "Мешает расчёту"], ["warning", "Проверьте"]].map(([key, label]) => <button key={key} aria-pressed={level === key} onClick={() => { setLevel(key); setPage(1); }}>{label}</button>)}</div><input className="ip-input" style={{width:280}} aria-label="Найти замечание" placeholder="Код 1С, название, регион" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} /></div><Button icon="refresh" onClick={() => { setData(null); setError(""); setRevision(v => v + 1); }} title="Обновляет проверку исходных данных и список замечаний. Цены не пересчитываются.">Обновить проверки</Button></div>
      <div className="ip-filters"><span className="small muted">Разделы:</span>{[["sources", "Исходные данные"], ["snapshot", "Последний расчёт"]].map(([key,label]) => <button className={`ip-chip ${section.split(",").includes(key) ? "on" : ""}`} key={key} aria-pressed={section.split(",").includes(key)} onClick={() => { setSection(toggle(section, key)); setPage(1); }}>{label}</button>)}</div>
      <div className="ip-filters"><span className="small muted">Типы:</span>{data?.filter_codes?.map(key => <button className={`ip-chip ${code.split(",").includes(key) ? "on" : ""}`} key={key} aria-pressed={code.split(",").includes(key)} onClick={() => { setCode(toggle(code, key)); setPage(1); }}>{issues[key] || ({ purchase: "Закупочная цена", delivery: "Доставка", retail: "Розничная цена", competitor_price: "Нет цены актуального аналога в регионе", classification: "Товар не классифицирован", parameters: "Не заполнены или некорректны параметры расчёта" })[key] || key}</button>)}</div>
      {data && <p className="small muted">{data.price_date ? `Прайс за ${data.price_date}.` : "Полный прайс пока не загружен."} {data.snapshot ? `Расчёт №${data.snapshot.version} за ${data.snapshot.date}.` : "Успешного расчёта пока нет. Исходные данные проверяются по последнему прайсу."}</p>}
      {error && <p role="alert">{error}</p>}{!ready && !error && <p role="status" className="sm-iprice-loading">Проверяем данные…</p>}
    </div>
    <div className="sm-iprice-table"><table className="ip-table"><thead><tr><th>Важность</th><th>Замечание</th><th>Раздел и товар</th><th>Исправление</th></tr></thead><tbody>{(ready ? selected.slice((currentPage - 1) * 50, currentPage * 50) : [])?.map(item => <tr key={item.id}><td><span className={`ip-tag ${item.severity === "error" ? "red" : "amber"}`}>{item.severity === "error" ? "Мешает расчёту" : "Проверьте"}</span></td><td>{issues[item.code] || item.message || item.code}</td><td>{item.nom}<span className="sub">{item.code_1c} · {item.region}</span><span className="sub">{item.section === "sources" ? "Исходные данные" : "Последний расчёт"}</span></td><td>{item.fix}</td></tr>)}</tbody></table></div>
    {ready && selected.length === 0 && <p className="ip-empty">Замечаний по выбранным условиям нет.</p>}
    <Pager page={currentPage} totalPages={pages} count={selected.length} pageSize={50} onPage={setPage} disabled={!ready} /></Panel>
  </div>;
}
