import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "./date_range_picker.css";


const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

const MONTHS_SHORT = [
  "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
  "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
];

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];


function localDate(year, month, day) {
  return new Date(year, month, day, 12, 0, 0, 0);
}


function fromIso(value) {
  const [year, month, day] = String(value || "").split("-").map(Number);
  if (!year || !month || !day) return null;
  const result = localDate(year, month - 1, day);
  return result.getFullYear() === year && result.getMonth() === month - 1 && result.getDate() === day ? result : null;
}


function toIso(value) {
  if (!value) return "";
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}


function displayDate(value) {
  const parsed = fromIso(value);
  if (!parsed) return "";
  return `${String(parsed.getDate()).padStart(2, "0")}.${String(parsed.getMonth() + 1).padStart(2, "0")}.${parsed.getFullYear()}`;
}


function parseDisplay(value) {
  const match = String(value || "").trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!match) return "";
  const parsed = localDate(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  return parsed.getFullYear() === Number(match[3]) && parsed.getMonth() === Number(match[2]) - 1 && parsed.getDate() === Number(match[1]) ? toIso(parsed) : "";
}


function maskDisplayDate(value, previousValue = "") {
  if (
    String(value).length < String(previousValue).length
    && String(previousValue).endsWith(".")
    && String(value) === String(previousValue).slice(0, -1)
  ) return String(value);
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  if (digits.length < 2) return digits;
  if (digits.length === 2) return `${digits}.`;
  if (digits.length < 4) return `${digits.slice(0, 2)}.${digits.slice(2)}`;
  if (digits.length === 4) return `${digits.slice(0, 2)}.${digits.slice(2)}.`;
  return `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4)}`;
}


function addDays(value, amount) {
  return localDate(value.getFullYear(), value.getMonth(), value.getDate() + amount);
}


function addMonths(value, amount) {
  return localDate(value.getFullYear(), value.getMonth() + amount, 1);
}


function monthStart(value) {
  return localDate(value.getFullYear(), value.getMonth(), 1);
}


function monthIndex(value) {
  return value.getFullYear() * 12 + value.getMonth();
}


function startOfWeek(value) {
  const weekday = value.getDay() || 7;
  return addDays(value, 1 - weekday);
}


function normalizedRange(start, end) {
  if (!start || !end) return null;
  return start <= end ? { start, end } : { start: end, end: start };
}


function initialCalendarMonths(start, end) {
  const startDate = fromIso(start);
  const endDate = fromIso(end);
  const fallback = monthStart(new Date());

  if (startDate && endDate) {
    const startMonth = monthStart(startDate);
    const endMonth = monthStart(endDate);

    if (monthIndex(startMonth) < monthIndex(endMonth)) return { left: startMonth, right: endMonth };

    if (monthIndex(startMonth) === monthIndex(endMonth)) return { left: addMonths(startMonth, -1), right: startMonth };

    return { left: endMonth, right: startMonth };
  }

  if (endDate) return { left: addMonths(monthStart(endDate), -1), right: monthStart(endDate) };

  if (startDate) return { left: addMonths(monthStart(startDate), -1), right: monthStart(startDate) };

  return { left: addMonths(fallback, -1), right: fallback };
}


function CalendarIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3v3M18 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" /></svg>;
}


function PresetIcon({ list = false, reset = false }) {
  if (reset) return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M19 12a7 7 0 1 1-2-5" /></svg>;
  if (list) return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7h11M8 12h11M8 17h11M4 7h.01M4 12h.01M4 17h.01" /></svg>;
  return <CalendarIcon />;
}


