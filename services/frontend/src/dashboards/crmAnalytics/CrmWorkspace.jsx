import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CrmAnalyticsDashboard } from "./CrmAnalyticsDashboard";
import { CrmDealSection } from "./CrmDealSection";
import { DashboardInstruction } from "../../components/DashboardInstruction";
import "./crm_sections.css";

const SECTIONS = [["leads", "Лиды"], ["deals", "Сделки"]];

function SectionIcon({ section }) {
  return <svg className="crm-section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {section === "leads" ? <><circle cx="9" cy="7" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2H3M17 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" /></> : <><rect x="3" y="7" width="18" height="14" rx="2" /><path d="M8 7V4h8v3M3 12a23 23 0 0 0 18 0M10 12v3h4v-3" /></>}
  </svg>;
}

export function CrmWorkspace({ dashboard }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("section");
  const urlSection = SECTIONS.some(([key]) => key === requested) ? requested : "leads";
  const [pendingSection, setPendingSection] = useState(null);
  const section = pendingSection || urlSection;
  useEffect(() => {
    if (pendingSection === urlSection) setPendingSection(null);
  }, [pendingSection, urlSection]);
  const [toolbarTarget, setToolbarTarget] = useState(null);
  const [tabs, setTabs] = useState({ leads: "leads", deals: "funnel" });
  const [resetTokens, setResetTokens] = useState({ leads: 0, deals: 0 });
  const validTabs = section === "leads" ? ["leads", "analytics"] : ["funnel", "managers"];
  const currentTab = validTabs.includes(params.get("tab")) ? params.get("tab") : tabs[section];
  const changeTab = (tab) => {
    setTabs((old) => ({ ...old, [section]: tab }));
    setParams((old) => { const next = new URLSearchParams(old); next.set("section", section); next.set("tab", tab); return next; }, { replace: true });
  };
  return <section className="crm-workspace crm-dashboard" data-heading-tooltip="disabled">
    <header className="crm-workspace-heading"><div className="dashboard-title-with-instruction"><h1>Аналитика CRM</h1><DashboardInstruction dashboard="crm" /></div><div className="crm-filter-actions" ref={setToolbarTarget} /></header>
    <nav className="crm-section-tabs" aria-label="Раздел CRM">{SECTIONS.map(([key, label]) => <button key={key} type="button" aria-pressed={section === key} className={section === key ? "active" : ""} onClick={() => { if (key === section) return; setTabs((old) => ({ ...old, [section]: currentTab })); setResetTokens((old) => ({ ...old, [key]: old[key] + 1 })); setPendingSection(key); setParams((old) => { const next = new URLSearchParams(old); next.set("section", key); next.set("tab", tabs[key]); return next; }, { replace: true }); }}><SectionIcon section={key} /><span>{label}</span></button>)}</nav>
    <div hidden={section !== "leads"}><CrmAnalyticsDashboard dashboard={dashboard} toolbarTarget={toolbarTarget} embedded onPreferencesSaved={() => setResetTokens((old) => ({ ...old, deals: old.deals + 1 }))} resetToken={resetTokens.leads} tab={section === "leads" ? currentTab : tabs.leads} onTabChange={changeTab} /></div>
    <div hidden={section !== "deals"}><CrmDealSection section="deals" active={section === "deals"} resetToken={resetTokens.deals} tab={section === "deals" ? currentTab : tabs.deals} onTabChange={changeTab} /></div>
  </section>;
}
