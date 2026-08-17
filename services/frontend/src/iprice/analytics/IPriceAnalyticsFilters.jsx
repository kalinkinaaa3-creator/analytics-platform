import {
  useMemo,
  useState,
} from "react";

import {
  IPriceDependentMultiSelect,
} from "../components/IPriceDependentMultiSelect";

import {
  IPRICE_REGION_FILTERS,
} from "../filterDefinitions";


export function IPriceAnalyticsFilters({
  options = {},
  selected = {},
  loading = false,
  error = "",
  onChange,
  onClear,
  canClear = false,
}) {
  const [expanded, setExpanded] = useState(true);

  const selectedCount = useMemo(
    () => Object.values(selected || {}).filter(
      (values) => Array.isArray(values) && values.length > 0,
    ).length,
    [selected],
  );

  function changeFilter(name, values) {
    const nextFilters = {...(selected || {})};

    if (Array.isArray(values) && values.length > 0) {
      nextFilters[name] = values;
    } else {
      delete nextFilters[name];
    }

    onChange?.(nextFilters);
  }

  return (
    <section className="iprice-filters-panel">
      <div className="iprice-filters-panel__header">
        <button
          type="button"
          className="iprice-filters-toggle"
          aria-expanded={expanded}
          aria-label={expanded ? "Скрыть фильтры" : "Показать фильтры"}
          title={expanded ? "Скрыть фильтры" : "Показать фильтры"}
          onClick={() => setExpanded((previous) => !previous)}
        >
          <span
            className={[
              "iprice-filters-toggle__chevron",
              expanded ? "iprice-filters-toggle__chevron--expanded" : "",
            ].filter(Boolean).join(" ")}
            aria-hidden="true"
          />
        </button>

        <div className="iprice-filters-panel__summary">
          Выбрано фильтров: <strong>{selectedCount}</strong>
        </div>
      </div>

      {expanded && error && (
        <div className="iprice-inline-error">{error}</div>
      )}

      {expanded && (
        <>
          <div className="iprice-filters-grid">
            {IPRICE_REGION_FILTERS.map(([name, label]) => (
              <IPriceDependentMultiSelect
                key={name}
                name={name}
                label={label}
                options={options?.[name] || []}
                selected={selected?.[name] || []}
                loading={loading && !options?.[name]}
                onChange={changeFilter}
              />
            ))}
          </div>

          <div className="iprice-filters-actions">
            <button
              type="button"
              disabled={loading || (selectedCount === 0 && !canClear)}
              onClick={() => onClear?.()}
            >
              Очистить фильтры
            </button>
          </div>
        </>
      )}
    </section>
  );
}
