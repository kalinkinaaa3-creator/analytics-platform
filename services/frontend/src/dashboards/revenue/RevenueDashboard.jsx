import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import "../spinner.css";
import "./revenue.css";
import { RevenueCharts } from "./RevenueCharts";

const FILTERS = [
  ["direction", "Направление", "filter--sm"],
  ["project", "Проект", "filter--md"],
  ["manager", "Менеджер", "filter--md"],
  ["partner", "Контрагент", "filter--xl"],
  ["consignee", "Грузополучатель", "filter--xl"],
  ["nom_view", "Вид продукции", "filter--sm"],
  ["nom_category", "Категория", "filter--sm"],
  ["nom_group", "Группа", "filter--sm"],
  ["nom", "Номенклатура", "filter--xll"],
  ["nom_code", "Код", "filter--smm"],
];

function GlobalSpinner() {
  return (
    <div className="global-spinner-overlay show">
      <div className="spinner-container">
        <div className="infinite-spinner"></div>
        <div className="spinner-text">Загрузка данных...</div>
      </div>
    </div>
  );
}

function normalizeList(value) {
  if (!value) return [];

  if (Array.isArray(value)) {
    return value.filter(
      (item) => item !== "" && item !== null && item !== undefined
    );
  }

  return [value].filter(
    (item) => item !== "" && item !== null && item !== undefined
  );
}

function buildPayload(filters) {
  const payload = {};

  Object.entries(filters || {}).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      const values = normalizeList(value);

      if (values.length > 0) {
        payload[key] = values;
      }

      return;
    }

    if (value !== "" && value !== null && value !== undefined) {
      payload[key] = value;
    }
  });

  return payload;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";

  const number = Number(value);

  if (Number.isNaN(number)) return value;

  return number.toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function Toast({ message }) {
  if (!message) return null;

  return <div id="toast">{message}</div>;
}

