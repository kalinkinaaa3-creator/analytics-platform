/* eslint-disable react-hooks/set-state-in-effect */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  Cell,
  Tooltip,
  Treemap,
} from "recharts";

import {
  useSearchParams,
} from "react-router-dom";

import {
  getIPricePriceAnalytics,
  getIPriceSnapshotFilters,
  createIPriceAnalyticsSelection,
  updateIPricePriceZones,
} from "../api/ipriceApi";

import {
  IPRICE_REGION_FILTERS,
} from "../filterDefinitions";

import {
  IPriceProductImage,
} from "../components/IPriceProductImage";

import {
  IPriceAnalyticsFilters,
} from "./IPriceAnalyticsFilters";

import {
  IPricePriceZoneDialog,
} from "./IPricePriceZoneDialog";


const FILTER_PARAM_PREFIX = "af_";
const PAGE_SIZE = 50;

const DRILL_FIELDS = [
  "category",
  "subcategory",
  "subcategory_type",
];

const ZONE_META = {
  below_market: {
    label: "Ниже рынка",
    color: "#d99a02",
    className: "below",
  },
  in_market: {
    label: "В рынке",
    color: "#307672",
    className: "market",
  },
  above_market: {
    label: "Выше рынка",
    color: "#e53d34",
    className: "above",
  },
  critical_above: {
    label: "Критически выше",
    color: "#930d06",
    className: "critical",
  },
  no_market_data: {
    label: "Нет данных",
    color: "#8b8f89",
    className: "empty",
  },
};


function getErrorMessage(error, fallback) {
  return (
    error?.response?.data?.message
    || error?.response?.data?.detail
    || error?.message
    || fallback
  );
}


function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(number);
}


