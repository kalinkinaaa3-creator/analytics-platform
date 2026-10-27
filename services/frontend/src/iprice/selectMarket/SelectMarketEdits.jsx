import { ZoneTag } from "./ZoneTag";
import { fmtPct, fmtMoney, fmtNumber } from "./archiveFormat";
import { Pager } from "./ui/Pager";
import { PriceLadder } from "./PriceLadder";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { Corridor } from "./Corridor";
import { priceText, errorText } from "./format";
import { SelectMarketFilters } from "./SelectMarketFilters";
import { Button, Drawer } from "./ui/primitives";
import { useConfirm } from "./ui/useConfirm";

const root = "/v1/select-market/iprice/snapshots/";

export function PriceEditor({ snapshotId, row: initialRow, onSaved, refreshRevision = 0 }) {
  const [error, setError] = useState("");
  const [currentRow, setCurrentRow] = useState(null);
  const row = currentRow || initialRow;
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${root}${snapshotId}/rows/`, { params: { product_id: initialRow.product_id }, signal: controller.signal }).then(({data}) => {
      const next = data.rows.find(item => item.id === initialRow.id);
      if (next) { setCurrentRow(next); setError(""); }
    }).catch(err => { if (!controller.signal.aborted) setError(errorText(err)); });
    return () => controller.abort();
  }, [snapshotId, initialRow.id, initialRow.product_id, refreshRevision]);
  const [price, setPrice] = useState(row.effective.rrp ?? "");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewPrice, setPreviewPrice] = useState(null);
  const [previewFailure, setPreviewFailure] = useState(null);
  const validInput = /^\d+$/.test(String(price)) && Number(price) > 0;
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      if (!/^\d+$/.test(String(price)) || Number(price) <= 0) return;
      api.get(`${root}${snapshotId}/rows/${row.id}/approval/`, { params: { price }, signal: controller.signal })
        .then(({ data }) => { if (!controller.signal.aborted) { setPreviewPrice({ ...data, requested: String(price) }); setPreviewFailure(null); } })
        .catch(err => { if (!controller.signal.aborted && err.code !== "ERR_CANCELED") setPreviewFailure({ requested: String(price), message: errorText(err, "Не удалось проверить цену.") }); });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [price, row.id, snapshotId]);
  const failure = previewFailure?.requested === String(price) ? previewFailure.message : "";
  const checked = validInput && !failure && previewPrice?.requested === String(price) ? previewPrice : null;
  const previewMessage = !validInput ? "Введите положительную цену целыми рублями." : failure || (checked ? checked.valid ? "" : checked.message : "Обновляем расчёт…");
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
  return <div className="ip-stack">
    <div className="ip-row between"><div className="ip-row"><span className="muted">Новая цена</span><b style={{ fontSize: 20 }}>{fmtMoney(row.effective.rrp)}</b><span className="ip-tag blue">{row.effective.approval_source === "manual" ? "Цена сотрудника" : "Расчёт iPrice"}</span></div><ZoneTag zone={row.zone} percent={Number(row.regional_competitor_rrp_median) > 0 && row.effective.rrp != null ? (Number(row.effective.rrp) / Number(row.regional_competitor_rrp_median) - 1) * 100 : null} /></div>
    <Corridor region={{ ...row, effective_approved_rrp: row.effective.rrp }} preview={previewPrice?.valid ? previewPrice.requested : undefined} />
    <form onSubmit={save} onChangeCapture={() => setError("")} className="ip-panel pad ip-stack sm-iprice-editor">
      <div className="ip-section-title">Своя цена</div>
      <p className="small muted">Введите цену без НДС целыми рублями. iPrice покажет маржу и цены для оптовиков. Утверждение версии выполняется отдельно, отправки в 1С нет.</p>
      <label className="ip-field">Ваша цена *
        <div className="ip-affix"><input className="ip-input num" type="number" min="1" step="1" required value={price} onChange={e => setPrice(e.target.value)} disabled={busy} /><span className="suf">₽</span></div>
        <span className="small muted">Расчёт iPrice: {fmtMoney(row.calculated_rrp)}. Нижняя граница: {fmtMoney(row.minimum_price)}.</span>
      </label>
      <div className="ip-stack" aria-busy={validInput && !checked && !failure}>
        <div className="small muted" role="status" aria-live="polite" style={{ minHeight: 36 }}>
          {previewMessage}{!checked && previewPrice && <span className="sub">Показан предыдущий результат для {fmtMoney(previewPrice.requested)}.</span>}
        </div>
        <p>Маржа: {previewPrice?.margin == null ? "—" : fmtPct(previewPrice.margin)}</p>
        <PriceLadder region={row} preview={previewPrice} />
      </div>
      <label className="ip-field">Причина<textarea aria-label="Причина" className="ip-textarea" required maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} disabled={busy} placeholder="Например: договорились с сетью до конца квартала" /><span className="small muted">Кто согласовал и зачем. Коллеги увидят причину в истории цены.</span></label>
      <div className="ip-row" style={{ justifyContent: "flex-end" }}>
        {row.calculated_rrp != null && Number(row.calculated_rrp) !== Number(row.effective.rrp) && <Button variant="ghost" disabled={busy} onClick={() => { setPrice(String(row.calculated_rrp)); setComment("Возвращена цена по расчёту iPrice."); }}>Вернуть расчёт iPrice</Button>}
        <Button type="submit" variant="accent" icon="check" disabled={busy || !checked?.valid || !comment.trim()}>{busy ? "Сохраняем…" : "Сохранить цену"}</Button>
      </div>{error && <p role="alert">{error}</p>}
    </form>
    <details className="ip-advanced"><summary>Расчёт iPrice по шагам</summary><div className="ip-explain sm-panel-body">{[
      ["Закупочная цена", row.product_cost],
      [row.include_transport ? "Доставка на единицу" : "Доставка не учитывается", row.logistics_unit],
      ["Закупка с доставкой", row.cost_with_logistics],
      ["Цена по правилам компании", row.preliminary_rrp],
      ["Нижняя граница", row.minimum_price],
      ["Цена по расчёту", row.calculated_rrp],
    ].map(([title, value], i) => <div className="st" key={title}><span className="n">{i + 1}</span><span>{title}</span><strong className="v">{fmtMoney(value)}</strong></div>)}</div></details>
    <PriceHistory key={refreshRevision} snapshotId={snapshotId} rowId={row.id} />
  </div>;
}

const fields = [
  ["coefficients", "base_analog", "Коэффициент по рынку"],
  ["coefficients", "base_exclusive", "Маржа по себестоимости"],
  ["coefficients", "minimum_margin", "Минимальная маржа"],
  ["discounts", "small", "Скидка малого опта"], ["discounts", "medium", "Скидка среднего опта"], ["discounts", "large", "Скидка крупного опта"],
];
export function ParameterEditor({ snapshotId, onSaved, row = null, listScope = null, selectionCount = null }) {
  const [confirm, confirmation] = useConfirm();
  const [historyRevision, setHistoryRevision] = useState(0);
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState({ code_1c: row?.snapshot_product__code_1c || "", sale_region: row?.sale_region || "" });
  const [groupFilters, setGroupFilters] = useState({});
  const [deliveryMode, setDeliveryMode] = useState("");
  const [deliveryCost, setDeliveryCost] = useState("");
  const [reason, setReason] = useState("");
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
    if (pending.current || Object.keys(fieldErrors).length || (apply && (!preview || !hasChanges || !reason.trim()))) return;
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
    if (apply) { payload.expected_revision = preview.edit_revision; payload.reason = reason.trim(); }
    if (apply && listScope) payload.expected_scope = preview.affected.scope_signature;
    try {
      const { data } = await api.post(`${root}${snapshotId}/parameters/`, payload);
      if (apply) { setPreview(null); setReason(""); setHistoryRevision(value => value + 1); onSaved(); } else setPreview(data);
    } catch (err) { setPreview(null); setError(errorText(err)); }
    finally { pending.current = false; setBusy(false); }
  }
  const title = "Настройки параметров расчета";
  return <>{confirmation}<Button variant="ghost" icon="settings" onClick={() => { setPreview(null); setError(""); setOpen(true); }}>{title}</Button><Drawer open={open} onClose={() => { if (!busy) setOpen(false); }} title={title}><div className="ip-stack sm-iprice-editor" onChangeCapture={() => setError("")}>
    <section className="ip-panel pad ip-stack"><div className="ip-section-title">1. Область изменения</div>
    <p>{selectionCount ? `Изменяются выбранные товары (${selectionCount}) во всех регионах. Состав будет проверен перед применением.` : listScope ? "Изменяются все строки текущего списка, включая другие страницы. Учитываются поиск, фильтры, зоны и замечания." : "Фильтры применяются совместно по точному значению. Заполните хотя бы один."} Пустые параметры сохраняют прежние значения. Маржа и скидки задаются в процентах: 15 означает 15%.</p>
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
    <label className="ip-field">Причина изменения *<textarea className="ip-textarea" aria-label="Причина изменения" required maxLength={2000} disabled={busy} value={reason} onChange={e => setReason(e.target.value)} placeholder="Укажите, почему меняются цены или параметры расчёта" /><span className="small muted">Обязательна при применении. Сохраняется в истории изменений.</span></label>
    {preview && <div className="ip-row" style={{ justifyContent: "flex-end" }}><Button disabled={busy} onClick={() => setOpen(false)}>Отмена</Button><Button variant="primary" disabled={busy || !preview.affected.regions || !hasChanges || !reason.trim() || !!Object.keys(fieldErrors).length} onClick={() => submit(true)}>Применить и пересчитать</Button></div>}
    <p>Параметры сохраняются для следующих расчётов. Текущий расчёт пересчитывается; прежние ручные цены остаются в истории и требуют повторного согласования.</p>
    {error && <p role="alert">{error}</p>}
    {open && <ParameterHistory key={historyRevision} snapshotId={snapshotId} rowId={row?.id} />}
  </div></Drawer></>;
}

function parameterChangesText(changes = {}) {
  return Object.entries(changes).map(([key, value]) => {
    if (["coefficients", "discounts", "delivery"].includes(key) && value && typeof value === "object") return parameterChangesText(value);
    const label = fields.find(([, field]) => field === key)?.[2] || ({ include_transport: "Учитывать транспортные расходы", logistics_unit: "Доставка на единицу" })[key] || key;
    const text = key === "include_transport" ? value === true ? "Да" : value === false ? "Нет" : "—"
      : key === "logistics_unit" ? `${fmtMoney(value)} без НДС`
      : ["base_exclusive", "minimum_margin", "small", "medium", "large"].includes(key) ? value == null || value === "" || !Number.isFinite(Number(value)) ? "—" : `${Number(Number(value) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 4 })} %`
      : key === "base_analog" ? fmtNumber(value, 2) : value == null ? "—" : String(value).replace(".", ",");
    return `${label}: ${text}`;
  }).filter(Boolean).join("; ");
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
  return <details className="sm-version-history"><summary>История версии</summary>
    {error && <p role="alert">{error}</p>}
    {data && <div className="ip-stack sm-panel-body">
      <h3>Утверждения версии</h3>
      {!data.activations.length && <p>Версия ещё не утверждалась.</p>}
      {data.activations.map((item, i) => <p key={i}>{new Date(item.at).toLocaleString("ru-RU")} · {item.username || "Система"} · {item.action === "deactivate" ? "Утверждение снято" : "Версия утверждена"} · предыдущие версии: {item.previous_snapshot_ids.join(", ") || "—"}</p>)}
      <h3>Корректировки цен</h3>{!data.approvals.length && <p className="muted">Ручных корректировок нет.</p>}
      {data.approvals.map(item => <p key={item.id}>{item.snapshot_region__snapshot_product__code_1c} · {item.snapshot_region__sale_region} · {priceText(item.approved_rrp)} руб. · {item.approved_by__username || "Система"} · {new Date(item.approved_at).toLocaleString("ru-RU")} · {item.comment}{item.is_current ? " (текущая)" : ""}</p>)}
      <Pager page={page} totalPages={data.pages} count={data.count} pageSize={50} onPage={setPage} />
      <h3>Последние 50 изменений параметров</h3>{!data.parameter_changes.length && <p className="muted">Параметры не изменялись.</p>}
      {data.parameter_changes.map(item => <div className="ip-panel pad ip-stack" key={item.id}><div className="ip-row"><span className={`ip-tag ${item.status === "success" ? "green" : item.status === "error" ? "red" : "gray"}`}>{({ success: "Применено", error: "Ошибка", pending: "Ожидает применения" })[item.status] || "Неизвестный статус"}</span><span className="small muted">{new Date(item.created_at).toLocaleString("ru-RU")} · {item.user__username || "Система"}</span></div><span>{parameterChangesText(item.changes) || "Нет изменённых параметров"}</span>{item.reason && <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>Причина: {item.reason}</p>}</div>)}
    </div>}
  </details>;
}

function PriceHistory({ snapshotId, rowId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(root + snapshotId + "/history/", { params: { row_id: rowId, page: 1 }, signal: controller.signal })
      .then(({data}) => { setResult(data); setError(""); })
      .catch(() => { if (!controller.signal.aborted) setError("Не удалось загрузить историю цены."); });
    return () => controller.abort();
  }, [snapshotId, rowId]);
  return <section className="ip-panel pad"><h3>История цены</h3><p className="small muted">Последние 50 изменений</p>{error && <p role="alert">{error}</p>}{!result && !error && <p role="status" className="sm-iprice-loading">Загружаем историю…</p>}{result && <>{!result.approvals.length && <p className="muted">Ручных изменений пока нет.</p>}{result.approvals.slice(0,50).map(item => <article className="sm-history-entry" key={item.id}><b>{fmtMoney(item.approved_rrp)}</b><div className="sm-history-meta"><span>{item.approved_by__username || "Система"}</span><time>{new Date(item.approved_at).toLocaleString("ru-RU")}</time></div><p>{item.comment}</p></article>)}</>}</section>;
}

function ParameterHistory({ snapshotId, rowId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(root + snapshotId + "/history/", { params: { parameter_row_id: rowId }, signal: controller.signal })
      .then(({data}) => { setData(data); setError(""); })
      .catch(() => { if (!controller.signal.aborted) setError("Не удалось загрузить историю параметров."); });
    return () => controller.abort();
  }, [snapshotId, rowId]);
  return <section className="ip-panel pad"><h3>История изменений параметров</h3><p className="small muted">Последние 50 изменений</p>{error && <p role="alert">{error}</p>}{!data && !error && <p role="status" className="sm-iprice-loading">Загружаем историю…</p>}{data && <>{!data.parameter_changes.length && <p className="muted">Параметры не изменялись.</p>}{data.parameter_changes.slice(0,50).map(item => <article className="sm-history-entry" key={item.id}><div className="ip-row"><span className="ip-tag gray">{({success:"Применено",error:"Ошибка",pending:"Ожидает применения"})[item.status]}</span><span className="small muted">Товаров: {item.affected?.products ?? "—"} · регионов: {item.affected?.regions ?? "—"}</span></div><div className="sm-history-meta"><span>{item.user__username || "Система"}</span><time>{new Date(item.created_at).toLocaleString("ru-RU")}</time></div><p>{parameterChangesText(item.changes)}</p>{item.reason && <p>{item.reason}</p>}</article>)}</>}</section>;
}
