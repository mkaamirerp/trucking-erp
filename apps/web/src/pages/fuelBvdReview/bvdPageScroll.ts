export type PageTransitionIntent = "manual" | "field" | null;

export function resetScrollContainerToOrigin(el: HTMLDivElement | null): void {
  if (!el) return;
  el.scrollLeft = 0;
  el.scrollTop = 0;
}

export function resetScrollContainersToOrigin(...elements: (HTMLDivElement | null)[]): void {
  for (const el of elements) resetScrollContainerToOrigin(el);
}
