import { PlannedSalesDashboard } from "./plannedSales/PlannedSalesDashboard";
import { ProjectGanttDashboard } from "./projects/ProjectGanttDashboard";
import "./spinner.css";

function GlobalSpinner() {
  return (
    <div className="global-spinner-overlay show">
      <div className="spinner-container">
        <div className="infinite-spinner"></div>
        <div className="spinner-text">Загрузка данных...</div>
      </div>
    </div>
  );
}

export function DashboardRenderer({ data, loading, onFiltersChange }) {
  if (loading && !data?.widgets?.length) {
    return <GlobalSpinner />;
  }

  if (!data?.widgets?.length) {
    return <div>Нет данных для отображения</div>;
  }

  return (
    <>
      {data.widgets.map((widget) => {
        if (widget.type === "planned_sales_dashboard") {
          return (
            <PlannedSalesDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
            />
          );
        }

        if (widget.type === "fb_project_gantt") {
          return (
            <ProjectGanttDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
            />
          );
        }

        return (
          <div key={widget.id}>
            <h3>{widget.type}</h3>
            <pre>{JSON.stringify(widget.data, null, 2)}</pre>
          </div>
        );
      })}

      {loading && <GlobalSpinner />}
    </>
  );
}