function CalendarMonth({ month, side, start, end, selecting, hover, preserveEnd, menu, onMenu, onMonthChange, onYearChange, onHover, onSelect }) {
  const cells = useMemo(() => {
    const first = localDate(month.getFullYear(), month.getMonth(), 1);
    const gridStart = addDays(first, 1 - (first.getDay() || 7));
    return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
  }, [month]);

  const preview = selecting && hover && !preserveEnd ? normalizedRange(selecting, hover) : normalizedRange(start, end);
  const menuOpen = menu?.side === side;
  const yearMode = menuOpen && menu?.mode === "years";
  const years = useMemo(() => Array.from({ length: 21 }, (_, index) => month.getFullYear() - 10 + index), [month]);

  return <section className="date-range-picker__month"><div className="date-range-picker__month-header"><button type="button" className={`date-range-picker__period-selector${menuOpen ? " is-open" : ""}`} onClick={() => onMenu(menuOpen ? null : { side, mode: "months" })}><span>{MONTHS[month.getMonth()]} {month.getFullYear()}</span><i aria-hidden="true">⌄</i></button>{menuOpen && <div className="date-range-picker__period-menu">{!yearMode ? <><div className="date-range-picker__period-year"><button type="button" aria-label="Предыдущий год" onClick={() => onYearChange(side, month.getFullYear() - 1)}>‹</button><button type="button" className="date-range-picker__period-year-value" onClick={() => onMenu({ side, mode: "years" })}>{month.getFullYear()}<span aria-hidden="true">⌄</span></button><button type="button" aria-label="Следующий год" onClick={() => onYearChange(side, month.getFullYear() + 1)}>›</button></div><div className="date-range-picker__period-months">{MONTHS_SHORT.map((name, index) => <button type="button" key={name} className={index === month.getMonth() ? "is-selected" : ""} onClick={() => onMonthChange(side, index)}>{name}</button>)}</div></> : <><div className="date-range-picker__years-header"><button type="button" onClick={() => onMenu({ side, mode: "months" })}>‹</button><strong>Выберите год</strong><span /></div><div className="date-range-picker__period-years">{years.map((year) => <button type="button" key={year} className={year === month.getFullYear() ? "is-selected" : ""} onClick={() => { onYearChange(side, year); onMenu({ side, mode: "months" }); }}>{year}</button>)}</div></>}</div>}</div><div className="date-range-picker__weekdays">{WEEKDAYS.map((day) => <span key={day}>{day}</span>)}</div><div className="date-range-picker__days">{cells.map((day) => {
    const iso = toIso(day); const outside = day.getMonth() !== month.getMonth(); const isStart = !outside && iso === preview?.start; const isEnd = !outside && iso === preview?.end; const inRange = !outside && preview && iso >= preview.start && iso <= preview.end;
    return <button type="button" key={iso} className={`${outside ? "is-outside " : ""}${inRange ? "is-in-range " : ""}${isStart ? "is-start " : ""}${isEnd ? "is-end" : ""}`.trim()} onMouseEnter={() => onHover(iso)} onFocus={() => onHover(iso)} onClick={() => onSelect(side, iso)} aria-label={displayDate(iso)} aria-pressed={Boolean(inRange)}><span>{day.getDate()}</span></button>;
  })}</div></section>;
}


