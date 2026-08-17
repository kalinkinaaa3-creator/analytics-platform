import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  IPriceUploadsSection,
} from "./IPriceUploadsSection";

import {
  IPriceParsersSection,
} from "./IPriceParsersSection";

const SECTION_UPLOADS = "uploads";
const SECTION_PARSERS = "parsers";


const DATA_SECTIONS = [
  {
    id: SECTION_UPLOADS,
    label: "Выгрузки и загрузки",
  },
  {
    id: SECTION_PARSERS,
    label: "Парсеры",
  },
];


function isAllowedSection(
  section,
) {
  return DATA_SECTIONS.some(
    (item) => item.id === section,
  );
}


function getSectionFromUrl() {
  const params = new URLSearchParams(
    window.location.search,
  );

  const section = params.get(
    "data_section",
  );

  return isAllowedSection(section)
    ? section
    : SECTION_UPLOADS;
}


function updateSectionInUrl(
  section,
) {
  const normalizedSection = (
    isAllowedSection(section)
      ? section
      : SECTION_UPLOADS
  );

  const url = new URL(
    window.location.href,
  );

  url.searchParams.set(
    "tab",
    "data",
  );

  url.searchParams.set(
    "data_section",
    normalizedSection,
  );

  window.history.replaceState(
    {},
    "",
    url,
  );
}


export function IPriceDataTab({
  canEdit = false,
  onSnapshotsChanged,
  realtimeEvent,
}) {
  const [
    activeSection,
    setActiveSection,
  ] = useState(
    getSectionFromUrl,
  );


  useEffect(() => {
    function handlePopState() {
      setActiveSection(
        getSectionFromUrl(),
      );
    }

    window.addEventListener(
      "popstate",
      handlePopState,
    );

    return () => {
      window.removeEventListener(
        "popstate",
        handlePopState,
      );
    };
  }, []);


  useEffect(() => {
    const sectionFromUrl = (
      getSectionFromUrl()
    );

    if (
      sectionFromUrl
      !== activeSection
    ) {
      updateSectionInUrl(
        activeSection,
      );
    }
  }, [
    activeSection,
  ]);


  const handleSectionChange = (
    useCallback(
      (section) => {
        const normalizedSection = (
          isAllowedSection(section)
            ? section
            : SECTION_UPLOADS
        );

        updateSectionInUrl(
          normalizedSection,
        );

        setActiveSection(
          normalizedSection,
        );
      },
      [],
    )
  );


  function renderSection() {
    if (
      activeSection
      === SECTION_UPLOADS
    ) {
      return (
        <IPriceUploadsSection
          canEdit={canEdit}
          realtimeEvent={realtimeEvent}
          onSnapshotsChanged={
            onSnapshotsChanged
          }
        />
      );
    }

    if (
      activeSection
      === SECTION_PARSERS
    ) {
      return (
        <IPriceParsersSection
          canEdit={canEdit}
          realtimeEvent={realtimeEvent}
        />
      );
    }

    return (
      <IPriceUploadsSection
        canEdit={canEdit}
        realtimeEvent={realtimeEvent}
        onSnapshotsChanged={
          onSnapshotsChanged
        }
      />
    );
  }


  return (
    <section className="iprice-data-tab">
      <nav
        className="iprice-data-sections"
        aria-label={
          "Разделы данных и настроек"
        }
      >
        {DATA_SECTIONS.map(
          (section) => {
            const isActive = (
              activeSection
              === section.id
            );

            return (
              <button
                key={section.id}
                type="button"
                className={[
                  (
                    "iprice-data-"
                    + "sections__button"
                  ),
                  isActive
                    ? (
                        "iprice-data-"
                        + "sections__button"
                        + "--active"
                      )
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={
                  isActive
                    ? "page"
                    : undefined
                }
                onClick={() => {
                  handleSectionChange(
                    section.id,
                  );
                }}
              >
                {section.label}
              </button>
            );
          },
        )}
      </nav>

      <div className="iprice-data-tab__content">
        {renderSection()}
      </div>
    </section>
  );
}
