import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getIPriceHealth,
} from "../api/ipriceApi";


const LEVEL_ALL = "all";
const LEVEL_ERROR = "ERROR";
const LEVEL_WARNING = "WARNING";


function formatNumber(
  value,
  maximumFractionDigits = 0,
) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "0";
  }

  return number.toLocaleString(
    "ru-RU",
    {
      maximumFractionDigits,
    },
  );
}


function getErrorMessage(error) {
  return (
    error?.response?.data?.detail
    || error?.response?.data?.error
    || error?.response?.data?.message
    || error?.message
    || "Не удалось выполнить контроль данных."
  );
}


function normalizeArray(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  const result = [];
  const seen = new Set();

  values.forEach((value) => {
    const normalizedValue = String(
      value ?? ""
    ).trim();

    if (!normalizedValue) {
      return;
    }

    const key = (
      normalizedValue.toLocaleLowerCase(
        "ru-RU"
      )
    );

    if (seen.has(key)) {
      return;
    }

    seen.add(key);
    result.push(normalizedValue);
  });

  return result;
}


function getOptionValue(option) {
  if (
    option
    && typeof option === "object"
  ) {
    return String(
      option.value ?? ""
    ).trim();
  }

  return String(
    option ?? ""
  ).trim();
}


function getOptionLabel(option) {
  if (
    option
    && typeof option === "object"
  ) {
    return String(
      option.label
      ?? option.value
      ?? ""
    ).trim();
  }

  return String(
    option ?? ""
  ).trim();
}


function getOptionCount(option) {
  if (
    !option
    || typeof option !== "object"
  ) {
    return null;
  }

  const count = Number(
    option.count
  );

  return Number.isFinite(count)
    ? count
    : null;
}


function HealthCard({
  label,
  value,
  type = "default",
  note,
}) {
  return (
    <article
      className={[
        "iprice-health-card",
        (
          "iprice-health-card"
          + `--${type}`
        ),
      ].join(" ")}
    >
      <span className="iprice-health-card__label">
        {label}
      </span>

      <strong className="iprice-health-card__value">
        {formatNumber(value)}
      </strong>

      {note && (
        <small>
          {note}
        </small>
      )}
    </article>
  );
}


