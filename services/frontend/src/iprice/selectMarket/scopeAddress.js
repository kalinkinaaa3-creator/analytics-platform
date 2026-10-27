const prefixes = { price_scope: "p_", market_scope: "m_", compare_scope: "c_" };
const defaults = { page: 1, pageSize: 50, mode: "products", ordering: "nom", problemsOnly: false, hierarchy: "classification", comparison: "groups", type: "" };
function visibleFilters(scope) {
  if (scope?.filters && typeof scope.filters === "object") {
    scope.filters = Object.fromEntries(Object.entries(scope.filters).filter(([key]) => !["group_1", "item_type"].includes(key)));
  }
  return scope;
}
export function readScope(params, key) {
  if (params.has(key)) { try { return visibleFilters(JSON.parse(params.get(key))); } catch { return {}; } }
  const result = { snapshotId: params.get("snapshot"), baseId: params.get("compare_from"), filters: {}, path: {} };
  for (const [name, value] of params) {
    if (!name.startsWith(prefixes[key])) continue;
    const field = name.slice(prefixes[key].length);
    if (field.startsWith("filter_")) (result.filters[field.slice(7)] ||= []).push(value);
    else if (field.startsWith("path_")) result.path[field.slice(5)] = value;
    else result[field] = ["page", "pageSize"].includes(field) ? Number(value) : field === "problemsOnly" ? value === "true" : value;
  }
  return visibleFilters(result);
}
export function writeScope(params, key, scope) {
  params.delete(key);
  for (const name of [...params.keys()]) if (name.startsWith(prefixes[key])) params.delete(name);
  for (const [field, value] of Object.entries(scope)) {
    if (["snapshotId", "baseId"].includes(field) || value == null || value === "" && field !== "comparison" || value === defaults[field]) continue;
    if (field === "filters" || field === "path") {
      for (const [name, values] of Object.entries(value)) for (const item of Array.isArray(values) ? values : [values]) params.append(`${prefixes[key]}${field === "filters" ? "filter" : "path"}_${name}`, item);
    } else params.set(`${prefixes[key]}${field}`, String(value));
  }
  return params;
}
