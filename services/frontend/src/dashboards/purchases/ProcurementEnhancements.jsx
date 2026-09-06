import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api/client";
import { DateRangePicker } from "../../components/DateRangePicker";
import "./procurement_enhancements.css";

export function procurementNumber(value, suffix = "", maximumFractionDigits = 2) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(Number(value))}${suffix}`;
}

export function ProcurementTooltip({ state, title, rows = [] }) {
  const ref = useRef(null);
  const [position, setPosition] = useState({ left: state?.x || 0, top: state?.y || 0 });
  useLayoutEffect(() => {
    if (!state || !ref.current) return;
    const box = ref.current.getBoundingClientRect();
    const gap = 14;
    const padding = 10;
    const left = state.x + gap + box.width <= window.innerWidth - padding ? state.x + gap : state.x - gap - box.width;
    const top = state.y + gap + box.height <= window.innerHeight - padding ? state.y + gap : state.y - gap - box.height;
    setPosition({
      left: Math.max(padding, Math.min(left, window.innerWidth - box.width - padding)),
      top: Math.max(padding, Math.min(top, window.innerHeight - box.height - padding)),
    });
  }, [state]);
  if (!state) return null;
  return createPortal(
    <aside ref={ref} className="procurement-chart-tooltip" style={position}>
      <strong>{title}</strong>
      {rows.map((row) => <div key={row.label}><i style={{ background: row.color }} /><span>{row.label}</span><b style={row.valueColor ? { color: row.valueColor } : undefined}>{procurementNumber(row.value, row.suffix, row.digits)}</b></div>)}
    </aside>,
    document.body,
  );
}

function dateValue(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || "")) ? String(value) : "";
}

function isFullMonthRange(start, end) {
  if (!start || !end) return false;
  const startParts = start.split("-").map(Number);
  const endParts = end.split("-").map(Number);
  if (startParts.length !== 3 || endParts.length !== 3 || startParts.some(Number.isNaN) || endParts.some(Number.isNaN)) return false;
  return startParts[2] === 1 && endParts[2] === new Date(endParts[0], endParts[1], 0).getDate();
}

function errorText(error, fallback) {
  const data = error?.response?.data;
  return data?.value || data?.period || data?.date_start || data?.date_end || data?.detail || fallback;
}

export function PlanEditor({ kind, publicToken, dateStart, dateEnd, onSaved, onSavingChange }) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState(dateValue(dateStart));
  const [end, setEnd] = useState(dateValue(dateEnd));
  const [value, setValue] = useState("");
  const [existing, setExisting] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const endpoint = publicToken
    ? `/v1/datasets/public-group/${publicToken}/fb-${kind}/plans/`
    : `/v1/datasets/fb-${kind}/plans/`;
  const invalidMonthBounds = Boolean(start && end && !isFullMonthRange(start, end));

  useEffect(() => {
    if (!open || !start || !end || start > end || invalidMonthBounds) { setExisting([]); return undefined; }
    let active = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await api.get(endpoint, { params: { date_start: start, date_end: end } });
        if (active) setExisting(response.data?.existing || []);
      } catch (requestError) {
        if (active) setError(errorText(requestError, "Не удалось проверить существующий план."));
      } finally {
        if (active) setLoading(false);
      }
    }, 180);
    return () => { active = false; clearTimeout(timer); };
  }, [open, start, end, endpoint, invalidMonthBounds]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => { if (event.key === "Escape" && !saving) setOpen(false); };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open, saving]);

  const show = () => {
    setStart(dateValue(dateStart));
    setEnd(dateValue(dateEnd));
    setValue("");
    setError("");
    setOpen(true);
  };
  const save = async () => {
    setError("");
    if (!start || !end || start > end) { setError("Укажите корректный период."); return; }
    if (!isFullMonthRange(start, end)) return;
    if (!/^\d+$/.test(value) || Number(value) <= 0) { setError("Плановое значение должно быть целым числом больше нуля."); return; }
    setSaving(true);
    onSavingChange?.(true);
    let completed = false;
    try {
      await api.post(endpoint, { date_start: start, date_end: end, value: Number(value) });
      await onSaved?.();
      completed = true;
      setOpen(false);
    } catch (requestError) {
      setError(errorText(requestError, "Не удалось сохранить план."));
    } finally {
      setSaving(false);
      if (!completed) onSavingChange?.(false);
    }
  };

  return <>
    <button type="button" className="procurement-plan-trigger" onClick={show} title="Установить план" aria-label="Установить план">✎</button>
    {open && createPortal(<div className="procurement-plan-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setOpen(false); }}><section className="procurement-plan-dialog" style={{ overflow: "visible" }} role="dialog" aria-modal="true" aria-labelledby={`${kind}-plan-title`}>
      <header><div><small>Плановые показатели</small><h3 id={`${kind}-plan-title`}>Установить план</h3></div><button type="button" onClick={() => setOpen(false)} disabled={saving} aria-label="Закрыть">×</button></header>
      <div className="procurement-plan-fields"><div className="procurement-plan-period" style={{ gridColumn: "1 / -1" }}><DateRangePicker start={start} end={end} resetRange={{ start: dateValue(dateStart), end: dateValue(dateEnd) }} onChange={({ start: nextStart, end: nextEnd }) => { setStart(nextStart); setEnd(nextEnd); setError(""); }} /></div><label className="procurement-plan-value"><span>Плановое значение</span><input type="text" inputMode="numeric" value={value} placeholder="Введите целое число" onChange={(event) => { setValue(event.target.value.replace(/\D/g, "")); setError(""); }} /></label></div>
      {invalidMonthBounds && <div className="procurement-plan-warning"><strong>Период плана должен начинаться с первого числа месяца и заканчиваться последним числом месяца.</strong></div>}
      {loading && <div className="procurement-plan-checking">Проверяем существующие значения…</div>}
      {!loading && existing.length > 0 && <div className="procurement-plan-warning"><strong>В выбранном диапазоне есть пересечения с ранее установленным планом.</strong><p>При сохранении изменятся только даты выбранного диапазона.</p></div>}
      {error && <div className="procurement-plan-error" role="alert">{error}</div>}
      <footer><button type="button" className="procurement-plan-cancel" onClick={() => setOpen(false)} disabled={saving}>Отмена</button><button type="button" className="procurement-plan-save" onClick={save} disabled={saving || invalidMonthBounds}>{saving ? "Сохранение…" : "Сохранить"}</button></footer>
    </section></div>, document.body)}
    {saving && !onSavingChange && createPortal(<div className="global-spinner-overlay show"><div className="spinner-container"><div className="infinite-spinner" /><div className="spinner-text">Обновление данных...</div></div></div>, document.body)}
  </>;
}