export function DateRangePicker({ start, end, onChange, label = "Период", resetRange = null }) {
  const root = useRef(null);
  const initialMonths = useMemo(() => initialCalendarMonths(start, end), [start, end]);
  const [open, setOpen] = useState(false);
  const [popoverSide, setPopoverSide] = useState("right");
  const [draft, setDraft] = useState({ start, end });
  const [anchor, setAnchor] = useState("");
  const [hover, setHover] = useState("");
  const [preserveEnd, setPreserveEnd] = useState(false);
  const [startInput, setStartInput] = useState(displayDate(start));
  const [endInput, setEndInput] = useState(displayDate(end));
  const [leftViewMonth, setLeftViewMonth] = useState(initialMonths.left);
  const [rightViewMonth, setRightViewMonth] = useState(initialMonths.right);
  const [calendarMenu, setCalendarMenu] = useState(null);


  const applyRange = useCallback((nextRange, close = true) => {
    const range = normalizedRange(nextRange.start, nextRange.end);
    if (!range) return false;
    setDraft(range); setStartInput(displayDate(range.start)); setEndInput(displayDate(range.end)); setAnchor(""); setHover(""); setPreserveEnd(false); setCalendarMenu(null);
    if (range.start !== start || range.end !== end) onChange(range);
    if (close) setOpen(false);
    return true;
  }, [end, onChange, start]);


  const applyInputs = useCallback((close = true) => {
    const parsedStart = parseDisplay(startInput); const parsedEnd = parseDisplay(endInput);
    if (!parsedStart || !parsedEnd) {
      setStartInput(displayDate(draft.start || start)); setEndInput(displayDate(draft.end || end)); setPreserveEnd(false); setCalendarMenu(null);
      if (close) setOpen(false);
      return false;
    }
    return applyRange({ start: parsedStart, end: parsedEnd }, close);
  }, [applyRange, draft.end, draft.start, end, endInput, start, startInput]);


  const openPicker = () => {
    if (open) return;
    const rootBounds = root.current?.getBoundingClientRect();
    const popoverWidth = window.innerWidth <= 900 ? 720 : 980;
    const edgePadding = window.innerWidth <= 900 ? 22 : 28;
    const spaceRight = rootBounds ? window.innerWidth - rootBounds.left - edgePadding : popoverWidth;
    const spaceLeft = rootBounds ? rootBounds.right - edgePadding : popoverWidth;
    const months = initialCalendarMonths(start, end);
    setPopoverSide(spaceRight >= popoverWidth || spaceRight >= spaceLeft ? "right" : "left");
    setDraft({ start, end }); setStartInput(displayDate(start)); setEndInput(displayDate(end)); setAnchor(""); setHover(""); setPreserveEnd(false); setCalendarMenu(null); setLeftViewMonth(months.left); setRightViewMonth(months.right); setOpen(true);
  };


  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => { if (!root.current?.contains(event.target)) applyInputs(true); };
    const closeOnEscape = (event) => {
      if (event.key === "Escape" && calendarMenu) {
        setCalendarMenu(null);
        return;
      }
      if (event.key === "Escape") {
        setDraft({ start, end }); setStartInput(displayDate(start)); setEndInput(displayDate(end)); setAnchor(""); setHover(""); setPreserveEnd(false); setCalendarMenu(null); setOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOutside); document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("mousedown", closeOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, [applyInputs, calendarMenu, end, open, start]);


  const selectDate = (side, iso) => {
    setCalendarMenu(null);

    const currentStart = draft.start || start;
    const currentEnd = draft.end || end;

    if (side === "left") {
      if (currentEnd && iso <= currentEnd) {
        setAnchor("");
        setHover("");
        setPreserveEnd(false);
        setDraft({ start: iso, end: currentEnd });
        setStartInput(displayDate(iso));
        setEndInput(displayDate(currentEnd));
        return;
      }

      setAnchor(iso);
      setHover(iso);
      setPreserveEnd(false);
      setDraft({ start: iso, end: "" });
      setStartInput(displayDate(iso));
      setEndInput("");
      return;
    }

    if (currentStart && iso >= currentStart) {
      setAnchor("");
      setHover("");
      setPreserveEnd(false);
      setDraft({ start: currentStart, end: iso });
      setStartInput(displayDate(currentStart));
      setEndInput(displayDate(iso));
      return;
    }

    setAnchor(iso);
    setHover(iso);
    setPreserveEnd(false);
    setDraft({ start: "", end: iso });
    setStartInput("");
    setEndInput(displayDate(iso));
  };


  const setVisibleMonth = (side, nextMonth) => {
    if (side === "left") {
      setLeftViewMonth(nextMonth);
      if (monthIndex(nextMonth) >= monthIndex(rightViewMonth)) setRightViewMonth(addMonths(nextMonth, 1));
    } else {
      setRightViewMonth(nextMonth);
      if (monthIndex(nextMonth) <= monthIndex(leftViewMonth)) setLeftViewMonth(addMonths(nextMonth, -1));
    }
  };


  const selectVisibleMonth = (side, selectedMonthIndex) => {
    if (side === "left") {
      const nextMonth = localDate(leftViewMonth.getFullYear(), selectedMonthIndex, 1);
      setVisibleMonth("left", nextMonth);
    } else {
      const nextMonth = localDate(rightViewMonth.getFullYear(), selectedMonthIndex, 1);
      setVisibleMonth("right", nextMonth);
    }
    setCalendarMenu(null);
  };


  const selectVisibleYear = (side, year) => {
    if (side === "left") {
      const nextMonth = localDate(year, leftViewMonth.getMonth(), 1);
      setVisibleMonth("left", nextMonth);
    } else {
      const nextMonth = localDate(year, rightViewMonth.getMonth(), 1);
      setVisibleMonth("right", nextMonth);
    }
  };


  const moveLeftMonth = (amount) => {
    setCalendarMenu(null);
    const nextMonth = addMonths(leftViewMonth, amount);
    setVisibleMonth("left", nextMonth);
  };


  const moveRightMonth = (amount) => {
    setCalendarMenu(null);
    const nextMonth = addMonths(rightViewMonth, amount);
    setVisibleMonth("right", nextMonth);
  };


  const closePeriodMenuOutside = (event) => {
    if (!calendarMenu) return;
    const target = event.target;
    if (target.closest(".date-range-picker__period-selector")) return;
    if (target.closest(".date-range-picker__period-menu")) return;
    setCalendarMenu(null);
  };


  const preset = (kind) => {
    const today = localDate(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
    const monday = startOfWeek(today); let range;
    if (kind === "today") range = { start: toIso(today), end: toIso(today) };
    if (kind === "yesterday") { const yesterday = addDays(today, -1); range = { start: toIso(yesterday), end: toIso(yesterday) }; }
    if (kind === "current-week") range = { start: toIso(monday), end: toIso(today) };
    if (kind === "previous-week") range = { start: toIso(addDays(monday, -7)), end: toIso(addDays(monday, -1)) };
    if (kind === "current-month") range = { start: toIso(localDate(today.getFullYear(), today.getMonth(), 1)), end: toIso(today) };
    if (kind === "previous-month") { const first = localDate(today.getFullYear(), today.getMonth() - 1, 1); range = { start: toIso(first), end: toIso(localDate(today.getFullYear(), today.getMonth(), 0)) }; }
    if (kind === "reset") range = resetRange || { start: toIso(localDate(today.getFullYear(), 0, 1)), end: toIso(today) };
    if (range) applyRange(range);
  };


  const inputKeyDown = (event) => { if (event.key === "Enter") applyInputs(true); if (event.key === "Escape") { setPreserveEnd(false); setCalendarMenu(null); setOpen(false); } };
  const selectedText = draft.start && draft.end ? `${displayDate(draft.start)} — ${displayDate(draft.end)}` : "Выберите период";


  return <div className={`crm-filter date-range-picker${open ? " date-range-picker--open" : ""}`} ref={root}><span>{label}</span><div className="date-range-picker__control" onClick={openPicker}><input value={startInput} maxLength={10} inputMode="numeric" aria-label="Дата начала" onFocus={openPicker} onChange={(event) => setStartInput(maskDisplayDate(event.target.value, startInput))} onKeyDown={inputKeyDown} /><b>—</b><input value={endInput} maxLength={10} inputMode="numeric" aria-label="Дата окончания" onFocus={openPicker} onChange={(event) => setEndInput(maskDisplayDate(event.target.value, endInput))} onKeyDown={inputKeyDown} /><button type="button" aria-label={open ? "Закрыть календарь" : "Открыть календарь"} onClick={(event) => { event.stopPropagation(); if (open) applyInputs(true); else openPicker(); }}><CalendarIcon /></button></div>{open && <div className={`date-range-picker__popover date-range-picker__popover--${popoverSide}`} onMouseDownCapture={closePeriodMenuOutside}><aside className="date-range-picker__presets"><button type="button" onClick={() => preset("today")}><PresetIcon />Сегодня</button><button type="button" onClick={() => preset("yesterday")}><PresetIcon />Вчера</button><button type="button" onClick={() => preset("current-week")}><PresetIcon list />Текущая неделя</button><button type="button" onClick={() => preset("previous-week")}><PresetIcon list />Прошлая неделя</button><button type="button" onClick={() => preset("current-month")}><PresetIcon />Текущий месяц</button><button type="button" onClick={() => preset("previous-month")}><PresetIcon />Прошлый месяц</button><hr /><button type="button" onClick={() => preset("reset")}><PresetIcon reset />Сбросить</button></aside><div className="date-range-picker__calendars"><button type="button" className="date-range-picker__nav date-range-picker__nav--previous" aria-label="Предыдущий месяц" onClick={() => moveLeftMonth(-1)}>‹</button><CalendarMonth month={leftViewMonth} side="left" start={draft.start} end={draft.end} selecting={anchor} hover={hover} preserveEnd={preserveEnd} menu={calendarMenu} onMenu={setCalendarMenu} onMonthChange={selectVisibleMonth} onYearChange={selectVisibleYear} onHover={setHover} onSelect={selectDate} /><CalendarMonth month={rightViewMonth} side="right" start={draft.start} end={draft.end} selecting={anchor} hover={hover} preserveEnd={preserveEnd} menu={calendarMenu} onMenu={setCalendarMenu} onMonthChange={selectVisibleMonth} onYearChange={selectVisibleYear} onHover={setHover} onSelect={selectDate} /><button type="button" className="date-range-picker__nav date-range-picker__nav--next" aria-label="Следующий месяц" onClick={() => moveRightMonth(1)}>›</button></div><footer>Выбрано: <strong>{selectedText}</strong></footer></div>}</div>;
}