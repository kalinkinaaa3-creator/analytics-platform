import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DashboardRenderer } from "../dashboards/DashboardRenderer";

export function PublicDashboardPage() {
  const { token, dashboardSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState(null);
  const [errorStatus, setErrorStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const filtersKey = searchParams.toString();

  useEffect(() => {
    async function loadDashboard() {
      setLoading(true);
      setErrorStatus(null);

      try {
        const response = await api.get(
          `/v1/dashboards/public-group/${token}/dashboard/${dashboardSlug}/?${filtersKey}`
        );
        setData(response.data);
      } catch (error) {
        setErrorStatus(error.response?.status || 500);
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, [token, dashboardSlug, filtersKey]);

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

  if (loading && !data) return <div>Загрузка...</div>;

  if (errorStatus) return <div>Ошибка загрузки публичного dashboard</div>;

  return (
    <DashboardRenderer
      data={data}
      loading={loading}
      onFiltersChange={handleFiltersChange}
    />
  );
}