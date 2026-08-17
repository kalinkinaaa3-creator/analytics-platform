import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  Navigate,
  useSearchParams,
} from "react-router-dom";

import {
  activateIPriceSnapshot,
  deactivateIPriceSnapshot,
  downloadBlob,
  exportIPriceSnapshot,
  getIPriceAccess,
  getIPriceSnapshots,
  runIPriceSnapshot,
} from "./api/ipriceApi";

import {
  IPriceSnapshotHeader,
} from "./components/IPriceSnapshotHeader";

import {
  IPriceCalculationTab,
} from "./calculation/IPriceCalculationTab";

import {
  IPriceAnalyticsTab,
} from "./analytics/IPriceAnalyticsTab";

import {
  IPriceHistoryTab,
} from "./history/IPriceHistoryTab";

import {
  IPriceProductDrawer,
} from "./product/IPriceProductDrawer";

import {
  IPriceToast,
} from "./components/IPriceToast";

import {
  IPriceTabs,
} from "./IPriceTabs";

import {
  IPriceDataTab,
} from "./data/IPriceDataTab";

import "./iprice.css";
import "../dashboards/spinner.css";
import { api } from "../api/client";


const DEFAULT_TAB = "analytics";

const ALLOWED_TABS = new Set([
  "analytics",
  "calculation",
  "history",
  "data",
]);


function buildIPriceWsUrl() {
  const baseURL = (
    api.defaults.baseURL
    || window.location.origin
  );
  const url = new URL(
    baseURL,
    window.location.origin,
  );

  url.protocol = (
    url.protocol === "https:"
      ? "wss:"
      : "ws:"
  );
  url.pathname = "/ws/dashboards/";
  url.search = "";

  return url.toString();
}


/* ============================================================
   NORMALIZATION
   ============================================================ */


function normalizeTab(value) {
  if (
    value
    && ALLOWED_TABS.has(value)
  ) {
    return value;
  }

  return DEFAULT_TAB;
}


function normalizePositiveInteger(value) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return null;
  }

  const normalizedValue = Number(value);

  if (
    !Number.isInteger(normalizedValue)
    || normalizedValue <= 0
  ) {
    return null;
  }

  return normalizedValue;
}


function selectDefaultSnapshot(
  snapshots,
) {
  if (
    !Array.isArray(snapshots)
    || snapshots.length === 0
  ) {
    return null;
  }

  const activeSnapshot = snapshots.find(
    (snapshot) => (
      snapshot.is_active
    )
  );

  if (activeSnapshot) {
    return activeSnapshot;
  }

  const latestSnapshot = snapshots.find(
    (snapshot) => (
      snapshot.is_latest
    )
  );

  if (latestSnapshot) {
    return latestSnapshot;
  }

  const currentSuccessfulSnapshot = (
    snapshots.find(
      (snapshot) => (
        snapshot.is_current
        && snapshot.status === "success"
      )
    )
  );

  if (currentSuccessfulSnapshot) {
    return currentSuccessfulSnapshot;
  }

  return snapshots[0];
}


function getApiErrorMessage(
  error,
  fallbackMessage,
) {
  return (
    error?.response?.data?.message
    || error?.response?.data?.detail
    || error?.message
    || fallbackMessage
  );
}


