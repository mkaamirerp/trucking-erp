import type { PdfTextItem } from "./bvdPdfHighlight";
import { getTextLayerSpanElements, spanElementsForItemIndices as domSpanForIndices } from "./bvdPdfDomHighlight";

export function spanElementsForItemIndices(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  indices: number[],
): HTMLElement[] {
  return domSpanForIndices(pageDiv, items, indices);
}

export function toPageCoordsFromDom(
  pageDiv: HTMLElement,
  client: DOMRect,
): { left: number; top: number; width: number; height: number } {
  const pr = pageDiv.getBoundingClientRect();
  return {
    left: client.left - pr.left,
    top: client.top - pr.top,
    width: client.width,
    height: client.height,
  };
}

export function ensureTextLayerIndex(pageDiv: HTMLElement, items: PdfTextItem[]): void {
  getTextLayerSpanElements(pageDiv);
}
