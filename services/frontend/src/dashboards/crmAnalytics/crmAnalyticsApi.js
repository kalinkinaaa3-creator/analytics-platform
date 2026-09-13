import { api } from "../../api/client";

async function publishedRequest(url, payload, signal) {
  for (let attempt = 0; ; attempt += 1) {
    try { return await api.post(url, payload, { signal }); }
    catch (error) {
      if (error.response?.status !== 409 || attempt > 0 || signal?.aborted) throw error;
      await new Promise((resolve) => setTimeout(resolve, 300));
      if (signal?.aborted) throw error;
    }
  }
}


export async function fetchCrmFilters(payload) {
  const response = await publishedRequest("/v1/bitrix24/dashboard/filters/", payload);
  return response.data;
}


export async function fetchCrmDashboard(payload) {
  const response = await publishedRequest("/v1/bitrix24/dashboard/", payload);
  return response.data;
}


export async function fetchCrmRows(payload, signal) {
  const response = await publishedRequest("/v1/bitrix24/dashboard/rows/", payload, signal);
  return response.data;
}


export async function exportCrmRows(payload, filename = "bitrix24_lead_generation.xlsx") {
  const response = await api.post(
    "/v1/bitrix24/dashboard/export/",
    payload,
    { responseType: "blob" },
  );
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function refreshCrmAnalytics() {
  return (await api.post("/v1/bitrix24/dashboard/refresh/")).data;
}

export async function fetchCrmRefreshState() {
  return (await api.get("/v1/bitrix24/dashboard/refresh/")).data;
}

export async function fetchDepartmentPreferences() {
  return (await api.get("/v1/bitrix24/dashboard/department-preferences/")).data;
}

export async function saveDepartmentPreferences(rows) {
  return (await api.post("/v1/bitrix24/dashboard/department-preferences/", { rows })).data;
}
