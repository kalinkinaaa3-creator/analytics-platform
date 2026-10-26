import { fmtPct, fmtMoney } from "./archiveFormat";


export function PriceLadder({ region, preview }) {
  const prices = preview?.prices || region.effective;
  const gross = preview?.gross || region.effective_gross;
  return <div className="sm-iprice-table"><div className="ip-ladder" role="table" aria-label="Цены по ступеням">
    <div className="h" role="columnheader">Покупатель</div><div className="h r" role="columnheader">Сейчас</div><div className="h r" role="columnheader">По расчёту</div><div className="h r" role="columnheader">{preview ? "Станет" : "Новая"}</div>
    {[["rrp", "Розница"], ["small", "Мелкий опт"], ["medium", "Средний опт"], ["large", "Крупный опт"]].map(([key, label]) => <div key={key} style={{ display: "contents" }} role="row">
      <div role="cell" className={key === "rrp" ? "base" : ""}>{label}{key !== "rrp" && region[`discount_${key}`] != null && <span className="disc">скидка {fmtPct(region[`discount_${key}`])}</span>}</div>
      <div role="cell" className={`r ${key === "rrp" ? "base" : ""}`}>{fmtMoney(region[key === "rrp" ? "current_retail" : `current_${key}`])}</div>
      <div role="cell" className={`r ${key === "rrp" ? "base" : ""}`}>{fmtMoney(region[`calculated_${key}`])}</div>
      <div role="cell" className={`r ${key === "rrp" ? "base" : ""}`}><b>{fmtMoney(prices?.[key])}</b><span className="disc">{fmtMoney(gross?.[key])} с НДС 22%</span></div>
    </div>)}
  </div></div>;
}
