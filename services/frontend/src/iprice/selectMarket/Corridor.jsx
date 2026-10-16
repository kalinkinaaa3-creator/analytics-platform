// Adapted from user-provided iprice-frontend.zip; no demo/auth dependencies.
import { toNumber, fmtMoney, fmtPct } from "./archiveFormat";


// Коридор цены: себестоимость и нижняя граница задают пол,
// цены конкурентов служат ориентиром, на шкале видны текущая и новая цена.
export function Corridor({ region, preview }) {
  const cost = toNumber(region.cost_with_logistics);
  const floor = toNumber(region.minimum_price);
  const mMin = toNumber(region.regional_competitor_rrp_min);
  const mMax = toNumber(region.regional_competitor_rrp_max);
  const mMed = toNumber(region.regional_competitor_rrp_median);
  const now = toNumber(region.current_retail);
  const next = toNumber(region.effective_approved_rrp);
  const mine = preview === undefined ? null : toNumber(preview);

  const vals = [cost, floor, mMin, mMax, mMed, now, next, mine].filter((v) => v !== null && v > 0);
  if (vals.length < 2) return null;
  const lo = Math.min(...vals) * 0.94;
  const hi = Math.max(...vals) * 1.04;
  const x = (v) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;
  const w = (a, b) => `${((b - a) / (hi - lo)) * 100}%`;

  const marks = [
    now !== null ? { k: "now", v: now, label: "Сейчас в прайсе" } : null,
    next !== null ? { k: "next", v: next, label: mine !== null ? "Новая цена iPrice" : "Новая цена" } : null,
    mine !== null ? { k: "mine", v: mine, label: "Ваша цена" } : null,
  ].filter(Boolean);

  const target = mine ?? next;
  const aboveFloor = target !== null && floor ? (target - floor) / floor : null;
  const vsMarket = target !== null && mMed ? (target - mMed) / mMed : null;

  return (
    <figure className="ip-corr" aria-label="Коридор цены">
      <figcaption className="ip-corr-cap">
        <span>Коридор цены</span>
        {aboveFloor !== null ? (
          <span>
            {mine !== null ? "Ваша цена" : "Новая цена"} {Math.abs(aboveFloor) < 0.0005 ? "на нижней границе" : aboveFloor > 0 ? `выше нижней границы на ${fmtPct(aboveFloor)}` : `ниже нижней границы на ${fmtPct(Math.abs(aboveFloor))}`}
            {vsMarket !== null ? `, ${vsMarket >= 0 ? "дороже" : "дешевле"} середины рынка на ${fmtPct(Math.abs(vsMarket))}` : ", цен конкурентов нет"}.
          </span>
        ) : null}
      </figcaption>
      <div className="ip-corr-track">
        {cost ? <span className="loss" style={{ left: 0, width: x(cost) }} title={`Ниже ${fmtMoney(cost)}: убыток`} /> : null}
        {cost && floor && floor > cost ? <span className="thin" style={{ left: x(cost), width: w(cost, floor) }} title={`От ${fmtMoney(cost)} до ${fmtMoney(floor)}: маржа ниже минимальной`} /> : null}
        {mMin !== null && mMax !== null ? <span className="market" style={{ left: x(mMin), width: w(mMin, Math.max(mMax, mMin * 1.002)) }} title={`Конкуренты: от ${fmtMoney(mMin)} до ${fmtMoney(mMax)}`} /> : null}
        {mMed !== null ? <span className="med" style={{ left: x(mMed) }} title={`Середина рынка ${fmtMoney(mMed)}`} /> : null}
        {floor ? <span className="floor" style={{ left: x(floor) }} title={`Нижняя граница ${fmtMoney(floor)}`} /> : null}
        {marks.map((m) => <span key={m.k} className={`pin ${m.k}`} style={{ left: x(m.v) }} title={`${m.label}: ${fmtMoney(m.v)}`} />)}
      </div>
      {floor && mMax !== null && floor > mMax ? (
        <p className="ip-corr-note">
          Нижняя граница {fmtMoney(floor)} выше самой высокой цены конкурентов {fmtMoney(mMax)}. По цене рынка компания получит маржу ниже минимальной.
          Варианты: снизить себестоимость или доставку, поставить цену выше рынка или убрать товар из региона.
        </p>
      ) : floor && mMed !== null && floor > mMed ? (
        <p className="ip-corr-note">Нижняя граница {fmtMoney(floor)} выше середины рынка: половина конкурентов продаёт дешевле, чем компания может себе позволить.</p>
      ) : null}
      <dl className="ip-corr-legend">
        {cost ? <div><dt><i className="sw loss" />Убыток</dt><dd>ниже {fmtMoney(cost)}</dd></div> : null}
        {floor ? <div><dt><i className="sw floor" /><span>Нижняя граница</span></dt><dd>{fmtMoney(floor)}</dd></div> : null}
        {mMin !== null ? <div><dt><i className="sw market" />Конкуренты</dt><dd>{fmtMoney(mMin)}…{fmtMoney(mMax)}, середина {fmtMoney(mMed)}</dd></div> : null}
        {marks.map((m) => <div key={m.k}><dt><i className={`sw pin-${m.k}`} />{m.label}</dt><dd><b>{fmtMoney(m.v)}</b></dd></div>)}
      </dl>
    </figure>
  );
}
