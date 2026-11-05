import { useState } from "react";
import "./DashboardInstruction.css";

const FILES = {
  crm: "Аналитика CRM инструкция пользователя.docx",
  price: "Коммерческий прайс - инструкция пользователя.docx",
};

export function DashboardInstruction({ dashboard }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const filename = FILES[dashboard];
  const tooltip = "Скачать инструкцию пользователя в формате Word (.docx)";
  async function download() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}instructions/${encodeURIComponent(filename)}`, { cache: "no-cache" });
      if (!response.ok) throw new Error("missing");
      const blob = await response.blob();
      const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
      // A missing static file may return the application's HTML with HTTP 200.
      if (signature.join(",") !== "80,75,3,4") throw new Error("not-docx");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch {
      setError("Инструкция пока недоступна. Обратитесь к администратору.");
    } finally {
      setBusy(false);
    }
  }
  return <span className="dashboard-instruction">
    <button className="dashboard-instruction-button" type="button" title={tooltip} aria-label={tooltip} disabled={busy} aria-busy={busy} onClick={download}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M12 11v7m-3-3 3 3 3-3" /></svg>
    </button>
    {error && <span className="dashboard-instruction-error" role="alert" onClick={() => setError("")}>{error}</span>}
  </span>;
}
