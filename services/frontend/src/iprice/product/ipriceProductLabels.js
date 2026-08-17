export function getIPriceCompetitorSourceLabel(source) {
  const normalizedSource = String(source || "").trim().toLowerCase();
  const labels = {
    tara: "ТАРА",
    ps: "ПЛАСТИК СИСТЕМА",
    tt: "ТОПАЗ",
  };

  return labels[normalizedSource] || normalizedSource.toUpperCase();
}


export function formatMatchPropertyValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return value === "__ANY__" ? "Любой цвет (по запросу)" : String(value);
}
