import { Link, useOutletContext } from "react-router-dom";
import "./select-market.css";

export function SelectMarketIcon({ type }) {
  return <svg className="sm-system-icon" width="48" height="48" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="#E1EDF8" />
    {type === "sps" ? <>
      <rect x="5" y="17" width="4" height="7" rx="1" fill="#3F72AA" />
      <rect x="11" y="14" width="4" height="10" rx="1" fill="#3F72AA" />
      <rect x="17" y="11" width="4" height="13" rx="1" fill="#3F72AA" />
      <rect x="23" y="8" width="4" height="16" rx="1" fill="#F39F63" />
    </> : <>
      <polygon points="6,16 12,9 26,9 26,23 12,23" fill="#3F72AA" stroke="#3F72AA" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="10.4" cy="16" r="1.8" fill="#F39F63" />
      <path d="M17.5 20.6V11.5H20.5A2.5 2.5 0 0 1 20.5 16.5H16M16 18.6H21.2" fill="none" stroke="#E1EDF8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </>}
  </svg>;
}

export function SelectMarketHome() {
  const { sections, organization, menuStatus } = useOutletContext();
  const items = Object.values(sections).flat();
  return <section className="sm-home" aria-labelledby="sm-home-title">
    <header className="sm-home-heading">
      <span className="sm-eyebrow">Рабочее пространство</span>
      <h1 id="sm-home-title">{organization.name}</h1>
      <p>Выберите систему для работы</p>
    </header>
    <nav className="sm-system-grid" aria-label="Доступные системы">
      {items.map((item) => <Link className="sm-system-card" key={item.id} to={item.url}>
        <SelectMarketIcon type={item.component} />
        <span className="sm-system-copy">
          <strong>{item.component === "sps" ? "СПС" : item.component === "suc" ? "СУЦ" : item.name}</strong>
          <span>{item.name}</span>
        </span>
        <svg className="sm-system-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
      </Link>)}
    </nav>
    {menuStatus === "loading" && <p className="sm-empty" role="status">Загружаем разделы…</p>}
    {menuStatus === "error" && <p className="sm-empty" role="alert">Не удалось загрузить разделы. Обновите страницу.</p>}
    {menuStatus === "ready" && items.length === 0 && <p className="sm-empty">Доступные разделы появятся после назначения прав администратором.</p>}
  </section>;
}

export function SelectMarketSystem({ dashboard }) {
  return <section className="sm-system-page" aria-labelledby="sm-system-title">
    <Link className="sm-back-link" to="/">← Главная</Link>
    <div className="sm-system-heading"><SelectMarketIcon type={dashboard.component} /><h1 id="sm-system-title">{dashboard.name}</h1></div>
    <div className="sm-system-empty"><h2>Раздел готовится</h2><p>Данные и инструменты появятся после подключения системы.</p></div>
  </section>;
}
