import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CrmAnalyticsDashboard } from "./CrmAnalyticsDashboard";
import { CrmDealSection } from "./CrmDealSection";
import "./crm_sections.css";

const SECTIONS = [["leads", "Лиды"], ["deals", "Сделки"], ["full-cycle", "Полный цикл"]];

export function CrmWorkspace({ dashboard }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("section");
  const section = SECTIONS.some(([key]) => key === requested) ? requested : "leads";
  const [toolbarTarget, setToolbarTarget] = useState(null);
  const [tabs, setTabs] = useState({ leads: "leads", deals: "funnel", "full-cycle": "funnel" });
  const validTabs = section === "leads" ? ["leads", "analytics"] : ["funnel", "managers"];
  const currentTab = validTabs.includes(params.get("tab")) ? params.get("tab") : tabs[section];
  const changeTab = (tab) => {
    setTabs((old) => ({ ...old, [section]: tab }));
    setParams((old) => { const next = new URLSearchParams(old); next.set("section", section); next.set("tab", tab); return next; }, { replace: true });
  };
  return <section className="crm-workspace crm-dashboard">
    <header className="crm-workspace-heading"><h1>Аналитика CRM</h1><div className="crm-filter-actions" ref={setToolbarTarget} /></header>
    <nav className="crm-section-tabs" aria-label="Раздел CRM">{SECTIONS.map(([key, label]) => <button key={key} type="button" aria-pressed={section === key} className={section === key ? "active" : ""} onClick={() => { setTabs((old) => ({ ...old, [section]: currentTab })); setParams((old) => { const next = new URLSearchParams(old); next.set("section", key); next.set("tab", tabs[key]); return next; }, { replace: true }); }}>{label}</button>)}</nav>
    <div hidden={section !== "leads"}><CrmAnalyticsDashboard dashboard={dashboard} toolbarTarget={toolbarTarget} embedded tab={section === "leads" ? currentTab : tabs.leads} onTabChange={changeTab} /></div>
    <div hidden={section !== "deals"}><CrmDealSection section="deals" active={section === "deals"} tab={section === "deals" ? currentTab : tabs.deals} onTabChange={changeTab} /></div>
    <div hidden={section !== "full-cycle"}><CrmDealSection section="full-cycle" active={section === "full-cycle"} /></div>
  </section>;
}
