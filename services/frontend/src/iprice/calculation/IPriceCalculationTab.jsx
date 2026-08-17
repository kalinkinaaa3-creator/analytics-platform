import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getIPriceSnapshotFilters,
  getIPriceSnapshotRows,
  changeIPriceSnapshotParameters,
  getIPriceAnalyticsSelection,
} from "../api/ipriceApi";

import {useSearchParams} from "react-router-dom";

import {
  IPriceDependentMultiSelect,
} from "../components/IPriceDependentMultiSelect";

import {
  IPriceProductImage,
} from "../components/IPriceProductImage";

import {
  IPRICE_PRODUCT_FILTERS,
  IPRICE_REGION_FILTERS,
} from "../filterDefinitions";


const MODE_PRODUCTS = "products";
const MODE_REGIONS = "regions";

const DEFAULT_PAGE_SIZE = 50;

const DEFAULT_PRODUCT_ORDERING = (
  "-current_vs_competitor_percent"
);

const DEFAULT_REGION_ORDERING = (
  "-current_vs_effective_approved_amount"
);

const PRICE_TYPE_COLUMNS = [
  ["distr", "Дистрибьютор"],
  ["distr_1", "Дистрибьютор 1"],
  ["small", "Малый опт"],
  ["medium", "Средний опт"],
  ["large", "Крупный опт"],
];

const PRICE_ZONE_LABELS = {
  below_market: "Ниже рынка",
  in_market: "В рынке",
  above_market: "Выше рынка",
  critical_above: "Критически выше",
  no_market_data: "Нет данных / Эксклюзивы",
};


function createEmptyRowsData() {
  return {
    count: 0,
    totalPages: 0,
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    hasNext: false,
    hasPrevious: false,
    results: [],
  };
}


function getDefaultOrdering(mode) {
  return (
    mode === MODE_REGIONS
      ? DEFAULT_REGION_ORDERING
      : DEFAULT_PRODUCT_ORDERING
  );
}


function getRequestErrorMessage(
  error,
  fallbackMessage,
) {
  return (
    error?.response?.data?.message
    || error?.response?.data?.detail
    || error?.message
    || fallbackMessage
  );
}


function normalizeFilters(filters) {
  const result = {};

  Object.entries(
    filters || {}
  ).forEach(([
    filterName,
    values,
  ]) => {
    if (
      Array.isArray(values)
      && values.length > 0
    ) {
      result[filterName] = values;
    }
  });

  return result;
}


function formatNumber(
  value,
  {
    maximumFractionDigits = 2,
    minimumFractionDigits = 0,
  } = {},
) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return String(value);
  }

  return number.toLocaleString(
    "ru-RU",
    {
      minimumFractionDigits,
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

  return `${formatNumber(
    value,
    {
      maximumFractionDigits: 2,
    },
  )} ₽`;
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


function formatPercent(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return String(value);
  }

  return `${formatNumber(
    number * 100,
    {
      maximumFractionDigits: 2,
    },
  )}%`;
}


function calculateDeltaPercent(
  amount,
  referenceValue,
) {
  const amountNumber = Number(amount);
  const referenceNumber = Number(referenceValue);

  if (
    amount === null
    || amount === undefined
    || amount === ""
    || referenceValue === null
    || referenceValue === undefined
    || referenceValue === ""
    || !Number.isFinite(amountNumber)
    || !Number.isFinite(referenceNumber)
    || referenceNumber === 0
  ) {
    return null;
  }

  return amountNumber / referenceNumber;
}

function calculatePriceDelta(value, referenceValue) {
  const valueNumber = Number(value);
  const referenceNumber = Number(referenceValue);
  if (
    value === null || value === undefined || value === ""
    || referenceValue === null || referenceValue === undefined || referenceValue === ""
    || !Number.isFinite(valueNumber) || !Number.isFinite(referenceNumber)
  ) {
    return {amount: null, percent: null};
  }
  const amount = valueNumber - referenceNumber;
  return {amount, percent: calculateDeltaPercent(amount, referenceNumber)};
}


function formatPricingMethod(value) {
  if (value === "analog") {
    return "Аналог";
  }

  if (value === "exclusive") {
    return "Эксклюзив";
  }

  return value || "—";
}


function getPricePositionClass(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return "";
  }

  if (number > 0) {
    return "iprice-price-position--above";
  }

  if (number < 0) {
    return "iprice-price-position--below";
  }

  return "iprice-price-position--equal";
}


function getApprovalDifference(
  row,
) {
  const calculatedRrp = Number(
    row.calculated_rrp
  );

  const effectiveRrp = Number(
    row.effective_approved_rrp
  );

  if (
    !Number.isFinite(calculatedRrp)
    || !Number.isFinite(effectiveRrp)
  ) {
    return null;
  }

  const amount = (
    effectiveRrp - calculatedRrp
  );

  return {
    amount,
    percent: calculatedRrp !== 0
      ? amount / calculatedRrp
      : null,
  };
}


