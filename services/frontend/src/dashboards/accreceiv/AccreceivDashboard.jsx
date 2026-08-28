import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { DateRangePicker } from "../../components/DateRangePicker";
import "../spinner.css";
import "./accreceiv.css";

const FILTERS = [
  ["partner", "Контрагент"],
  ["contract_partner", "Договор"],
  ["manager_name", "Менеджер"],
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

function AccreceivIndicators({ indicators }) {
  return (
    <div id="indicators-container">
      <div className="indicators-container">
        <div className="indicators-column">
          <div className="indicator-card">
            <div className="title">Σ (кон. остаток), руб</div>
            <div className="value" id="indicator-cost">
              {formatNumber(indicators?.cost)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AccreceivChart({ chart }) {
  const finalStock = chart?.final_stock || [];
  const yTicks = chart?.y_axis?.ticks || [];
  const xLabels = chart?.x_labels || [];

  if (!chart || !finalStock.length) {
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
            {chart.title || "Динамика ДЗ, руб"}
          </span>

          <span className="chart-legend">
            <span className="legend-item">
              <span className="legend-dot plan"></span> Σ (кон. остаток)
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
              <linearGradient id="planGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#307672" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#307672" stopOpacity="0" />
              </linearGradient>
            </defs>

            <path className="area plan-area" d={makeAreaPath(finalStock)} />
            <path className="line plan-line" d={makeLinePath(finalStock)} />
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

          {finalStock.map((point, index) => {
            const normalized = normalizePoint(point);

            return (
              <div
                key={`final-stock-${index}`}
                className="point plan"
                style={{
                  "--x": normalized.x,
                  "--y": normalized.y,
                  left: `${normalized.x * 100}%`,
                  top: `${(1 - normalized.y) * 100}%`,
                }}
                title={`Σ (кон. остаток): ${formatNumber(normalized.value)}`}
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

function AccreceivTreeTable({
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
            <th>Контрагент</th>
            <th>Договор</th>
            <th>Менеджер</th>
            <th>Σ (кон. остаток), руб</th>
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
              <td colSpan="5" className="no-data-row">
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

        <td colSpan="3" style={{ fontWeight: "bold" }}>
          —
        </td>

        <td className="number">{formatNumber(monthNode.final_stock)}</td>
      </tr>

      {(monthNode.children || []).map((partnerNode, index) => (
        <TreePartner
          key={`${month}__partner__${index}__${partnerNode.partner || ""}`}
          month={month}
          partnerNode={partnerNode}
          monthExpanded={monthExpanded}
          expandedCodes={expandedCodes}
          onToggleCode={onToggleCode}
        />
      ))}
    </>
  );
}

function TreePartner({
  month,
  partnerNode,
  monthExpanded,
  expandedCodes,
  onToggleCode,
}) {
  const partner = partnerNode.partner || "";
  const codeKey = `${month}__${partner}`;
  const codeExpanded = expandedCodes.has(codeKey);

  return (
    <>
      <tr
        className={`code-row ${monthExpanded ? "" : "collapsed"}`}
        data-month={month}
        data-code={partner}
      >
        <td>{partnerNode.month_year || month}</td>

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
          {partner || "—"}
        </td>

        <td>{partnerNode.contract_partner || "—"}</td>
        <td>{partnerNode.manager_name || "—"}</td>
        <td className="number">{formatNumber(partnerNode.final_stock)}</td>
      </tr>

      {(partnerNode.children || []).map((detail, index) => (
        <tr
          key={`${codeKey}__detail__${index}`}
          className={`detail-row ${
            monthExpanded && codeExpanded ? "" : "collapsed"
          }`}
          data-month={month}
          data-code={partner}
        >
          <td>{detail.month_year || month}</td>
          <td style={{ paddingLeft: "40px" }}>
            {detail.partner || partner || "—"}
          </td>
          <td>{detail.contract_partner || "—"}</td>
          <td>{detail.manager_name || "—"}</td>
          <td className="number">{formatNumber(detail.final_stock)}</td>
        </tr>
      ))}
    </>
  );
}

export function AccreceivDashboard({ data, publicToken = null }) {
  const [dashboardData, setDashboardData] = useState(data || {});
  const [expandedMonths, setExpandedMonths] = useState(new Set());
  const [expandedCodes, setExpandedCodes] = useState(new Set());
  const [isApplyingFilters, setIsApplyingFilters] = useState(false);
  const [exporting, setExporting] = useState(false);

  const filters = dashboardData?.filters || {};
  const filterValues = dashboardData?.filter_values || {};
  const indicators = dashboardData?.indicators || {};
  const chart = dashboardData?.chart || null;
  const accreceivTree = dashboardData?.accreceiv_tree || [];

  const defaultFilters = useMemo(() => {
    const yesterday = new Date();

    yesterday.setDate(yesterday.getDate() - 1);

    return {
      partner: [],
      contract_partner: [],
      manager_name: [],
      date_start: `${yesterday.getFullYear()}-01-01`,
      date_end: yesterday.toISOString().slice(0, 10),
    };
  }, []);

  const [localFilters, setLocalFilters] = useState({
    partner: normalizeList(filters.partner),
    contract_partner: normalizeList(filters.contract_partner),
    manager_name: normalizeList(filters.manager_name),
    date_start: filters.date_start || "",
    date_end: filters.date_end || "",
  });

  /* Данные виджета приходят асинхронно и намеренно синхронизируют локальное состояние. */
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setDashboardData(data || {});
  }, [data]);

  useEffect(() => {
    setLocalFilters({
      partner: normalizeList(filters.partner),
      contract_partner: normalizeList(filters.contract_partner),
      manager_name: normalizeList(filters.manager_name),
      date_start: filters.date_start || "",
      date_end: filters.date_end || "",
    });

    setExpandedMonths(new Set());
    setExpandedCodes(new Set());
  }, [filters, accreceivTree]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const currentFilters = useMemo(
    () => ({
      partner: localFilters.partner || [],
      contract_partner: localFilters.contract_partner || [],
      manager_name: localFilters.manager_name || [],
      date_start: localFilters.date_start || "",
      date_end: localFilters.date_end || "",
    }),
    [localFilters]
  );


  function getBuilderUrl() {
    if (publicToken) {
      return `/v1/dashboards/public-group/${publicToken}/dashboard/accreceiv/`;
    }

    return "/v1/dashboards/builder/accreceiv/";
  }

  function getExportUrl() {
    if (publicToken) {
      return `/v1/datasets/public-group/${publicToken}/fb-accreceiv/export/`;
    }

    return "/v1/datasets/fb-accreceiv/export/";
  }


  async function fetchAccreceiv(nextFilters) {
    const payload = buildPayload(nextFilters);

    const response = await api.post(getBuilderUrl(), payload);

    const widget = response.data?.widgets?.find(
      (item) => item.type === "fb_accreceiv_dashboard"
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
      await fetchAccreceiv(next);
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

  async function resetFilters() {
    setLocalFilters(defaultFilters);
    setIsApplyingFilters(true);

    try {
      await fetchAccreceiv(defaultFilters);
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

    accreceivTree.forEach((monthNode) => {
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
      link.download = `accreceiv_${new Date().toISOString().slice(0, 10)}.xlsx`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(blobUrl);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="accreceiv">
      <h2>ДЗ</h2>

      <form id="filterForm" onSubmit={(event) => event.preventDefault()}>
        <div className="dashboard-filter-actions">
        <button type="button" className="filters-export" onClick={exportExcel} disabled={exporting || isApplyingFilters}>{exporting ? "Экспорт..." : "Экспорт"}</button>
        <button type="button" id="resetFilters" className="filters-reset" onClick={resetFilters} disabled={isApplyingFilters}>Очистить</button>
        </div>
        <div className="dashboard-filter-grid">
        {FILTERS.map(([name, label]) => (
          <DashboardMultiSelect
            key={name}
            label={label}
            options={filterValues[name] || []}
            selected={localFilters[name] || []}
            onApply={(value) => {
              const next = { ...currentFilters, [name]: value };
              changeFilter(name, value);
              applyFilters(next);
            }}
          />
        ))}
        <DateRangePicker start={localFilters.date_start} end={localFilters.date_end} resetRange={{ start: defaultFilters.date_start, end: defaultFilters.date_end }} onChange={({ start, end }) => { const next = { ...currentFilters, date_start: start, date_end: end }; setLocalFilters(next); applyFilters(next); }} />
        </div>
      </form>

      <AccreceivIndicators indicators={indicators} />

      <AccreceivChart chart={chart} />

      <AccreceivTreeTable
        tree={accreceivTree}
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
