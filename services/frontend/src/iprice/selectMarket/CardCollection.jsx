import { useState } from "react";
import { Pager } from "./ui/Pager";
import { FilterChip } from "./SelectMarketFilters";

export function CardCollection({ items, filters = [], children }) {
  const [selected, setSelected] = useState({});
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(() => {
    try { const value = Number(sessionStorage.getItem("select-market-iprice-page-size")); return [25, 50, 100].includes(value) ? value : 50; } catch { return 50; }
  });
  const matches = (item, except) => filters.every(([key]) => key === except || !selected[key]?.length || selected[key].includes(String(item[key] || "Не указано")));
  const visible = items.filter(item => matches(item));
  const pages = Math.max(1, Math.ceil(visible.length / size));
  const current = Math.min(page, pages);
  if (!items.length) return null;
  return <div className="ip-stack">
    {!!filters.length && <div className="ip-filters">{filters.map(([key, label, display]) => <FilterChip key={key} name={key} label={label} displayValue={display} values={[...new Set(items.filter(item => matches(item, key)).map(item => String(item[key] || "Не указано")))].sort((a,b) => a.localeCompare(b,"ru"))} selected={selected[key] || []} onChange={value => { setSelected({...selected,[key]:value}); setPage(1); }} />)}</div>}
    {!visible.length && <div className="ip-empty"><b>Нет товаров для выбранных фильтров</b></div>}
    <div className="ip-cards">{visible.slice((current - 1) * size, current * size).map(children)}</div>
    <Pager page={current} totalPages={pages} count={visible.length} pageSize={size} onPage={setPage} onPageSize={value => { setSize(value); setPage(1); try { sessionStorage.setItem("select-market-iprice-page-size", String(value)); } catch { /* storage disabled */ } }} />
  </div>;
}
