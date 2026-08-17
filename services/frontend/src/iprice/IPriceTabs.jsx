const IPRICE_TABS = [
  {
    id: "analytics",
    label: "Аналитика",
  },
  {
    id: "calculation",
    label: "Расчёт цен",
  },
  {
    id: "history",
    label: "История изменений",
  },
  {
    id: "data",
    label: "Данные и настройки",
  },
];


export function IPriceTabs({
  activeTab,
  onChange,
}) {
  return (
    <div
      className="iprice-tabs"
      role="tablist"
      aria-label="Разделы iPrice"
    >
      {IPRICE_TABS.map((tab) => {
        const isActive = (
          activeTab === tab.id
        );

        return (
          <button
            type="button"
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            className={[
              "iprice-tab",
              isActive
                ? "iprice-tab--active"
                : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => {
              onChange(tab.id);
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
