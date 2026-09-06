import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import "./refresh_info_tooltip.css";

const formatDuration = (seconds) => {
  if (!Number.isFinite(Number(seconds)) || Number(seconds) <= 0) return null;
  const minutes = Math.max(1, Math.round(Number(seconds) / 60));
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
};

export function RefreshInfoTooltip({ children, lastUpdated, averageSeconds, averageText, schedule, disabledReason = "", sections = null }) {
  const anchorRef = useRef(null);
  const tooltipRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, side: "right" });

  useLayoutEffect(() => {
    if (!open || !anchorRef.current || !tooltipRef.current) return;
    const anchor = anchorRef.current.getBoundingClientRect();
    const tooltip = tooltipRef.current.getBoundingClientRect();
    const gap = 12;
    const padding = 10;
    const fitsRight = anchor.right + gap + tooltip.width <= window.innerWidth - padding;
    const left = fitsRight ? anchor.right + gap : Math.max(padding, anchor.left - gap - tooltip.width);
    const top = Math.min(Math.max(padding, anchor.top + anchor.height / 2 - tooltip.height / 2), window.innerHeight - tooltip.height - padding);
    setPosition({ left, top, side: fitsRight ? "right" : "left" });
  }, [open]);

  const duration = formatDuration(averageSeconds) || averageText || "оценка появится после успешных запусков";
  const tooltip = open ? createPortal(
    <aside ref={tooltipRef} className={`refresh-info-tooltip is-${position.side}`} style={{ left: position.left, top: position.top }} role="tooltip">
      <div className="refresh-info-tooltip__eyebrow">Обновление данных</div>
      {sections ? sections.map((section, index) => <div className="refresh-info-tooltip__section" key={section.title}><span>{section.title}</span><strong>{section.content}</strong>{index < sections.length - 1 && <div className="refresh-info-tooltip__divider" />}</div>) : <>{disabledReason ? <div className="refresh-info-tooltip__warning">{disabledReason}</div> : <div className="refresh-info-tooltip__row"><span>Данные актуальны на:</span><strong>{lastUpdated || "—"}</strong></div>}<div className="refresh-info-tooltip__row"><span>Среднее время обновления:</span><strong>{duration}</strong></div><div className="refresh-info-tooltip__divider" /><div className="refresh-info-tooltip__schedule"><span>Данные обновляются:</span><strong>{schedule}</strong></div></>}
    </aside>,
    document.body,
  ) : null;

  return <span ref={anchorRef} className="refresh-info-tooltip-anchor" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocusCapture={() => setOpen(true)} onBlurCapture={() => setOpen(false)}>{children}{tooltip}</span>;
}

const DASHBOARD_INFO = [
  [".context-dashboard", { schedule: "ежедневно, включая субботу и воскресенье, в 06:50 МСК", endpoint: "/v1/context/refresh/state/", averageText: "ориентировочно 1–3 мин" }],
  [".seo-dashboard", { schedule: "ежедневно, включая субботу и воскресенье, в 06:40 МСК", endpoint: "/v1/seo/refresh/state/", averageText: "ориентировочно 1–3 мин" }],
  [".crm-dashboard", { schedule: "пн–сб в 03:10 и 15:10 МСК; вс в 10:00 — дополнительная сверка лидов за последние 14 дней", endpoint: "/v1/bitrix24/dashboard/refresh/", averageText: "ориентировочно 5–7 мин" }],
  [".planned-sales-dashboard", { schedule: "ежедневно, включая субботу и воскресенье, в 07:30 МСК", averageText: "ориентировочно 2–5 мин" }],
  [".revenue-dashboard", { schedule: "ежедневно, включая субботу и воскресенье, в 07:30 МСК", averageText: "ориентировочно 2–5 мин" }],
  [".purchases", { schedule: "ежедневно, включая субботу и воскресенье, в 06:00 МСК", averageText: "ориентировочно 2–5 мин" }],
  [".turnover", { schedule: "ежедневно, включая субботу и воскресенье, в 06:10 МСК", averageText: "ориентировочно 5–10 мин" }],
  [".accreceiv", { schedule: "ежедневно, включая субботу и воскресенье, в 06:20 МСК", averageText: "ориентировочно 5–10 мин" }],
  [".project-gantt-dashboard", { schedule: "ежедневно, включая субботу и воскресенье, в 07:00 МСК", averageText: "ориентировочно 2–3 мин" }],
  [".wordstat-dashboard", { schedule: "ежемесячно 3-го числа в 13:00 МСК", averageText: "ориентировочно 7–8 дн" }],
];

