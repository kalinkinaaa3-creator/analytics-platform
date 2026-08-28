import { useCallback, useLayoutEffect, useState } from "react";

const DASHBOARD_SELECTOR = ".crm-dashboard, .project-gantt-dashboard, .revenue-dashboard, .wordstat-dashboard, .purchases, .accreceiv, .turnover";
const EDGE_PADDING = 12;

export function useDropdownPosition({ open, rootRef, menuRef, contentKey = "", preferredWidth = null }) {
  const [position, setPosition] = useState({ left: 0, width: null, maxWidth: null, ready: false });
  const resetPosition = useCallback(() => {
    setPosition((current) => (
      current.left === 0 && current.width === null && current.maxWidth === null && !current.ready
        ? current
        : { left: 0, width: null, maxWidth: null, ready: false }
    ));
  }, []);

  useLayoutEffect(() => {
    if (!open) return undefined;

    let frame = 0;
    const root = rootRef.current;
    const menu = menuRef.current;
    if (!root || !menu) return undefined;

    const dashboard = root.closest(DASHBOARD_SELECTOR);

    function measure() {
      if (!rootRef.current || !menuRef.current) return;

      const rootBounds = rootRef.current.getBoundingClientRect();
      const menuBounds = menuRef.current.getBoundingClientRect();
      const dashboardBounds = dashboard?.getBoundingClientRect();
      const leftBoundary = Math.max(
        EDGE_PADDING,
        dashboardBounds?.left ?? EDGE_PADDING,
      );
      const rightBoundary = Math.min(
        window.innerWidth - EDGE_PADDING,
        dashboardBounds?.right ?? window.innerWidth - EDGE_PADDING,
      );
      const availableWidth = Math.max(0, rightBoundary - leftBoundary);
      const configuredWidth = typeof preferredWidth === "function"
        ? preferredWidth()
        : preferredWidth;
      const naturalWidth = configuredWidth || Math.max(menuBounds.width, menuRef.current.scrollWidth);
      const effectiveWidth = Math.min(naturalWidth, availableWidth);

      let left = 0;
      if (rootBounds.left + effectiveWidth > rightBoundary) {
        left = rootBounds.right - effectiveWidth >= leftBoundary
          ? rootBounds.width - effectiveWidth
          : leftBoundary - rootBounds.left;
      }

      const next = {
        left: Math.round(left),
        width: effectiveWidth ? Math.floor(effectiveWidth) : null,
        maxWidth: availableWidth ? Math.floor(availableWidth) : null,
        ready: true,
      };
      setPosition((current) => (
        current.left === next.left
        && current.width === next.width
        && current.maxWidth === next.maxWidth
        && current.ready
          ? current
          : next
      ));
    }

    function watchPosition() {
      measure();
      frame = window.requestAnimationFrame(watchPosition);
    }

    measure();
    frame = window.requestAnimationFrame(watchPosition);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(root);
    observer?.observe(menu);
    if (dashboard) observer?.observe(dashboard);

    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    window.visualViewport?.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("scroll", measure);

    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      window.visualViewport?.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("scroll", measure);
    };
  }, [open, rootRef, menuRef, contentKey, preferredWidth]);

  return {
    menuStyle: {
      left: position.left,
      ...(position.width ? { width: position.width } : {}),
      ...(position.maxWidth ? { maxWidth: position.maxWidth } : {}),
      visibility: position.ready ? "visible" : "hidden",
    },
    resetPosition,
  };
}
