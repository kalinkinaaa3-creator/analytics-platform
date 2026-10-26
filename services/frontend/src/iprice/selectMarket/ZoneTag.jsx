import { fmtPct } from "./archiveFormat";
import Icon from "./ui/Icon";
import { usePriceZones, zoneHint } from "./priceZonesContext";
const zones = {
  below_market: ["below", "Дешевле рынка", "Дешевле", "down"],
  in_market: ["market", "На уровне рынка", "На уровне", "approx"],
  above_market: ["above", "Дороже рынка", "Дороже", "up"],
  critical_above: ["critical", "Дороже рынка, риск", "Дороже", "alert"],
  no_market_data: ["none", "Нет цен конкурентов", "Нет данных", "minus"],
};

export function ZoneTag({ zone, percent }) {
  const { config } = usePriceZones();
  const [tone, label, short, icon] = zones[zone] || zones.no_market_data;
  const text = tone === "none" || percent == null ? label : tone === "market"
    ? `${label} ${fmtPct(percent, { percent: true, sign: true })}`
    : `${short} на ${fmtPct(Math.abs(percent), { percent: true })}`;
  return <span className={`ip-tag z-${tone}`} title={zoneHint(zone, config)}><Icon name={icon} size={12} />{text}</span>;
}
