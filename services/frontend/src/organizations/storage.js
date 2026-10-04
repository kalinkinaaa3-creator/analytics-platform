// Organization is tab-local; auth tokens retain the existing shared login behavior.
function storageKey() {
  return `workspace.organization:${localStorage.getItem("username") || ""}`;
}

export function getOrganizationId() {
  return sessionStorage.getItem(storageKey());
}

export function setOrganizationId(id) {
  if (id == null) sessionStorage.removeItem(storageKey());
  else sessionStorage.setItem(storageKey(), String(id));
}
