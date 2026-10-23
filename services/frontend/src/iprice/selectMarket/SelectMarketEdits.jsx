import { PriceLadder } from "./PriceLadder";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { Corridor } from "./Corridor";
import { priceText, errorText } from "./format";
import { SelectMarketFilters } from "./SelectMarketFilters";
import { Button, Drawer } from "./ui/primitives";
import { useConfirm } from "./ui/useConfirm";

const root = "/v1/select-market/iprice/snapshots/";

export function PriceEditor({ snapshotId, row, onSaved }) {
  const [price, setPrice] = useState(row.effective.rrp ?? "");
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewPrice, setPreviewPrice] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      if (!/^\d+$/.test(String(price)) || Number(price) <= 0) return;
      api.get(`${root}${snapshotId}/rows/${row.id}/approval/`, { params: { price }, signal: controller.signal })
        .then(({ data }) => { setPreviewPrice({ ...data, requested: String(price) }); setError(""); })
        .catch(err => { if (err.code !== "ERR_CANCELED") setError(errorText(err, "Не удалось проверить цену.")); });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [price, row.id, snapshotId]);
  const checked = previewPrice?.requested === String(price) ? previewPrice : null;
  const pending = useRef(false);
  async function save(event) {
    event.preventDefault();
    if (pending.current || !checked?.valid) return;
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
    {checked && <><p>Маржа: {checked.margin == null ? "—" : `${priceText(Number(checked.margin) * 100)}%`}</p>{!checked.valid && <p role="alert">{checked.message}</p>}<PriceLadder region={row} preview={checked} /></>}
    {row.calculated_rrp != null && <Button variant="ghost" disabled={busy} onClick={() => setPrice(String(row.calculated_rrp))}>Вернуть расчёт iPrice</Button>}
    <p>Оптовые цены пересчитаются по скидкам этой строки. Утверждение всей версии выполняется отдельно.</p>
    <button className="sm-iprice-primary" disabled={busy || !checked?.valid}>{busy ? "Сохраняем…" : "Сохранить цену"}</button>
    {error && <p role="alert">{error}</p>}
    <PriceHistory snapshotId={snapshotId} rowId={row.id} />
  </form>;
}

