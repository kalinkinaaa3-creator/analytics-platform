import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  downloadManagerTrackingTemplate,
  exportCrmRows,
  fetchCrmDashboard,
  fetchCrmFilters,
  fetchCrmRefreshState,
  fetchCrmRows,
  refreshCrmAnalytics,
  uploadManagerTracking,
} from "./crmAnalyticsApi";
import "./crm_analytics.css";


const STATUS_LABELS = {
  unprocessed: "Не обработан",
  assigned: "Назначен",
  in_progress: "В работе",
  converted: "Конвертирован",
  low_quality: "Некачественный",
  other: "Прочее",
  unmapped: "Не настроен",
};

function isoDate(value) {
  return value.toISOString().slice(0, 10);
}

function initialFilters() {
  const today = new Date();
  return {
    date_start: `${today.getFullYear()}-01-01`,
    date_end: isoDate(today),
    department_ids: [],
    manager_ids: [],
    source_ids: [],
    status_ids: [],
    group_by: "month",
  };
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(number);
}

function formatDate(value, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", includeTime ? {
    dateStyle: "short",
    timeStyle: "short",
  } : { dateStyle: "short" }).format(date);
}

function KpiCard({ label, value, note }) {
  return (
    <article className="crm-kpi-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </article>
  );
}

function FilterSelect({ label, value, options, valueKey, labelKey, onChange }) {
  return (
    <label className="crm-filter">
      <span>{label}</span>
      <select value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
        <option value="">Все</option>
        {options.map((item) => (
          <option key={item[valueKey]} value={item[valueKey]}>
            {item[labelKey] || item[valueKey]}
          </option>
        ))}
      </select>
    </label>
  );
}

function mergeStatusSeries(rows) {
  const byPeriod = new Map();
  rows.forEach((row) => {
    const key = String(row.period);
    const current = byPeriod.get(key) || { period: key };
    current[row.dashboard_status] = Number(row.value || 0);
    byPeriod.set(key, current);
  });
  return Array.from(byPeriod.values());
}

function mergeComparisonSeries(currentRows, previousRows) {
  const size = Math.max(currentRows.length, previousRows.length);
  return Array.from({ length: size }, (_, index) => ({
    period: currentRows[index]?.period || previousRows[index]?.period || "",
    current: Number(currentRows[index]?.value || 0),
    previous: Number(previousRows[index]?.value || 0),
  }));
}

