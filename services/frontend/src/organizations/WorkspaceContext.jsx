import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { setOrganizationId } from "./storage";
import "./workspace.css";
import { WorkspaceContext } from "./useWorkspace";

export function WorkspaceProvider({ children }) {
  const { logout } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [error, setError] = useState("");
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api.get("/v1/organizations/", { signal: controller.signal }).then(({ data }) => {
      setOrganizationId(data.organization.id);
      setWorkspace(data);
    }).catch((err) => {
      if (err.code !== "ERR_CANCELED") setError(err.response?.data?.detail || "Не удалось загрузить рабочее пространство.");
    });
    return () => controller.abort();
  }, []);

  async function switchOrganization(id) {
    if (switching || String(id) === String(workspace.organization.id)) return;
    setSwitching(true);
    setError("");
    try {
      const { data } = await api.post("/v1/organizations/switch/", { organization_id: Number(id) });
      setOrganizationId(data.organization.id);
      // Discard requests, module caches, sockets, filters and mounted components.
      // Other browser tabs keep their own organization and remain untouched.
      window.location.assign("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Не удалось переключить организацию.");
      setSwitching(false);
    }
  }

  if (!workspace) return (
    <div className="workspace-loading" role="status">
      {error || "Загрузка рабочего пространства…"}
      {error && <div className="workspace-loading-actions">
        <button type="button" onClick={() => { setOrganizationId(null); window.location.assign("/"); }}>Открыть организацию по умолчанию</button>
        <button type="button" onClick={logout}>Выйти</button>
      </div>}
    </div>
  );

  return <WorkspaceContext.Provider value={{ ...workspace, switching, switchOrganization }}>
    {error && <div className="workspace-error" role="alert">{error}</div>}
    {children}
    {switching && <div className="workspace-switching" role="status">Открываем организацию…</div>}
  </WorkspaceContext.Provider>;
}
