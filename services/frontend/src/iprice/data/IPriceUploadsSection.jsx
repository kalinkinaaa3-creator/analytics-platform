import {
  useRef,
  useState,
} from "react";

import {
  downloadBlob,
  exportIPriceDataFile,
  exportIPriceUploadTemplate,
  uploadIPriceDataFile,
} from "../api/ipriceApi";


const UPLOAD_DEFINITIONS = [
  {
    id: "product_classification",
    hasTemplate: true,
    title: "1. Классификация товаров",
    accept: ".xlsx",
    fileHint: "Excel .xlsx",
  },

  {
    id: "transport_cost",
    hasTemplate: true,
    title: "2. Логистические расходы",
    accept: ".xlsx,.xls",
    fileHint: "Excel",
  },

  {
    id: "product_cost",
    hasTemplate: true,
    title: "3. Себестоимость товаров",
    accept: ".xlsx,.xls",
    fileHint: "Excel",
  },

  {
    id: "calculation_config",
    hasTemplate: true,
    title: "4. Конфигурации расчёта",
    accept: ".xlsx,.xls",
    fileHint: "Excel",
  },

  {
    id: "parser_prefixes",
    hasTemplate: true,
    title: "Региональные префиксы конкурентов",
    accept: ".xlsx,.xls,.csv",
    fileHint: "Excel или CSV",
  },
];


const EXPORT_DEFINITIONS = [
  {
    id: "parser_products",
    title: "1. Данные для продуктового анализа",
  },

  {
    id: "product_cost_template",
    title: "2. Список товаров на себестоимость",
  },

  {
    id: "preparation_check",
    title: "Предварительная проверка и контроль ошибок",
  },
];


function formatBytes(bytes) {
  const value = Number(bytes);

  if (
    !Number.isFinite(value)
    || value < 0
  ) {
    return "—";
  }

  if (value < 1024) {
    return `${value} Б`;
  }

  if (value < 1024 ** 2) {
    return (
      `${(value / 1024).toFixed(1)} КБ`
    );
  }

  return (
    `${(
      value / (1024 ** 2)
    ).toFixed(1)} МБ`
  );
}


function getErrorMessage(error) {
  const data = error?.response?.data;

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (typeof data?.message === "string") {
    return data.message;
  }

  if (
    data
    && typeof data === "object"
  ) {
    const entries = Object.entries(
      data,
    );

    if (entries.length > 0) {
      return entries
        .map(([
          key,
          value,
        ]) => {
          const preparedValue = (
            Array.isArray(value)
              ? value.join(", ")
              : String(value)
          );

          return `${key}: ${preparedValue}`;
        })
        .join("; ");
    }
  }

  return (
    error?.message
    || "Не удалось выполнить операцию."
  );
}


function formatResultValue(value) {
  if (
    value === null
    || value === undefined
  ) {
    return "—";
  }

  if (typeof value === "boolean") {
    return value
      ? "Да"
      : "Нет";
  }

  if (Array.isArray(value)) {
    return value.length > 0
      ? value.join(", ")
      : "—";
  }

  if (typeof value === "object") {
    return JSON.stringify(
      value,
      null,
      2,
    );
  }

  return String(value);
}


function getVisibleResultEntries(result) {
  if (
    !result
    || typeof result !== "object"
    || Array.isArray(result)
  ) {
    return [];
  }

  const preferredFields = [
    "created",
    "updated",
    "reactivated",
    "unchanged",
    "inactivated",
    "skipped",
    "processed",
    "loaded",
    "inserted",
    "deleted",
    "errors",
    "warnings",
    "input_rows",
    "classifications_loaded",
    "automatic_matches_loaded",
    "excluded_matches_preserved",
    "success",
    "message",
  ];

  const resultEntries = Object.entries(
    result,
  );

  const preferredEntries = (
    preferredFields
      .filter((fieldName) => (
        Object.prototype.hasOwnProperty.call(
          result,
          fieldName,
        )
      ))
      .map((fieldName) => ([
        fieldName,
        result[fieldName],
      ]))
  );

  if (preferredEntries.length > 0) {
    return preferredEntries;
  }

  return resultEntries.slice(0, 10);
}


const RESULT_FIELD_LABELS = {
  input_rows: "Строк в файле",
  classifications_loaded: "Действующих классификаций",
  automatic_matches_loaded: "Связей из файла",
  excluded_matches_preserved: "Сохранено исключений",
};


