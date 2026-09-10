from pathlib import Path

path = Path("services/frontend/src/dashboards/crmAnalytics/CrmAnalyticsDashboard.jsx")
content = path.read_text(encoding="utf-8")
old = '<td>{item.title || "—"}</td><td><small className="crm-customer-badge">'
new = '<td><span className="crm-detail-title" title={item.title || ""}>{item.title || "—"}</span></td><td><small className="crm-customer-badge">'
assert content.count(old) == 1, content.count(old)
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="")
