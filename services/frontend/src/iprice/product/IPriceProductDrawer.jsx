import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getIPriceMarketAssortment,
  getIPriceOwnAssortment,
  getIPriceSnapshotProductDetail,
  updateIPriceCompetitorSelection,
} from "../api/ipriceApi";

import {
  IPriceRegionCalculationDetails,
} from "./IPriceRegionCalculationDetails";

import {
  IPriceCompetitorCard,
} from "./IPriceCompetitorCard";
import {
  formatMatchPropertyValue,
  getIPriceCompetitorSourceLabel,
} from "./ipriceProductLabels";

import {
  IPriceProductImage,
} from "../components/IPriceProductImage";


const TAB_OVERVIEW = "overview";
const TAB_REGIONS = "regions";
const TAB_COMPETITORS = "competitors";
const TAB_MARKET = "market";
const TAB_OWN = "own";


const DRAWER_TABS = [
  {
    id: TAB_OVERVIEW,
    label: "Обзор",
  },
  {
    id: TAB_REGIONS,
    label: "Регионы",
  },
  {
    id: TAB_COMPETITORS,
    label: "Конкуренты",
  },
  {
    id: TAB_MARKET,
    label: "Рыночный ассортимент",
  },
  {
    id: TAB_OWN,
    label: "Собственный ассортимент",
  },
];


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

  if (Number.isNaN(number)) {
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


function formatWholeMoney(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }
  return `${formatNumber(value, 0)} ₽`;
}