function ResultDetails({
  result,
}) {
  const entries = getVisibleResultEntries(
    result,
  );

  if (entries.length === 0) {
    return null;
  }

  return (
    <details className="iprice-data-result">
      <summary>
        Результат операции
      </summary>

      <dl>
        {entries.map(([
          key,
          value,
        ]) => (
          <div key={key}>
            <dt>
              {RESULT_FIELD_LABELS[key] || key}
            </dt>

            <dd className={typeof value === "number" ? "iprice-data-result__number" : ""}>
              {formatResultValue(value)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}


function UploadCard({
  canEdit,
  definition,
  state,
  onFileChange,
  onUpload,
  onTemplateExport,
  onClear,
}) {
  const inputRef = useRef(null);

  const file = state?.file || null;
  const uploading = Boolean(
    state?.uploading,
  );
  const exportingTemplate = Boolean(
    state?.exportingTemplate,
  );

  return (
    <article className="iprice-data-operation-card">
      <div className="iprice-data-operation-card__header">
        <div>
          <h3>
            {definition.title}
          </h3>

        </div>

      </div>

      <div className="iprice-data-file">
        <input
          ref={inputRef}
          type="file"
          accept={definition.accept}
          disabled={!canEdit || uploading}
          onChange={(event) => {
            const selectedFile = (
              event.target.files?.[0]
              || null
            );

            onFileChange(
              definition.id,
              selectedFile,
            );
          }}
        />

        <button
          type="button"
          disabled={!canEdit || uploading}
          onClick={() => {
            inputRef.current?.click();
          }}
        >
          Выбрать файл
        </button>

        <div className="iprice-data-file__info">
          {file ? (
            <>
              <strong title={file.name}>
                {file.name}
              </strong>

              <span>
                {formatBytes(file.size)}
              </span>
            </>
          ) : (
            <>
              <strong>
                Файл не выбран
              </strong>

              <span>
                {definition.fileHint}
              </span>
            </>
          )}
        </div>
      </div>

      {uploading && (
        <div className="iprice-data-progress">
          <div>
            <span
              style={{
                width: (
                  `${state.progress || 0}%`
                ),
              }}
            />
          </div>

          <strong>
            {state.progress || 0}%
          </strong>
        </div>
      )}

      {state?.error && (
        <div className="iprice-data-operation-error">
          {state.error}
        </div>
      )}

      {state?.successMessage && (
        <div className="iprice-data-operation-success">
          {state.successMessage}
        </div>
      )}

      <ResultDetails
        result={state?.result}
      />

      <div className="iprice-data-operation-card__actions">
        <button
          type="button"
          disabled={
            uploading
            || !canEdit
            || !file
          }
          onClick={() => {
            onUpload(definition.id);
          }}
        >
          {uploading
            ? "Импорт..."
            : "Импорт"}
        </button>

        {definition.hasTemplate && (
          <button
            type="button"
            disabled={uploading || exportingTemplate}
            onClick={() => {
              onTemplateExport(definition.id);
            }}
          >
            {exportingTemplate
              ? "Формирование..."
              : "Выгрузить шаблон"}
          </button>
        )}

        <button
          type="button"
          disabled={
            uploading
            || (
              !file
              && !state?.result
              && !state?.error
            )
          }
          onClick={() => {
            if (inputRef.current) {
              inputRef.current.value = "";
            }

            onClear(definition.id);
          }}
        >
          Очистить
        </button>
      </div>
    </article>
  );
}


function ExportCard({
  definition,
  exporting,
  disabled,
  error,
  onExport,
}) {
  return (
    <article className="iprice-data-operation-card">
      <div className="iprice-data-operation-card__header">
        <div>
          <h3>
            {definition.title}
          </h3>

        </div>

      </div>

      {error && (
        <div className="iprice-data-operation-error">
          {error}
        </div>
      )}

      <div className="iprice-data-operation-card__actions">
        <button
          type="button"
          disabled={
            disabled
            || exporting
          }
          onClick={() => {
            onExport(definition.id);
          }}
        >
          {exporting
            ? "Формирование..."
            : "Экспорт"}
        </button>
      </div>
    </article>
  );
}


function createInitialUploadStates() {
  return Object.fromEntries(
    UPLOAD_DEFINITIONS.map(
      (definition) => ([
        definition.id,
        {
          file: null,
          uploading: false,
          exportingTemplate: false,
          progress: 0,
          result: null,
          error: "",
          successMessage: "",
        },
      ]),
    ),
  );
}


function createInitialExportStates() {
  return Object.fromEntries(
    EXPORT_DEFINITIONS.map(
      (definition) => ([
        definition.id,
        {
          exporting: false,
          error: "",
        },
      ]),
    ),
  );
}


export function IPriceUploadsSection({
  canEdit = false,
  onSnapshotsChanged,
}) {
  const [
    uploadStates,
    setUploadStates,
  ] = useState(
    createInitialUploadStates,
  );

  const [
    exportStates,
    setExportStates,
  ] = useState(
    createInitialExportStates,
  );


  function updateUploadState(
    uploadType,
    patch,
  ) {
    setUploadStates(
      (previous) => ({
        ...previous,

        [uploadType]: {
          ...previous[uploadType],
          ...patch,
        },
      }),
    );
  }


  function updateExportState(
    exportType,
    patch,
  ) {
    setExportStates(
      (previous) => ({
        ...previous,

        [exportType]: {
          ...previous[exportType],
          ...patch,
        },
      }),
    );
  }


  function handleFileChange(
    uploadType,
    file,
  ) {
    updateUploadState(
      uploadType,
      {
        file,
        progress: 0,
        result: null,
        error: "",
        successMessage: "",
      },
    );
  }


  function handleUploadClear(
    uploadType,
  ) {
    updateUploadState(
      uploadType,
      {
        file: null,
        uploading: false,
        progress: 0,
        result: null,
        error: "",
        successMessage: "",
      },
    );
  }


  async function handleUpload(
    uploadType,
  ) {
    const state = uploadStates[
      uploadType
    ];

    if (!state?.file) {
      return;
    }

    updateUploadState(
      uploadType,
      {
        uploading: true,
        progress: 0,
        result: null,
        error: "",
        successMessage: "",
      },
    );

    try {
      const result = (
        await uploadIPriceDataFile(
          uploadType,
          state.file,
          {
            onUploadProgress: (
              progressEvent
            ) => {
              const total = Number(
                progressEvent.total || 0,
              );

              if (total <= 0) {
                return;
              }

              const progress = Math.min(
                100,
                Math.round(
                  (
                    progressEvent.loaded
                    / total
                  )
                  * 100,
                ),
              );

              updateUploadState(
                uploadType,
                {
                  progress,
                },
              );
            },
          },
        )
      );

      updateUploadState(
        uploadType,
        {
          uploading: false,
          progress: 100,
          result,
          error: "",
          successMessage: "Файл успешно обработан.",
        },
      );

      onSnapshotsChanged?.();
    } catch (requestError) {
      updateUploadState(
        uploadType,
        {
          uploading: false,
          progress: 0,
          result: null,
          successMessage: "",
          error: getErrorMessage(
            requestError,
          ),
        },
      );
    }
  }


  async function handleTemplateExport(
    uploadType,
  ) {
    updateUploadState(
      uploadType,
      {
        exportingTemplate: true,
        error: "",
      },
    );

    try {
      const exportedFile = (
        await exportIPriceUploadTemplate(
          uploadType,
        )
      );

      downloadBlob(
        exportedFile.blob,
        exportedFile.filename,
      );

      updateUploadState(
        uploadType,
        {
          exportingTemplate: false,
        },
      );
    } catch (requestError) {
      updateUploadState(
        uploadType,
        {
          exportingTemplate: false,
          error: getErrorMessage(
            requestError,
          ),
        },
      );
    }
  }


  async function handleExport(
    exportType,
  ) {
    updateExportState(
      exportType,
      {
        exporting: true,
        error: "",
      },
    );

    try {
      let exportedFile;

      exportedFile = (
        await exportIPriceDataFile(
          exportType,
        )
      );

      downloadBlob(
        exportedFile.blob,
        exportedFile.filename,
      );

      updateExportState(
        exportType,
        {
          exporting: false,
          error: "",
        },
      );
    } catch (requestError) {
      updateExportState(
        exportType,
        {
          exporting: false,
          error: getErrorMessage(
            requestError,
          ),
        },
      );
    }
  }


  const uploadInProgress = (
    Object.values(
      uploadStates,
    ).some(
      (state) => state.uploading,
    )
  );

  const exportInProgress = (
    Object.values(
      exportStates,
    ).some(
      (state) => state.exporting,
    )
  );


  return (
    <section className="iprice-data-operations">
      <div className="iprice-data-section-header">
        <div className="iprice-data-section-header__status">
          {uploadInProgress && (
            <span>
              Выполняется загрузка
            </span>
          )}

          {exportInProgress && (
            <span>
              Формируется выгрузка
            </span>
          )}
        </div>
      </div>

      <section className="iprice-data-operation-group">
        <div className="iprice-data-operation-group__header">
          <h3>
            Выгрузки
          </h3>

        </div>

        <div className="iprice-data-operation-grid iprice-data-operation-grid--exports">
          {EXPORT_DEFINITIONS.map(
            (definition) => (
                <ExportCard
                  key={definition.id}
                  definition={definition}
                  exporting={
                    exportStates[
                      definition.id
                    ]?.exporting
                  }
                  error={
                    exportStates[
                      definition.id
                    ]?.error
                  }
                  disabled={false}
                  onExport={
                    handleExport
                  }
                />
              )
          )}
        </div>
      </section>

      <section className="iprice-data-operation-group">
        <div className="iprice-data-operation-group__header">
          <h3>
            Загрузки
          </h3>

        </div>

        <div className="iprice-data-operation-grid iprice-data-operation-grid--uploads">
          {UPLOAD_DEFINITIONS.map(
            (definition) => (
              <UploadCard
                canEdit={canEdit}
                key={definition.id}
                definition={definition}
                state={
                  uploadStates[
                    definition.id
                  ]
                }
                onFileChange={
                  handleFileChange
                }
                onUpload={
                  handleUpload
                }
                onTemplateExport={
                  handleTemplateExport
                }
                onClear={
                  handleUploadClear
                }
              />
            ),
          )}
        </div>
      </section>

    </section>
  );
}
