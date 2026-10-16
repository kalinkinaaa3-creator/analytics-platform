// Форматы значений по дизайн-системе: неразрывный пробел в разрядах,
// запятая, минус U+2212, пробел перед знаком процента.

const MINUS = "−";
const NBSP = "\u00a0";

export function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(String(value).replace(/[\s\u00a0\u202f]/g, "").replace(",", ".").replace("\u2212", "-"));
  return Number.isFinite(n) ? n : null;
}

function fix(text) {
  return text.replace(/\u202f/g, NBSP).replace(/-/g, MINUS);
}

export function fmtNumber(value, digits = 0) {
  const n = toNumber(value);
  if (n === null) return "—";
  return fix(n.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
}

export function fmtMoney(value, { digits = 2, unit = true } = {}) {
  const n = toNumber(value);
  if (n === null) return "—";
  return fmtNumber(n, digits) + (unit ? `${NBSP}₽` : "");
}

export function fmtMoneyDelta(value, digits = 2) {
  const n = toNumber(value);
  if (n === null) return "—";
  const sign = n > 0 ? "+" : "";
  return sign + fmtMoney(n, { digits });
}

// Доли (0.034) -> «3,4 %». Если значение уже в процентах, передайте { percent: true }.
export function fmtPct(value, { digits = 1, sign = false, percent = false } = {}) {
  const n = toNumber(value);
  if (n === null) return "—";
  const p = percent ? n : n * 100;
  const s = sign && p > 0 ? "+" : "";
  return `${s}${fmtNumber(p, digits)}${NBSP}%`;
}

export function fmtPp(value, digits = 1) {
  const n = toNumber(value);
  if (n === null) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${fmtNumber(n * 100, digits)}${NBSP}п.${NBSP}п.`;
}

export function fmtDate(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("ru-RU");
}

export function fmtDateTime(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return `${d.toLocaleDateString("ru-RU")}, ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

export function fmtRelative(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.round(diff / 60)} мин назад`;
  const today = new Date();
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `сегодня в ${time}`;
  const y = new Date(today); y.setDate(today.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return `вчера в ${time}`;
  return fmtDateTime(d);
}

export function plural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}

export function countText(n, one, few, many) {
  return `${fmtNumber(n)}${NBSP}${plural(Number(n) || 0, one, few, many)}`;
}

export function todayISO() {
  const d = new Date();
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// Деление с защитой: (a − b) / b
export function deviation(a, b) {
  const x = toNumber(a);
  const y = toNumber(b);
  if (x === null || y === null || y === 0) return null;
  return (x - y) / y;
}

export function margin(price, cost) {
  const p = toNumber(price);
  const c = toNumber(cost);
  if (p === null || c === null || p === 0) return null;
  return (p - c) / p;
}
