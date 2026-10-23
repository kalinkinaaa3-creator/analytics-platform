const zones = {
  below_market: ["below", "Ниже рынка"], in_market: ["market", "В рынке"],
  above_market: ["above", "Выше рынка"], critical_above: ["critical", "Критически выше"],
  no_market_data: ["none", "Нет данных"],
};

export function ZoneTag({ zone, percent }) {
  const [tone, label] = zones[zone] || zones.no_market_data;
  return <span className={`ip-tag z-${tone}`}>{label}{tone !== "none" && percent != null && <> · {percent > 0 ? "+" : ""}{percent.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%</>}</span>;
}
