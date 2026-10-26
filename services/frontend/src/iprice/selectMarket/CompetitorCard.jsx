import { ProductImage } from "./ProductImage";
import { fmtMoney } from "./archiveFormat";
import { getIPriceCompetitorSourceLabel, getIPriceCompetitorPriceProperties } from "../product/ipriceProductLabels";
import { useState } from "react";
import { Button, Modal } from "./ui/primitives";
import Icon from "./ui/Icon";
import { errorText } from "./format";
import { saveCompetitorSelection } from "./competitorSelection";

export function CompetitorCard({ card, editable, onChangeMode }) {
  const mode = card.selection_mode || "auto";
  const properties = getIPriceCompetitorPriceProperties(card.source, card.price_variants || card.variants);
  return <article className={`ip-card sm-competitor-card ${editable ? "" : "sm-competitor-card-readonly"} ${mode === "exclude" ? "excluded" : mode === "include" ? "included" : ""}`}>
    <div className="ip-card-top"><div className="ip-thumb"><ProductImage src={card.image} name={card.name} /></div><div style={{ minWidth: 0, flex: 1 }}><div className="ip-row"><span className="ip-tag outline">{getIPriceCompetitorSourceLabel(card.source)}</span><span className={`ip-tag ${card.is_used_in_snapshot ? "blue" : "gray"}`}>{card.is_used_in_snapshot ? "Учтён в расчёте" : "Не учтён"}</span></div><h3 className="ip-card-title">{card.name || `Товар ${card.product_key}`}</h3></div></div>
    <div className="ip-row between"><span className="price">{fmtMoney(card.price)}</span>{/^https?:\/\//i.test(card.url || "") && <a className="small ip-row" href={card.url} target="_blank" rel="noopener noreferrer">На сайте конкурента <Icon name="ext" /></a>}</div>
    <div className="ip-props">{[...new Set([card.material, card.color, card.modification, card.additional_property].filter(Boolean))].map(value => <span key={value} className="ip-tag gray">{value}</span>)}{properties.map(({ label, value }) => <span key={JSON.stringify([label, value])} className="ip-tag gray">{label}: {value}</span>)}</div>
    <div className="small muted">Без НДС. Регионы: {(card.regions || []).join(", ") || "не указаны"}.{card.competitor_price_date && ` Цена от ${new Date(card.competitor_price_date).toLocaleDateString("ru-RU")}.`}{card.article_number_analogs && ` Группа аналогов: ${card.article_number_analogs}.`}</div>
    {editable && <div className="ip-row between sm-competitor-card-actions" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}><span className="small muted">Цена в расчёте{mode === "mixed" ? " · разные решения по регионам" : ""}</span><div className="ip-seg" role="group" aria-label="Учитывать цену">{[["auto", "Авто"], ["include", "Учитывать"], ["exclude", "Не учитывать"]].map(([key, label]) => <button key={key} aria-pressed={mode === key} onClick={() => { if (key !== mode) onChangeMode(card, key); }}>{label}</button>)}</div></div>}
  </article>;
}

export function SelectionModal({ target, snapshotId, productId, revision, onClose, onSaved }) {
  const tooMany = target.card.competitor_product_keys.length > 50;
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    if (busy || tooMany || !reason.trim()) return;
    setBusy(true); setError("");
    try {
      await saveCompetitorSelection({ snapshotId, productId, keys: target.card.competitor_product_keys, mode: target.mode, reason: reason.trim(), revision });
      onSaved(); onClose();
    } catch (err) { setError(errorText(err, "Изменение не сохранилось.")); }
    finally { setBusy(false); }
  }
  return <Modal title={target.mode === "include" ? "Учитывать цену этого товара?" : target.mode === "exclude" ? "Не учитывать цену этого товара?" : "Вернуть решение системы?"} onClose={() => { if (!busy) onClose(); }} footer={<><Button disabled={busy} onClick={onClose}>Отмена</Button><Button variant="accent" disabled={busy || tooMany || !reason.trim()} onClick={save}>{busy ? "Пересчитываем…" : "Сохранить и пересчитать"}</Button></>}>
    {tooMany && <p role="alert">В карточке больше 50 региональных позиций. Измените участие по отдельным позициям в окне «История и состав аналогов». Групповое изменение не отправлено.</p>}
    <p className="muted">Цена товара будет пересчитана во всех регионах. Ручные цены потребуется подтвердить повторно.</p><label>Причина<textarea className="ip-textarea" value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></label>{error && <p role="alert">{error}</p>}
  </Modal>;
}