const fields = [
  ["coefficients", "base_analog", "Коэффициент аналога"],
  ["coefficients", "base_exclusive", "Маржа без конкурентов"],
  ["coefficients", "minimum_margin", "Минимальная маржа"],
  ["discounts", "small", "Скидка малого опта"], ["discounts", "medium", "Скидка среднего опта"], ["discounts", "large", "Скидка крупного опта"],
];
export function ParameterEditor({ snapshotId, onSaved, row = null, listScope = null }) {
  const [confirm, confirmation] = useConfirm();
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState({ code_1c: row?.snapshot_product__code_1c || "", sale_region: row?.sale_region || "" });
  const [groupFilters, setGroupFilters] = useState({});
  const [deliveryMode, setDeliveryMode] = useState("");
  const [deliveryCost, setDeliveryCost] = useState("");
  const [values, setValues] = useState({});
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const fieldErrors = {};
  const numeric = value => Number(String(value).trim().replace(",", "."));
  fields.forEach(([, key]) => {
    const text = values[key]?.trim();
    if (!text) return;
    const value = numeric(text);
    if (!/^\d+(?:[.,]\d+)?$/.test(text) || !Number.isFinite(value)) fieldErrors[key] = "Введите положительное число или ноль.";
    else if (key === "base_analog" && value <= 0) fieldErrors[key] = "Коэффициент должен быть больше нуля.";
    else if (key !== "base_analog" && (value < 0 || value >= 100)) fieldErrors[key] = "Допустимо от 0 до значения меньше 100%.";
    else if ((text.split(/[.,]/)[1]?.length || 0) > (key === "base_analog" ? 6 : 4)) fieldErrors[key] = "Слишком много знаков после запятой.";
  });
  const hasChanges = Object.values(values).some(value => value.trim()) || deliveryMode !== "" || deliveryCost !== "";
  async function submit(apply) {
    if (pending.current || Object.keys(fieldErrors).length || (apply && (!preview || !hasChanges))) return;
    if (apply && !await confirm(`Пересчитать ${preview.affected.regions} региональных цен? Ручные цены потребуют повторного согласования.`)) return;
    pending.current = true; setBusy(true); setError("");
    const payload = { filters: { ...groupFilters }, coefficients: {}, discounts: {}, preview: !apply };
    if (listScope) {
      payload.filters = listScope.filters;
      payload.search = listScope.search;
      payload.list_scope = { mode: listScope.mode, zone: listScope.zone, problems_only: listScope.problems_only };
    }
    if (deliveryMode !== "" || deliveryCost !== "") {
      payload.delivery = {};
      if (deliveryMode !== "") payload.delivery.include_transport = deliveryMode === "on";
      if (deliveryCost !== "") payload.delivery.logistics_unit = deliveryCost;
    }
    Object.entries(filters).forEach(([key, value]) => { if (value.trim()) payload.filters[key] = [value.trim()]; });
    fields.forEach(([group, key]) => { if (values[key]?.trim()) payload[group][key] = (numeric(values[key]) / (key === "base_analog" ? 1 : 100)).toFixed(6); });
    if (apply) payload.expected_revision = preview.edit_revision;
    if (apply && listScope) payload.expected_scope = preview.affected.scope_signature;
    try {
      const { data } = await api.post(`${root}${snapshotId}/parameters/`, payload);
      if (apply) { setPreview(null); onSaved(); } else setPreview(data);
    } catch (err) { setPreview(null); setError(errorText(err)); }
    finally { pending.current = false; setBusy(false); }
  }
  const title = row ? "Параметры позиции и доставка" : "Правила для списка";
  return <>{confirmation}<Button variant="ghost" icon="settings" onClick={() => { setPreview(null); setOpen(true); }}>{title}</Button><Drawer open={open} onClose={() => { if (!busy) setOpen(false); }} title={title}><div className="ip-stack sm-iprice-editor">
    <section className="ip-panel pad ip-stack"><div className="ip-section-title">1. Область изменения</div>
    <p>{listScope ? "Изменяются все строки текущего списка, включая другие страницы. Учитываются поиск, фильтры, зоны и замечания." : "Фильтры применяются совместно по точному значению. Заполните хотя бы один."} Пустые параметры сохраняют прежние значения. Маржа и скидки задаются в процентах: 15 означает 15%.</p>
    {!listScope && <div className="sm-iprice-sources">{[["code_1c", "Код 1С"], ["sale_region", "Регион"]].map(([key, title]) => <label key={key}>{title}<input disabled={busy || !!row} value={filters[key]} onChange={e => { setFilters({ ...filters, [key]: e.target.value }); setPreview(null); }} /></label>)}</div>}
    {!row && !listScope && <fieldset disabled={busy} className="sm-iprice-fieldset"><SelectMarketFilters snapshotId={snapshotId} search="" filters={groupFilters} onChange={value => { setGroupFilters(value); setPreview(null); }} /></fieldset>}
    <Button disabled={busy || !!Object.keys(fieldErrors).length} onClick={() => submit(false)}>Проверить выбор</Button>
    {preview && <div className="ip-grid k2">{[["Товаров", preview.affected.products], ["Цен по регионам", preview.affected.regions]].map(([label, count]) => <div key={label} className="ip-kpi"><span className="l">{label}</span><span className="v">{count}</span></div>)}</div>}
    </section><section className="ip-panel pad ip-stack"><div className="ip-section-title">2. Новые значения</div><p className="small muted">Заполните только изменяемые параметры.</p>
    {row && <p>Транспортные расходы: {row.include_transport ? "учитываются" : "не учитываются"}. Введено на единицу: {priceText(row.entered_logistics_unit)} руб. без НДС.</p>}
    <label>Учитывать транспортные расходы<select aria-label="Учитывать транспортные расходы" disabled={busy} value={deliveryMode} onChange={e => { setDeliveryMode(e.target.value); setPreview(null); }}><option value="">Не изменять</option><option value="off">Нет</option><option value="on">Да</option></select></label>
    <label>Доставка на единицу, руб. без НДС<input type="number" min="0" step="0.01" disabled={busy} value={deliveryCost} onChange={e => { setDeliveryCost(e.target.value); setPreview(null); }} placeholder="Не изменять" /></label>
    {["coefficients", "discounts"].map(group => <section className="ip-stack" key={group}>{group === "discounts" && <div className="ip-cap">Скидки от розничной цены для оптовых покупателей</div>}<div className="ip-grid k2">{fields.filter(([g]) => g === group).map(([, key, title]) => <label className="ip-field" key={key}>{title}<div className="ip-affix"><input className="ip-input num" aria-label={title} inputMode="decimal" disabled={busy} value={values[key] || ""} placeholder="Не изменять" aria-invalid={!!fieldErrors[key]} onChange={e => { setValues({ ...values, [key]: e.target.value }); setPreview(null); }} /><span className="suf">{key === "base_analog" ? "×" : "%"}</span></div>{fieldErrors[key] && <span className="small" role="alert">{fieldErrors[key]}</span>}</label>)}</div></section>)}
    </section>
    {preview && <div className="ip-row" style={{ justifyContent: "flex-end" }}><Button disabled={busy} onClick={() => setOpen(false)}>Отмена</Button><Button variant="primary" disabled={busy || !preview.affected.regions || !hasChanges || !!Object.keys(fieldErrors).length} onClick={() => submit(true)}>Применить и пересчитать</Button></div>}
    <p>Параметры сохраняются для следующих расчётов. Текущий расчёт пересчитывается; прежние ручные цены остаются в истории и требуют повторного согласования.</p>
    {error && <p role="alert">{error}</p>}
  </div></Drawer></>;
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

function PriceHistory({ snapshotId, rowId }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/history/`, { params: { row_id: rowId, page }, signal: controller.signal })
      .then(({ data }) => { setResult({ ...data, requestedPage: page }); setError(""); })
      .catch(e => { if (e.code !== "ERR_CANCELED") setError("Не удалось загрузить историю цены."); });
    return () => controller.abort();
  }, [snapshotId, rowId, page]);
  const ready = result?.requestedPage === page;
  return <section className="ip-panel pad ip-stack"><h3>История цены</h3>{error && <p role="alert">{error}</p>}{!ready && !error && <p role="status">Загружаем историю…</p>}{ready && <>{!result.approvals.length && <p className="muted">Ручных изменений пока нет.</p>}{result.approvals.map(item => <div key={item.id}><b>{priceText(item.approved_rrp)} ₽</b><span className="sub">{item.approved_by__username || "Система"} · {new Date(item.approved_at).toLocaleString("ru-RU")}</span><p>{item.comment}</p></div>)}{result.pages > 1 && <div className="ip-row"><Button disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</Button><span>{page} / {result.pages}</span><Button disabled={page >= result.pages} onClick={() => setPage(page + 1)}>Далее</Button></div>}</>}</section>;
}
