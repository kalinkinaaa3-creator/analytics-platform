import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import "../spinner.css";
import "./turnover.css";

const FILTERS = [
  ["nomenclature", "Номенклатура"],
  ["warehouse_group", "Группа складов"],
  ["warehouse", "Склад"],
  ["quantity", "Качество"],
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

function normalizePoint(point) {
  return {
    x: Number(point?.x || 0),
    y: Number(point?.y || 0),
    value: point?.value,
  };
}

function makeLinePath(points) {
  const cleanPoints = (points || []).map(normalizePoint);

  if (!cleanPoints.length) return "";

  return cleanPoints
    .map((point, index) => {
      const x = point.x * 100;
      const y = (1 - point.y) * 100;

      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function makeAreaPath(points) {
  const cleanPoints = (points || []).map(normalizePoint);

  if (!cleanPoints.length) return "";

  const line = makeLinePath(cleanPoints);
  const firstX = cleanPoints[0].x * 100;
  const lastX = cleanPoints[cleanPoints.length - 1].x * 100;

  return `${line} L ${lastX} 100 L ${firstX} 100 Z`;
}

function shouldShowXLabel(total, index) {
  if (total <= 8) return true;
  if (total <= 16) return index % 2 === 0;
  if (total <= 28) return index % 3 === 0;

  return index % 4 === 0;
}

function MultiSelect({ name, label, options, selected, onChange, onApply }) {
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
    <div className="filter">
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

          <div>
            {visibleOptions.map((item) => (
              <div className="dropdown-item" key={item}>
                <label>
                  <input
                    type="checkbox"
                    value={item}
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
    </div>
  );
}

function TurnoverIndicators({ indicators }) {
  return (
    <div id="indicators-container">
      <div className="indicators-container">
        <div className="indicators-column">
          <div className="indicator-card">
            <div className="title">Факт, руб</div>
            <div className="value" id="indicator-cost">
              {formatNumber(indicators?.cost)}
            </div>
          </div>
        </div>

        <div className="indicators-column">
          <div className="indicator-card deviation-card">
            <div className="title">Отклонение, руб</div>
            <div
              className={`value deviation ${indicators?.deviation_color || ""}`}
              id="indicator-deviation"
            >
              {formatNumber(indicators?.deviation)}
            </div>
          </div>
        </div>

        <div className="indicators-column">
          <div className="indicator-card">
            <div className="title">План, руб</div>
            <div className="value" id="indicator-plan">
              {formatNumber(indicators?.indicator)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TurnoverChart({ chart }) {
  const factPoints = chart?.final_stock || [];
  const planPoints = chart?.mutual_finstock || [];
  const yTicks = chart?.y_axis?.ticks || [];
  const xLabels = chart?.x_labels || [];

  if (!chart || (!factPoints.length && !planPoints.length)) {
    return (
      <div id="chart-container">
        <div className="no-data-overlay">
          Нет данных по выбранным фильтрам за заданный период
        </div>
      </div>
    );
  }

  return (
    <div id="chart-container">
      <div id="price-chart" className="chart">
        <div className="chart-title">
          <span className="chart-title-text">
            {chart.title || "Динамика стоимости остатков, руб"}
          </span>

          <span className="chart-legend">
            <span className="legend-item">
              <span className="legend-dot fact"></span> Факт
            </span>
            <span className="legend-item">
              <span className="legend-dot plan"></span> План
            </span>
          </span>
        </div>

        <div className="chart-body">
          <svg
            className="chart-lines"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="factGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#7f4a88" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#7f4a88" stopOpacity="0" />
              </linearGradient>

              <linearGradient id="planGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#307672" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#307672" stopOpacity="0" />
              </linearGradient>
            </defs>

            <path className="area fact-area" d={makeAreaPath(factPoints)} />
            <path className="line fact-line" d={makeLinePath(factPoints)} />

            <path className="area plan-area" d={makeAreaPath(planPoints)} />
            <path className="line plan-line" d={makeLinePath(planPoints)} />
          </svg>

          {yTicks.map((tick, index) => (
            <div
              key={`${tick.label || tick.value}-${index}`}
              className="y-tick"
              style={{ "--y": tick.pos }}
            >
              <span>{tick.label || tick.value}</span>
            </div>
          ))}

          {factPoints.map((point, index) => {
            const normalized = normalizePoint(point);

            return (
              <div
                key={`fact-${index}`}
                className="point fact"
                style={{
                  "--x": normalized.x,
                  "--y": normalized.y,
                  left: `${normalized.x * 100}%`,
                  top: `${(1 - normalized.y) * 100}%`,
                }}
                title={`Факт: ${formatNumber(normalized.value)}`}
              ></div>
            );
          })}

          {planPoints.map((point, index) => {
            const normalized = normalizePoint(point);

            return (
              <div
                key={`plan-${index}`}
                className="point plan"
                style={{
                  "--x": normalized.x,
                  "--y": normalized.y,
                  left: `${normalized.x * 100}%`,
                  top: `${(1 - normalized.y) * 100}%`,
                }}
                title={`План: ${formatNumber(normalized.value)}`}
              ></div>
            );
          })}

          <div className="x-axis">
            {xLabels.map((label, index) => (
              <span
                key={`${label.label}-${index}`}
                style={{
                  "--left": label.pos,
                  display: shouldShowXLabel(xLabels.length, index)
                    ? "block"
                    : "none",
                }}
              >
                {label.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TurnoverTreeTable({
  tree,
  expandedMonths,
  expandedCodes,
  onToggleMonth,
  onToggleCode,
  onToggleAll,
}) {
  const allExpanded = expandedMonths.size > 0;

  return (
    <div className="purchases-table-wrapper" style={{ marginTop: "50px" }}>
      <table id="purchasesTreeTable">
        <thead id="purchasesTreeHead">
          <tr>
            <th>
              <span
                id="global-toggle"
                data-expanded={allExpanded ? "true" : "false"}
                onClick={onToggleAll}
              >
                {allExpanded ? "[-]" : "[+]"}
              </span>{" "}
              Год-Месяц
            </th>
            <th>Номенклатура</th>
            <th>Группа складов</th>
            <th>Склады</th>
            <th>Качество</th>
            <th>Средний запас, шт</th>
            <th>Средний запас, руб</th>
          </tr>
        </thead>

        <tbody id="purchasesTreeTableBody">
          {tree?.length ? (
            tree.map((monthNode) => (
              <TreeMonth
                key={monthNode.month_year}
                monthNode={monthNode}
                expandedMonths={expandedMonths}
                expandedCodes={expandedCodes}
                onToggleMonth={onToggleMonth}
                onToggleCode={onToggleCode}
              />
            ))
          ) : (
            <tr>
              <td colSpan="7" className="no-data-row">
                Нет данных по выбранным фильтрам за заданный период
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function TreeMonth({
  monthNode,
  expandedMonths,
  expandedCodes,
  onToggleMonth,
  onToggleCode,
}) {
  const month = monthNode.month_year;
  const monthExpanded = expandedMonths.has(month);

  return (
    <>
      <tr
        className={`month-row ${monthExpanded ? "" : "collapsed"}`}
        data-month={month}
      >
        <td>
          <span
            className="toggle-sign"
            onClick={(event) => {
              event.stopPropagation();
              onToggleMonth(month);
            }}
          >
            {monthExpanded ? "[-]" : "[+]"}
          </span>{" "}
          {month}
        </td>
        <td colSpan="4" style={{ fontWeight: "bold" }}>
          —
        </td>
        <td className="number">{formatNumber(monthNode.mutual_finstock)}</td>
        <td className="number">{formatNumber(monthNode.final_stock)}</td>
      </tr>

      {(monthNode.children || []).map((nomenclatureNode, index) => (
        <TreeNomenclature
          key={`${month}__nomenclature__${index}__${
            nomenclatureNode.partner || ""
          }`}
          month={month}
          nomenclatureNode={nomenclatureNode}
          index={index}
          monthExpanded={monthExpanded}
          expandedCodes={expandedCodes}
          onToggleCode={onToggleCode}
        />
      ))}
    </>
  );
}

function TreeNomenclature({
  month,
  nomenclatureNode,
  index,
  monthExpanded,
  expandedCodes,
  onToggleCode,
}) {
  const nomenclature = nomenclatureNode.partner || "";
  const codeKey = `${month}__${nomenclature}`;
  const codeExpanded = expandedCodes.has(codeKey);

  return (
    <>
      <tr
        className={`code-row ${monthExpanded ? "" : "collapsed"}`}
        data-month={month}
        data-code={nomenclature}
      >
        <td>{nomenclatureNode.month_year || month}</td>

        <td style={{ paddingLeft: "20px" }}>
          <span
            className="toggle-sign"
            onClick={(event) => {
              event.stopPropagation();

              if (monthExpanded) {
                onToggleCode(codeKey);
              }
            }}
          >
            {codeExpanded ? "[-]" : "[+]"}
          </span>{" "}
          {index < 10 ? (
            <>
              <strong>{index + 1}</strong> {nomenclature || "—"}
            </>
          ) : (
            nomenclature || "—"
          )}
        </td>

        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td className="number">{formatNumber(nomenclatureNode.mutual_finstock)}</td>
        <td className="number">{formatNumber(nomenclatureNode.final_stock)}</td>
      </tr>

      {(nomenclatureNode.children || []).map((warehouseGroupNode, index) => (
        <TreeWarehouseGroup
          key={`${codeKey}__warehouse_group__${index}`}
          month={month}
          codeKey={codeKey}
          warehouseGroupNode={warehouseGroupNode}
          monthExpanded={monthExpanded}
          codeExpanded={codeExpanded}
        />
      ))}
    </>
  );
}

function TreeWarehouseGroup({
  month,
  codeKey,
  warehouseGroupNode,
  monthExpanded,
  codeExpanded,
}) {
  return (
    <>
      <tr
        className={`detail-row ${
          monthExpanded && codeExpanded ? "" : "collapsed"
        }`}
        data-month={month}
        data-code={codeKey.split("__").slice(1).join("__")}
      >
        <td>{warehouseGroupNode.month_year || month}</td>
        <td style={{ paddingLeft: "40px" }}>
          {warehouseGroupNode.partner || "—"}
        </td>
        <td>{warehouseGroupNode.contract_partner || "—"}</td>
        <td>{warehouseGroupNode.manager_name || "—"}</td>
        <td>{warehouseGroupNode.quantity || "—"}</td>
        <td className="number">
          {formatNumber(warehouseGroupNode.mutual_finstock)}
        </td>
        <td className="number">{formatNumber(warehouseGroupNode.final_stock)}</td>
      </tr>

      {(warehouseGroupNode.children || []).map((warehouseNode, index) => (
        <tr
          key={`${codeKey}__warehouse__${index}`}
          className={`detail-row ${
            monthExpanded && codeExpanded ? "" : "collapsed"
          }`}
          data-month={month}
          data-code={codeKey.split("__").slice(1).join("__")}
        >
          <td>{warehouseNode.month_year || month}</td>
          <td style={{ paddingLeft: "60px" }}>
            {warehouseNode.partner || warehouseGroupNode.partner || "—"}
          </td>
          <td>{warehouseNode.contract_partner || "—"}</td>
          <td>{warehouseNode.manager_name || "—"}</td>
          <td>{warehouseNode.quantity || "—"}</td>
          <td className="number">{formatNumber(warehouseNode.mutual_finstock)}</td>
          <td className="number">{formatNumber(warehouseNode.final_stock)}</td>
        </tr>
      ))}
    </>
  );
}

export function TurnoverDashboard({ data, publicToken = null }) {
  const [dashboardData, setDashboardData] = useState(data || {});
  const [expandedMonths, setExpandedMonths] = useState(new Set());
  const [expandedCodes, setExpandedCodes] = useState(new Set());
  const [isApplyingFilters, setIsApplyingFilters] = useState(false);
  const [exporting, setExporting] = useState(false);

  const filters = dashboardData?.filters || {};
  const filterValues = dashboardData?.filter_values || {};
  const indicators = dashboardData?.indicators || {};
  const chart = dashboardData?.chart || null;
  const turnoverTree = dashboardData?.turnover_tree || [];

  const defaultFilters = useMemo(() => {
    const yesterday = new Date();

    yesterday.setDate(yesterday.getDate() - 1);

    return {
      nomenclature: [],
      warehouse_group: [],
      warehouse: [],
      quantity: [],
      date_start: `${yesterday.getFullYear()}-01-01`,
      date_end: yesterday.toISOString().slice(0, 10),
    };
  }, []);

  const [localFilters, setLocalFilters] = useState({
    nomenclature: normalizeList(filters.nomenclature),
    warehouse_group: normalizeList(filters.warehouse_group),
    warehouse: normalizeList(filters.warehouse),
    quantity: normalizeList(filters.quantity),
    date_start: filters.date_start || "",
    date_end: filters.date_end || "",
  });

  useEffect(() => {
    setDashboardData(data || {});
  }, [data]);

  useEffect(() => {
    setLocalFilters({
      nomenclature: normalizeList(filters.nomenclature),
      warehouse_group: normalizeList(filters.warehouse_group),
      warehouse: normalizeList(filters.warehouse),
      quantity: normalizeList(filters.quantity),
      date_start: filters.date_start || "",
      date_end: filters.date_end || "",
    });

    setExpandedMonths(new Set());
    setExpandedCodes(new Set());
  }, [filters, turnoverTree]);

  const currentFilters = useMemo(
    () => ({
      nomenclature: localFilters.nomenclature || [],
      warehouse_group: localFilters.warehouse_group || [],
      warehouse: localFilters.warehouse || [],
      quantity: localFilters.quantity || [],
      date_start: localFilters.date_start || "",
      date_end: localFilters.date_end || "",
    }),
    [localFilters]
  );


  function getBuilderUrl() {
    if (publicToken) {
      return `/v1/dashboards/public-group/${publicToken}/dashboard/turnover/`;
    }

    return "/v1/dashboards/builder/turnover/";
  }

  function getExportUrl() {
    if (publicToken) {
      return `/v1/datasets/public-group/${publicToken}/fb-turnover/export/`;
    }

    return "/v1/datasets/fb-turnover/export/";
  }


  async function fetchTurnover(nextFilters) {
    const payload = buildPayload(nextFilters);

    const response = await api.post(getBuilderUrl(), payload);

    const widget = response.data?.widgets?.find(
      (item) => item.type === "fb_turnover_dashboard"
    );

    const nextData = widget?.data;

    if (!nextData) return;

    setDashboardData(nextData);
    setExpandedMonths(new Set());
    setExpandedCodes(new Set());
  }

  async function applyFilters(next = currentFilters) {
    setIsApplyingFilters(true);

    try {
      await fetchTurnover(next);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  function changeFilter(name, value) {
    setLocalFilters((prev) => ({
      ...prev,
      [name]: value,
    }));
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
      await fetchTurnover(defaultFilters);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  function toggleMonth(month) {
    setExpandedMonths((prev) => {
      const next = new Set(prev);

      if (next.has(month)) {
        next.delete(month);

        setExpandedCodes((prevCodes) => {
          const result = new Set(prevCodes);

          Array.from(result).forEach((key) => {
            if (key.startsWith(`${month}__`)) {
              result.delete(key);
            }
          });

          return result;
        });
      } else {
        next.add(month);

        setExpandedCodes((prevCodes) => {
          const result = new Set(prevCodes);

          Array.from(result).forEach((key) => {
            if (key.startsWith(`${month}__`)) {
              result.delete(key);
            }
          });

          return result;
        });
      }

      return next;
    });
  }

  function toggleCode(codeKey) {
    setExpandedCodes((prev) => {
      const next = new Set(prev);

      if (next.has(codeKey)) {
        next.delete(codeKey);
      } else {
        next.add(codeKey);
      }

      return next;
    });
  }

  function toggleAll() {
    if (expandedMonths.size > 0) {
      setExpandedMonths(new Set());
      setExpandedCodes(new Set());
      return;
    }

    const nextMonths = new Set();

    turnoverTree.forEach((monthNode) => {
      nextMonths.add(monthNode.month_year);
    });

    setExpandedMonths(nextMonths);
    setExpandedCodes(new Set());
  }

  async function exportExcel() {
    setExporting(true);

    try {
      const payload = buildPayload(currentFilters);

      const response = await api.post(getExportUrl(), payload, {
        responseType: "blob",
      });

      const blobUrl = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = blobUrl;
      link.download = `turnover_${new Date().toISOString().slice(0, 10)}.xlsx`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(blobUrl);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="turnover">
      <h2>Остатки</h2>

      <form id="filterForm">
        {FILTERS.map(([name, label]) => (
          <MultiSelect
            key={name}
            name={name}
            label={label}
            options={filterValues[name] || []}
            selected={localFilters[name] || []}
            onChange={(value) => changeFilter(name, value)}
            onApply={() => applyFilters()}
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
          id="resetFilters"
          className="filters-reset"
          onClick={resetFilters}
          disabled={isApplyingFilters}
        >
          Очистить
        </button>
      </form>

      <TurnoverIndicators indicators={indicators} />

      <TurnoverChart chart={chart} />

      <TurnoverTreeTable
        tree={turnoverTree}
        expandedMonths={expandedMonths}
        expandedCodes={expandedCodes}
        onToggleMonth={toggleMonth}
        onToggleCode={toggleCode}
        onToggleAll={toggleAll}
      />

      {isApplyingFilters && <GlobalSpinner />}
    </div>
  );
}