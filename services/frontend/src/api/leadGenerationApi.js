import { api } from "./client";

function query(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  });
  return params.toString();
}

export async function getLeadGenerationReport(page, filters) { return (await api.get(`/v1/lead-generation/reports/${page}/?${query(filters)}`)).data; }
export async function getLeadGenerationSources() { return (await api.get("/v1/lead-generation/sources/")).data; }
export async function saveLeadGenerationSources(sourceIds) { return (await api.post("/v1/lead-generation/sources/", { source_ids: sourceIds })).data; }
export async function getLeadGenerationRefreshInfo() { return (await api.get("/v1/lead-generation/refresh/info/")).data; }
export async function downloadLeadGenerationPlan() { return (await api.get("/v1/lead-generation/plan/download/", { responseType: "blob" })).data; }
export async function uploadLeadGenerationPlan(file) { const body = new FormData(); body.append("file", file); return (await api.post("/v1/lead-generation/plan/upload/", body)).data; }
export async function exportLeadGenerationReport(page, filters) { return (await api.get(`/v1/lead-generation/reports/${page}/export/?${query(filters)}`, { responseType: "blob" })).data; }
