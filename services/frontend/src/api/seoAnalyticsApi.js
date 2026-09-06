import { api } from "./client";


function query(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => item && params.append(key, item));
    else if (value) params.set(key, value);
  });
  return params.toString();
}


export async function getSeoFilterOptions(page = "", filters = {}) {
  return (await api.get(`/v1/seo/filters/?page=${encodeURIComponent(page)}&${query(filters)}`)).data;
}


export async function getSeoReport(page, filters) {
  return (await api.get(`/v1/seo/reports/${page}/?${query(filters)}`)).data;
}


export async function exportSeoReport(page, filters) {
  const started = (await api.post(`/v1/seo/reports/${page}/export/?${query(filters)}`)).data;
  let current = started;
  while (current.running) {
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    current = (await api.get(`/v1/seo/exports/${started.id}/`)).data;
  }
  if (!current.ready) throw new Error(current.error || "Не удалось сформировать Excel-выгрузку.");
  return (await api.get(`/v1/seo/exports/${started.id}/download/`, { responseType: "blob" })).data;
}


export async function downloadSeoConfiguration(kind) {
  return (await api.get(`/v1/seo/configuration/${kind}/template/`, { responseType: "blob" })).data;
}


export async function uploadSeoConfiguration(kind, file) {
  const data = new FormData();
  data.append("file", file);
  return (await api.post(`/v1/seo/configuration/${kind}/upload/`, data)).data;
}


export async function startSeoRefresh(page, filters) {
  return (await api.post(`/v1/seo/refresh/?page=${encodeURIComponent(page)}&${query(filters)}`)).data;
}


export async function getSeoRefreshState() {
  return (await api.get("/v1/seo/refresh/state/")).data;
}
