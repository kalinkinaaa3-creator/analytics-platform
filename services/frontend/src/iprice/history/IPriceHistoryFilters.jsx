import {
  useMemo,
  useState,
} from "react";

import {
  IPriceDependentMultiSelect,
} from "../components/IPriceDependentMultiSelect";
import {clearIPriceFilterSearches} from "../components/ipriceFilterEvents";

import {
  IPRICE_PRODUCT_FILTERS,
  IPRICE_REGION_FILTERS,
} from "../filterDefinitions";


export function IPriceHistoryFilters({
  mode = "products",
  options = {},
  selected = {},
  loading = false,
  onChange,
  onClear,
}) {
  const [expanded, setExpanded] = useState(true);

  const definitions = (
    mode === "regions"
      ? IPRICE_REGION_FILTERS
      : IPRICE_PRODUCT_FILTERS
  );

  const selectedCount = useMemo(
    () => definitions.reduce(
      (total, [filterName]) => (
        total
        + (
          Array.isArray(selected?.[filterName])
            ? selected[filterName].length
            : 0
        )
      ),
      0,
    ),
    [definitions, selected],
  );

  function changeFilter(filterName, values) {
    const nextFilters = {
      ...(selected || {}),
    };

    if (Array.isArray(values) && values.length > 0) {
      nextFilters[filterName] = values;
    } else {
      delete nextFilters[filterName];
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
          aria-label={
            expanded
              ? "Скрыть фильтры"
              : "Показать фильтры"
          }
          title={
            expanded
              ? "Скрыть фильтры"
              : "Показать фильтры"
          }
          onClick={() => {
            setExpanded((previous) => !previous);
          }}
        >
          <span
            className={[
              "iprice-filters-toggle__chevron",
              expanded
                ? "iprice-filters-toggle__chevron--expanded"
                : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden="true"
          />
        </button>

        <div className="iprice-filters-panel__summary">
          Выбрано фильтров:{" "}
          <strong>{selectedCount}</strong>
        </div>
      </div>

      {expanded && (
        <>
          <div className="iprice-filters-grid">
            {definitions.map(([
              filterName,
              filterLabel,
            ]) => (
              <IPriceDependentMultiSelect
                key={filterName}
                name={filterName}
                label={filterLabel}
                options={options?.[filterName] || []}
                selected={selected?.[filterName] || []}
                loading={
                  loading
                  && !options?.[filterName]
                }
                onChange={changeFilter}
              />
            ))}
          </div>

          <div className="iprice-filters-actions">
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                clearIPriceFilterSearches();
                onClear?.();
              }}
            >
              Очистить фильтры
            </button>
          </div>
        </>
      )}
    </section>
  );
}
