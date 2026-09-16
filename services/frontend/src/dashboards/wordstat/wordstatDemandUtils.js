export const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const COLORS = ["#536f50", "#73869a", "#b98a3e", "#765f8e", "#3f8a88"];
export const TONES = { growth: "#536f50", decline: "#aa584b", stable: "#89939c", new: "#b98a3e", missing: "#89939c" };
export const LEVELS = [["feature", "Категории"], ["category", "Подкатегории"], ["phrase", "Запросы"]];
export const number = (v, digits = 0) => v == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(v);
export const signed = (v, digits = 1) => {
  if (v == null) return "—";
  const rounded = Math.round(v * 10 ** digits) / 10 ** digits || 0;
  return `${rounded > 0 ? "+" : ""}${number(rounded, digits)}`;
};
export const percent = (v) => v == null ? "—" : `${number(v, 1)}%`;
export const growth = (item) => item?.status === "new" ? "Новый" : item?.growth_percent == null ? "Нет сравнения" : `${signed(item.growth_percent)}%`;
export const dateLabel = (v) => v ? v.split("-").reverse().join(".") : "—";
export const monthLabel = (v) => v ? new Date(`${v}-01T12:00:00`).toLocaleDateString("ru-RU", { month: "long", year: "numeric" }) : "—";
export const seriesColor = (index) => COLORS[index] || `hsl(${(index * 137.508) % 360} 43% 43%)`;
export function objectNoun(count, level) {
  const words = { feature: ["категория", "категории", "категорий"], category: ["подкатегория", "подкатегории", "подкатегорий"], phrase: ["запрос", "запроса", "запросов"] }[level];
  const n = Math.abs(count || 0), last = n % 10;
  return words[n % 100 >= 11 && n % 100 <= 14 ? 2 : last === 1 ? 0 : last >= 2 && last <= 4 ? 1 : 2];
}
export function sortedChanges(items, direction, sort) {
  return items.filter((p) => p.status === direction).sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key];
    if (av == null || bv == null) return av == null && bv == null ? a.id.localeCompare(b.id) : av == null ? 1 : -1;
    return (av - bv) * (sort.direction === "asc" ? 1 : -1) || a.id.localeCompare(b.id);
  });
}
export function defaultSeasonIds(items, selectedPhrase) {
  const sorted = [...items].sort((a, b) => (b.growth_percent ?? -Infinity) - (a.growth_percent ?? -Infinity) || (b.absolute_change ?? -Infinity) - (a.absolute_change ?? -Infinity) || a.id.localeCompare(b.id));
  const focused = sorted.find((p) => selectedPhrase && p.phrase === selectedPhrase);
  return (focused ? [focused, ...sorted.filter((p) => p !== focused)] : sorted).slice(0, 3).map((p) => p.id);
}

export function statusDistribution(items = []) {
  const completeTotal = items.length > 0 && items.every((item) => item.current_volume != null);
  const total = completeTotal ? items.reduce((sum, item) => sum + item.current_volume, 0) : null;
  return Object.fromEntries(["growth", "decline", "stable", "new", "missing"].map((status) => {
    const members = items.filter((item) => item.status === status);
    const volume = members.every((item) => item.current_volume != null)
      ? members.reduce((sum, item) => sum + item.current_volume, 0) : null;
    return [status, { count: members.length, share: items.length ? members.length * 100 / items.length : null,
      volume_share: total > 0 && volume != null ? volume * 100 / total : null }];
  }));
}
