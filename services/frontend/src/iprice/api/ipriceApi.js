import {
  api,
} from "../../api/client";

const IPRICE_BASE_URL = (
  "/v1/datasets/iprice"
);


const DATASETS_BASE_URL = (
  "/v1/datasets"
);


export async function getIPriceAccess() {
  const response = await api.get(
    `${IPRICE_BASE_URL}/access/`,
  );

  return response.data?.dashboard || {};
}


/* ============================================================
   PRICE ANALYTICS
   ============================================================ */


export async function getIPricePriceAnalytics(
  snapshotId,
  payload = {},
) {
  if (!snapshotId) {
    throw new Error("snapshotId is required");
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/analytics/`
    ),
    payload,
  );

  return response.data || {};
}


export async function getIPricePriceZones() {
  const response = await api.get(
    `${IPRICE_BASE_URL}/analytics/price-zones/`,
  );

  return response.data || {};
}


export async function updateIPricePriceZones(payload) {
  const response = await api.post(
    `${IPRICE_BASE_URL}/analytics/price-zones/`,
    payload,
  );

  return response.data || {};
}


export async function createIPriceAnalyticsSelection(
  snapshotId,
  payload = {},
) {
  const response = await api.post(
    `${IPRICE_BASE_URL}/snapshots/${snapshotId}/analytics/selection/`,
    payload,
  );
  return response.data || {};
}


export async function getIPriceAnalyticsSelection(token) {
  const response = await api.get(
    `${IPRICE_BASE_URL}/analytics/selection/${encodeURIComponent(token)}/`,
  );
  return response.data || {};
}

/* ============================================================
   SNAPSHOTS
   ============================================================ */


export async function getIPriceSnapshots(
  params = {},
) {
  const response = await api.get(
    `${IPRICE_BASE_URL}/snapshots/`,
    {
      params,
    },
  );

  return {
    count: Number(
      response.data?.count || 0
    ),
    results: Array.isArray(
      response.data?.results
    )
      ? response.data.results
      : [],
  };
}


export async function getIPriceSnapshot(
  snapshotId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/`
    ),
  );

  return response.data;
}


export async function runIPriceSnapshot(
  calculationDate,
) {
  const payload = {};

  if (calculationDate) {
    payload.calculation_date = (
      calculationDate
    );
  }

  const response = await api.post(
    `${IPRICE_BASE_URL}/snapshots/run/`,
    payload,
  );

  return response.data;
}


export async function activateIPriceSnapshot(
  snapshotId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/activate/`
    ),
    {},
  );

  return response.data;
}


export async function deactivateIPriceSnapshot(
  snapshotId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.delete(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/activate/`
    ),
  );

  return response.data;
}


/* ============================================================
   SNAPSHOT COMPARISON
   ============================================================ */


export async function compareIPriceSnapshots({
  baseSnapshotId,
  comparisonSnapshotId,
  mode = "products",
  changeType = "all",
  page = 1,
  pageSize = 50,
  search = "",
  filters = {},
} = {}) {
  if (!baseSnapshotId) {
    throw new Error(
      "baseSnapshotId is required"
    );
  }

  if (!comparisonSnapshotId) {
    throw new Error(
      "comparisonSnapshotId is required"
    );
  }

  if (
    Number(baseSnapshotId)
    === Number(comparisonSnapshotId)
  ) {
    throw new Error(
      "Snapshots must be different"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + "/snapshots/compare/"
    ),
    {
      base_snapshot_id: Number(
        baseSnapshotId
      ),
      comparison_snapshot_id: Number(
        comparisonSnapshotId
      ),
      mode,
      change_type: changeType,
      page,
      page_size: pageSize,
      search: String(
        search || ""
      ).trim(),
      filters: (
        filters
        && typeof filters === "object"
          ? filters
          : {}
      ),
    },
  );

  const summary = (
    response.data?.summary
    && typeof response.data.summary
      === "object"
  )
    ? response.data.summary
    : {};

  return {
    mode: (
      response.data?.mode
      || mode
    ),

    baseSnapshot: (
      response.data?.base_snapshot
      || null
    ),

    comparisonSnapshot: (
      response.data?.comparison_snapshot
      || null
    ),

    summary: {
      total: Number(
        summary.total || 0
      ),
      added: Number(
        summary.added || 0
      ),
      removed: Number(
        summary.removed || 0
      ),
      changed: Number(
        summary.changed || 0
      ),
      unchanged: Number(
        summary.unchanged || 0
      ),
      priceIncreased: Number(
        summary.price_increased || 0
      ),
      priceDecreased: Number(
        summary.price_decreased || 0
      ),
      finalRrpIncreased: Number(
        summary.final_rrp_increased || 0
      ),
      finalRrpDecreased: Number(
        summary.final_rrp_decreased || 0
      ),
      statusChanged: Number(
        summary.status_changed || 0
      ),
      newErrors: Number(
        summary.new_errors || 0
      ),
      resolvedErrors: Number(
        summary.resolved_errors || 0
      ),
    },

    filteredCount: Number(
      response.data?.filtered_count || 0
    ),

    page: Number(
      response.data?.page || page
    ),

    pageSize: Number(
      response.data?.page_size
      || pageSize
    ),

    totalPages: Number(
      response.data?.total_pages || 0
    ),

    hasNext: Boolean(
      response.data?.has_next
    ),

    hasPrevious: Boolean(
      response.data?.has_previous
    ),

    results: Array.isArray(
      response.data?.results
    )
      ? response.data.results
      : [],
  };
}



