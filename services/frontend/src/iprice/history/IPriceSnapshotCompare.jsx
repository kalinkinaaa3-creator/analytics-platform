import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  compareIPriceSnapshots,
  getIPriceSnapshotCompareFilters,
} from "../api/ipriceApi";

import {
  IPriceHistoryFilters,
} from "./IPriceHistoryFilters";

import {
  IPriceProductImage,
} from "../components/IPriceProductImage";


const MODE_PRODUCTS = "products";
const MODE_REGIONS = "regions";


const HISTORY_REFRESH_EVENTS = new Set([
  "parameters_changed",
  "approval_saved",
  "competitor_selection_changed",
  "snapshot_finished",
  "snapshot_activated",
]);

const PRICE_TYPE_COLUMNS = [
  ["distr", "Дистрибьютор"],
  ["distr_1", "Дистрибьютор 1"],
  ["small", "Малый опт"],
  ["medium", "Средний опт"],
  ["large", "Крупный опт"],
];

const CHANGE_TYPE_OPTIONS = [
  {
    value: "all",
    label: "Все строки",
  },
  {
    value: "added",
    label: "Добавлены",
  },
  {
    value: "removed",
    label: "Удалены",
  },
  {
    value: "changed",
    label: "Изменены",
  },
  {
    value: "unchanged",
    label: "Без изменений",
  },
  {
    value: "price_increased",
    labels: {
      products: "Медиана розницы выросла",
      regions: "Розничная цена выросла",
    },
  },
  {
    value: "price_decreased",
    labels: {
      products: "Медиана розницы снизилась",
      regions: "Розничная цена снизилась",
    },
  },
  {
    value: "final_rrp_increased",
    labels: {
      products: "Медиана итоговой РРЦ выросла",
      regions: "Итоговая РРЦ выросла",
    },
  },
  {
    value: "final_rrp_decreased",
    labels: {
      products: "Медиана итоговой РРЦ снизилась",
      regions: "Итоговая РРЦ снизилась",
    },
  },
  {
    value: "new_error",
    label: "Новая ошибка",
  },
  {
    value: "resolved_error",
    label: "Ошибка устранена",
  },
  {
    value: "status_changed",
    label: "Статус изменён",
  },
];

const CHANGE_TYPE_LABELS = {
  added: "Добавлено",
  removed: "Удалено",
  changed: "Изменено",
  unchanged: "Без изменений",
};

const STATUS_LABELS = {
  success: "Рассчитано",
  warning: "Предупреждение",
  error: "Ошибка",
};

const PRICING_METHOD_LABELS = {
  analog: "Аналог",
  exclusive: "Эксклюзив",
};


function normalizeId(value) {
  const number = Number(value);

  if (
    !Number.isInteger(number)
    || number <= 0
  ) {
    return null;
  }

  return number;
}


function formatNumber(
  value,
  maximumFractionDigits = 2,
) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return String(value);
  }

  return number.toLocaleString(
    "ru-RU",
    {
      minimumFractionDigits: 0,
      maximumFractionDigits,
    },
  );
}


function formatMoney(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  return `${formatNumber(value)} ₽`;
}


function formatPercent(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return String(value);
  }

  return `${formatNumber(
    number * 100,
  )}%`;
}


function formatSignedMoney(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return String(value);
  }

  return `${number > 0 ? "+" : ""}${
    formatMoney(number)
  }`;
}


function calculateRetailDelta(
  retailValue,
  finalRrpValue,
) {
  const retail = Number(retailValue);
  const finalRrp = Number(finalRrpValue);

  if (
    retailValue === null
    || retailValue === undefined
    || retailValue === ""
    || finalRrpValue === null
    || finalRrpValue === undefined
    || finalRrpValue === ""
    || !Number.isFinite(retail)
    || !Number.isFinite(finalRrp)
  ) {
    return {
      amount: null,
      percent: null,
    };
  }

  const amount = retail - finalRrp;

  return {
    amount,
    percent: finalRrp !== 0
      ? amount / finalRrp
      : null,
  };
}


function calculateMargin(
  finalRrpValue,
  costValue,
) {
  const finalRrp = Number(finalRrpValue);
  const cost = Number(costValue);

  if (
    finalRrpValue === null
    || finalRrpValue === undefined
    || finalRrpValue === ""
    || costValue === null
    || costValue === undefined
    || costValue === ""
    || !Number.isFinite(finalRrp)
    || !Number.isFinite(cost)
    || finalRrp === 0
  ) {
    return null;
  }

  return (finalRrp - cost) / finalRrp;
}


function DeltaSnapshotValue({
  retailValue,
  finalRrpValue,
}) {
  const delta = calculateRetailDelta(
    retailValue,
    finalRrpValue,
  );

  return (
    <span className="iprice-history-delta-value">
      <span>{formatSignedMoney(delta.amount)}</span>
      <small>{formatPercent(delta.percent)}</small>
    </span>
  );
}

function MarketDeltaSnapshotValue({ value, marketValue }) {
  const delta = calculateRetailDelta(value, marketValue);
  return (
    <span className="iprice-history-delta-value">
      <span>{formatSignedMoney(delta.amount)}</span>
      <small>{formatPercent(delta.percent)}</small>
    </span>
  );
}


