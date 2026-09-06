import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { useDropdownPosition } from "../../components/useDropdownPosition";
import { WordstatDemandAnalysis } from "./WordstatDemandAnalysis";
import "../seoAnalytics/seo_analytics.css";
import "./wordstat.css";
import "../spinner.css";

const FILTERS = [
  ["feature", "Категории"],
  ["category", "Подкатегории"],
  ["phrase", "Запросы"],
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

const MONTH_FIELDS = [
  "month_1",
  "month_2",
  "month_3",
  "month_4",
  "month_5",
  "month_6",
  "month_7",
  "month_8",
  "month_9",
  "month_10",
  "month_11",
  "month_12",
];

const MONTHS_FIELDS = [
  "monthS_1",
  "monthS_2",
  "monthS_3",
  "monthS_4",
  "monthS_5",
  "monthS_6",
  "monthS_7",
  "monthS_8",
  "monthS_9",
  "monthS_10",
  "monthS_11",
  "monthS_12",
];

const DEVICE_FIELDS = [
  "desktop",
  "phone",
  "tablet",
  "other_device",
];

const REGION_FIELDS = [
  "ekb_macroregion",
  "kras_macroregion",
  "mos_macroregion",
  "nign_macroregion",
  "novos_macroregion",
  "spb_macroregion",
  "sng_macroregion",
  "other_macroregion",
];

const QUARTER_FIELDS = [
  "quarter1",
  "quarter2",
  "quarter3",
  "quarter4",
];

function normalizeList(value) {
  if (!value) return [];

  if (Array.isArray(value)) {
    return value.filter((item) => item !== "" && item !== null && item !== undefined);
  }

  return [value].filter((item) => item !== "" && item !== null && item !== undefined);
}

function buildPayload(filters, page = null) {
  const payload = {};

  Object.entries(filters || {}).forEach(([key, value]) => {
    const values = normalizeList(value);

    if (values.length > 0) {
      payload[key] = values;
    }
  });

  if (page) {
    payload.page = page;
  }

  return payload;
}

function getCellColor(row, field, index) {
  if (field === "growth") {
    return row.growth_color || "";
  }

  if (MONTH_FIELDS.includes(field)) {
    return row.month_colors?.[index] || "";
  }

  if (MONTHS_FIELDS.includes(field)) {
    return row.monthS_colors?.[index] || "";
  }

  if (DEVICE_FIELDS.includes(field)) {
    return row.device_colors?.[field] || "";
  }

  if (REGION_FIELDS.includes(field)) {
    return row.region_colors?.[field] || "";
  }

  if (QUARTER_FIELDS.includes(field)) {
    return row.quarter_colors?.[index] || "";
  }

  return "";
}

function DataCell({ row, field, index, thick = false }) {
  const color = getCellColor(row, field, index);

  return (
    <td
      className={`${thick ? "b-thick " : ""}data-cell`}
      style={color ? { backgroundColor: color } : undefined}
    >
      {row[field] ?? ""}
    </td>
  );
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
    <div className={`wordstat-filter${open ? " wordstat-filter--open" : ""}`} ref={rootRef}>
      <label>{label}</label>
      <button
        type="button"
        className="wordstat-multiselect__control"
        aria-expanded={open}
        onClick={toggleMenu}
      >
        <span>{shownSelection.length ? `Выбрано: ${shownSelection.length}` : "Все"}</span>
        <i aria-hidden="true">▾</i>
      </button>
      {open && (
        <div ref={menuRef} className="wordstat-multiselect__menu" style={menuStyle}>
          <input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск…" />
          <div className="wordstat-multiselect__actions">
            <button type="button" disabled={!visibleOptions.length} onClick={selectVisible}>Выбрать найденные</button>
            <button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button>
          </div>
          <div className="wordstat-multiselect__options">
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

function WordstatTableRow({ row }) {
  const isFirst = Boolean(row.show_phrase);
  const isSummary = Boolean(row.is_summary);

  return (
    <tr
      className={`phrase-group ${isFirst ? "first-row" : ""} ${
        isSummary ? "summary-row" : ""
      }`}
    >
      {isFirst ? (
        <td className={`phrase-cell ${isSummary ? "summary-phrase" : ""}`}>
          {row.phrase}
        </td>
      ) : (
        <td className="phrase-cell empty-cell"></td>
      )}

      <td>{row.year ?? ""}</td>

      {MONTH_FIELDS.map((field, index) => (
        <DataCell
          key={field}
          row={row}
          field={field}
          index={index}
        />
      ))}

      <DataCell row={row} field="total" thick />
      <DataCell row={row} field="average" thick />
      <DataCell row={row} field="growth" thick />

      {DEVICE_FIELDS.map((field, index) => (
        <DataCell
          key={field}
          row={row}
          field={field}
          index={index}
          thick={index === 0}
        />
      ))}

      {REGION_FIELDS.map((field, index) => (
        <DataCell
          key={field}
          row={row}
          field={field}
          index={index}
          thick={index === 0}
        />
      ))}

      {MONTHS_FIELDS.map((field, index) => (
        <DataCell
          key={field}
          row={row}
          field={field}
          index={index}
          thick={index === 0}
        />
      ))}

      {QUARTER_FIELDS.map((field, index) => (
        <DataCell
          key={field}
          row={row}
          field={field}
          index={index}
          thick={index === 0}
        />
      ))}
    </tr>
  );
}

function WordstatHeader() {
  const months = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
  ];

  return (
    <thead>
      <tr className="trend-row">
        <th></th>
        <th></th>
        <th className="group-frequency" colSpan={15}>
          Частотность
        </th>
        <th className="b-thick group-devices" colSpan={4}>
          Устройства
        </th>
        <th className="b-thick group-regions" colSpan={8}>
          Регионы
        </th>
        <th className="b-thick group-season" colSpan={12}>
          Сезонность
        </th>
        <th className="b-thick group-coefficients" colSpan={4}>
          Коэффициенты, %
        </th>
      </tr>

      <tr className="header-row">
        <th>Запросы</th>
        <th>Год</th>

        {months.map((month) => (
          <th className="group-frequency" key={`freq-${month}`}>
            {month}
          </th>
        ))}

        <th className="b-thick">Сумма</th>
        <th className="b-thick">Среднее</th>
        <th className="b-thick">Годовой прирост, %</th>

        <th className="b-thick group-devices">ПК</th>
        <th className="group-devices">Телефоны</th>
        <th className="group-devices">Планшеты</th>
        <th className="group-devices">Прочее</th>

        <th className="b-thick group-regions">ЕКБ</th>
        <th className="group-regions">КРАС</th>
        <th className="group-regions">МСК</th>
        <th className="group-regions">НИЖК</th>
        <th className="group-regions">НОВС</th>
        <th className="group-regions">СПБ</th>
        <th className="group-regions">СНГ</th>
        <th className="group-regions">Прочее</th>

        {months.map((month, index) => (
          <th
            className={`${index === 0 ? "b-thick " : ""}group-season`}
            key={`season-${month}`}
          >
            {month}
          </th>
        ))}

        <th className="b-thick group-coefficients">Iкв</th>
        <th className="group-coefficients">IIкв</th>
        <th className="group-coefficients">IIIкв</th>
        <th className="group-coefficients">IVкв</th>
      </tr>
    </thead>
  );
}

function WordstatStatistics({ data }) {
  const wrapperRef = useRef(null);

  const [rows, setRows] = useState(data?.rows || []);
  const [pagination, setPagination] = useState(data?.pagination || {});
  const [filterValues, setFilterValues] = useState(data?.filter_values || {});

  const [localFilters, setLocalFilters] = useState({
    feature: normalizeList(data?.filters?.feature),
    category: normalizeList(data?.filters?.category),
    phrase: normalizeList(data?.filters?.phrase),
  });

  const [isApplyingFilters, setIsApplyingFilters] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setRows(data?.rows || []);
    setPagination(data?.pagination || {});
    setFilterValues(data?.filter_values || {});

    setLocalFilters({
      feature: normalizeList(data?.filters?.feature),
      category: normalizeList(data?.filters?.category),
      phrase: normalizeList(data?.filters?.phrase),
    });
  }, [data]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const currentFilters = useMemo(
    () => ({
      feature: localFilters.feature || [],
      category: localFilters.category || [],
      phrase: localFilters.phrase || [],
    }),
    [localFilters]
  );

  async function fetchWordstat(nextFilters, page = 1, append = false) {
    const payload = buildPayload(nextFilters, page);

    const response = await api.post(
      "/v1/dashboards/builder/wordstat/",
      payload
    );

    const widget = response.data?.widgets?.find(
      (item) => item.type === "yd_wordstat_table"
    );

    const nextData = widget?.data;

    if (!nextData) return;

    if (append) {
      setRows((prev) => [...prev, ...(nextData.rows || [])]);
    } else {
      setRows(nextData.rows || []);

      if (wrapperRef.current) {
        wrapperRef.current.scrollTop = 0;
      }
    }

    setPagination(nextData.pagination || {});
    setFilterValues(nextData.filter_values || {});
  }

  async function applyFilters(next = currentFilters) {
    setIsApplyingFilters(true);

    try {
      await fetchWordstat(next, 1, false);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  async function resetFilters() {
    const next = {
      feature: [],
      category: [],
      phrase: [],
    };

    setLocalFilters(next);
    setIsApplyingFilters(true);

    try {
      await fetchWordstat(next, 1, false);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  async function loadNextPage() {
    if (isLoadingMore || isApplyingFilters || !pagination?.has_next) return;

    const nextPage = pagination.next_page;

    if (!nextPage) return;

    setIsLoadingMore(true);

    try {
      await fetchWordstat(currentFilters, nextPage, true);
    } finally {
      setIsLoadingMore(false);
    }
  }

  function handleScroll(event) {
    const element = event.currentTarget;

    const scrollBottom = element.scrollTop + element.clientHeight;
    const threshold = element.scrollHeight - 80;

    if (scrollBottom >= threshold) {
      loadNextPage();
    }
  }

  async function exportExcel() {
    setIsExporting(true);

    try {
      const payload = buildPayload(currentFilters);

      const response = await api.post(
        "/v1/datasets/yd-wordstat/export/",
        payload,
        {
          responseType: "blob",
        }
      );

      const blobUrl = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = blobUrl;
      link.download = `wordstat_${new Date().toISOString().slice(0, 10)}.xlsx`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(blobUrl);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="wordstat-dashboard">

      <form id="filterForm" onSubmit={(event) => event.preventDefault()}>
        <div className="wordstat-filter-grid">
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
        </div>

        <div className="wordstat-filter-actions">
          <button
            type="button"
            className="filters-export"
            onClick={exportExcel}
            disabled={isExporting || isApplyingFilters}
          >
            {isExporting ? "Экспорт..." : "Экспорт"}
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

      <div
        ref={wrapperRef}
        className="gantt-table-wrapper"
        onScroll={handleScroll}
      >
        <table id="head">
          <WordstatHeader />

          <tbody id="projectsTableBody">
            {rows.map((row, index) => (
              <WordstatTableRow
                key={`${row.phrase || "empty"}-${row.year || "year"}-${index}`}
                row={row}
              />
            ))}
          </tbody>
        </table>

        {isLoadingMore && (
          <div id="infiniteSpinner" className="infinite-spinner"></div>
        )}
      </div>
      {isApplyingFilters && <GlobalSpinner />}
    </div>
  );
}

export function WordstatDashboard({ data, publicToken = null }) {
  const [tab, setTab] = useState("demand");
  return <section className="seo-dashboard wd-dashboard" data-dashboard-type="wordstat">
    <h2 className="wd-title">Тренды и сезонность</h2>
    <nav className="wd-tabs" aria-label="Разделы Wordstat">
      <button type="button" className={tab === "demand" ? "is-active" : ""} aria-pressed={tab === "demand"} onClick={() => setTab("demand")}>Анализ спроса</button>
      <button type="button" className={tab === "statistics" ? "is-active" : ""} aria-pressed={tab === "statistics"} onClick={() => setTab("statistics")}>Статистика запросов</button>
    </nav>
    <div hidden={tab !== "demand"}><WordstatDemandAnalysis publicToken={publicToken} revision={data} active={tab === "demand"} /></div>
    <div hidden={tab !== "statistics"}><WordstatStatistics data={data} /></div>
  </section>;
}