/* ============================================================
   SNAPSHOT COMPARISON FILTERS
   ============================================================ */


export async function getIPriceSnapshotCompareFilters({
  baseSnapshotId,
  comparisonSnapshotId,
  mode = "products",
  filters = {},
} = {}) {
  if (!baseSnapshotId) {
    throw new Error(
      "baseSnapshotId is required"
    );
  }

  if (!comparisonSnapshotId) {
    throw new Error(
      "comparisonSnapshotId is required"
    );
  }

  if (
    Number(baseSnapshotId)
    === Number(comparisonSnapshotId)
  ) {
    throw new Error(
      "Snapshots must be different"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + "/snapshots/compare/filters/"
    ),
    {
      base_snapshot_id: Number(
        baseSnapshotId
      ),
      comparison_snapshot_id: Number(
        comparisonSnapshotId
      ),
      mode,
      filters: (
        filters
        && typeof filters === "object"
          ? filters
          : {}
      ),
    },
  );

  return {
    mode: (
      response.data?.mode
      || mode
    ),
    baseSnapshot: (
      response.data?.base_snapshot
      || null
    ),
    comparisonSnapshot: (
      response.data?.comparison_snapshot
      || null
    ),
    selected: (
      response.data?.selected
      && typeof response.data.selected
        === "object"
    )
      ? response.data.selected
      : {},
    options: (
      response.data?.options
      && typeof response.data.options
        === "object"
    )
      ? response.data.options
      : {},
  };
}


/* ============================================================
   EXPORT
   ============================================================ */


function getFilenameFromDisposition(
  disposition,
) {
  if (!disposition) {
    return null;
  }

  const utfMatch = disposition.match(
    /filename\*=UTF-8''([^;]+)/i
  );

  if (utfMatch?.[1]) {
    return decodeURIComponent(
      utfMatch[1]
    );
  }

  const regularMatch = disposition.match(
    /filename="?([^"]+)"?/i
  );

  return regularMatch?.[1] || null;
}


