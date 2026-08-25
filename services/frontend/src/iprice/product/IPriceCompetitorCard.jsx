import {
  IPriceProductImage,
} from "../components/IPriceProductImage";
import {
  getIPriceCompetitorPriceProperties,
  getIPriceCompetitorSourceLabel,
} from "./ipriceProductLabels";
import {IPriceColorSwatch} from "./IPriceColorSwatch";


function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("ru-RU", {
        maximumFractionDigits: digits,
      })
    : String(value);
}


function formatMoney(value) {
  return value === null || value === undefined || value === ""
    ? "—"
    : `${formatNumber(value, 0)} ₽`;
}


export function IPriceCompetitorCard({
  competitor,
  selectionEditable = false,
  selectionBusy = false,
  onSelectionChange,
}) {
  const variants = Array.isArray(
    competitor?.price_variants
  )
    ? competitor.price_variants
    : [];
  const image = variants.find(
    (variant) => variant.image
  )?.image || competitor?.image;
  const snapshotRegionalEntries = Array.isArray(
    competitor?.regional_entries,
  ) ? competitor.regional_entries : [];
  const variantRows = variants.flatMap((variant) => {
    const regions = Array.isArray(variant.regions) && variant.regions.length
      ? variant.regions
      : Array.isArray(competitor?.applicable_regions) && competitor.applicable_regions.length
        ? competitor.applicable_regions
        : ["Регион не определён"];
    return regions.map((region) => ({
      key: `${variant.id || variant.url || competitor?.id}|${region}`,
      region,
      productKey: variant.product_key ?? competitor?.competitor_product_key,
      price: variant.final_price ?? variant.price,
      url: variant.url || competitor?.url,
    }));
  });
  const regionalRows = (
    snapshotRegionalEntries.length
      ? snapshotRegionalEntries.map((entry) => ({
          key: `${entry.product_key}|${entry.region}`,
          region: entry.region,
          productKey: entry.product_key,
          price: entry.price,
          url: entry.url,
        }))
      : variantRows.length
      ? variantRows
      : (
          Array.isArray(competitor?.applicable_regions)
          && competitor.applicable_regions.length
            ? competitor.applicable_regions
            : ["Регион не определён"]
        ).map((region) => ({
          key: `${competitor?.id || competitor?.competitor_product_key}|${region}`,
          region,
          productKey: competitor?.competitor_product_key,
          price: competitor?.competitor_final_price_max,
          url: competitor?.url,
        }))
  ).sort((left, right) => left.region.localeCompare(right.region, "ru"));
  const prices = regionalRows
    .map((row) => row.price)
    .filter((price) => price !== null && price !== undefined && price !== "")
    .map(Number)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  const middle = Math.floor(prices.length / 2);
  const medianPrice = competitor?.competitor_final_price_median ?? (prices.length
    ? (prices.length % 2 ? prices[middle] : (prices[middle - 1] + prices[middle]) / 2)
    : competitor?.competitor_final_price_max);
  const priceProperties = getIPriceCompetitorPriceProperties(
    competitor?.source,
    variants,
  );
  return (
    <article className="iprice-market-card">
      <IPriceProductImage
        src={image}
        alt={variants[0]?.name}
        caption={variants[0]?.name}
        className="iprice-product-drawer__image"
        placeholderClassName="iprice-product-drawer__image-placeholder"
        placeholderText="Нет изображения"
      />

      <div className="iprice-market-card__body">
        <div className="iprice-market-card__header">
          <strong>{getIPriceCompetitorSourceLabel(competitor?.source)}</strong>
        </div>
        <details className="iprice-market-price-details">
          <summary className="iprice-market-card__price">
            <span>Медиана рынка</span>
            <strong>{formatMoney(medianPrice)}</strong>
          </summary>
          <div className="iprice-market-price-details__rows">
            {regionalRows.length ? regionalRows.map((row) => (
              <div key={row.key} className="iprice-market-price-details__row">
                <span>{row.region} · {row.productKey ?? competitor?.competitor_product_key ?? "—"}</span>
                <strong>{formatMoney(row.price)}</strong>
                {row.url ? <a href={row.url} target="_blank" rel="noreferrer">Открыть товар</a> : <span>Ссылка отсутствует</span>}
              </div>
            )) : <div className="iprice-market-price-details__empty">Региональные цены отсутствуют.</div>}
          </div>
        </details>
        <div className="iprice-market-card__properties">
          <span>
            Материал iPrice: {competitor?.material || "—"}
          </span>
          <span className="iprice-market-card__property-row">
            Цвет iPrice: <IPriceColorSwatch color={competitor?.color} />
          </span>
          <span>
            Модификация iPrice: {competitor?.modification || "—"}
          </span>
          {competitor?.article_number_analogs && (
            <span className="iprice-market-card__description">
              {competitor.article_number_analogs}
            </span>
          )}
          {competitor?.additional_property && (
            <span>
              Вариант товара: {competitor.additional_property}
            </span>
          )}
          {priceProperties.map((property) => (
            <span key={`${property.label}|${property.value}`}>
              {property.label}: {property.value}
            </span>
          ))}
        </div>
        {competitor?.is_price_used_in_calculation === false && (
          <div className="iprice-market-card__flags">
            <span className="iprice-market-card__flag--warning">
              Цена аналога отсутствует — эта цена не используется
            </span>
          </div>
        )}
        {onSelectionChange && (
          <div className="iprice-market-card__actions">
            <button
              type="button"
              className="iprice-table-action"
              disabled={!selectionEditable || selectionBusy}
              title={!selectionEditable
                ? "Состав конкурентов зафиксирован для этого снапшота"
                : "Исключить конкурента и пересчитать цены"}
              onClick={() => onSelectionChange(
                competitor?.competitor_product_keys
                  || [competitor?.competitor_product_key],
                "exclude",
              )}
            >
              {selectionBusy
                ? "Пересчёт…"
                : "Исключить из расчёта"}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
