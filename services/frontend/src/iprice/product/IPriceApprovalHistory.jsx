import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getIPriceRegionApprovalHistory,
} from "../api/ipriceApi";


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


function formatDateTime(value) {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat(
    "ru-RU",
    {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    },
  ).format(date);
}


function ApprovalPrices({
  approval,
}) {
  return (
    <div className="iprice-approval-history__prices">
      <div>
        <span>
          РРЦ
        </span>

        <strong>
          {formatMoney(
            approval.approved_rrp
          )}
        </strong>
      </div>

      <div>
        <span>
          Дистрибьютор
        </span>

        <strong>
          {formatMoney(
            approval.approved_distr
          )}
        </strong>
      </div>

      <div>
        <span>
          Дистрибьютор 1
        </span>

        <strong>
          {formatMoney(
            approval.approved_distr_1
          )}
        </strong>
      </div>

      <div>
        <span>
          Малый опт
        </span>

        <strong>
          {formatMoney(
            approval.approved_small
          )}
        </strong>
      </div>

      <div>
        <span>
          Средний опт
        </span>

        <strong>
          {formatMoney(
            approval.approved_medium
          )}
        </strong>
      </div>

      <div>
        <span>
          Крупный опт
        </span>

        <strong>
          {formatMoney(
            approval.approved_large
          )}
        </strong>
      </div>
    </div>
  );
}


export function IPriceApprovalHistory({
  snapshotId,
  regionId,
  refreshKey = 0,
}) {
  const [
    approvals,
    setApprovals,
  ] = useState([]);

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");


  const loadHistory = useCallback(
    async () => {
      if (
        !snapshotId
        || !regionId
      ) {
        setApprovals([]);
        return;
      }

      setLoading(true);
      setError("");

      try {
        const result = (
          await getIPriceRegionApprovalHistory(
            snapshotId,
            regionId,
          )
        );

        setApprovals(
          result.approvals
        );
      } catch (requestError) {
        setError(
          requestError.response
            ?.data?.message
          || requestError.response
            ?.data?.detail
          || (
            "Не удалось загрузить "
            + "историю утверждений."
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [
      snapshotId,
      regionId,
    ],
  );


  useEffect(() => {
    loadHistory();
  }, [
    loadHistory,
    refreshKey,
  ]);


  if (loading) {
    return (
      <div className="iprice-approval-history__state">
        Загрузка истории...
      </div>
    );
  }


  if (error) {
    return (
      <div className="iprice-inline-error">
        <span>
          {error}
        </span>

        <button
          type="button"
          onClick={loadHistory}
        >
          Повторить
        </button>
      </div>
    );
  }


  if (approvals.length === 0) {
    return (
      <div className="iprice-approval-history__state">
        Ручные утверждения для этой строки
        отсутствуют.
      </div>
    );
  }


  return (
    <div className="iprice-approval-history">
      <h4>
        История утверждений
      </h4>

      <div className="iprice-approval-history__list">
        {approvals.map((approval) => (
          <article
            key={approval.id}
            className={[
              "iprice-approval-history__item",
              approval.is_current
                ? (
                    "iprice-approval-history"
                    + "__item--current"
                  )
                : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <div className="iprice-approval-history__header">
              <div>
                <strong>
                  Ревизия {approval.revision}
                </strong>

                {approval.is_current && (
                  <span>
                    Текущая
                  </span>
                )}
              </div>

              <div>
                <span>
                  {approval
                    .approved_by_username
                    || "—"}
                </span>

                <span>
                  {formatDateTime(
                    approval.approved_at
                  )}
                </span>
              </div>
            </div>

            <ApprovalPrices
              approval={approval}
            />

            {approval.comment && (
              <div className="iprice-approval-history__comment">
                <span>
                  Комментарий
                </span>

                <p>
                  {approval.comment}
                </p>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}