export async function exportIPriceSnapshot(
  snapshotId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/export/`
    ),
    {
      responseType: "blob",
    },
  );

  const filename = (
    getFilenameFromDisposition(
      response.headers[
        "content-disposition"
      ]
    )
    || `iprice_snapshot_${snapshotId}.xlsx`
  );

  return {
    blob: response.data,
    filename,
  };
}


export function downloadBlob(
  blob,
  filename,
) {
  const objectUrl = URL.createObjectURL(
    blob
  );

  const link = document.createElement(
    "a"
  );

  link.href = objectUrl;
  link.download = filename;
  link.style.display = "none";

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
  }, 1000);
}


/* ============================================================
   IPRICE DATA UPLOADS AND EXPORTS
   ============================================================ */


const IPRICE_UPLOAD_URLS = {
  transport_cost: (
    `${IPRICE_BASE_URL}`
    + "/transport-cost/upload/"
  ),

  product_cost: (
    `${IPRICE_BASE_URL}`
    + "/product-cost/upload/"
  ),

  calculation_config: (
    `${IPRICE_BASE_URL}`
    + "/calculation-config/upload/"
  ),

  parser_prefixes: (
    `${DATASETS_BASE_URL}`
    + "/parsers/prefixes/upload/"
  ),

  product_classification: (
    `${DATASETS_BASE_URL}`
    + "/parsers/product-classification/upload/"
  ),

  product_directory: (
    `${DATASETS_BASE_URL}`
    + "/parsers/product-directory/upload/"
  ),
};


const IPRICE_EXPORT_URLS = {
  product_control: (
    `${DATASETS_BASE_URL}`
    + "/parsers/product-url-control/export/"
  ),

  product_cost_template: (
    `${IPRICE_BASE_URL}`
    + "/product-cost-template/export/"
  ),

  parser_products: (
    `${IPRICE_BASE_URL}`
    + "/parser-products/export/"
  ),

  preparation_check: (
    `${IPRICE_BASE_URL}`
    + "/preparation-check/export/"
  ),
};


function buildDefaultExportFilename(
  exportType,
) {
  const timestamp = new Date()
    .toISOString()
    .slice(0, 19)
    .replaceAll(":", "-");

  const filenames = {
    product_control: (
      `parser_product_url_control_${timestamp}.xlsx`
    ),
    product_cost_template: (
      `iprice_product_cost_template_${timestamp}.xlsx`
    ),

    parser_products: (
      `iprice_parser_products_${timestamp}.xlsx`
    ),

    preparation_check: (
      `iprice_preparation_check_${timestamp}.xlsx`
    ),
  };

  return (
    filenames[exportType]
    || `iprice_export_${timestamp}.xlsx`
  );
}


export async function uploadIPriceDataFile(
  uploadType,
  file,
  {
    fieldName = "file",
    additionalData = {},
    onUploadProgress,
  } = {},
) {
  const url = IPRICE_UPLOAD_URLS[
    uploadType
  ];

  if (!url) {
    throw new Error(
      `Unknown upload type: ${uploadType}`
    );
  }

  if (!(file instanceof File)) {
    throw new Error(
      "A valid file is required"
    );
  }

  const formData = new FormData();

  formData.append(
    fieldName,
    file,
  );

  Object.entries(
    additionalData || {},
  ).forEach(([
    key,
    value,
  ]) => {
    if (
      value === null
      || value === undefined
    ) {
      return;
    }

    formData.append(
      key,
      String(value),
    );
  });

  const response = await api.post(
    url,
    formData,
    {
      headers: {
        "Content-Type": (
          "multipart/form-data"
        ),
      },

      onUploadProgress:
        typeof onUploadProgress
          === "function"
          ? onUploadProgress
          : undefined,
    },
  );

  return response.data;
}


export async function getProductClassificationRunStatus() {
  const response = await api.get(
    `${DATASETS_BASE_URL}/parsers/product-directory/upload/`,
  );

  return response.data || { status: "not_started" };
}


export async function exportIPriceDataFile(
  exportType,
) {
  const url = IPRICE_EXPORT_URLS[
    exportType
  ];

  if (!url) {
    throw new Error(
      `Unknown export type: ${exportType}`
    );
  }

  const response = await api.get(
    url,
    {
      responseType: "blob",
    },
  );

  const filename = (
    getFilenameFromDisposition(
      response.headers[
        "content-disposition"
      ]
    )
    || buildDefaultExportFilename(
      exportType
    )
  );

  return {
    blob: response.data,
    filename,
  };
}


export async function exportIPriceUploadTemplate(
  uploadType,
) {
  if (!IPRICE_UPLOAD_URLS[uploadType]) {
    throw new Error(
      `Unknown upload type: ${uploadType}`
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/upload-templates/${uploadType}/export/`
    ),
    {
      responseType: "blob",
    },
  );

  const filename = (
    getFilenameFromDisposition(
      response.headers[
        "content-disposition"
      ],
    )
    || `iprice_${uploadType}_template.xlsx`
  );

  return {
    blob: response.data,
    filename,
  };
}


/* ============================================================
   PARSER MASTER PIPELINE
   ============================================================ */


export async function getParserMasterRunStatus() {
  const response = await api.get(
    (
      `${DATASETS_BASE_URL}`
      + "/parsers/master/run/"
    ),
  );

  return {
    activeRun: (
      response.data?.active_run
      || null
    ),

    latestRun: (
      response.data?.latest_run
      || null
    ),
  };
}


