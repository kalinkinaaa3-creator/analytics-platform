import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { Panel, Button, Drawer } from "./ui/primitives";
import Icon from "./ui/Icon";
import { FilterChip } from "./SelectMarketFilters";
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
      <div className="ip-row"><div className="ip-affix sm-catalog-search"><span className="pre"><Icon name="search" size={16} /></span><input className="ip-input" type="search" aria-label="Поиск по названию или URL" placeholder="Поиск по названию или URL" value={search} maxLength={200} onChange={event => filter(setSearch, event.target.value)} /></div>
        <div className="ip-filters"><FilterChip name="competitor" label="Конкурент" displayValue={getIPriceCompetitorSourceLabel} values={["tara", "tt", "ps"]} selected={source ? [source] : []} onChange={values => filter(setSource, values.at(-1) || "")} /></div></div>
      {message && <div className="ip-alert" role="status"><span>{message}</span><Button size="s" variant="ghost" onClick={() => setMessage("")} aria-label="Скрыть сообщение">×</Button></div>}
      {error && <p role="alert">{error} <Button size="s" onClick={() => setRevision(value => value + 1)}>Повторить</Button></p>}
      {loading && <p role="status">Загружаем товары…</p>}
      {!loading && !error && <><div className="sm-unclassified-grid">{data?.results.map(card => <article key={card.product_keys.join("-")} className="ip-card sm-unclassified-card">
        <div className="ip-card-top"><div className="ip-thumb"><ProductImage src={card.image} name={card.name} /></div><div><span className="ip-tag outline">{getIPriceCompetitorSourceLabel(card.source)}</span><h3 className="ip-card-title">{card.name || "Название ещё не загружено"}</h3><span className="small muted sm-catalog-keys">Ключи: {card.product_keys.join(", ")}</span></div></div>
        <div><strong className="price">{card.price == null ? "Цена не загружена" : fmtMoney(card.price)}</strong>{card.price != null && <div className="small muted">Медиана по регионам, без НДС.<br /><span>{card.dates.length === 1 ? `Цена от ${date(card.dates[0])}` : "Даты цен — по регионам"}</span></div>}</div>
        <details className="sm-regional-prices"><summary>Регионы и цены · {card.regional_entries.length}</summary><div className="sm-catalog-regions"><table className="ip-table"><thead><tr><th>Регион</th><th>Цена без НДС</th><th>Дата сбора</th><th /></tr></thead><tbody>{card.regional_entries.flatMap(entry => entry.offers.map(offer => <tr key={`${entry.region}-${offer.product_key}`}><td>{entry.region}</td><td>{fmtMoney(offer.price)}</td><td>{date(offer.date)}</td><td>{safeUrl(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer" aria-label="На сайте конкурента" title="На сайте конкурента"><Icon name="ext" /></a>}</td></tr>))}</tbody></table></div></details>
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
  return <Drawer open title="Классификация товара" onClose={() => { if (!busy) onClose(); }}>
    <div className="ip-stack sm-classification-editor">
    <div className="sm-classification-heading"><h3>{card.name || "Название ещё не загружено"}</h3></div>
    <p className="small muted">Классификация сохраняется для всех регионов этой карточки. Автоматические аналоги определяются по общей классификации.</p>
    <p className="small muted">Существующие расчёты и ручные цены не меняются. Классификация учитывается в следующем расчёте. Цены конкурента обновятся при следующем сборе; сохранение классификации не запускает сбор автоматически.</p>
    <Button disabled={busy} onClick={() => { setValues({ ...defaults, item_type: defaults.item_type || "product" }); setError(""); }}>Заполнить по текущему товару</Button>
    <ClassificationFields values={values} choices={choices} disabled={busy} onChange={(key, value) => { setError(""); setValues(current => ({ ...current, [key]: value })); }} />
    <label className="ip-field">Комментарий к изменению<textarea className="ip-textarea" maxLength={2000} disabled={busy} value={reason} onChange={event => setReason(event.target.value)} /></label>
    {error && <p role="alert">{error}</p>}
    <div className="ip-row sm-classification-actions"><Button disabled={busy} onClick={onClose}>Отмена</Button><Button variant="accent" disabled={busy || !reason.trim()} onClick={save}>{busy ? "Сохраняем…" : "Сохранить классификацию"}</Button></div>
    </div>
  </Drawer>;
}

function ClassificationFields({ values, choices, disabled, onChange }) {
  const [active, setActive] = useState(null);
  const [query, setQuery] = useState("");
  const root = useRef(null);
  const input = useRef(null);
  useEffect(() => {
    if (!active) return;
    input.current?.focus();
    const close = event => { if (!root.current?.contains(event.target)) setActive(null); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [active]);
  const label = fields.find(([key]) => key === active)?.[1];
  const display = (key, value) => key === "item_type" ? ({ product: "Товар", component: "Комплектующее" })[value] || value : value;
  const options = active === "item_type" ? ["product", "component"] : [...new Set([values[active], ...(choices[active] || [])].filter(Boolean))].sort((a, b) => a.localeCompare(b, "ru"));
  const visible = options.filter(value => display(active, value).toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  function choose(value) { onChange(active, value); setActive(null); }
  return <div ref={root} className="sm-classification-fields" onKeyDown={event => { if (active && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setActive(null); } }}>
    {fields.map(([key, title]) => <button type="button" className={`ip-chip sm-classification-chip ${values[key] ? "on" : ""}`} key={key} disabled={disabled} aria-expanded={active === key} aria-haspopup="listbox" aria-label={`${title}: ${display(key, values[key]) || "Не заполнено"}`} title={`${title}: ${display(key, values[key]) || "Не заполнено"}`} onClick={() => { setQuery(""); setActive(active === key ? null : key); }}>
      <span className="sm-classification-chip-text"><span>{title}</span><b>{display(key, values[key]) || "Не заполнено"}</b></span><Icon name="chevDown" size={12} />
    </button>)}
    {active && <div className="ip-pop sm-classification-pop">
      <div className="ip-row between"><b>{label}</b><Button variant="ghost" size="s" icon="x" aria-label="Закрыть список" onClick={() => setActive(null)} /></div>
      <div className="ip-affix"><span className="pre"><Icon name="search" size={14} /></span><input ref={input} className="ip-input" value={query} maxLength={255} disabled={disabled} aria-label={`Найти значение: ${label}`} placeholder={active === "item_type" ? "Найти значение" : "Найти или ввести значение"} onChange={event => setQuery(event.target.value)} /></div>
      <div className="list" role="listbox" aria-label={label}>{visible.map(value => <button type="button" role="option" aria-selected={values[active] === value} className="opt" key={value} disabled={disabled} onClick={() => choose(value)}><span className="lbl">{display(active, value)}</span>{values[active] === value && <span aria-hidden="true">✓</span>}</button>)}{!visible.length && <p className="small muted">Нет значений</p>}</div>
      <div className="foot">{active !== "item_type" && <><Button size="s" variant="ghost" disabled={disabled} onClick={() => choose("")}>Очистить</Button>{query.trim() && !options.includes(query.trim()) && <Button size="s" disabled={disabled} onClick={() => choose(query.trim())}>Использовать введённое значение</Button>}</>}</div>
    </div>}
  </div>;
}
