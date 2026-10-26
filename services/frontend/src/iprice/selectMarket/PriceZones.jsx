import { fmtPct } from "./archiveFormat";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button, Panel } from "./ui/primitives";
import Icon from "./ui/Icon";
import { errorText } from "./format";

import { PriceZonesContext as Context, usePriceZones } from "./priceZonesContext";
const fields = [["below_market_threshold", "Синий: дешевле рынка, разница меньше"], ["above_market_threshold", "Оранжевый: дороже рынка, разница больше"], ["critical_threshold", "Красный: риск, разница больше"]];
const number = value => value.trim() === "" ? NaN : Number(value.replace(",", "."));

export function PriceZonesProvider({ children }) {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get('/v1/select-market/iprice/price-zones/', { signal: controller.signal })
      .then(r => { setConfig(r.data); setError(""); })
      .catch(e => { if (e.code !== "ERR_CANCELED") setError("Не удалось загрузить пороги цветов."); });
    return () => controller.abort();
  }, []);
  return <Context.Provider value={{ config, setConfig, error }}>{children}</Context.Provider>;
}

export function ZoneSettings({ canEdit, onSaved }) {
  const { config, error } = usePriceZones();
  return <details className="ip-advanced"><summary><Icon name="settings" size={16} />Пороги цветов{config && <span className="small muted">Синий: ниже {fmtPct(config.below_market_threshold)} · зелёный: до {fmtPct(config.above_market_threshold, { sign: true })} · красный: выше {fmtPct(config.critical_threshold, { sign: true })}</span>}</summary>
    {error && <p role="alert">{error}</p>}
    {config ? <ZoneForm key={JSON.stringify(config)} config={config} canEdit={canEdit} onSaved={onSaved} /> : !error && <p role="status">Загружаем пороги…</p>}
  </details>;
}

function ZoneForm({ config, canEdit, onSaved }) {
  const { setConfig } = usePriceZones();
  const [form, setForm] = useState(() => Object.fromEntries(fields.map(([key]) => [key, String(Number(config[key]) * 100)])));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const errors = {};
  fields.forEach(([key]) => { if (!Number.isFinite(number(form[key]))) errors[key] = "Введите число."; });
  if (number(form.below_market_threshold) < -100 || number(form.below_market_threshold) > 0) errors.below_market_threshold = "Допустимо от −100 до 0%.";
  if (number(form.above_market_threshold) < 0) errors.above_market_threshold = "Порог не может быть отрицательным.";
  if (number(form.critical_threshold) <= number(form.above_market_threshold)) errors.critical_threshold = "Красный порог должен превышать оранжевый.";
  async function save(event) {
    event.preventDefault();
    if (busy || !canEdit || Object.keys(errors).length) return;
    setBusy(true); setMessage("");
    try {
      const payload = Object.fromEntries(fields.map(([key]) => [key, (number(form[key]) / 100).toFixed(6)]));
      const { data } = await api.post('/v1/select-market/iprice/price-zones/', payload);
      setConfig(data); onSaved();
    } catch (e) { setMessage(errorText(e, "Пороги не сохранились.")); }
    finally { setBusy(false); }
  }
  return <Panel title="Пороги цветов" sub="Разница с ценой конкурентов, при которой меняется цвет метки. Цены не пересчитываются.">
    <form className="ip-stack sm-panel-body" onSubmit={save}><div className="ip-grid k3">{fields.map(([key, label]) => <label className="ip-field" key={key}>{label}<div className="ip-affix"><input className="ip-input num" aria-label={label} inputMode="decimal" disabled={!canEdit || busy} value={form[key]} aria-invalid={!!errors[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /><span className="suf">%</span></div>{errors[key] && <span className="small" role="alert">{errors[key]}</span>}</label>)}</div>
      <div className="ip-row small muted"><div className="ip-bar" style={{ width: 240 }}>{["#5b8ec7", "#2e7d5b", "#f39f63", "#b23b3b"].map(color => <span key={color} style={{ width: "25%", background: color }} />)}</div><span>Зелёный: от {form.below_market_threshold}% до +{form.above_market_threshold}%.</span></div>
      {message && <p role="alert">{message}</p>}{canEdit ? <div className="ip-row" style={{ justifyContent: "flex-end" }}><Button type="submit" variant="primary" disabled={busy || !!Object.keys(errors).length}>{busy ? "Сохраняем…" : "Сохранить пороги"}</Button></div> : <p className="small muted">Пороги меняют сотрудники с правом редактирования.</p>}
    </form>
  </Panel>;
}
