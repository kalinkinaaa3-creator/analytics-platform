import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CrmAnalyticsDashboard } from "./CrmAnalyticsDashboard";
import { CrmDealSection } from "./CrmDealSection";
import "./crm_sections.css";

const SECTIONS = [["leads", "Лиды"], ["deals", "Сделки"], ["full-cycle", "Воронка"]];

function SectionIcon({ section }) {
  return <svg className="crm-section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {section === "leads" ? <><circle cx="9" cy="7" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2H3M17 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" /></> : section === "deals" ? <><rect x="3" y="7" width="18" height="14" rx="2" /><path d="M8 7V4h8v3M3 12a23 23 0 0 0 18 0M10 12v3h4v-3" /></> : <><circle cx="12" cy="4" r="2.5" /><circle cx="4" cy="19" r="2.5" /><circle cx="20" cy="19" r="2.5" /><path d="m11 6-6 10M13 6l6 10M7 19h10" /></>}
  </svg>;
}

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
    <nav className="crm-section-tabs" aria-label="Раздел CRM">{SECTIONS.map(([key, label]) => <button key={key} type="button" aria-pressed={section === key} className={section === key ? "active" : ""} onClick={() => { if (key === section) return; setTabs((old) => ({ ...old, [section]: currentTab })); setParams((old) => { const next = new URLSearchParams(old); next.set("section", key); next.set("tab", tabs[key]); return next; }, { replace: true }); }}><SectionIcon section={key} /><span>{label}</span></button>)}</nav>
    <div hidden={section !== "leads"}><CrmAnalyticsDashboard dashboard={dashboard} toolbarTarget={toolbarTarget} embedded tab={section === "leads" ? currentTab : tabs.leads} onTabChange={changeTab} /></div>
    <div hidden={section !== "deals"}><CrmDealSection section="deals" active={section === "deals"} tab={section === "deals" ? currentTab : tabs.deals} onTabChange={changeTab} /></div>
    <div hidden={section !== "full-cycle"}><CrmDealSection section="full-cycle" active={section === "full-cycle"} /></div>
  </section>;
}
