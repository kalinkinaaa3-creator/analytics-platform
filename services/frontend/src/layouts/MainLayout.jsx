import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";
import "../styles/list_base.css";

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

      <div className="sidebar" id="sidebar">
        <button
          className="toggle-btn"
          onClick={(event) => {
            event.stopPropagation();
            toggleSidebar();
          }}
        ></button>

        <div className="user-info">
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
          Выход
        </button>
      </div>

      <div className="content">
        <Outlet />
      </div>
    </div>
  );
}