function MultiSelectFilter({
  label,
  options,
  selectedValues,
  disabled,
  onChange,
}) {
  const rootRef = useRef(null);
  const menuRef = useRef(null);

  const [
    opened,
    setOpened,
  ] = useState(false);

  const [
    search,
    setSearch,
  ] = useState("");
  const [menuLeft, setMenuLeft] = useState(0);

  const normalizedSelected = useMemo(
    () => normalizeArray(
      selectedValues
    ),
    [selectedValues],
  );

  const selectedSet = useMemo(
    () => new Set(
      normalizedSelected.map(
        (value) => (
          value.toLocaleLowerCase(
            "ru-RU"
          )
        ),
      ),
    ),
    [normalizedSelected],
  );

  const visibleOptions = useMemo(
    () => {
      const normalizedSearch = (
        search
          .trim()
          .toLocaleLowerCase("ru-RU")
      );

      return (
        Array.isArray(options)
          ? options
          : []
      ).filter((option) => {
        const optionLabel = (
          getOptionLabel(option)
        );

        if (!optionLabel) {
          return false;
        }

        if (!normalizedSearch) {
          return true;
        }

        return optionLabel
          .toLocaleLowerCase("ru-RU")
          .includes(normalizedSearch);
      });
    },
    [
      options,
      search,
    ],
  );


  useEffect(() => {
    if (!opened) {
      return undefined;
    }

    function handleDocumentClick(event) {
      if (
        rootRef.current
        && !rootRef.current.contains(
          event.target
        )
      ) {
        setOpened(false);
      }
    }

    document.addEventListener(
      "mousedown",
      handleDocumentClick,
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleDocumentClick,
      );
    };
  }, [opened]);

  useLayoutEffect(() => {
    if (!opened) {
      return undefined;
    }

    function updateMenuPosition() {
      const root = rootRef.current;
      const menu = menuRef.current;
      if (!root || !menu) return;
      const bounds = root.getBoundingClientRect();
      const menuWidth = menu.getBoundingClientRect().width;
      const viewportPadding = 12;
      const fitsToRight = (
        bounds.left + menuWidth <= window.innerWidth - viewportPadding
      );
      const nextLeft = fitsToRight
        ? 0
        : Math.max(
            viewportPadding - bounds.left,
            bounds.width - menuWidth,
          );
      setMenuLeft((current) => (
        Math.abs(current - nextLeft) < 1 ? current : nextLeft
      ));
    }

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [opened, visibleOptions]);


  function toggleValue(value) {
    const normalizedValue = String(
      value ?? ""
    ).trim();

    if (!normalizedValue) {
      return;
    }

    const valueKey = (
      normalizedValue.toLocaleLowerCase(
        "ru-RU"
      )
    );

    if (selectedSet.has(valueKey)) {
      onChange(
        normalizedSelected.filter(
          (selectedValue) => (
            selectedValue
              .toLocaleLowerCase(
                "ru-RU"
              )
            !== valueKey
          ),
        ),
      );

      return;
    }

    onChange([
      ...normalizedSelected,
      normalizedValue,
    ]);
  }


  return (
    <div
      ref={rootRef}
      className={[
        "iprice-health-filter",
        opened
          ? (
              "iprice-health-filter"
              + "--opened"
            )
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className="iprice-health-filter__trigger"
        disabled={disabled}
        onClick={() => {
          setOpened(
            (previous) => !previous
          );
        }}
      >
        <span>
          {label}
        </span>

        <strong>
          {normalizedSelected.length > 0
            ? normalizedSelected.length
            : "Все"}
        </strong>
      </button>

      {opened && !disabled && (
        <div
          ref={menuRef}
          className="iprice-health-filter__menu"
          style={{ left: `${menuLeft}px` }}
        >
          <input
            type="search"
            value={search}
            placeholder="Поиск"
            autoFocus
            onChange={(event) => {
              setSearch(
                event.target.value
              );
            }}
          />

          <div className="iprice-health-filter__actions">
            <button
              type="button"
              disabled={
                normalizedSelected.length
                === 0
              }
              onClick={() => {
                onChange([]);
              }}
            >
              Очистить
            </button>

            <button
              type="button"
              onClick={() => {
                setOpened(false);
              }}
            >
              Готово
            </button>
          </div>

          <div className="iprice-health-filter__options">
            {visibleOptions.length === 0 ? (
              <div className="iprice-health-filter__empty">
                Значения не найдены.
              </div>
            ) : (
              visibleOptions.map(
                (option) => {
                  const value = (
                    getOptionValue(option)
                  );

                  const optionLabel = (
                    getOptionLabel(option)
                  );

                  const count = (
                    getOptionCount(option)
                  );

                  const checked = (
                    selectedSet.has(
                      value.toLocaleLowerCase(
                        "ru-RU"
                      )
                    )
                  );

                  return (
                    <label
                      key={value}
                      className="iprice-health-filter-option"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          toggleValue(value);
                        }}
                      />

                      <span title={optionLabel}>
                        {optionLabel}
                      </span>

                      {count !== null && (
                        <small>
                          {formatNumber(count)}
                        </small>
                      )}
                    </label>
                  );
                },
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}


function SectionStatusCard({
  section,
  active,
  disabled,
  onClick,
}) {
  return (
    <button
      type="button"
      className={[
        "iprice-health-section-card",
        (
          "iprice-health-section-card"
          + `--${section.status || "success"}`
        ),
        active
          ? (
              "iprice-health-section-card"
              + "--active"
            )
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled}
      onClick={onClick}
    >
      <div>
        <strong>
          {section.label}
        </strong>

        <span>
          Проверено:
          {" "}
          {formatNumber(
            section.checked
          )}
        </span>
      </div>

      <dl>
        <div>
          <dt>
            Ошибки
          </dt>

          <dd>
            {formatNumber(
              section.errors_count
            )}
          </dd>
        </div>

        <div>
          <dt>
            Предупреждения
          </dt>

          <dd>
            {formatNumber(
              section.warnings_count
            )}
          </dd>
        </div>
      </dl>
    </button>
  );
}


function HealthTable({
  rows,
}) {
  return (
    <div className="iprice-health-table-wrapper">
      <table className="iprice-health-table">
        <thead>
          <tr>
            <th>Уровень</th>
            <th>Раздел</th>
            <th>Группа</th>
            <th>Код</th>
            <th>Ключ</th>
            <th>Product key</th>
            <th>Product key конкурента</th>
            <th>Код 1С</th>
            <th>Производство</th>
            <th>Регион</th>
            <th>Источник</th>
            <th>Описание</th>
            <th>Детали</th>
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <span
                  className={[
                    "iprice-health-level",
                    (
                      "iprice-health-level"
                      + `--${
                        String(
                          row.level || ""
                        ).toLowerCase()
                      }`
                    ),
                  ].join(" ")}
                >
                  {row.level === LEVEL_ERROR
                    ? "Ошибка"
                    : "Предупреждение"}
                </span>
              </td>

              <td>
                {row.section_label || "—"}
              </td>

              <td>
                {row.issue_group || "—"}
              </td>

              <td>
                <code>
                  {row.error_code || "—"}
                </code>
              </td>

              <td>
                {row.business_key || "—"}
              </td>

              <td>
                {row.product_key ?? "—"}
              </td>

              <td>
                {
                  row.competitor_product_key
                  ?? "—"
                }
              </td>

              <td>
                {row.code_1c ?? "—"}
              </td>

              <td>
                {row.departure || "—"}
              </td>

              <td>
                {row.arrival || "—"}
              </td>

              <td>
                {row.source || "—"}
              </td>

              <td className="iprice-health-table__message">
                {row.message || "—"}
              </td>

              <td>
                {row.details
                  && Object.keys(
                    row.details
                  ).length > 0 ? (
                    <details>
                      <summary>
                        Показать
                      </summary>

                      <pre>
                        {JSON.stringify(
                          row.details,
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  ) : (
                    "—"
                  )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function HealthPagination({
  page,
  totalPages,
  count,
  pageSize,
  loading,
  onPageChange,
  onPageSizeChange,
}) {
  if (count === 0) {
    return null;
  }

  return (
    <div className="iprice-health-pagination">
      <div>
        Найдено:
        {" "}
        <strong>
          {formatNumber(count)}
        </strong>
      </div>

      <div>
        <button
          type="button"
          disabled={
            loading
            || page <= 1
          }
          onClick={() => {
            onPageChange(page - 1);
          }}
        >
          Назад
        </button>

        <span>
          Страница
          {" "}
          <strong>
            {page}
          </strong>
          {" "}
          из
          {" "}
          <strong>
            {totalPages || 1}
          </strong>
        </span>

        <button
          type="button"
          disabled={
            loading
            || page >= totalPages
          }
          onClick={() => {
            onPageChange(page + 1);
          }}
        >
          Вперёд
        </button>
      </div>

      <label>
        <span>
          Строк на странице
        </span>

        <select
          value={pageSize}
          disabled={loading}
          onChange={(event) => {
            onPageSizeChange(
              Number(
                event.target.value
              ),
            );
          }}
        >
          <option value={25}>
            25
          </option>

          <option value={50}>
            50
          </option>

          <option value={100}>
            100
          </option>

          <option value={200}>
            200
          </option>
        </select>
      </label>
    </div>
  );
}


export function IPriceHealthSection({
  realtimeEvent,
}) {
  const [
    result,
    setResult,
  ] = useState(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    refreshing,
    setRefreshing,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    level,
    setLevel,
  ] = useState(LEVEL_ALL);

  const [
    selectedSections,
    setSelectedSections,
  ] = useState([]);

  const [
    selectedIssueGroups,
    setSelectedIssueGroups,
  ] = useState([]);

  const [
    selectedErrorCodes,
    setSelectedErrorCodes,
  ] = useState([]);

  const [
    searchInput,
    setSearchInput,
  ] = useState("");

  const [
    appliedSearch,
    setAppliedSearch,
  ] = useState("");

  const [
    page,
    setPage,
  ] = useState(1);

  const [
    pageSize,
    setPageSize,
  ] = useState(50);

  const requestIdRef = useRef(0);


  const loadHealth = useCallback(
    async ({
      nextLevel = level,
      nextSections = selectedSections,
      nextIssueGroups = (
        selectedIssueGroups
      ),
      nextErrorCodes = selectedErrorCodes,
      nextSearch = appliedSearch,
      nextPage = 1,
      nextPageSize = pageSize,
      forceRefresh = false,
      silent = false,
    } = {}) => {
      const requestId = (
        requestIdRef.current + 1
      );

      requestIdRef.current = requestId;

      if (forceRefresh) {
        setRefreshing(true);
      } else if (!silent) {
        setLoading(true);
      }

      setError("");

      try {
        const response = (
          await getIPriceHealth({
            level: nextLevel,
            sections: nextSections,
            issueGroups: nextIssueGroups,
            errorCodes: nextErrorCodes,
            search: nextSearch,
            page: nextPage,
            pageSize: nextPageSize,
            forceRefresh,
          })
        );

        if (
          requestIdRef.current
          !== requestId
        ) {
          return;
        }

        setResult(response);
        setPage(response.page);
      } catch (requestError) {
        if (
          requestIdRef.current
          !== requestId
        ) {
          return;
        }

        setError(
          getErrorMessage(
            requestError
          ),
        );
      } finally {
        if (
          requestIdRef.current
          === requestId
        ) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [
      level,
      selectedSections,
      selectedIssueGroups,
      selectedErrorCodes,
      appliedSearch,
      pageSize,
    ],
  );


  useEffect(() => {
    loadHealth();
  }, [
    loadHealth,
  ]);


  useEffect(() => {
    if (
      realtimeEvent?.change_type === "source_data_updated"
      || String(realtimeEvent?.change_type || "")
        .startsWith("parser_")
    ) {
      loadHealth({
        forceRefresh: true,
        silent: true,
      });
    }
  }, [realtimeEvent, loadHealth]);


  const summary = (
    result?.summary || {}
  );

  const sections = (
    result?.sections || []
  );

  const filterOptions = (
    result?.filterOptions || {}
  );

  const rows = (
    result?.results || []
  );


  function applyFilters({
    nextLevel = level,
    nextSections = selectedSections,
    nextIssueGroups = (
      selectedIssueGroups
    ),
    nextErrorCodes = selectedErrorCodes,
    nextSearch = appliedSearch,
    nextPageSize = pageSize,
  } = {}) {
    setPage(1);

    loadHealth({
      nextLevel,
      nextSections,
      nextIssueGroups,
      nextErrorCodes,
      nextSearch,
      nextPage: 1,
      nextPageSize,
    });
  }


  function handleSectionCardClick(
    sectionName,
  ) {
    const normalizedCurrent = (
      normalizeArray(
        selectedSections
      )
    );

    const selected = (
      normalizedCurrent.includes(
        sectionName
      )
    );

    const nextSections = selected
      ? normalizedCurrent.filter(
          (value) => (
            value !== sectionName
          ),
        )
      : [
          ...normalizedCurrent,
          sectionName,
        ];

    setSelectedSections(
      nextSections
    );

    applyFilters({
      nextSections,
    });
  }


  function handleClearFilters() {
    setLevel(LEVEL_ALL);
    setSelectedSections([]);
    setSelectedIssueGroups([]);
    setSelectedErrorCodes([]);
    setSearchInput("");
    setAppliedSearch("");
    setPage(1);

    loadHealth({
      nextLevel: LEVEL_ALL,
      nextSections: [],
      nextIssueGroups: [],
      nextErrorCodes: [],
      nextSearch: "",
      nextPage: 1,
    });
  }


  function handleSearchSubmit(event) {
    event.preventDefault();

    const nextSearch = (
      searchInput.trim()
    );

    setAppliedSearch(
      nextSearch
    );

    applyFilters({
      nextSearch,
    });
  }


  const selectedFilterCount = (
    selectedSections.length
    + selectedIssueGroups.length
    + selectedErrorCodes.length
    + (
      level === LEVEL_ALL
        ? 0
        : 1
    )
    + (
      appliedSearch
        ? 1
        : 0
    )
  );


  return (
    <section className="iprice-health">
      <div className="iprice-data-section-header">
        <div>
          <h2>
            Контроль данных
          </h2>

          <p>
            Проверка полноты и согласованности
            данных перед запуском расчёта iPrice.
          </p>
        </div>

        <button
          type="button"
          className="iprice-health-refresh-button"
          disabled={
            loading
            || refreshing
          }
          onClick={() => {
            loadHealth({
              nextPage: 1,
              forceRefresh: true,
            });
          }}
        >
          {refreshing
            ? "Проверка..."
            : "Запустить проверку"}
        </button>
      </div>

      {error && (
        <div className="iprice-data-operation-error">
          <span>
            {error}
          </span>

          <button
            type="button"
            onClick={() => {
              loadHealth();
            }}
          >
            Повторить
          </button>
        </div>
      )}

      {loading && !result ? (
        <div className="iprice-history-loading">
          Выполняется контроль данных...
        </div>
      ) : (
        <>
          <section className="iprice-health-summary">
            <HealthCard
              label="Проверено строк"
              value={
                summary.checkedTotal
              }
            />

            <HealthCard
              label="Всего проблем"
              value={
                summary.issuesTotal
              }
              type={
                summary.issuesTotal > 0
                  ? "warning"
                  : "success"
              }
            />

            <HealthCard
              label="Ошибок"
              value={
                summary.errorsTotal
              }
              type={
                summary.errorsTotal > 0
                  ? "error"
                  : "success"
              }
            />

            <HealthCard
              label="Предупреждений"
              value={
                summary.warningsTotal
              }
              type={
                summary.warningsTotal > 0
                  ? "warning"
                  : "success"
              }
            />

            <HealthCard
              label="Разделов без проблем"
              value={
                summary.healthySections
              }
              type="success"
            />

            <HealthCard
              label="Проблемных разделов"
              value={
                summary.problemSections
              }
              type={
                summary.problemSections > 0
                  ? "error"
                  : "success"
              }
            />
          </section>

          <section className="iprice-health-sections">
            <div className="iprice-health-block-header">
              <div>
                <h3>
                  Состояние разделов
                </h3>

                <p>
                  Нажатие на карточку применяет
                  или снимает фильтр по разделу.
                </p>
              </div>
            </div>

            <div className="iprice-health-sections__grid">
              {sections.map((section) => (
                <SectionStatusCard
                  key={section.name}
                  section={section}
                  active={
                    selectedSections.includes(
                      section.name
                    )
                  }
                  disabled={
                    loading
                    || refreshing
                  }
                  onClick={() => {
                    handleSectionCardClick(
                      section.name
                    );
                  }}
                />
              ))}
            </div>
          </section>

          <section className="iprice-health-controls">
            <div className="iprice-health-block-header">
              <div>
                <h3>
                  Фильтры проблем
                </h3>

                <p>
                  Фильтры применяются к таблице
                  результатов проверки.
                </p>
              </div>

              <div>
                <span>
                  Активных фильтров:
                  {" "}
                  <strong>
                    {selectedFilterCount}
                  </strong>
                </span>

                <button
                  type="button"
                  disabled={
                    loading
                    || refreshing
                    || selectedFilterCount === 0
                  }
                  onClick={
                    handleClearFilters
                  }
                >
                  Очистить всё
                </button>
              </div>
            </div>

            <div className="iprice-health-controls__grid">
              <label className="iprice-health-level-filter">
                <span>
                  Уровень
                </span>

                <select
                  value={level}
                  disabled={
                    loading
                    || refreshing
                  }
                  onChange={(event) => {
                    const nextLevel = (
                      event.target.value
                    );

                    setLevel(nextLevel);

                    applyFilters({
                      nextLevel,
                    });
                  }}
                >
                  <option value={LEVEL_ALL}>
                    Все
                  </option>

                  <option value={LEVEL_ERROR}>
                    Ошибки
                  </option>

                  <option value={LEVEL_WARNING}>
                    Предупреждения
                  </option>
                </select>
              </label>

              <MultiSelectFilter
                label="Раздел"
                options={
                  filterOptions.sections
                }
                selectedValues={
                  selectedSections
                }
                disabled={
                  loading
                  || refreshing
                }
                onChange={(values) => {
                  setSelectedSections(
                    values
                  );

                  applyFilters({
                    nextSections: values,
                  });
                }}
              />

              <MultiSelectFilter
                label="Группа проблемы"
                options={
                  filterOptions.issueGroups
                }
                selectedValues={
                  selectedIssueGroups
                }
                disabled={
                  loading
                  || refreshing
                }
                onChange={(values) => {
                  setSelectedIssueGroups(
                    values
                  );

                  applyFilters({
                    nextIssueGroups: values,
                  });
                }}
              />

              <MultiSelectFilter
                label="Код ошибки"
                options={
                  filterOptions.errorCodes
                }
                selectedValues={
                  selectedErrorCodes
                }
                disabled={
                  loading
                  || refreshing
                }
                onChange={(values) => {
                  setSelectedErrorCodes(
                    values
                  );

                  applyFilters({
                    nextErrorCodes: values,
                  });
                }}
              />

              <form
                className="iprice-health-search"
                onSubmit={
                  handleSearchSubmit
                }
              >
                <label>
                  <span>
                    Поиск
                  </span>

                  <input
                    type="search"
                    value={searchInput}
                    placeholder={
                      "Ключ, product key, код, текст"
                    }
                    disabled={
                      loading
                      || refreshing
                    }
                    onChange={(event) => {
                      setSearchInput(
                        event.target.value
                      );
                    }}
                  />
                </label>

                <button
                  type="submit"
                  disabled={
                    loading
                    || refreshing
                  }
                >
                  Найти
                </button>
              </form>
            </div>
          </section>

          <section className="iprice-health-results">
            <div className="iprice-health-block-header">
              <div>
                <h3>
                  Найденные проблемы
                </h3>

                <p>
                  Ошибки необходимо устранить
                  до запуска рабочего snapshot.
                </p>
              </div>

              <span>
                Найдено:
                {" "}
                <strong>
                  {formatNumber(
                    result?.count
                  )}
                </strong>
              </span>
            </div>

            {rows.length === 0 ? (
              <div className="iprice-health-empty">
                {summary.issuesTotal === 0
                  ? (
                      "Проблемы не обнаружены. "
                      + "Данные готовы к расчёту."
                    )
                  : (
                      "По выбранным фильтрам "
                      + "проблемы не найдены."
                    )}
              </div>
            ) : (
              <HealthTable
                rows={rows}
              />
            )}

            <HealthPagination
              page={result?.page || 1}
              totalPages={
                result?.totalPages || 0
              }
              count={result?.count || 0}
              pageSize={
                result?.pageSize || pageSize
              }
              loading={
                loading
                || refreshing
              }
              onPageChange={(nextPage) => {
                setPage(nextPage);

                loadHealth({
                  nextPage,
                });
              }}
              onPageSizeChange={(
                nextPageSize
              ) => {
                setPageSize(
                  nextPageSize
                );

                setPage(1);

                loadHealth({
                  nextPage: 1,
                  nextPageSize,
                });
              }}
            />
          </section>
        </>
      )}
    </section>
  );
}
