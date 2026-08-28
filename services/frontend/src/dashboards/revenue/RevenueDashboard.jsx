import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { DateRangePicker } from "../../components/DateRangePicker";
import { useDropdownPosition } from "../../components/useDropdownPosition";
import "../spinner.css";
import "./revenue.css";
import { RevenueCharts } from "./RevenueCharts";

const FILTERS = [
  ["direction", "Направление"],
  ["project", "Проект"],
  ["manager", "Менеджер"],
  ["partner", "Контрагент"],
  ["consignee", "Грузополучатель"],
  ["nom_view", "Вид продукции"],
  ["nom_category", "Категория"],
  ["nom_group", "Группа"],
  ["nom", "Номенклатура"],
  ["nom_code", "Код"],
  ["nom_hier", "Номенклатура (группировка)"],
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

function localIsoDate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
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

function MultiSelect({ label, options, selected, onApply }) {
  const rootRef = useRef(null);
  const menuRef = useRef(null);
  const selectedRef = useRef(selected);
  const draftRef = useRef(selected);
  const onApplyRef = useRef(onApply);
  const openRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(selected);
  const [search, setSearch] = useState("");

  const safeOptions = useMemo(() => options || [], [options]);
  const safeSelected = useMemo(() => normalizeList(selected), [selected]);

  useEffect(() => {
    selectedRef.current = safeSelected;
    onApplyRef.current = onApply;
    if (!open) draftRef.current = safeSelected;
  }, [safeSelected, onApply, open]);

  const visibleOptions = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("ru-RU");

    if (!q) return safeOptions;

    return safeOptions.filter((item) =>
      String(item).toLocaleLowerCase("ru-RU").includes(q)
    );
  }, [safeOptions, search]);

  function updateDraft(next) {
    draftRef.current = next;
    setDraft(next);
  }

  function commit() {
    const current = selectedRef.current;
    const next = draftRef.current;
    if (current.length !== next.length || current.some((value, index) => value !== next[index])) {
      onApplyRef.current(next);
    }
  }

  function closeMenu() {
    commit();
    openRef.current = false;
    setOpen(false);
    setSearch("");
  }

  useEffect(() => {
    function handleDocumentClick(event) {
      if (openRef.current && !rootRef.current?.contains(event.target)) {
        const current = selectedRef.current;
        const next = draftRef.current;
        if (current.length !== next.length || current.some((value, index) => value !== next[index])) {
          onApplyRef.current(next);
        }
        openRef.current = false;
        setOpen(false);
        setSearch("");
      }
    }

    document.addEventListener("mousedown", handleDocumentClick);

    return () => {
      document.removeEventListener("mousedown", handleDocumentClick);
    };
  }, []);

  const { menuStyle, resetPosition } = useDropdownPosition({
    open,
    rootRef,
    menuRef,
    contentKey: `${visibleOptions.length}:${search}`,
  });

  function toggleMenu() {
    if (open) {
      closeMenu();
      return;
    }
    updateDraft(safeSelected);
    resetPosition();
    openRef.current = true;
    setOpen(true);
  }

  function toggleItem(item) {
    updateDraft(draft.includes(item) ? draft.filter((value) => value !== item) : [...draft, item]);
  }

  function selectVisible() {
    updateDraft([...new Set([...draft, ...visibleOptions])]);
  }

  const shownSelection = open ? draft : safeSelected;

  return (
    <div className={`revenue-filter${open ? " revenue-filter--open" : ""}`} ref={rootRef}>
      <label>{label}</label>
      <button
        type="button"
        className="revenue-multiselect__control"
        aria-expanded={open}
        onClick={toggleMenu}
      >
        <span>{shownSelection.length ? `Выбрано: ${shownSelection.length}` : "Все"}</span>
        <i aria-hidden="true">▾</i>
      </button>
      {open && (
        <div ref={menuRef} className="revenue-multiselect__menu" style={menuStyle}>
          <input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск…" />
          <div className="revenue-multiselect__actions">
            <button type="button" disabled={!visibleOptions.length} onClick={selectVisible}>Выбрать найденные</button>
            <button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button>
          </div>
          <div className="revenue-multiselect__options">
            {visibleOptions.map((item) => (
              <label key={item}>
                <input type="checkbox" checked={draft.includes(item)} onChange={() => toggleItem(item)} />
                <span>{item}</span>
              </label>
            ))}
            {!visibleOptions.length && <p>Нет значений</p>}
          </div>
        </div>
      )}
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

  const filters = useMemo(() => dashboardData?.filters || {}, [dashboardData?.filters]);
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
    nom_hier: [],
    date_start: `${new Date().getFullYear()}-01-01`,
    date_end: localIsoDate(),
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
    nom_hier: normalizeList(filters.nom_hier),
    date_start: filters.date_start || "",
    date_end: filters.date_end || "",
  });

  /* eslint-disable react-hooks/set-state-in-effect */
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
      nom_hier: normalizeList(filters.nom_hier),
      date_start: filters.date_start || "",
      date_end: filters.date_end || "",
    });
  }, [filters]);
  /* eslint-enable react-hooks/set-state-in-effect */

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
      nom_hier: localFilters.nom_hier || [],
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

      <form id="filterForm" onSubmit={(event) => event.preventDefault()}>
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

        <div className="revenue-filter-grid">
          {FILTERS.map(([name, label]) => (
            <MultiSelect
              key={name}
              label={label}
              options={filterValues[name] || []}
              selected={localFilters[name] || []}
              onApply={(value) => {
                const next = { ...currentFilters, [name]: value };
                setLocalFilters(next);
                applyFilters(next);
              }}
            />
          ))}

          <DateRangePicker
            key={`${localFilters.date_start}:${localFilters.date_end}`}
            start={localFilters.date_start}
            end={localFilters.date_end}
            resetRange={{
              start: `${new Date().getFullYear()}-01-01`,
              end: localIsoDate(),
            }}
            onChange={({ start, end }) => {
              const next = { ...currentFilters, date_start: start, date_end: end };
              setLocalFilters(next);
              applyFilters(next);
            }}
          />
        </div>
      </form>

      <RevenueIndicators kpi={kpi} />

      <RevenueCharts charts={charts} />

      {isApplyingFilters && <GlobalSpinner />}
    </div>
  );
}