function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(number)} ₽`;
}


function formatPercent(value, signed = false) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  const prefix = signed && number > 0 ? "+" : "";
  return `${prefix}${new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(number)}%`;
}


function formatCalculationStatus(value) {
  return ({
    success: "Рассчитано",
    warning: "Есть предупреждения",
    error: "Ошибка",
  })[value] || "—";
}


function AnalyticsStatusBadge({value}) {
  return (
    <span className={[
      "iprice-row-status",
      value ? `iprice-row-status--${value}` : "",
    ].filter(Boolean).join(" ")}>
      {formatCalculationStatus(value)}
    </span>
  );
}


function normalizeFilters(filters) {
  return Object.fromEntries(
    Object.entries(filters || {}).filter(
      ([, values]) => Array.isArray(values) && values.length > 0,
    ),
  );
}


function readFiltersFromUrl(searchParams) {
  const filters = {};
  IPRICE_REGION_FILTERS.forEach(([name]) => {
    const values = searchParams.getAll(`${FILTER_PARAM_PREFIX}${name}`);
    if (values.length > 0) {
      filters[name] = values;
    }
  });
  return filters;
}


function readDrillFromUrl(searchParams) {
  const path = {};
  DRILL_FIELDS.forEach((field) => {
    const value = searchParams.get(`ad_${field}`);
    if (value) {
      path[field] = value;
    }
  });

  let level = "root";
  if (path.category) level = "category";
  if (path.subcategory) level = "subcategory";
  if (path.subcategory_type) level = "subcategory_type";
  return {path, level};
}


function zoneForDeviation(value, config) {
  const deviation = Number(value);
  if (!Number.isFinite(deviation)) return "no_market_data";
  if (deviation < Number(config?.below_market_percent ?? -3)) {
    return "below_market";
  }
  if (deviation <= Number(config?.above_market_percent ?? 3)) {
    return "in_market";
  }
  if (deviation <= Number(config?.critical_percent ?? 10)) {
    return "above_market";
  }
  return "critical_above";
}


function TreemapTile(props) {
  const {
    x,
    y,
    width,
    height,
    depth,
    name,
    item,
    zone,
    onSelect,
  } = props;

  if (depth !== 1 || width < 2 || height < 2) {
    return null;
  }

  const meta = ZONE_META[zone] || ZONE_META.no_market_data;
  const showLabel = width >= 90 && height >= 46;
  const showValue = width >= 120 && height >= 72;

  return (
    <g
      className="iprice-analytics-treemap__tile"
      onClick={() => onSelect?.(item)}
    >
      <rect
        x={x + 1}
        y={y + 1}
        width={Math.max(0, width - 2)}
        height={Math.max(0, height - 2)}
        rx={4}
        fill={meta.color}
      />
      {showLabel && (
        <text
          x={x + 10}
          y={y + 20}
          fill="#ffffff"
          fontSize="12"
          fontWeight="700"
        >
          {String(name || "").slice(0, Math.max(8, Math.floor(width / 8)))}
        </text>
      )}
      {showValue && (
        <text
          x={x + 10}
          y={y + 40}
          fill="rgba(255,255,255,0.88)"
          fontSize="11"
        >
          {formatNumber(item?.product_count)} товаров
        </text>
      )}
    </g>
  );
}


function AnalyticsTooltip({active, payload}) {
  if (!active || !payload?.length) {
    return null;
  }

  const source = payload[0]?.payload;
  const item = source?.item || source;
  if (!item) return null;

  return (
    <div className="iprice-analytics-tooltip">
      <strong>{item.label || item.nom || "Не указано"}</strong>
      <span>Товаров: {formatNumber(item.product_count || 1)}</span>
      <span>Покрытие: {formatPercent(item.market_coverage_percent)}</span>
      <span>
        Отклонение: {formatPercent(
          item.median_deviation_percent ?? item.deviation_percent,
          true,
        )}
      </span>
      {Array.isArray(item.zones) && item.zones.map((zone) => (
        <span key={zone.key} className="iprice-analytics-tooltip__zone">
          <i style={{backgroundColor: ZONE_META[zone.key]?.color}} />
          {zone.label}: {formatNumber(zone.count)}
        </span>
      ))}
    </div>
  );
}


function AnalyticsTreemapChart({items, onSelect}) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;

    function updateWidth() {
      const nextWidth = Math.floor(element.getBoundingClientRect().width);
      setWidth((current) => current === nextWidth ? current : nextWidth);
    }

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="iprice-analytics-treemap">
      {width > 0 && (
        <Treemap
          width={width}
          height={250}
          data={items}
          dataKey="size"
          nameKey="name"
          content={<TreemapTile onSelect={onSelect} />}
          isAnimationActive={false}
        >
          {items.map((item) => (
            <Cell key={item.name} fill={ZONE_META[item.zone]?.color} />
          ))}
          <Tooltip content={<AnalyticsTooltip />} />
        </Treemap>
      )}
    </div>
  );
}


function MetricCard({label, value, detail, tone = "neutral", onClick}) {
  return (
    <button type="button" className={`iprice-analytics-metric iprice-analytics-metric--${tone}`} onClick={onClick}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </button>
  );
}


function ZoneDistribution({zones = [], onSelect}) {
  const maximum = Math.max(1, ...zones.map((zone) => Number(zone.count || 0)));

  return (
    <div className="iprice-analytics-zones">
      {zones.map((zone) => {
        const meta = ZONE_META[zone.key] || ZONE_META.no_market_data;
        return (
          <button type="button" className="iprice-analytics-zone-row" key={zone.key} onClick={() => onSelect?.([zone.key])}>
            <div className="iprice-analytics-zone-row__label">
              <span className={`iprice-analytics-zone-dot iprice-analytics-zone-dot--${meta.className}`} />
              <span>{zone.key === "no_market_data" ? "Нет данных / Эксклюзивы" : zone.label || meta.label}</span>
              <strong>{formatNumber(zone.count)}</strong>
            </div>
            <div className="iprice-analytics-zone-row__track">
              <span
                style={{
                  width: `${Math.max(2, Number(zone.count || 0) / maximum * 100)}%`,
                  backgroundColor: meta.color,
                }}
              />
            </div>
            <small>{formatPercent(zone.percent)}</small>
          </button>
        );
      })}
    </div>
  );
}


function PriceDelta({amount, percent}) {
  return (
    <span className="iprice-analytics-delta">
      <strong>{formatMoney(amount)}</strong>
      <small>{formatPercent(percent, true)}</small>
    </span>
  );
}


function ZoneMix({zones = [], total = 0}) {
  return (
    <div className="iprice-analytics-zone-mix" title={zones.map((zone) => `${zone.label}: ${zone.count}`).join("; ")}>
      <div className="iprice-analytics-zone-mix__bar">
        {zones.filter((zone) => Number(zone.count) > 0).map((zone) => (
          <span key={zone.key} style={{width: `${Number(zone.count) / Math.max(1, Number(total)) * 100}%`, backgroundColor: ZONE_META[zone.key]?.color}} />
        ))}
      </div>
      <div className="iprice-analytics-zone-mix__legend">
        {zones.filter((zone) => Number(zone.count) > 0).map((zone) => (
          <span key={zone.key}><i style={{backgroundColor: ZONE_META[zone.key]?.color}} />{formatNumber(zone.count)}</span>
        ))}
      </div>
    </div>
  );
}


function SortHeader({field, ordering, onSort, children, back = false, onBack}) {
  const active = ordering === field || ordering === `-${field}`;
  return (
    <th>
      <div className="iprice-analytics-sort-header">
        {back && <button type="button" className="iprice-analytics-back" onClick={onBack} aria-label="Назад" title="Назад">‹</button>}
        <button type="button" onClick={() => onSort(field)}>
          <span>{children}</span>
          <i className={active ? "is-active" : ""}>{ordering === field ? "↑" : "↓"}</i>
        </button>
      </div>
    </th>
  );
}


export function IPriceAnalyticsTab({
  snapshot,
  onOpenProduct,
  onOpenPricingSelection,
  realtimeEvent,
  canEdit = false,
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [initialDrill] = useState(
    () => readDrillFromUrl(searchParams),
  );
  const analyticsRequestRef = useRef(0);
  const regionsRequestRef = useRef(0);
  const filtersRequestRef = useRef(0);

  const [filters, setFilters] = useState(
    () => readFiltersFromUrl(searchParams),
  );
  const [filterOptions, setFilterOptions] = useState({});
  const [filtersLoading, setFiltersLoading] = useState(false);
  const [filtersError, setFiltersError] = useState("");
  const [searchInput, setSearchInput] = useState(
    () => searchParams.get("a_search") || "",
  );
  const [appliedSearch, setAppliedSearch] = useState(
    () => searchParams.get("a_search") || "",
  );
  const [drillPath, setDrillPath] = useState(initialDrill.path);
  const [drillLevel, setDrillLevel] = useState(initialDrill.level);
  const [page, setPage] = useState(1);
  const [ordering, setOrdering] = useState("-product_count");
  const [selectedZones, setSelectedZones] = useState([]);
  const [tableMode, setTableMode] = useState("products");
  const [analytics, setAnalytics] = useState(null);
  const [regions, setRegions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [error, setError] = useState("");
  const [zoneConfig, setZoneConfig] = useState(null);
  const [zoneDialogOpen, setZoneDialogOpen] = useState(false);
  const [zoneSaving, setZoneSaving] = useState(false);
  const [zoneError, setZoneError] = useState("");
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState("");
  const realtimeVersion = realtimeEvent?.receivedAt || 0;

  const cleanFilters = useMemo(
    () => normalizeFilters(filters),
    [filters],
  );

  const snapshotReady = Boolean(
    snapshot?.id && snapshot?.status === "success",
  );
  const pricingEditable = Boolean(
    canEdit && snapshotReady && snapshot?.is_latest && !snapshot?.is_active
  );
  const hasSelection = Boolean(
    Object.keys(cleanFilters).length
    || appliedSearch
    || Object.keys(drillPath).length
    || selectedZones.length
  );

  const writeUrlState = useCallback(({
    nextFilters = filters,
    nextSearch = appliedSearch,
    nextPath = drillPath,
  } = {}) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);

      IPRICE_REGION_FILTERS.forEach(([name]) => {
        next.delete(`${FILTER_PARAM_PREFIX}${name}`);
      });
      Object.entries(normalizeFilters(nextFilters)).forEach(([name, values]) => {
        values.forEach((value) => {
          next.append(`${FILTER_PARAM_PREFIX}${name}`, value);
        });
      });

      if (nextSearch) next.set("a_search", nextSearch);
      else next.delete("a_search");

      DRILL_FIELDS.forEach((field) => next.delete(`ad_${field}`));
      Object.entries(nextPath || {}).forEach(([field, value]) => {
        next.set(`ad_${field}`, value);
      });

      return next;
    }, {replace: true});
  }, [appliedSearch, drillPath, filters, setSearchParams]);

  const loadFilters = useCallback(async () => {
    if (!snapshotReady) return;
    const requestId = filtersRequestRef.current + 1;
    filtersRequestRef.current = requestId;
    setFiltersLoading(true);
    setFiltersError("");

    try {
      const result = await getIPriceSnapshotFilters(snapshot.id, {
        mode: "regions",
        filters: cleanFilters,
      });
      if (requestId === filtersRequestRef.current) {
        setFilterOptions(result.options || {});
      }
    } catch (requestError) {
      if (requestId === filtersRequestRef.current) {
        setFiltersError(getErrorMessage(
          requestError,
          "Не удалось загрузить значения фильтров.",
        ));
      }
    } finally {
      if (requestId === filtersRequestRef.current) {
        setFiltersLoading(false);
      }
    }
  }, [cleanFilters, snapshot, snapshotReady]);

  const loadAnalytics = useCallback(async () => {
    if (!snapshotReady) {
      setAnalytics(null);
      return;
    }
    const requestId = analyticsRequestRef.current + 1;
    analyticsRequestRef.current = requestId;
    setLoading(true);
    setError("");

    try {
      const result = await getIPricePriceAnalytics(snapshot.id, {
        view: "products",
        filters: cleanFilters,
        search: appliedSearch,
        drill_level: drillLevel,
        drill_path: drillPath,
        page,
        page_size: PAGE_SIZE,
        ordering,
        price_zones: selectedZones,
      });
      if (requestId === analyticsRequestRef.current) {
        setAnalytics(result);
        setZoneConfig(result.price_zones || null);
      }
    } catch (requestError) {
      if (requestId === analyticsRequestRef.current) {
        setAnalytics(null);
        setError(getErrorMessage(
          requestError,
          "Не удалось загрузить ценовую аналитику.",
        ));
      }
    } finally {
      if (requestId === analyticsRequestRef.current) {
        setLoading(false);
      }
    }
  }, [
    appliedSearch,
    cleanFilters,
    drillLevel,
    drillPath,
    page,
    ordering,
    selectedZones,
    snapshot,
    snapshotReady,
  ]);

  const loadRegions = useCallback(async () => {
    if (!snapshotReady || tableMode !== "regions") return;
    const requestId = regionsRequestRef.current + 1;
    regionsRequestRef.current = requestId;
    setRegionsLoading(true);

    try {
      const result = await getIPricePriceAnalytics(snapshot.id, {
        view: "regions",
        filters: cleanFilters,
        search: appliedSearch,
        drill_level: drillLevel,
        drill_path: drillPath,
        page,
        page_size: PAGE_SIZE,
        ordering,
        price_zones: selectedZones,
      });
      if (requestId === regionsRequestRef.current) {
        setRegions(result);
      }
    } catch (requestError) {
      if (requestId === regionsRequestRef.current) {
        setRegions(null);
        setError(getErrorMessage(
          requestError,
          "Не удалось загрузить региональную детализацию.",
        ));
      }
    } finally {
      if (requestId === regionsRequestRef.current) {
        setRegionsLoading(false);
      }
    }
  }, [
    appliedSearch,
    cleanFilters,
    drillLevel,
    drillPath,
    page,
    ordering,
    selectedZones,
    snapshot,
    snapshotReady,
    tableMode,
  ]);

  useEffect(() => {
    loadFilters();
  }, [loadFilters, realtimeVersion]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics, realtimeVersion]);

  useEffect(() => {
    loadRegions();
  }, [loadRegions, realtimeVersion]);

  function changeFilters(nextFilters) {
    setFilters(nextFilters);
    setPage(1);
    setDrillPath({});
    setDrillLevel("root");
    setTableMode("products");
    setSelectedZones([]);
    writeUrlState({nextFilters, nextPath: {}});
  }

  function applySearch() {
    const nextSearch = searchInput.trim();
    setAppliedSearch(nextSearch);
    setPage(1);
    setDrillPath({});
    setDrillLevel("root");
    setTableMode("products");
    setSelectedZones([]);
    writeUrlState({nextSearch, nextPath: {}});
  }

  function clearAllFilters() {
    setFilters({});
    setSearchInput("");
    setAppliedSearch("");
    setPage(1);
    setDrillPath({});
    setDrillLevel("root");
    setTableMode("products");
    setSelectedZones([]);
    writeUrlState({nextFilters: {}, nextSearch: "", nextPath: {}});
  }

  function selectZones(nextZones) {
    setSelectedZones(nextZones || []);
    setPage(1);
  }

  function toggleOrdering(field) {
    setOrdering((current) => current === field ? `-${field}` : field);
    setPage(1);
  }

  function goBackOneLevel() {
    const depth = Object.keys(drillPath).length;
    if (!depth) return;
    openBreadcrumb(depth - 1);
  }

  function openGroup(item) {
    if (!analytics?.next_level || !item?.key) return;
    const nextPath = {
      ...drillPath,
      [analytics.next_level]: item.key,
    };
    setDrillPath(nextPath);
    setDrillLevel(analytics.next_level);
    setPage(1);
    setTableMode("products");
    writeUrlState({nextPath});
  }

  function openBreadcrumb(index) {
    const nextPath = {};
    DRILL_FIELDS.slice(0, index).forEach((field) => {
      if (drillPath[field]) nextPath[field] = drillPath[field];
    });
    const nextLevel = index === 0 ? "root" : DRILL_FIELDS[index - 1];
    setDrillPath(nextPath);
    setDrillLevel(nextLevel);
    setPage(1);
    setTableMode("products");
    writeUrlState({nextPath});
  }

  async function saveZones(values) {
    setZoneSaving(true);
    setZoneError("");
    try {
      const result = await updateIPricePriceZones(values);
      setZoneConfig(result);
      setZoneDialogOpen(false);
      await Promise.all([
        loadAnalytics(),
        loadFilters(),
        tableMode === "regions" ? loadRegions() : Promise.resolve(),
      ]);
    } catch (requestError) {
      setZoneError(getErrorMessage(
        requestError,
        "Не удалось сохранить ценовые зоны.",
      ));
    } finally {
      setZoneSaving(false);
    }
  }

  async function openPricingSelection() {
    if (!pricingEditable || !hasSelection || selectionLoading) return;
    setSelectionLoading(true);
    setSelectionError("");
    try {
      const selection = await createIPriceAnalyticsSelection(snapshot.id, {
        view: "products",
        filters: cleanFilters,
        search: appliedSearch,
        drill_level: drillLevel,
        drill_path: drillPath,
        price_zones: selectedZones,
      });
      onOpenPricingSelection?.(selection);
    } catch (requestError) {
      setSelectionError(getErrorMessage(
        requestError,
        "Не удалось подготовить выбранные товары.",
      ));
    } finally {
      setSelectionLoading(false);
    }
  }

  if (!snapshotReady) {
    return (
      <section className="iprice-tab-content">
        Для отображения аналитики необходимо выбрать успешно рассчитанную версию.
      </section>
    );
  }

  const summary = analytics?.summary || {};
  const zones = Array.isArray(summary.zones) ? summary.zones : [];
  const zoneCounts = summary.zone_counts || {};
  const aboveCount = Number(zoneCounts.above_market || 0)
    + Number(zoneCounts.critical_above || 0);
  const chartItems = (analytics?.result_type === "groups"
    ? analytics?.results || []
    : []).map((item) => ({
      name: item.label,
      size: Math.max(1, Number(item.product_count || 0)),
      zone: zoneForDeviation(item.median_deviation_percent, zoneConfig),
      item,
    }));
  const tableData = tableMode === "regions" ? regions : analytics;
  const tableRows = tableData?.results || [];
  const pagination = tableData?.pagination || {};

  return (
    <section className="iprice-analytics">
      <div className="iprice-calculation__top">
        <div className="iprice-search">
          <input
            type="search"
            value={searchInput}
            placeholder="Поиск по: код 1С, номенклатура 1С"
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                applySearch();
              }
            }}
          />
          <button type="button" onClick={applySearch}>Найти</button>
        </div>
      </div>

      <div className="iprice-calculation-workspace iprice-analytics-workspace">
        <IPriceAnalyticsFilters
          options={filterOptions}
          selected={filters}
          loading={filtersLoading}
          error={filtersError}
          onChange={changeFilters}
          onClear={clearAllFilters}
          canClear={Boolean(
            appliedSearch
            || selectedZones.length
            || Object.keys(drillPath).length
          )}
        />

        {loading && !analytics ? (
          <div className="iprice-analytics-loading">
            <span className="iprice-table-loading__spinner" />
            <span>Формируем ценовую аналитику…</span>
          </div>
        ) : error && !analytics ? (
          <div className="iprice-inline-error">{error}</div>
        ) : (
          <>
            <div className="iprice-analytics-actions">
              <nav className="iprice-analytics-breadcrumb" aria-label="Детализация аналитики">
                {(analytics?.breadcrumb || []).map((item, index) => (
                  <button
                    type="button"
                    key={`${item.level}-${item.value || "root"}`}
                    className={index === analytics.breadcrumb.length - 1 ? "is-current" : ""}
                    onClick={() => openBreadcrumb(index)}
                  >
                    {item.value || item.label}
                  </button>
                ))}
              </nav>

              <div className="iprice-analytics-actions__controls">
                <button
                  type="button"
                  className="iprice-analytics-button iprice-analytics-button--primary"
                  disabled={!pricingEditable || !hasSelection || selectionLoading}
                  title={
                    !canEdit
                      ? "Недостаточно прав для изменения параметров"
                      : snapshot?.is_active
                        ? "Версия активирована"
                        : !snapshot?.is_latest
                          ? "Редактирование доступно только в последней успешной версии"
                          : !hasSelection
                            ? "Выберите хотя бы один фильтр, ценовую зону или уровень детализации"
                            : "Перейти к настройке цен выбранных товаров"
                  }
                  onClick={openPricingSelection}
                >
                  {selectionLoading ? "Подготовка…" : "Настроить цены"}
                </button>
                <button
                  type="button"
                  className="iprice-analytics-button iprice-analytics-button--secondary"
                  disabled={!canEdit}
                  title={!canEdit ? "Недостаточно прав для настройки ценовых зон" : ""}
                  onClick={() => {
                    setZoneError("");
                    setZoneDialogOpen(true);
                  }}
                >
                  Настроить ценовые зоны
                </button>
              </div>
            </div>

            {selectionError && (
              <div className="iprice-inline-error">{selectionError}</div>
            )}

            <div className="iprice-analytics-metrics">
              <MetricCard
                label="Товаров"
                value={formatNumber(summary.total_products)}
                detail={`${formatNumber(summary.market_covered)} сопоставлено с конкурентами`}
                onClick={() => selectZones([])}
              />
              <MetricCard
                label="Покрытие рынком"
                value={formatPercent(summary.market_coverage_percent)}
                detail="Доля анализируемых товаров"
                tone="coverage"
                onClick={() => selectZones(["below_market", "in_market", "above_market", "critical_above"])}
              />
              <MetricCard
                label="Ниже рынка"
                value={formatNumber(zoneCounts.below_market)}
                detail="По медиане розницы"
                tone="below"
                onClick={() => selectZones(["below_market"])}
              />
              <MetricCard
                label="В рынке"
                value={formatNumber(zoneCounts.in_market)}
                detail="По медиане розницы"
                tone="market"
                onClick={() => selectZones(["in_market"])}
              />
              <MetricCard
                label="Выше рынка"
                value={formatNumber(aboveCount)}
                detail="По медиане розницы"
                tone="above"
                onClick={() => selectZones(["above_market", "critical_above"])}
              />
              <MetricCard
                label="Ошибки расчёта"
                value={formatNumber(summary.calculation_errors)}
                detail="Требуют проверки"
                tone="error"
                onClick={() => changeFilters({...filters, calculation_status: ["error"]})}
              />
            </div>

            <div className="iprice-analytics-visuals">
              <article className="iprice-analytics-panel iprice-analytics-panel--treemap">
                <div className="iprice-analytics-panel__header">
                  <div>
                    <h3>{analytics?.next_level_label || "Товары"}</h3>
                    <span>Размер — количество товаров, цвет — ценовая зона</span>
                  </div>
                  <strong>{formatPercent(summary.median_deviation_percent, true)}</strong>
                </div>

                {chartItems.length > 0 ? (
                  <AnalyticsTreemapChart
                    items={chartItems}
                    onSelect={openGroup}
                  />
                ) : (
                  <div className="iprice-analytics-panel__empty">
                    Детализация достигла уровня товара.
                  </div>
                )}
              </article>

              <article className="iprice-analytics-panel">
                <div className="iprice-analytics-panel__header">
                  <div>
                    <h3>Распределение по ценовым зонам</h3>
                    <span>
                      Активные пороги: {formatPercent(zoneConfig?.below_market_percent)} / {formatPercent(zoneConfig?.above_market_percent)} / {formatPercent(zoneConfig?.critical_percent)}
                    </span>
                  </div>
                </div>
                <ZoneDistribution zones={zones} onSelect={selectZones} />
              </article>
            </div>

            <div className="iprice-table-toolbar iprice-analytics-table-toolbar">
              <div className="iprice-table-toolbar__count">
                Найдено строк: <strong>{formatNumber(pagination.count)}</strong>
              </div>

              {analytics?.result_type === "products" && (
                <div className="iprice-mode-switch" role="group" aria-label="Детализация данных">
                  <button
                    type="button"
                    className={`iprice-mode-switch__button ${tableMode === "products" ? "iprice-mode-switch__button--active" : ""}`}
                    onClick={() => {
                      setTableMode("products");
                      setPage(1);
                    }}
                  >
                    По товарам
                  </button>
                  <button
                    type="button"
                    className={`iprice-mode-switch__button ${tableMode === "regions" ? "iprice-mode-switch__button--active" : ""}`}
                    onClick={() => {
                      setTableMode("regions");
                      setPage(1);
                    }}
                  >
                    По регионам
                  </button>
                </div>
              )}
            </div>

            <div className="iprice-table-wrapper iprice-analytics-table-wrapper">
              {(loading || regionsLoading) && (
                <div className="iprice-table-loading">
                  <span className="iprice-table-loading__spinner" />
                  <span>Загрузка данных…</span>
                </div>
              )}

              {!loading && !regionsLoading && tableRows.length === 0 ? (
                <div className="iprice-table-empty">По выбранным условиям данных нет.</div>
              ) : (
                <table className="iprice-rows-table iprice-analytics-table">
                  <thead>
                    {tableMode === "regions" ? (
                      <tr>
                        <th>Фото</th>
                        <SortHeader field="code_1c" ordering={ordering} onSort={toggleOrdering}>Код 1С</SortHeader>
                        <SortHeader field="nom" ordering={ordering} onSort={toggleOrdering} back={drillLevel !== "root"} onBack={goBackOneLevel}>Номенклатура 1С</SortHeader>
                        <th>Ключ системы</th>
                        <SortHeader field="sale_region" ordering={ordering} onSort={toggleOrdering}>Регион продажи</SortHeader>
                        <SortHeader field="departure" ordering={ordering} onSort={toggleOrdering}>Место производства</SortHeader>
                        <th>Метод расчёта</th>
                        <SortHeader field="retail_price" ordering={ordering} onSort={toggleOrdering}>Медиана розницы</SortHeader>
                        <SortHeader field="final_rrp" ordering={ordering} onSort={toggleOrdering}>Медиана итоговой РРЦ</SortHeader>
                        <th>Δ: розница − итоговая РРЦ</th>
                        <SortHeader field="market_price" ordering={ordering} onSort={toggleOrdering}>Медиана рынка</SortHeader>
                        <SortHeader field="final_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: итоговая РРЦ − рынок</SortHeader>
                        <SortHeader field="retail_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: розница − рынок</SortHeader>
                        <th>Ценовая зона</th>
                        <SortHeader field="calculation_status" ordering={ordering} onSort={toggleOrdering}>Статус</SortHeader>
                      </tr>
                    ) : analytics?.result_type === "groups" ? (
                      <tr>
                        <SortHeader field="label" ordering={ordering} onSort={toggleOrdering} back={drillLevel !== "root"} onBack={goBackOneLevel}>{analytics?.next_level_label}</SortHeader>
                        <SortHeader field="product_count" ordering={ordering} onSort={toggleOrdering}>Товаров</SortHeader>
                        <th>Распределение по ценовым зонам</th>
                        <SortHeader field="competitor_count" ordering={ordering} onSort={toggleOrdering}>Кол-во товаров-конкурентов</SortHeader>
                        <SortHeader field="market_coverage_percent" ordering={ordering} onSort={toggleOrdering}>Покрытие рынком</SortHeader>
                        <SortHeader field="median_retail_price" ordering={ordering} onSort={toggleOrdering}>Медиана розницы</SortHeader>
                        <SortHeader field="median_final_rrp" ordering={ordering} onSort={toggleOrdering}>Медиана итоговой РРЦ</SortHeader>
                        <SortHeader field="retail_delta" ordering={ordering} onSort={toggleOrdering}>Δ: розница − итоговая РРЦ</SortHeader>
                        <SortHeader field="median_market_price" ordering={ordering} onSort={toggleOrdering}>Медиана рынка</SortHeader>
                        <SortHeader field="final_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: итоговая РРЦ − рынок</SortHeader>
                        <SortHeader field="retail_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: розница − рынок</SortHeader>
                        <SortHeader field="calculation_errors" ordering={ordering} onSort={toggleOrdering}>Ошибки расчёта</SortHeader>
                      </tr>
                    ) : (
                      <tr>
                        <th>Фото</th>
                        <SortHeader field="code_1c" ordering={ordering} onSort={toggleOrdering}>Код 1С</SortHeader>
                        <SortHeader field="nom" ordering={ordering} onSort={toggleOrdering} back={drillLevel !== "root"} onBack={goBackOneLevel}>Номенклатура 1С</SortHeader>
                        <th>Ключ системы</th>
                        <SortHeader field="pricing_method" ordering={ordering} onSort={toggleOrdering}>Метод расчёта</SortHeader>
                        <SortHeader field="competitor_count" ordering={ordering} onSort={toggleOrdering}>Кол-во товаров-конкурентов</SortHeader>
                        <SortHeader field="median_retail_price" ordering={ordering} onSort={toggleOrdering}>Медиана розницы</SortHeader>
                        <SortHeader field="median_final_rrp" ordering={ordering} onSort={toggleOrdering}>Медиана итоговой РРЦ</SortHeader>
                        <SortHeader field="retail_delta" ordering={ordering} onSort={toggleOrdering}>Δ: розница − итоговая РРЦ</SortHeader>
                        <SortHeader field="median_market_price" ordering={ordering} onSort={toggleOrdering}>Медиана рынка</SortHeader>
                        <SortHeader field="final_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: итоговая РРЦ − рынок</SortHeader>
                        <SortHeader field="retail_market_delta_percent" ordering={ordering} onSort={toggleOrdering}>Δ: розница − рынок</SortHeader>
                        <SortHeader field="zone" ordering={ordering} onSort={toggleOrdering}>Ценовая зона</SortHeader>
                        <SortHeader field="calculation_status" ordering={ordering} onSort={toggleOrdering}>Статус</SortHeader>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {tableRows.map((row) => {
                      const zone = row.zone || zoneForDeviation(
                        row.median_deviation_percent,
                        zoneConfig,
                      );
                      const zoneMeta = ZONE_META[zone] || ZONE_META.no_market_data;
                      const isGroup = analytics?.result_type === "groups" && tableMode === "products";
                      const productId = row.id || row.product_id;

                      return (
                        <tr key={`${tableMode}-${row.id || row.key}`} className="iprice-table-row">
                          {tableMode === "regions" ? (
                            <>
                              <td><IPriceProductImage src={row.image} alt={row.nom} /></td>
                              <td>{row.code_1c || "—"}</td>
                              <td>
                                <button
                                  type="button"
                                  className="iprice-analytics-link"
                                  onClick={() => onOpenProduct?.({
                                    id: row.product_id,
                                    base_product_key: row.base_product_key,
                                    code_1c: row.code_1c,
                                    nom: row.nom,
                                  })}
                                >
                                  {row.nom || "Без наименования"}
                                </button>
                              </td>
                              <td>{row.base_product_key || "—"}</td>
                              <td>{row.sale_region || "—"}</td>
                              <td>{row.departure || "—"}</td>
                              <td>{({analog: "Аналог", exclusive: "Эксклюзив"})[row.pricing_method] || "—"}</td>
                              <td>{formatMoney(row.retail_price)}</td>
                              <td>{formatMoney(row.final_rrp)}</td>
                              <td><PriceDelta amount={row.retail_delta} percent={row.retail_delta_percent} /></td>
                              <td>{formatMoney(row.market_price)}</td>
                              <td><PriceDelta amount={row.final_market_delta} percent={row.final_market_delta_percent} /></td>
                              <td><PriceDelta amount={row.retail_market_delta} percent={row.retail_market_delta_percent} /></td>
                              <td><span className={`iprice-analytics-zone-badge iprice-analytics-zone-badge--${zoneMeta.className}`}>{zoneMeta.label}</span></td>
                              <td><AnalyticsStatusBadge value={row.calculation_status} /></td>
                            </>
                          ) : isGroup ? (
                            <>
                              <td>
                                <button type="button" className="iprice-analytics-link" onClick={() => openGroup(row)}>
                                  {row.label}
                                </button>
                              </td>
                              <td>{formatNumber(row.product_count)}</td>
                              <td><ZoneMix zones={row.zones} total={row.product_count} /></td>
                              <td>{formatNumber(row.competitor_count)}</td>
                              <td>{formatPercent(row.market_coverage_percent)}</td>
                              <td>{formatMoney(row.median_retail_price)}</td>
                              <td>{formatMoney(row.median_final_rrp)}</td>
                              <td><PriceDelta amount={row.retail_delta} percent={row.retail_delta_percent} /></td>
                              <td>{formatMoney(row.median_market_price)}</td>
                              <td><PriceDelta amount={row.final_market_delta} percent={row.final_market_delta_percent} /></td>
                              <td><PriceDelta amount={row.retail_market_delta} percent={row.retail_market_delta_percent} /></td>
                              <td>{formatNumber(row.calculation_errors)}</td>
                            </>
                          ) : (
                            <>
                              <td><IPriceProductImage src={row.image} alt={row.nom} /></td>
                              <td>{row.code_1c || "—"}</td>
                              <td>
                                <button
                                  type="button"
                                  className="iprice-analytics-link"
                                  onClick={() => onOpenProduct?.({
                                    id: productId,
                                    base_product_key: row.base_product_key,
                                    code_1c: row.code_1c,
                                    nom: row.nom,
                                  })}
                                >
                                  {row.nom || "Без наименования"}
                                </button>
                              </td>
                              <td>{row.base_product_key || "—"}</td>
                              <td>{({analog: "Аналог", exclusive: "Эксклюзив"})[row.pricing_method] || "—"}</td>
                              <td>{formatNumber(row.competitor_count)}</td>
                              <td>{formatMoney(row.median_retail_price)}</td>
                              <td>{formatMoney(row.median_final_rrp)}</td>
                              <td><PriceDelta amount={row.retail_delta} percent={row.retail_delta_percent} /></td>
                              <td>{formatMoney(row.median_market_price)}</td>
                              <td><PriceDelta amount={row.final_market_delta} percent={row.final_market_delta_percent} /></td>
                              <td><PriceDelta amount={row.retail_market_delta} percent={row.retail_market_delta_percent} /></td>
                              <td><span className={`iprice-analytics-zone-badge iprice-analytics-zone-badge--${zoneMeta.className}`}>{zoneMeta.label}</span></td>
                              <td><AnalyticsStatusBadge value={row.calculation_status} /></td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {Number(pagination.pages || 1) > 1 && (
              <div className="iprice-pagination">
                <button type="button" disabled={page <= 1} onClick={() => setPage((previous) => Math.max(1, previous - 1))}>Назад</button>
                <span>Страница {pagination.page || page} из {pagination.pages}</span>
                <button type="button" disabled={page >= pagination.pages} onClick={() => setPage((previous) => previous + 1)}>Вперёд</button>
              </div>
            )}
          </>
        )}
      </div>

      {zoneDialogOpen && (
        <IPricePriceZoneDialog
          key={zoneConfig?.id || "default"}
          open
          config={zoneConfig}
          saving={zoneSaving}
          error={zoneError}
          onClose={() => {
            if (!zoneSaving) setZoneDialogOpen(false);
          }}
          onSave={saveZones}
        />
      )}
    </section>
  );
}
