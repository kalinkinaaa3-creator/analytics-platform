import { useLayoutEffect, useRef, useState } from "react";


function overlaps(left, right) {
  const horizontalGap = 4;
  const verticalGap = 2;
  return left.left < right.right + horizontalGap
    && left.right + horizontalGap > right.left
    && left.top < right.bottom + verticalGap
    && left.bottom + verticalGap > right.top;
}


export function CollisionSafeChartLabel({ x, y, children, className = "", textAnchor = "middle" }) {
  const labelRef = useRef(null);
  const [hidden, setHidden] = useState(false);

  useLayoutEffect(() => {
    const label = labelRef.current;
    const svg = label?.closest("svg");
    if (!label || !svg) return undefined;

    const update = () => {
      const boundary = svg.getBoundingClientRect();
      const labels = [...svg.querySelectorAll(".collision-safe-chart-label")];
      const accepted = [];
      let visible = true;

      for (const candidate of labels) {
        const box = candidate.getBoundingClientRect();
        const inside = box.left >= boundary.left + 2
          && box.right <= boundary.right - 2
          && box.top >= boundary.top + 2
          && box.bottom <= boundary.bottom - 2;
        const acceptedHere = inside && !accepted.some((acceptedBox) => overlaps(box, acceptedBox));
        if (acceptedHere) accepted.push(box);
        if (candidate === label) {
          visible = acceptedHere;
          break;
        }
      }
      setHidden((current) => current === !visible ? current : !visible);
    };

    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [children, x, y]);

  return <text ref={labelRef} x={x} y={y} textAnchor={textAnchor} className={`collision-safe-chart-label ${className}`.trim()} visibility={hidden ? "hidden" : "visible"}>{children}</text>;
}
