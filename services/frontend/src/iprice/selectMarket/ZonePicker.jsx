import { usePriceZones, zoneHint } from "./priceZonesContext";
const marketZones = {
  below_market: "Ниже рынка", in_market: "В рынке", above_market: "Выше рынка",
  critical_above: "Критически выше рынка", no_market_data: "Нет данных рынка",
};

export function ZonePicker({ value, onChange }) {
  const { config } = usePriceZones();
  const selected = value ? value.split(",") : [];
  return <div className="ip-row" role="group" aria-label="Ценовая зона">
    <span className="small muted">К рынку:</span>
    {[["", "Все зоны"], ...Object.entries(marketZones)].map(([key, label]) =>
      <button key={key} type="button" className={`ip-chip${key ? selected.includes(key) ? " on" : "" : !selected.length ? " on" : ""}`} aria-pressed={key ? selected.includes(key) : !selected.length} onClick={() => onChange(!key ? "" : (selected.includes(key) ? selected.filter(v => v !== key) : [...selected, key]).join(","))} aria-label={label} title={zoneHint(key, config)}>{key && <span style={{ width: 9, height: 9, borderRadius: 2, background: { below_market: "#5b8ec7", in_market: "#2e7d5b", above_market: "#f39f63", critical_above: "#b23b3b", no_market_data: "#c3ccd6" }[key] }} />}{label}{key && config && key !== "no_market_data" && <span className="quiet small">{zoneHint(key, config)}</span>}</button>)}
  </div>;
}
