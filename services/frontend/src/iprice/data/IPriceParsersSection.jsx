import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getParserMasterRunStatus,
  runParserMasterPipeline,
} from "../api/ipriceApi";
import { TaraWorkerPanel } from './TaraWorkerPanel';


const ACTIVE_STATUSES = new Set([
  "queued",
  "running",
  "waiting_tara",
  "waiting_session",
]);


const STATUS_LABELS = {
  waiting_tara: 'Выполняется этап Тары',
  waiting_session: 'Ожидается Windows-исполнитель Тары',
  cancelled: 'Отменён',
  queued: "В очереди",
  running: "Выполняется",
  success: "Завершён",
  failed: "Ошибка",
};


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
      second: "2-digit",
    },
  ).format(date);
}


function getErrorMessage(error) {
  return (
    error?.response?.data?.message
    || error?.response?.data?.detail
    || error?.message
    || "Не удалось выполнить операцию."
  );
}


function getRunDuration(run) {
  if (!run?.started_at) {
    return "—";
  }

  const startedAt = new Date(
    run.started_at,
  );

  const finishedAt = run.finished_at
    ? new Date(run.finished_at)
    : new Date();

  if (
    Number.isNaN(startedAt.getTime())
    || Number.isNaN(
      finishedAt.getTime()
    )
  ) {
    return "—";
  }

  const seconds = Math.max(
    0,
    Math.floor(
      (
        finishedAt.getTime()
        - startedAt.getTime()
      )
      / 1000,
    ),
  );

  const hours = Math.floor(
    seconds / 3600,
  );

  const minutes = Math.floor(
    (seconds % 3600) / 60,
  );

  const remainingSeconds = (
    seconds % 60
  );

  const parts = [];

  if (hours > 0) {
    parts.push(`${hours} ч`);
  }

  if (
    minutes > 0
    || hours > 0
  ) {
    parts.push(`${minutes} мин`);
  }

  parts.push(
    `${remainingSeconds} сек`,
  );

  return parts.join(" ");
}


export function IPriceParsersSection({
  canEdit = false,
  realtimeEvent,
}) {
  const [
    activeRun,
    setActiveRun,
  ] = useState(null);

  const [
    latestRun,
    setLatestRun,
  ] = useState(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    starting,
    setStarting,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    message,
    setMessage,
  ] = useState("");


  const displayedRun = (
    activeRun
    || latestRun
  );


  const pipelineRunning = Boolean(
    activeRun
    && ACTIVE_STATUSES.has(
      activeRun.status,
    )
  );


  const loadStatus = useCallback(
    async ({
      silent = false,
    } = {}) => {
      if (!silent) {
        setLoading(true);
      }

      try {
        const response = (
          await getParserMasterRunStatus()
        );

        setActiveRun(
          response.activeRun,
        );

        setLatestRun(
          response.latestRun,
        );

        setError("");
      } catch (requestError) {
        setError(
          getErrorMessage(
            requestError,
          ),
        );
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [],
  );


  useEffect(() => {
    loadStatus();
    const timer = setInterval(() => loadStatus({ silent: true }), 15000);
    return () => clearInterval(timer);
  }, [
    loadStatus,
  ]);


  useEffect(() => {
    if (
      String(realtimeEvent?.change_type || "")
        .startsWith("parser_")
    ) {
      loadStatus({ silent: true });
    }
  }, [realtimeEvent, loadStatus]);




  async function handleRun() {
    setStarting(true);
    setError("");
    setMessage("");

    try {
      const response = (
        await runParserMasterPipeline()
      );

      setMessage(
        response.message
        || "Парсеры запущены.",
      );

      if (response.run) {
        setActiveRun(
          response.run,
        );

        setLatestRun(
          response.run,
        );
      }

      await loadStatus({
        silent: true,
      });
    } catch (requestError) {
      const responseRun = (
        requestError
          ?.response
          ?.data
          ?.run
        || null
      );

      if (responseRun) {
        setActiveRun(
          ACTIVE_STATUSES.has(
            responseRun.status,
          )
            ? responseRun
            : null,
        );

        setLatestRun(
          responseRun,
        );
      }

      setError(
        getErrorMessage(
          requestError,
        ),
      );
    } finally {
      setStarting(false);
    }
  }


  const statusLabel = (
    STATUS_LABELS[
      displayedRun?.status
    ]
    || displayedRun?.status
    || "Запусков ещё не было"
  );

  const resultLabel = (
    displayedRun?.status === "success"
      ? "Успешно"
      : displayedRun?.status === "failed"
        ? "Неуспешно"
        : ACTIVE_STATUSES.has(
            displayedRun?.status
          )
          ? "В процессе"
          : "—"
  );


  return (
    <section className="iprice-parsers">
      <TaraWorkerPanel canEdit={canEdit} />
      <div className="iprice-data-section-header">
        <div>
          <p>
            Запуск процесса обновления
            <b> классифицированных</b> товаров конкурентов.
          </p>
        </div>

        <button
          type="button"
          className="iprice-parser-run-button"
          disabled={
            !canEdit
            || loading
            || starting
            || pipelineRunning
          }
          onClick={handleRun}
        >
          {starting
            ? "Запуск..."
            : (
                pipelineRunning
                  ? "Парсеры выполняются"
                  : "Запустить парсеры"
              )}
        </button>
      </div>

      {error && (
        <div className="iprice-data-operation-error">
          {error}
        </div>
      )}

      {message && (
        <div className="iprice-data-operation-success">
          {message}
        </div>
      )}

      {loading ? (
        <div className="iprice-parser-loading">
          <div className="iprice-table-loading">
            <div className="iprice-table-loading__spinner" />
            <span>Загрузка данных...</span>
          </div>
        </div>
      ) : (
      <section className="iprice-parser-status">
        <div className="iprice-parser-status__header">
          <div>
            <h3>
              Последний запуск
            </h3>

            <span
              className={[
                "iprice-parser-status-badge",
                displayedRun?.status
                  ? (
                      "iprice-parser-status-badge"
                      + `--${displayedRun.status}`
                    )
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {statusLabel}
            </span>
          </div>

        </div>

        {displayedRun ? (
          <dl className="iprice-parser-status__details">
            <div>
              <dt>
                Статус
              </dt>

              <dd>
                {resultLabel}
              </dd>
            </div>

            <div>
              <dt>
                Запустил
              </dt>

              <dd>
                {
                  displayedRun.started_by
                  || "—"
                }
              </dd>
            </div>

            <div>
              <dt>
                Начат
              </dt>

              <dd>
                {formatDateTime(
                  displayedRun.started_at,
                )}
              </dd>
            </div>

            <div>
              <dt>
                Завершён
              </dt>

              <dd>
                {formatDateTime(
                  displayedRun.finished_at,
                )}
              </dd>
            </div>

            <div>
              <dt>
                Длительность
              </dt>

              <dd>
                {getRunDuration(
                  displayedRun,
                )}
              </dd>
            </div>
          </dl>
        ) : (
          <div className="iprice-data-placeholder">
            Запусков парсеров ещё не было.
          </div>
        )}

        {displayedRun?.error && (
          <div className="iprice-data-operation-error">
            {displayedRun.error}
          </div>
        )}

      </section>
      )}
    </section>
  );
}
