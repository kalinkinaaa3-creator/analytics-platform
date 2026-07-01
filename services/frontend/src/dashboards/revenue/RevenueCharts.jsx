import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const CHARTS = [
  {
    key: "revenue",
    title: "Выручка",
    barLabel: "Выручка, руб",
    unit: "млн",
    gradientFrom: "#46b7b9",
    gradientTo: "#144d53",
  },
  {
    key: "quantity",
    title: "Количество",
    barLabel: "Количество, шт",
    unit: "",
    gradientFrom: "#1891ac",
    gradientTo: "#253b6e",
  },
  {
    key: "weight_total",
    title: "Вес",
    barLabel: "Вес, кг",
    unit: "",
    gradientFrom: "#a393eb",
    gradientTo: "#27296d",
  },
  {
    key: "shipments",
    title: "Отгрузки",
    barLabel: "Отгрузки, шт",
    unit: "",
    gradientFrom: "#5DADE2",
    gradientTo: "#21618C",
  },
  {
    key: "clients",
    title: "Клиенты",
    barLabel: "Клиенты, шт",
    newKey: "new_clients",
    newLabel: "Новые клиенты",
    unit: "",
    gradientFrom: "#d4be85",
    gradientTo: "#ec610a",
    newGradientFrom: "#E74C3C",
    newGradientTo: "#922B21",
  },
  {
    key: "sku",
    title: "SKU",
    barLabel: "SKU, шт",
    newKey: "new_sku",
    newLabel: "Новые SKU",
    unit: "",
    gradientFrom: "#ddba2e",
    gradientTo: "#a78709",
    newGradientFrom: "#E74C3C",
    newGradientTo: "#922B21",
  },
];

function formatValue(value, unit) {
  const number = Number(value || 0);

  if (unit === "млн") {
    return `${(number / 1000000).toLocaleString("ru-RU", {
      maximumFractionDigits: 1,
    })} млн`;
  }

  return number.toLocaleString("ru-RU", {
    maximumFractionDigits: 0,
  });
}

function formatLabelValue(value, unit) {
  const number = Number(value || 0);

  if (!number) return "";

  if (unit === "млн") {
    return `${(number / 1000000).toLocaleString("ru-RU", {
      maximumFractionDigits: 1,
    })} млн`;
  }

  if (number >= 1000000) {
    return `${(number / 1000000).toLocaleString("ru-RU", {
      maximumFractionDigits: 1,
    })} млн`;
  }

  if (number >= 10000) {
    return `${Math.round(number / 1000).toLocaleString("ru-RU")} тыс`;
  }

  return number.toLocaleString("ru-RU", {
    maximumFractionDigits: 0,
  });
}

function prepareChartRows(charts, config) {
  const mainRows = charts?.[config.key] || [];
  const newRows = config.newKey ? charts?.[config.newKey] || [] : [];

  const map = {};

  mainRows.forEach((row) => {
    const total = Number(row.value || 0);

    map[row.period] = {
      period: row.period,
      value: total,
      baseValue: total,
      newValue: 0,
    };
  });

  newRows.forEach((row) => {
    const current = map[row.period] || {
      period: row.period,
      value: 0,
      baseValue: 0,
      newValue: 0,
    };

    const newValue = Number(row.value || 0);
    const total = Number(current.value || 0);

    current.newValue = newValue;
    current.baseValue = Math.max(total - newValue, 0);

    map[row.period] = current;
  });

  return Object.values(map).sort((a, b) => a.period.localeCompare(b.period));
}

function shouldShowLabel(index, total, width, y, value, unit) {
  if (!value || Number(value) === 0) return false;
  if (width < 24) return false;
  if (y < 18) return false;

  if (unit === "млн") {
    if (total <= 6) return true;
    if (total <= 12) return index % 2 === 0;
    if (total <= 24) return index % 4 === 0;
    return index % 6 === 0;
  }

  if (total <= 12) return true;
  if (total <= 24) return index % 2 === 0;
  if (total <= 36) return index % 3 === 0;

  return index % 4 === 0;
}

function renderBarLabel(unit, total) {
  return function BarLabel(props) {
    const { x, y, width, value, index } = props;

    if (!shouldShowLabel(index, total, width, y, value, unit)) {
      return null;
    }

    const label = formatLabelValue(value, unit);
    if (!label) return null;

    return (
      <text
        x={x + width / 2}
        y={y - 8}
        textAnchor="middle"
        fontSize={12}
        fontWeight={700}
        fill="#334155"
        pointerEvents="none"
      >
        {label}
      </text>
    );
  };
}

