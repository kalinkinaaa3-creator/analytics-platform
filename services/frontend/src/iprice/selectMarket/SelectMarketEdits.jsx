import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { Corridor } from "./Corridor";
import { priceText, errorText } from "./format";
import { SelectMarketFilters } from "./SelectMarketFilters";

const root = "/v1/select-market/iprice/snapshots/";

export function PriceEditor({ snapshotId, row, onSaved }) {
  const [price, setPrice] = useState(row.effective.rrp ?? "");
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  async function save(event) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      await api.post(`${root}${snapshotId}/rows/${row.id}/approval/`, {
        approved_rrp: price, comment, expected_revision: row.last_approval_revision ?? row.effective.approval_revision ?? 0,
      });
      onSaved();
    } catch (err) { setError(errorText(err)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <form onSubmit={save} className="sm-iprice-editor">
    <Corridor region={{ ...row, effective_approved_rrp: row.effective.rrp }} preview={price} />
    <p>Нижняя граница: {priceText(row.minimum_price)} · Рынок: {priceText(row.regional_competitor_rrp_median)} руб. без НДС</p>
    <label>Своя РРЦ без НДС, целые рубли<input type="number" min="1" step="1" required value={price} onChange={e => setPrice(e.target.value)} disabled={busy} /></label>
    {price !== "" && row.minimum_price != null && Number(price) < Number(row.minimum_price) && <p role="status">Цена ниже расчётной нижней границы. Проверьте маржинальность.</p>}
    <label>Причина<input required maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} disabled={busy} /></label>
    <p>Оптовые цены пересчитаются по скидкам этой строки. Утверждение всей версии выполняется отдельно.</p>
    <button className="sm-iprice-primary" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить цену"}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

const fields = [
  ["coefficients", "base_analog", "Коэффициент аналога"],
  ["coefficients", "base_exclusive", "Маржа эксклюзива (доля)"],
  ["coefficients", "minimum_margin", "Минимальная маржа (доля)"],
  ["discounts", "small", "Скидка малого опта"], ["discounts", "medium", "Скидка среднего опта"], ["discounts", "large", "Скидка крупного опта"],
];
export function ParameterEditor({ snapshotId, onSaved, row = null }) {
  const [filters, setFilters] = useState({ code_1c: row?.snapshot_product__code_1c || "", sale_region: row?.sale_region || "" });
  const [groupFilters, setGroupFilters] = useState({});
  const [deliveryMode, setDeliveryMode] = useState("");
  const [deliveryCost, setDeliveryCost] = useState("");
  const [values, setValues] = useState({});
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  async function submit(apply) {
    if (pending.current || (apply && !preview)) return;
    pending.current = true; setBusy(true); setError("");
    const payload = { filters: { ...groupFilters }, coefficients: {}, discounts: {}, preview: !apply };
    if (deliveryMode !== "" || deliveryCost !== "") {
      payload.delivery = {};
      if (deliveryMode !== "") payload.delivery.include_transport = deliveryMode === "on";
      if (deliveryCost !== "") payload.delivery.logistics_unit = deliveryCost;
    }
    Object.entries(filters).forEach(([key, value]) => { if (value.trim()) payload.filters[key] = [value.trim()]; });
    fields.forEach(([group, key]) => { if (values[key]) payload[group][key] = values[key]; });
    if (apply) payload.expected_revision = preview.edit_revision;
    try {
      const { data } = await api.post(`${root}${snapshotId}/parameters/`, payload);
      if (apply) { setPreview(null); onSaved(); } else setPreview(data);
    } catch (err) { setPreview(null); setError(errorText(err)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <details className="sm-iprice-editor"><summary>{row ? "Параметры позиции и доставка" : "Изменить параметры выбранных товаров"}</summary>
    <p>Фильтры применяются совместно по точному значению. Заполните хотя бы один. Пустые параметры сохраняют прежние значения. Скидки задаются долями: 0,15 = 15%.</p>
    <div className="sm-iprice-sources">{[["code_1c", "Код 1С"], ["sale_region", "Регион"]].map(([key, title]) => <label key={key}>{title}<input disabled={busy || !!row} value={filters[key]} onChange={e => { setFilters({ ...filters, [key]: e.target.value }); setPreview(null); }} /></label>)}</div>
    {!row && <fieldset disabled={busy} className="sm-iprice-fieldset"><SelectMarketFilters snapshotId={snapshotId} search="" filters={groupFilters} onChange={value => { setGroupFilters(value); setPreview(null); }} /></fieldset>}
    {row && <p>Транспортные расходы: {row.include_transport ? "учитываются" : "не учитываются"}. Введено на единицу: {priceText(row.entered_logistics_unit)} руб. без НДС.</p>}
    <label>Учитывать транспортные расходы<select aria-label="Учитывать транспортные расходы" disabled={busy} value={deliveryMode} onChange={e => { setDeliveryMode(e.target.value); setPreview(null); }}><option value="">Не изменять</option><option value="off">Нет</option><option value="on">Да</option></select></label>
    <label>Доставка на единицу, руб. без НДС<input type="number" min="0" step="0.01" disabled={busy} value={deliveryCost} onChange={e => { setDeliveryCost(e.target.value); setPreview(null); }} placeholder="Не изменять" /></label>
    <div className="sm-iprice-sources">{fields.map(([, key, title]) => <label key={key}>{title}<input type="number" step="0.000001" disabled={busy} value={values[key] || ""} onChange={e => { setValues({ ...values, [key]: e.target.value }); setPreview(null); }} /></label>)}</div>
    <button disabled={busy} onClick={() => submit(false)}>Проверить выбор</button>
    {preview && <p>Товаров: {preview.affected.products}, региональных строк: {preview.affected.regions}. <button className="sm-iprice-primary" disabled={busy || !preview.affected.regions} onClick={() => submit(true)}>Применить и пересчитать</button></p>}
    <p>Параметры сохраняются для следующих расчётов. Текущий расчёт пересчитывается; прежние ручные цены остаются в истории и требуют повторного согласования.</p>
    {error && <p role="alert">{error}</p>}
  </details>;
}

export function SnapshotHistory({ snapshotId }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/history/`, { params: { page }, signal: controller.signal }).then(r => { setData(r.data); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить историю."); });
    return () => controller.abort();
  }, [snapshotId, page]);
  return <details><summary>История версии</summary>
    {error && <p role="alert">{error}</p>}
    {data && <>
      <h3>Утверждения версии</h3>
      {!data.activations.length && <p>Версия ещё не утверждалась.</p>}
      {data.activations.map((item, i) => <p key={i}>{new Date(item.at).toLocaleString("ru-RU")} · {item.username || "Система"} · {item.action === "deactivate" ? "Утверждение снято" : "Версия утверждена"} · предыдущие версии: {item.previous_snapshot_ids.join(", ") || "—"}</p>)}
      <h3>Корректировки цен</h3>
      {data.approvals.map(item => <p key={item.id}>{item.snapshot_region__snapshot_product__code_1c} · {item.snapshot_region__sale_region} · {priceText(item.approved_rrp)} руб. · {item.approved_by__username || "Система"} · {new Date(item.approved_at).toLocaleString("ru-RU")} · {item.comment}{item.is_current ? " (текущая)" : ""}</p>)}
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>Назад</button> {page} / {data.pages} <button disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Далее</button>
      <h3>Последние 50 изменений параметров</h3>
      {data.parameter_changes.map(item => <p key={item.id}>{new Date(item.created_at).toLocaleString("ru-RU")} · {item.user__username} · {item.status} · {JSON.stringify(item.changes)}</p>)}
    </>}
  </details>;
}