function getSuccessfulSnapshots(snapshots) {
  return (
    Array.isArray(snapshots)
      ? snapshots
      : []
  ).filter(
    (snapshot) => (
      snapshot.status === "success"
    )
  );
}


function getErrorMessage(error) {
  return (
    error?.response?.data?.detail
    || error?.response?.data?.message
    || error?.message
    || "Не удалось сравнить snapshot."
  );
}


function SnapshotOption({
  snapshot,
}) {
  return (
    <>
      {snapshot.display_version}
      {" · "}
      {snapshot.calculation_date}

      {snapshot.is_active
        ? " · активная"
        : snapshot.was_active
          ? " · была активна"
          : ""}
    </>
  );
}


function ChangeBadge({
  value,
}) {
  return (
    <span
      className={[
        "iprice-compare-change-badge",
        value
          ? (
              "iprice-compare-change-badge"
              + `--${value}`
            )
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {CHANGE_TYPE_LABELS[value]
        || value
        || "—"}
    </span>
  );
}


function StatusValue({
  value,
}) {
  return (
    <span
      className={[
        "iprice-compare-status",
        value
          ? `iprice-compare-status--${value}`
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {STATUS_LABELS[value]
        || value
        || "—"}
    </span>
  );
}


function SideValue({
  value,
  formatter = (
    currentValue
  ) => currentValue ?? "—",
  changed = false,
}) {
  return (
    <span
      className={
        changed
          ? "iprice-compare-value--changed"
          : ""
      }
    >
      {formatter(value)}
    </span>
  );
}


function ParameterPair({ base, comparison, formatter = formatPercent }) {
  return <>{formatter(base)} {" → "} {formatter(comparison)}</>;
}


function PriceTypePair({ base, comparison, field, productMode = false }) {
  const priceField = productMode ? `effective_${field}_median` : `effective_${field}`;
  const discountField = productMode ? `discount_${field}_median` : `discount_${field}`;
  return (
    <div className="iprice-parameter-value">
      <strong>
        {formatMoney(base[priceField])} {" → "} {formatMoney(comparison[priceField])}
      </strong>
      <span>
        {formatPercent(base[discountField])} {" → "} {formatPercent(comparison[discountField])}
      </span>
    </div>
  );
}


function ProductRowsTable({
  rows,
  showParameters,
  onOpenProduct,
  comparisonSnapshotId,
  baseSnapshotId,
}) {
  return (
    <div className="iprice-compare-table-wrapper">
      <table className="iprice-compare-table iprice-compare-table--products">
        <thead>
          <tr>
            <th className="iprice-compare-column-change iprice-sticky-column iprice-sticky-column--history-1">Изменение</th>
            <th className="iprice-column-image iprice-sticky-column iprice-sticky-column--history-2">Фото</th>
            <th className="iprice-column-code iprice-sticky-column iprice-sticky-column--history-3">Код 1С</th>
            <th className="iprice-compare-name iprice-sticky-column iprice-sticky-column--history-4">Номенклатура 1С</th>
            <th className="iprice-column-product-key">Ключ системы</th>
            <th className="iprice-column-iprice-type">Тип номенклатуры iPrice</th>
            <th className="iprice-column-method">Метод расчёта</th>
            {showParameters && (
              <>
                <th className="iprice-column-parameter iprice-parameter-boundary--start">Значение метода расчёта</th>
                <th className="iprice-column-parameter">Минимальная допустимая маржа</th>
                {PRICE_TYPE_COLUMNS.map(([, label], index) => (
                  <th key={label} className={`iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>{label}</th>
                ))}
              </>
            )}
            <th className="iprice-column-history-number-pair">Кол-во товаров-конкурентов</th>
            <th className="iprice-column-history-money-pair">Медиана розницы</th>
            <th className="iprice-column-history-money-pair">Медиана итоговой РРЦ</th>
            <th className="iprice-column-history-money-pair">Δ: розница − итоговая РРЦ</th>
            <th className="iprice-column-history-money-pair">Медиана рынка</th>
            <th className="iprice-column-history-money-pair">Δ: итоговая РРЦ − рынок</th>
            <th className="iprice-column-history-money-pair">Δ: розница − рынок</th>
            <th className="iprice-column-status">Статус</th>
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => {
            const base = row.base || {};
            const comparison = (
              row.comparison || {}
            );

            const current = (
              row.comparison
              || row.base
              || {}
            );

            const changedFields = (
              Array.isArray(
                row.changed_fields
              )
                ? row.changed_fields
                : []
            );

            return (
              <tr
                key={String(row.key)}
                className={
                  row.change_type
                    ? (
                        "iprice-compare-row"
                        + `--${row.change_type}`
                      )
                    : ""
                }
              >
                <td className="iprice-compare-column-change iprice-sticky-column iprice-sticky-column--history-1">
                  <ChangeBadge
                    value={row.change_type}
                  />
                </td>

                <td className="iprice-column-image iprice-sticky-column iprice-sticky-column--history-2">
                  <IPriceProductImage
                    src={current.image}
                    alt={current.nom}
                  />
                </td>

                <td className="iprice-column-code iprice-sticky-column iprice-sticky-column--history-3">
                  {current.code_1c ?? "—"}
                </td>

                <td className="iprice-compare-name iprice-sticky-column iprice-sticky-column--history-4">
                  <button
                    type="button"
                    className="iprice-product-name-link"
                    onClick={() => onOpenProduct?.(
                      {
                        ...current,
                        id: (
                          current.id
                          ?? current.snapshot_product_id
                        ),
                      },
                      row.comparison
                        ? comparisonSnapshotId
                        : baseSnapshotId,
                    )}
                  >
                    {current.nom || "—"}
                  </button>

                  <small>
                    {[
                      current.nom_category,
                      current.nom_group,
                    ]
                      .filter(Boolean)
                      .join(" / ")
                      || "—"}
                  </small>
                </td>

                <td className="iprice-column-product-key">
                  {current.base_product_key ?? "—"}
                </td>

                <td className="iprice-column-iprice-type">
                    {current.category || "—"}

                  <div className="iprice-row-secondary">
                    {[
                      current.subcategory,
                      current.subcategory_type,
                    ]
                      .filter(Boolean)
                      .join(" / ")
                      || "—"}
                  </div>
                </td>

                <td className="iprice-column-method">
                  <SideValue
                    value={base.pricing_method}
                    formatter={(value) => (
                      PRICING_METHOD_LABELS[value]
                      || value
                      || "—"
                    )}
                    changed={changedFields.includes(
                      "pricing_method"
                    )}
                  />
                  {" → "}
                  <SideValue
                    value={comparison.pricing_method}
                    formatter={(value) => (
                      PRICING_METHOD_LABELS[value]
                      || value
                      || "—"
                    )}
                    changed={changedFields.includes(
                      "pricing_method"
                    )}
                  />
                </td>

                {showParameters && (
                  <>
                    <td className="iprice-column-history-percent-pair iprice-column-parameter iprice-parameter-boundary--start">
                      <ParameterPair
                        base={base.pricing_method === "analog"
                          ? base.base_analog_median
                          : base.base_exclusive_median}
                        comparison={comparison.pricing_method === "analog"
                          ? comparison.base_analog_median
                          : comparison.base_exclusive_median}
                        formatter={(value) => (
                          (base.pricing_method === "analog"
                            && comparison.pricing_method === "analog")
                            ? formatNumber(value)
                            : formatPercent(value)
                        )}
                      />
                    </td>
                    <td className="iprice-column-history-percent-pair iprice-column-parameter">
                      <ParameterPair
                        base={base.minimum_margin_median}
                        comparison={comparison.minimum_margin_median}
                      />
                    </td>
                    {PRICE_TYPE_COLUMNS.map(([field], index) => (
                      <td key={field} className={`iprice-column-history-money-pair iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>
                        <PriceTypePair
                          base={base}
                          comparison={comparison}
                          field={field}
                          productMode
                        />
                      </td>
                    ))}
                  </>
                )}

                <td className="iprice-column-history-number-pair">
                  {formatNumber(
                    base.competitor_count,
                    0,
                  )}
                  {" → "}
                  {formatNumber(
                    comparison
                      .competitor_count,
                    0,
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  <SideValue
                    value={
                      base.current_retail_median
                    }
                    formatter={formatMoney}
                    changed={changedFields.includes(
                      "current_retail_median"
                    )}
                  />
                  {" → "}
                  <SideValue
                    value={
                      comparison
                        .current_retail_median
                    }
                    formatter={formatMoney}
                    changed={changedFields.includes(
                      "current_retail_median"
                    )}
                  />
                </td>

                <td className="iprice-column-history-money-pair">
                  <SideValue
                    value={
                      base.effective_approved_rrp_median
                    }
                    formatter={formatMoney}
                    changed={changedFields.includes(
                      "effective_approved_rrp_median"
                    )}
                  />
                  {" → "}
                  <SideValue
                    value={
                      comparison
                        .effective_approved_rrp_median
                    }
                    formatter={formatMoney}
                    changed={changedFields.includes(
                      "effective_approved_rrp_median"
                    )}
                  />
                </td>

                <td className="iprice-column-history-money-pair">
                  <DeltaSnapshotValue
                    retailValue={
                      base.current_retail_median
                    }
                    finalRrpValue={
                      base.effective_approved_rrp_median
                    }
                  />
                  {" → "}
                  <DeltaSnapshotValue
                    retailValue={
                      comparison.current_retail_median
                    }
                    finalRrpValue={
                      comparison.effective_approved_rrp_median
                    }
                  />
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base
                      .competitor_rrp_median
                  )}
                  {" → "}
                  {formatMoney(
                    comparison
                      .competitor_rrp_median
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  <MarketDeltaSnapshotValue value={base.effective_approved_rrp_median} marketValue={base.competitor_rrp_median} />
                  {" → "}
                  <MarketDeltaSnapshotValue value={comparison.effective_approved_rrp_median} marketValue={comparison.competitor_rrp_median} />
                </td>

                <td className="iprice-column-history-money-pair">
                  <MarketDeltaSnapshotValue value={base.current_retail_median} marketValue={base.competitor_rrp_median} />
                  {" → "}
                  <MarketDeltaSnapshotValue value={comparison.current_retail_median} marketValue={comparison.competitor_rrp_median} />
                </td>

                <td className="iprice-column-status">
                  <StatusValue
                    value={
                      base.calculation_status
                    }
                  />
                  {" → "}
                  <StatusValue
                    value={
                      comparison
                        .calculation_status
                    }
                  />
                </td>

              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


function RegionRowsTable({
  rows,
  showParameters,
  onOpenProduct,
  comparisonSnapshotId,
  baseSnapshotId,
}) {
  return (
    <div className="iprice-compare-table-wrapper">
      <table className="iprice-compare-table iprice-compare-table--regions">
        <thead>
          <tr>
            <th className="iprice-compare-column-change iprice-sticky-column iprice-sticky-column--history-1">Изменение</th>
            <th className="iprice-column-image iprice-sticky-column iprice-sticky-column--history-2">Фото</th>
            <th className="iprice-column-code iprice-sticky-column iprice-sticky-column--history-3">Код 1С</th>
            <th className="iprice-compare-name iprice-sticky-column iprice-sticky-column--history-4">Номенклатура 1С</th>
            <th className="iprice-column-product-key">Ключ системы</th>
            <th className="iprice-column-iprice-type">Тип номенклатуры iPrice</th>
            <th className="iprice-column-method">Метод расчёта</th>
            {showParameters && (
              <>
                <th className="iprice-column-parameter iprice-parameter-boundary--start">Значение метода расчёта</th>
                <th className="iprice-column-parameter">Минимальная допустимая маржа</th>
                {PRICE_TYPE_COLUMNS.map(([, label], index) => (
                  <th key={label} className={`iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>{label}</th>
                ))}
              </>
            )}
            <th className="iprice-column-region">Регион продажи</th>
            <th className="iprice-column-region">Место производства</th>
            <th className="iprice-column-history-money-pair">Себестоимость</th>
            <th className="iprice-column-history-money-pair">Логистика</th>
            <th className="iprice-column-history-money-pair">Розничная цена</th>
            <th className="iprice-column-history-money-pair">Итоговая РРЦ</th>
            <th className="iprice-column-history-money-pair">Δ: розница − итоговая РРЦ</th>
            <th className="iprice-column-history-money-pair">Медиана рынка</th>
            <th className="iprice-column-history-money-pair">Δ: итоговая РРЦ − рынок</th>
            <th className="iprice-column-history-money-pair">Δ: розница − рынок</th>
            <th className="iprice-column-history-percent-pair">Расчётная маржа</th>
            <th className="iprice-column-status">Статус</th>
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => {
            const base = row.base || {};
            const comparison = (
              row.comparison || {}
            );

            const current = (
              row.comparison
              || row.base
              || {}
            );

            return (
              <tr
                key={JSON.stringify(row.key)}
                className={
                  row.change_type
                    ? (
                        "iprice-compare-row"
                        + `--${row.change_type}`
                      )
                    : ""
                }
              >
                <td className="iprice-compare-column-change iprice-sticky-column iprice-sticky-column--history-1">
                  <ChangeBadge
                    value={row.change_type}
                  />
                </td>

                <td className="iprice-column-image iprice-sticky-column iprice-sticky-column--history-2">
                  <IPriceProductImage
                    src={current.image}
                    alt={current.nom}
                  />
                </td>

                <td className="iprice-column-code iprice-sticky-column iprice-sticky-column--history-3">
                  {current.code_1c ?? "—"}
                </td>

                <td className="iprice-compare-name iprice-sticky-column iprice-sticky-column--history-4">
                  <button
                    type="button"
                    className="iprice-product-name-link"
                    onClick={() => onOpenProduct?.(
                      {
                        ...current,
                        id: current.snapshot_product_id,
                      },
                      row.comparison
                        ? comparisonSnapshotId
                        : baseSnapshotId,
                    )}
                  >
                    {current.nom || "—"}
                  </button>

                  <small>
                    {[
                      current.nom_category,
                      current.nom_group,
                    ]
                      .filter(Boolean)
                      .join(" / ")
                      || "—"}
                  </small>
                </td>

                <td className="iprice-column-product-key">
                  {current.base_product_key ?? "—"}
                </td>

                <td className="iprice-column-iprice-type">
                    {current.category || "—"}

                  <div className="iprice-row-secondary">
                    {[
                      current.subcategory,
                      current.subcategory_type,
                    ]
                      .filter(Boolean)
                      .join(" / ")
                      || "—"}
                  </div>
                </td>

                <td className="iprice-column-method">
                  <SideValue
                    value={base.pricing_method}
                    formatter={(value) => (
                      PRICING_METHOD_LABELS[value]
                      || value
                      || "—"
                    )}
                    changed={row.changed_fields?.includes(
                      "pricing_method"
                    )}
                  />
                  {" → "}
                  <SideValue
                    value={comparison.pricing_method}
                    formatter={(value) => (
                      PRICING_METHOD_LABELS[value]
                      || value
                      || "—"
                    )}
                    changed={row.changed_fields?.includes(
                      "pricing_method"
                    )}
                  />
                </td>

                {showParameters && (
                  <>
                    <td className="iprice-column-history-percent-pair iprice-column-parameter iprice-parameter-boundary--start">
                      <ParameterPair
                        base={base.pricing_method === "analog" ? base.base_analog : base.base_exclusive}
                        comparison={comparison.pricing_method === "analog" ? comparison.base_analog : comparison.base_exclusive}
                        formatter={(value) => (
                          (base.pricing_method === "analog" && comparison.pricing_method === "analog")
                            ? formatNumber(value)
                            : formatPercent(value)
                        )}
                      />
                    </td>
                    <td className="iprice-column-history-percent-pair iprice-column-parameter">
                      <ParameterPair base={base.minimum_margin} comparison={comparison.minimum_margin} />
                    </td>
                    {PRICE_TYPE_COLUMNS.map(([field], index) => (
                      <td key={field} className={`iprice-column-history-money-pair iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>
                        <PriceTypePair base={base} comparison={comparison} field={field} />
                      </td>
                    ))}
                  </>
                )}

                <td className="iprice-column-region">
                  {current.sale_region || "—"}
                </td>

                <td className="iprice-column-region">
                  {current.departure || "—"}
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base.product_cost
                  )}
                  {" → "}
                  {formatMoney(
                    comparison.product_cost
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base.logistics_unit
                  )}
                  {" → "}
                  {formatMoney(
                    comparison.logistics_unit
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base.current_retail
                  )}
                  {" → "}
                  {formatMoney(
                    comparison.current_retail
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base.effective_approved_rrp
                  )}
                  {" → "}
                  {formatMoney(
                    comparison
                      .effective_approved_rrp
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  <DeltaSnapshotValue
                    retailValue={base.current_retail}
                    finalRrpValue={
                      base.effective_approved_rrp
                    }
                  />
                  {" → "}
                  <DeltaSnapshotValue
                    retailValue={
                      comparison.current_retail
                    }
                    finalRrpValue={
                      comparison.effective_approved_rrp
                    }
                  />
                </td>

                <td className="iprice-column-history-money-pair">
                  {formatMoney(
                    base
                      .regional_competitor_rrp_median
                  )}
                  {" → "}
                  {formatMoney(
                    comparison
                      .regional_competitor_rrp_median
                  )}
                </td>

                <td className="iprice-column-history-money-pair">
                  <MarketDeltaSnapshotValue value={base.effective_approved_rrp} marketValue={base.regional_competitor_rrp_median} />
                  {" → "}
                  <MarketDeltaSnapshotValue value={comparison.effective_approved_rrp} marketValue={comparison.regional_competitor_rrp_median} />
                </td>

                <td className="iprice-column-history-money-pair">
                  <MarketDeltaSnapshotValue value={base.current_retail} marketValue={base.regional_competitor_rrp_median} />
                  {" → "}
                  <MarketDeltaSnapshotValue value={comparison.current_retail} marketValue={comparison.regional_competitor_rrp_median} />
                </td>

                <td className="iprice-column-history-percent-pair">
                  {formatPercent(
                    calculateMargin(
                      base.effective_approved_rrp,
                      base.cost_with_logistics,
                    )
                  )}
                  {" → "}
                  {formatPercent(
                    calculateMargin(
                      comparison.effective_approved_rrp,
                      comparison.cost_with_logistics,
                    )
                  )}
                </td>

                <td className="iprice-column-status">
                  <StatusValue
                    value={
                      base.calculation_status
                    }
                  />
                  {" → "}
                  <StatusValue
                    value={
                      comparison
                        .calculation_status
                    }
                  />
                </td>

              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


export function IPriceSnapshotCompare({
  snapshots,
  selectedSnapshotId,
  loading = false,
  realtimeEvent,
  onOpenProduct,
}) {
  const successfulSnapshots = useMemo(
    () => getSuccessfulSnapshots(
      snapshots
    ),
    [snapshots],
  );

  const orderedSnapshots = useMemo(
    () => (
      [...successfulSnapshots]
        .sort((left, right) => (
          Number(right.version_number)
          - Number(left.version_number)
        ))
    ),
    [
      successfulSnapshots,
    ],
  );

  const defaultComparisonId = useMemo(
    () => (
      orderedSnapshots[0]?.id
      || null
    ),
    [
      orderedSnapshots,
    ],
  );

  const defaultBaseId = useMemo(
    () => (
      orderedSnapshots[1]?.id
      || null
    ),
    [
      orderedSnapshots,
    ],
  );

  const [
    baseSnapshotId,
    setBaseSnapshotId,
  ] = useState(defaultBaseId);

  const [
    comparisonSnapshotId,
    setComparisonSnapshotId,
  ] = useState(defaultComparisonId);

  const [
    mode,
    setMode,
  ] = useState(MODE_PRODUCTS);

  const [
    changeType,
    setChangeType,
  ] = useState("all");

  const [
    search,
    setSearch,
  ] = useState("");

  const [
    filters,
    setFilters,
  ] = useState({});

  const [
    filterOptions,
    setFilterOptions,
  ] = useState({});

  const [
    filtersLoading,
    setFiltersLoading,
  ] = useState(false);

  const [
    filtersError,
    setFiltersError,
  ] = useState("");

  const [
    page,
    setPage,
  ] = useState(1);

  const [
    pageSize,
    setPageSize,
  ] = useState(50);

  const [showParameters, setShowParameters] = useState(false);

  const [
    result,
    setResult,
  ] = useState(null);

  const [
    requestLoading,
    setRequestLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    comparisonStarted,
    setComparisonStarted,
  ] = useState(false);

  const filtersRequestIdRef = useRef(0);
  const comparisonRequestIdRef = useRef(0);
  const lastRealtimeEventRef = useRef(null);


  useEffect(() => {
    setComparisonSnapshotId(
      defaultComparisonId
    );

    setBaseSnapshotId(
      defaultBaseId
    );

    setFilters({});
    setFilterOptions({});
    setFiltersError("");

    setResult(null);
    setComparisonStarted(false);
    setPage(1);
  }, [
    defaultComparisonId,
    defaultBaseId,
  ]);


  const canCompare = Boolean(
    baseSnapshotId
    && comparisonSnapshotId
    && baseSnapshotId
      !== comparisonSnapshotId
  );


  const loadFilterOptions = useCallback(
    async ({
      nextFilters = {},
      nextMode = mode,
    } = {}) => {
      if (!canCompare) {
        setFilterOptions({});
        return;
      }

      const requestId = (
        filtersRequestIdRef.current + 1
      );

      filtersRequestIdRef.current = requestId;
      setFiltersLoading(true);
      setFiltersError("");

      try {
        const response = (
          await getIPriceSnapshotCompareFilters({
            baseSnapshotId,
            comparisonSnapshotId,
            mode: nextMode,
            filters: nextFilters,
          })
        );

        if (
          filtersRequestIdRef.current
          !== requestId
        ) {
          return;
        }

        setFilterOptions(
          response.options || {}
        );
        setFilters(
          response.selected || nextFilters
        );
      } catch (requestError) {
        if (
          filtersRequestIdRef.current
          !== requestId
        ) {
          return;
        }

        setFiltersError(
          getErrorMessage(requestError)
        );
      } finally {
        if (
          filtersRequestIdRef.current
          === requestId
        ) {
          setFiltersLoading(false);
        }
      }
    },
    [
      baseSnapshotId,
      comparisonSnapshotId,
      canCompare,
      mode,
    ],
  );


  useEffect(() => {
    if (!canCompare) {
      setFilters({});
      setFilterOptions({});
      setFiltersError("");
      return;
    }

    setFilters({});
    setFilterOptions({});
    setFiltersError("");

    loadFilterOptions({
      nextFilters: {},
      nextMode: mode,
    });
  }, [
    baseSnapshotId,
    comparisonSnapshotId,
    mode,
    canCompare,
    loadFilterOptions,
  ]);


  const loadComparison = useCallback(
    async ({
      nextPage = page,
      nextChangeType = changeType,
      nextSearch = search,
      nextMode = mode,
      nextPageSize = pageSize,
      nextFilters = filters,
    } = {}) => {
      if (!canCompare) {
        return;
      }

      const requestId = (
        comparisonRequestIdRef.current + 1
      );

      comparisonRequestIdRef.current = requestId;
      setRequestLoading(true);
      setError("");

      try {
        const response = (
          await compareIPriceSnapshots({
            baseSnapshotId,
            comparisonSnapshotId,
            mode: nextMode,
            changeType: nextChangeType,
            page: nextPage,
            pageSize: nextPageSize,
            search: nextSearch,
            filters: nextFilters,
          })
        );

        if (
          comparisonRequestIdRef.current
          !== requestId
        ) {
          return;
        }

        setResult(response);
        setPage(response.page);
        setComparisonStarted(true);
      } catch (requestError) {
        if (
          comparisonRequestIdRef.current
          !== requestId
        ) {
          return;
        }

        setError(
          getErrorMessage(requestError)
        );
      } finally {
        if (
          comparisonRequestIdRef.current
          === requestId
        ) {
          setRequestLoading(false);
        }
      }
    },
    [
      baseSnapshotId,
      comparisonSnapshotId,
      canCompare,
      mode,
      changeType,
      page,
      pageSize,
      search,
      filters,
    ],
  );

  useEffect(() => {
    if (!realtimeEvent) {
      return;
    }

    const eventType = String(
      realtimeEvent.change_type || ""
    );

    if (
      !HISTORY_REFRESH_EVENTS.has(
        eventType
      )
    ) {
      return;
    }

    const eventSnapshotId = Number(
      realtimeEvent.snapshot_id
    );

    const affectsBaseSnapshot = (
      eventSnapshotId
      === Number(baseSnapshotId)
    );

    const affectsComparisonSnapshot = (
      eventSnapshotId
      === Number(comparisonSnapshotId)
    );

    if (
      !affectsBaseSnapshot
      && !affectsComparisonSnapshot
    ) {
      return;
    }

    const eventKey = (
      realtimeEvent.receivedAt
      ?? realtimeEvent
    );

    if (
      lastRealtimeEventRef.current
      === eventKey
    ) {
      return;
    }

    lastRealtimeEventRef.current = eventKey;

    loadFilterOptions({
      nextFilters: filters,
      nextMode: mode,
    });

    loadComparison({
      nextPage: page,
      nextChangeType: changeType,
      nextSearch: search,
      nextMode: mode,
      nextPageSize: pageSize,
      nextFilters: filters,
    });
  }, [
    realtimeEvent,
    baseSnapshotId,
    comparisonSnapshotId,
    mode,
    changeType,
    page,
    pageSize,
    search,
    filters,
    loadFilterOptions,
    loadComparison,
  ]);


  useEffect(() => {
    if (loading || !canCompare) {
      return;
    }

    loadComparison({
      nextPage: 1,
      nextChangeType: "all",
      nextSearch: "",
      nextFilters: {},
    });
    // Version or mode changes start a fresh comparison.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    baseSnapshotId,
    comparisonSnapshotId,
    mode,
    loading,
    canCompare,
  ]);


  function handleModeChange(
    nextMode,
  ) {
    if (nextMode === mode) {
      return;
    }

    setMode(nextMode);
    setChangeType("all");
    setSearch("");
    setFilters({});
    setFilterOptions({});
    setFiltersError("");
    setPage(1);
    setResult(null);
    setComparisonStarted(false);
    setError("");
  }


  function handleFiltersChange(
    nextFilters,
  ) {
    const normalizedFilters = (
      nextFilters
      && typeof nextFilters === "object"
        ? nextFilters
        : {}
    );

    setFilters(normalizedFilters);
    setPage(1);

    loadFilterOptions({
      nextFilters: normalizedFilters,
    });

    if (comparisonStarted) {
      loadComparison({
        nextPage: 1,
        nextFilters: normalizedFilters,
      });
    }
  }


  function handleFiltersClear() {
    const nextFilters = {};

    setFilters(nextFilters);
    setPage(1);

    loadFilterOptions({
      nextFilters,
    });

    if (comparisonStarted) {
      loadComparison({
        nextPage: 1,
        nextFilters,
      });
    }
  }


  function handleChangeType(
    nextChangeType,
  ) {
    setChangeType(nextChangeType);
    setPage(1);

    if (comparisonStarted) {
      loadComparison({
        nextPage: 1,
        nextChangeType,
      });
    }
  }


  function handleSearchSubmit(event) {
    event.preventDefault();
    setPage(1);

    loadComparison({
      nextPage: 1,
    });
  }


  const summary = result?.summary || {
    total: 0,
    added: 0,
    removed: 0,
    changed: 0,
    unchanged: 0,
    priceIncreased: 0,
    priceDecreased: 0,
    finalRrpIncreased: 0,
    finalRrpDecreased: 0,
    statusChanged: 0,
    newErrors: 0,
    resolvedErrors: 0,
  };

  const rows = Array.isArray(
    result?.results
  )
    ? result.results
    : [];

  const changeTypeCounts = {
    all: summary.total,
    added: summary.added,
    removed: summary.removed,
    changed: summary.changed,
    unchanged: summary.unchanged,
    price_increased: summary.priceIncreased,
    price_decreased: summary.priceDecreased,
    final_rrp_increased: summary.finalRrpIncreased,
    final_rrp_decreased: summary.finalRrpDecreased,
    new_error: summary.newErrors,
    resolved_error: summary.resolvedErrors,
    status_changed: summary.statusChanged,
  };


  return (
    <section className="iprice-history-placeholder iprice-compare">
      <div className="iprice-calculation__top">
        <div
          className="iprice-mode-switch"
          role="group"
          aria-label="Режим сравнения"
        >
          <button
            type="button"
            className={
              mode === MODE_PRODUCTS
                ? "iprice-mode-switch__button iprice-mode-switch__button--active"
                : "iprice-mode-switch__button"
            }
            disabled={requestLoading}
            onClick={() => {
              handleModeChange(MODE_PRODUCTS);
            }}
          >
            По товарам
          </button>

          <button
            type="button"
            className={
              mode === MODE_REGIONS
                ? "iprice-mode-switch__button iprice-mode-switch__button--active"
                : "iprice-mode-switch__button"
            }
            disabled={requestLoading}
            onClick={() => {
              handleModeChange(MODE_REGIONS);
            }}
          >
            По регионам
          </button>
        </div>

        <form
          className="iprice-search"
          onSubmit={handleSearchSubmit}
        >
          <input
            type="search"
            value={search}
            disabled={requestLoading}
            placeholder={
              "Поиск по: код 1С, "
              + "номенклатура 1С"
            }
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />

          <button
            type="submit"
            disabled={requestLoading || !canCompare}
          >
            Найти
          </button>
        </form>
      </div>

      <div className="iprice-history-compare-controls">
        <label>
          <span>
            Базовая версия
          </span>

          <select
            value={baseSnapshotId || ""}
            disabled={
              loading
              || requestLoading
            }
            onChange={(event) => {
              setBaseSnapshotId(
                normalizeId(
                  event.target.value
                )
              );

              setFilters({});
              setFilterOptions({});
              setFiltersError("");
              setResult(null);
              setComparisonStarted(false);
            }}
          >
            {successfulSnapshots.map(
              (snapshot) => (
                <option
                  key={snapshot.id}
                  value={snapshot.id}
                  disabled={
                    snapshot.id
                    === comparisonSnapshotId
                  }
                >
                  <SnapshotOption
                    snapshot={snapshot}
                  />
                </option>
              )
            )}
          </select>
        </label>

        <div
          className="iprice-history-compare-arrow"
          aria-hidden="true"
        >
          →
        </div>

        <label>
          <span>
            Сравниваемая версия
          </span>

          <select
            value={
              comparisonSnapshotId || ""
            }
            disabled={
              loading
              || requestLoading
            }
            onChange={(event) => {
              setComparisonSnapshotId(
                normalizeId(
                  event.target.value
                )
              );

              setFilters({});
              setFilterOptions({});
              setFiltersError("");
              setResult(null);
              setComparisonStarted(false);
            }}
          >
            {successfulSnapshots.map(
              (snapshot) => (
                <option
                  key={snapshot.id}
                  value={snapshot.id}
                  disabled={
                    snapshot.id
                    === baseSnapshotId
                  }
                >
                  <SnapshotOption
                    snapshot={snapshot}
                  />
                </option>
              )
            )}
          </select>
        </label>

      </div>

      {canCompare && (
        <>
          {filtersError && (
            <div className="iprice-inline-error">
              <span>
                Не удалось загрузить фильтры:{" "}
                {filtersError}
              </span>

              <button
                type="button"
                onClick={() => {
                  loadFilterOptions({
                    nextFilters: filters,
                  });
                }}
              >
                Повторить
              </button>
            </div>
          )}

        </>
      )}

      {!canCompare && (
        <div className="iprice-history-placeholder__body">
          Выберите две разные успешные версии.
        </div>
      )}

      {error && (
        <div className="iprice-inline-error">
          <span>
            {error}
          </span>

          <button
            type="button"
            onClick={() => {
              loadComparison();
            }}
          >
            Повторить
          </button>
        </div>
      )}

      {canCompare && (
          <>
            <IPriceHistoryFilters
              mode={mode}
              options={filterOptions}
              selected={filters}
              loading={filtersLoading}
              onChange={handleFiltersChange}
              onClear={handleFiltersClear}
            />

            <div className="iprice-table-toolbar">
              <div className="iprice-table-toolbar__count">
                Найдено строк:{" "}
                <strong>
                  {formatNumber(
                    result?.filteredCount,
                    0,
                  )}
                </strong>
              </div>

              <div className="iprice-table-toolbar__controls">
                <button
                  type="button"
                  className="iprice-parameter-columns-toggle"
                  aria-expanded={showParameters}
                  onClick={() => setShowParameters((visible) => !visible)}
                >
                  <span>Параметры расчёта</span>
                  <span className={`iprice-parameter-columns-toggle__chevron ${showParameters ? "iprice-parameter-columns-toggle__chevron--expanded" : ""}`} aria-hidden="true" />
                </button>
                <label>
                  <span>Тип изменения</span>
                  <select
                    value={changeType}
                    disabled={requestLoading}
                    onChange={(event) => {
                      handleChangeType(
                        event.target.value
                      );
                    }}
                  >
                    {CHANGE_TYPE_OPTIONS.map((option) => (
                      <option
                        key={option.value}
                        value={option.value}
                      >
                        {option.labels?.[mode] || option.label}
                        {" ("}
                        {result
                          ? formatNumber(
                              changeTypeCounts[option.value] || 0,
                              0,
                            )
                          : "…"}
                        {")"}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>Строк на странице</span>
                  <select
                    value={pageSize}
                    disabled={requestLoading}
                    onChange={(event) => {
                      const nextPageSize = Number(
                        event.target.value
                      );

                      setPageSize(nextPageSize);
                      setPage(1);
                      loadComparison({
                        nextPage: 1,
                        nextPageSize,
                      });
                    }}
                  >
                    {[25, 50, 100, 200, 500].map(
                      (value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      )
                    )}
                  </select>
                </label>
              </div>
            </div>

            {requestLoading && (
              <div className="iprice-compare-table-wrapper">
                <div className="iprice-table-loading">
                  <div className="iprice-table-loading__spinner" />
                  <span>Загрузка данных...</span>
                </div>
              </div>
            )}

            {comparisonStarted && result && (
              <>

            {!requestLoading
              && rows.length === 0 && (
                <div className="iprice-history-empty">
                  Строки по выбранным условиям
                  не найдены.
                </div>
              )}

            {!requestLoading
              && rows.length > 0
              && (
                mode === MODE_PRODUCTS
                  ? (
                      <ProductRowsTable
                        rows={rows}
                        showParameters={showParameters}
                        onOpenProduct={onOpenProduct}
                        comparisonSnapshotId={comparisonSnapshotId}
                        baseSnapshotId={baseSnapshotId}
                      />
                    )
                  : (
                      <RegionRowsTable
                        rows={rows}
                        showParameters={showParameters}
                        onOpenProduct={onOpenProduct}
                        comparisonSnapshotId={comparisonSnapshotId}
                        baseSnapshotId={baseSnapshotId}
                      />
                    )
              )}

            <div className="iprice-pagination">
              <button
                type="button"
                disabled={
                  requestLoading
                  || !result.hasPrevious
                }
                onClick={() => {
                  loadComparison({
                    nextPage: page - 1,
                  });
                }}
              >
                Назад
              </button>

              <span>
                Страница{" "}
                <strong>
                  {result.page}
                </strong>
                {" из "}
                <strong>
                  {Math.max(
                    result.totalPages,
                    1,
                  )}
                </strong>
              </span>

              <button
                type="button"
                disabled={
                  requestLoading
                  || !result.hasNext
                }
                onClick={() => {
                  loadComparison({
                    nextPage: page + 1,
                  });
                }}
              >
                Далее
              </button>
            </div>
              </>
            )}
          </>
        )}
    </section>
  );
}
