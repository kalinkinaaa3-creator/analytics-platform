import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import "../styles/list_base.css";

export function PublicLayout() {
  const { token } = useParams();
  const navigate = useNavigate();

  const [groupName, setGroupName] = useState("");
  const [sections, setSections] = useState({});

  useEffect(() => {
    async function loadPublicGroup() {
      const response = await api.get(`/v1/dashboards/public-group/${token}/`);

      setGroupName(response.data.group_name || "Публичный доступ");
      setSections(response.data.sections || {});

      const firstSection = Object.values(response.data.sections || {})[0];
      const firstDashboard = firstSection?.[0];

      if (
        firstDashboard &&
        (
          window.location.pathname === `/public/${token}` ||
          window.location.pathname === `/public-group/${token}`
        )
      ) {
        navigate(`/public/${token}/dashboards/${firstDashboard.dashboard_slug}`, {
          replace: true,
        });
      }
    }

    loadPublicGroup();
  }, [token, navigate]);

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
          <span>{groupName || "Публичный доступ"}</span>
        </div>

        <div className="sections-container">
          {Object.entries(sections).map(([sectionName, items]) => (
            <div className="section" key={sectionName}>
              <div className="section-title" onClick={toggleSubmenu}>
                <span className="arrow"></span>
                <span className="section-icon">🗁&nbsp;</span>
                {sectionName}
              </div>

              <div className="submenu">
                {items.map((item) => (
                  <NavLink
                    to={`/public/${token}/dashboards/${item.dashboard_slug}`}
                    key={item.dashboard_slug}
                    className={({ isActive }) => (isActive ? "active" : "")}
                  >
                    <span className="text">{item.name}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="content">
        <Outlet />
      </div>
    </div>
  );
}