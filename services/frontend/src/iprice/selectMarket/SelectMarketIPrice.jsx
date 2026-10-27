import { Notice } from "./Notice";
import { PriceZonesProvider } from "./PriceZones";
import { SelectMarketHealth } from "./SelectMarketHealth";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { Button, PageHead, Panel, Tabs } from "./ui/primitives";
import Icon from "./ui/Icon";
import { SelectMarketHelp } from "./SelectMarketHelp";
import "./demo.css";
import "./selectMarketIPrice.css";
import { SelectMarketCalculations } from "./SelectMarketCalculations";
import { errorText } from "./format";

const root = "/v1/select-market/iprice/";
const sources = [
  ["price", "Прайс", "Полный прайс всех регионов за выбранную дату. Четыре уровня групп, цены с НДС 22%; код 1С — текст. Цена без НДС рассчитывается с округлением до целого рубля.", "price-file/"],
  ["product_cost", "Закупочные цены", "Полный файл за один месяц: дата, текстовый код, наименование, регион и закупочная цена без НДС. Замена файла сохраняет параметры доставки."],
  ["parser_prefixes", "Регионы конкурентов", "Файл полностью заменяет список региональных префиксов."],
  ["product_classification", "Классификация и аналоги", "Полная классификация. Шаблон содержит собственные товары, включая позиции без сайта, и уже классифицированных конкурентов. Заполните новые строки; ручные связи и исключения сохраняются."],
  ["calculation_config", "Параметры расчёта", "Месяц, код и регион; коэффициенты и три оптовые скидки. include_transport: 1 — учитывать доставку, 0 — не учитывать. logistics_unit — расходы без НДС на единицу, до копеек. Классификация и карточка сайта не обязательны."],
];
const statuses = { queued: "В очереди", running: "Выполняется", waiting_tara: "Ожидание ТАРА", waiting_session: "Ожидание Windows-исполнителя", waiting_remote: "Ожидание ТАРА", recovery_required: "Требуется проверка администратором", success: "Завершён", failed: "Ошибка", cancelled: "Отменён" };
const steps = { starting: "Подготовка", base_parser: "Сайт", base_report: "Итоги загрузки сайта", tt_parser: "ТопТара", tt_report: "Итоги ТопТара", ps_parser: "PS", ps_report: "Итоги PS", tara_parser: "ТАРА", tara_failed_retry: "Повтор ошибок ТАРА", tara_report: "Итоги ТАРА", completed: "Все этапы завершены" };

