export function getIPriceCompetitorSourceLabel(source) {
  const normalizedSource = String(source || "").trim().toLowerCase();
  const labels = {
    tara: "ТАРА",
    ps: "ПЛАСТИК СИСТЕМА",
    tt: "ТОПАЗ",
  };

  return labels[normalizedSource] || normalizedSource.toUpperCase();
}


export function getIPriceCompetitorPriceProperties(source, variants) {
  const normalizedSource = String(source || "").trim().toLowerCase();
  const result = [];
  const seen = new Set();
  const sourceVariants = Array.isArray(variants) ? variants : [];
  const visibleVariants = normalizedSource === "tara"
    ? sourceVariants.filter((variant) => variant?.is_selected_price_row === true)
    : sourceVariants;

  visibleVariants.forEach((variant) => {
    const rawValue = String(variant?.properties_price || "").trim();
    if (!rawValue) {
      return;
    }
    let label = "";
    let value = rawValue;
    if (normalizedSource === "ps") {
      const separatorIndex = rawValue.indexOf("/");
      if (separatorIndex >= 0) {
        value = rawValue.slice(0, separatorIndex).trim();
        label = rawValue.slice(separatorIndex + 1).trim();
      }
      label = label || "Опция";
    } else if (normalizedSource === "tara") {
      label = "Количество";
    } else {
      return;
    }
    if (!value) {
      return;
    }
    const key = `${label.toLowerCase()}|${value.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      result.push({label, value});
    }
  });
  return result;
}
