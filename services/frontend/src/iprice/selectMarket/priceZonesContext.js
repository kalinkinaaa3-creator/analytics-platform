import { createContext, useContext } from "react";
export const PriceZonesContext = createContext({ config: null, error: "" });
const pct = value => Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 4 });
export function usePriceZones() { return useContext(PriceZonesContext); }

export function zoneHint(key, config) {
  if (!config) return "";
  const below = pct(Number(config.below_market_threshold) * 100);
  const above = pct(Number(config.above_market_threshold) * 100);
  const critical = pct(Number(config.critical_threshold) * 100);
  return { below_market: `меньше ${below}%`, in_market: `от ${below}% до +${above}%`, above_market: `выше +${above}% до +${critical}%`, critical_above: `выше +${critical}%`, no_market_data: "нет пригодной цены для сравнения" }[key] || "";
}

