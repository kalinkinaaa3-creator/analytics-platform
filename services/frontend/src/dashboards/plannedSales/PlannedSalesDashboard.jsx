import { useState } from "react";
import "./planned_sales.css";
import { api } from "../../api/client";
import { formatInt, normalizeValue, unformatNumber } from "./formatters";
import { PlannedSalesCharts } from "./PlannedSalesCharts";




function HeaderTitle({ title }) {
  return title.split("\n").map((part, index) => (
    <span key={index}>
      {index > 0 && <br />}
      {part}
    </span>
  ));
}

function getRowTitle(row) {
  if (row.is_grand) return "Итого по компании";
  if (row.level === 1 && row.is_summary) return "Итого";
  if (row.level === 3) return row.level3;
  if (row.level === 2) return row.level2;
  return row.level1 || "";
}

function IndicatorCard({ title, value, color }) {
  return (
    <div className="indicator-card">
      <div className="title">{title}</div>
      <div className="value pct" style={{ color }}>
        {formatInt(value)}%
      </div>
    </div>
  );
}

function PeriodIndicators({ title, item, yearLabel }) {
  return (
    <div className="indicators-group">
      <h3>{title}</h3>
      <div className="indicators-row">
        <IndicatorCard title="Прошло времени" value={item?.time_passed} />
        <IndicatorCard title="Выполнение плана" value={item?.vs_plan} color={item?.vs_plan_color} />
        <IndicatorCard title={`Факт vs ${Number(yearLabel) - 1}`} value={item?.vs_sply} color={item?.vs_sply_color} />
        <IndicatorCard title="Факт vs Проекция" value={item?.fact_proj} color={item?.fact_proj_color} />
      </div>
    </div>
  );
}

function Toast({ message }) {
  if (!message) return null;

  return (
    <div id="toast">
      {message}
    </div>
  );
}

function EditableCell({ row, field, canEdit, onSave }) {
  const editable = !row.is_grand && !row.is_summary && row.id_directory;

  if (!editable || !canEdit) {
    return <>{formatInt(row[field])}</>;
  }

  return (
    <input
      key={`${row.date}-${row.id_directory}-${field}-${row[field] ?? ""}`}
      type="text"
      className={
        field === "plan"
          ? "edit-plan formatted-number"
          : "edit-projection formatted-number"
      }
      data-date={row.date}
      data-id={row.id_directory}
      defaultValue={formatInt(row[field])}
      onFocus={(event) => {
        event.target.dataset.originalValue = unformatNumber(
          event.target.value
        );

        event.target.value = unformatNumber(event.target.value);
      }}
      onBlur={(event) => {
        const input = event.target;

        const original = normalizeValue(
          input.dataset.originalValue || "0"
        );

        const current = normalizeValue(input.value);

        input.value = formatInt(current);

        if (original === current) return;

        input.dataset.originalValue = current.toString();

        onSave({
          date: input.dataset.date,
          id_directory: input.dataset.id,
          field,
          value: current,
        });
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          event.currentTarget.blur();
        }
      }}
    />
  );
}

function DataCell({ row, config, canEdit, onSave }) {
  const [field, , className = "", colorField] = config;

  if (className === "editable-plan" || className === "editable-projection") {
    return (
      <td className={field === "plan" ? "col-plan" : "col-projection"}>
        <EditableCell row={row} field={field} canEdit={canEdit} onSave={onSave} />
      </td>
    );
  }

  if (className.includes("percent")) {
    return (
      <td className={`percent-cell ${className.includes("italics") ? "italics" : ""}`}>
        <span className="percent-dot" style={{ backgroundColor: row[colorField] }}></span>
        {formatInt(row[field])}%
      </td>
    );
  }

  return <td className={className}>{formatInt(row[field])}</td>;
}

