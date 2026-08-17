import {
  useMemo,
  useState,
} from "react";

import {
  saveIPriceRegionApproval,
} from "../api/ipriceApi";


function normalizeDecimal(value) {
  if (
    value === null
    || value === undefined
  ) {
    return "";
  }

  return String(value)
    .trim()
    .replace(/\s+/g, "")
    .replace(",", ".");
}


function parsePositiveNumber(value) {
  const normalizedValue = (
    normalizeDecimal(value)
  );

  if (!normalizedValue) {
    return null;
  }

  const number = Number(
    normalizedValue
  );

  if (
    !Number.isFinite(number)
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


function formatEditableMoney(value) {
  const number = Number(
    normalizeDecimal(value)
  );

  if (!Number.isFinite(number)) {
    return value === null || value === undefined
      ? ""
      : String(value);
  }

  return number.toLocaleString(
    "ru-RU",
    {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: true,
    },
  );
}


function calculateDiscountPrice(
  rrp,
  discount,
) {
  const normalizedRrp = Number(rrp);
  const normalizedDiscount = Number(
    discount
  );

  if (
    !Number.isFinite(normalizedRrp)
    || !Number.isFinite(
      normalizedDiscount
    )
    || normalizedDiscount < 0
    || normalizedDiscount >= 1
  ) {
    return null;
  }

  return (
    normalizedRrp
    * (
      1 - normalizedDiscount
    )
  );
}


function PreviewPrice({
  label,
  value,
  discount,
}) {
  return (
    <div className="iprice-approval-preview__item">
      <span>
        {label}
      </span>

      <small>
        {Number.isFinite(Number(discount))
          ? `${formatNumber(Number(discount) * 100)}%`
          : "—"}
      </small>

      <strong>
        {formatMoney(value)}
      </strong>
    </div>
  );
}


export function IPriceApprovalEditor({
  snapshotId,
  snapshotIsCurrent,
  region,
  onSaved,
  onCancel,
}) {
  const initialRrp = (
    region.current_approval
      ?.approved_rrp
    ?? region.effective_approved_rrp
    ?? region.default_approved_rrp
    ?? region.calculated_rrp
    ?? ""
  );

  const [
    approvedRrp,
    setApprovedRrp,
  ] = useState(
    initialRrp === ""
      ? ""
      : formatEditableMoney(initialRrp)
  );

  const [
    comment,
    setComment,
  ] = useState("");

  const [
    saving,
    setSaving,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");


  const numericRrp = useMemo(
    () => parsePositiveNumber(
      approvedRrp
    ),
    [approvedRrp],
  );


  const preview = useMemo(
    () => ({
      distr: calculateDiscountPrice(
        numericRrp,
        region.discount_distr,
      ),

      distr1: calculateDiscountPrice(
        numericRrp,
        region.discount_distr_1,
      ),

      small: calculateDiscountPrice(
        numericRrp,
        region.discount_small,
      ),

      medium: calculateDiscountPrice(
        numericRrp,
        region.discount_medium,
      ),

      large: calculateDiscountPrice(
        numericRrp,
        region.discount_large,
      ),
    }),
    [
      numericRrp,
      region.discount_distr,
      region.discount_distr_1,
      region.discount_small,
      region.discount_medium,
      region.discount_large,
    ],
  );


  const canApprove = Boolean(
    snapshotId
    && snapshotIsCurrent
    && region.calculation_status
      === "success"
  );


  async function handleSubmit(event) {
    event.preventDefault();

    if (!canApprove) {
      setError(
        "Утверждать цену можно только "
        + "в текущей успешной версии расчёта."
      );

      return;
    }

    if (numericRrp === null) {
      setError(
        "Утверждённая РРЦ должна быть "
        + "числом больше нуля."
      );

      return;
    }

    setSaving(true);
    setError("");

    try {
      const result = (
        await saveIPriceRegionApproval(
          snapshotId,
          region.id,
          {
            approvedRrp: normalizeDecimal(
              approvedRrp
            ),
            comment: comment.trim(),
          },
        )
      );

      onSaved?.({
        regionId: region.id,
        approval: result.approval,
        message: (
          result.message
          || "Утверждённая цена сохранена."
        ),
      });
    } catch (requestError) {
      setError(
        requestError.response
          ?.data?.message
        || requestError.response
          ?.data?.detail
        || (
          "Не удалось сохранить "
          + "утверждённую цену."
        )
      );
    } finally {
      setSaving(false);
    }
  }


  return (
    <form
      className="iprice-approval-editor"
      onSubmit={handleSubmit}
    >
      <div className="iprice-approval-editor__header">
        <div>
          <h3>
            Утверждение РРЦ
          </h3>

          <p>
            {region.sale_region || "—"}
            {" / "}
            {region.departure || "—"}
          </p>
        </div>

        {region.current_approval && (
          <span>
            Текущая ревизия:{" "}
            {
              region.current_approval
                .revision
            }
          </span>
        )}
      </div>

      {!snapshotIsCurrent && (
        <div className="iprice-approval-editor__warning">
          Это не текущая техническая версия
          выбранной даты. Сохранение новой
          утверждённой цены запрещено.
        </div>
      )}

      {region.calculation_status
        !== "success" && (
        <div className="iprice-approval-editor__warning">
          Региональная строка рассчитана
          с ошибкой или предупреждением.
          Утверждение недоступно.
        </div>
      )}

      <div className="iprice-approval-editor__field">
        <label
          htmlFor={
            `iprice_approved_rrp_`
            + region.id
          }
        >
          Утверждённая РРЦ
        </label>

        <input
          id={
            `iprice_approved_rrp_`
            + region.id
          }
          type="text"
          inputMode="decimal"
          value={approvedRrp}
          disabled={
            saving
            || !canApprove
          }
          placeholder="Например, 12500"
          onChange={(event) => {
            setApprovedRrp(
              event.target.value
            );

            setError("");
          }}
          onFocus={() => {
            if (numericRrp !== null) {
              setApprovedRrp(
                String(numericRrp).replace(".", ",")
              );
            }
          }}
          onBlur={() => {
            if (numericRrp !== null) {
              setApprovedRrp(
                formatEditableMoney(numericRrp)
              );
            }
          }}
        />
      </div>

      <div className="iprice-approval-editor__comparison">
        <div>
          <span>
            Расчётная РРЦ
          </span>

          <strong>
            {formatMoney(
              region.calculated_rrp
            )}
          </strong>
        </div>

        <div>
          <span>
            Итоговая РРЦ
          </span>

          <strong>
            {formatMoney(
              region.effective_approved_rrp
            )}
          </strong>
        </div>
      </div>

      <div className="iprice-approval-preview">
        <h4>
          Производные цены после сохранения
        </h4>

        <div className="iprice-approval-preview__grid">
          <PreviewPrice
            label="Дистрибьютор"
            value={preview.distr}
            discount={region.discount_distr}
          />

          <PreviewPrice
            label="Дистрибьютор 1"
            value={preview.distr1}
            discount={region.discount_distr_1}
          />

          <PreviewPrice
            label="Малый опт"
            value={preview.small}
            discount={region.discount_small}
          />

          <PreviewPrice
            label="Средний опт"
            value={preview.medium}
            discount={region.discount_medium}
          />

          <PreviewPrice
            label="Крупный опт"
            value={preview.large}
            discount={region.discount_large}
          />
        </div>
      </div>

      <div className="iprice-approval-editor__field">
        <label
          htmlFor={
            `iprice_approval_comment_`
            + region.id
          }
        >
          Комментарий
        </label>

        <textarea
          id={
            `iprice_approval_comment_`
            + region.id
          }
          rows={3}
          value={comment}
          disabled={
            saving
            || !canApprove
          }
          placeholder={
            "Причина изменения цены "
            + "или дополнительная информация"
          }
          onChange={(event) => {
            setComment(
              event.target.value
            );
          }}
        />
      </div>

      {error && (
        <div className="iprice-inline-error">
          {error}
        </div>
      )}

      <div className="iprice-approval-editor__actions">
        <button
          type="button"
          disabled={saving}
          onClick={onCancel}
        >
          Отмена
        </button>

        <button
          type="submit"
          disabled={
            saving
            || !canApprove
            || numericRrp === null
          }
        >
          {saving
            ? "Сохранение..."
            : "Утвердить цену"}
        </button>
      </div>
    </form>
  );
}
