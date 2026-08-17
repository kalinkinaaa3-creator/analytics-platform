import {
  useState,
} from "react";


const FIELDS = [
  ["below_market_percent", "Ниже рынка до, %"],
  ["above_market_percent", "В рынке до, %"],
  ["critical_percent", "Критически выше от, %"],
];


export function IPricePriceZoneDialog({
  open,
  config,
  saving = false,
  error = "",
  onClose,
  onSave,
}) {
  const [values, setValues] = useState(() => ({
    below_market_percent: config?.below_market_percent ?? -3,
    above_market_percent: config?.above_market_percent ?? 3,
    critical_percent: config?.critical_percent ?? 10,
  }));

  if (!open) {
    return null;
  }

  return (
    <div
      className="iprice-analytics-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) {
          onClose?.();
        }
      }}
    >
      <section
        className="iprice-analytics-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="iprice-price-zones-title"
      >
        <div className="iprice-analytics-dialog__header">
          <div>
            <h3 id="iprice-price-zones-title">Ценовые зоны</h3>
            <p>Пороговые значения отклонения итоговой РРЦ от рынка.</p>
          </div>

          <button
            type="button"
            className="iprice-analytics-dialog__close"
            aria-label="Закрыть"
            title="Закрыть"
            disabled={saving}
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="iprice-analytics-dialog__fields">
          {FIELDS.map(([name, label]) => (
            <label key={name}>
              <span>{label}</span>
              <input
                type="number"
                step="0.1"
                value={values[name] ?? ""}
                disabled={saving}
                onChange={(event) => {
                  setValues((previous) => ({
                    ...previous,
                    [name]: event.target.value,
                  }));
                }}
              />
            </label>
          ))}
        </div>

        <div className="iprice-analytics-zone-preview">
          <span>Ниже рынка</span>
          <span>В рынке</span>
          <span>Выше рынка</span>
          <span>Критически выше</span>
        </div>

        {error && (
          <div className="iprice-inline-error">{error}</div>
        )}

        <div className="iprice-analytics-dialog__actions">
          <button
            type="button"
            className="iprice-analytics-button iprice-analytics-button--secondary"
            disabled={saving}
            onClick={onClose}
          >
            Отмена
          </button>
          <button
            type="button"
            className="iprice-analytics-button"
            disabled={saving}
            onClick={() => onSave?.({
              below_market_percent: Number(values.below_market_percent),
              above_market_percent: Number(values.above_market_percent),
              critical_percent: Number(values.critical_percent),
            })}
          >
            {saving ? "Сохранение…" : "Применить"}
          </button>
        </div>
      </section>
    </div>
  );
}