export function SelectMarketIPrice({ dashboard }) {
  const [help, setHelp] = useState(false);
  const [navigationRevision, setNavigationRevision] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  const address = new URLSearchParams(location.hash.slice(1));
  const requestedView = address.get("suc");
  const view = ["home", "prices", "market", "versions", "data", "compare"].includes(requestedView) ? requestedView : "home";
  const dataTab = ["uploads", "parser", "health"].includes(address.get("data")) ? address.get("data") : "uploads";
  function sectionAddress(next, tab, reset = false) {
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (reset) ["product", "row", "product_region", "price_scope", "market_scope", "compare_scope", "compare_product", "compare_snapshot", "compare_region"].forEach(key => params.delete(key));
    if (reset) for (const key of [...params.keys()]) if (/^[pmc]_/.test(key)) params.delete(key);
    params.set("suc", next);
    if (next !== "data") params.delete("data"); else if (tab) params.set("data", tab);
    return { pathname: location.pathname, search: location.search, hash: `#${params}` };
  }
  function setView(next, tab) {
    navigate(sectionAddress(next, tab), { state: location.state });
  }
  function setDataTab(tab) { setView("data", tab); }
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [priceDate, setPriceDate] = useState(() => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()));
  const [uploads, setUploads] = useState({});
  const mounted = useRef(false);
  const actionPending = useRef(false);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const { data } = await api.get(`${root}status/`, { signal: controller.signal });
        if (!controller.signal.aborted) { setState(data); setStatusError(""); }
      } catch (err) {
        if (!controller.signal.aborted && err.code !== "ERR_CANCELED") setStatusError(errorText(err));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { mounted.current = false; clearTimeout(timer); controller.abort(); };
  }, []);

  async function perform(key, action) {
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(key); setError(""); setMessage("");
    try {
      await action();
      try {
        const { data } = await api.get(`${root}status/`);
        if (mounted.current) { setState(data); setStatusError(""); }
      } catch {
        if (mounted.current) setStatusError("Операция выполнена, но обновить состояние пока не удалось. Повторяем автоматически.");
      }
    } catch (err) {
      if (mounted.current) setError(errorText(err));
    } finally {
      actionPending.current = false;
      if (mounted.current) setBusy("");
    }
  }
  const active = state?.run && !["success", "failed", "cancelled"].includes(state.run.status);

  function template(key, route) {
    perform(`template-${key}`, async () => {
      const response = await api.get(`${root}${route || `sources/${key}/`}`, { responseType: "blob" });
      if (!mounted.current) return;
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a"); link.href = url; link.download = `select_market_${key}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  function upload(file, key, title, route) {
    if (!file || busy || !state?.can_edit) return;
    if (key === "price" && !priceDate) { setError("Выберите дату полного прайса."); return; }
    if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 10 * 1024 * 1024) { setError("Выберите XLSX размером не более 10 МБ."); return; }
    perform(key, async () => {
      const body = new FormData(); body.append("file", file);
      if (key === "price") body.append("price_date", priceDate);
      setUploads(previous => ({ ...previous, [key]: { state: "uploading", file: file.name, progress: 0 } }));
      try {
        const { data: result } = await api.post(`${root}${route || `sources/${key}/`}`, body, { onUploadProgress: event => {
          if (mounted.current) setUploads(previous => ({ ...previous, [key]: { state: "uploading", file: file.name, progress: event.total ? Math.round(event.loaded / event.total * 100) : 0 } }));
        } });
        if (mounted.current) setUploads(previous => ({ ...previous, [key]: { state: "done", file: file.name, message: `Файл загружен и проверен. ${Object.entries({rows: "Строк", loaded: "Загружено", created: "Создано", updated: "Обновлено", skipped: "Пропущено", deleted: "Удалено"}).filter(([key]) => typeof result?.[key] === "number").map(([key, label]) => `${label}: ${result[key].toLocaleString("ru-RU")}`).join("; ")}. Новые данные войдут в следующий расчёт.`.replace("проверен. .", "проверен.") } }));
      } catch (err) {
        if (mounted.current) setUploads(previous => ({ ...previous, [key]: { state: "error", file: file.name, message: errorText(err) } }));
      }
    });
  }
  return <PriceZonesProvider><section className="sm-system-page sm-iprice" aria-label={dashboard.name} aria-busy={!state || !!busy} onWheelCapture={event => {
    const input = document.activeElement;
    if (input instanceof HTMLInputElement && input.type === "number" && event.currentTarget.contains(input)) input.blur();
  }}>
    <header className="ip-head"><div className="ip-head-row">
      <nav className="ip-nav" aria-label="Разделы iPrice">{[["home", "Главная", "home"], ["prices", "Цены", "table"], ["market", "Рынок", "chart"], ["versions", "Расчёты", "layers"], ["data", "Данные", "data"]].map(([key, title, icon]) => <a href={`${location.pathname}${location.search}${sectionAddress(key, undefined, true).hash}`} key={key} className={(view === key || (key === "versions" && view === "compare")) ? "active" : ""} aria-current={(view === key || (key === "versions" && view === "compare")) ? "page" : undefined} onClick={e => { if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; e.preventDefault(); navigate(sectionAddress(key, undefined, true), { state: {...location.state, sucReturn: undefined} }); setNavigationRevision(value => value + 1); }}><Icon name={icon} size={16} />{title}</a>)}</nav>
      <div className="ip-head-spacer" /><div id="sm-iprice-version-slot" />
      <Button variant="ghost" icon="help" aria-label="Справка" title="Справка: шаги работы, цвета, словарь" onClick={() => setHelp(true)} />
    </div></header>
    <SelectMarketHelp open={help} onClose={() => setHelp(false)} />
    <main className="ip-main">
      {error && <Notice key={"error:" + error} error onClose={() => setError("")}>{error}</Notice>}
      {statusError && <p role="alert" className="sm-iprice-error">{statusError}</p>}
      {message && <Notice key={"message:" + message} onClose={() => setMessage("")}>{message}</Notice>}
      {!state && <p role="status" className="sm-iprice-loading">Загружаем источники…</p>}
      {state && <>
        <SelectMarketCalculations navigationRevision={navigationRevision} canEdit={state.can_edit} view={view} onNavigate={setView} onHelp={() => setHelp(view === "market" ? "colors" : "steps")} sourceState={state} />
        {view === "data" && <>
          <PageHead title="Исходные данные" text="iPrice считает цены по закупочной стоимости, доставке, правилам компании и ценам конкурентов. Перед расчётом обновите файлы." onHelp={() => setHelp(true)} />
          <Tabs value={dataTab} onChange={setDataTab} items={[["uploads", "Файлы"], ["parser", "Цены конкурентов"], ["health", "Проверка данных"]]} />
          {dataTab === "uploads" && <>
            <div className="ip-alert info"><Icon name="info" /><div className="body"><b>Загрузка в три действия</b><span>Скачайте шаблон, заполните его в Excel и перетащите файл в карточку. Закупочные цены обновляйте каждый месяц, остальные файлы — при изменениях.</span></div></div>
            <div className="ip-grid k2 sm-iprice-source-grid">{sources.map(([key, title, hint, route]) => <Panel key={key} title={title} sub={hint} actions={<Button size="s" variant="ghost" icon="download" disabled={!!busy} onClick={() => template(key, route)}>Шаблон</Button>}>
              <div className="ip-stack sm-upload-body">
                <div className="sm-source-date">{key === "price" && state.can_edit && <label>Дата полного прайса<input className="ip-input" type="date" required value={priceDate} disabled={!!busy} onChange={e => setPriceDate(e.target.value)} /></label>}</div>
                {state.can_edit ? <label className={`ip-drop ${busy ? "disabled" : ""}`} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); upload(e.dataTransfer.files?.[0], key, title, route); }}>
                  <Icon name="upload" size={22} /><div><b>Перетащите файл</b> или <span>выберите на компьютере</span></div><div className="small quiet">Excel (.xlsx) по шаблону, до 10 МБ</div>
                  <input type="file" accept=".xlsx" aria-label={`Загрузить ${title}`} disabled={!!busy || (key === "price" && !priceDate)} onChange={e => { upload(e.target.files?.[0], key, title, route); e.target.value = ""; }} />
                </label> : <span className="small muted">Файлы загружают сотрудники с правом редактирования.</span>}
                {uploads[key]?.state === "uploading" && <><p role="status" className="sm-iprice-loading">Загружаем и проверяем {uploads[key].file}…</p><div className={`ip-progress ${uploads[key].progress >= 100 ? "indet" : ""}`}><span style={{ width: `${uploads[key].progress}%` }} /></div></>}
                {uploads[key] && uploads[key].state !== "uploading" && <div role="status" className={`ip-alert ${uploads[key].state === "done" ? "success" : "error"}`}><div className="body"><b>{uploads[key].file}</b><span>{uploads[key].message}</span></div></div>}
              </div>
            </Panel>)}</div>
          </>}
          {dataTab === "parser" && <div className="ip-grid side"><Panel title="Сбор цен конкурентов" sub="Сайт загружается полностью. Товары конкурентов выбираются из активной классификации. Общая очередь защищает источники от одновременных сборов."
            actions={state.can_edit && <Button variant="primary" icon="play" disabled={!!busy || active || !state.parsers_enabled} onClick={() => perform("parsers", async () => { await api.post(`${root}parsers/start/`, {}); if (mounted.current) setMessage("Запуск зарегистрирован. Состояние обновляется автоматически."); })}>{active ? "Обновление выполняется" : "Собрать цены"}</Button>}>
            <div className="ip-stack sm-panel-body">{!state.parsers_enabled && <p>Запуск парсеров пока не включён администратором.</p>}
              {state.run ? <><span className={`ip-tag ${state.run.status === "failed" ? "red" : state.run.status === "success" ? "green" : "blue"}`}>{statuses[state.run.status] || state.run.status}</span><p>Сейчас: <b>{steps[state.run.step] || state.run.step || "—"}</b></p>{active && <p role="status" className="sm-iprice-loading">Обновляем цены конкурентов…</p>}<dl className="ip-kv"><dt>Начали</dt><dd>{state.run.started_at ? new Date(state.run.started_at).toLocaleString("ru-RU") : "—"}</dd><dt>Закончили</dt><dd>{state.run.finished_at ? new Date(state.run.finished_at).toLocaleString("ru-RU") : active ? "ещё идёт" : "—"}</dd></dl></> : <span className="ip-tag gray">Ещё не собирали</span>}
              {state.run?.status === "failed" && <p role="alert">Обновление завершилось с ошибкой. Подробности доступны администратору в журнале запуска.</p>}
              {state.queue.map(item => <p key={`queue-${item.id}`}>{statuses[item.status] || item.status}{item.position ? ` · Место в очереди: ${item.position}` : ""}{item.message ? ` · ${item.message}` : ""}</p>)}
            </div></Panel><Panel title="Файлы для сверки" sub="Excel для ручной проверки данных"><div className="ip-stack sm-panel-body"><Button icon="download" disabled={!!busy} onClick={() => template("parser_products", "review/parser_products/")}>Товары конкурентов</Button><Button icon="download" disabled={!!busy} onClick={() => template("preparation_check", "review/preparation_check/")}>Готовность к расчёту</Button><p>Проверка исходных данных и замечаний последнего расчёта. Полная проверка коэффициентов выполняется при расчёте.</p></div></Panel></div>}
          {dataTab === "health" && <><SelectMarketHealth /><Panel title="Последние загрузки файлов" sub="Ошибки загрузки показываются при проверке файла. Ошибки расчёта доступны в разделе «Цены»."><div className="sm-panel-body">
            {!state.imports.length && !state.price_imports.length && <div className="ip-empty"><b>Файлы пока не загружались</b><span>Перейдите во вкладку «Файлы» и заполните шаблоны.</span></div>}
            <ul>{[
              ...state.price_imports.map(item => ({ ...item, kind: "price", created_at: item.date_add || item.date })),
              ...state.imports,
            ].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).filter((item, index, all) => all.findIndex(other => other.kind === item.kind) === index).map(item => <li key={item.kind + "-" + item.id}>{sources.find(source => source[0] === item.kind)?.[1] || item.kind}: {item.filename} · {new Date(item.created_at).toLocaleString("ru-RU")}{item.kind === "price" && ` · прайс за ${item.date} · ${item.rows} строк · версия ${item.revision}`}</li>)}</ul>
          </div></Panel></>}
        </>}
      </>}
    </main>
  </section></PriceZonesProvider>;
}