export async function runParserMasterPipeline() {
  const response = await api.post(
    (
      `${DATASETS_BASE_URL}`
      + "/parsers/master/run/"
    ),
    {},
  );

  return {
    status: (
      response.data?.status
      || ""
    ),

    message: (
      response.data?.message
      || ""
    ),

    run: (
      response.data?.run
      || null
    ),
  };
}


/* ============================================================
   IPRICE HEALTH
   ============================================================ */


export async function getIPriceHealth({
  level = "all",
  sections = [],
  issueGroups = [],
  errorCodes = [],
  search = "",
  page = 1,
  pageSize = 50,
  forceRefresh = false,
} = {}) {
  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + "/data/health/"
    ),
    {
      level,
      sections: Array.isArray(sections)
        ? sections
        : [],
      issue_groups: Array.isArray(
        issueGroups
      )
        ? issueGroups
        : [],
      error_codes: Array.isArray(
        errorCodes
      )
        ? errorCodes
        : [],
      search: String(
        search || ""
      ).trim(),
      page,
      page_size: pageSize,
      force_refresh: Boolean(
        forceRefresh
      ),
    },
  );

  const summary = (
    response.data?.summary
    && typeof response.data.summary
      === "object"
  )
    ? response.data.summary
    : {};

  const selected = (
    response.data?.selected
    && typeof response.data.selected
      === "object"
  )
    ? response.data.selected
    : {};

  const filterOptions = (
    response.data?.filter_options
    && typeof response.data.filter_options
      === "object"
  )
    ? response.data.filter_options
    : {};

  return {
    summary: {
      sectionsCount: Number(
        summary.sections_count || 0
      ),
      checkedTotal: Number(
        summary.checked_total || 0
      ),
      issuesTotal: Number(
        summary.issues_total || 0
      ),
      errorsTotal: Number(
        summary.errors_total || 0
      ),
      warningsTotal: Number(
        summary.warnings_total || 0
      ),
      healthySections: Number(
        summary.healthy_sections || 0
      ),
      problemSections: Number(
        summary.problem_sections || 0
      ),
      issueGroups: Array.isArray(
        summary.issue_groups
      )
        ? summary.issue_groups
        : [],
      errorCodes: Array.isArray(
        summary.error_codes
      )
        ? summary.error_codes
        : [],
    },

    sections: Array.isArray(
      response.data?.sections
    )
      ? response.data.sections
      : [],

    filterOptions: {
      levels: Array.isArray(
        filterOptions.levels
      )
        ? filterOptions.levels
        : [],

      sections: Array.isArray(
        filterOptions.sections
      )
        ? filterOptions.sections
        : [],

      issueGroups: Array.isArray(
        filterOptions.issue_groups
      )
        ? filterOptions.issue_groups
        : [],

      errorCodes: Array.isArray(
        filterOptions.error_codes
      )
        ? filterOptions.error_codes
        : [],
    },

    selected: {
      level: (
        selected.level
        || level
      ),

      sections: Array.isArray(
        selected.sections
      )
        ? selected.sections
        : [],

      issueGroups: Array.isArray(
        selected.issue_groups
      )
        ? selected.issue_groups
        : [],

      errorCodes: Array.isArray(
        selected.error_codes
      )
        ? selected.error_codes
        : [],

      search: (
        selected.search
        || search
      ),
    },

    count: Number(
      response.data?.count || 0
    ),

    page: Number(
      response.data?.page || page
    ),

    pageSize: Number(
      response.data?.page_size
      || pageSize
    ),

    totalPages: Number(
      response.data?.total_pages || 0
    ),

    hasNext: Boolean(
      response.data?.has_next
    ),

    hasPrevious: Boolean(
      response.data?.has_previous
    ),

    results: Array.isArray(
      response.data?.results
    )
      ? response.data.results
      : [],
  };
}


/* ============================================================
   SNAPSHOT ROWS AND FILTERS
   ============================================================ */


