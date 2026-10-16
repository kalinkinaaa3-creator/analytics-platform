import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { SelectMarketIcon } from "../../organizations/SelectMarketHome";
import "./selectMarketIPrice.css";
import { SelectMarketCalculations } from "./SelectMarketCalculations";
import { errorText } from "./format";

const root = "/v1/select-market/iprice/";
const sources = [
  ["price", "Прайс", "Полный прайс всех регионов за выбранную дату. Четыре уровня групп, цены с НДС 22%; код 1С — текст. Цена без НДС рассчитывается с округлением до целого рубля.", "price-file/"],
  ["product_cost", "Закупочные цены", "Полный файл за один месяц: дата, текстовый код, наименование, регион и закупочная цена без НДС. Замена файла сохраняет параметры доставки."],
  ["parser_prefixes", "Регионы конкурентов", "Файл полностью заменяет список региональных префиксов."],
  ["product_classification", "Классификация и аналоги", "Полная классификация. Ручные связи и исключения сохраняются."],
  ["calculation_config", "Параметры расчёта", "Месяц, код и регион; коэффициенты и три оптовые скидки. include_transport: 1 — учитывать доставку, 0 — не учитывать. logistics_unit — расходы без НДС на единицу, до копеек. Классификация и карточка сайта не обязательны."],
];
const statuses = { queued: "В очереди", running: "Выполняется", waiting_tara: "Ожидание ТАРА", waiting_session: "Ожидание Windows-исполнителя", waiting_remote: "Ожидание ТАРА", recovery_required: "Требуется проверка администратором", success: "Завершён", failed: "Ошибка", cancelled: "Отменён" };
const steps = { starting: "Подготовка", base_parser: "Сайт", base_report: "Итоги загрузки сайта", tt_parser: "ТопТара", tt_report: "Итоги ТопТара", ps_parser: "PS", ps_report: "Итоги PS", tara_parser: "ТАРА", tara_failed_retry: "Повтор ошибок ТАРА", tara_report: "Итоги ТАРА", completed: "Все этапы завершены" };

