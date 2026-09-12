import { useLayoutEffect, useRef } from "react";

function textWidth(node) {
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  let width = 0;
  while (walker.nextNode()) {
    range.selectNodeContents(walker.currentNode);
    width += range.getBoundingClientRect().width;
  }
  return Math.ceil(width);
}

export function SummaryTableFrame({ children }) {
  const rootRef = useRef(null);
  useLayoutEffect(() => {
    const root = rootRef.current;
    const table = root.querySelector("table");
    const panel = root.closest(".crm-panel");
    const grid = panel?.parentElement;
    let frame;
    let disposed = false;
    const measure = () => {
      if (!root.clientWidth) return;
      root.style.setProperty("--crm-summary-font-size", "12px");
      const fitColumns = () => {
        const columns = new Map();
        const metrics = [...table.querySelectorAll(".crm-summary-value,.crm-summary-delta")];
        for (const metric of metrics) {
          const column = metric.closest("td").cellIndex;
          const widths = columns.get(column) || [];
          [...metric.children].forEach((part, index) => {
            const width = part.matches(".crm-delta-arrow") ? 10 : part.matches(".crm-inline-delta") && part.children.length
              ? 14 + textWidth(part.lastElementChild) : textWidth(part);
            widths[index] = Math.max(widths[index] || 0, width);
          });
          columns.set(column, widths);
        }
        for (const metric of metrics) {
          metric.style.gridTemplateColumns = columns.get(metric.closest("td").cellIndex).map(width => `${width}px`).join(" ");
        }
        table.style.width = "1px";
        const minimumWidth = table.getBoundingClientRect().width;
        table.style.width = "";
        return minimumWidth;
      };
      const minimumWidth = fitColumns();
      if (grid?.classList.contains("crm-chart-grid")) {
        const gap = parseFloat(getComputedStyle(grid).columnGap) || 0;
        const panelInsets = panel.getBoundingClientRect().width - root.clientWidth;
        // Reflow a panel only when its numbers cannot fit beside its neighbour.
        panel.style.gridColumn = minimumWidth > (grid.clientWidth - gap) / 2 - panelInsets ? "1 / -1" : "";
      }
      if (minimumWidth > root.clientWidth) {
        root.style.setProperty("--crm-summary-font-size", `${Math.max(10, Math.floor(12 * root.clientWidth / minimumWidth * 10) / 10)}px`);
        fitColumns();
      }
    };
    const schedule = () => { if (disposed) return; cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(root);
    if (grid) observer.observe(grid);
    document.fonts?.ready.then(schedule);
    return () => { disposed = true; observer.disconnect(); cancelAnimationFrame(frame); if (panel) panel.style.gridColumn = ""; };
  }, [children]);
  return <div ref={rootRef} className="crm-summary-wrap">{children}</div>;
}
