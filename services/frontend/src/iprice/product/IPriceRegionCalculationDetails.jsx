import {
  useMemo,
} from "react";

import {
  IPriceCompetitorCard,
} from "./IPriceCompetitorCard";


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
    2,
  )}%`;
}


function formatDate(value) {
  if (!value) {
    return "—";
  }

  const stringValue = String(value);

  if (
    /^\d{4}-\d{2}-\d{2}$/.test(
      stringValue
    )
  ) {
    const [
      year,
      month,
      day,
    ] = stringValue.split("-");

    return `${day}.${month}.${year}`;
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return stringValue;
  }

  return new Intl.DateTimeFormat(
    "ru-RU",
    {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    },
  ).format(date);
}


function normalizeText(value) {
  return String(
    value ?? ""
  )
    .trim()
    .toLocaleLowerCase("ru-RU");
}


function competitorAppliesToRegion(
  competitor,
  saleRegion,
) {
  if (competitor?.is_all_regions) {
    return true;
  }

  const normalizedSaleRegion = (
    normalizeText(saleRegion)
  );

  if (!normalizedSaleRegion) {
    return false;
  }

  const applicableRegions = Array.isArray(
    competitor?.applicable_regions
  )
    ? competitor.applicable_regions
    : [];

  return applicableRegions.some(
    (region) => (
      normalizeText(region)
      === normalizedSaleRegion
    )
  );
}


function DetailItem({
  label,
  value,
  secondary,
  previous,
}) {
  return (
    <div className="iprice-region-detail-item">
      <span>
        {label}
      </span>

      <strong>
        {value}
      </strong>

      {previous && (
        <del>
          {previous}
        </del>
      )}

      {secondary && (
        <small>
          {secondary}
        </small>
      )}
    </div>
  );
}


function CalculationStep({
  label,
  value,
  note,
  emphasized = false,
}) {
  return (
    <div
      className={[
        "iprice-region-calculation-step",
        emphasized
          ? (
              "iprice-region-calculation-step"
              + "--emphasized"
            )
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div>
        <span>
          {label}
        </span>

        {note && (
          <small>
            {note}
          </small>
        )}
      </div>

      <strong>
        {value}
      </strong>
    </div>
  );
}


function DiscountItem({
  label,
  discount,
  price,
}) {
  return (
    <div className="iprice-region-discount">
      <span>
        {label}
      </span>

      <strong>
        {formatMoney(price)}
      </strong>

      <small>
        {formatPercent(discount)}
      </small>
    </div>
  );
}


function IssuesBlock({
  title,
  codes,
  type,
}) {
  const safeCodes = Array.isArray(
    codes
  )
    ? codes
    : [];

  if (safeCodes.length === 0) {
    return null;
  }

  return (
    <div
      className={[
        "iprice-region-issues",
        `iprice-region-issues--${type}`,
      ].join(" ")}
    >
      <strong>
        {title}
      </strong>

      <ul>
        {safeCodes.map((code) => (
          <li key={code}>
            {code}
          </li>
        ))}
      </ul>
    </div>
  );
}


export function IPriceRegionCalculationDetails({
  region,
  competitors,
  selectionEditable = false,
  selectionBusyKey = "",
  onSelectionChange,
}) {
  const regionalCompetitors = useMemo(
    () => (
      (Array.isArray(competitors)
        ? competitors
        : []
      ).filter(
        (competitor) => (
          competitorAppliesToRegion(
            competitor,
            region.sale_region,
          )
        )
      )
    ),
    [
      competitors,
      region.sale_region,
    ],
  );


  const effectiveRrp = (
    region.effective_approved_rrp
    ?? region.default_approved_rrp
    ?? region.calculated_rrp
  );


  return (
    <div className="iprice-region-details">
      <section className="iprice-region-details__section">
        <h4>
          Как рассчитана цена
        </h4>

        <div className="iprice-region-calculation-chain">
          <CalculationStep
            label="Себестоимость"
            value={formatMoney(
              region.product_cost
            )}
            note={
              region.product_cost_month
                ? (
                    `Месяц: ${
                      formatDate(
                        region.product_cost_month
                      )
                    }`
                  )
                : null
            }
          />

          <CalculationStep
            label="Логистика на единицу"
            value={formatMoney(
              region.logistics_unit
            )}
            note={
              (
                `Транспорт: ${
                  formatMoney(
                    region.transport_cost
                  )
                }; в еврофуре: ${
                  formatNumber(
                    region.quantity_eurotruck,
                    0,
                  )
                }`
              )
            }
          />

          <CalculationStep
            label="Себестоимость с логистикой"
            value={formatMoney(
              region.cost_with_logistics
            )}
            emphasized
          />

          <CalculationStep
            label="Минимальная цена"
            value={formatMoney(
              region.minimum_price
            )}
            note={
              `Минимальная маржа: ${
                formatPercent(
                  region.minimum_margin
                )
              }`
            }
          />

          <CalculationStep
            label={
              region.current_approval
                ? "Утверждённая РРЦ"
                : "Итоговая РРЦ по умолчанию"
            }
            value={formatMoney(
              effectiveRrp
            )}
            note={
              region.current_approval
                ? (
                    `Ручное утверждение, rev. ${
                      region.current_approval
                        .revision
                    }`
                  )
                : (
                    `Медиана конкурентов: ${
                      formatMoney(
                        region
                          .regional_competitor_rrp_median
                      )
                    }`
                  )
            }
            emphasized
          />
        </div>
      </section>

      <section className="iprice-region-details__section">
        <h4>
          Использованные коэффициенты
        </h4>

        <div className="iprice-region-details-grid">
          {region.pricing_method === "analog" && (
            <DetailItem
              label="Коэффициент к цене аналога"
              value={formatNumber(
                region.base_analog
              )}
            />
          )}

          {region.pricing_method === "exclusive" && (
            <DetailItem
              label="Базовая маржа эксклюзива"
              value={formatPercent(
                region.base_exclusive
              )}
            />
          )}

          <DetailItem
            label="Минимальная допустимая маржа"
            value={formatPercent(
              region.minimum_margin
            )}
          />

          <DetailItem
            label="Текущая маржа"
            value={formatPercent(
              region.margin_current
            )}
          />

          <DetailItem
            label="Расчётная маржа"
            value={formatPercent(
              region.effective_margin_calculated
              ?? region.margin_calculated
            )}
            previous={
              region.previous_effective_margin_calculated
                !== null
              && region.previous_effective_margin_calculated
                !== undefined
              && Number(
                region.previous_effective_margin_calculated
              ) !== Number(
                region.effective_margin_calculated
                ?? region.margin_calculated
              )
                ? formatPercent(
                    region
                      .previous_effective_margin_calculated
                  )
                : null
            }
          />
        </div>
      </section>

      <section className="iprice-region-details__section">
        <h4>
          Скидки и производные цены
        </h4>

        <div className="iprice-region-discounts">
          <DiscountItem
            label="Дистрибьютор"
            discount={
              region.discount_distr
            }
            price={
              region.effective_distr
              ?? region.calculated_distr
            }
          />

          <DiscountItem
            label="Дистрибьютор 1"
            discount={
              region.discount_distr_1
            }
            price={
              region.effective_distr_1
              ?? region.calculated_distr_1
            }
          />

          <DiscountItem
            label="Малый опт"
            discount={
              region.discount_small
            }
            price={
              region.effective_small
              ?? region.calculated_small
            }
          />

          <DiscountItem
            label="Средний опт"
            discount={
              region.discount_medium
            }
            price={
              region.effective_medium
              ?? region.calculated_medium
            }
          />

          <DiscountItem
            label="Крупный опт"
            discount={
              region.discount_large
            }
            price={
              region.effective_large
              ?? region.calculated_large
            }
          />
        </div>
      </section>

      <section className="iprice-region-details__section">
        <h4>
          Конкуренты региона
        </h4>

        <p className="iprice-region-details__note">
          В расчёте региона учитываются только
          конкуренты, применимые к региону{" "}
          <strong>
            {region.sale_region || "—"}
          </strong>.
        </p>

        {regionalCompetitors.length === 0 ? (
          <div className="iprice-product-empty">
            Применимые конкуренты отсутствуют.
          </div>
        ) : (
          <div className="iprice-region-competitors">
            {regionalCompetitors.map(
              (competitor) => (
                <IPriceCompetitorCard
                  key={competitor.id}
                  competitor={competitor}
                  coefficient={region.base_analog}
                  showVariants={false}
                  selectionEditable={selectionEditable}
                  selectionBusy={selectionBusyKey === competitor.group_key}
                  onSelectionChange={(keys, mode) => onSelectionChange?.(
                    keys, mode, competitor.group_key
                  )}
                />
              )
            )}
          </div>
        )}
      </section>

      <IssuesBlock
        title="Ошибки расчёта"
        codes={region.error_codes}
        type="error"
      />

      <IssuesBlock
        title="Предупреждения"
        codes={region.warning_codes}
        type="warning"
      />

    </div>
  );
}
