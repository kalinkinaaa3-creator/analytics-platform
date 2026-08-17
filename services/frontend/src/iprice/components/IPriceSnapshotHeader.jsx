import {
  IPriceSnapshotActions,
} from "./IPriceSnapshotActions";


function formatDate(
  value,
  {
    withTime = false,
  } = {},
) {
  if (!value) {
    return "—";
  }

  /*
   * Дата вида YYYY-MM-DD не должна проходить
   * через new Date(), иначе в некоторых часовых
   * поясах она может сместиться на предыдущий день.
   */
  if (
    !withTime
    && /^\d{4}-\d{2}-\d{2}$/.test(value)
  ) {
    const [
      year,
      month,
      day,
    ] = value.split("-");

    return `${day}.${month}.${year}`;
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  const options = withTime
    ? {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }
    : {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      };

  return new Intl.DateTimeFormat(
    "ru-RU",
    options,
  ).format(date);
}


function getSnapshotStatus(snapshot) {
  if (!snapshot) {
    return {
      label: "Версия не выбрана",
      className: "iprice-status--neutral",
    };
  }

  if (snapshot.status === "building") {
    return {
      label: "Выполняется",
      className: "iprice-status--building",
    };
  }

  if (snapshot.status === "failed") {
    return {
      label: "Ошибка расчёта",
      className: "iprice-status--error",
    };
  }

  if (snapshot.status === "success") {
    return {
      label: "Рассчитан",
      className: "iprice-status--success",
    };
  }

  return {
    label: (
      snapshot.status
      || "Неизвестно"
    ),
    className: "iprice-status--neutral",
  };
}


function SnapshotFlag({
  children,
  className = "",
}) {
  return (
    <span
      className={[
        "iprice-snapshot-flag",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </span>
  );
}


export function IPriceSnapshotHeader({
  canEdit = false,
  snapshots,
  selectedSnapshot,
  selectedSnapshotId,
  loading,
  running,
  activating,
  exporting,
  onSnapshotChange,
  onRun,
  onActivate,
  onDeactivate,
  onExport,
}) {
  const safeSnapshots = Array.isArray(
    snapshots
  )
    ? snapshots
    : [];

  const statusInfo = getSnapshotStatus(
    selectedSnapshot
  );

  return (
    <section className="iprice-snapshot-header">
      <div className="iprice-snapshot-header__toolbar">
        <div className="iprice-snapshot-header__selector">
          <label htmlFor="iprice_snapshot_select">
            Версия расчёта
          </label>

          <select
            id="iprice_snapshot_select"
            value={
              selectedSnapshotId || ""
            }
            disabled={
              loading
              || safeSnapshots.length === 0
            }
            onChange={(event) => {
              const value = event.target.value;

              onSnapshotChange(
                value
                  ? Number(value)
                  : null
              );
            }}
          >
            {safeSnapshots.length === 0 && (
              <option value="">
                Версии отсутствуют
              </option>
            )}

            {safeSnapshots.map(
              (snapshot) => (
                <option
                  key={snapshot.id}
                  value={snapshot.id}
                >
                  {snapshot.display_version}
                  {" – "}
                  {formatDate(
                    snapshot.calculation_date
                  )}
                  {snapshot.is_active
                    ? " – активная"
                    : snapshot.was_active
                      ? " – была активна"
                      : ""}
                  {snapshot.is_current
                    ? " – текущая"
                    : ""}
                </option>
              )
            )}
          </select>
        </div>

        <IPriceSnapshotActions
          canEdit={canEdit}
          snapshot={selectedSnapshot}
          running={running}
          activating={activating}
          exporting={exporting}
          onRun={onRun}
          onActivate={onActivate}
          onDeactivate={onDeactivate}
          onExport={onExport}
        />
      </div>

      {loading && (
        <div className="iprice-snapshot-header__loading">
          Загрузка версий…
        </div>
      )}

      {!loading && selectedSnapshot && (
        <>
          <div className="iprice-snapshot-header__main">
            <div className="iprice-snapshot-version">
              <span className="iprice-snapshot-version__label">
                Выбрана версия
              </span>

              <strong className="iprice-snapshot-version__value">
                {selectedSnapshot.display_version}
              </strong>
            </div>

            <div className="iprice-snapshot-flags">
              <SnapshotFlag
                className={
                  statusInfo.className
                }
              >
                {statusInfo.label}
              </SnapshotFlag>

              {selectedSnapshot.is_active && (
                <SnapshotFlag className="iprice-flag--active">
                  Активный окончательный
                </SnapshotFlag>
              )}

              {selectedSnapshot.is_current && (
                <SnapshotFlag className="iprice-flag--current">
                  Текущая версия даты
                </SnapshotFlag>
              )}

              {selectedSnapshot.is_latest && (
                <SnapshotFlag className="iprice-flag--latest">
                  Последний расчёт
                </SnapshotFlag>
              )}
            </div>
          </div>

          <div className="iprice-snapshot-header__details">
            <div className="iprice-snapshot-detail">
              <span>Дата расчёта</span>

              <strong>
                {formatDate(
                  selectedSnapshot
                    .calculation_date
                )}
              </strong>
            </div>

            <div className="iprice-snapshot-detail">
              <span>Товаров</span>

              <strong>
                {selectedSnapshot
                  .products_count ?? 0}
              </strong>
            </div>

            <div className="iprice-snapshot-detail">
              <span>Региональных строк</span>

              <strong>
                {selectedSnapshot
                  .regions_count ?? 0}
              </strong>
            </div>

            <div className="iprice-snapshot-detail">
              <span>Строк с ошибкой</span>

              <strong>
                {selectedSnapshot
                  .errors_count ?? 0}
              </strong>
            </div>

            <div className="iprice-snapshot-detail">
              <span>Создан</span>

              <strong>
                {formatDate(
                  selectedSnapshot.created_at,
                  {
                    withTime: true,
                  }
                )}
              </strong>
            </div>

            <div className="iprice-snapshot-detail">
              <span>Создал</span>

              <strong>
                {selectedSnapshot
                  .created_by_username || "—"}
              </strong>
            </div>

            {selectedSnapshot.finished_at && (
              <div className="iprice-snapshot-detail">
                <span>Завершён</span>

                <strong>
                  {formatDate(
                    selectedSnapshot.finished_at,
                    {
                      withTime: true,
                    }
                  )}
                </strong>
              </div>
            )}

            {selectedSnapshot.activated_at && (
              <div className="iprice-snapshot-detail">
                <span>Активирован</span>

                <strong>
                  {formatDate(
                    selectedSnapshot.activated_at,
                    {
                      withTime: true,
                    }
                  )}
                </strong>
              </div>
            )}

            {selectedSnapshot
              .activated_by_username && (
              <div className="iprice-snapshot-detail">
                <span>Активировал</span>

                <strong>
                  {selectedSnapshot
                    .activated_by_username}
                </strong>
              </div>
            )}
          </div>

          {selectedSnapshot.status === "failed"
            && selectedSnapshot.error && (
              <div className="iprice-snapshot-error">
                <strong>
                  Ошибка расчёта:
                </strong>

                <span>
                  {selectedSnapshot.error}
                </span>
              </div>
            )}
        </>
      )}

      {!loading
        && safeSnapshots.length === 0 && (
          <div className="iprice-snapshot-empty">
            Расчёты iPrice ещё не выполнены.
          </div>
        )}
    </section>
  );
}