function renderTabContent({
  activeTab,
  selectedSnapshot,
  selectedSnapshotId,
  snapshots,
  loadingSnapshots,
  activatingSnapshotId,
  exportingSnapshotId,
  onOpenProduct,
  onOpenPricingSelection,
  onOpenSnapshot,
  onActivateSnapshot,
  onExportSnapshot,
  regionApprovalEvent,
  realtimeEvent,
  onSnapshotsChanged,
  canEdit,
}) {
  switch (activeTab) {
    case "calculation":
      return (
        <IPriceCalculationTab
          snapshot={selectedSnapshot}
          onOpenProduct={onOpenProduct}
          regionApprovalEvent={regionApprovalEvent}
          realtimeEvent={realtimeEvent}
          canEdit={canEdit}
        />
      );

    case "history":
      return (
        <IPriceHistoryTab
          snapshots={snapshots}
          selectedSnapshotId={
            selectedSnapshotId
          }
          loading={loadingSnapshots}
          realtimeEvent={realtimeEvent}
          onOpenProduct={onOpenProduct}
        />
      );

    case "data":
      return (
        <IPriceDataTab
          canEdit={canEdit}
          snapshots={snapshots}
          selectedSnapshotId={
            selectedSnapshotId
          }
          onSnapshotsChanged={
            onSnapshotsChanged
          }
          realtimeEvent={realtimeEvent}
        />
      );

    case "analytics":
    default:
      return (
        <IPriceAnalyticsTab
          snapshot={selectedSnapshot}
          onOpenProduct={onOpenProduct}
          onOpenPricingSelection={onOpenPricingSelection}
          realtimeEvent={realtimeEvent}
          canEdit={canEdit}
        />
      );
  }
}


/* ============================================================
   PAGE
   ============================================================ */


