import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDropdownPosition } from "../../components/useDropdownPosition";

export function FloatingTooltip({ children, getAnchor, id }) {
  const tooltipRef = useRef(null);
  useLayoutEffect(() => {
    const place = () => {
      const element = tooltipRef.current;
      const anchor = getAnchor();
      if (!element || !anchor) return;
      const { width, height } = element.getBoundingClientRect();
      const right = anchor.right ?? anchor.left;
      const bottom = anchor.bottom ?? anchor.top;
      const left = right + 10 + width <= window.innerWidth - 12 ? right + 10 : anchor.left - width - 10;
      const top = bottom + 10 + height <= window.innerHeight - 12 ? bottom + 10 : anchor.top - height - 10;
      element.style.left = `${Math.max(12, Math.min(left, window.innerWidth - width - 12))}px`;
      element.style.top = `${Math.max(12, Math.min(top, window.innerHeight - height - 12))}px`;
      element.style.visibility = "visible";
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  });
  return createPortal(<div ref={tooltipRef} id={id} role="tooltip" className="wd-floating-tooltip" style={{ visibility: "hidden" }}>{children}</div>, document.body);
}

export function Help({ children, label = "Пояснение" }) {
  const anchorRef = useRef(null);
  const [open, setOpen] = useState(false);
  const id = useId();
  return <><button ref={anchorRef} type="button" className="wd-floating-help wd-help" aria-label={label} aria-describedby={open ? id : undefined}
    onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
    onClick={(e) => { e.stopPropagation(); setOpen(true); }} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 7v5M8 4.5v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg></button>
    {open && <FloatingTooltip id={id} getAnchor={() => anchorRef.current?.getBoundingClientRect()}>{children}</FloatingTooltip>}</>;
}

export function SelectField({ label, help, options, value, onChange, placeholder = "Выберите", className = "" }) {
  const rootRef = useRef(null), menuRef = useRef(null), buttonRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [index, setIndex] = useState(0);
  const id = useId();
  const visible = options.filter((item) => item.label.toLocaleLowerCase("ru-RU").includes(search.toLocaleLowerCase("ru-RU")));
  const { menuStyle, resetPosition } = useDropdownPosition({ open, rootRef, menuRef, contentKey: `${visible.length}:${search}` });
  useEffect(() => {
    const close = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const choose = (item) => { onChange(item.value); setOpen(false); buttonRef.current?.focus(); };
  const toggle = () => { resetPosition(); setSearch(""); setIndex(Math.max(0, options.findIndex((o) => o.value === value))); setOpen(!open); };
  const keyboard = (event) => {
    if (event.key === "Escape") { setOpen(false); buttonRef.current?.focus(); }
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      if (!open) { toggle(); return; }
      setIndex((old) => event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1 : Math.max(0, Math.min(visible.length - 1, old + (event.key === "ArrowDown" ? 1 : -1))));
    }
    if (event.key === "Enter" && open && visible[index]) { event.preventDefault(); choose(visible[index]); }
  };
  useEffect(() => { if (open) menuRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" }); }, [index, open]);
  return <div ref={rootRef} className={`dashboard-filter wd-control wd-select ${open ? "dashboard-filter--open" : ""} ${className}`} onKeyDown={keyboard}>
    <div className="wd-control-label"><label htmlFor={id}>{label}</label>{help}</div>
    <button ref={buttonRef} id={id} type="button" className="dashboard-multiselect__control" aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-options`} onClick={toggle}>
      <span>{options.find((o) => o.value === value)?.label || placeholder}</span><i aria-hidden="true">▾</i>
    </button>
    {open && <div ref={menuRef} className="dashboard-multiselect__menu" style={menuStyle}>
      <input aria-label={`Поиск: ${label}`} value={search} onChange={(e) => { setSearch(e.target.value); setIndex(0); }} placeholder="Поиск…" />
      <div id={`${id}-options`} className="dashboard-multiselect__options wd-select-options" role="listbox" aria-label={label}>
        {visible.map((item, i) => <button key={item.value} type="button" role="option" aria-selected={item.value === value} data-active={i === index} onClick={() => choose(item)}>{item.label}</button>)}
        {!visible.length && <p>Нет значений</p>}
      </div>
    </div>}
  </div>;
}

export function LoadingBlock() {
  return <div className="global-spinner-overlay show" role="status" aria-label="Загрузка данных"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Загрузка данных...</div></div></div>;
}
