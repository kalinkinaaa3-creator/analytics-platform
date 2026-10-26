import { usePriceZones, zoneHint } from "./priceZonesContext";
import { Drawer } from "./ui/primitives";
import Icon from "./ui/Icon";
import { useEffect } from "react";
import { ZoneTag } from "./ZoneTag";

const steps = [
  ["Загрузите данные", "Прайс всех регионов за выбранную дату, закупочные цены без НДС и правила расчёта в Excel по шаблонам.", "Данные → Файлы"],
  ["Соберите цены конкурентов", "Обновите сайт и цены конкурентов. Дождитесь завершения сбора.", "Данные → Цены конкурентов"],
  ["Посчитайте новые цены", "Выберите дату: iPrice создаст отдельную версию расчёта для товаров и регионов.", "Расчёты → Посчитать цены"],
  ["Проверьте", "Проверьте отклонения от рынка и ошибки строк. Для своей цены укажите причину.", "Главная и Цены"],
  ["Утвердите и выгрузите", "Утверждение фиксирует версию внутри системы. Скачайте Excel; автоматической отправки в 1С нет.", "Расчёты → Утвердить внутри системы"],
];
const glossary = [
  ["РРЦ", "Розничная цена. Расчёт выполняется без НДС; рядом и в Excel показывается цена с НДС 22%."],
  ["Закупочная цена", "Цена закупки без НДС для пары «товар + регион». Загружается вручную за месяц расчёта."],
  ["Доставка", "Расходы на единицу без НДС. Прибавляются к закупке только при включённом параметре «Учитывать транспортные расходы»."],
  ["Цена конкурентов", "Ориентир по пригодным аналогам в регионе. Отсутствие данных рынка не означает нулевую цену."],
  ["Минимальная маржа", "Ограничение нижней цены. В форме маржа и скидки вводятся в процентах: 15 означает 15%. В Excel-шаблоне используются доли: 0,15 означает 15%."],
  ["Расчёт", "Сохранённая версия цен и исходных данных. Статус «Ждёт проверки» не исключает ошибок отдельных строк."],
  ["Утверждённая версия", "Проверенная версия с зафиксированными ценами. Для изменения создайте новый расчёт. Снятие утверждения не разблокирует прежние цены."],
];
const zones = ["below_market", "in_market", "above_market", "critical_above", "no_market_data"];
export function SelectMarketHelp({ open, onClose }) {
  const { config } = usePriceZones();
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      const section = typeof open === "string" ? open : "about";
      const target = document.getElementById(`sm-help-${section}`);
      const body = target?.closest(".ip-drawer-body");
      if (body) body.scrollTop = section === "about" ? 0 : body.scrollTop + target.getBoundingClientRect().top - body.getBoundingClientRect().top - 20;
    }, 50);
    return () => clearTimeout(timer);
  }, [open]);
  return <Drawer open={open} onClose={onClose} title="Справка" sub="Шаги работы, цвета, частые вопросы, словарь">
    <div className="ip-stack ip-help" style={{ gap: 20 }}>
      <section className="ip-stack" style={{ gap: 8 }}><h3 id="sm-help-about">О системе</h3><p>iPrice предлагает розничную цену на каждый наш товар в каждом регионе. В расчёт идут три источника:</p>
        <div className="ip-help-three"><div><Icon name="wallet" /><b>Закупочная цена</b><span>закупка и учитываемая доставка; задаёт нижнюю границу цены</span></div><div><Icon name="compare" /><b>Цены конкурентов</b><span>похожий товар в регионе; служат ориентиром</span></div><div><Icon name="settings" /><b>Правила компании</b><span>положение к рынку и маржа</span></div></div>
        <p>Ваша задача: проверить цены, поправить спорные и утвердить расчёт внутри системы.</p></section>
      <section className="ip-stack" style={{ gap: 8 }}><h3 id="sm-help-steps">Пять шагов к новым ценам</h3><ol className="ip-help-steps">{steps.map(([title, text, where], i) => <li key={title}><span className="n">{i + 1}</span><div><b>{title}</b><p>{text}</p><span className="where">Раздел: {where}</span></div></li>)}</ol></section>
      <section className="ip-stack" style={{ gap: 8 }}><h3 id="sm-help-colors">Цвета</h3><p>Цвет метки показывает положение новой итоговой цены относительно рынка. Пороги задаются в разделе «Рынок».</p><ul className="ip-help-zones">{zones.map(zone => <li key={zone}><ZoneTag zone={zone} /><span>{zoneHint(zone, config)}</span></li>)}</ul></section>
      <section className="ip-stack" style={{ gap: 8 }}><h3 id="sm-help-faq">Частые вопросы</h3>{[
        ["Как поменять цену товара?", "Откройте «Цены», найдите товар по названию или коду 1С. Нажмите «Своя цена», введите целую цену без НДС и причину."],
        ["Почему у товара такая цена?", "Откройте карточку товара. Она показывает закупку, доставку, параметры, нижнюю границу, цены конкурентов и итоговые цены."],
        ["Можно изменить сразу несколько товаров?", "В разделе «Цены» откройте параметры выбранных товаров. Задайте фильтры, проверьте выбор и подтвердите пересчёт."],
        ["Когда цены попадут в 1С?", "На этом этапе автоматической отправки в 1С нет. Утвердите версию внутри системы и скачайте Excel."],
        ["Что если товар не классифицирован или отсутствует на сайте?", "Товар из Excel остаётся в расчёте с предупреждением. Без пригодных аналогов цена рассчитывается от закупочной стоимости при наличии необходимых параметров."],
      ].map(([q, a]) => <details key={q} className="ip-help-faq"><summary>{q}</summary><p>{a}</p></details>)}</section>
      <section className="ip-stack" style={{ gap: 8 }}><h3 id="sm-help-glossary">Словарь</h3><dl className="ip-help-glossary">{glossary.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}</dl></section>
    </div>
  </Drawer>;
}