function StatusBadge({
  value,
}) {
  const labels = {
    success: "Рассчитано",
    warning: "Предупреждение",
    error: "Ошибка",
  };

  return (
    <span
      className={[
        "iprice-row-status",
        value
          ? `iprice-row-status--${value}`
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {labels[value] || value || "—"}
    </span>
  );
}


function ErrorCounters({
  warningCodes,
  errorCodes,
}) {
  const warnings = Array.isArray(
    warningCodes
  )
    ? warningCodes.length
    : 0;

  const errors = Array.isArray(
    errorCodes
  )
    ? errorCodes.length
    : 0;

  if (
    warnings === 0
    && errors === 0
  ) {
    return null;
  }

  return (
    <div className="iprice-row-issues">
      {errors > 0 && (
        <span className="iprice-row-issues__error">
          Ошибок: {errors}
        </span>
      )}

      {warnings > 0 && (
        <span className="iprice-row-issues__warning">
          Предупреждений: {warnings}
        </span>
      )}
    </div>
  );
}


function ParameterValue({ value, percent = false }) {
  return percent ? formatPercent(value) : formatNumber(value);
}


function PriceTypeValue({ price, discount }) {
  return (
    <div className="iprice-parameter-value">
      <strong>{formatMoney(price)}</strong>
      <span>{formatPercent(discount)}</span>
    </div>
  );
}


function SortableColumn({ field, ordering, onSort, className = "", children }) {
  const active = ordering === field || ordering === `-${field}`;
  return (
    <th className={className}>
      <div className="iprice-analytics-sort-header">
        <button type="button" onClick={() => onSort(field)}>
          <span>{children}</span>
          <i className={active ? "is-active" : ""}>
            {ordering === field ? "↑" : "↓"}
          </i>
        </button>
      </div>
    </th>
  );
}


function ProductRowsTable({
  rows,
  onOpenProduct,
  showParameters,
  ordering,
  onSort,
}) {
  return (
    <table className="iprice-rows-table iprice-rows-table--products">
      <thead>
        <tr>
          <th className="iprice-column-image iprice-sticky-column iprice-sticky-column--calculation-1">
            Фото
          </th>

          <SortableColumn field="code_1c" ordering={ordering} onSort={onSort} className="iprice-column-code iprice-sticky-column iprice-sticky-column--calculation-2">Код 1С</SortableColumn>

          <SortableColumn field="nom" ordering={ordering} onSort={onSort} className="iprice-column-name iprice-sticky-column iprice-sticky-column--calculation-3">Номенклатура 1С</SortableColumn>

          <th className="iprice-column-product-key">
            Ключ системы
          </th>

          <th className="iprice-column-iprice-type">
            Тип номенклатуры iPrice
          </th>

          <SortableColumn field="pricing_method" ordering={ordering} onSort={onSort} className="iprice-column-method">Метод расчёта</SortableColumn>

          {showParameters && (
            <>
              <th className="iprice-column-parameter iprice-parameter-boundary--start">Значение метода расчёта</th>
              <th className="iprice-column-parameter">Минимальная допустимая маржа</th>
              {PRICE_TYPE_COLUMNS.map(([, label], index) => (
                <th key={label} className={`iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>{label}</th>
              ))}
            </>
          )}

          <SortableColumn field="competitor_count" ordering={ordering} onSort={onSort} className="iprice-column-number">Кол-во товаров-конкурентов</SortableColumn>

          <SortableColumn field="current_retail_median" ordering={ordering} onSort={onSort} className="iprice-column-money">Медиана розницы</SortableColumn>

          <SortableColumn field="effective_approved_rrp_median" ordering={ordering} onSort={onSort} className="iprice-column-money">Медиана итоговой РРЦ</SortableColumn>

          <SortableColumn field="current_vs_approved_amount" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: розница − итоговая РРЦ</SortableColumn>

          <SortableColumn field="competitor_rrp_median" ordering={ordering} onSort={onSort} className="iprice-column-money">Медиана рынка</SortableColumn>

          <SortableColumn field="approved_vs_competitor_percent" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: итоговая РРЦ − рынок</SortableColumn>
          <SortableColumn field="current_vs_competitor_percent" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: розница − рынок</SortableColumn>

          <SortableColumn field="calculation_status" ordering={ordering} onSort={onSort} className="iprice-column-status">Статус</SortableColumn>

        </tr>
      </thead>

      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            className="iprice-table-row"
          >
            <td className="iprice-column-image iprice-sticky-column iprice-sticky-column--calculation-1">
              <IPriceProductImage
                src={row.image}
                alt={row.nom}
              />
            </td>

            <td className="iprice-column-code iprice-sticky-column iprice-sticky-column--calculation-2">
              {row.code_1c ?? "—"}
            </td>

            <td className="iprice-column-name iprice-sticky-column iprice-sticky-column--calculation-3">
              <button
                type="button"
                className="iprice-product-name-link"
                onClick={() => onOpenProduct?.(row)}
              >
                {row.nom || "—"}
              </button>

              {(row.nom_category || row.nom_group) && (
                <div className="iprice-row-secondary">
                  {[
                    row.nom_category,
                    row.nom_group,
                  ]
                    .filter(Boolean)
                    .join(" / ")}
                </div>
              )}
            </td>

            <td className="iprice-column-product-key">
              {row.base_product_key ?? "—"}
            </td>

            <td className="iprice-column-iprice-type">
              <div>
                {row.category || "—"}
              </div>

              <div className="iprice-row-secondary">
                {[
                  row.subcategory,
                  row.subcategory_type,
                ]
                  .filter(Boolean)
                  .join(" / ")
                  || "—"}
              </div>
            </td>

            <td className="iprice-column-method">
              {formatPricingMethod(
                row.pricing_method
              )}
            </td>

            {showParameters && (
              <>
                <td className="iprice-cell-percent iprice-column-parameter iprice-parameter-boundary--start">
                  <ParameterValue
                    value={row.pricing_method === "analog"
                      ? row.calculation_details?.base_analog_median
                      : row.calculation_details?.base_exclusive_median}
                    percent={row.pricing_method === "exclusive"}
                  />
                  <div className="iprice-row-secondary">
                    {row.pricing_method === "analog"
                      ? "К цене аналога"
                      : "Базовая маржа"}
                  </div>
                </td>
                <td className="iprice-cell-percent iprice-column-parameter">
                  <ParameterValue
                    value={row.calculation_details?.minimum_margin_median}
                    percent
                  />
                </td>
                {PRICE_TYPE_COLUMNS.map(([field], index) => (
                  <td key={field} className={`iprice-cell-money iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>
                    <PriceTypeValue
                      price={row.calculation_details?.[`effective_${field}_median`]}
                      discount={row.calculation_details?.[`discount_${field}_median`]}
                    />
                  </td>
                ))}
              </>
            )}

            <td className="iprice-cell-number">
              {row.competitor_count ?? 0}
            </td>

            <td className="iprice-cell-money">
              {formatMoney(
                row.current_retail_median
              )}
            </td>

            <td className="iprice-cell-money">
              {formatMoney(
                row.effective_approved_rrp_median
              )}
            </td>

            <td
              className={[
                "iprice-cell-money",
                getPricePositionClass(
                  row.current_vs_approved_amount
                ),
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {formatSignedMoney(
                row.current_vs_approved_amount
              )}

              <div className="iprice-row-secondary">
                {formatPercent(
                  calculateDeltaPercent(
                    row.current_vs_approved_amount,
                    row.effective_approved_rrp_median,
                  )
                )}
              </div>
            </td>

            <td className="iprice-cell-money">
              {formatMoney(
                row.competitor_rrp_median
              )}
            </td>

            <td className="iprice-cell-money">
              {formatSignedMoney(
                calculatePriceDelta(row.effective_approved_rrp_median, row.competitor_rrp_median).amount
              )}
              <div className="iprice-row-secondary">{formatPercent(calculatePriceDelta(row.effective_approved_rrp_median, row.competitor_rrp_median).percent)}</div>
            </td>

            <td className="iprice-cell-money">
              {formatSignedMoney(row.current_vs_competitor_amount)}
              <div className="iprice-row-secondary">{formatPercent(row.current_vs_competitor_percent)}</div>
            </td>

            <td className="iprice-column-status">
              <StatusBadge
                value={
                  row.calculation_status
                }
              />

              <ErrorCounters
                warningCodes={
                  row.warning_codes
                }
                errorCodes={
                  row.error_codes
                }
              />
            </td>

          </tr>
        ))}
      </tbody>
    </table>
  );
}


function RegionRowsTable({
  rows,
  onOpenProduct,
  showParameters,
  ordering,
  onSort,
}) {
  return (
    <table className="iprice-rows-table iprice-rows-table--regions">
      <thead>
        <tr>
          <th className="iprice-column-image iprice-sticky-column iprice-sticky-column--calculation-1">
            Фото
          </th>

          <SortableColumn field="snapshot_product__code_1c" ordering={ordering} onSort={onSort} className="iprice-column-code iprice-sticky-column iprice-sticky-column--calculation-2">Код 1С</SortableColumn>

          <SortableColumn field="snapshot_product__nom" ordering={ordering} onSort={onSort} className="iprice-column-name iprice-sticky-column iprice-sticky-column--calculation-3">Номенклатура 1С</SortableColumn>

          <th className="iprice-column-product-key">
            Ключ системы
          </th>

          <th className="iprice-column-iprice-type">
            Тип номенклатуры iPrice
          </th>

          <SortableColumn field="snapshot_product__pricing_method" ordering={ordering} onSort={onSort} className="iprice-column-method">Метод расчёта</SortableColumn>

          {showParameters && (
            <>
              <th className="iprice-column-parameter iprice-parameter-boundary--start">Значение метода расчёта</th>
              <th className="iprice-column-parameter">Минимальная допустимая маржа</th>
              {PRICE_TYPE_COLUMNS.map(([, label], index) => (
                <th key={label} className={`iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>{label}</th>
              ))}
            </>
          )}

          <SortableColumn field="sale_region" ordering={ordering} onSort={onSort} className="iprice-column-region">Регион продажи</SortableColumn>
          <SortableColumn field="departure" ordering={ordering} onSort={onSort} className="iprice-column-region">Место производства</SortableColumn>

          <SortableColumn field="product_cost" ordering={ordering} onSort={onSort} className="iprice-column-money">Себестоимость</SortableColumn>

          <SortableColumn field="logistics_unit" ordering={ordering} onSort={onSort} className="iprice-column-money">Логистика</SortableColumn>

          <SortableColumn field="current_retail" ordering={ordering} onSort={onSort} className="iprice-column-money">Розничная цена</SortableColumn>

          <SortableColumn field="effective_approved_rrp" ordering={ordering} onSort={onSort} className="iprice-column-money">Итоговая РРЦ</SortableColumn>

          <SortableColumn field="current_vs_effective_approved_amount" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: розница − итоговая РРЦ</SortableColumn>

          <SortableColumn field="regional_competitor_rrp_median" ordering={ordering} onSort={onSort} className="iprice-column-money">Медиана рынка</SortableColumn>

          <SortableColumn field="effective_vs_competitor_percent" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: итоговая РРЦ − рынок</SortableColumn>
          <SortableColumn field="current_vs_competitor_percent" ordering={ordering} onSort={onSort} className="iprice-column-money">Δ: розница − рынок</SortableColumn>

          <SortableColumn field="effective_margin_calculated" ordering={ordering} onSort={onSort} className="iprice-column-percent">Расчётная маржа</SortableColumn>

          <SortableColumn field="calculation_status" ordering={ordering} onSort={onSort} className="iprice-column-status">Статус</SortableColumn>

        </tr>
      </thead>

      <tbody>
        {rows.map((row) => {
          const approvalDifference = (
            getApprovalDifference(row)
          );

          return (
            <tr
              key={row.id}
              className={[
                "iprice-table-row",
                row.current_approval
                  ? "iprice-product-region--approved"
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <td className="iprice-column-image iprice-sticky-column iprice-sticky-column--calculation-1">
                <IPriceProductImage
                  src={row.image}
                  alt={row.nom}
                />
              </td>

              <td className="iprice-column-code iprice-sticky-column iprice-sticky-column--calculation-2">
                {row.code_1c ?? "—"}
              </td>

              <td className="iprice-column-name iprice-sticky-column iprice-sticky-column--calculation-3">
                <button
                  type="button"
                  className="iprice-product-name-link"
                  onClick={() => {
                    onOpenProduct?.({
                      id: row.snapshot_product,
                      base_product_key: row.base_product_key,
                      code_1c: row.code_1c,
                      nom: row.nom,
                    });
                  }}
                >
                  {row.nom || "—"}
                </button>

                {(row.nom_category || row.nom_group) && (
                  <div className="iprice-row-secondary">
                    {[
                      row.nom_category,
                      row.nom_group,
                    ]
                      .filter(Boolean)
                      .join(" / ")}
                  </div>
                )}
              </td>

              <td className="iprice-column-product-key">
                {row.base_product_key ?? "—"}
              </td>

              <td className="iprice-column-iprice-type">
                <div>
                  {row.category || "—"}
                </div>

                <div className="iprice-row-secondary">
                  {[
                    row.subcategory,
                    row.subcategory_type,
                  ]
                    .filter(Boolean)
                    .join(" / ")
                    || "—"}
                </div>
              </td>

              <td className="iprice-column-method">
                {formatPricingMethod(
                  row.pricing_method
                )}
              </td>

              {showParameters && (
                <>
                  <td className="iprice-cell-percent iprice-column-parameter iprice-parameter-boundary--start">
                    <ParameterValue
                      value={row.pricing_method === "analog"
                        ? row.base_analog
                        : row.base_exclusive}
                      percent={row.pricing_method === "exclusive"}
                    />
                    <div className="iprice-row-secondary">
                      {row.pricing_method === "analog"
                        ? "К цене аналога"
                        : "Базовая маржа"}
                    </div>
                  </td>
                  <td className="iprice-cell-percent iprice-column-parameter">
                    <ParameterValue value={row.minimum_margin} percent />
                  </td>
                  {PRICE_TYPE_COLUMNS.map(([field], index) => (
                    <td key={field} className={`iprice-cell-money iprice-column-derived ${index === 0 ? "iprice-discount-boundary--start" : ""} ${index === PRICE_TYPE_COLUMNS.length - 1 ? "iprice-parameter-boundary--end" : ""}`}>
                      <PriceTypeValue
                        price={row[`effective_${field}`] ?? row[`calculated_${field}`]}
                        discount={row[`discount_${field}`]}
                      />
                    </td>
                  ))}
                </>
              )}

              <td className="iprice-column-region">
                {row.sale_region || "—"}
              </td>
              <td className="iprice-column-region">
                {row.departure || "—"}
              </td>

              <td className="iprice-cell-money">
                {formatMoney(row.product_cost)}
              </td>

              <td className="iprice-cell-money">
                {formatMoney(row.logistics_unit)}
              </td>

              <td className="iprice-cell-money">
                {formatMoney(row.current_retail)}
              </td>

              <td className="iprice-cell-money">
                <strong>
                  {formatMoney(
                    row.effective_approved_rrp
                    ?? row.default_approved_rrp
                    ?? row.calculated_rrp
                  )}
                </strong>

                {row.current_approval && (
                  <>
                    <div className="iprice-row-secondary">
                      Ручная, rev. {row.current_approval.revision}
                    </div>

                    {approvalDifference && (
                      <div
                        className={[
                          "iprice-approval-difference",
                          approvalDifference.amount > 0
                            ? "iprice-approval-difference--up"
                            : (
                                approvalDifference.amount < 0
                                  ? "iprice-approval-difference--down"
                                  : ""
                              ),
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        {approvalDifference.amount > 0 ? "+" : ""}
                        {formatMoney(approvalDifference.amount)}
                        {" / "}
                        {approvalDifference.percent !== null
                          ? (
                              `${approvalDifference.percent > 0 ? "+" : ""}`
                              + formatPercent(approvalDifference.percent)
                            )
                          : "—"}
                      </div>
                    )}
                  </>
                )}
              </td>

              <td
                className={[
                  "iprice-cell-money",
                  getPricePositionClass(
                    row.current_vs_effective_approved_amount
                  ),
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {formatSignedMoney(
                  row.current_vs_effective_approved_amount
                )}

                <div className="iprice-row-secondary">
                  {formatPercent(
                    row.current_vs_effective_approved_percent
                  )}
                </div>
              </td>

              <td className="iprice-cell-money">
                {formatMoney(
                  row.regional_competitor_rrp_median
                )}
              </td>

              <td className="iprice-cell-money">
                {formatSignedMoney(calculatePriceDelta(row.effective_approved_rrp, row.regional_competitor_rrp_median).amount)}
                <div className="iprice-row-secondary">{formatPercent(calculatePriceDelta(row.effective_approved_rrp, row.regional_competitor_rrp_median).percent)}</div>
              </td>

              <td className="iprice-cell-money">
                {formatSignedMoney(calculatePriceDelta(row.current_retail, row.regional_competitor_rrp_median).amount)}
                <div className="iprice-row-secondary">{formatPercent(calculatePriceDelta(row.current_retail, row.regional_competitor_rrp_median).percent)}</div>
              </td>

              <td className="iprice-cell-percent">
                {formatPercent(
                  row.effective_margin_calculated
                )}
              </td>

              <td className="iprice-column-status">
                <StatusBadge
                  value={row.calculation_status}
                />

                <ErrorCounters
                  warningCodes={row.warning_codes}
                  errorCodes={row.error_codes}
                />
              </td>

            </tr>
          );
        })}
      </tbody>
    </table>
  );
}


export function IPriceCalculationTab({
  snapshot,
  onOpenProduct,
  regionApprovalEvent,
  realtimeEvent,
  canEdit = false,
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const rowsRequestIdRef = useRef(0);
  const filtersRequestIdRef = useRef(0);

  const [
    mode,
    setMode,
  ] = useState(MODE_PRODUCTS);

  const [
    filtersExpanded,
    setFiltersExpanded,
  ] = useState(true);

  const [
    filters,
    setFilters,
  ] = useState({});

  const [
    filterOptions,
    setFilterOptions,
  ] = useState({});

  const [
    searchInput,
    setSearchInput,
  ] = useState("");

  const [
    appliedSearch,
    setAppliedSearch,
  ] = useState("");

  const [
    ordering,
    setOrdering,
  ] = useState(
    DEFAULT_PRODUCT_ORDERING
  );

  const [
    page,
    setPage,
  ] = useState(1);

  const [
    pageSize,
    setPageSize,
  ] = useState(
    DEFAULT_PAGE_SIZE
  );

  const [
    rowsData,
    setRowsData,
  ] = useState(
    createEmptyRowsData
  );

  const [
    loadingRows,
    setLoadingRows,
  ] = useState(false);

  const [
    loadingFilters,
    setLoadingFilters,
  ] = useState(false);

  const [
    rowsError,
    setRowsError,
  ] = useState("");

  const [
    filtersError,
    setFiltersError,
  ] = useState("");

  const [showParameters, setShowParameters] = useState(false);
  const [pricingSettingsExpanded, setPricingSettingsExpanded] = useState(false);
  const [editCoefficients, setEditCoefficients] = useState(false);
  const [editDiscounts, setEditDiscounts] = useState(false);
  const [parameterValues, setParameterValues] = useState({});
  const [parameterPreview, setParameterPreview] = useState(null);
  const [parameterLoading, setParameterLoading] = useState(false);
  const [parameterMessage, setParameterMessage] = useState("");
  const [parameterScope, setParameterScope] = useState(null);
  const [transferredSelection, setTransferredSelection] = useState(null);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState("");


  const filterConfig = useMemo(
    () => (
      mode === MODE_REGIONS
        ? IPRICE_REGION_FILTERS
        : IPRICE_PRODUCT_FILTERS
    ),
    [mode],
  );


  const toggleOrdering = useCallback((field) => {
    setOrdering((current) => current === field ? `-${field}` : field);
    setPage(1);
  }, [setOrdering]);


  const cleanFilters = useMemo(
    () => normalizeFilters(filters),
    [filters],
  );

  const requestFilters = useMemo(() => {
    if (!transferredSelection?.product_keys?.length) return cleanFilters;
    return {
      ...cleanFilters,
      base_product_key: transferredSelection.product_keys.map(String),
    };
  }, [cleanFilters, transferredSelection]);


  const selectedFiltersCount = (
    Object.keys(cleanFilters).length
    + (transferredSelection ? 1 : 0)
  );


  const snapshotReady = Boolean(
    snapshot?.id
    && snapshot.status === "success"
  );

  const parametersEditable = Boolean(
    canEdit
    && snapshotReady
    && snapshot.is_latest
    && !snapshot.is_active
  );

  const parameterUnavailableMessage = !canEdit
    ? "Недостаточно прав для изменения настроек ценообразования"
    : snapshot?.is_active
      ? "Настройки ценообразования недоступны: версия активирована"
      : "Редактирование доступно только в последней успешной версии";


  const loadRows = useCallback(
    async () => {
      if (!snapshotReady) {
        rowsRequestIdRef.current += 1;

        setRowsData(
          createEmptyRowsData()
        );

        setLoadingRows(false);
        setRowsError("");

        return;
      }

      const requestId = (
        rowsRequestIdRef.current + 1
      );

      rowsRequestIdRef.current = (
        requestId
      );

      setLoadingRows(true);
      setRowsError("");

      try {
        const result = (
          await getIPriceSnapshotRows(
            snapshot.id,
            {
              mode,
              page,
              pageSize,
              ordering,
              search: appliedSearch,
              filters: requestFilters,
            },
          )
        );

        if (
          requestId
          !== rowsRequestIdRef.current
        ) {
          return;
        }

        setRowsData(result);
      } catch (error) {
        if (
          requestId
          !== rowsRequestIdRef.current
        ) {
          return;
        }

        setRowsError(
          getRequestErrorMessage(
            error,
            (
              "Не удалось загрузить "
              + "строки расчёта."
            ),
          )
        );
      } finally {
        if (
          requestId
          === rowsRequestIdRef.current
        ) {
          setLoadingRows(false);
        }
      }
    },
    [
      snapshotReady,
      snapshot?.id,
      mode,
      page,
      pageSize,
      ordering,
      appliedSearch,
      requestFilters,
    ],
  );


  const loadFilters = useCallback(
    async () => {
      if (!snapshotReady) {
        filtersRequestIdRef.current += 1;

        setFilterOptions({});
        setLoadingFilters(false);
        setFiltersError("");

        return;
      }

      const requestId = (
        filtersRequestIdRef.current + 1
      );

      filtersRequestIdRef.current = (
        requestId
      );

      setLoadingFilters(true);
      setFiltersError("");

      try {
        const result = (
          await getIPriceSnapshotFilters(
            snapshot.id,
            {
              mode,
              filters: requestFilters,
            },
          )
        );

        if (
          requestId
          !== filtersRequestIdRef.current
        ) {
          return;
        }

        setFilterOptions(
          result.options || {}
        );
      } catch (error) {
        if (
          requestId
          !== filtersRequestIdRef.current
        ) {
          return;
        }

        setFiltersError(
          getRequestErrorMessage(
            error,
            (
              "Не удалось загрузить "
              + "зависимые фильтры."
            ),
          )
        );
      } finally {
        if (
          requestId
          === filtersRequestIdRef.current
        ) {
          setLoadingFilters(false);
        }
      }
    },
    [
      snapshotReady,
      snapshot?.id,
      mode,
      requestFilters,
    ],
  );


  useEffect(() => {
    if (
      !regionApprovalEvent
      || regionApprovalEvent.snapshotId
        !== snapshot?.id
    ) {
      return;
    }

    const {
      regionId,
      approval,
    } = regionApprovalEvent;

    if (
      !regionId
      || !approval
    ) {
      return;
    }

    setRowsData((previous) => ({
      ...previous,
      results: previous.results.map(
        (row) => {
          if (row.id !== regionId) {
            return row;
          }

          const approvedRrp = Number(
            approval.approved_rrp
          );
          const currentRetail = Number(
            row.current_retail
          );
          const costWithLogistics = Number(
            row.cost_with_logistics
          );
          const hasApprovedRrp = (
            approval.approved_rrp !== null
            && approval.approved_rrp !== undefined
            && approval.approved_rrp !== ""
            && Number.isFinite(approvedRrp)
            && approvedRrp !== 0
          );
          const hasCurrentRetail = (
            row.current_retail !== null
            && row.current_retail !== undefined
            && row.current_retail !== ""
            && Number.isFinite(currentRetail)
          );
          const hasCostWithLogistics = (
            row.cost_with_logistics !== null
            && row.cost_with_logistics !== undefined
            && row.cost_with_logistics !== ""
            && Number.isFinite(costWithLogistics)
          );

          return {
            ...row,
            current_approval: approval,
            effective_approved_rrp: (
              approval.approved_rrp
            ),
            effective_distr: (
              approval.approved_distr
            ),
            effective_distr_1: (
              approval.approved_distr_1
            ),
            effective_small: (
              approval.approved_small
            ),
            effective_medium: (
              approval.approved_medium
            ),
            effective_large: (
              approval.approved_large
            ),
            current_vs_effective_approved_amount: (
              hasApprovedRrp && hasCurrentRetail
                ? currentRetail - approvedRrp
                : null
            ),
            current_vs_effective_approved_percent: (
              hasApprovedRrp && hasCurrentRetail
                ? (
                    currentRetail - approvedRrp
                  ) / approvedRrp
                : null
            ),
            effective_margin_calculated: (
              hasApprovedRrp
              && hasCostWithLogistics
                ? (
                    approvedRrp
                    - costWithLogistics
                  ) / approvedRrp
                : null
            ),
          };
        }
      ),
    }));
  }, [
    regionApprovalEvent,
    snapshot?.id,
  ]);


  /*
   * При смене snapshot полностью сбрасываем
   * состояние расчётной вкладки.
   */
  useEffect(() => {
    rowsRequestIdRef.current += 1;
    filtersRequestIdRef.current += 1;

    setMode(MODE_PRODUCTS);
    setFilters({});
    setFilterOptions({});

    setSearchInput("");
    setAppliedSearch("");

    setOrdering(
      DEFAULT_PRODUCT_ORDERING
    );

    setPage(1);
    setPageSize(
      DEFAULT_PAGE_SIZE
    );

    setRowsData(
      createEmptyRowsData()
    );

    setRowsError("");
    setFiltersError("");
  }, [
    snapshot?.id,
  ]);


  useEffect(() => {
    let cancelled = false;
    const token = searchParams.get("c_selection");
    const productKey = searchParams.get("c_product_key");
    setSelectionError("");

    if (productKey) {
      setTransferredSelection(null);
      setFilters({base_product_key: [String(productKey)]});
      setMode(MODE_PRODUCTS);
      setPricingSettingsExpanded(parametersEditable);
      return () => { cancelled = true; };
    }
    if (!token) {
      setTransferredSelection(null);
      return () => { cancelled = true; };
    }

    setSelectionLoading(true);
    getIPriceAnalyticsSelection(token).then((result) => {
      if (cancelled) return;
      if (Number(result.snapshot_id) !== Number(snapshot?.id)) {
        throw new Error("Выборка относится к другой версии расчёта.");
      }
      const context = result.context || {};
      const nextFilters = {...(context.filters || {})};
      Object.entries(context.drill_path || {}).forEach(([name, value]) => {
        nextFilters[name] = [value];
      });
      setTransferredSelection(result);
      setFilters(nextFilters);
      setMode(context.mode === MODE_REGIONS ? MODE_REGIONS : MODE_PRODUCTS);
      setSearchInput(context.search || "");
      setAppliedSearch(context.search || "");
      setPricingSettingsExpanded(parametersEditable);
      setPage(1);
    }).catch((error) => {
      if (!cancelled) {
        setTransferredSelection(null);
        setSelectionError(getRequestErrorMessage(
          error,
          "Не удалось восстановить выборку аналитики.",
        ));
      }
    }).finally(() => {
      if (!cancelled) setSelectionLoading(false);
    });
    return () => { cancelled = true; };
  }, [snapshot?.id, parametersEditable, searchParams]);


  useEffect(() => {
    loadRows();
  }, [loadRows]);


  useEffect(() => {
    loadFilters();
  }, [loadFilters]);


  useEffect(() => {
    if (parametersEditable) {
      return;
    }
    setPricingSettingsExpanded(false);
    setEditCoefficients(false);
    setEditDiscounts(false);
    setParameterValues({});
    setParameterPreview(null);
    setParameterMessage("");
    setParameterScope(null);
  }, [parametersEditable]);


  useEffect(() => {
    let cancelled = false;
    if (
      !parametersEditable
      || !snapshot?.id
      || (selectedFiltersCount === 0 && !appliedSearch)
    ) {
      setParameterScope(null);
      return () => {
        cancelled = true;
      };
    }
    changeIPriceSnapshotParameters(snapshot.id, {
      mode,
      filters: requestFilters,
      search: appliedSearch,
      preview: true,
    }).then((result) => {
      if (!cancelled) {
        setParameterScope(result.affected || null);
      }
    }).catch(() => {
      if (!cancelled) {
        setParameterScope(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [
    parametersEditable,
    snapshot?.id,
    mode,
    requestFilters,
    appliedSearch,
    selectedFiltersCount,
  ]);


  useEffect(() => {
    if (
      !realtimeEvent
      || realtimeEvent.snapshot_id !== snapshot?.id
    ) {
      return;
    }

    if (
      realtimeEvent.change_type === "approval_saved"
      || realtimeEvent.change_type === "snapshot_finished"
      || realtimeEvent.change_type === "snapshot_activated"
      || realtimeEvent.change_type === "parameters_changed"
    ) {
      loadRows();
      loadFilters();
    }
  }, [
    realtimeEvent,
    snapshot?.id,
    loadRows,
    loadFilters,
  ]);


  function changeMode(nextMode) {
    if (
      nextMode !== MODE_PRODUCTS
      && nextMode !== MODE_REGIONS
    ) {
      return;
    }

    if (nextMode === mode) {
      return;
    }

    rowsRequestIdRef.current += 1;
    filtersRequestIdRef.current += 1;

    setMode(nextMode);
    setFilters({});
    setFilterOptions({});

    setSearchInput("");
    setAppliedSearch("");

    setOrdering(
      getDefaultOrdering(nextMode)
    );

    setPage(1);

    setRowsError("");
    setFiltersError("");
  }


  function changeFilter(
    filterName,
    values,
  ) {
    setFilters((previous) => {
      const nextFilters = {
        ...previous,
      };

      if (
        Array.isArray(values)
        && values.length > 0
      ) {
        nextFilters[filterName] = values;
      } else {
        delete nextFilters[
          filterName
        ];
      }

      return nextFilters;
    });

    setPage(1);
  }


  function applySearch() {
    setAppliedSearch(
      searchInput.trim()
    );

    setPage(1);
  }


  function clearAll() {
    rowsRequestIdRef.current += 1;
    filtersRequestIdRef.current += 1;

    setFilters({});
    setTransferredSelection(null);
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.delete("c_selection");
      next.delete("c_product_key");
      return next;
    }, {replace: true});
    setSearchInput("");
    setAppliedSearch("");
    setPage(1);

    setRowsError("");
    setFiltersError("");
  }


  function changeParameterValue(name, value, percent = false) {
    if (percent && value && !/^\d*(?:\.\d{0,2})?$/.test(value)) {
      return;
    }
    const numericValue = Number(value);
    if (value && Number.isFinite(numericValue)) {
      if (percent && numericValue > 99.99) {
        return;
      }
      if (name === "base_analog" && numericValue > 1) {
        return;
      }
    }
    setParameterValues((previous) => ({
      ...previous,
      [name]: value,
    }));
  }


  function buildParameterPayload(preview) {
    const coefficients = {};
    const discounts = {};
    if (editCoefficients) {
      ["base_analog", "base_exclusive", "minimum_margin"].forEach((name) => {
        if (parameterValues[name] !== "" && parameterValues[name] !== undefined) {
          coefficients[name] = name === "base_analog"
            ? parameterValues[name]
            : String(Number(parameterValues[name]) / 100);
        }
      });
    }
    if (editDiscounts) {
      PRICE_TYPE_COLUMNS.forEach(([name]) => {
        if (parameterValues[name] !== "" && parameterValues[name] !== undefined) {
          discounts[name] = String(Number(parameterValues[name]) / 100);
        }
      });
    }
    return {
      mode,
      filters: requestFilters,
      search: appliedSearch,
      coefficients,
      discounts,
      preview,
    };
  }


  async function previewParameterChanges() {
    setParameterMessage("");
    if (!editCoefficients && !editDiscounts) {
      setParameterMessage("Выберите хотя бы один раздел параметров.");
      return;
    }
    const analogValue = Number(parameterValues.base_analog);
    if (editCoefficients && parameterValues.base_analog
      && (analogValue < 0.1 || analogValue > 1)) {
      setParameterMessage("Коэффициент к цене аналога должен быть от 0,1 до 1.");
      return;
    }
    if (editCoefficients && parameterValues.base_exclusive) {
      const baseExclusive = Number(parameterValues.base_exclusive);
      if (baseExclusive < 1 || baseExclusive > 99.99) {
        setParameterMessage("Базовая маржа должна быть от 1% до 99,99%.");
        return;
      }
    }
    if (editCoefficients
      && parameterValues.minimum_margin !== ""
      && parameterValues.minimum_margin !== undefined) {
      const minimumMargin = Number(parameterValues.minimum_margin);
      if (minimumMargin < 0 || minimumMargin > 99.99) {
        setParameterMessage("Минимальная допустимая маржа должна быть от 0% до 99,99%.");
        return;
      }
    }
    const invalidDiscount = editDiscounts && PRICE_TYPE_COLUMNS.some(([name]) => {
      if (parameterValues[name] === "" || parameterValues[name] === undefined) {
        return false;
      }
      const value = Number(parameterValues[name]);
      return value < 0 || value > 99.99;
    });
    if (invalidDiscount) {
      setParameterMessage("Скидки должны быть от 0% до 99,99%.");
      return;
    }
    const payload = buildParameterPayload(true);
    if (Object.keys(payload.coefficients).length === 0
      && Object.keys(payload.discounts).length === 0) {
      setParameterMessage("Введите хотя бы одно новое значение.");
      return;
    }
    setParameterLoading(true);
    try {
      const result = await changeIPriceSnapshotParameters(snapshot.id, payload);
      setParameterPreview(result.affected || null);
    } catch (error) {
      setParameterMessage(getRequestErrorMessage(error, "Не удалось проверить изменения."));
    } finally {
      setParameterLoading(false);
    }
  }


  async function applyParameterChanges() {
    setParameterLoading(true);
    setParameterMessage("");
    try {
      const result = await changeIPriceSnapshotParameters(
        snapshot.id,
        buildParameterPayload(false),
      );
      setParameterPreview(null);
      setParameterValues({});
      setParameterMessage("");
      await Promise.all([loadRows(), loadFilters()]);
    } catch (error) {
      setParameterMessage(getRequestErrorMessage(error, "Не удалось применить изменения."));
    } finally {
      setParameterLoading(false);
    }
  }


  if (!snapshot) {
    return (
      <section className="iprice-tab-content">
        <h2>Расчёт цен</h2>

        <p>
          Версия расчёта не выбрана.
        </p>
      </section>
    );
  }


  if (snapshot.status === "building") {
    return (
      <section className="iprice-tab-content">
        <h2>Расчёт цен</h2>

        <p>
          Расчёт ещё выполняется. После завершения
          расчёта таблица станет доступна.
        </p>
      </section>
    );
  }


  if (snapshot.status === "failed") {
    return (
      <section className="iprice-tab-content">
        <h2>Расчёт цен</h2>

        <p>
          Расчёт завершён с ошибкой. Для просмотра
          таблицы выберите успешно рассчитанную версию.
        </p>
      </section>
    );
  }


  if (!snapshotReady) {
    return (
      <section className="iprice-tab-content">
        <h2>Расчёт цен</h2>

        <p>
          Таблица доступна только для успешно
          рассчитанного snapshot.
        </p>
      </section>
    );
  }


  return (
    <section className="iprice-calculation">
      <div className="iprice-calculation__top">
        <div
          className="iprice-mode-switch"
          role="group"
          aria-label="Режим таблицы iPrice"
        >
          <button
            type="button"
            className={
              mode === MODE_PRODUCTS
                ? "iprice-mode-switch__button iprice-mode-switch__button--active"
                : "iprice-mode-switch__button"
            }
            onClick={() => {
              changeMode(
                MODE_PRODUCTS
              );
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
            onClick={() => {
              changeMode(
                MODE_REGIONS
              );
            }}
          >
            По регионам
          </button>
        </div>

        <div className="iprice-search">
          <input
            type="search"
            value={searchInput}
            placeholder={
              "Поиск по: код 1С, "
              + "номенклатура 1С"
            }
            onChange={(event) => {
              setSearchInput(
                event.target.value
              );
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                applySearch();
              }
            }}
          />

          <button
            type="button"
            onClick={applySearch}
          >
            Найти
          </button>
        </div>
      </div>

      <div className="iprice-calculation-workspace">
      <div className="iprice-filters-panel">
        <div className="iprice-filters-panel__header">
          <button
            type="button"
            className="iprice-filters-toggle"
            aria-expanded={filtersExpanded}
            aria-label={
              filtersExpanded
                ? "Скрыть фильтры"
                : "Показать фильтры"
            }
            title={
              filtersExpanded
                ? "Скрыть фильтры"
                : "Показать фильтры"
            }
            onClick={() => {
              setFiltersExpanded((previous) => !previous);
            }}
          >
            <span
              className={[
                "iprice-filters-toggle__chevron",
                filtersExpanded
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
            <strong>
              {selectedFiltersCount}
            </strong>
          </div>
        </div>

        {filtersExpanded && filtersError && (
          <div className="iprice-inline-error">
            {filtersError}
          </div>
        )}

        {filtersExpanded && selectionError && (
          <div className="iprice-inline-error">{selectionError}</div>
        )}

        {filtersExpanded && (
        <div className="iprice-filters-grid">
          {filterConfig.map(([
            filterName,
            filterLabel,
          ]) => (
            <IPriceDependentMultiSelect
              key={filterName}
              name={filterName}
              label={filterLabel}
              options={
                filterOptions[
                  filterName
                ] || []
              }
              selected={
                filters[
                  filterName
                ] || []
              }
              disabled={!snapshotReady}
              loading={
                loadingFilters
                && !filterOptions[
                  filterName
                ]
              }
              onChange={
                changeFilter
              }
            />
          ))}
        </div>

        )}

        {filtersExpanded && (
          <div className="iprice-filters-actions">
            <button
              type="button"
              disabled={
                selectedFiltersCount === 0
                && !appliedSearch
                && !searchInput
              }
              onClick={clearAll}
            >
              Очистить фильтры
            </button>
          </div>
        )}
      </div>

      <section
          className={`iprice-filters-panel iprice-parameter-editor ${parametersEditable ? "" : "iprice-parameter-editor--disabled"}`}
          aria-disabled={!parametersEditable}
        >
          <div className="iprice-filters-panel__header iprice-parameter-editor__header">
            <h3>Настройки ценообразования</h3>
            <button
              type="button"
              className="iprice-filters-toggle"
              disabled={!parametersEditable}
              aria-expanded={parametersEditable && pricingSettingsExpanded}
              aria-label={parametersEditable && pricingSettingsExpanded ? "Скрыть настройки ценообразования" : "Показать настройки ценообразования"}
              title={parametersEditable ? (pricingSettingsExpanded ? "Скрыть настройки ценообразования" : "Показать настройки ценообразования") : parameterUnavailableMessage}
              onClick={() => setPricingSettingsExpanded((expanded) => !expanded)}
            >
              <span
                className={`iprice-filters-toggle__chevron ${pricingSettingsExpanded ? "iprice-filters-toggle__chevron--expanded" : ""}`}
                aria-hidden="true"
              />
            </button>
            {!parametersEditable && (
              <div className="iprice-filters-panel__summary">
                {parameterUnavailableMessage}
              </div>
            )}
          </div>

          {(transferredSelection || selectionLoading) && (
            <div className="iprice-transferred-selection">
              {selectionLoading ? (
                <strong>Восстанавливаем выборку из аналитики…</strong>
              ) : (
                <>
                  <strong>
                    Выборка из аналитики, количество товаров: {transferredSelection.product_count
                      ?? transferredSelection.product_keys?.length
                      ?? 0}
                  </strong>
                  {transferredSelection.context?.price_zones?.length > 0 && (
                    <span>
                      Распределение по ценовым зонам: {transferredSelection.context.price_zones
                        .map((zone) => PRICE_ZONE_LABELS[zone] || zone)
                        .join(", ")}
                    </span>
                  )}
                </>
              )}
            </div>
          )}

          {parametersEditable && pricingSettingsExpanded && <>
          <p className="iprice-parameter-editor__notice">
            Выберите хотя бы один фильтр. Изменения применятся ко всем отфильтрованным позициям.
          </p>
          <div className="iprice-parameter-editor__sections">
            <fieldset>
              <label className="iprice-parameter-editor__section-toggle">
                <input
                  type="checkbox"
                  checked={editCoefficients}
                  onChange={(event) => setEditCoefficients(event.target.checked)}
                />
                <span>Параметры расчёта</span>
              </label>
              <div className="iprice-parameter-editor__fields">
                {[
                  ["base_analog", "Коэффициент к цене аналога"],
                  ["base_exclusive", "Базовая маржа эксклюзива"],
                  ["minimum_margin", "Минимальная допустимая маржа"],
                ].map(([name, label]) => {
                  const method = name === "base_analog"
                    ? "analog"
                    : (name === "base_exclusive" ? "exclusive" : null);
                  const applicable = !method
                    || parameterScope?.pricing_methods?.includes(method);
                  return (
                  <label key={name}>
                    <span>{label}</span>
                    <input
                      type="number"
                      min={name === "base_analog" ? "0.1" : (name === "minimum_margin" ? "0" : "1")}
                      max={name === "base_analog" ? "1" : "99.99"}
                      step="0.01"
                      value={parameterValues[name] || ""}
                      disabled={!editCoefficients || parameterLoading || !applicable}
                      onChange={(event) => changeParameterValue(name, event.target.value, name !== "base_analog")}
                    />
                  </label>
                  );
                })}
              </div>
            </fieldset>

            <fieldset>
              <label className="iprice-parameter-editor__section-toggle">
                <input
                  type="checkbox"
                  checked={editDiscounts}
                  onChange={(event) => setEditDiscounts(event.target.checked)}
                />
                <span>Скидки по типам цен</span>
              </label>
              <div className="iprice-parameter-editor__fields iprice-parameter-editor__fields--discounts">
                {PRICE_TYPE_COLUMNS.map(([name, label]) => (
                  <label key={name}>
                    <span>{label}</span>
                    <input
                      type="number"
                      min="0"
                      max="99.99"
                      step="0.01"
                      value={parameterValues[name] || ""}
                      disabled={!editDiscounts || parameterLoading}
                      onChange={(event) => changeParameterValue(name, event.target.value, true)}
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          </div>

          <div className="iprice-filters-actions iprice-parameter-editor__actions">
            {parameterMessage && <span>{parameterMessage}</span>}
            <button
              type="button"
              disabled={
                parameterLoading
                || (selectedFiltersCount === 0 && !appliedSearch)
                || (!editCoefficients && !editDiscounts)
              }
              onClick={previewParameterChanges}
            >
              {parameterLoading ? "Проверка…" : "Применить изменения"}
            </button>
          </div>
          </>}
      </section>

      <div className="iprice-table-toolbar">
        <div className="iprice-table-toolbar__count">
          Найдено строк:{" "}
          <strong>
            {formatNumber(
              rowsData.count,
              {
                maximumFractionDigits: 0,
              },
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
            <span>
              Строк на странице
            </span>

            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(
                  Number(
                    event.target.value
                  )
                );

                setPage(1);
              }}
            >
              {
                [
                  25,
                  50,
                  100,
                  200,
                  500,
                ].map((value) => (
                  <option
                    key={value}
                    value={value}
                  >
                    {value}
                  </option>
                ))
              }
            </select>
          </label>

        </div>
      </div>

      {parameterPreview && (
        <div className="iprice-modal-overlay" role="presentation">
          <div className="iprice-modal iprice-parameter-confirmation" role="dialog" aria-modal="true">
            <h2>Применить параметры?</h2>
            <p>Будут пересчитаны все строки, соответствующие выбранным фильтрам.</p>
            <dl className="iprice-parameter-preview">
              <div><dt>Товаров</dt><dd>{parameterPreview.products}</dd></div>
              <div><dt>Региональных строк</dt><dd>{parameterPreview.regions}</dd></div>
              <div><dt>Комбинаций параметров</dt><dd>{parameterPreview.routes}</dd></div>
            </dl>
            <div className="iprice-modal-actions">
              <button
                type="button"
                disabled={parameterLoading}
                onClick={() => setParameterPreview(null)}
              >
                Отмена
              </button>
              <button
                type="button"
                disabled={parameterLoading}
                onClick={applyParameterChanges}
              >
                {parameterLoading ? "Применение…" : "Применить параметры"}
              </button>
            </div>
          </div>
        </div>
      )}

      {rowsError && (
        <div className="iprice-inline-error">
          {rowsError}

          <button
            type="button"
            onClick={loadRows}
          >
            Повторить
          </button>
        </div>
      )}

      <div
        className={[
          "iprice-table-wrapper",
          loadingRows
            ? "iprice-table-wrapper--loading"
            : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {!loadingRows
          && rowsData.results.length > 0 && (
          mode === MODE_PRODUCTS
            ? (
                <ProductRowsTable
                  rows={
                    rowsData.results
                  }
                  onOpenProduct={
                    onOpenProduct
                  }
                  showParameters={showParameters}
                  ordering={ordering}
                  onSort={toggleOrdering}
                />
              )
            : (
                <RegionRowsTable
                  rows={
                    rowsData.results
                  }
                  onOpenProduct={
                    onOpenProduct
                  }
                  showParameters={showParameters}
                  ordering={ordering}
                  onSort={toggleOrdering}
                />
              )
        )}

        {!loadingRows
          && rowsData.results.length === 0
          && !rowsError && (
            <div className="iprice-table-empty">
              По выбранным условиям строки
              не найдены.
            </div>
          )}

        {loadingRows && (
          <div className="iprice-table-loading">
            <div className="iprice-table-loading__spinner" />

            <span>
              Обновление строк...
            </span>
          </div>
        )}
      </div>

      <div className="iprice-pagination">
        <button
          type="button"
          disabled={
            !rowsData.hasPrevious
            || loadingRows
          }
          onClick={() => {
            setPage((previous) => (
              Math.max(
                1,
                previous - 1,
              )
            ));
          }}
        >
          Назад
        </button>

        <span>
          Страница{" "}
          <strong>
            {rowsData.page || page || 1}
          </strong>{" "}
          из{" "}
          <strong>
            {Math.max(
              rowsData.totalPages || 1,
              1,
            )}
          </strong>
        </span>

        <button
          type="button"
          disabled={
            !rowsData.hasNext
            || loadingRows
          }
          onClick={() => {
            setPage((previous) => (
              previous + 1
            ));
          }}
        >
          Далее
        </button>
      </div>
      </div>
    </section>
  );
}
