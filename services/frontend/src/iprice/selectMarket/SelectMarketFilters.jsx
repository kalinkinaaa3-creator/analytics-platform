import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { DashboardMultiSelect } from "../../components/DashboardMultiSelect";

const labels = { group_1: "Группа 1", group_2: "Группа 2", group_3: "Группа 3", group_4: "Группа 4",
  is_classified: "Наличие классификации", category: "Категория", subcategory: "Подкатегория",
  subcategory_type: "Тип подкатегории", color: "Цвет", material: "Материал", modification: "Модификация", item_type: "Тип позиции" };
const display = (key, value) => value === "__empty__" ? "Не заполнено" : key === "is_classified" ? (value === "true" ? "Классифицирован" : "Без классификации") : value;

export function SelectMarketFilters({ snapshotId, comparisonId, search, filters, onChange }) {
  const [options, setOptions] = useState({});
  const [error, setError] = useState("");
  const serialized = JSON.stringify(filters);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`/v1/select-market/iprice/snapshots/${snapshotId}/filters/`, {
      params: { filters: serialized, search, comparison_id: comparisonId || undefined }, signal: controller.signal,
    }).then(({ data }) => { setOptions(data); setError(""); })
      .catch(err => { if (err.code !== "ERR_CANCELED") setError("Не удалось загрузить варианты фильтров."); });
    return () => controller.abort();
  }, [snapshotId, comparisonId, search, serialized]);
  return <details><summary>Группы 1С и классификация</summary>
    {error && <p role="alert">{error}</p>}
    <div className="sm-iprice-sources">{Object.entries(labels).map(([key, label]) => {
      const values = [...new Set([...(options[key] || []), ...(filters[key] || [])])];
      return <DashboardMultiSelect key={key} floating label={label}
        options={values.map(value => display(key, value))}
        selected={(filters[key] || []).map(value => display(key, value))}
        onApply={selected => onChange({ ...filters, [key]: values.filter(value => selected.includes(display(key, value))) })}
        emptyLabel="Все" />;
    })}</div>
    <button type="button" onClick={() => onChange({})}>Сбросить фильтры</button>
  </details>;
}
