import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";

function Tip({ anchor, id, title, text }) {
  const [pos, setPos] = useState(null);
  useEffect(() => {
    if (!anchor) return undefined;
    const place = () => {
      const r = anchor.getBoundingClientRect();
      const w = Math.min(320, window.innerWidth - 24);
      const left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12));
      const below = r.bottom + 8;
      const up = window.innerHeight - below < 160;
      setPos({ left, width: w, top: up ? undefined : below, bottom: up ? window.innerHeight - r.top + 8 : undefined });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => { window.removeEventListener("scroll", place, true); window.removeEventListener("resize", place); };
  }, [anchor]);
  if (!pos) return null;
  const host = anchor.closest("dialog") || document.querySelector(".sm-iprice") || document.body;
  return createPortal(
    <div className="ip-tip" role="tooltip" id={id} style={pos}>
      {title ? <b>{title}</b> : null}
      <span>{text}</span>
    </div>,
    host,
  );
}

// Слово с пунктиром: наведите или нажмите – появится объяснение.
// k – ключ словаря GLOSSARY; text – своё объяснение вместо словарного.
export function Term({ text, title, children, icon = false }) {
  const g = null;
  const body = text || g?.text;
  const head = title ?? g?.term;
  const id = useId();
  const [el, setEl] = useState(null);
  const [open, setOpen] = useState(false);
  if (!body) return children ?? head ?? null;
  const show = () => setOpen(true);
  const hide = () => setOpen(false);
  return (
    <>
      <span
        ref={setEl}
        className={`ip-term ${icon ? "has-icon" : ""}`}
        tabIndex={0}
        role="button"
        aria-describedby={open ? id : undefined}
        aria-label={icon && !children ? `Пояснение: ${head}` : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        onKeyDown={(e) => { if (e.key === "Escape") hide(); }}
      >
        {icon ? children ?? null : children ?? head}
        {icon ? <Icon name="help" size={14} /> : null}
      </span>
      {open ? <Tip anchor={el} id={id} title={head && (icon || String(children) !== head) ? head : null} text={body} /> : null}
    </>
  );
}

