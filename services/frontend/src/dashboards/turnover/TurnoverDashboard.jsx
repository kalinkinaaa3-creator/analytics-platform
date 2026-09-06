import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";
import { DateRangePicker } from "../../components/DateRangePicker";
import "../spinner.css";
import "./turnover.css";
import { PlanEditor, ProcurementTooltip, procurementNumber } from "../purchases/ProcurementEnhancements";

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

function formatChartPeriod(value, tooltip = false) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!match) return String(value || "");
  if (match[3]) return `${match[3]}.${match[2]}.${match[1]}`;
  return new Intl.DateTimeFormat("ru-RU", { month: tooltip ? "long" : "short", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)))
    .replace(/\s*г\.$/u, "");
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
  const count = Math.min(total, 10);
  if (count < 2 || total <= count) return true;
  return Array.from(
    { length: count },
    (_, position) => Math.round(position * (total - 1) / (count - 1)),
  ).includes(index);
}

function shouldShowPointValue(points, index, labelsCount) {
  if (labelsCount <= 8) return true;
  const valid = points.map((point, position) => ({ value: Number(point?.value), position })).filter(({ value }) => Number.isFinite(value));
  if (!valid.length) return false;
  const minimum = valid.reduce((best, item) => item.value < best.value ? item : best);
  const maximum = valid.reduce((best, item) => item.value > best.value ? item : best);
  return new Set([0, points.length - 1, minimum.position, maximum.position]).has(index);
}

function TurnoverIndicators({ indicators, planEditor }) {
  return (
    <div id="indicators-container">
      <div className="indicators-container">
        <div className="indicators-column">
          <div className="indicator-card">
            <div className="title">Факт, руб</div>
            <div className="value" id="indicator-cost">
              {procurementNumber(indicators?.cost, "", 0)}
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
              {procurementNumber(indicators?.deviation, "", 0)}
            </div>
          </div>
        </div>

        <div className="indicators-column">
          <div className="indicator-card indicator-card--editable">
            <div className="title">План, руб</div>
            <div className="value" id="indicator-plan">
              {procurementNumber(indicators?.indicator, "", 0)}
            </div>
            {planEditor}
          </div>
        </div>
      </div>
    </div>
  );
}