function formatPercent(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—";
  }

  return `${formatNumber(
    Number(value) * 100,
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


function calculateMargin(price, cost) {
  const preparedPrice = Number(price);
  const preparedCost = Number(cost);

  if (
    !Number.isFinite(preparedPrice)
    || !Number.isFinite(preparedCost)
    || preparedPrice === 0
  ) {
    return null;
  }

  return (
    preparedPrice - preparedCost
  ) / preparedPrice;
}


function median(values) {
  const prepared = values
    .filter((value) => value !== null && value !== undefined && value !== "")
    .map(Number)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);

  if (!prepared.length) {
    return null;
  }

  const middle = Math.floor(
    prepared.length / 2
  );

  return prepared.length % 2
    ? prepared[middle]
    : (prepared[middle - 1] + prepared[middle]) / 2;
}


function MarginValue({
  value,
  previous,
}) {
  const hasPrevious = (
    previous !== null
    && previous !== undefined
    && Number(previous) !== Number(value)
  );

  return (
    <div className="iprice-revised-value">
      <strong>{formatPercent(value)}</strong>
      {hasPrevious && (
        <del>{formatPercent(previous)}</del>
      )}
    </div>
  );
}


function getStatusLabel(value) {
  const labels = {
    success: "Рассчитано",
    warning: "Предупреждение",
    error: "Ошибка",
  };

  return labels[value] || value || "—";
}


function getPricingMethodLabel(value) {
  if (value === "analog") {
    return "Аналог";
  }

  if (value === "exclusive") {
    return "Эксклюзив";
  }

  return value || "—";
}


function MetricCard({
  label,
  value,
  secondary,
}) {
  return (
    <div className="iprice-product-metric">
      <span>
        {label}
      </span>

      <strong>
        {value}
      </strong>

      {secondary && (
        <small>
          {secondary}
        </small>
      )}
    </div>
  );
}


const PRICE_RANGE_METRICS = [
  ["current_retail_median", "Медиана розницы", "#3b9a63"],
  ["competitor_rrp_min", "Минимум рынка", "#efa819"],
  ["competitor_rrp_median", "Медиана рынка", "#f0642d"],
  ["competitor_rrp_max", "Максимум рынка", "#a91442"],
];


function getPriceRangeStep(span) {
  const roughStep = Math.max(span / 5, 1);
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * magnitude;
}


function normalizePrice(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}


function PriceRangeMetric({ label, value, color, secondary, symbol }) {
  return (
    <div className="iprice-price-range-summary__item">
      <span className="iprice-price-range-summary__icon" style={{ borderColor: color, color }}>
        {symbol}
      </span>
      <div>
        <span>{label}</span>
        <strong style={{ color }}>{value}</strong>
        {secondary && <small>{secondary}</small>}
      </div>
    </div>
  );
}


function PriceRangeChart({ product }) {
  const isExclusive = product?.pricing_method === "exclusive";
  const marketMetrics = PRICE_RANGE_METRICS
    .map(([field, label, color]) => {
      const rawValue = product?.[field];
      return {
        field,
        label,
        color,
        value: rawValue === null || rawValue === undefined || rawValue === ""
          ? null
          : Math.round(Number(rawValue)),
      };
    })
    .filter((item) => (
      Number.isFinite(item.value)
      && (!isExclusive || item.field === "current_retail_median")
    ))
    .sort((left, right) => left.value - right.value);
  const finalRrp = normalizePrice(product?.effective_approved_rrp_median);
  const finalMetric = finalRrp !== null
    ? {
        field: "effective_approved_rrp_median",
        label: "Итоговая РРЦ",
        color: isExclusive ? "#4878c7" : "#ff6b2c",
        value: Math.round(finalRrp),
      }
    : null;
  const availableMetrics = finalMetric
    ? [...marketMetrics, finalMetric]
    : marketMetrics;

  if (!availableMetrics.length) {
    return <div className="iprice-product-chart-empty">Данные ценового диапазона отсутствуют.</div>;
  }

  const values = availableMetrics.map((item) => item.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const spread = rawMax - rawMin;
  const padding = spread > 0 ? spread * 0.14 : Math.max(Math.abs(rawMin) * 0.12, 100);
  const step = getPriceRangeStep((spread || padding) + (padding * 2));
  const domainMin = Math.max(0, Math.floor((rawMin - padding) / step) * step);
  const domainMax = Math.ceil((rawMax + padding) / step) * step || step;
  const domainSpan = domainMax - domainMin;
  const laneLastPositions = [];
  const chartData = marketMetrics.map((item) => {
    const position = ((item.value - domainMin) / domainSpan) * 100;
    let lane = laneLastPositions.findIndex(
      (lastPosition) => position - lastPosition >= 16,
    );
    if (lane === -1) {
      lane = laneLastPositions.length;
    }
    laneLastPositions[lane] = position;
    return { ...item, position, lane };
  });
  const ticks = Array.from({ length: 6 }, (_, index) => ({
    value: domainMin + ((domainSpan * index) / 5),
    position: index * 20,
  }));
  const finalPosition = finalMetric
    ? ((finalMetric.value - domainMin) / domainSpan) * 100
    : null;
  const marketMin = normalizePrice(product?.competitor_rrp_min);
  const marketMedian = normalizePrice(product?.competitor_rrp_median);
  const marketMax = normalizePrice(product?.competitor_rrp_max);
  const retailMedian = normalizePrice(product?.current_retail_median);
  const marketAvailable = !isExclusive && [marketMin, marketMedian, marketMax].every((value) => value !== null);
  const reference = isExclusive ? retailMedian : marketMedian;
  const positionPercent = finalRrp !== null && reference !== null && reference !== 0
    ? ((finalRrp - reference) / reference) * 100
    : null;
  const positionLabel = positionPercent === null
    ? "Недостаточно данных"
    : Math.abs(positionPercent) < 0.05
      ? `Совпадает с медианой ${isExclusive ? "розницы" : "рынка"}`
      : `${positionPercent > 0 ? "Выше" : "Ниже"} медианы ${isExclusive ? "розницы" : "рынка"}`;
  const positionColor = isExclusive ? "#4878c7" : positionPercent > 0 ? "#a91442" : positionPercent < 0 ? "#efa819" : "#3b9a63";
  const rangeStart = marketAvailable ? ((marketMin - domainMin) / domainSpan) * 100 : 0;
  const rangeWidth = marketAvailable ? ((marketMax - marketMin) / domainSpan) * 100 : 0;
  const marketMedianPosition = marketAvailable
    ? ((marketMedian - domainMin) / domainSpan) * 100
    : null;
  const markerDistance = finalPosition !== null && marketMedianPosition !== null
    ? Math.abs(finalPosition - marketMedianPosition)
    : null;
  const relationMode = markerDistance === null
    ? "standard"
    : markerDistance <= 2
      ? "cluster"
      : markerDistance <= 9
        ? "close"
        : "standard";
  const relationCenter = finalPosition !== null && marketMedianPosition !== null
    ? (finalPosition + marketMedianPosition) / 2
    : null;
  const relationAmount = finalRrp !== null && marketMedian !== null
    ? finalRrp - marketMedian
    : null;

  return (
    <div className="iprice-price-range">
      <div className="iprice-price-range__header">
        <h3>Ценовой диапазон</h3>
        <span className={`iprice-price-range__badge ${isExclusive ? "is-exclusive" : ""}`}>
          {isExclusive ? "Эксклюзивный товар" : marketAvailable ? "Есть аналоги на рынке" : "Аналоги не найдены"}
        </span>
      </div>

      <div className={`iprice-price-range__body ${isExclusive ? "is-exclusive" : ""}`}>
        {isExclusive && (
          <div className="iprice-price-range__exclusive-note">
            <span aria-hidden="true">◇</span>
            <div><strong>У товара нет аналогов на рынке</strong><small>Сравнение с рынком недоступно</small></div>
          </div>
        )}
        <div className="iprice-price-range__scale-wrap">
          <div className="iprice-price-range__scale">
            {marketAvailable && (
              <span className="iprice-price-range__market-band" style={{ left: `${rangeStart}%`, width: `${rangeWidth}%` }} />
            )}
            {ticks.map((tick) => (
              <span key={tick.position} className="iprice-price-range__tick" style={{ left: `${tick.position}%` }}>
                <i />
                <small>{formatWholeMoney(tick.value)}</small>
              </span>
            ))}
            {chartData.map((metric) => (
              <span
                key={metric.field}
                className={`iprice-price-range__marker ${metric.field === "competitor_rrp_median" ? `is-market-median is-${relationMode}` : ""}`}
                style={{ left: `${metric.position}%`, "--marker-color": metric.color, "--marker-lane": metric.lane }}
              >
                <i />
                {(isExclusive || metric.field !== "current_retail_median") && (
                  <strong>{formatWholeMoney(metric.value)}</strong>
                )}
                <small>{metric.label}</small>
              </span>
            ))}
            {finalMetric && (
              <span
                className={`iprice-price-range__final-marker is-${relationMode}`}
                style={{ left: `${finalPosition}%`, "--marker-color": finalMetric.color }}
              >
                <span>Итоговая РРЦ<strong>{formatWholeMoney(finalMetric.value)}</strong></span>
                <i />
              </span>
            )}
            {relationMode === "cluster" && relationCenter !== null && (
              <span
                className="iprice-price-range__cluster"
                style={{ left: `${relationCenter}%` }}
              >
                <span><small>РРЦ</small><strong>{formatWholeMoney(finalRrp)}</strong></span>
                <span><small>Медиана рынка</small><strong>{formatWholeMoney(marketMedian)}</strong></span>
                <span><small>Разница</small><strong>{formatSignedMoney(relationAmount)} / {positionPercent === null ? "—" : `${positionPercent > 0 ? "+" : ""}${formatNumber(positionPercent, 1)}%`}</strong></span>
              </span>
            )}
            {relationMode === "close" && relationCenter !== null && (
              <span
                className="iprice-price-range__close-relation"
                style={{ left: `${relationCenter}%` }}
              >
                <span>Разница {formatSignedMoney(relationAmount)} / {positionPercent === null ? "—" : `${positionPercent > 0 ? "+" : ""}${formatNumber(positionPercent, 1)}%`}</span>
                <strong>РРЦ {positionPercent > 0 ? "выше" : positionPercent < 0 ? "ниже" : "равна"} медианы рынка</strong>
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="iprice-price-range-summary">
        <PriceRangeMetric label="Медиана розницы" value={formatWholeMoney(retailMedian)} color="#3b9a63" secondary="Цена розничных продаж" symbol="▱" />
        {!isExclusive && marketAvailable && <PriceRangeMetric label="Минимум рынка" value={formatWholeMoney(marketMin)} color="#efa819" symbol="▥" />}
        {!isExclusive && marketAvailable && <PriceRangeMetric label="Медиана рынка" value={formatWholeMoney(marketMedian)} color="#f0642d" symbol="▥" />}
        {!isExclusive && marketAvailable && <PriceRangeMetric label="Максимум рынка" value={formatWholeMoney(marketMax)} color="#a91442" symbol="▥" />}
        {isExclusive && <PriceRangeMetric label="Итоговая РРЦ" value={formatWholeMoney(finalRrp)} color="#4878c7" secondary="Ваша итоговая цена" symbol="◇" />}
        <PriceRangeMetric
          label="Позиция итоговой РРЦ"
          value={positionLabel}
          color={positionColor}
          secondary={positionPercent === null ? null : `${positionPercent > 0 ? "+" : ""}${formatNumber(positionPercent, 1)}%`}
          symbol={positionPercent > 0 ? "↑" : positionPercent < 0 ? "↓" : "✓"}
        />
        {!isExclusive && marketAvailable && <PriceRangeMetric label="Диапазон рынка" value={`${formatWholeMoney(marketMin)} – ${formatWholeMoney(marketMax)}`} color="#d8843f" symbol="▭" />}
      </div>
    </div>
  );
}


function OverviewTab({
  product,
  regions,
}) {
  const successfulRegions = useMemo(
    () => (
      regions.filter(
        (region) => (
          region.calculation_status
          === "success"
        )
      )
    ),
    [regions],
  );

  const errorRegions = useMemo(
    () => (
      regions.filter(
        (region) => (
          region.calculation_status
          === "error"
        )
      )
    ),
    [regions],
  );

  const effectivePrices = useMemo(
    () => (
      regions
        .map(
          (region) => Number(
            region.effective_approved_rrp
          )
        )
        .filter(
          (value) => (
            Number.isFinite(value)
          )
        )
    ),
    [regions],
  );

  const effectiveMin = (
    effectivePrices.length
      ? Math.min(...effectivePrices)
      : null
  );

  const effectiveMax = (
    effectivePrices.length
      ? Math.max(...effectivePrices)
      : null
  );

  const chartProduct = useMemo(() => ({
    ...product,
    current_retail_median: (
      normalizePrice(product.current_retail_median)
      ?? median(regions.map((region) => region.current_retail))
    ),
    effective_approved_rrp_median: (
      normalizePrice(product.effective_approved_rrp_median)
      ?? median(regions.map((region) => (
        region.effective_approved_rrp
        ?? region.default_approved_rrp
      )))
    ),
  }), [product, regions]);

  return (
    <div className="iprice-product-overview">
      <section className="iprice-product-overview__section">
        <div className="iprice-product-metrics">
        <MetricCard
          label="Медиана розницы"
          value={formatMoney(
            product.current_retail_median
          )}
          secondary={
            (
              product.current_retail_min
              !== product.current_retail_max
            )
              ? (
                  `${formatMoney(
                    product.current_retail_min
                  )} — ${formatMoney(
                    product.current_retail_max
                  )}`
                )
              : null
          }
        />

        <MetricCard
          label="Медиана итоговой РРЦ"
          value={formatMoney(
            product.effective_approved_rrp_median
          )}
        />

        <MetricCard
          label="Δ: розница − итоговая РРЦ"
          value={formatSignedMoney(
            product.current_vs_approved_amount
          )}
        />

        <MetricCard
          label="Медиана рынка"
          value={formatMoney(
            product.competitor_rrp_median
          )}
          secondary={
            product.competitor_count
              ? (
                  `${product.competitor_count} `
                  + "товаров-конкурентов"
                )
              : "Конкуренты отсутствуют"
          }
        />

        <MetricCard
          label="Итоговая РРЦ"
          value={
            effectiveMin === effectiveMax
              ? formatMoney(effectiveMin)
              : (
                  `${formatMoney(effectiveMin)}`
                  + " — "
                  + `${formatMoney(effectiveMax)}`
                )
          }
          secondary="Диапазон по регионам"
        />

        <MetricCard
          label="Региональные расчёты"
          value={`${successfulRegions.length} из ${regions.length}`}
          secondary={
            errorRegions.length
              ? (
                  `С ошибкой: `
                  + errorRegions.length
                )
              : "Ошибок нет"
          }
          />
        </div>
      </section>

      <section className="iprice-product-overview__section iprice-product-parameters-summary">
        <div className="iprice-product-parameters-summary__coefficients">
          <MetricCard
            label="Параметр расчёта"
            value={
              product.pricing_method === "analog"
                ? formatNumber(product.calculation_details?.base_analog_median)
                : formatPercent(product.calculation_details?.base_exclusive_median)
            }
            secondary={
              product.pricing_method === "analog"
                ? "К цене аналога"
                : "Базовая маржа"
            }
          />
          <MetricCard
            label="Минимальная допустимая маржа"
            value={formatPercent(product.calculation_details?.minimum_margin_median)}
          />
        </div>

        <div className="iprice-product-parameters-summary__prices">
          {[
            ["distr", "Дистрибьютор"],
            ["distr_1", "Дистрибьютор 1"],
            ["small", "Малый опт"],
            ["medium", "Средний опт"],
            ["large", "Крупный опт"],
          ].map(([field, label]) => (
            <MetricCard
              key={field}
              label={label}
              value={formatMoney(product.calculation_details?.[`effective_${field}_median`])}
              secondary={formatPercent(product.calculation_details?.[`discount_${field}_median`])}
            />
          ))}
        </div>
      </section>

      <section className="iprice-product-overview__section">
        <div className="iprice-product-info-grid">
        <div>
          <span>Метод расчёта</span>
          <strong>
            {getPricingMethodLabel(
              product.pricing_method
            )}
          </strong>
        </div>

        <div>
          <span>Статус расчёта</span>
          <strong>
            {getStatusLabel(
              product.calculation_status
            )}
          </strong>
        </div>

        <div>
          <span>Тип номенклатуры iPrice</span>
          <strong>
            {product.category || "—"}
          </strong>
        </div>

        <div>
          <span>Категория iPrice</span>
          <strong>
            {product.subcategory || "—"}
          </strong>
        </div>

        <div>
          <span>Подкатегория iPrice</span>
          <strong>
            {product.subcategory_type || "—"}
          </strong>
        </div>

        <div>
          <span>Категория номенклатуры 1С</span>
          <strong>
            {product.nom_category || "—"}
          </strong>
        </div>

        <div>
          <span>Группа номенклатуры 1С</span>
          <strong>
            {product.nom_group || "—"}
          </strong>
        </div>

        <div>
          <span>Вид номенклатуры 1С</span>
          <strong>
            {product.nom_view || "—"}
          </strong>
        </div>

        <div>
          <span>Материал iPrice</span>
          <strong>
            {product.material || "—"}
          </strong>
        </div>

        <div>
          <span>Цвет iPrice</span>
          <strong>
            {product.color || "—"}
          </strong>
        </div>

        <div>
          <span>Модификация iPrice</span>
          <strong>
            {product.modification || "—"}
          </strong>
          </div>
        </div>

        {Array.isArray(product.error_codes)
          && product.error_codes.length > 0 && (
            <div className="iprice-product-issues iprice-product-issues--error">
              <strong>
                Ошибки товара
              </strong>

              <ul>
                {product.error_codes.map(
                  (code) => (
                    <li key={code}>
                      {code}
                    </li>
                  )
                )}
              </ul>
            </div>
          )}

        {Array.isArray(product.warning_codes)
          && product.warning_codes.length > 0 && (
            <div className="iprice-product-issues iprice-product-issues--warning">
              <strong>
                Предупреждения
              </strong>

              <ul>
                {product.warning_codes.map(
                  (code) => (
                    <li key={code}>
                      {code}
                    </li>
                  )
                )}
              </ul>
            </div>
          )}
      </section>

      <section className="iprice-product-overview__section">
        <PriceRangeChart product={chartProduct} />
      </section>
    </div>
  );
}



function getApprovalDifference(
  region,
) {
  const calculated = Number(
    region.calculated_rrp
  );

  const effective = Number(
    region.effective_approved_rrp
  );

  if (
    !Number.isFinite(calculated)
    || !Number.isFinite(effective)
  ) {
    return null;
  }

  const amount = (
    effective - calculated
  );

  const percent = (
    calculated !== 0
      ? amount / calculated
      : null
  );

  return {
    amount,
    percent,
  };
}


function RegionsTab({
  regions,
  competitors,
  snapshotId,
  selectionEditable,
  selectionBusyKey,
  onSelectionChange,
}) {
  const [
    detailsRegionId,
    setDetailsRegionId,
  ] = useState(null);

  useEffect(() => {
    setDetailsRegionId(null);
  }, [snapshotId]);


  if (!regions.length) {
    return (
      <div className="iprice-product-empty">
        Региональные строки отсутствуют.
      </div>
    );
  }


  return (
    <div className="iprice-product-table-wrapper">
      <table className="iprice-product-table">
        <thead>
          <tr>
            <th>Регион продажи</th>
            <th>Место производства</th>
            <th>Розничная цена</th>
            <th>Себестоимость</th>
            <th>Логистика</th>
            <th>Медиана рынка</th>
            <th>Итоговая РРЦ</th>
            <th>Расчётная маржа</th>
            <th>Статус расчёта</th>
            <th>Действия</th>
          </tr>
        </thead>

        <tbody>
          {regions.map((region) => {
            const approvalDifference = (
              getApprovalDifference(region)
            );

            return (
              <Fragment key={region.id}>
                <tr
                  className={
                    region.current_approval
                      ? "iprice-product-region--approved"
                      : ""
                  }
                >
                  <td>
                    {region.sale_region || "—"}
                  </td>

                  <td>
                    {region.departure || "—"}
                  </td>

                  <td>
                    {formatMoney(
                      region.current_retail
                    )}
                  </td>

                  <td>
                    {formatMoney(
                      region.product_cost
                    )}
                  </td>

                  <td>
                    {formatMoney(
                      region.logistics_unit
                    )}
                  </td>

                  <td>
                    {formatMoney(
                      region
                        .regional_competitor_rrp_median
                    )}
                  </td>

                  <td>
                    <strong>
                      {formatMoney(
                        region
                          .effective_approved_rrp
                      )}
                    </strong>

                    {region.current_approval && (
                      <>
                        <div className="iprice-product-table__secondary">
                          Ручное утверждение, rev.{" "}
                          {
                            region.current_approval
                              .revision
                          }
                        </div>

                        {approvalDifference && (
                          <div
                            className={[
                              "iprice-approval-difference",
                              approvalDifference.amount > 0
                                ? (
                                    "iprice-approval-difference"
                                    + "--up"
                                  )
                                : (
                                    approvalDifference.amount < 0
                                      ? (
                                          "iprice-approval-difference"
                                          + "--down"
                                        )
                                      : ""
                                  ),
                            ]
                              .filter(Boolean)
                              .join(" ")}
                          >
                            {approvalDifference.amount > 0
                              ? "+"
                              : ""}

                            {formatMoney(
                              approvalDifference.amount
                            )}

                            {" / "}

                            {approvalDifference.percent
                              !== null
                              ? (
                                  `${
                                    approvalDifference.percent > 0
                                      ? "+"
                                      : ""
                                  }${formatPercent(
                                    approvalDifference.percent
                                  )}`
                                )
                              : "—"}
                          </div>
                        )}
                      </>
                    )}
                  </td>

                  <td>
                    <MarginValue
                      value={
                        region.effective_margin_calculated
                        ?? region.margin_calculated
                      }
                      previous={
                        region
                          .previous_effective_margin_calculated
                      }
                    />
                  </td>

                  <td>
                    {getStatusLabel(
                      region.calculation_status
                    )}
                  </td>

                  <td>
                    <div className="iprice-product-region-actions">
                      <button
                        type="button"
                        className="iprice-table-action"
                        onClick={() => {
                          setDetailsRegionId(
                            (previous) => (
                              previous === region.id
                                ? null
                                : region.id
                            )
                          );
                        }}
                      >
                        Расчёт
                      </button>

                    </div>
                  </td>
                </tr>

                {detailsRegionId
                  === region.id && (
                  <tr className="iprice-approval-row">
                    <td colSpan={10}>
                      <IPriceRegionCalculationDetails
                        region={region}
                        competitors={competitors}
                        selectionEditable={selectionEditable}
                        selectionBusyKey={selectionBusyKey}
                        onSelectionChange={onSelectionChange}
                      />
                    </td>
                  </tr>
                )}

              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


function CompetitorsTab({
  competitors,
  selectionEditable,
  selectionBusyKey,
  onSelectionChange,
}) {
  if (!competitors.length) {
    return (
      <div className="iprice-product-empty">
        Конкуренты в расчёте отсутствуют.
      </div>
    );
  }

  return (
    <div className="iprice-market-cards">
      {competitors.map((competitor) => (
        <IPriceCompetitorCard
          key={competitor.id}
          competitor={competitor}
          selectionEditable={selectionEditable}
          selectionBusy={selectionBusyKey === competitor.group_key}
          onSelectionChange={(keys, mode) => onSelectionChange?.(
            keys, mode, competitor.group_key
          )}
        />
      ))}
    </div>
  );
}


function WeightedSimilarity({ evidence }) {
  const rows = Object.entries(evidence || {});
  if (!rows.length) {
    return <span className="iprice-similarity">Сравнение свойств не рассчитано</span>;
  }
  return rows.map(([name, item]) => (
    <span
      key={name}
      className={item?.matched
        ? "iprice-similarity iprice-similarity--matched"
        : "iprice-similarity iprice-similarity--not-matched"}
      title={`Наше: ${formatMatchPropertyValue(item?.base)}; конкурент: ${formatMatchPropertyValue(item?.competitor)}`}
    >
      {item?.matched ? "✓" : "×"}{" "}
      {item?.label || "Свойство товара"}
    </span>
  ));
}


function MarketMedianPrice({ item }) {
  const rows = (Array.isArray(item.variants) ? item.variants : [])
    .flatMap((variant) => {
      const regions = Array.isArray(variant.regions) && variant.regions.length
        ? variant.regions
        : ["Регион не определён"];
      return regions.map((region) => ({
        key: `${variant.product_key}|${region}`,
        region,
        productKey: variant.product_key,
        price: variant.price,
        url: variant.url,
      }));
    })
    .sort((left, right) => left.region.localeCompare(right.region, "ru"));

  return (
    <details className="iprice-market-price-details">
      <summary className="iprice-market-card__price">
        <span>Медиана рынка</span>
        <strong>{formatWholeMoney(item.price)}</strong>
      </summary>
      <div className="iprice-market-price-details__rows">
        {rows.length ? rows.map((row) => (
          <div key={row.key} className="iprice-market-price-details__row">
            <span>
              {row.region}
              {" · "}
              {row.productKey ?? "—"}
            </span>
            <strong>{formatWholeMoney(row.price)}</strong>
            {row.url ? (
              <a href={row.url} target="_blank" rel="noreferrer">
                Открыть товар
              </a>
            ) : (
              <span>Ссылка отсутствует</span>
            )}
          </div>
        )) : (
          <div className="iprice-market-price-details__empty">
            Региональные цены отсутствуют.
          </div>
        )}
      </div>
    </details>
  );
}


const EMPTY_MODIFICATION_FILTER = "__EMPTY_MODIFICATION__";


function ModificationFilter({
  items,
  value,
  onChange,
  competitorValue = "",
  onCompetitorChange = null,
}) {
  const modifications = Array.from(new Set(
    items
      .map((item) => String(item.modification || "").trim())
      .filter(Boolean),
  )).sort((left, right) => left.localeCompare(right, "ru"));
  const hasEmpty = items.some(
    (item) => !String(item.modification || "").trim(),
  );
  const competitors = Array.from(new Set(
    items
      .map((item) => String(item.source || "").trim().toLowerCase())
      .filter(Boolean),
  )).sort((left, right) => (
    getIPriceCompetitorSourceLabel(left).localeCompare(
      getIPriceCompetitorSourceLabel(right),
      "ru",
    )
  ));

  return (
    <div className="iprice-assortment-filter">
      <label className="iprice-assortment-filter__modification">
        <span>Модификация iPrice</span>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Все модификации</option>
          {modifications.map((modification) => (
            <option key={modification} value={modification}>
              {modification}
            </option>
          ))}
          {hasEmpty && (
            <option value={EMPTY_MODIFICATION_FILTER}>
              Не указана
            </option>
          )}
        </select>
      </label>
      {onCompetitorChange && (
        <label className="iprice-assortment-filter__competitor">
          <span>Конкурент</span>
          <select
            value={competitorValue}
            onChange={(event) => onCompetitorChange(event.target.value)}
          >
            <option value="">Все конкуренты</option>
            {competitors.map((source) => (
              <option key={source} value={source}>
                {getIPriceCompetitorSourceLabel(source)}
              </option>
            ))}
          </select>
        </label>
      )}
      <span className="iprice-assortment-filter__count">
        Показано {items.filter((item) => (
          (
            !value
            || (value === EMPTY_MODIFICATION_FILTER
              ? !String(item.modification || "").trim()
              : String(item.modification || "").trim() === value)
          )
          && (
            !competitorValue
            || String(item.source || "").trim().toLowerCase() === competitorValue
          )
        )).length} из {items.length}
      </span>
    </div>
  );
}


function MarketTab({
  loading,
  error,
  data,
  selectionEditable,
  selectionBusyKey,
  onSelectionChange,
}) {
  const [modificationFilter, setModificationFilter] = useState("");
  const [competitorFilter, setCompetitorFilter] = useState("");
  const results = Array.isArray(data?.results) ? data.results : [];
  const filteredResults = results.filter((item) => (
    (
      !modificationFilter
      || (modificationFilter === EMPTY_MODIFICATION_FILTER
        ? !String(item.modification || "").trim()
        : String(item.modification || "").trim() === modificationFilter)
    )
    && (
      !competitorFilter
      || String(item.source || "").trim().toLowerCase() === competitorFilter
    )
  ));

  if (loading) {
    return (
      <div className="iprice-product-empty">
        Загрузка рыночного ассортимента...
      </div>
    );
  }

  if (error) {
    return (
      <div className="iprice-inline-error">
        <span>{error}</span>
      </div>
    );
  }

  const eligibleCount = results.filter((item) => item.match_eligible).length;
  const calculatedCount = results.filter(
    (item) => item.similarity_score !== null && item.similarity_score !== undefined
  ).length;

  if (!results.length) {
    return (
      <div className="iprice-product-empty">
        Подходящие товары рынка не найдены.
      </div>
    );
  }

  return (
    <>
      <div className="iprice-market-summary">
        <div>
          <span>Аналогов</span>
          <strong>
            {results.length}
          </strong>
        </div>

        <div>
          <span>Прошли пороги</span>
          <strong>
            {eligibleCount}
          </strong>
        </div>

        <div>
          <span>Сходство рассчитано</span>
          <strong>
            {calculatedCount}
          </strong>
        </div>
      </div>

      <ModificationFilter
        items={results}
        value={modificationFilter}
        onChange={setModificationFilter}
        competitorValue={competitorFilter}
        onCompetitorChange={setCompetitorFilter}
      />

      {filteredResults.length ? (
        <div className="iprice-market-cards">
        {filteredResults.map((item) => (
          <article
            key={item.group_key}
            className="iprice-market-card"
          >
            <IPriceProductImage
              src={item.image}
              alt={item.subcategory}
              className="iprice-product-drawer__image"
              placeholderClassName="iprice-product-drawer__image-placeholder"
              placeholderText="Нет изображения"
            />

            <div className="iprice-market-card__body">
              <div className="iprice-market-card__header">
                <strong>
                  {getIPriceCompetitorSourceLabel(
                    item.source
                  )}
                </strong>

                <span>
                  Сходство:{" "}
                  {item.similarity_score === null || item.similarity_score === undefined
                    ? "—"
                    : `${Number(item.similarity_score).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`}
                </span>
              </div>

              <h4>
                {[
                  item.category,
                  item.subcategory,
                  item.subcategory_type,
                ]
                  .filter(Boolean)
                  .join(" / ")}
              </h4>

              <MarketMedianPrice item={item} />

              <div className="iprice-market-card__properties">
                <span>
                  Материал iPrice:{" "}
                  {item.material || "—"}
                </span>

                <span>
                  Цвет iPrice:{" "}
                  {item.color || "—"}
                </span>

                <span>
                  Модификация iPrice:{" "}
                  {item.modification || "—"}
                </span>

                {item.additional_property && (
                  <span>
                    Вариант товара: {item.additional_property}
                  </span>
                )}
              </div>

              <div className="iprice-market-card__similarity">
                <span className="iprice-similarity">
                  Покрытие свойств: {item.match_coverage === null || item.match_coverage === undefined
                    ? "—"
                    : `${Number(item.match_coverage).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`}
                </span>
                <WeightedSimilarity evidence={item.similarity} />
              </div>

              <div className="iprice-market-card__flags">
                {item.is_used_in_snapshot && item.is_price_used_in_calculation !== false && (
                  <span>
                    Участвует в расчёте
                  </span>
                )}
                {item.selection_mode === "include" && (
                  <span>Включён вручную</span>
                )}
                {item.selection_mode === "exclude" && (
                  <span className="iprice-market-card__flag--not-used">
                    Исключён вручную
                  </span>
                )}
                {item.selection_mode === "auto" && item.match_eligible && (
                  <span>Автоматически прошёл пороги</span>
                )}
                {item.selection_mode === "auto" && !item.match_eligible && (
                  <span className="iprice-market-card__flag--not-used">
                    Не прошёл автоматические пороги
                  </span>
                )}
                {item.is_price_used_in_calculation === false && (
                  <span className="iprice-market-card__flag--not-used">
                    Цена отсутствует
                  </span>
                )}
              </div>

              <div className="iprice-market-card__actions">
                {item.selection_mode !== "auto" ? (
                  <button
                    type="button"
                    className="iprice-table-action"
                    disabled={!selectionEditable || selectionBusyKey === item.group_key}
                    onClick={() => onSelectionChange?.(
                      item.competitor_product_keys,
                      "auto",
                      item.group_key,
                    )}
                  >
                    {selectionBusyKey === item.group_key
                      ? "Пересчёт…"
                      : "Вернуть автоматический выбор"}
                  </button>
                ) : item.is_used_in_snapshot ? (
                  <button
                    type="button"
                    className="iprice-table-action"
                    disabled={!selectionEditable || selectionBusyKey === item.group_key}
                    onClick={() => onSelectionChange?.(
                      item.competitor_product_keys,
                      "exclude",
                      item.group_key,
                    )}
                  >
                    {selectionBusyKey === item.group_key
                      ? "Пересчёт…"
                      : "Исключить из расчёта"}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="iprice-table-action"
                    disabled={!selectionEditable || selectionBusyKey === item.group_key}
                    onClick={() => onSelectionChange?.(
                      item.competitor_product_keys,
                      "include",
                      item.group_key,
                    )}
                  >
                    {selectionBusyKey === item.group_key
                      ? "Пересчёт…"
                      : "Включить в расчёт"}
                  </button>
                )}
              </div>

            </div>
          </article>
        ))}
        </div>
      ) : (
        <div className="iprice-product-empty">
          Товары с выбранными параметрами не найдены.
        </div>
      )}
    </>
  );
}


function OwnAssortmentTab({
  loading,
  error,
  data,
}) {
  const [modificationFilter, setModificationFilter] = useState("");
  const results = Array.isArray(data?.results) ? data.results : [];
  const filteredResults = results.filter((item) => (
    !modificationFilter
    || (modificationFilter === EMPTY_MODIFICATION_FILTER
      ? !String(item.modification || "").trim()
      : String(item.modification || "").trim() === modificationFilter)
  ));

  if (loading) {
    return (
      <div className="iprice-product-empty">
        Загрузка собственного ассортимента...
      </div>
    );
  }

  if (error) {
    return (
      <div className="iprice-inline-error">
        <span>{error}</span>
      </div>
    );
  }

  if (!results.length) {
    return (
      <div className="iprice-product-empty">
        Собственный ассортимент не найден.
      </div>
    );
  }

  return (
    <>
      <div className="iprice-market-summary">
        <div>
          <span>Товаров</span>
          <strong>{data.counts?.cards ?? 0}</strong>
        </div>
        <div>
          <span>Прошли пороги</span>
          <strong>{data.counts?.eligible ?? 0}</strong>
        </div>
        <div>
          <span>Сходство рассчитано</span>
          <strong>{data.counts?.calculated ?? 0}</strong>
        </div>
      </div>

      <ModificationFilter
        items={results}
        value={modificationFilter}
        onChange={setModificationFilter}
      />

      {filteredResults.length ? (
        <div className="iprice-market-cards">
        {filteredResults.map((item) => (
          <article
            key={item.group_key}
            className="iprice-market-card"
          >
            <IPriceProductImage
              src={item.image}
              alt={item.name}
              className="iprice-product-drawer__image"
              placeholderClassName="iprice-product-drawer__image-placeholder"
              placeholderText="Нет изображения"
            />
            <div className="iprice-market-card__body">
              <div className="iprice-market-card__header">
                <strong>Ключ системы: {item.product_key}</strong>
                <span>
                  Сходство: {item.similarity_score === null || item.similarity_score === undefined
                    ? "—"
                    : `${Number(item.similarity_score).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`}
                </span>
              </div>
              <h4>{item.name || "Без наименования"}</h4>
              <details className="iprice-market-price-details">
                <summary className="iprice-market-card__price">
                  <span>Медиана розницы</span>
                  <strong>{formatWholeMoney(item.price)}</strong>
                </summary>
                <div className="iprice-market-price-details__rows">
                  {Array.isArray(item.regional_prices)
                    && item.regional_prices.length ? (
                    item.regional_prices.map((row) => (
                      <div
                        key={`${item.product_key}|${row.region}`}
                        className="iprice-market-price-details__row"
                      >
                        <span>{row.region}</span>
                        <strong>{formatWholeMoney(row.price)}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="iprice-market-price-details__empty">
                      Региональные цены отсутствуют.
                    </div>
                  )}
                </div>
              </details>
              <div className="iprice-market-card__properties">
                <span>Код 1С: {item.code_1c || "—"}</span>
                <span>Медиана рынка: {formatWholeMoney(item.market_price)}</span>
                <span>Материал iPrice: {item.material || "—"}</span>
                <span>Цвет iPrice: {item.color || "—"}</span>
                <span>Модификация iPrice: {item.modification || "—"}</span>
              </div>
              <div className="iprice-market-card__similarity">
                <span className="iprice-similarity">
                  Покрытие свойств: {item.match_coverage === null || item.match_coverage === undefined
                    ? "—"
                    : `${Number(item.match_coverage).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`}
                </span>
                <WeightedSimilarity evidence={item.similarity} />
              </div>
              {item.url && (
                <a href={item.url} target="_blank" rel="noreferrer">
                  Открыть товар
                </a>
              )}
            </div>
          </article>
        ))}
        </div>
      ) : (
        <div className="iprice-product-empty">
          Товары с выбранной модификацией не найдены.
        </div>
      )}
    </>
  );
}


export function IPriceProductDrawer({
  canEdit = false,
  snapshotId,
  productId,
  onClose,
  onRegionApprovalSaved,
  onCompetitorSelectionChanged,
  realtimeEvent,
  pricingEditable = false,
  onOpenPricing,
}) {
  const [
    activeTab,
    setActiveTab,
  ] = useState(TAB_OVERVIEW);

  const [
    detail,
    setDetail,
  ] = useState(null);

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    marketData,
    setMarketData,
  ] = useState(null);

  const [
    marketLoading,
    setMarketLoading,
  ] = useState(false);

  const [
    marketError,
    setMarketError,
  ] = useState("");

  const [ownData, setOwnData] = useState(null);
  const [ownLoading, setOwnLoading] = useState(false);
  const [ownError, setOwnError] = useState("");
  const [selectionBusyKey, setSelectionBusyKey] = useState("");


  const loadDetail = useCallback(
    async () => {
      if (
        !snapshotId
        || !productId
      ) {
        return;
      }

      setLoading(true);
      setError("");

      try {
        const result = (
          await getIPriceSnapshotProductDetail(
            snapshotId,
            productId,
          )
        );

        setDetail(result);
      } catch (requestError) {
        setError(
          requestError.response
            ?.data?.message
          || requestError.response
            ?.data?.detail
          || (
            "Не удалось загрузить "
            + "карточку товара."
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [
      snapshotId,
      productId,
    ],
  );


  const loadMarket = useCallback(
    async () => {
      if (
        !snapshotId
        || !productId
      ) {
        return;
      }

      setMarketLoading(true);
      setMarketError("");

      try {
        const result = (
          await getIPriceMarketAssortment(
            snapshotId,
            productId,
          )
        );

        setMarketData(result);
      } catch (requestError) {
        setMarketError(
          requestError.response
            ?.data?.message
          || requestError.response
            ?.data?.detail
          || (
            "Не удалось загрузить "
            + "рыночный ассортимент."
          )
        );
      } finally {
        setMarketLoading(false);
      }
    },
    [
      snapshotId,
      productId,
    ],
  );

  const loadOwnAssortment = useCallback(
    async () => {
      if (!snapshotId || !productId) {
        return;
      }
      setOwnLoading(true);
      setOwnError("");
      try {
        setOwnData(
          await getIPriceOwnAssortment(snapshotId, productId)
        );
      } catch (requestError) {
        setOwnError(
          requestError.response?.data?.message
          || requestError.response?.data?.detail
          || "Не удалось загрузить собственные аналоги."
        );
      } finally {
        setOwnLoading(false);
      }
    },
    [snapshotId, productId],
  );


  useEffect(() => {
    setActiveTab(TAB_OVERVIEW);
    setDetail(null);
    setMarketData(null);
    setMarketError("");
    setOwnData(null);
    setOwnError("");

    loadDetail();
  }, [
    loadDetail,
  ]);


  useEffect(() => {
    if (
      (
        realtimeEvent?.change_type === "approval_saved"
        || realtimeEvent?.change_type === "parameters_changed"
        || realtimeEvent?.change_type === "competitor_selection_changed"
      )
      && realtimeEvent.snapshot_id === snapshotId
      && (
        realtimeEvent.change_type === "parameters_changed"
        || realtimeEvent.product_id === productId
      )
    ) {
      loadDetail();
      if (realtimeEvent.change_type === "competitor_selection_changed") {
        loadMarket();
      }
    }
  }, [
    realtimeEvent,
    snapshotId,
    productId,
    loadDetail,
    loadMarket,
  ]);

  useEffect(() => {
    if (
      activeTab === TAB_OWN
      && !ownData
      && !ownLoading
      && !ownError
    ) {
      loadOwnAssortment();
    }
  }, [
    activeTab,
    ownData,
    ownLoading,
    ownError,
    loadOwnAssortment,
  ]);


  useEffect(() => {
    if (
      activeTab === TAB_MARKET
      && !marketData
      && !marketLoading
      && !marketError
    ) {
      loadMarket();
    }
  }, [
    activeTab,
    marketData,
    marketLoading,
    marketError,
    loadMarket,
  ]);


  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener(
      "keydown",
      handleKeyDown,
    );

    return () => {
      document.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [
    onClose,
  ]);


  function handleApprovalSaved({
    regionId,
    approval,
    message,
  }) {
    if (
      !regionId
      || !approval
    ) {
      return;
    }

    setDetail((previousDetail) => {
      if (!previousDetail) {
        return previousDetail;
      }

      const previousRegions = Array.isArray(
        previousDetail.regions
      )
        ? previousDetail.regions
        : [];

      const updatedRegions = previousRegions.map(
        (region) => {
          if (region.id !== regionId) {
            return region;
          }

          return {
            ...region,
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
            previous_effective_margin_calculated: (
              region.effective_margin_calculated
              ?? region.margin_calculated
            ),
            effective_margin_calculated: (
              calculateMargin(
                approval.approved_rrp,
                region.cost_with_logistics,
              )
            ),
          };
        }
      );
      const approvedMedian = median(
        updatedRegions.map(
          (region) => (
            region.effective_approved_rrp
            ?? region.default_approved_rrp
          )
        )
      );
      const retailMedian = Number(
        previousDetail.product
          ?.current_retail_median
      );

      return {
        ...previousDetail,
        product: {
          ...previousDetail.product,
          effective_approved_rrp_median: approvedMedian,
          current_vs_approved_amount: (
            Number.isFinite(retailMedian)
            && approvedMedian !== null
              ? retailMedian - approvedMedian
              : null
          ),
        },
        regions: updatedRegions,
      };
    });

    setError("");

    onRegionApprovalSaved?.({
      snapshotId,
      productId,
      regionId,
      approval,
      message,
    });

    if (message) {
      console.info(message);
    }
  }

  const handleCompetitorSelection = useCallback(async (
    competitorProductKeys,
    selectionMode,
    groupKey = "selection",
  ) => {
    if (!snapshotId || !productId || selectionBusyKey) {
      return;
    }
    setSelectionBusyKey(groupKey);
    setError("");
    try {
      const response = await updateIPriceCompetitorSelection(
        snapshotId,
        productId,
        {
          competitor_product_keys: competitorProductKeys,
          selection_mode: selectionMode,
        },
      );
      onCompetitorSelectionChanged?.({
        snapshotId,
        productId,
        ...(response?.result || {}),
      });
      await Promise.all([
        loadDetail(),
        loadMarket(),
      ]);
    } catch (requestError) {
      setError(
        requestError.response?.data?.message
        || requestError.response?.data?.detail
        || "Не удалось изменить состав конкурентов.",
      );
    } finally {
      setSelectionBusyKey("");
    }
  }, [
    snapshotId,
    productId,
    selectionBusyKey,
    loadDetail,
    loadMarket,
    onCompetitorSelectionChanged,
  ]);


  if (!productId) {
    return null;
  }

  const product = detail?.product || {};
  const regions = Array.isArray(
    detail?.regions
  )
    ? detail.regions
    : [];

  const competitors = Array.isArray(
    detail?.competitors
  )
    ? detail.competitors
    : [];

  return (
    <div
      className="iprice-product-drawer-overlay"
      onMouseDown={(event) => {
        if (
          event.target
          === event.currentTarget
        ) {
          onClose();
        }
      }}
    >
      <aside
        className="iprice-product-drawer"
        aria-label="Карточка товара iPrice"
      >
        <header className="iprice-product-drawer__header">
          <div>
            <span>
              Карточка товара
            </span>

            <h2>
              {product.nom || "Загрузка..."}
            </h2>
          </div>

          <button
            type="button"
            aria-label="Закрыть карточку"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        {loading && !detail && (
          <div className="iprice-product-drawer__loading">
            Загрузка карточки...
          </div>
        )}

        {error && (
          <div className="iprice-inline-error">
            <span>{error}</span>
          </div>
        )}

        {detail && (
          <>
            <div className="iprice-product-drawer__summary">
              <IPriceProductImage
                src={product.image}
                alt={product.nom}
                className="iprice-product-drawer__image"
                placeholderClassName="iprice-product-drawer__image-placeholder"
                placeholderText="Нет изображения"
              />

              <div>
                <div>
                  Код 1С:{" "}
                  <strong>
                    {product.code_1c ?? "—"}
                  </strong>
                </div>

                <div>
                  Ключ системы:{" "}
                  <strong>
                    {
                      product
                        .base_product_key
                      ?? "—"
                    }
                  </strong>
                </div>

                <div>
                  Расчёт:{" "}
                  <strong>
                    {
                      detail.snapshot
                        ?.display_version
                      || "—"
                    }
                  </strong>
                </div>

                {product.url && (
                  <a
                    href={product.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть товар
                  </a>
                )}
              </div>

              <div className="iprice-product-drawer__modification">
                <span>Модификация iPrice</span>
                <strong>{product.modification || "—"}</strong>
              </div>

              <button
                type="button"
                className="iprice-action-button iprice-action-button--primary iprice-product-drawer__pricing-button"
                disabled={!pricingEditable || !product.base_product_key}
                title={
                  pricingEditable
                    ? "Перейти к настройке цен этого товара"
                    : "Настройки доступны только для последней успешной неактивированной версии при наличии права редактирования"
                }
                onClick={() => onOpenPricing?.(product.base_product_key)}
              >
                Настроить цены
              </button>
            </div>

            <div
              className="iprice-product-drawer__tabs"
              role="tablist"
            >
              {DRAWER_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={
                    activeTab === tab.id
                  }
                  className={
                    activeTab === tab.id
                      ? "active"
                      : ""
                  }
                  onClick={() => {
                    setActiveTab(tab.id);
                  }}
                >
                  {tab.label}

                  {tab.id === TAB_REGIONS && (
                    <span>
                      {regions.length}
                    </span>
                  )}

                  {tab.id
                    === TAB_COMPETITORS && (
                    <span>
                      {competitors.length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div className="iprice-product-drawer__content">
              {activeTab === TAB_OVERVIEW && (
                <OverviewTab
                  product={product}
                  regions={regions}
                />
              )}

              {activeTab === TAB_REGIONS && (
                <RegionsTab
                  canEdit={canEdit}
                  regions={regions}
                  competitors={competitors}
                  snapshotId={snapshotId}
                  selectionEditable={Boolean(
                    canEdit && detail.snapshot?.competitor_selection_editable
                  )}
                  selectionBusyKey={selectionBusyKey}
                  onSelectionChange={handleCompetitorSelection}
                  snapshotIsCurrent={Boolean(
                    detail.snapshot?.is_current
                  )}
                  onApprovalSaved={
                    handleApprovalSaved
                  }
                />
              )}

              {activeTab
                === TAB_COMPETITORS && (
                <CompetitorsTab
                  competitors={competitors}
                  selectionEditable={Boolean(
                    canEdit && detail.snapshot?.competitor_selection_editable
                  )}
                  selectionBusyKey={selectionBusyKey}
                  onSelectionChange={handleCompetitorSelection}
                />
              )}

              {activeTab === TAB_MARKET && (
                <MarketTab
                  key={`${snapshotId}:${productId}`}
                  loading={marketLoading}
                  error={marketError}
                  data={marketData}
                  selectionEditable={Boolean(
                    canEdit && detail.snapshot?.competitor_selection_editable
                  )}
                  selectionBusyKey={selectionBusyKey}
                  onSelectionChange={handleCompetitorSelection}
                />
              )}

              {activeTab === TAB_OWN && (
                <OwnAssortmentTab
                  loading={ownLoading}
                  error={ownError}
                  data={ownData}
                />
              )}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
