import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";
import "../styles/list_base.css";

function DashboardIcon({ name }) {
  const icons = {
    projects: (
      <>
        <rect x="4" y="5" width="16" height="14" rx="2" />
        <path d="M8 5V3h8v2" />
        <path d="M4 10h16" />
      </>
    ),

    revenue: (
      <>
        <path d="M4 19V13" />
        <path d="M9 19V9" />
        <path d="M14 19V12" />
        <path d="M19 19V5" />
      </>
    ),

    trends: (
      <>
        <path d="M3 17l6-6 4 4 8-9" />
        <path d="M16 6h5v5" />
      </>
    ),

    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="M15 15l6 6" />
      </>
    ),

    advertising: (
      <>
        <path d="M4 11v4" />
        <path d="M4 11l12-5v14L4 15" />
        <path d="M8 15l2 5" />
      </>
    ),

    leads: (
      <>
        <circle cx="9" cy="8" r="3" />
        <circle cx="17" cy="9" r="2.5" />
        <path d="M3 20c0-4 2.5-6 6-6s6 2 6 6" />
        <path d="M14 15c3.5 0 6 1.5 6 5" />
      </>
    ),

    purchases: (
      <>
        <path d="M4 8h16l-2 11H6z" />
        <path d="M8 8l4-5 4 5" />
      </>
    ),

    receivables: (
      <>
        <path d="M6 3h9l4 4v14H6z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6" />
        <path d="M9 17h5" />
      </>
    ),

    stock: (
      <>
        <path d="M5 6c0-2 14-2 14 0s-14 2-14 0z" />
        <path d="M5 6v6c0 2 14 2 14 0V6" />
        <path d="M5 12v6c0 2 14 2 14 0v-6" />
      </>
    ),

    sales: (
      <>
        <path d="M4 20V11h4v9" />
        <path d="M10 20V5h4v15" />
        <path d="M16 20V8h4v12" />
      </>
    ),

    crm: (
      <>
        <circle cx="9" cy="8" r="3" />
        <circle cx="17" cy="9" r="2.5" />
        <path d="M3 20c0-4 2.5-6 6-6s6 2 6 6" />
        <path d="M14 15c3.5 0 6 1.5 6 5" />
      </>
    ),
  };

  if (!icons[name]) {
    return null;
  }

  return (
    <svg
      className="dashboard-menu-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      {icons[name]}
    </svg>
  );
}

function isSectionLink(item) {
  return (
    item.navigation_type === "section_link"
    || item.id === "iprice"
  );
}

export function MainLayout() {
  const { logout, username } = useAuth();
  const navigate = useNavigate();

  const [sections, setSections] = useState({});

  useEffect(() => {
    async function loadMenu() {
      try {
        const response = await api.get("/v1/dashboards/menu/");
        setSections(response.data.sections || {});
      } catch (error) {
        if (error.response?.status === 401) {
          logout();
          navigate("/login");
        }
      }
    }

    loadMenu();
  }, [logout, navigate]);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  function toggleSidebar() {
    document.getElementById("sidebar")?.classList.toggle("open");
  }

  function toggleSubmenu(event) {
    const title = event.currentTarget;
    const submenu = title.nextElementSibling;

    submenu?.classList.toggle("collapsed");
    title.classList.toggle("collapsed");
  }

  useEffect(() => {
    const sidebar = document.getElementById("sidebar");
    const toggleBtn = document.getElementById("toggleBtn");

    function handleDocumentClick(event) {
      if (
        sidebar &&
        toggleBtn &&
        !sidebar.contains(event.target) &&
        !toggleBtn.contains(event.target)
      ) {
        sidebar.classList.remove("open");
      }
    }

    document.addEventListener("click", handleDocumentClick);

    return () => {
      document.removeEventListener("click", handleDocumentClick);
    };
  }, []);

  return (
    <div className="app-shell">
      <button
        className="sidebar-toggle-btn"
        id="toggleBtn"
        title="Меню"
        onClick={(event) => {
          event.stopPropagation();
          toggleSidebar();
        }}
      >
        ☰
      </button>

      <div className="sidebar open" id="sidebar">
        <button
          className="toggle-btn"
          onClick={(event) => {
            event.stopPropagation();
            toggleSidebar();
          }}
        ></button>

        <div className="user-info">
          <svg className="user-info-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4.5 3.2-7 8-7s8 2.5 8 7" />
          </svg>

          <span>{username || "Пользователь"}</span>
        </div>

        <div className="sections-container">
          {Object.entries(sections).map(([group, items]) => {
            const sectionLinks = items.filter(
              isSectionLink
            );
            const submenuItems = items.filter(
              (item) => !isSectionLink(item)
            );

            return (
              <div className="section" key={group}>
                {sectionLinks.map((item) => (
                  <NavLink
                    to={item.url}
                    key={item.id}
                    className={({ isActive }) => [
                      "section-title",
                      "section-title--link",
                      isActive ? "active" : "",
                    ].filter(Boolean).join(" ")}
                  >
                    <span className="section-icon">
                      {item.icon}&nbsp;
                    </span>
                    {item.name}
                  </NavLink>
                ))}

                {submenuItems.length > 0 && (
                  <>
                    <div className="section-title" onClick={toggleSubmenu}>
                      <span className="arrow"></span>
                      <span className="section-icon">🗁&nbsp;</span>
                      {group}
                    </div>

                    <div className="submenu">
                      {submenuItems.map((item) => (
                        <NavLink
                          to={item.url}
                          key={item.id}
                          className={({ isActive }) => (
                            isActive ? "active" : ""
                          )}
                        >
                          <DashboardIcon name={item.icon} />
                          <span className="text">{item.name}</span>
                        </NavLink>
                      ))}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>

        <button type="button" className="logout-btn" onClick={handleLogout}>
          <svg
            className="logout-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M10 5H5v14h5" />
            <path d="M14 8l4 4-4 4" />
            <path d="M18 12H9" />
          </svg>
          <span>Выход</span>
        </button>
      </div>

      <div className="content">
        <Outlet />
      </div>
    </div>
  );
}
