import { useEffect, useMemo, useRef, useState } from "react";

import "../../components/date_range_picker.css";
import "./lead_generation_week_range_picker.css";


const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function localDate(year, month, day) { return new Date(year, month, day, 12); }
function fromIso(value) { const [year, month, day] = String(value || "").split("-").map(Number); return year && month && day ? localDate(year, month - 1, day) : null; }
function toIso(value) { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`; }
function addDays(value, amount) { return localDate(value.getFullYear(), value.getMonth(), value.getDate() + amount); }
function addMonths(value, amount) { return localDate(value.getFullYear(), value.getMonth() + amount, 1); }
function monthStart(value) { return localDate(value.getFullYear(), value.getMonth(), 1); }
function monthIndex(value) { return value.getFullYear() * 12 + value.getMonth(); }
function monday(value) { return addDays(value, 1 - (value.getDay() || 7)); }
function currentMonday() { return monday(localDate(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())); }
function display(value) { const date = typeof value === "string" ? fromIso(value) : value; return date ? `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()}` : ""; }
function rangeText(range) { return range?.start && range?.end ? `${display(range.start)} — ${display(addDays(fromIso(range.end), 6))}` : "Выберите период"; }
function weekCount(range) { return range?.start && range?.end ? Math.round((fromIso(range.end) - fromIso(range.start)) / 604800000) + 1 : 0; }
function weekLabel(count) { const lastTwo = count % 100; const last = count % 10; if (lastTwo >= 11 && lastTwo <= 14) return "полных недель"; if (last === 1) return "полная неделя"; if (last >= 2 && last <= 4) return "полные недели"; return "полных недель"; }

function initialMonths(start, end) {
  const startMonth = monthStart(fromIso(start) || currentMonday());
  const endMonth = monthStart(addDays(fromIso(end) || fromIso(start) || currentMonday(), 6));
  if (endMonth > startMonth && addMonths(startMonth, 1).getTime() === endMonth.getTime()) return { left: startMonth, right: endMonth };
  return { left: addMonths(endMonth, -1), right: endMonth };
}

function CalendarIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3v3M18 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" /></svg>; }
function ResetIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8V4m0 0h4M4.5 4.5A8 8 0 1 1 4 15" /></svg>; }

function Month({ value, side, menu, onMenu, onMonthChange, onYearChange, preview, minimum, maximum, onHover, onSelect }) {
  const days = useMemo(() => {
    const first = monthStart(value);
    const gridStart = addDays(first, 1 - (first.getDay() || 7));
    return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
  }, [value]);
  const selectedEnd = preview?.end ? toIso(addDays(fromIso(preview.end), 6)) : "";
  const menuOpen = menu?.side === side; const yearMode = menuOpen && menu.mode === "years";
  const years = useMemo(() => Array.from({ length: new Date().getFullYear() - 2024 + 1 }, (_, index) => 2024 + index), []);
  return <section className="leadgen-week-picker__month"><div className="date-range-picker__month-header"><button type="button" className={`date-range-picker__period-selector${menuOpen ? " is-open" : ""}`} onClick={() => onMenu(menuOpen ? null : { side, mode:"months" })}><span>{MONTHS[value.getMonth()]} {value.getFullYear()}</span><i aria-hidden="true">⌄</i></button>{menuOpen && <div className="date-range-picker__period-menu">{!yearMode ? <><div className="date-range-picker__period-year"><button type="button" aria-label="Предыдущий год" onClick={() => onYearChange(side, value.getFullYear() - 1)}>‹</button><button type="button" className="date-range-picker__period-year-value" onClick={() => onMenu({ side, mode:"years" })}>{value.getFullYear()}<span aria-hidden="true">⌄</span></button><button type="button" aria-label="Следующий год" onClick={() => onYearChange(side, value.getFullYear() + 1)}>›</button></div><div className="date-range-picker__period-months">{MONTHS.map((name, index) => <button type="button" key={name} className={index === value.getMonth() ? "is-selected" : ""} onClick={() => onMonthChange(side, index)}>{name.slice(0, 3)}</button>)}</div></> : <><div className="date-range-picker__years-header"><button type="button" onClick={() => onMenu({ side, mode:"months" })}>‹</button><strong>Выберите год</strong><span /></div><div className="date-range-picker__period-years">{years.map((year) => <button type="button" key={year} className={year === value.getFullYear() ? "is-selected" : ""} onClick={() => { onYearChange(side, year); onMenu({ side, mode:"months" }); }}>{year}</button>)}</div></>}</div>}</div><div className="leadgen-week-picker__weekdays">{WEEKDAYS.map((name) => <span key={name}>{name}</span>)}</div><div className="leadgen-week-picker__days">{days.map((day) => {
    const iso = toIso(day); const week = toIso(monday(day)); const outside = day.getMonth() !== value.getMonth();
    const disabled = week < minimum || week > maximum; const selected = preview?.start && iso >= preview.start && iso <= selectedEnd;
    return <button type="button" key={iso} disabled={disabled} className={`${outside ? "is-outside " : ""}${selected ? "is-in-range " : ""}${iso === preview?.start ? "is-start " : ""}${iso === selectedEnd ? "is-end" : ""}`.trim()} onMouseEnter={() => !disabled && onHover(week)} onFocus={() => !disabled && onHover(week)} onClick={() => onSelect(week)}><span>{day.getDate()}</span></button>;
  })}</div></section>;
}

export function LeadGenerationWeekRangePicker({ start, end, onChange, resetRange, minWeek = "2024-12-30" }) {
  const root = useRef(null); const initial = useMemo(() => initialMonths(start, end), [start, end]);
  const maximum = toIso(currentMonday());
  const [open, setOpen] = useState(false); const [draft, setDraft] = useState({ start, end });
  const [anchor, setAnchor] = useState(""); const [hover, setHover] = useState("");
  const [leftMonth, setLeftMonth] = useState(initial.left); const [rightMonth, setRightMonth] = useState(initial.right);
  const [calendarMenu, setCalendarMenu] = useState(null);
  const preview = useMemo(() => {
    if (!anchor || !hover) return draft;
    return anchor <= hover ? { start: anchor, end: hover } : { start: hover, end: anchor };
  }, [anchor, draft, hover]);

  const openPicker = () => { const months = initialMonths(start, end); setDraft({ start, end }); setAnchor(""); setHover(""); setCalendarMenu(null); setLeftMonth(months.left); setRightMonth(months.right); setOpen(true); };
  const select = (week) => { setCalendarMenu(null); if (!anchor) { setAnchor(week); setHover(week); setDraft({ start: week, end: week }); return; } const next = anchor <= week ? { start: anchor, end: week } : { start: week, end: anchor }; setDraft(next); setAnchor(""); setHover(""); setOpen(false); onChange(next); };
  const reset = () => { const next = resetRange || { start: minWeek, end: maximum }; setDraft(next); setAnchor(""); setHover(""); setCalendarMenu(null); setOpen(false); onChange(next); };
  const move = (amount) => { setCalendarMenu(null); setLeftMonth((old) => addMonths(old, amount)); setRightMonth((old) => addMonths(old, amount)); };
  const setVisibleMonth = (side, value) => { const next = monthStart(value); if (side === "left") { setLeftMonth(next); if (monthIndex(next) >= monthIndex(rightMonth)) setRightMonth(addMonths(next, 1)); } else { setRightMonth(next); if (monthIndex(next) <= monthIndex(leftMonth)) setLeftMonth(addMonths(next, -1)); } setCalendarMenu(null); };
  const selectVisibleMonth = (side, month) => setVisibleMonth(side, localDate(side === "left" ? leftMonth.getFullYear() : rightMonth.getFullYear(), month, 1));
  const selectVisibleYear = (side, year) => { const boundedYear = Math.max(2024, Math.min(new Date().getFullYear(), Number(year))); setVisibleMonth(side, localDate(boundedYear, side === "left" ? leftMonth.getMonth() : rightMonth.getMonth(), 1)); };

  useEffect(() => { if (!open) return undefined; const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false); }; const escape = (event) => { if (event.key === "Escape") setOpen(false); }; document.addEventListener("mousedown", outside); document.addEventListener("keydown", escape); return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", escape); }; }, [open]);

  const count = weekCount(draft);
  return <div className={`leadgen-week-picker${open ? " is-open" : ""}`} ref={root}><label>Период (полные недели)</label><button type="button" className="leadgen-week-picker__control" onClick={() => open ? setOpen(false) : openPicker()}><span>{rangeText({ start, end })}</span><CalendarIcon /></button>{open && <div className="leadgen-week-picker__popover"><div className="leadgen-week-picker__calendars"><button type="button" className="leadgen-week-picker__nav is-previous" onClick={() => move(-1)} aria-label="Предыдущие месяцы">‹</button><Month value={leftMonth} side="left" menu={calendarMenu} onMenu={setCalendarMenu} onMonthChange={selectVisibleMonth} onYearChange={selectVisibleYear} preview={preview} minimum={minWeek} maximum={maximum} onHover={setHover} onSelect={select} /><Month value={rightMonth} side="right" menu={calendarMenu} onMenu={setCalendarMenu} onMonthChange={selectVisibleMonth} onYearChange={selectVisibleYear} preview={preview} minimum={minWeek} maximum={maximum} onHover={setHover} onSelect={select} /><button type="button" className="leadgen-week-picker__nav is-next" onClick={() => move(1)} aria-label="Следующие месяцы">›</button></div><footer><CalendarIcon /><p><strong>Выбрано: {rangeText(draft)} ({count} {weekLabel(count)})</strong><span>Можно выбрать только полные недели (с понедельника по воскресенье).</span></p><button type="button" className="leadgen-week-picker__reset" onClick={reset}><ResetIcon />Сбросить</button></footer></div>}</div>;
}