export function CrmAnalyticsDashboard({ dashboard: dashboardMeta }) {
  const [activeTab, setActiveTab] = useState("leads");
  const [filters, setFilters] = useState(initialFilters);
  const [filterOptions, setFilterOptions] = useState({
    departments: [], managers: [], sources: [], statuses: [], last_updated_at: null,
  });
  const [dashboard, setDashboard] = useState(null);
  const [rows, setRows] = useState({ items: [], page: 1, pages: 0, total: 0 });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [uploadingManagers, setUploadingManagers] = useState(false);
  const canEdit = Boolean(dashboardMeta?.can_edit);

  const payload = useMemo(() => ({ ...filters }), [filters]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [dashboardResult, rowsResult] = await Promise.all([
        fetchCrmDashboard(payload),
        fetchCrmRows({ ...payload, page, page_size: 50 }),
      ]);
      setDashboard(dashboardResult);
      setRows(rowsResult);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось загрузить аналитику CRM.");
    } finally {
      setLoading(false);
    }
  }, [page, payload]);

  useEffect(() => {
    fetchCrmFilters().then((options) => {
      setFilterOptions(options);
      setRefreshing(Boolean(options.refresh?.running));
    }).catch(() => {
      setError("Не удалось загрузить справочники фильтров.");
    });
  }, []);

  useEffect(() => {
    // Initial and filter-driven synchronization with the dashboard API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [loadData]);

  function setSingleFilter(name, value, numeric = false) {
    setPage(1);
    setFilters((current) => ({
      ...current,
      [name]: value === "" ? [] : [numeric ? Number(value) : value],
    }));
  }

  async function handleExport() {
    setExporting(true);
    try {
      await exportCrmRows(payload);
    } catch {
      setError("Не удалось сформировать Excel-выгрузку.");
    } finally {
      setExporting(false);
    }
  }

  const reloadAll = useCallback(async () => {
    setFilterOptions(await fetchCrmFilters());
    await loadData();
  }, [loadData]);

  async function handleRefresh() {
    setError("");
    try {
      await refreshCrmAnalytics();
      setRefreshing(true);
    } catch (requestError) {
      if (requestError.response?.status === 409) setRefreshing(true);
      else setError(requestError.response?.data?.detail || "Не удалось запустить обновление.");
    }
  }

  async function handleManagersUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadingManagers(true);
    setError("");
    try {
      await uploadManagerTracking(file);
      setRefreshing(true);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось загрузить перечень менеджеров.");
    } finally {
      setUploadingManagers(false);
      event.target.value = "";
    }
  }

  useEffect(() => {
    if (!refreshing) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const state = await fetchCrmRefreshState();
        if (!state.running) {
          setRefreshing(false);
          if (state.status === "failed") setError(state.error || "Обновление завершилось с ошибкой.");
          else await reloadAll();
        }
      } catch {
        // Повторяем проверку состояния на следующем интервале.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [refreshing, reloadAll]);

  const cards = dashboard?.cards || {};
  const comparison = dashboard?.comparison || {};
  const speed = dashboard?.processing_speed || {};
  const statusSeries = mergeStatusSeries(dashboard?.status_dynamics || []);
  const leadComparisonSeries = mergeComparisonSeries(
    dashboard?.lead_dynamics || [],
    comparison?.lead_dynamics || [],
  );
  const lowQualityComparisonSeries = mergeComparisonSeries(
    dashboard?.low_quality_dynamics || [],
    comparison?.low_quality_dynamics || [],
  );
  const statusKeys = Array.from(new Set(
    (dashboard?.status_dynamics || []).map((item) => item.dashboard_status),
  ));

  return (
    <main className="crm-dashboard">
      <header className="crm-dashboard__header">
        <h1>Аналитика CRM</h1>
        <div className="crm-dashboard__actions">
          {canEdit && <button type="button" onClick={downloadManagerTrackingTemplate}>Шаблон менеджеров</button>}
          {canEdit && <label className="crm-upload-button">{uploadingManagers ? "Загрузка…" : "Загрузить менеджеров"}<input type="file" accept=".xlsx" disabled={uploadingManagers || refreshing} onChange={handleManagersUpload} /></label>}
          {canEdit && <button type="button" onClick={handleRefresh} disabled={refreshing} title={filterOptions.last_updated_at ? `Данные актуальны на: ${formatDate(filterOptions.last_updated_at, true)}` : "Данные отсутствуют"}>{refreshing ? "Обновление…" : "Обновить"}</button>}
        </div>
      </header>

      <section className="crm-filters" aria-label="Фильтры аналитики CRM">
        <FilterSelect label="Подразделение" value={filters.department_ids[0]} options={filterOptions.departments} valueKey="primary_department_id" labelKey="department_name" onChange={(value) => setSingleFilter("department_ids", value, true)} />
        <FilterSelect label="Менеджер" value={filters.manager_ids[0]} options={filterOptions.managers} valueKey="manager_id" labelKey="manager_name" onChange={(value) => setSingleFilter("manager_ids", value, true)} />
        <FilterSelect label="Источник" value={filters.source_ids[0]} options={filterOptions.sources} valueKey="source_id" labelKey="source_name" onChange={(value) => setSingleFilter("source_ids", value)} />
        <FilterSelect label="Стадия" value={filters.status_ids[0]} options={filterOptions.statuses} valueKey="status_id" labelKey="status_name" onChange={(value) => setSingleFilter("status_ids", value)} />
        <label className="crm-filter">
          <span>Группировка</span>
          <select value={filters.group_by} onChange={(event) => setFilters((current) => ({ ...current, group_by: event.target.value }))}>
            <option value="day">День</option><option value="week">Неделя</option><option value="month">Месяц</option><option value="quarter">Квартал</option><option value="year">Год</option>
          </select>
        </label>
        <label className="crm-filter"><span>Дата начала</span><input type="date" value={filters.date_start} onChange={(event) => { setPage(1); setFilters((current) => ({ ...current, date_start: event.target.value })); }} /></label>
        <label className="crm-filter"><span>Дата окончания</span><input type="date" value={filters.date_end} onChange={(event) => { setPage(1); setFilters((current) => ({ ...current, date_end: event.target.value })); }} /></label>
      </section>

      <nav className="crm-tabs" aria-label="Разделы аналитики CRM">
        <button type="button" className={activeTab === "leads" ? "active" : ""} onClick={() => setActiveTab("leads")}>Лидогенерация</button>
        <button type="button" className={activeTab === "analytics" ? "active" : ""} onClick={() => setActiveTab("analytics")}>Аналитика</button>
      </nav>

      {error && <div className="crm-alert">{error}</div>}
      {loading && <div className="crm-loading">Загрузка данных…</div>}

      {!loading && activeTab === "leads" && (
        <>
          <section className="crm-kpi-grid">
            <KpiCard label="Всего лидов" value={formatNumber(cards.total)} note={`Год к году: ${formatNumber(comparison.total_change_percent, 1)}%`} />
            <KpiCard label="Обработано" value={formatNumber(cards.processed)} />
            <KpiCard label="Не обработано" value={formatNumber(cards.unprocessed)} />
            <KpiCard label="Передано в АПМ" value={formatNumber(cards.apm)} />
            <KpiCard label="Некачественные" value={formatNumber(cards.low_quality)} />
            <KpiCard label="Стадия не настроена" value={formatNumber(cards.unmapped)} />
          </section>
          <section className="crm-panel">
            <div className="crm-panel__title"><div><h2>Лиды</h2><p>Найдено: {formatNumber(rows.total)}</p></div><button type="button" onClick={handleExport} disabled={exporting}>{exporting ? "Формирование…" : "Выгрузить Excel"}</button></div>
            <div className="crm-table-wrap"><table><thead><tr><th>ID</th><th>Название лида</th><th>Менеджер</th><th>Стадия</th><th>Источник</th><th>Дата создания</th><th title="По данным Bitrix24">Дата изменения</th><th>Сумма, руб</th><th>Обработка, дней</th></tr></thead><tbody>{rows.items.map((item) => <tr key={item.lead_id}><td>{item.lead_id}</td><td>{item.title || "—"}</td><td>{item.manager_name || "—"}</td><td><span className={`crm-status crm-status--${item.dashboard_status}`}>{item.status_name || STATUS_LABELS[item.dashboard_status] || item.status_id || "—"}</span></td><td>{item.source_name || item.source_id || "—"}</td><td>{formatDate(item.source_created_at, true)}</td><td>{formatDate(item.source_updated_at, true)}</td><td>{formatNumber(item.opportunity, 2)}</td><td>{formatNumber(item.processing_duration_days, 2)}</td></tr>)}</tbody></table></div>
            <div className="crm-pagination"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Назад</button><span>Страница {rows.page || 1} из {Math.max(rows.pages || 1, 1)}</span><button type="button" disabled={page >= rows.pages} onClick={() => setPage((value) => value + 1)}>Далее</button></div>
          </section>
        </>
      )}

      {!loading && activeTab === "analytics" && (
        <>
          <section className="crm-kpi-grid crm-kpi-grid--speed">
            <KpiCard label="Средняя скорость, дней" value={formatNumber(speed.average_days, 2)} />
            <KpiCard label="Медиана, дней" value={formatNumber(speed.median_days, 2)} />
            <KpiCard label="P75, дней" value={formatNumber(speed.p75_days, 2)} />
            <KpiCard label="P90, дней" value={formatNumber(speed.p90_days, 2)} note={`Лидов в расчёте: ${formatNumber(speed.sample_size)}`} />
          </section>
          <section className="crm-chart-grid">
            <article className="crm-panel"><h2>Динамика лидов</h2><ResponsiveContainer width="100%" height={300}><LineChart data={leadComparisonSeries}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period" /><YAxis allowDecimals={false} /><Tooltip /><Legend /><Line type="monotone" dataKey="current" name="Выбранный период" stroke="#2563eb" strokeWidth={3} /><Line type="monotone" dataKey="previous" name="Годом ранее" stroke="#94a3b8" strokeWidth={2} strokeDasharray="6 4" /></LineChart></ResponsiveContainer></article>
            <article className="crm-panel"><h2>Динамика некачественных лидов</h2><ResponsiveContainer width="100%" height={300}><LineChart data={lowQualityComparisonSeries}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period" /><YAxis allowDecimals={false} /><Tooltip /><Legend /><Line type="monotone" dataKey="current" name="Выбранный период" stroke="#dc2626" strokeWidth={3} /><Line type="monotone" dataKey="previous" name="Годом ранее" stroke="#f59e0b" strokeWidth={2} strokeDasharray="6 4" /></LineChart></ResponsiveContainer></article>
            <article className="crm-panel crm-panel--wide"><h2>Структура статусов</h2><ResponsiveContainer width="100%" height={340}><BarChart data={statusSeries}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period" /><YAxis allowDecimals={false} /><Tooltip /><Legend />{statusKeys.map((key, index) => <Bar key={key} dataKey={key} name={STATUS_LABELS[key] || key} stackId="statuses" fill={["#2563eb", "#0f766e", "#f59e0b", "#7c3aed", "#dc2626", "#64748b"][index % 6]} />)}</BarChart></ResponsiveContainer></article>
          </section>
        </>
      )}
    </main>
  );
}
