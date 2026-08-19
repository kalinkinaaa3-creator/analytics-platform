import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";


const FILTER_VALUE_LABELS = {
  pricing_method: {
    analog: "Аналог",
    exclusive: "Эксклюзив",
  },
  calculation_status: {
    success: "Рассчитано",
    warning: "Предупреждение",
    error: "Ошибка",
  },
};


function getValueLabel(
  filterName,
  value,
  fallback,
) {
  return (
    FILTER_VALUE_LABELS[filterName]?.[value]
    ?? fallback
    ?? value
  );
}


export function IPriceDependentMultiSelect({
  name,
  label,
  options,
  selected,
  disabled = false,
  loading = false,
  onChange,
}) {
  const rootRef = useRef(null);
  const dropdownRef = useRef(null);

  const [
    open,
    setOpen,
  ] = useState(false);

  const [
    search,
    setSearch,
  ] = useState("");
  const [dropdownLeft, setDropdownLeft] = useState(0);

  const safeSelected = Array.isArray(
    selected
  )
    ? selected
    : [];

  const safeOptions = Array.isArray(
    options
  )
    ? options
    : [];

  const selectedSet = useMemo(
    () => new Set(safeSelected),
    [safeSelected],
  );

  const visibleOptions = useMemo(
    () => {
      const normalizedSearch = (
        search.trim().toLowerCase()
      );

      if (!normalizedSearch) {
        return safeOptions;
      }

      return safeOptions.filter(
        (option) => {
          const rawValue = String(
            option?.value ?? ""
          );
          const label = String(
            getValueLabel(
              name,
              rawValue,
              option?.label,
            )
          ).toLowerCase();

          return (
            label.includes(normalizedSearch)
            || rawValue.toLowerCase().includes(
              normalizedSearch
            )
          );
        }
      );
    },
    [
      safeOptions,
      search,
      name,
    ],
  );


  useEffect(() => {
    function handleDocumentClick(event) {
      if (
        rootRef.current
        && !rootRef.current.contains(
          event.target
        )
      ) {
        setOpen(false);
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
  }, []);


  useLayoutEffect(() => {
    if (!open) {
      return undefined;
    }

    function updateDropdownPosition() {
      const root = rootRef.current;
      const dropdown = dropdownRef.current;
      if (!root || !dropdown) {
        return;
      }
      const bounds = root.getBoundingClientRect();
      const dropdownWidth = dropdown.getBoundingClientRect().width;
      const viewportPadding = 12;
      const fitsToRight = (
        bounds.left + dropdownWidth
        <= window.innerWidth - viewportPadding
      );
      const nextLeft = fitsToRight
        ? 0
        : Math.max(
            viewportPadding - bounds.left,
            bounds.width - dropdownWidth,
          );
      setDropdownLeft((current) => (
        Math.abs(current - nextLeft) < 1 ? current : nextLeft
      ));
    }

    updateDropdownPosition();
    window.addEventListener("resize", updateDropdownPosition);
    window.addEventListener("scroll", updateDropdownPosition, true);
    return () => {
      window.removeEventListener("resize", updateDropdownPosition);
      window.removeEventListener("scroll", updateDropdownPosition, true);
    };
  }, [open, visibleOptions, name]);


  function toggleValue(value) {
    const nextValues = selectedSet.has(value)
      ? safeSelected.filter(
          (item) => item !== value
        )
      : [
          ...safeSelected,
          value,
        ];

    onChange(
      name,
      nextValues,
    );
  }


  function selectVisible() {
    const nextValues = new Set(
      safeSelected
    );

    visibleOptions.forEach(
      (option) => {
        nextValues.add(
          option.value
        );
      }
    );

    onChange(
      name,
      Array.from(nextValues),
    );
  }


  function clearFilter() {
    onChange(
      name,
      [],
    );
  }


  function getButtonLabel() {
    if (safeSelected.length === 0) {
      return "Все";
    }

    if (safeSelected.length === 1) {
      return getValueLabel(
        name,
        safeSelected[0],
      );
    }

    return `Выбрано: ${safeSelected.length}`;
  }


  return (
    <div
      ref={rootRef}
      className={[
        "iprice-filter",
        "iprice-multiselect",
        open
          ? "iprice-multiselect--open"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <label
        htmlFor={`iprice_filter_${name}`}
      >
        {label}
      </label>

      <button
        id={`iprice_filter_${name}`}
        type="button"
        className="iprice-multiselect__trigger"
        title={getButtonLabel()}
        disabled={disabled}
        onClick={() => {
          setOpen((previous) => !previous);
        }}
      >
        <span>
          {getButtonLabel()}
        </span>

        <span aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div
          ref={dropdownRef}
          className="iprice-multiselect__dropdown"
          style={{ left: `${dropdownLeft}px` }}
        >
          <input
            type="text"
            value={search}
            placeholder="Поиск..."
            className="iprice-multiselect__search"
            onChange={(event) => {
              setSearch(
                event.target.value
              );
            }}
          />

          <div className="iprice-multiselect__controls">
            <button
              type="button"
              onClick={selectVisible}
            >
              Выбрать найденные
            </button>

            <button
              type="button"
              disabled={
                safeSelected.length === 0
              }
              onClick={clearFilter}
            >
              Очистить
            </button>
          </div>

          <div className="iprice-multiselect__options">
            {loading && (
              <div className="iprice-multiselect__message">
                Загрузка...
              </div>
            )}

            {!loading
              && visibleOptions.length === 0 && (
                <div className="iprice-multiselect__message">
                  Нет значений
                </div>
              )}

            {!loading
              && visibleOptions.map(
                (option) => {
                  const value = String(
                    option.value
                  );
                  const optionLabel = (
                    getValueLabel(
                      name,
                      value,
                      option.label,
                    )
                  );

                  return (
                    <label
                      key={value}
                      className="iprice-multiselect__option"
                    >
                      <input
                        type="checkbox"
                        checked={
                          selectedSet.has(
                            value
                          )
                        }
                        onChange={() => {
                          toggleValue(value);
                        }}
                      />

                      <span
                        className="iprice-multiselect__option-label"
                        title={optionLabel}
                      >
                        {optionLabel}
                      </span>

                      <span className="iprice-multiselect__option-count">
                        {option.count ?? 0}
                      </span>
                    </label>
                  );
                }
              )}
          </div>
        </div>
      )}
    </div>
  );
}
