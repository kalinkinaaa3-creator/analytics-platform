import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Navigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DashboardRenderer } from "../dashboards/DashboardRenderer";

function buildDashboardWsUrl() {
  const baseURL = api.defaults.baseURL || window.location.origin;
  const url = new URL(baseURL, window.location.origin);

  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/dashboards/";
  url.search = "";

  return url.toString();
}

export function DashboardPage() {
  const { dashboardSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState(null);
  const [errorStatus, setErrorStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const filtersKey = searchParams.toString();
  const loadDashboardRef = useRef(null);

  const loadDashboard = useCallback(
    async ({ showSpinner = true } = {}) => {
      if (showSpinner) {
        setLoading(true);
      }

      setErrorStatus(null);

      try {
        const response = await api.get(
          `/v1/dashboards/builder/${dashboardSlug}/?${filtersKey}`
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
    [dashboardSlug, filtersKey]
  );

  useEffect(() => {
    loadDashboardRef.current = loadDashboard;
  }, [loadDashboard]);

  useEffect(() => {
    loadDashboard({ showSpinner: true });
  }, [loadDashboard]);

  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;
    let stopped = false;
    let reconnectAttempt = 0;

    function connect() {
      const access = localStorage.getItem("access");

      if (!access) {
        console.warn("Dashboard WebSocket skipped: no access token");
        return;
      }

      const wsUrl = buildDashboardWsUrl();
      socket = new WebSocket(`${wsUrl}?token=${encodeURIComponent(access)}`);

      socket.onopen = () => {
        reconnectAttempt = 0;
        console.log("Dashboard WebSocket connected");
      };

      socket.onmessage = (event) => {
        let message = null;

        try {
          message = JSON.parse(event.data);
        } catch (error) {
          console.error("Dashboard WebSocket invalid message:", error);
          return;
        }

        if (
          message.type === "dashboard_updated" &&
          message.dashboard === "PlannedSales"
        ) {
          loadDashboardRef.current?.({ showSpinner: false });
        }
      };

      socket.onerror = (error) => {
        console.error("Dashboard WebSocket error:", error);
      };

      socket.onclose = (event) => {
        console.log("Dashboard WebSocket closed:", event.code, event.reason);

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
      if (value) {
        nextParams.set(key, value);
      } else {
        nextParams.delete(key);
      }
    });

    setSearchParams(nextParams);
  }

  if (errorStatus === 403) {
    return <Navigate to="/access-denied" replace />;
  }

  if (errorStatus) return <div>Ошибка загрузки dashboard</div>;

  return (
    <DashboardRenderer
      data={data}
      loading={loading}
      onFiltersChange={handleFiltersChange}
    />
  );
}