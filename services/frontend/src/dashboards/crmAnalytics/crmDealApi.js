import { api } from "../../api/client";

export async function crmSectionRequest(section, part, payload, signal) {
  return (await api.post(`/v1/bitrix24/dashboard/${section}/${part}/`, payload, { signal })).data;
}

export async function exportCrmSection(section, payload, filename = null) {
  const response = await api.post(`/v1/bitrix24/dashboard/${section}/export/`, payload, { responseType: "blob" });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || `crm_${section}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}