function TurnoverChart({ chart }) {
  const [tooltip, setTooltip] = useState(null);
  const factPoints = chart?.final_stock || [];
  const planPoints = chart?.mutual_finstock || [];
  const yTicks = chart?.y_axis?.ticks || [];
  const xLabels = chart?.x_labels || [];
  const tooltipFor = (point, event) => {
    const match = (items) => items.find((item) => Math.abs(Number(item.x) - Number(point.x)) < .0001);
    const factValue = match(factPoints)?.value; const planValue = match(planPoints)?.value;
    const deviation = Number.isFinite(Number(factValue)) && Number.isFinite(Number(planValue)) ? Number(factValue) - Number(planValue) : null;
    const deviationPercent = deviation !== null && Number(planValue) !== 0 ? deviation * 100 / Number(planValue) : null;
    const period = xLabels.reduce((best, item) => Math.abs(Number(item.pos) - Number(point.x)) < Math.abs(Number(best?.pos ?? 99) - Number(point.x)) ? item : best, null);
    setTooltip({ x: event.clientX, y: event.clientY, title: formatChartPeriod(period?.label, true), rows: [
      { label: "Факт", value: factValue, suffix: " руб", digits: 0, color: "#7f4a88" },
      { label: "План", value: planValue, suffix: " руб", digits: 0, color: "#307672" },
      { label: "Отклонение", value: deviation, suffix: " руб", digits: 0, color: "#a46258" },
      { label: "Отклонение, %", value: deviationPercent, suffix: "%", color: deviation < 0 ? "#4f7d51" : deviation > 0 ? "#b4433b" : "#71806e", valueColor: deviation < 0 ? "#4f7d51" : deviation > 0 ? "#d65a50" : undefined },
    ] });
  };

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
                onMouseEnter={(event) => tooltipFor(normalized, event)} onMouseMove={(event) => tooltipFor(normalized, event)} onMouseLeave={() => setTooltip(null)}
              >{shouldShowPointValue(factPoints, index, xLabels.length) && <span className="procurement-point-value">{procurementNumber(normalized.value, "", 0)}</span>}</div>
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
                onMouseEnter={(event) => tooltipFor(normalized, event)} onMouseMove={(event) => tooltipFor(normalized, event)} onMouseLeave={() => setTooltip(null)}
              />
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
                {formatChartPeriod(label.label)}
              </span>
            ))}
          </div>
          <ProcurementTooltip state={tooltip} title={tooltip?.title} rows={tooltip?.rows} />
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
  loadingMonths,
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
                loadingMonths={loadingMonths}
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
  loadingMonths,
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
              onToggleMonth(monthNode);
            }}
          >
            {loadingMonths.has(month) ? "[…]" : monthExpanded ? "[-]" : "[+]"}
          </span>{" "}
          {month}
        </td>
        <td colSpan="4" style={{ fontWeight: "bold" }}>
          —
        </td>
        <td className="number">{formatNumber(monthNode.mutual_finstock)}</td>
        <td className="number">{formatNumber(monthNode.final_stock)}</td>
      </tr>

      {monthExpanded && (monthNode.children || []).map((nomenclatureNode, index) => (
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

      {monthExpanded && codeExpanded && (nomenclatureNode.children || []).map((warehouseGroupNode, index) => (
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
  const [loadingMonths, setLoadingMonths] = useState(new Set());

  const filters = useMemo(
    () => dashboardData?.filters || {},
    [dashboardData?.filters]
  );
  const filterValues = dashboardData?.filter_values || {};
  const indicators = dashboardData?.indicators || {};
  const chart = dashboardData?.chart || null;
  const turnoverTree = useMemo(
    () => dashboardData?.turnover_tree || [],
    [dashboardData?.turnover_tree]
  );

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

  /* Данные виджета приходят асинхронно и намеренно синхронизируют локальное состояние. */
  /* eslint-disable react-hooks/set-state-in-effect */
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
  }, [filters]);
  /* eslint-enable react-hooks/set-state-in-effect */

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

  async function resetFilters() {
    setLocalFilters(defaultFilters);
    setIsApplyingFilters(true);

    try {
      await fetchTurnover(defaultFilters);
    } finally {
      setIsApplyingFilters(false);
    }
  }

  async function loadMonthChildren(monthNode) {
    const month = monthNode.month_year;
    if (monthNode.children_loaded || loadingMonths.has(month)) return true;

    setLoadingMonths((current) => new Set(current).add(month));

    try {
      const payload = buildPayload({
        ...currentFilters,
        tree_month: String(month).slice(0, 7),
      });
      const response = await api.post(getBuilderUrl(), payload);
      const widget = response.data?.widgets?.find(
        (item) => item.type === "fb_turnover_dashboard"
      );
      const loadedNode = widget?.data?.turnover_tree?.[0];
      if (!loadedNode) return false;

      setDashboardData((current) => ({
        ...current,
        turnover_tree: (current.turnover_tree || []).map((item) => (
          item.month_year === month ? loadedNode : item
        )),
      }));
      return true;
    } catch (error) {
      console.error("Failed to load turnover month details", error);
      return false;
    } finally {
      setLoadingMonths((current) => {
        const next = new Set(current);
        next.delete(month);
        return next;
      });
    }
  }

  async function toggleMonth(monthNode) {
    const month = monthNode.month_year;
    const opening = !expandedMonths.has(month);
    if (opening && !(await loadMonthChildren(monthNode))) return;

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

  async function toggleAll() {
    if (expandedMonths.size > 0) {
      setExpandedMonths(new Set());
      setExpandedCodes(new Set());
      return;
    }

    const results = await Promise.all(turnoverTree.map(loadMonthChildren));
    const nextMonths = new Set(
      turnoverTree
        .filter((_, index) => results[index])
        .map((monthNode) => monthNode.month_year)
    );

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

      <form id="filterForm" onSubmit={(event) => event.preventDefault()}>
        <div className="dashboard-filter-actions">
        <button type="button" className={`filters-export${exporting ? " is-loading" : ""}`} onClick={exportExcel} disabled={exporting || isApplyingFilters} aria-busy={exporting}>{exporting ? "Экспорт..." : "Экспорт"}</button>
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

      <TurnoverIndicators indicators={indicators} planEditor={<PlanEditor kind="turnover" publicToken={publicToken} dateStart={localFilters.date_start} dateEnd={localFilters.date_end} onSaved={() => fetchTurnover(currentFilters)} />} />

      <TurnoverChart chart={chart} />

      <TurnoverTreeTable
        tree={turnoverTree}
        expandedMonths={expandedMonths}
        expandedCodes={expandedCodes}
        onToggleMonth={toggleMonth}
        onToggleCode={toggleCode}
        onToggleAll={toggleAll}
        loadingMonths={loadingMonths}
      />

      {isApplyingFilters && <GlobalSpinner />}
    </div>
  );
}
