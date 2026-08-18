import { api } from "../../api/client";


export async function fetchCrmFilters() {
  const response = await api.get("/v1/bitrix24/dashboard/filters/");
  return response.data;
}


export async function fetchCrmDashboard(payload) {
  const response = await api.post("/v1/bitrix24/dashboard/", payload);
  return response.data;
}


export async function fetchCrmRows(payload) {
  const response = await api.post("/v1/bitrix24/dashboard/rows/", payload);
  return response.data;
}


export async function exportCrmRows(payload) {
  const response = await api.post(
    "/v1/bitrix24/dashboard/export/",
    payload,
    { responseType: "blob" },
  );
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = "bitrix24_lead_generation.xlsx";
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

export async function downloadManagerTrackingTemplate() {
  const response = await api.get("/v1/bitrix24/dashboard/managers/template/", { responseType: "blob" });
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = "bitrix24_manager_tracking.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function uploadManagerTracking(file) {
  const formData = new FormData();
  formData.append("file", file);
  return (await api.post("/v1/bitrix24/dashboard/managers/upload/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })).data;
}