export function IPricePage() {
  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams();


  const tabFromUrl = normalizeTab(
    searchParams.get("tab")
  );

  const snapshotIdFromUrl = (
    normalizePositiveInteger(
      searchParams.get("snapshot")
    )
  );

  const productIdFromUrl = (
    normalizePositiveInteger(
      searchParams.get("product")
    )
  );


  const [
    access,
    setAccess,
  ] = useState(null);

  const [
    accessDenied,
    setAccessDenied,
  ] = useState(false);

  const [
    activeTab,
    setActiveTab,
  ] = useState(tabFromUrl);

  const [
    snapshots,
    setSnapshots,
  ] = useState([]);

  const [
    selectedSnapshotId,
    setSelectedSnapshotId,
  ] = useState(
    snapshotIdFromUrl
  );

  const [
    openedProductId,
    setOpenedProductId,
  ] = useState(
    productIdFromUrl
  );

  const [
    loadingSnapshots,
    setLoadingSnapshots,
  ] = useState(true);

  const [
    snapshotsError,
    setSnapshotsError,
  ] = useState("");

  const [
    runningSnapshot,
    setRunningSnapshot,
  ] = useState(false);

  const [
    activatingSnapshotId,
    setActivatingSnapshotId,
  ] = useState(null);

  const [
    exportingSnapshotId,
    setExportingSnapshotId,
  ] = useState(null);

  const [
    toast,
    setToast,
  ] = useState({
    message: "",
    type: "success",
  });


  const [
    regionApprovalEvent,
    setRegionApprovalEvent,
  ] = useState(null);

  const [
    realtimeEvent,
    setRealtimeEvent,
  ] = useState(null);

  const loadSnapshotsRef = useRef(null);


  const selectedSnapshot = useMemo(
    () => (
      snapshots.find(
        (snapshot) => (
          snapshot.id
          === selectedSnapshotId
        )
      ) || null
    ),
    [
      snapshots,
      selectedSnapshotId,
    ],
  );


  /* ============================================================
     NOTIFICATIONS
     ============================================================ */


  const showToast = useCallback(
    (
      message,
      type = "success",
    ) => {
      setToast({
        message,
        type,
      });
    },
    [],
  );


  const closeToast = useCallback(
    () => {
      setToast({
        message: "",
        type: "success",
      });
    },
    [],
  );


  /* ============================================================
     URL
     ============================================================ */


  const updateMainUrlParams = useCallback(
    ({
      tab,
      snapshotId,
      removeProduct = false,
      removeAnalyticsState = false,
      removeCalculationState = false,
      replace = true,
    }) => {
      setSearchParams(
        (previousParams) => {
          const nextParams = (
            new URLSearchParams(
              previousParams
            )
          );

          const normalizedTab = normalizeTab(
            tab
          );

          if (
            normalizedTab
            === DEFAULT_TAB
          ) {
            nextParams.delete("tab");
          } else {
            nextParams.set(
              "tab",
              normalizedTab
            );
          }

          const normalizedSnapshotId = (
            normalizePositiveInteger(
              snapshotId
            )
          );

          if (normalizedSnapshotId) {
            nextParams.set(
              "snapshot",
              String(
                normalizedSnapshotId
              )
            );
          } else {
            nextParams.delete(
              "snapshot"
            );
          }

          if (removeProduct) {
            nextParams.delete(
              "product"
            );
          }

          if (removeAnalyticsState) {
            Array.from(nextParams.keys()).forEach((key) => {
              if (
                key === "a_search"
                || key.startsWith("af_")
                || key.startsWith("ad_")
              ) {
                nextParams.delete(key);
              }
            });
          }


          if (normalizedTab !== "calculation") {
            nextParams.delete("c_selection");
            nextParams.delete("c_product_key");
          }

          if (removeCalculationState) {
            nextParams.delete("c_selection");
            nextParams.delete("c_product_key");
          }

          return nextParams;
        },
        {
          replace,
        },
      );
    },
    [
      setSearchParams,
    ],
  );


  const setProductUrlParam = useCallback(
    (
      productId,
      {
        replace = true,
      } = {},
    ) => {
      setSearchParams(
        (previousParams) => {
          const nextParams = (
            new URLSearchParams(
              previousParams
            )
          );

          const normalizedProductId = (
            normalizePositiveInteger(
              productId
            )
          );

          if (normalizedProductId) {
            nextParams.set(
              "product",
              String(
                normalizedProductId
              )
            );
          } else {
            nextParams.delete(
              "product"
            );
          }

          return nextParams;
        },
        {
          replace,
        },
      );
    },
    [
      setSearchParams,
    ],
  );


  /* ============================================================
     SNAPSHOT LIST
     ============================================================ */


  const loadSnapshots = useCallback(
    async () => {
      setLoadingSnapshots(true);
      setSnapshotsError("");

      try {
        const result = (
          await getIPriceSnapshots()
        );

        setSnapshots(
          Array.isArray(result.results)
            ? result.results
            : []
        );
      } catch (error) {
        console.error(
          "Failed to load iPrice:",
          error
        );

        setSnapshots([]);
        setSelectedSnapshotId(null);
        setOpenedProductId(null);

        setSnapshotsError(
          getApiErrorMessage(
            error,
            (
              "Не удалось загрузить "
              + "версии iPrice."
            ),
          )
        );
      } finally {
        setLoadingSnapshots(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadSnapshotsRef.current = loadSnapshots;
  }, [loadSnapshots]);


  const upsertSnapshot = useCallback(
    (
      nextSnapshot,
      {
        markAsLatest = false,
      } = {},
    ) => {
      if (!nextSnapshot?.id) {
        return;
      }

      setSnapshots((previous) => {
        const alreadyExists = (
          previous.some(
            (snapshot) => (
              snapshot.id
              === nextSnapshot.id
            )
          )
        );

        const updatedSnapshots = (
          previous.map(
            (snapshot) => {
              if (
                snapshot.id
                === nextSnapshot.id
              ) {
                return {
                  ...snapshot,
                  ...nextSnapshot,
                  is_latest: Boolean(
                    markAsLatest
                    || nextSnapshot.is_latest
                  ),
                };
              }

              if (markAsLatest) {
                return {
                  ...snapshot,
                  is_latest: false,
                };
              }

              return snapshot;
            }
          )
        );

        if (alreadyExists) {
          return updatedSnapshots;
        }

        return [
          {
            ...nextSnapshot,
            is_latest: Boolean(
              markAsLatest
              || nextSnapshot.is_latest
            ),
          },
          ...updatedSnapshots,
        ];
      });
    },
    [],
  );


  const applyActivatedSnapshot = useCallback(
    (
      activatedSnapshot,
    ) => {
      if (!activatedSnapshot?.id) {
        return;
      }

      setSnapshots((previous) => (
        previous.map(
          (snapshot) => {
            if (
              snapshot.id
              === activatedSnapshot.id
            ) {
              return {
                ...snapshot,
                ...activatedSnapshot,
                is_active: true,
              };
            }

            if (snapshot.is_active) {
              return {
                ...snapshot,
                is_active: false,
              };
            }

            return snapshot;
          }
        )
      ));
    },
    [],
  );


  const applyDeactivatedSnapshot = useCallback(
    (deactivatedSnapshot) => {
      if (!deactivatedSnapshot?.id) {
        return;
      }
      setSnapshots((previous) => (
        previous.map((snapshot) => (
          snapshot.id === deactivatedSnapshot.id
            ? {
                ...snapshot,
                ...deactivatedSnapshot,
                is_active: false,
              }
            : snapshot
        ))
      ));
    },
    [],
  );


  /* ============================================================
     SYNCHRONIZATION EFFECTS
     ============================================================ */


  useEffect(() => {
    let cancelled = false;

    async function loadAccess() {
      try {
        const result = await getIPriceAccess();

        if (!cancelled) {
          setAccess(result);
        }
      } catch (error) {
        if (
          !cancelled
          && error?.response?.status === 403
        ) {
          setAccessDenied(true);
        } else if (
          !cancelled
          && error?.response?.status !== 401
        ) {
          setSnapshotsError(
            getApiErrorMessage(
              error,
              "Не удалось проверить доступ к iPrice.",
            )
          );
          setLoadingSnapshots(false);
        }
      }
    }

    loadAccess();

    return () => {
      cancelled = true;
    };
  }, []);


  useEffect(() => {
    setActiveTab(tabFromUrl);
  }, [
    tabFromUrl,
  ]);


  useEffect(() => {
    setOpenedProductId(
      productIdFromUrl
    );
  }, [
    productIdFromUrl,
  ]);


  useEffect(() => {
    if (!access) {
      return;
    }

    loadSnapshots();
  }, [
    access,
    loadSnapshots,
  ]);


  useEffect(() => {
    if (!access) {
      return undefined;
    }

    let socket = null;
    let reconnectTimer = null;
    let stopped = false;
    let reconnectAttempt = 0;

    function connect() {
      const token = localStorage.getItem("access");
      const suffix = token
        ? `?token=${encodeURIComponent(token)}`
        : "";

      socket = new WebSocket(
        `${buildIPriceWsUrl()}${suffix}`
      );

      socket.onopen = () => {
        reconnectAttempt = 0;
        console.log(
          "iPrice WebSocket connected"
        );
      };

      socket.onmessage = (event) => {
        let message;

        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        if (
          message.type !== "dashboard_updated"
          || message.dashboard !== "IPrice"
        ) {
          return;
        }

        setRealtimeEvent({
          ...message,
          receivedAt: Date.now(),
        });

        if (
          String(message.change_type || "")
            .startsWith("snapshot_")
        ) {
          loadSnapshotsRef.current?.();
        }
      };

      socket.onerror = (error) => {
        console.error(
          "iPrice WebSocket error:",
          error,
        );
      };

      socket.onclose = (event) => {
        console.log(
          "iPrice WebSocket closed:",
          event.code,
          event.reason,
        );

        if (stopped) {
          return;
        }

        reconnectAttempt += 1;
        reconnectTimer = window.setTimeout(
          connect,
          Math.min(30000, 1000 * (2 ** reconnectAttempt)),
        );
      };
    }

    connect();

    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [access]);


  /*
   * Список snapshot загружается один раз.
   * При изменении параметра snapshot повторный
   * backend-запрос списка не выполняется.
   */
  useEffect(() => {
    if (
      loadingSnapshots
      || snapshots.length === 0
    ) {
      return;
    }

    const snapshotFromUrl = (
      snapshots.find(
        (snapshot) => (
          snapshot.id
          === snapshotIdFromUrl
        )
      )
    );

    const nextSelectedSnapshot = (
      snapshotFromUrl
      || selectDefaultSnapshot(
        snapshots
      )
    );

    const nextSnapshotId = (
      nextSelectedSnapshot?.id
      || null
    );

    setSelectedSnapshotId(
      (previousSnapshotId) => (
        previousSnapshotId
        === nextSnapshotId
          ? previousSnapshotId
          : nextSnapshotId
      )
    );

    if (
      nextSnapshotId
      !== snapshotIdFromUrl
    ) {
      setOpenedProductId(null);

      updateMainUrlParams({
        tab: tabFromUrl,
        snapshotId: nextSnapshotId,
        removeProduct: true,
        removeCalculationState: true,
      });
    }
  }, [
    loadingSnapshots,
    snapshots,
    snapshotIdFromUrl,
    tabFromUrl,
    updateMainUrlParams,
  ]);


  /* ============================================================
     NAVIGATION
     ============================================================ */


  function changeTab(nextTab) {
    const normalizedTab = normalizeTab(
      nextTab
    );

    setActiveTab(normalizedTab);

    updateMainUrlParams({
      tab: normalizedTab,
      snapshotId: selectedSnapshotId,
      removeProduct: false,
      removeAnalyticsState: normalizedTab !== "analytics",
    });
  }


  function openPricingSelection(selection) {
    if (!selection?.token) return;
    setOpenedProductId(null);
    setActiveTab("calculation");
    setSearchParams((previousParams) => {
      const nextParams = new URLSearchParams(previousParams);
      nextParams.set("tab", "calculation");
      nextParams.set("snapshot", String(selectedSnapshotId));
      nextParams.set("c_selection", selection.token);
      nextParams.delete("c_product_key");
      nextParams.delete("product");
      Array.from(nextParams.keys()).forEach((key) => {
        if (key === "a_search" || key.startsWith("af_") || key.startsWith("ad_")) {
          nextParams.delete(key);
        }
      });
      return nextParams;
    });
  }


  function openProductPricing(productKey) {
    if (!productKey) return;
    setOpenedProductId(null);
    setActiveTab("calculation");
    setSearchParams((previousParams) => {
      const nextParams = new URLSearchParams(previousParams);
      nextParams.set("tab", "calculation");
      nextParams.set("snapshot", String(selectedSnapshotId));
      nextParams.set("c_product_key", String(productKey));
      nextParams.delete("c_selection");
      nextParams.delete("product");
      return nextParams;
    });
  }


  function changeSnapshot(
    nextSnapshotId,
  ) {
    const normalizedSnapshotId = (
      normalizePositiveInteger(
        nextSnapshotId
      )
    );

    if (
      normalizedSnapshotId
      === selectedSnapshotId
    ) {
      return;
    }

    setSelectedSnapshotId(
      normalizedSnapshotId
    );

    setOpenedProductId(null);

    updateMainUrlParams({
      tab: activeTab,
      snapshotId: normalizedSnapshotId,
      removeProduct: true,
      removeCalculationState: true,
    });
  }


  function openProduct(product, productSnapshotId = null) {
    const productId = (
      normalizePositiveInteger(
        product?.id
      )
    );

    if (!productId) {
      showToast(
        "Не удалось определить товар.",
        "error",
      );

      return;
    }

    setOpenedProductId(
      productId
    );

    const normalizedProductSnapshotId = normalizePositiveInteger(
      productSnapshotId
    );

    if (
      normalizedProductSnapshotId
      && normalizedProductSnapshotId !== selectedSnapshotId
    ) {
      setSelectedSnapshotId(normalizedProductSnapshotId);
      updateMainUrlParams({
        tab: activeTab,
        snapshotId: normalizedProductSnapshotId,
      });
    }

    setProductUrlParam(
      productId
    );
  }


  function closeProduct() {
    setOpenedProductId(null);

    setProductUrlParam(null);
  }


  const handleRegionApprovalSaved = useCallback(
    ({
      snapshotId,
      productId,
      regionId,
      approval,
      message,
    }) => {
      if (
        !snapshotId
        || !regionId
        || !approval
      ) {
        return;
      }

      setRegionApprovalEvent({
        eventId: `${regionId}-${approval.id || approval.revision || Date.now()}`,
        snapshotId,
        productId,
        regionId,
        approval,
      });

      showToast(
        message
        || "Утверждённая цена сохранена."
      );
    },
    [showToast],
  );


  /* ============================================================
     RUN SNAPSHOT
     ============================================================ */


  async function handleRunSnapshot(
    calculationDate,
  ) {
    setRunningSnapshot(true);

    try {
      const result = (
        await runIPriceSnapshot(
          calculationDate
        )
      );

      const nextSnapshot = (
        result.snapshot
      );

      if (nextSnapshot?.id) {
        upsertSnapshot(
          nextSnapshot,
          {
            markAsLatest: true,
          },
        );

        setSelectedSnapshotId(
          nextSnapshot.id
        );

        setOpenedProductId(null);

        updateMainUrlParams({
          tab: activeTab,
          snapshotId: nextSnapshot.id,
          removeProduct: true,
          removeCalculationState: true,
        });
      }

      showToast(
        result.message
        || "Расчёт iPrice запущен."
      );

      return true;
    } catch (error) {
      const responseData = (
        error.response?.data
      );

      const existingSnapshot = (
        responseData?.snapshot
      );

      if (existingSnapshot?.id) {
        upsertSnapshot(
          existingSnapshot,
          {
            markAsLatest: true,
          },
        );

        setSelectedSnapshotId(
          existingSnapshot.id
        );

        setOpenedProductId(null);

        updateMainUrlParams({
          tab: activeTab,
          snapshotId: existingSnapshot.id,
          removeProduct: true,
          removeCalculationState: true,
        });
      }

      showToast(
        responseData?.message
        || responseData?.detail
        || "Не удалось запустить расчёт.",
        "error",
      );

      return false;
    } finally {
      setRunningSnapshot(false);
    }
  }


  /* ============================================================
     ACTIVATE SNAPSHOT
     ============================================================ */


  async function handleActivateSnapshot(
    snapshotId = selectedSnapshotId,
  ) {
    const normalizedSnapshotId = (
      normalizePositiveInteger(
        snapshotId
      )
    );

    if (!normalizedSnapshotId) {
      showToast(
        "Версия расчёта не выбрана.",
        "error",
      );

      return false;
    }

    setActivatingSnapshotId(
      normalizedSnapshotId
    );

    try {
      const result = (
        await activateIPriceSnapshot(
          normalizedSnapshotId
        )
      );

      if (result.snapshot) {
        applyActivatedSnapshot(
          result.snapshot
        );
      }

      showToast(
        result.message
        || "Версия активирована."
      );

      return true;
    } catch (error) {
      showToast(
        getApiErrorMessage(
          error,
          (
            "Не удалось активировать "
            + "версию."
          ),
        ),
        "error",
      );

      return false;
    } finally {
      setActivatingSnapshotId(null);
    }
  }


  async function handleDeactivateSnapshot(
    snapshotId = selectedSnapshotId,
  ) {
    const normalizedSnapshotId = normalizePositiveInteger(snapshotId);
    if (!normalizedSnapshotId) {
      showToast("Версия расчёта не выбрана.", "error");
      return false;
    }

    setActivatingSnapshotId(normalizedSnapshotId);
    try {
      const result = await deactivateIPriceSnapshot(normalizedSnapshotId);
      if (result.snapshot) {
        applyDeactivatedSnapshot(result.snapshot);
      }
      showToast(result.message || "Версия деактивирована.");
      return true;
    } catch (error) {
      showToast(
        getApiErrorMessage(error, "Не удалось деактивировать версию."),
        "error",
      );
      return false;
    } finally {
      setActivatingSnapshotId(null);
    }
  }


  /* ============================================================
     EXPORT SNAPSHOT
     ============================================================ */


  async function handleExportSnapshot(
    snapshotId = selectedSnapshotId,
  ) {
    const normalizedSnapshotId = (
      normalizePositiveInteger(
        snapshotId
      )
    );

    if (!normalizedSnapshotId) {
      showToast(
        "Версия расчёта не выбрана.",
        "error",
      );

      return false;
    }

    setExportingSnapshotId(
      normalizedSnapshotId
    );

    try {
      const result = (
        await exportIPriceSnapshot(
          normalizedSnapshotId
        )
      );

      downloadBlob(
        result.blob,
        result.filename,
      );

      showToast(
        "Файл расчёта сформирован."
      );

      return true;
    } catch (error) {
      let message = (
        "Не удалось выгрузить расчёт."
      );

      const responseBlob = (
        error.response?.data
      );

      if (
        responseBlob instanceof Blob
      ) {
        try {
          const text = (
            await responseBlob.text()
          );

          if (text) {
            const data = JSON.parse(text);

            message = (
              data.message
              || data.detail
              || message
            );
          }
        } catch {
          // Ответ backend не является JSON.
        }
      } else {
        message = getApiErrorMessage(
          error,
          message,
        );
      }

      showToast(
        message,
        "error",
      );

      return false;
    } finally {
      setExportingSnapshotId(null);
    }
  }


  /* ============================================================
     RENDER
     ============================================================ */


  if (accessDenied) {
    return (
      <Navigate
        to="/access-denied"
        replace
      />
    );
  }

  const canEdit = Boolean(
    access?.can_edit
  );

  if (
    loadingSnapshots
    && snapshots.length === 0
  ) {
    return (
      <div className="global-spinner-overlay show">
        <div className="spinner-container">
          <div className="infinite-spinner" />
          <div className="spinner-text">
            Загрузка данных...
          </div>
        </div>
      </div>
    );
  }


  return (
    <div className="iprice-page">
      <h2>iPrice</h2>

      {snapshotsError && (
        <div className="iprice-page-error">
          <span>
            {snapshotsError}
          </span>

          <button
            type="button"
            onClick={loadSnapshots}
          >
            Повторить
          </button>
        </div>
      )}

      <IPriceSnapshotHeader
        canEdit={canEdit}
        snapshots={snapshots}
        selectedSnapshot={
          selectedSnapshot
        }
        selectedSnapshotId={
          selectedSnapshotId
        }
        loading={
          loadingSnapshots
        }
        running={
          runningSnapshot
        }
        activating={
          activatingSnapshotId
          === selectedSnapshotId
        }
        exporting={
          exportingSnapshotId
          === selectedSnapshotId
        }
        onSnapshotChange={
          changeSnapshot
        }
        onRun={
          handleRunSnapshot
        }
        onActivate={
          handleActivateSnapshot
        }
        onDeactivate={
          handleDeactivateSnapshot
        }
        onExport={
          handleExportSnapshot
        }
      />

      <IPriceTabs
        activeTab={activeTab}
        onChange={changeTab}
      />

      <main className="iprice-page-body">
        {renderTabContent({
          activeTab,
          selectedSnapshot,
          selectedSnapshotId,
          snapshots,
          loadingSnapshots,
          activatingSnapshotId,
          exportingSnapshotId,
          onOpenProduct: openProduct,
          onOpenPricingSelection: openPricingSelection,
          onOpenSnapshot: changeSnapshot,
          onActivateSnapshot: (snapshotId) => (
            handleActivateSnapshot(
              snapshotId
            )
          ),
          onExportSnapshot: (snapshotId) => (
            handleExportSnapshot(
              snapshotId
            )
          ),
          onSnapshotsChanged: loadSnapshots,
          regionApprovalEvent,
          realtimeEvent,
          canEdit,
        })}
      </main>

      {openedProductId
        && selectedSnapshotId && (
          <IPriceProductDrawer
            canEdit={canEdit}
            snapshotId={
              selectedSnapshotId
            }
            productId={
              openedProductId
            }
            onClose={
              closeProduct
            }
            onRegionApprovalSaved={
              handleRegionApprovalSaved
            }
            realtimeEvent={realtimeEvent}
            pricingEditable={Boolean(
              canEdit
              && selectedSnapshot?.status === "success"
              && selectedSnapshot?.is_latest
              && !selectedSnapshot?.is_active
            )}
            onOpenPricing={openProductPricing}
          />
        )}

      <IPriceToast
        message={toast.message}
        type={toast.type}
        onClose={closeToast}
      />
    </div>
  );
}
