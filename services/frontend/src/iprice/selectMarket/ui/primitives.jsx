import { useEffect, useRef } from "react";
import Icon from "./Icon";

export function Button({ variant = "secondary", size, icon, children, className = "", ...props }) {
  return <button type="button" className={["ip-btn", variant, size, icon && !children ? "icon" : "", className].filter(Boolean).join(" ")} {...props}>{icon && <Icon name={icon} />}{children}</button>;
}

// Archive drawer on the native top layer; the platform menu cannot clip it.
export function Drawer({ open, onClose, title, sub, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!open) return;
    const previous = document.activeElement;
    dialog.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { dialog.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, [open]);
  return <dialog ref={ref} className="sm-demo-dialog" aria-label={title} onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    {open && <aside className="ip-drawer"><div className="ip-drawer-head"><div style={{ flex: 1, minWidth: 0 }}><h2>{title}</h2>{sub && <div className="muted small">{sub}</div>}</div><Button variant="ghost" icon="x" onClick={onClose} aria-label="Закрыть" /></div><div className="ip-drawer-body">{children}</div></aside>}
  </dialog>;
}

export function PageHead({ title, text, actions, onHelp }) {
  return <div className="ip-page-head"><div><h1>{title}</h1>{text && <p>{text} {onHelp && <button className="ip-linkbtn" onClick={onHelp}>Подробнее</button>}</p>}</div>{actions && <div className="ip-row">{actions}</div>}</div>;
}

export function Panel({ title, sub, actions, children }) {
  return <section className="ip-panel">{title && <div className="ip-panel-head"><div className="ip-panel-title"><h2>{title}</h2>{sub && <p>{sub}</p>}</div>{actions && <div className="ip-row">{actions}</div>}</div>}{children}</section>;
}

export function Tabs({ value, onChange, items }) {
  return <div className="ip-tabs" role="tablist">{items.map(([key, title]) => <button type="button" key={key} role="tab" aria-selected={value === key} onClick={() => onChange(key)}>{title}</button>)}</div>;
}

export function Confirmation({ message, onAnswer }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!message) return;
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, [message]);
  return <dialog className="sm-demo-dialog sm-demo-confirm" ref={ref} aria-label="Подтверждение действия" onCancel={e => { e.preventDefault(); onAnswer(false); }} onClick={e => { if (e.target === e.currentTarget) onAnswer(false); }}>
    {message && <div className="ip-modal"><h2>Подтвердите действие</h2><div className="muted">{message}</div><div className="foot"><Button onClick={() => onAnswer(false)}>Отмена</Button><Button variant="primary" onClick={() => onAnswer(true)}>Подтвердить</Button></div></div>}
  </dialog>;
}

export function Modal({ title, onClose, children, footer }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => { dialog.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="sm-demo-dialog sm-demo-confirm" aria-label={title} onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}><div className="ip-modal"><div className="ip-row between"><h2>{title}</h2><Button variant="ghost" icon="x" aria-label="Закрыть" onClick={onClose} /></div>{children}<div className="foot">{footer}</div></div></dialog>;
}
