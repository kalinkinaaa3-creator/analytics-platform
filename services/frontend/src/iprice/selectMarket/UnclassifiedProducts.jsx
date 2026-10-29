import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Panel, Button, Modal } from "./ui/primitives";
import { Pager } from "./ui/Pager";
import { ProductImage } from "./ProductImage";
import { fmtMoney } from "./archiveFormat";
import { errorText } from "./format";
import { getIPriceCompetitorSourceLabel } from "../product/ipriceProductLabels";

const fields = [["category", "Тип"], ["subcategory", "Категория"], ["subcategory_type", "Подкатегория"],
  ["material", "Материал"], ["color", "Цвет"], ["modification", "Модификация"],
  ["article_number_analogs", "Группа аналогов"], ["item_type", "Тип позиции"]];
const date = value => value ? new Date(value).toLocaleDateString("ru-RU") : "—";
const safeUrl = value => /^https?:\/\//i.test(value || "");

export function UnclassifiedProducts({ snapshotId, productId, canEdit }) {
  const endpoint = `/v1/select-market/iprice/snapshots/${snapshotId}/products/${productId}/unclassified/`;
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      api.get(endpoint, { params: { search, source, page }, signal: controller.signal })
        .then(response => { setData(response.data); })
        .catch(err => { if (!controller.signal.aborted) setError(errorText(err)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [endpoint, search, source, page, revision]);
  function filter(setter, value) { setter(value); setPage(1); setLoading(true); setMessage(""); }
  return <Panel title="Неклассифицированные товары" sub="Общий каталог конкурентов. Названия, фотографии и цены — по последнему сбору; классификация применяется ко всем регионам карточки.">
    <div className="sm-panel-body ip-stack">
      <div className="ip-row"><label className="ip-field sm-catalog-search">Поиск по названию или URL<input className="ip-input" value={search} maxLength={200} onChange={event => filter(setSearch, event.target.value)} /></label>
        <label className="ip-field">Конкурент<select className="ip-select" value={source} onChange={event => filter(setSource, event.target.value)}><option value="">Все</option>{["tara", "tt", "ps"].map(key => <option key={key} value={key}>{getIPriceCompetitorSourceLabel(key)}</option>)}</select></label></div>
      {message && <div className="ip-alert" role="status"><span>{message}</span><Button size="s" variant="ghost" onClick={() => setMessage("")} aria-label="Скрыть сообщение">×</Button></div>}
      {error && <p role="alert">{error} <Button size="s" onClick={() => setRevision(value => value + 1)}>Повторить</Button></p>}
      {loading && <p role="status">Загружаем товары…</p>}
      {!loading && !error && <><div className="sm-unclassified-grid">{data?.results.map(card => <article key={card.product_keys.join("-")} className="ip-card sm-unclassified-card">
        <div className="ip-card-top"><div className="ip-thumb"><ProductImage src={card.image} name={card.name} /></div><div><span className="ip-tag outline">{getIPriceCompetitorSourceLabel(card.source)}</span><h3 className="ip-card-title">{card.name || "Название ещё не загружено"}</h3>{!card.name && <span className="small sm-catalog-url">{card.url}</span>}<span className="small muted">Ключи: {card.product_keys.join(", ")}</span></div></div>
        <div><strong className="price">{card.price == null ? "Цена не загружена" : fmtMoney(card.price)}</strong>{card.price != null && <div className="small muted">Медиана по регионам, без НДС.<br /><span>{card.dates.length === 1 ? `Цена от ${date(card.dates[0])}` : "Даты цен — по регионам"}</span></div>}</div>
        <details className="sm-regional-prices"><summary>Регионы и цены · {card.regional_entries.length}</summary><div className="sm-catalog-regions"><table className="ip-table"><thead><tr><th>Регион</th><th>Цена без НДС</th><th>Дата сбора</th><th /></tr></thead><tbody>{card.regional_entries.flatMap(entry => entry.offers.map(offer => <tr key={`${entry.region}-${offer.product_key}`}><td>{entry.region}</td><td>{fmtMoney(offer.price)}</td><td>{date(offer.date)}</td><td>{safeUrl(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer">На сайте</a>}</td></tr>))}</tbody></table></div></details>
        {canEdit && <Button onClick={() => setEditing(card)}>Классифицировать</Button>}
      </article>)}</div>
        {!data?.results.length && <div className="ip-empty">{search || source ? "Нет товаров для выбранных фильтров" : "Неклассифицированных товаров нет"}</div>}
        <Pager page={data?.page || 1} totalPages={data?.pages || 1} count={data?.count || 0} pageSize={24} onPage={value => { setLoading(true); setPage(value); }} />
      </>}
      {!!data?.history?.length && <details><summary>История классификации · последние 50 изменений</summary><div className="sm-classification-history">{data.history.map(item => <article key={item.id}><div className="small muted">Ключи: {item.product_keys.join(", ")} · {item.changed_by__username || "—"} · {new Date(item.created_at).toLocaleString("ru-RU")}</div><p>{fields.map(([key, label]) => `${label}: ${key === "item_type" ? item.after[key] === "component" ? "Комплектующее" : "Товар" : item.after[key] || "—"}`).join(" · ")}</p><p>{item.reason}</p></article>)}</div></details>}
    </div>
    {editing && <ClassificationEditor card={editing} endpoint={endpoint} defaults={data.defaults} choices={data.choices} onClose={() => setEditing(null)} onSaved={text => { setEditing(null); setMessage(text); setLoading(true); setRevision(value => value + 1); }} />}
  </Panel>;
}

function ClassificationEditor({ card, endpoint, defaults, choices, onClose, onSaved }) {
  const [values, setValues] = useState(Object.fromEntries(fields.map(([key]) => [key, key === "item_type" ? "product" : ""])));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setBusy(true); setError("");
    try {
      const response = await api.post(endpoint, { product_keys: card.product_keys, revision: card.revision, values, reason });
      onSaved(response.data.message);
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }
  return <Modal title="Классификация товара" onClose={() => { if (!busy) onClose(); }} footer={<><Button disabled={busy} onClick={onClose}>Отмена</Button><Button variant="accent" disabled={busy || !reason.trim()} onClick={save}>{busy ? "Сохраняем…" : "Сохранить классификацию"}</Button></>}>
    <p>{card.name || card.url}</p><p className="small muted">Классификация сохраняется для всех регионов этой карточки. Автоматические аналоги определяются по общей классификации.</p>
    <p className="small muted">Существующие расчёты и ручные цены не меняются. Классификация учитывается в следующем расчёте. Цены конкурента обновятся при следующем сборе; сохранение классификации не запускает сбор автоматически.</p>
    <Button disabled={busy} onClick={() => { setValues({ ...defaults, item_type: defaults.item_type || "product" }); setError(""); }}>Заполнить по текущему товару</Button>
    <div className="sm-classification-fields">{fields.map(([key, label]) => <label className="ip-field" key={key}>{label}{key === "item_type" ? <select className="ip-select" value={values[key]} disabled={busy} onChange={event => setValues({ ...values, [key]: event.target.value })}><option value="product">Товар</option><option value="component">Комплектующее</option></select> : <><input className="ip-input" maxLength={255} disabled={busy} value={values[key]} list={`classification-${key}`} onChange={event => { setError(""); setValues({ ...values, [key]: event.target.value }); }} /><datalist id={`classification-${key}`}>{choices[key]?.map(value => <option key={value} value={value} />)}</datalist></>}</label>)}</div>
    <label className="ip-field">Комментарий к изменению<textarea className="ip-textarea" maxLength={2000} disabled={busy} value={reason} onChange={event => setReason(event.target.value)} /></label>
    {error && <p role="alert">{error}</p>}
  </Modal>;
}