function MultiSelect({ name, label, options, selected, onChange, onApply, className = "" }) {
  const rootRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState(false);

  const safeOptions = options || [];
  const safeSelected = selected || [];

  const selectedSet = useMemo(() => new Set(safeSelected), [safeSelected]);

  const visibleOptions = useMemo(() => {
    const q = search.trim().toLowerCase();

    if (!q) return safeOptions;

    return safeOptions.filter((item) =>
      String(item).toLowerCase().includes(q)
    );
  }, [safeOptions, search]);

  const allVisibleSelected =
    visibleOptions.length > 0 &&
    visibleOptions.every((item) => selectedSet.has(item));

  useEffect(() => {
    function handleDocumentClick(event) {
      if (!rootRef.current) return;

      if (!rootRef.current.contains(event.target)) {
        setOpen(false);
        setSearch("");

        if (pending) {
          setPending(false);
          onApply();
        }
      }
    }

    document.addEventListener("mousedown", handleDocumentClick);

    return () => {
      document.removeEventListener("mousedown", handleDocumentClick);
    };
  }, [pending, onApply]);

  function updateSelected(next) {
    onChange(next);
    setPending(true);
  }

  function toggleItem(item) {
    if (selectedSet.has(item)) {
      updateSelected(safeSelected.filter((value) => value !== item));
      return;
    }

    updateSelected([...safeSelected, item]);
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      updateSelected(
        safeSelected.filter((item) => !visibleOptions.includes(item))
      );
      return;
    }

    updateSelected(Array.from(new Set([...safeSelected, ...visibleOptions])));
  }

  function removeItem(item) {
    updateSelected(safeSelected.filter((value) => value !== item));
  }

  function handleInputKeyDown(event) {
    if (event.key !== "Enter") return;

    event.preventDefault();

    const value = search.trim();

    if (!value) return;

    if (!selectedSet.has(value)) {
      updateSelected([...safeSelected, value]);
    }

    setSearch("");
  }

  function renderSelectedTags() {
    if (safeSelected.length === 0) return null;

    if (safeSelected.length > 1) {
      return <div className="tag">...</div>;
    }

    return (
      <div className="tag">
        {safeSelected[0]}
        <button type="button" onClick={() => removeItem(safeSelected[0])}>
          ×
        </button>
      </div>
    );
  }

  return (
    <div className={`filter ${className}`}>
      <label htmlFor={`filter_${name}_list`}>{label}</label>

      <div
        ref={rootRef}
        className={`multi-select ${open ? "open" : ""}`}
        id={`multiSelect_${name}`}
      >
        <div className="top-bar">
          <div className="selected-items">{renderSelectedTags()}</div>

          <input
            type="text"
            id={`filter_${name}_list`}
            name={name}
            value={search}
            onFocus={() => setOpen(true)}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder=""
          />
        </div>

        <div className="dropdown">
          <div className="dropdown-item select-all">
            <label>
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleAllVisible}
              />
              <span>Выбрать все</span>
            </label>
          </div>

          {visibleOptions.map((item) => (
            <div className="dropdown-item" key={item}>
              <label>
                <input
                  type="checkbox"
                  checked={selectedSet.has(item)}
                  onChange={() => toggleItem(item)}
                />
                <span>{item}</span>
              </label>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value }) {
  return (
    <div className="indicator-card">
      <div className="title">{title}</div>
      <div className="value">{formatNumber(value)}</div>
    </div>
  );
}

function RevenueIndicators({ kpi }) {
  return (
    <div id="indicators-container">
      <div className="indicators-container revenue-indicators-grid">
        <div className="indicators-column">
          <KpiCard title="Выручка, руб" value={Math.round(Number(kpi?.revenue || 0))} />
          <KpiCard title="Количество, шт" value={kpi?.quantity} />
        </div>

        <div className="indicators-column"> 
          <KpiCard title="Вес, кг" value={Math.round(Number(kpi?.weight_total || 0))} />
          <KpiCard title="Клиенты, шт" value={kpi?.clients} />
        </div>

        <div className="indicators-column">
          <KpiCard title="Отгрузки, шт (реализации)" value={kpi?.shipments} />
          <KpiCard title="SKU, шт" value={kpi?.sku} />
        </div>
      </div>
    </div>
  );
}

export function RevenueDashboard({ data }) {
  const [dashboardData, setDashboardData] = useState(data || {});
  const [isApplyingFilters, setIsApplyingFilters] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState("");

  const filters = dashboardData?.filters || {};
  const filterValues = dashboardData?.filter_values || {};
  const kpi = dashboardData?.kpi || {};
  const charts = dashboardData?.charts || {};

  const lastUpdate = dashboardData?.last_update || null;

  const refreshTitle = lastUpdate
    ? `Данные актуальны на: ${lastUpdate}`
    : "Данные отсутствуют";


    const defaultFilters = useMemo(() => ({
    direction: [],
    project: [],
    manager: [],
    partner: [],
    consignee: [],
    nom_view: [],
    nom_category: [],
    nom_group: [],
    nom: [],
    nom_code: [],
    date_start: "",
    date_end: "",
    }), []);

  const [localFilters, setLocalFilters] = useState({
    direction: normalizeList(filters.direction),
    project: normalizeList(filters.project),
    manager: normalizeList(filters.manager),
    partner: normalizeList(filters.partner),
    consignee: normalizeList(filters.consignee),
    nom_view: normalizeList(filters.nom_view),
    nom_category: normalizeList(filters.nom_category),
    nom_group: normalizeList(filters.nom_group),
    nom: normalizeList(filters.nom),
    nom_code: normalizeList(filters.nom_code),
    date_start: filters.date_start || "",
    date_end: filters.date_end || "",
  });

  useEffect(() => {
    setDashboardData(data || {});
  }, [data]);

  useEffect(() => {
    setLocalFilters({
      direction: normalizeList(filters.direction),
      project: normalizeList(filters.project),
      manager: normalizeList(filters.manager),
      partner: normalizeList(filters.partner),
      consignee: normalizeList(filters.consignee),
      nom_view: normalizeList(filters.nom_view),
      nom_category: normalizeList(filters.nom_category),
      nom_group: normalizeList(filters.nom_group),
      nom: normalizeList(filters.nom),
      nom_code: normalizeList(filters.nom_code),
      date_start: filters.date_start || "",
      date_end: filters.date_end || "",
    });
  }, [filters]);

  const currentFilters = useMemo(
    () => ({
      direction: localFilters.direction || [],
      project: localFilters.project || [],
      manager: localFilters.manager || [],
      partner: localFilters.partner || [],
      consignee: localFilters.consignee || [],
      nom_view: localFilters.nom_view || [],
      nom_category: localFilters.nom_category || [],
      nom_group: localFilters.nom_group || [],
      nom: localFilters.nom || [],
      nom_code: localFilters.nom_code || [],
      date_start: localFilters.date_start || "",
      date_end: localFilters.date_end || "",
    }),
    [localFilters]
  );

  function showToast(message) {
    setToast(message);

    setTimeout(() => {
      setToast("");
    }, 2500);
  }

  function changeFilter(name, value) {
    setLocalFilters((prev) => ({
      ...prev,
      [name]: value,
    }));
  }

  async function fetchRevenue(nextFilters) {
    const payload = buildPayload(nextFilters);

    const response = await api.post("/v1/dashboards/builder/revenue/", payload);

    const widget = response.data?.widgets?.find(
      (item) => item.type === "revenue_dashboard"
    );

    const nextData = widget?.data;

    if (!nextData) return;

    setDashboardData(nextData);
  }

  async function applyFilters(next = currentFilters) {
    setIsApplyingFilters(true);

    try {
      await fetchRevenue(next);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  const applyFiltersFromDom = useCallback(() => {
    const form = document.getElementById("filterForm");

    if (!form) return;

    const formData = new FormData(form);

    const next = {
      ...currentFilters,
      date_start: formData.get("date_start") || "",
      date_end: formData.get("date_end") || "",
    };

    setLocalFilters(next);
    applyFilters(next);
  }, [currentFilters]);

  useEffect(() => {
    const ids = ["date_start_filter", "date_end_filter"];

    ids.forEach((id) => {
      const element = document.getElementById(id);

      if (element) {
        element.addEventListener("change", applyFiltersFromDom);
      }
    });

    return () => {
      ids.forEach((id) => {
        const element = document.getElementById(id);

        if (element) {
          element.removeEventListener("change", applyFiltersFromDom);
        }
      });
    };
  }, [applyFiltersFromDom]);

  async function resetFilters() {
    setLocalFilters(defaultFilters);
    setIsApplyingFilters(true);

    try {
      await fetchRevenue(defaultFilters);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  async function exportExcel() {
    setExporting(true);

    try {
      const response = await api.post(
        "/v1/datasets/revenue/export/",
        buildPayload(currentFilters),
        {
          responseType: "blob",
        }
      );

      const blobUrl = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = blobUrl;
      link.download = `revenue_${new Date().toISOString().slice(0, 10)}.xlsx`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(blobUrl);
    } finally {
      setExporting(false);
    }
  }

  async function refreshSales() {
    setRefreshing(true);

    try {
      await api.post("/v1/datasets/sales/refresh/");
      showToast("Данные обновлены");
    } catch (error) {
      const status = error.response?.status;

      if (status === 429) {
        showToast(
          error.response?.data?.message ||
          "Обновление данных уже выполнено за текущий час"
        );
      } else if (status === 504) {
        showToast("Обновление выполняется. Данные обновятся после завершения");
      } else if (status === 401) {
        showToast("Сессия истекла. Войдите заново");
      } else if (status === 403) {
        showToast("Нет прав на обновление данных");
      } else {
        showToast("Ошибка обновления данных");
      }
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="revenue-dashboard">
      <Toast message={toast} />

      <h2>Динамика выручки</h2>

      <form id="filterForm">
        {FILTERS.map(([name, label, className]) => (
          <MultiSelect
            key={name}
            name={name}
            label={label}
            options={filterValues[name] || []}
            selected={localFilters[name] || []}
            onChange={(value) => changeFilter(name, value)}
            onApply={() => applyFilters()}
            className={className}
          />
        ))}

        <div className="filter">
          <label htmlFor="date_start_filter">Дата начала</label>
          <input
            type="date"
            id="date_start_filter"
            name="date_start"
            value={localFilters.date_start || ""}
            onChange={(event) =>
              setLocalFilters((prev) => ({
                ...prev,
                date_start: event.target.value,
              }))
            }
            disabled={isApplyingFilters}
          />
        </div>

        <div className="filter">
          <label htmlFor="date_end_filter">Дата окончания</label>
          <input
            type="date"
            id="date_end_filter"
            name="date_end"
            value={localFilters.date_end || ""}
            onChange={(event) =>
              setLocalFilters((prev) => ({
                ...prev,
                date_end: event.target.value,
              }))
            }
            disabled={isApplyingFilters}
          />
        </div>

        <div className="filters-actions">
          <button
            type="button"
            className="filters-export"
            onClick={exportExcel}
            disabled={exporting || isApplyingFilters}
          >
            {exporting ? "Экспорт..." : "Экспорт"}
          </button>

          <button
            type="button"
            className="filters-export"
            onClick={refreshSales}
            disabled={refreshing}
            title={refreshTitle}
          >
            {refreshing ? "Обновление..." : "Обновить"}
          </button>

          <button
            type="button"
            id="resetFilters"
            className="filters-reset"
            onClick={resetFilters}
            disabled={isApplyingFilters}
          >
            Очистить
          </button>
        </div>
      </form>

      <RevenueIndicators kpi={kpi} />

      <RevenueCharts charts={charts} />

      {isApplyingFilters && <GlobalSpinner />}
    </div>
  );
}