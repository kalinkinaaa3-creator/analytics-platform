import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DashboardRenderer } from "../dashboards/DashboardRenderer";

const DASHBOARD_WS_NAMES = {
  "planned-sales": "PlannedSales",
  purchases: "Purchases",
  projects: "Projects",
  wordstat: "Wordstat",
  accreceiv: "Accreceiv",
  turnover: "Turnover",
};

function buildDashboardWsUrl() {
  const baseURL = api.defaults.baseURL || window.location.origin;
  const url = new URL(baseURL, window.location.origin);

  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/dashboards/";
  url.search = "";

  return url.toString();
}

export function PublicDashboardPage() {
  const { token, dashboardSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState(null);
  const [errorStatus, setErrorStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const filtersKey = searchParams.toString();

  const loadDashboardRef = useRef(null);
  const dashboardSlugRef = useRef(null);



  const defaultDatesReady = true;


  const loadDashboard = useCallback(
    async ({ showSpinner = true } = {}) => {
      if (!defaultDatesReady) {
        return;
      }

      if (showSpinner) {
        setLoading(true);
      }

      setErrorStatus(null);

      try {
        const response = await api.get(
          `/v1/dashboards/public-group/${token}/dashboard/${dashboardSlug}/?${filtersKey}${dashboardSlug === "wordstat" ? "&metadata_only=1" : ""}`
        );

        setData(response.data);
      } catch (error) {
        setErrorStatus(error.response?.status || 500);
      } finally {
        if (showSpinner) {
          setLoading(false);
        }
      }
    },
    [token, dashboardSlug, filtersKey, defaultDatesReady]
  );

  useEffect(() => {
    loadDashboardRef.current = loadDashboard;
  }, [loadDashboard]);

  useEffect(() => {
    dashboardSlugRef.current = dashboardSlug;
  }, [dashboardSlug]);





  useEffect(() => {
    const timer = setTimeout(() => loadDashboard({ showSpinner: true }), 0);
    return () => clearTimeout(timer);
  }, [loadDashboard]);

  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;
    let stopped = false;
    let reconnectAttempt = 0;

    function connect() {
      const wsUrl = buildDashboardWsUrl();
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        reconnectAttempt = 0;
        console.log("Public dashboard WebSocket connected");
      };

      socket.onmessage = (event) => {
        let message;

        try {
          message = JSON.parse(event.data);
        } catch (error) {
          console.error("Public dashboard WebSocket invalid message:", error);
          return;
        }

        if (message.type !== "dashboard_updated") {
          return;
        }

        const currentSlug = dashboardSlugRef.current;
        const expectedDashboardName = DASHBOARD_WS_NAMES[currentSlug];

        if (!expectedDashboardName) {
          return;
        }

        if (message.dashboard === expectedDashboardName) {
          loadDashboardRef.current?.({ showSpinner: false });
        }
      };

      socket.onerror = (error) => {
        console.error("Public dashboard WebSocket error:", error);
      };

      socket.onclose = (event) => {
        console.log(
          "Public dashboard WebSocket closed:",
          event.code,
          event.reason
        );

        if (stopped) {
          return;
        }

        const delay = Math.min(30000, 1000 * 2 ** reconnectAttempt);
        reconnectAttempt += 1;

        reconnectTimer = setTimeout(() => {
          connect();
        }, delay);
      };
    }

    connect();

    return () => {
      stopped = true;

      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }

      if (
        socket &&
        (socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close(1000, "component unmounted");
      }
    };
  }, []);

  function handleFiltersChange(filters) {
    const nextParams = new URLSearchParams(searchParams);

    Object.entries(filters).forEach(([key, value]) => {
      nextParams.delete(key);

      if (Array.isArray(value)) {
        value.forEach((item) => {
          if (item) {
            nextParams.append(key, item);
          }
        });

        return;
      }

      if (value) {
        nextParams.set(key, value);
      }
    });

    setSearchParams(nextParams);
  }

  if (errorStatus) {
    return <div>Ошибка загрузки публичного dashboard</div>;
  }

  return (
    <DashboardRenderer
      data={data}
      loading={loading}
      onFiltersChange={handleFiltersChange}
      publicToken={token}
    />
  );
}