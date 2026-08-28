import { useEffect, useMemo, useRef, useState } from "react";
import { useDropdownPosition } from "./useDropdownPosition";
import "./dashboard_multi_select.css";

export function DashboardMultiSelect({ label, options = [], selected = [], onApply }) {
  const rootRef = useRef(null); const menuRef = useRef(null); const openRef = useRef(false);
  const selectedRef = useRef(selected); const draftRef = useRef(selected); const onApplyRef = useRef(onApply);
  const [open, setOpen] = useState(false); const [draft, setDraft] = useState(selected); const [search, setSearch] = useState("");
  useEffect(() => { selectedRef.current = selected; onApplyRef.current = onApply; if (!open) draftRef.current = selected; }, [selected, onApply, open]);
  const visible = useMemo(() => { const query = search.trim().toLocaleLowerCase("ru-RU"); return options.filter((item) => !query || String(item).toLocaleLowerCase("ru-RU").includes(query)); }, [options, search]);
  const updateDraft = (next) => { draftRef.current = next; setDraft(next); };
  const commit = () => { const current = selectedRef.current; const next = draftRef.current; if (current.length !== next.length || current.some((value, index) => value !== next[index])) onApplyRef.current(next); };
  useEffect(() => { const close = (event) => { if (openRef.current && !rootRef.current?.contains(event.target)) { commit(); openRef.current = false; setOpen(false); setSearch(""); } }; document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close); }, []);
  const { menuStyle, resetPosition } = useDropdownPosition({ open, rootRef, menuRef, contentKey: `${visible.length}:${search}` });
  const toggleMenu = () => { if (open) { commit(); openRef.current = false; setOpen(false); setSearch(""); } else { updateDraft(selected); resetPosition(); openRef.current = true; setOpen(true); } };
  const toggle = (value) => updateDraft(draft.includes(value) ? draft.filter((item) => item !== value) : [...draft, value]);
  const selectVisible = () => updateDraft([...new Set([...draft, ...visible])]);
  const shown = open ? draft : selected;
  return <div className={`dashboard-filter${open ? " dashboard-filter--open" : ""}`} ref={rootRef}><label>{label}</label><button type="button" className="dashboard-multiselect__control" aria-expanded={open} onClick={toggleMenu}><span>{shown.length ? `Выбрано: ${shown.length}` : "Все"}</span><i aria-hidden="true">▾</i></button>{open && <div ref={menuRef} className="dashboard-multiselect__menu" style={menuStyle}><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск…" /><div className="dashboard-multiselect__actions"><button type="button" disabled={!visible.length} onClick={selectVisible}>Выбрать найденные</button><button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button></div><div className="dashboard-multiselect__options">{visible.map((value) => <label key={String(value)}><input type="checkbox" checked={draft.includes(value)} onChange={() => toggle(value)} /><span>{value}</span></label>)}{!visible.length && <p>Нет значений</p>}</div></div>}</div>;
}