export function DashboardHeadingRefreshIcons() {
  useEffect(() => {
    const icons = [];
    DASHBOARD_INFO.forEach(([selector]) => {
      const root = document.querySelector(selector);
      if (!root || root.querySelector(".dashboard-refresh-info") || [...root.querySelectorAll("button")].some((button) => /^Обнов(ить|ление)/.test(button.textContent.trim()))) return;
      const heading = root.querySelector("h1, h2");
      if (!heading) return;
      const icon = document.createElement("button");
      icon.type = "button";
      icon.className = "dashboard-refresh-info";
      icon.textContent = "i";
      icon.setAttribute("aria-label", "Информация об обновлении данных");
      heading.appendChild(icon);
      icons.push(icon);
    });
    return () => icons.forEach((icon) => icon.remove());
  });
  return null;
}

export function DashboardRefreshTooltips() {
  const tooltipRef = useRef(null);
  const activeButtonRef = useRef(null);
  const cacheRef = useRef(new Map());
  const [state, setState] = useState(null);
  const [position, setPosition] = useState({ left: 0, top: 0, side: "right" });

  useLayoutEffect(() => {
    if (!state || !tooltipRef.current) return;
    const tooltip = tooltipRef.current.getBoundingClientRect();
    const gap = 12;
    const padding = 10;
    const fitsRight = state.anchor.right + gap + tooltip.width <= window.innerWidth - padding;
    setPosition({
      left: fitsRight ? state.anchor.right + gap : Math.max(padding, state.anchor.left - gap - tooltip.width),
      top: Math.min(Math.max(padding, state.anchor.top + state.anchor.height / 2 - tooltip.height / 2), window.innerHeight - tooltip.height - padding),
      side: fitsRight ? "right" : "left",
    });
  }, [state]);

  useLayoutEffect(() => {
    const find = (target) => {
      const button = target.closest?.("button");
      if (!button || (!/^Обнов(ить|ление)/.test(button.textContent.trim()) && !button.classList.contains("dashboard-refresh-info")) || button.closest('[class*="iprice"]')) return null;
      const entry = DASHBOARD_INFO.find(([selector]) => button.closest(selector));
      return entry ? { button, info: entry[1] } : null;
    };
    const show = async (event) => {
      const found = find(event.target);
      if (!found) return;
      const { button, info } = found;
      activeButtonRef.current = button;
      const nativeTitle = button.getAttribute("title") || "";
      if (nativeTitle) { button.dataset.refreshNativeTitle = nativeTitle; button.removeAttribute("title"); }
      const disabledReason = /^Недостаточно прав/i.test(nativeTitle) ? nativeTitle : "";
      const hasNoData = /^(Данные отсутствуют|Данные ещё не обновлялись)$/i.test(nativeTitle);
      const lastUpdated = disabledReason || hasNoData ? "—" : nativeTitle.replace(/^Данные актуальны на:\s*/i, "").replace(/^Данные актуальны на\s*/i, "") || "—";
      const cachedSeconds = info.endpoint ? cacheRef.current.get(info.endpoint) : null;
      setState({ anchor: button.getBoundingClientRect(), lastUpdated, disabledReason, ...info, averageSeconds: cachedSeconds });
      if (info.endpoint && cachedSeconds === undefined) {
        try {
          const payload = (await api.get(info.endpoint)).data;
          cacheRef.current.set(info.endpoint, payload.average_duration_seconds || null);
          if (activeButtonRef.current === button) setState((old) => old ? { ...old, averageSeconds: payload.average_duration_seconds } : old);
        } catch { cacheRef.current.set(info.endpoint, null); }
      }
    };
    const hide = (event) => {
      const found = find(event.target);
      if (!found || found.button.contains(event.relatedTarget)) return;
      if (found.button.dataset.refreshNativeTitle) { found.button.setAttribute("title", found.button.dataset.refreshNativeTitle); delete found.button.dataset.refreshNativeTitle; }
      if (activeButtonRef.current === found.button) { activeButtonRef.current = null; setState(null); }
    };
    document.addEventListener("pointerover", show);
    document.addEventListener("pointerout", hide);
    document.addEventListener("focusin", show);
    document.addEventListener("focusout", hide);
    return () => { document.removeEventListener("pointerover", show); document.removeEventListener("pointerout", hide); document.removeEventListener("focusin", show); document.removeEventListener("focusout", hide); };
  }, []);

  if (!state) return null;
  const duration = formatDuration(state.averageSeconds) || state.averageText;
  return createPortal(<aside ref={tooltipRef} className={`refresh-info-tooltip is-${position.side}`} style={{ left: position.left, top: position.top }} role="tooltip"><div className="refresh-info-tooltip__eyebrow">Обновление данных</div>{state.disabledReason ? <div className="refresh-info-tooltip__warning">{state.disabledReason}</div> : <div className="refresh-info-tooltip__row"><span>Данные актуальны на:</span><strong>{state.lastUpdated}</strong></div>}<div className="refresh-info-tooltip__row"><span>Среднее время обновления:</span><strong>{duration}</strong></div><div className="refresh-info-tooltip__divider" /><div className="refresh-info-tooltip__schedule"><span>Данные обновляются:</span><strong>{state.schedule}</strong></div></aside>, document.body);
}