function renderStackedLabel(unit, total) {
  return function StackedLabel(props) {
    const { x, y, width, index } = props;
    const value = props.value;

    if (!shouldShowLabel(index, total, width, y, value, unit)) {
      return null;
    }

    const label = formatLabelValue(value, unit);
    if (!label) return null;

    return (
      <text
        x={x + width / 2}
        y={y - 8}
        textAnchor="middle"
        fontSize={12}
        fontWeight={700}
        fill="#334155"
        pointerEvents="none"
      >
        {label}
      </text>
    );
  };
}

function CustomTooltip({ active, payload, label, unit, config }) {
  if (!active || !payload?.length) return null;

  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: "6px",
        padding: "8px 10px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        fontSize: "12px",
        textAlign: "left",
        fontWeight: 700,
      }}
    >
      <div style={{ fontWeight: "bold", marginBottom: "4px" }}>{label}</div>

      {payload.map((item) => {
        let labelText = config.barLabel;

        if (item.dataKey === "baseValue" && config.newKey) {
          labelText = `${config.barLabel} (без новых)`;
        }

        if (item.dataKey === "newValue") {
          labelText = config.newLabel;
        }

        return (
          <div key={item.dataKey} style={{ color: item.color }}>
            {labelText}: {formatValue(item.value, unit)}
          </div>
        );
      })}
    </div>
  );
}

function RevenueChart({ charts, config }) {
  const chartRows = prepareChartRows(charts, config);
  const totalPoints = chartRows.length;
  const showLabels = chartRows.length <= 18;

  if (!chartRows.length) {
    return null;
  }

  return (
    <div className="chart-block">
      <h4 style={{ margin: "0 0 10px 0", fontFamily: "Helvetica" }}>
        {config.title}
      </h4>

      <ResponsiveContainer width="100%" height={220} debounce={2000}>
        <ComposedChart
          data={chartRows}
          margin={{ top: 34, right: 24, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient
              id={`gradient-${config.key}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop
                offset="0%"
                stopColor={config.gradientFrom}
                stopOpacity={0.95}
              />
              <stop
                offset="100%"
                stopColor={config.gradientTo}
                stopOpacity={1}
              />
            </linearGradient>

            {config.newKey && (
              <linearGradient
                id={`gradient-${config.newKey}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor={config.newGradientFrom}
                  stopOpacity={0.95}
                />
                <stop
                  offset="100%"
                  stopColor={config.newGradientTo}
                  stopOpacity={1}
                />
              </linearGradient>
            )}
          </defs>

          <CartesianGrid strokeDasharray="3 3" vertical={false} />

          <XAxis
            dataKey="period"
            tick={{ fontSize: 12 }}
            interval="preserveStartEnd"
            padding={{ left: 8, right: 18 }}
            tickMargin={8}
          />

          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={(value) => formatValue(value, config.unit)}
            width={75}
          />

          <Tooltip
            content={
              <CustomTooltip
                unit={config.unit}
                config={config}
              />
            }
          />

          <Legend
            verticalAlign="bottom"
            height={28}
            formatter={(value) => (
              <span style={{ fontWeight: 700 }}>
                {value}
              </span>
            )}
          />

          {config.newKey ? (
            <>
              <Bar
                dataKey="baseValue"
                name={`${config.barLabel} (без новых)`}
                stackId={config.key}
                fill={`url(#gradient-${config.key})`}
                radius={[0, 0, 0, 0]}
                maxBarSize={26}
              />

              <Bar
                dataKey="newValue"
                name={config.newLabel}
                stackId={config.key}
                fill={`url(#gradient-${config.newKey})`}
                radius={[4, 4, 0, 0]}
                maxBarSize={26}
              >
                {showLabels && (
                <LabelList
                    dataKey="value"
                    content={renderStackedLabel(config.unit, totalPoints)}
                />
                )}
              </Bar>
            </>
          ) : (
            <Bar
              dataKey="value"
              name={config.barLabel}
              fill={`url(#gradient-${config.key})`}
              radius={[4, 4, 0, 0]}
              maxBarSize={26}
            >
              {showLabels && (
                <LabelList content={renderStackedLabel(config.unit, totalPoints)} />
              )}
            </Bar>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RevenueCharts({ charts }) {
  if (!charts) return null;

  return (
    <div id="charts-scroll-container">
      <div id="charts-container">
        {CHARTS.map((config) => (
          <RevenueChart
            key={config.key}
            charts={charts}
            config={config}
          />
        ))}
      </div>
    </div>
  );
}