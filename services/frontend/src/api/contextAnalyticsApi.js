import { api } from "./client";

function query(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
    else if (value !== undefined && value !== null && value !== "") params.set(key, value);
  });
  return params.toString();
}

export async function getContextOptions(filters = {}) { return (await api.get(`/v1/context/filters/?${query(filters)}`)).data; }
export async function getContextReport(page, filters) { return (await api.get(`/v1/context/reports/${page}/?${query(filters)}`)).data; }
export async function exportContextReport(page, filters) {
  const started = (await api.post(`/v1/context/reports/${page}/export/?${query(filters)}`)).data;
  let current = started;
  while (current.running) {
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    current = (await api.get(`/v1/context/exports/${started.id}/`)).data;
  }
  if (!current.ready) throw new Error(current.error || "Не удалось сформировать Excel-выгрузку.");
  return (await api.get(`/v1/context/exports/${started.id}/download/`, { responseType: "blob" })).data;
}
export async function getContextRefreshState() { return (await api.get("/v1/context/refresh/state/")).data; }
export async function startContextRefresh() { return (await api.post("/v1/context/refresh/")).data; }
export async function downloadContextGoals() { return (await api.get("/v1/context/configuration/goals/template/", { responseType: "blob" })).data; }
export async function uploadContextGoals(file) { const body = new FormData(); body.append("file", file); return (await api.post("/v1/context/configuration/goals/upload/", body)).data; }
