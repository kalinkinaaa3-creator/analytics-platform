import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { Button, Drawer } from "./ui/primitives";
import Icon from "./ui/Icon";

const labels = { sale_region: "Регион продажи", pricing_method: "Способ расчёта", calculation_status: "Статус товара", group_1: "Группа 1", group_2: "Группа 2", group_3: "Группа 3", group_4: "Группа 4",
  is_classified: "Наличие классификации", category: "Категория", subcategory: "Подкатегория",
  subcategory_type: "Тип подкатегории", color: "Цвет", material: "Материал", modification: "Модификация", item_type: "Тип позиции" };
const display = (key, value) => key === "pricing_method" ? ({ analog: "По рынку", exclusive: "Эксклюзив" })[value] || value : key === "calculation_status" ? ({success: "Готово", warning: "Есть замечание", error: "Нет цены"})[value] || value : value === "__empty__" ? "Не заполнено" : key === "is_classified" ? (value === "true" ? "Классифицирован" : "Без классификации") : value;

function Options({ name, values, selected, toggle }) {
  const [query, setQuery] = useState("");
  const visible = values.filter(v => display(name, v).toLowerCase().includes(query.trim().toLowerCase()));
  return <>{values.length > 8 && <div className="ip-affix"><span className="pre"><Icon name="search" size={14} /></span><input className="ip-input" placeholder="Найти значение" aria-label="Найти значение" value={query} onChange={e => setQuery(e.target.value)} /></div>}
    <div className="list" role="group" aria-label={labels[name]}>{visible.map(v => <label className="opt" key={v}><input type="checkbox" checked={selected.includes(v)} onChange={() => toggle(v)} /><span className="lbl">{display(name, v)}</span></label>)}{!visible.length && <span className="quiet small">Нет значений</span>}</div></>;
}

function Chip({ name, values, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = e => { if (e.key === "Escape" || (e.type === "pointerdown" && !ref.current?.contains(e.target))) setOpen(false); };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return <div ref={ref} className="sm-filter-chip"><button type="button" className={`ip-chip ${selected.length ? "on" : ""}`} aria-expanded={open} onClick={() => setOpen(!open)}>
    <span className="val">{labels[name]}: {selected.length ? `${display(name, selected[0])}${selected.length > 1 ? ` и ещё ${selected.length - 1}` : ""}` : "все"}</span>{!selected.length && <Icon name="chevDown" />}
  </button>{selected.length > 0 && <button type="button" className="sm-filter-clear" aria-label={`Сбросить «${labels[name]}»`} onClick={() => onChange([])}><Icon name="x" size={12} /></button>}{open && <div className="ip-pop" style={{ top: 36, left: 0 }}><Options name={name} values={values} selected={selected} toggle={v => onChange(selected.includes(v) ? selected.filter(x => x !== v) : [...selected, v])} />
    <div className="foot"><Button size="s" variant="ghost" onClick={() => onChange([])}>Сбросить</Button><Button size="s" onClick={() => setOpen(false)}>Готово</Button></div></div>}</div>;
}

export function SelectMarketFilters({ snapshotId, comparisonId, search, filters, onChange, mode = "regions", zone = "", problemsOnly = false }) {
  const [options, setOptions] = useState({});
  const [error, setError] = useState("");
  const [more, setMore] = useState(false);
  const serialized = JSON.stringify(filters);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`/v1/select-market/iprice/snapshots/${snapshotId}/filters/`, { params: { filters: serialized, search, mode, zone, problems_only: problemsOnly, comparison_id: comparisonId || undefined }, signal: controller.signal })
      .then(({ data }) => { setOptions(data); setError(""); }).catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить варианты фильтров."); });
    return () => controller.abort();
  }, [snapshotId, comparisonId, search, serialized, mode, zone, problemsOnly]);
  const set = (key, value) => { const next = { ...filters }; if (value.length) next[key] = value; else delete next[key]; onChange(next); };
  const values = key => [...new Set([...(options[key] || []), ...(filters[key] || [])])];
  return <><div className="ip-filters">{Object.keys(labels).filter(key => ["group_1", "group_2", "group_3", "group_4", "category", "is_classified"].includes(key) || filters[key]?.length).map(key => <Chip key={key} name={key} values={values(key)} selected={filters[key] || []} onChange={value => set(key, value)} />)}
    <Button size="s" icon="filter" onClick={() => setMore(true)}>Ещё фильтры</Button>{Object.values(filters).some(v => v.length) && <Button size="s" variant="ghost" onClick={() => onChange({})}>Сбросить все</Button>}
  </div>{error && <p role="alert">{error}</p>}<Drawer open={more} onClose={() => setMore(false)} title="Фильтры" sub="Списки подстраиваются под уже выбранные фильтры: остаются только подходящие значения.">
    {Object.entries(labels).map(([key, label]) => <details key={key} open={filters[key]?.length > 0} className="ip-panel sm-filter-section"><summary>{label}{filters[key]?.length > 0 && <span className="ip-badge">{filters[key].length}</span>}</summary>
      <div className="ip-pop sm-filter-options"><Options name={key} values={values(key)} selected={filters[key] || []} toggle={v => set(key, filters[key]?.includes(v) ? filters[key].filter(x => x !== v) : [...(filters[key] || []), v])} /></div></details>)}
    <div className="ip-row" style={{ justifyContent: "flex-end" }}><Button variant="ghost" onClick={() => onChange({})}>Сбросить все</Button><Button variant="primary" onClick={() => setMore(false)}>Показать товары</Button></div>
  </Drawer></>;
}
