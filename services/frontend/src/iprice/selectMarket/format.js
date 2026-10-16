export const priceText = value => value == null ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 4 });

export function errorText(error, fallback = "Не удалось выполнить запрос.") {
  const data = error.response?.data;
  if (!data || typeof data === "string") return fallback;
  const messages = value => typeof value === "string" ? [value]
    : Array.isArray(value) ? value.flatMap(messages)
      : value && typeof value === "object" ? Object.values(value).flatMap(messages) : [];
  return messages(data).join("; ") || fallback;
}
