import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import "./purchases.css";

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";

  const number = Number(value);

  if (Number.isNaN(number)) return value;

  return number.toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function numberClass(value) {
  const number = Number(value);

  if (Number.isNaN(number)) return "number";
  if (number > 0) return "number positive";
  if (number < 0) return "number negative";

  return "number";
}

function buildParams(filters) {
  const params = new URLSearchParams();

  Object.entries(filters || {}).forEach(([key, value]) => {
    if (value) {
      params.set(key, value);
    }
  });

  return params;
}

function IndicatorCard({ title, value }) {
  return (
    <div className="indicator-card">
      <div className="title">{title}</div>
      <div className="value">{formatNumber(value)}</div>
    </div>
  );
}

function PurchasesIndicators({ indicators }) {
  const deviation = Number(indicators?.deviation || 0);

  return (
    <div id="indicators-container">
      <div className="indicators-container">
        <div className="indicators-column">
          <IndicatorCard title="Факт, руб/кг" value={indicators?.fact} />
          <IndicatorCard title="План, руб/кг" value={indicators?.plan} />
        </div>

        <div className="indicators-column indicators-center">
          <div className="indicator-card deviation">
            <div className="title title-deviation">Отклонение, руб/кг</div>
            <div
              className={`value deviation-number ${
                deviation > 0 ? "positive" : deviation < 0 ? "negative" : ""
              }`}
            >
              {formatNumber(indicators?.deviation)}
            </div>
          </div>
        </div>

        <div className="indicators-column">
          <IndicatorCard title="Стоимость, руб" value={indicators?.cost} />
          <IndicatorCard title="Объем, кг" value={indicators?.quantity} />
        </div>
      </div>
    </div>
  );
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

function PurchasesChart({ chart }) {
  const fact = chart?.fact || [];
  const plan = chart?.plan || [];
  const yTicks = chart?.y_axis?.ticks || [];
  const xLabels = chart?.x_labels || [];

  if (!chart || (!fact.length && !plan.length)) {
    return (
      <div id="chart-container">
        <div className="no-data-overlay">Нет данных по выбранным фильтрам</div>
      </div>
    );
  }

  return (
    <div id="chart-container">
      <div id="price-chart" className="chart">
        <div className="chart-title">
          <span className="chart-title-text">
            {chart.title || "Динамика цены, руб/кг"}
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

              <filter id="glow">
                <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                <feMerge>
                  <feMergeNode in="coloredBlur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <path className="area fact-area" d={makeAreaPath(fact)} />
            <path className="area plan-area" d={makeAreaPath(plan)} />

            <path className="line fact-line" d={makeLinePath(fact)} />
            <path className="line plan-line" d={makeLinePath(plan)} />
          </svg>

          {yTicks.map((tick, index) => (
            <div
              key={`${tick.value}-${index}`}
              className="y-tick"
              style={{ "--y": tick.pos }}
            >
              <span>{tick.value}</span>
            </div>
          ))}

          {fact.map((point, index) => {
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

          {plan.map((point, index) => {
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

function PurchasesTreeTable({
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
            <th>Группа</th>
            <th>Номенклатура</th>
            <th>Партнер</th>
            <th>Объем, кг</th>
            <th>Стоимость, руб</th>
            <th>Цена, руб/кг</th>
            <th>План, руб/кг</th>
            <th>Отклонение, руб/кг</th>
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
              <td colSpan="9" className="no-data-row">
                Нет данных по выбранным фильтрам
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div id="infiniteSpinnerTree" className="infinite-spinner hidden"></div>
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
        <td className="number">{formatNumber(monthNode.quantity_1C)}</td>
        <td className="number">{formatNumber(monthNode.revenue_1C)}</td>
        <td className="number">{formatNumber(monthNode.price)}</td>
        <td className="number">{formatNumber(monthNode.indicator)}</td>
        <td className={numberClass(monthNode.deviation)}>
          {formatNumber(monthNode.deviation)}
        </td>
      </tr>

      {(monthNode.children || []).map((codeNode) => (
        <TreeCode
          key={`${month}__${codeNode.nomenclature_code}`}
          month={month}
          codeNode={codeNode}
          monthExpanded={monthExpanded}
          expandedCodes={expandedCodes}
          onToggleCode={onToggleCode}
        />
      ))}
    </>
  );
}

function TreeCode({
  month,
  codeNode,
  monthExpanded,
  expandedCodes,
  onToggleCode,
}) {
  const code = codeNode.nomenclature_code || "";
  const codeKey = `${month}__${code}`;
  const codeExpanded = expandedCodes.has(codeKey);

  return (
    <>
      <tr
        className={`code-row ${monthExpanded ? "" : "collapsed"}`}
        data-month={month}
        data-code={code}
      >
        <td>{codeNode.month_year || month}</td>
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
          {code || "—"}
        </td>
        <td colSpan="2">—</td>
        <td className="number">{formatNumber(codeNode.quantity_1C)}</td>
        <td className="number">{formatNumber(codeNode.revenue_1C)}</td>
        <td className="number">{formatNumber(codeNode.price)}</td>
        <td className="number">{formatNumber(codeNode.indicator)}</td>
        <td className={numberClass(codeNode.deviation)}>
          {formatNumber(codeNode.deviation)}
        </td>
      </tr>

      {(codeNode.children || []).map((detail, index) => (
        <tr
          key={`${codeKey}__${index}`}
          className={`detail-row ${
            monthExpanded && codeExpanded ? "" : "collapsed"
          }`}
          data-month={month}
          data-code={code}
        >
          <td>{detail.month_year || month}</td>
          <td>{code || "—"}</td>
          <td>{detail.nomenclature || "—"}</td>
          <td>{detail.partner || "—"}</td>
          <td className="number">{formatNumber(detail.quantity_1C)}</td>
          <td className="number">{formatNumber(detail.revenue_1C)}</td>
          <td className="number">{formatNumber(detail.price)}</td>
          <td className="number">{formatNumber(detail.indicator)}</td>
          <td className={numberClass(detail.deviation)}>
            {formatNumber(detail.deviation)}
          </td>
        </tr>
      ))}
    </>
  );
}

export function PurchasesDashboard({ data, onFiltersChange }) {
  const filters = data?.filters || {};
  const filterValues = data?.filter_values || {};
  const indicators = data?.indicators || {};
  const chart = data?.chart || null;
  const purchasesTree = data?.purchases_tree || [];

  const [localFilters, setLocalFilters] = useState(filters);
  const [expandedMonths, setExpandedMonths] = useState(new Set());
  const [expandedCodes, setExpandedCodes] = useState(new Set());
  const [exporting, setExporting] = useState(false);

  const defaultFilters = useMemo(() => {
    const now = new Date();
    const year = now.getFullYear();

    return {
      nomenclature_code: "",
      nomenclature: "",
      partner: "",
      date_start: `${year}-01-01`,
      date_end: now.toISOString().slice(0, 10),
    };
  }, []);

  function applyFilters(next) {
    setLocalFilters(next);

    if (onFiltersChange) {
      onFiltersChange(next);
    }
  }

  function handleFilterChange(name, value) {
    applyFilters({
      ...localFilters,
      [name]: value,
    });
  }

  const applyFiltersFromDom = useCallback(() => {
    const form = document.getElementById("filterForm");
    if (!form) return;

    const formData = new FormData(form);

    applyFilters({
      nomenclature_code: formData.get("nomenclature_code") || "",
      nomenclature: formData.get("nomenclature") || "",
      partner: formData.get("partner") || "",
      date_start: formData.get("date_start") || "",
      date_end: formData.get("date_end") || "",
    });
  }, [onFiltersChange]);

  useEffect(() => {
    setLocalFilters(filters);
    setExpandedMonths(new Set());
    setExpandedCodes(new Set());
  }, [filters, purchasesTree]);

  useEffect(() => {
    const ids = [
      "date_start_filter",
      "date_end_filter",
    ];

    ids.forEach((id) => {
      const el = document.getElementById(id);

      if (el) {
        el.addEventListener("change", applyFiltersFromDom);
      }
    });

    return () => {
      ids.forEach((id) => {
        const el = document.getElementById(id);

        if (el) {
          el.removeEventListener("change", applyFiltersFromDom);
        }
      });
    };
  }, [applyFiltersFromDom]);

  function resetFilters() {
    applyFilters(defaultFilters);
  }

  function toggleMonth(month) {
    setExpandedMonths((prev) => {
      const nextMonths = new Set(prev);

      if (nextMonths.has(month)) {
        nextMonths.delete(month);

        setExpandedCodes((prevCodes) => {
          const nextCodes = new Set(prevCodes);

          Array.from(nextCodes).forEach((key) => {
            if (key.startsWith(`${month}__`)) {
              nextCodes.delete(key);
            }
          });

          return nextCodes;
        });
      } else {
        nextMonths.add(month);

        setExpandedCodes((prevCodes) => {
          const nextCodes = new Set(prevCodes);

          Array.from(nextCodes).forEach((key) => {
            if (key.startsWith(`${month}__`)) {
              nextCodes.delete(key);
            }
          });

          return nextCodes;
        });
      }

      return nextMonths;
    });
  }

  function toggleCode(codeKey) {
    setExpandedCodes((prev) => {
      const nextCodes = new Set(prev);

      if (nextCodes.has(codeKey)) {
        nextCodes.delete(key);
      } else {
        nextCodes.add(codeKey);
      }

      return nextCodes;
    });
  }

  function toggleAll() {
    if (expandedMonths.size > 0) {
      setExpandedMonths(new Set());
      setExpandedCodes(new Set());
      return;
    }

    const nextMonths = new Set();

    purchasesTree.forEach((monthNode) => {
      nextMonths.add(monthNode.month_year);
    });

    setExpandedMonths(nextMonths);
    setExpandedCodes(new Set());
  }

  async function exportExcel() {
    setExporting(true);

    try {
      const params = buildParams(localFilters);

      const response = await api.get(
        `/v1/datasets/fb-purchases/export/?${params.toString()}`,
        {
          responseType: "blob",
        }
      );

      const blobUrl = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = blobUrl;
      link.download = `purchases_${new Date().toISOString().slice(0, 10)}.xlsx`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(blobUrl);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="purchases">
      <h2>Сырье</h2>

      <form id="filterForm">
        <div className="filter">
          <label htmlFor="filter_nomenclature_code_list">Группа</label>
          <select
            id="filter_nomenclature_code_list"
            name="nomenclature_code"
            value={localFilters.nomenclature_code || ""}
            onChange={(event) =>
              handleFilterChange("nomenclature_code", event.target.value)
            }
          >
            <option value=""></option>
            {(filterValues.nomenclature_code || []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <div className="filter">
          <label htmlFor="filter_nomenclature_list">Номенклатура</label>
          <select
            id="filter_nomenclature_list"
            name="nomenclature"
            value={localFilters.nomenclature || ""}
            onChange={(event) =>
              handleFilterChange("nomenclature", event.target.value)
            }
          >
            <option value=""></option>
            {(filterValues.nomenclature || []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <div className="filter">
          <label htmlFor="filter_partner_list">Контрагент</label>
          <select
            id="filter_partner_list"
            name="partner"
            value={localFilters.partner || ""}
            onChange={(event) =>
              handleFilterChange("partner", event.target.value)
            }
          >
            <option value=""></option>
            {(filterValues.partner || []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

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
          />
        </div>

        <button
          type="button"
          className="filters-export"
          onClick={exportExcel}
          disabled={exporting}
        >
          {exporting ? "Экспорт..." : "Экспорт"}
        </button>

        <button
          type="button"
          id="resetFilters"
          className="filters-reset"
          onClick={resetFilters}
        >
          Очистить
        </button>
      </form>

      <PurchasesIndicators indicators={indicators} />

      <PurchasesChart chart={chart} />

      <PurchasesTreeTable
        tree={purchasesTree}
        expandedMonths={expandedMonths}
        expandedCodes={expandedCodes}
        onToggleMonth={toggleMonth}
        onToggleCode={toggleCode}
        onToggleAll={toggleAll}
      />
    </div>
  );
}