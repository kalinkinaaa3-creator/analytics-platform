const COLOR_NOTICE = (
  "Изображение и оттенок на изображении могут отличаться "
  + "от фактического товара и его цвета."
);


function normalizeColor(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase("ru-RU")
    .replaceAll("ё", "е");
}


function getColorKind(value) {
  const normalized = normalizeColor(value);
  if ([
    "-",
    "__any__",
    "любой цвет (по запросу)",
    "цвет не установлен",
  ].includes(normalized)) {
    return "any";
  }
  const kinds = [
    ["yellow", "желт"],
    ["orange", "оранж"],
    ["blue", "син"],
    ["green", "зелен"],
    ["gray", "сер"],
    ["red", "красн"],
    ["white", "бел"],
    ["black", "черн"],
    ["brown", "корич"],
  ];
  return kinds.find(([, fragment]) => normalized.includes(fragment))?.[0] || "unknown";
}


function getIPriceColorLabel(value) {
  return getColorKind(value) === "any"
    ? "цвет не установлен"
    : (String(value || "").trim() || "Цвет не указан");
}


export function IPriceColorSwatch({ color, withNotice = true }) {
  const label = getIPriceColorLabel(color);
  const tooltip = withNotice ? `${label}. ${COLOR_NOTICE}` : label;

  return (
    <span className="iprice-color-swatch-wrapper">
      <span
        className={`iprice-color-swatch iprice-color-swatch--${getColorKind(color)}`}
        role="img"
        tabIndex={0}
        aria-label={tooltip}
      />
      <span className="iprice-color-swatch__tooltip" role="tooltip">
        <strong>{label}</strong>
        {withNotice && <span>{COLOR_NOTICE}</span>}
      </span>
    </span>
  );
}
