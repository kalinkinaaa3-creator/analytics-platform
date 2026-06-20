import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function formatMonth(dateString) {
  const date = new Date(dateString);

  return date.toLocaleString("ru-RU", {
    month: "short",
  });
}

function formatMillion(value) {
  const number = Number(value || 0);

  return `${(number / 1000000).toLocaleString("ru-RU", {
    maximumFractionDigits: 0,
  })} млн`;
}

function getSeriesLabel(value) {
  if (value === "appg") return `${new Date().getFullYear() - 1}`;
  if (value === "fact") return `${new Date().getFullYear()}`;
  if (value === "plan") return "plan";

  return value;
}

function prepareChartRows(rows, labels) {
  const map = {};

  rows.forEach((row) => {
    map[row.date] = row;
  });

  return labels.map((date) => ({
    date,
    month: formatMonth(date),
    appg: Number(map[date]?.appg || 0),
    fact: Number(map[date]?.fact || 0),
    plan: Number(map[date]?.plan || 0),
  }));
}

function CustomTooltip({ active, payload, label }) {
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

      {payload.map((item) => (
        <div key={item.dataKey} style={{ color: item.color }}>
          {getSeriesLabel(item.dataKey)}: {formatMillion(item.value)}
        </div>
      ))}
    </div>
  );
}

function PlannedSalesChart({ title, rows, labels }) {
  const chartRows = prepareChartRows(rows, labels);

  return (
    <div className="chart-block">
      <h4 style={{ margin: "0 0 10px 0", fontFamily: "Helvetica" }}>
        {title}
      </h4>

      <ResponsiveContainer width="100%" height={220} debounce={800}>
        <ComposedChart
          data={chartRows}
          margin={{ top: 15, right: 10, bottom: 0, left: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} />

          <XAxis
            dataKey="month"
            tick={{ fontSize: 12 }}
            interval="preserveStartEnd"
          />

          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={formatMillion}
            width={75}
          />

          <Tooltip content={<CustomTooltip />} />

          <Legend
            verticalAlign="bottom"
            height={28}
            formatter={(value) => (
              <span style={{ fontWeight: 700 }}>
                {getSeriesLabel(value)}
              </span>
            )}
          />

          <Bar
            dataKey="appg"
            fill="#3d84a8"
            radius={[4, 4, 0, 0]}
            maxBarSize={26}
          />

          <Bar
            dataKey="fact"
            fill="#1fab89"
            radius={[4, 4, 0, 0]}
            maxBarSize={26}
          />

          <Line
            type="monotone"
            dataKey="plan"
            name="plan"
            stroke="#e32636"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PlannedSalesCharts({ data }) {
  const source = Array.isArray(data) ? data : [];

  if (!source.length) return null;

  const labels = [...new Set(source.map((item) => item.date))].sort();

  const grouped = {};

  source.forEach((row) => {
    if (!row.level2) return;

    if (!grouped[row.level2]) {
      grouped[row.level2] = [];
    }

    grouped[row.level2].push(row);
  });

  return (
    <div id="charts-scroll-container">
      <div id="charts-container">
        {Object.entries(grouped).map(([level2, rows]) => (
          <PlannedSalesChart
            key={level2}
            title={level2}
            rows={rows}
            labels={labels}
          />
        ))}
      </div>
    </div>
  );
}