export async function getIPriceSnapshotRows(
  snapshotId,
  {
    mode = "products",
    page = 1,
    pageSize = 50,
    ordering = "",
    search = "",
    filters = {},
  } = {},
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/rows/`
    ),
    {
      mode,
      page,
      page_size: pageSize,
      ordering,
      search,
      filters,
    },
  );

  return {
    count: Number(
      response.data?.count || 0
    ),
    totalPages: Number(
      response.data?.total_pages || 0
    ),
    page: Number(
      response.data?.page || page
    ),
    pageSize: Number(
      response.data?.page_size
      || pageSize
    ),
    hasNext: Boolean(
      response.data?.has_next
    ),
    hasPrevious: Boolean(
      response.data?.has_previous
    ),
    mode: (
      response.data?.mode
      || mode
    ),
    snapshotId: (
      response.data?.snapshot_id
      || snapshotId
    ),
    results: Array.isArray(
      response.data?.results
    )
      ? response.data.results
      : [],
  };
}


export async function changeIPriceSnapshotParameters(
  snapshotId,
  payload,
) {
  const response = await api.post(
    `${IPRICE_BASE_URL}/snapshots/${snapshotId}/parameters/`,
    payload,
  );
  return response.data;
}


export async function getIPriceSnapshotFilters(
  snapshotId,
  {
    mode = "products",
    filters = {},
  } = {},
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}/filters/`
    ),
    {
      mode,
      filters,
    },
  );

  return {
    snapshotId: (
      response.data?.snapshot_id
      || snapshotId
    ),
    mode: (
      response.data?.mode
      || mode
    ),
    selected: (
      response.data?.selected
      && typeof response.data.selected
        === "object"
    )
      ? response.data.selected
      : {},
    options: (
      response.data?.options
      && typeof response.data.options
        === "object"
    )
      ? response.data.options
      : {},
  };
}


/* ============================================================
   PRODUCT DETAIL AND MARKET ASSORTMENT
   ============================================================ */


export async function getIPriceSnapshotProductDetail(
  snapshotId,
  productId,
  {
    saleRegions = [],
    departures = [],
  } = {},
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  if (!productId) {
    throw new Error(
      "productId is required"
    );
  }

  const params = new URLSearchParams();

  saleRegions.forEach((value) => {
    params.append(
      "sale_region",
      value,
    );
  });

  departures.forEach((value) => {
    params.append(
      "departure",
      value,
    );
  });

  const queryString = params.toString();

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}`
      + `/products/${productId}/`
      + (
        queryString
          ? `?${queryString}`
          : ""
      )
    ),
  );

  return response.data;
}


export async function getIPriceMarketAssortment(
  snapshotId,
  productId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  if (!productId) {
    throw new Error(
      "productId is required"
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}`
      + `/products/${productId}`
      + "/market-assortment/"
    ),
  );

  return response.data;
}


export async function updateIPriceCompetitorSelection(
  snapshotId,
  productId,
  payload,
) {
  if (!snapshotId || !productId) {
    throw new Error("snapshotId and productId are required");
  }
  const response = await api.post(
    `${IPRICE_BASE_URL}/snapshots/${snapshotId}/products/${productId}/competitor-selection/`,
    payload,
  );
  return response.data || {};
}


export async function getIPriceOwnAssortment(
  snapshotId,
  productId,
) {
  if (!snapshotId || !productId) {
    throw new Error(
      "snapshotId and productId are required"
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}`
      + `/products/${productId}`
      + "/own-assortment/"
    ),
  );

  return response.data;
}


/* ============================================================
   REGION APPROVALS
   ============================================================ */


export async function saveIPriceRegionApproval(
  snapshotId,
  regionId,
  {
    approvedRrp,
    comment = "",
  },
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  if (!regionId) {
    throw new Error(
      "regionId is required"
    );
  }

  const response = await api.post(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}`
      + `/regions/${regionId}`
      + "/approval/"
    ),
    {
      approved_rrp: approvedRrp,
      comment,
    },
  );

  return response.data;
}


export async function getIPriceRegionApprovalHistory(
  snapshotId,
  regionId,
) {
  if (!snapshotId) {
    throw new Error(
      "snapshotId is required"
    );
  }

  if (!regionId) {
    throw new Error(
      "regionId is required"
    );
  }

  const response = await api.get(
    (
      `${IPRICE_BASE_URL}`
      + `/snapshots/${snapshotId}`
      + `/regions/${regionId}`
      + "/approval-history/"
    ),
  );

  return {
    snapshotId,
    regionId,

    approvals: Array.isArray(
      response.data?.approvals
    )
      ? response.data.approvals
      : (
          Array.isArray(
            response.data?.results
          )
            ? response.data.results
            : []
        ),
  };
}
