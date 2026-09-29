import { SalesCalculatorDashboard } from "./salesCalculator/SalesCalculatorDashboard";
import { PlannedSalesDashboard } from "./plannedSales/PlannedSalesDashboard";
import { ProjectGanttDashboard } from "./projects/ProjectGanttDashboard";
import { WordstatDashboard } from "./wordstat/WordstatDashboard";
import { PurchasesDashboard } from "./purchases/PurchasesDashboard";
import { AccreceivDashboard } from "./accreceiv/AccreceivDashboard";
import { TurnoverDashboard } from "./turnover/TurnoverDashboard";
import { RevenueDashboard } from "./revenue/RevenueDashboard";
import { CrmWorkspace } from "./crmAnalytics/CrmWorkspace";
import { SeoAnalyticsDashboard } from "./seoAnalytics/SeoAnalyticsDashboard";
import { ContextAnalyticsDashboard } from "./contextAnalytics/ContextAnalyticsDashboard";
import { LeadGenerationDashboard } from "./leadGeneration/LeadGenerationDashboard";
import { DashboardHeadingRefreshIcons, DashboardRefreshTooltips } from "../components/RefreshInfoTooltip";

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

export function DashboardRenderer({
  data,
  loading,
  onFiltersChange,
  publicToken = null,
}) {
  if (loading && !data?.widgets?.length) {
    return <GlobalSpinner />;
  }

  if (!data?.widgets?.length) {
    return <div>Нет данных для отображения</div>;
  }

  return (
    <>
      <DashboardRefreshTooltips />
      <DashboardHeadingRefreshIcons />
      {data.widgets.map((widget) => {
        if (widget.type === "planned_sales_dashboard") {
          return (
            <PlannedSalesDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
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
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "yd_wordstat_table") {
          return (
            <WordstatDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "fb_purchases_dashboard") {
          return (
            <PurchasesDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "fb_accreceiv_dashboard") {
          return (
            <AccreceivDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "fb_turnover_dashboard") {
          return (
            <TurnoverDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "revenue_dashboard") {
          return (
            <RevenueDashboard
              key={widget.id}
              data={widget.data}
              dashboard={data.dashboard}
              onFiltersChange={onFiltersChange}
              publicToken={publicToken}
            />
          );
        }

        if (widget.type === "crm_analytics_dashboard") {
          return <CrmWorkspace key={widget.id} dashboard={data.dashboard} />;
        }

        if (widget.type === "seo_analytics_dashboard") {
          return <SeoAnalyticsDashboard key={widget.id} dashboard={data.dashboard} />;
        }
        if (widget.type === "context_analytics_dashboard") {
          return <ContextAnalyticsDashboard key={widget.id} dashboard={data.dashboard} />;
        }
        if (widget.type === "sales_calculator_dashboard") {
          return <SalesCalculatorDashboard key={widget.id} />;
        }
        if (widget.type === "lead_generation_dashboard") {
          return <LeadGenerationDashboard key={widget.id} dashboard={data.dashboard} />;
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
