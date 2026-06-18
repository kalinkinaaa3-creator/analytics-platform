import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";

export function PublicDashboardPage() {

  const [data, setData] = useState(null);
  const [errorStatus, setErrorStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const { token, dashboardSlug } = useParams();

  useEffect(() => {
    async function loadDashboard() {
      setLoading(true);
      setErrorStatus(null);

      try {
        const response = await api.get(`/v1/dashboards/public-group/${token}/dashboard/${dashboardSlug}/`);
        setData(response.data);
      } catch (error) {
        setErrorStatus(error.response?.status || 500);
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, [token, dashboardSlug]);

  if (loading) return <div>Загрузка...</div>;
  if (errorStatus) return <div>Ошибка загрузки публичного dashboard</div>;

  return (
    <>
      <h2>{data?.dashboard?.name}</h2>

      <pre
        style={{
          background: "#fff",
          padding: "20px",
          borderRadius: "8px",
          overflow: "auto",
          maxHeight: "75vh",
        }}
      >
        {JSON.stringify(data, null, 2)}
      </pre>
    </>
  );
}