export function SelectMarketIPrice({ dashboard }) {
  const [view, setView] = useState("home");
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [priceDate, setPriceDate] = useState("");
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

  return <section className="sm-system-page sm-iprice" aria-busy={!state || !!busy}>
    <header className="sm-system-heading"><SelectMarketIcon type="suc" /><h1>{dashboard.name}</h1></header>
    <nav className="sm-iprice-nav" aria-label="Разделы iPrice">{[["home", "Главная"], ["prices", "Цены"], ["market", "Рынок и изменения"], ["versions", "Расчёты и история"], ["data", "Исходные данные"]].map(([key, title]) => <button key={key} aria-current={view === key ? "page" : undefined} onClick={() => setView(key)}>{title}</button>)}</nav>
    <details><summary>Справка по работе с iPrice</summary>
      <ol><li>В разделе «Исходные данные» скачайте шаблоны. Прайс содержит все регионы за выбранную дату и исходные цены с НДС 22%. Коды 1С вводятся текстом.</li><li>Обновите сайт и конкурентов. Дождитесь завершения сбора, затем выберите дату и запустите расчёт.</li><li>Выберите рассчитанную версию. Проверьте ошибки строк. Карточка товара показывает источники, расчёт и оптовые цены.</li><li>Для своей РРЦ укажите причину. Параметры меняются по точным фильтрам после предварительного просмотра. Изменение аналогов требует повторного подтверждения ручных цен.</li><li>Утвердите проверенную версию внутри системы и скачайте Excel. В 1С цены автоматически не отправляются.</li></ol>
      <p>РРЦ — розничная цена. Маржа и скидки задаются долями: 0,15 означает 15%. «Нет данных рынка» означает отсутствие пригодной конкурентной цены. Предупреждение требует проверки; ошибка строки блокирует утверждение.</p>
      <p>Цены утверждённой версии зафиксированы. Чтобы изменить их, создайте новый расчёт. Снятие утверждения сохраняет историю и не разблокирует редактирование прежней версии.</p>
    </details>
    {error && <p role="alert" className="sm-iprice-error">{error}</p>}
    {statusError && <p role="alert" className="sm-iprice-error">{statusError}</p>}
    {message && <p role="status">{message}</p>}
    {!state && <p role="status" className="sm-iprice-loading">Загружаем источники…</p>}
    {state && <>
      <SelectMarketCalculations canEdit={state.can_edit} view={view} />
      <div hidden={view !== "data"}>
      <h2>Источники и загрузки</h2>
      {!state.can_edit && <p>Доступен просмотр. Загрузка файлов и запуск парсеров доступны редакторам.</p>}
      <div className="sm-iprice-sources">{sources.map(([key, title, hint, route]) => {
        const path = route || `sources/${key}/`;
        return <article key={key} className="sm-iprice-card"><h3>{title}</h3><p>{hint}</p>
          {key === "price" && state.can_edit && <label>Дата полного прайса<input type="date" required value={priceDate} disabled={!!busy} onChange={event => setPriceDate(event.target.value)} /></label>}
          <button type="button" disabled={!!busy} onClick={() => perform(`template-${key}`, async () => {
            const response = await api.get(`${root}${path}`, { responseType: "blob" });
            if (!mounted.current) return;
            const url = URL.createObjectURL(response.data);
            const link = document.createElement("a"); link.href = url; link.download = `select_market_${key}.xlsx`;
            document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
          })}>Скачать шаблон</button>
          {state.can_edit && <label>Загрузить XLSX
            <input type="file" accept=".xlsx" disabled={!!busy || (key === "price" && !priceDate)} onChange={event => {
              const file = event.target.files?.[0]; event.target.value = "";
              if (!file) return;
              if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 10 * 1024 * 1024) { setError("Выберите XLSX размером не более 10 МБ."); return; }
              perform(key, async () => {
                const body = new FormData(); body.append("file", file);
                if (key === "price") body.append("price_date", priceDate);
                await api.post(`${root}${path}`, body);
                if (mounted.current) setMessage(`${title}: файл загружен.`);
              });
            }} />
          </label>}
          {busy === key && <p role="status" className="sm-iprice-loading">Проверяем и загружаем файл…</p>}
        </article>;
      })}</div>
      <article className="sm-iprice-card"><h2>Обновление сайта и конкурентов</h2>
        <p>Сайт загружается полностью. Товары конкурентов выбираются из активной классификации. Во время ожидания ТАРА остальные сборы ожидают освобождения общего слота.</p>
        {state.can_edit && <button className="sm-iprice-primary" type="button" disabled={!!busy || active || !state.parsers_enabled} onClick={() => perform("parsers", async () => {
          await api.post(`${root}parsers/start/`, {});
          if (mounted.current) setMessage("Запуск зарегистрирован. Состояние обновляется автоматически.");
        })}>{active ? "Обновление выполняется" : "Обновить источники"}</button>}
        {!state.parsers_enabled && <p>Запуск парсеров пока не включён администратором.</p>}
        {state.run && <p>Запуск №{state.run.id}: <strong>{statuses[state.run.status] || state.run.status}</strong>. Этап: {steps[state.run.step] || state.run.step || "—"}.</p>}
        {state.run?.status === "failed" && <p>Обновление завершилось с ошибкой. Подробности доступны администратору в журнале запуска.</p>}
        {state.queue.map(item => <p key={item.id}>{statuses[item.status] || item.status}{item.position ? ` · Место в очереди: ${item.position}` : ""}{item.message ? ` · ${item.message}` : ""}</p>)}
      </article>
      <article className="sm-iprice-card"><h2>Последние загрузки файлов</h2>
        {!state.imports.length && !state.price_imports.length && <p className="sm-iprice-empty">Файлы пока не загружались.</p>}
        <ul>{state.price_imports.map(item => <li key={`price-${item.id}`}>Прайс за {item.date}: {item.filename} · {item.rows} строк · версия {item.revision}</li>)}
          {state.imports.map(item => <li key={item.id}>{sources.find(source => source[0] === item.kind)?.[1] || item.kind}: {item.filename} · {new Date(item.created_at).toLocaleString("ru-RU")}</li>)}</ul>
      </article>
      </div>
    </>}
  </section>;
}
