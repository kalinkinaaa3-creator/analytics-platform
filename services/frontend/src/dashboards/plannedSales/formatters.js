export function formatInt(value) {
  if (value === null || value === undefined || value === "") return "0";

  const number = Math.round(Number(value) || 0);

  return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export function unformatNumber(value) {
  if (!value) return "";
  return value.toString().replace(/\s/g, "").replace(",", ".");
}

export function normalizeValue(value) {
  if (value === null || value === undefined || value === "") return 0;

  const number = parseFloat(unformatNumber(value));
  return Number.isNaN(number) ? 0 : number;
}