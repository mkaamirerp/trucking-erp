import { useEffect, useRef } from "react";

export function useSynchronizedScroll(
  leftRef: React.RefObject<HTMLDivElement | null>,
  rightRef: React.RefObject<HTMLDivElement | null>,
  enabled: boolean,
) {
  const guardRef = useRef(false);

  useEffect(() => {
    const left = leftRef.current;
    const right = rightRef.current;
    if (!left || !right) return;

    const sync = (source: HTMLDivElement, target: HTMLDivElement) => {
      if (!enabled || guardRef.current) return;
      guardRef.current = true;
      target.scrollTop = source.scrollTop;
      target.scrollLeft = source.scrollLeft;
      requestAnimationFrame(() => {
        guardRef.current = false;
      });
    };

    const onLeft = () => sync(left, right);
    const onRight = () => sync(right, left);
    left.addEventListener("scroll", onLeft, { passive: true });
    right.addEventListener("scroll", onRight, { passive: true });
    return () => {
      left.removeEventListener("scroll", onLeft);
      right.removeEventListener("scroll", onRight);
    };
  }, [leftRef, rightRef, enabled]);
}
