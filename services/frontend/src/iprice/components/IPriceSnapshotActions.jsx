import {
  useState,
} from "react";


function getLocalDateInputValue() {
  const now = new Date();

  const year = now.getFullYear();
  const month = String(
    now.getMonth() + 1
  ).padStart(2, "0");

  const day = String(
    now.getDate()
  ).padStart(2, "0");

  return `${year}-${month}-${day}`;
}


export function IPriceSnapshotActions({
  canEdit = false,
  snapshot,
  running,
  activating,
  exporting,
  onRun,
  onActivate,
  onDeactivate,
  onExport,
}) {
  const [
    runDialogOpen,
    setRunDialogOpen,
  ] = useState(false);

  const [
    activateDialogOpen,
    setActivateDialogOpen,
  ] = useState(false);

  const [
    calculationDate,
    setCalculationDate,
  ] = useState(
    getLocalDateInputValue()
  );


  const anyActionRunning = (
    running
    || activating
    || exporting
  );

  const canToggleActivation = Boolean(
    snapshot
    && snapshot.status === "success"
    && (
      snapshot.is_active
      || snapshot.is_current
    )
  );

  const canExport = Boolean(
    snapshot
    && snapshot.status === "success"
  );


  async function submitRun(
    event,
  ) {
    event.preventDefault();

    const started = await onRun(
      calculationDate
    );

    if (started) {
      setRunDialogOpen(false);
    }
  }


  async function submitActivation() {
    const changed = snapshot?.is_active
      ? await onDeactivate()
      : await onActivate();

    if (changed) {
      setActivateDialogOpen(false);
    }
  }


  return (
    <>
      <div className="iprice-snapshot-actions">
        <button
          type="button"
          className="iprice-action-button iprice-action-button--primary"
          disabled={
            !canEdit
            || anyActionRunning
          }
          onClick={() => {
            setRunDialogOpen(true);
          }}
        >
          {running
            ? "Запуск…"
            : "Сделать расчёт"}
        </button>

        <button
          type="button"
          className="iprice-action-button"
          disabled={
            anyActionRunning
            || !canEdit
            || !canToggleActivation
          }
          title={
            snapshot?.status !== "success"
              ? (
                  "Активировать можно только "
                  + "успешно рассчитанную версию"
                )
              : (
                  !snapshot?.is_active
                  && !snapshot?.is_current
                    ? (
                        "Активировать можно только текущую "
                        + "ревизию выбранной даты"
                      )
                    : ""
                )
          }
          onClick={() => {
            setActivateDialogOpen(true);
          }}
        >
          {activating
            ? (snapshot?.is_active ? "Деактивация…" : "Активация…")
            : (snapshot?.is_active ? "Деактивировать" : "Активировать")}
        </button>

        <button
          type="button"
          className="iprice-action-button"
          disabled={
            anyActionRunning
            || !canExport
          }
          title={
            !canExport
              ? (
                  "Экспорт доступен только "
                  + "для успешно рассчитанной версии"
                )
              : ""
          }
          onClick={() => onExport()}
        >
          {exporting
            ? "Формирование файла…"
            : "Экспорт"}
        </button>
      </div>

      {runDialogOpen && (
        <div
          className="iprice-modal-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (
              event.target
              === event.currentTarget
              && !running
            ) {
              setRunDialogOpen(false);
            }
          }}
        >
          <div
            className="iprice-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="iprice_run_title"
          >
            <h2 id="iprice_run_title">
              Сделать расчёт
            </h2>

            <p>
              Будет создана новая техническая
              версия расчёта iPrice.
            </p>

            <form onSubmit={submitRun}>
              <label
                htmlFor="iprice_calculation_date"
              >
                Дата расчёта
              </label>

              <input
                id="iprice_calculation_date"
                type="date"
                value={calculationDate}
                max={getLocalDateInputValue()}
                required
                disabled={running}
                onChange={(event) => {
                  setCalculationDate(
                    event.target.value
                  );
                }}
              />

              <div className="iprice-modal-actions">
                <button
                  type="button"
                  className="iprice-action-button"
                  disabled={running}
                  onClick={() => {
                    setRunDialogOpen(false);
                  }}
                >
                  Отмена
                </button>

                <button
                  type="submit"
                  className={[
                    "iprice-action-button",
                    "iprice-action-button--primary",
                  ].join(" ")}
                  disabled={
                    running
                    || !calculationDate
                  }
                >
                  {running
                    ? "Запуск…"
                    : "Запустить расчёт"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {activateDialogOpen && snapshot && (
        <div
          className="iprice-modal-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (
              event.target
              === event.currentTarget
              && !activating
            ) {
              setActivateDialogOpen(false);
            }
          }}
        >
          <div
            className="iprice-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={
              "iprice_activate_title"
            }
          >
            <h2 id="iprice_activate_title">
              {snapshot.is_active
                ? "Деактивировать версию?"
                : "Активировать версию"}
            </h2>

            <p>
              Версия{" "}
              <strong>
                {snapshot.display_version}
              </strong>{" "}
              {snapshot.is_active
                ? "перестанет быть активным окончательным расчётом."
                : "станет единственным активным окончательным расчётом."}
            </p>

            {snapshot.is_active ? (
              <p className="iprice-modal-note">
                Если это последняя успешная версия,
                настройки ценообразования снова станут доступны.
                Для более ранних версий ограничение сохранится.
              </p>
            ) : (
              <>
                <p className="iprice-modal-note">
                  Предыдущая активная версия
                  сохранится в истории, но потеряет
                  признак активной.
                </p>

                <p className="iprice-modal-note iprice-modal-note--warning">
                  После активации версия станет окончательной.
                  Настройки ценообразования будут заблокированы,
                  изменить коэффициенты и скидки в этой версии
                  будет нельзя.
                </p>
              </>
            )}

            <div className="iprice-modal-actions">
              <button
                type="button"
                className="iprice-action-button"
                disabled={activating}
                onClick={() => {
                  setActivateDialogOpen(false);
                }}
              >
                Отмена
              </button>

              <button
                type="button"
                className={[
                  "iprice-action-button",
                  "iprice-action-button--primary",
                ].join(" ")}
                disabled={activating}
                onClick={submitActivation}
              >
                {activating
                  ? (snapshot.is_active ? "Деактивация…" : "Активация…")
                  : (snapshot.is_active ? "Деактивировать" : "Подтвердить")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
