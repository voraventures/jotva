import { useLayoutEffect, useState } from "react";

// Glossy glass highlight that glides to whichever element `resolveTarget()` returns,
// positioned inside `containerRef` (which must be position: relative). Re-measures when
// `key` changes or the container/target resize. Render the result on a <span>.
// Lives in the parent component so every child ref is attached before we measure.
export function useGlassLens(containerRef, resolveTarget, key) {
  const [box, setBox] = useState(null);
  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = () => {
      const target = resolveTarget();
      if (!container || !target) { setBox(null); return; }
      const c = container.getBoundingClientRect(), t = target.getBoundingClientRect();
      setBox((prev) => ({
        x: t.left - c.left - container.clientLeft + container.scrollLeft,
        y: t.top - c.top - container.clientTop + container.scrollTop,
        w: t.width, h: t.height, animate: !!prev,
      }));
    };
    measure();
    if (!container || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    const target = resolveTarget();
    if (target) observer.observe(target);
    return () => observer.disconnect();
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    "aria-hidden": true,
    className: `glass-lens${box?.animate ? " animate" : ""}`,
    style: box ? { transform: `translate(${box.x}px, ${box.y}px)`, width: box.w, height: box.h } : { opacity: 0 },
  };
}