export function PlannedSalesDashboard({ data, dashboard, onFiltersChange }) {
  const [selectedDate, setSelectedDate] = useState(data?.filters?.date || "");
  const [toast, setToast] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const [uploadingPlan, setUploadingPlan] = useState(false);

  const canEdit = Boolean(dashboard?.can_edit);

  const lastUpdate = data?.last_update || null;

  const refreshTitle = lastUpdate
    ? `Данные актуальны на: ${lastUpdate}`
    : "Данные отсутствуют";


  function showToast(message) {
    setToast(message);

    setTimeout(() => {
      setToast("");
    }, 2000);
  }

  function handleDateChange(date) {
    setSelectedDate(date);

    if (onFiltersChange) {
      onFiltersChange({ date });
    }
  }

  async function handleSave(payload) {
    try {
      await api.post("/v1/datasets/planned-sales/save-plan/", {
        ...payload,
        field: payload.field === "projection" ? "projection_s" : payload.field,
      });

      showToast("Данные сохранены");
    } catch (error) {
      console.error("Save error:", error);
      showToast("Ошибка сохранения");
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
        showToast(
          "Обновление выполняется. Данные обновятся после завершения"
        );
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

  async function handlePlanUpload(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    setUploadingPlan(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      await api.post(
        "/v1/datasets/planned-sales/plan-upload/",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        }
      );

      showToast("План успешно загружен");

      if (onFiltersChange) {
        onFiltersChange({
          date: selectedDate,
        });
      }
    } catch (error) {
      const message =
        error.response?.data?.error ||
        error.response?.data?.detail ||
        "Ошибка загрузки плана";

      showToast(message);
    } finally {
      setUploadingPlan(false);

      // Позволяет повторно выбрать тот же файл
      event.target.value = "";
    }
  }


  const dates = data?.filter_values?.date || [];
  const indicators = data?.indicators || {};
  const labels = data?.period_labels || {};
  const rows = data?.sales_tree || [];
  const chartData = data?.level2_month_agg || [];

  const selectedYear =
    Number(labels.year) ||
    Number(selectedDate?.slice(0, 4)) ||
    new Date().getFullYear();

  const previousYear = selectedYear - 1;

  const MONTH_FIELDS = [
    ["plan", "План, руб", "editable-plan"],
    ["fact", "Факт, руб"],
    ["fact_vs_plan", "Факт vs\nПлан, руб"],
    ["vs_plan_pct", "vs План, %", "percent", "vs_plan_pct_color"],
    ["appg", `${previousYear}, руб`],
    ["appg_slice", `${previousYear}\nYoY, руб`, "italics"],
    // ["plan_vs_SPLY", `План vs\n${previousYear}, %`, "percent italics", "plan_vs_SPLY_color"],
    ["fact_vs_SPLY", `Факт vs\n${previousYear}, %`, "percent", "fact_vs_SPLY_color"],
    ["yoy", "YoY, %", "percent", "yoy_color"],
    ["projection", "Проекция на\nмесяц, руб", "editable-projection"],
    ["proj_vs_plan_1", "Проекция vs\nПлан, %", "percent", "proj_vs_plan_1_color"],
    ["proj_vs_plan_2", "Проекция vs\nПлан, руб"],
    ["proj_vs_SPLY", `Проекция vs\n${previousYear}, %`, "percent", "proj_vs_SPLY_color"],
  ];

  const QUARTER_FIELDS = [
    ["plan_quarter", "План, руб"],
    ["fact_quarter", "Факт, руб"],
    ["fact_vs_plan_quarter", "Факт vs\nПлан, руб"],
    ["vs_plan_pct_quarter", "vs План, %", "percent", "vs_plan_pct_quarter_color"],
    ["year_SPLY_quarter", `${previousYear}, руб`],
    ["yoy_SPLY_quarter", `${previousYear}\nYoY, руб`, "italics"],
    // ["plan_vs_SPLY_quarter", `План vs\n${previousYear}, %`, "percent italics", "plan_vs_SPLY_quarter_color"],
    ["fact_vs_SPLY_quarter", `Факт vs\n${previousYear}, %`, "percent", "fact_vs_SPLY_quarter_color"],
    ["yoy_quarter", "YoY, %", "percent", "yoy_quarter_color"],
    ["projection_quarter", "Проекция на\nквартал, руб"],
    ["proj_vs_plan_q1", "Проекция vs\nПлан, %", "percent", "proj_vs_plan_q1_color"],
    ["proj_vs_plan_q2", "Проекция vs\nПлан, руб"],
    ["proj_vs_SPLY_quarter", `Проекция vs\n${previousYear}, %`, "percent", "proj_vs_SPLY_quarter_color"],
  ];

  const YEAR_FIELDS = [
    ["plan_year", "План, руб"],
    ["fact_year", "Факт, руб"],
    ["fact_vs_plan_year", "Факт vs\nПлан, руб"],
    ["vs_plan_pct_year", "vs План, %", "percent", "vs_plan_pct_year_color"],
    ["year_SPLY_year", `${previousYear}, руб`],
    ["yoy_SPLY_year", `${previousYear}\nYoY, руб`, "italics"],
    // ["plan_vs_SPLY_year", `План vs\n${previousYear}, %`, "percent italics", "plan_vs_SPLY_year_color"],
    ["fact_vs_SPLY_year", `Факт vs\n${previousYear}, %`, "percent", "fact_vs_SPLY_year_color"],
    ["yoy_year", "YoY, %", "percent", "yoy_year_color"],
    ["projection_year", "Проекция на\nгод, руб"],
    ["proj_vs_plan_y1", "Проекция vs\nПлан, %", "percent", "proj_vs_plan_y1_color"],
    ["proj_vs_plan_y2", "Проекция vs\nПлан, руб"],
    ["proj_vs_SPLY_year", `Проекция vs\n${previousYear}, %`, "percent", "proj_vs_SPLY_year_color"],
  ];

  return (
    <div className="planned-sales-dashboard">
      <h2>План/Факт продаж</h2>

      <form id="filterForm">
        <div className="filters-actions">
          {canEdit && (
            <>
              <input
                type="file"
                id="plan-upload-input"
                accept=".xlsx"
                style={{ display: "none" }}
                onChange={handlePlanUpload}
              />

              <button
                type="button"
                className="filters-export"
                disabled={uploadingPlan}
                onClick={() =>
                  document.getElementById("plan-upload-input")?.click()
                }
              >
                {uploadingPlan ? "Загрузка..." : "Загрузить план"}
              </button>
            </>
          )}

          <button
            type="button"
            className="filters-export"
            onClick={refreshSales}
            disabled={refreshing}
            title={refreshTitle}
          >
            {refreshing ? "Обновление..." : "Обновить"}
          </button>
        </div>
        <div className="filter">
          <label htmlFor="filter_date_list">Месяц</label>

          <div className="multi-select" id="multiSelect_date">
            <div className="dropdown static-buttons">
              <div id="options_date" className="buttons-container">
                {dates.map((date) => (
                  <div className="dropdown-item" key={date}>
                    <label>
                      <input
                        type="radio"
                        name="date"
                        value={date}
                        checked={date === selectedDate}
                        onChange={() => handleDateChange(date)}
                      />
                      <span>{date.slice(0, 7)}</span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

      </form>

      <div id="indicators-container">
        <div className="indicators-grid">
          <PeriodIndicators title={labels.month} item={indicators.month} yearLabel={indicators.year?.label} />
          <PeriodIndicators title={`${labels.quarter} кв.`} item={indicators.quarter} yearLabel={indicators.year?.label} />
          <PeriodIndicators title={`${labels.year} год YTM`} item={indicators.year} yearLabel={indicators.year?.label} />
        </div>
      </div>

      <div id="table-container" className="gantt-table-wrapper">
        <div className="table-scroll">
          <table id="head">
            <thead>
              <tr className="trend-row">
                <th className="sticky-col" rowSpan="2">Направление</th>
                <th className="group-month" colSpan="12">{labels.month}</th>
                <th className="group-quarter" colSpan="12">{labels.quarter} кв.</th>
                <th className="group-year" colSpan="12">{labels.year} год YTM</th>
              </tr>

              <tr className="header-row">
                {[...MONTH_FIELDS, ...QUARTER_FIELDS, ...YEAR_FIELDS].map(([, title], index) => (
                  <th
                    key={`${title}-${index}`}
                    className={
                      index < 12
                        ? "group-month"
                        : index < 24
                          ? "group-quarter"
                          : "group-year"
                    }
                  >
                    <HeaderTitle title={title} />
                  </th>
                ))}
              </tr>
            </thead>

            <tbody id="projectsTableBody">
              {rows.map((row, index) => (
                <tr
                  key={`${row.date}-${row.id_directory}-${index}`}
                  data-date={row.date}
                  data-id={row.id_directory || ""}
                  className={[
                    row.is_summary ? "summary-row" : "",
                    row.is_grand ? "grand" : "",
                    `level${row.level}`,
                  ].join(" ")}
                >
                  <td className="sticky-col">{getRowTitle(row)}</td>

                  {MONTH_FIELDS.map((config) => (
                    <DataCell
                      key={config[0]}
                      row={row}
                      config={config}
                      canEdit={canEdit}
                      onSave={handleSave}
                    />
                  ))}

                  {QUARTER_FIELDS.map((config) => (
                    <DataCell
                      key={config[0]}
                      row={row}
                      config={config}
                      canEdit={canEdit}
                      onSave={handleSave}
                    />
                  ))}

                  {YEAR_FIELDS.map((config) => (
                    <DataCell
                      key={config[0]}
                      row={row}
                      config={config}
                      canEdit={canEdit}
                      onSave={handleSave}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <PlannedSalesCharts data={chartData} />
      
      <Toast message={toast} />

    </div>
  );
}