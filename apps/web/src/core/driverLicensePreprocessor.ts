/**
 * Browser-side Driver Licence preprocessing.
 *
 * The RAW File is never changed. EXIF/orientation and all geometry work happen on canvases.
 * Final corners come only from four independently supported straight edge lines; rounded
 * physical corner arcs are deliberately excluded from edge sampling.
 */
import {
  ANALYSIS_MAX_LONG_SIDE,
  DL_ASPECT,
  EDGE_SAMPLE_CORNER_IGNORE_END,
  EDGE_SAMPLE_CORNER_IGNORE_START,
  EDGE_SAMPLE_COUNT,
  GRADIENT_MAG_THRESHOLD,
  LEVEL_TOLERANCE_DEG,
  MIN_ABSOLUTE_INLIERS,
  MIN_EDGE_SPAN_COVERAGE,
  MIN_INLIER_RATIO,
  ORIENTATION_ORDER,
  PARALLEL_TOLERANCE_DEG,
  PREPROCESS_VERSION,
  RANSAC_DISTANCE_THRESHOLD,
  RANSAC_ITERATIONS,
  SEARCH_PX_MAX,
  SEARCH_PX_MIN,
  SEARCH_PX_RATIO,
  TARGET_H,
  TARGET_W,
  axialAngleDeg,
  classifyGeometry,
  cornersFromEdgeLines,
  distance,
  lineFromPoints,
  measureQuadrilateral,
  orderCorners,
  postValidateCanvas,
  rotatePointAroundImageCenter,
  validateSourceQuadrilateral,
  type EdgeDiagnostics,
  type EdgeLines,
  type EdgeName,
  type GeometryClass,
  type GeometryMetrics,
  type LineParam,
  type Point,
  type SemanticOrientation,
  type WorkingOrientation,
} from "./driverLicenseGeometry";

export {
  ANALYSIS_MAX_LONG_SIDE,
  DL_ASPECT,
  EDGE_SAMPLE_COUNT,
  MIN_ABSOLUTE_INLIERS,
  MIN_EDGE_SPAN_COVERAGE,
  MIN_INLIER_RATIO,
  PREPROCESS_VERSION,
  RANSAC_DISTANCE_THRESHOLD,
  TARGET_H,
  TARGET_W,
};
export type { GeometryClass, Point };

export type DriverLicenseProcessReport = {
  preprocess_version: string;
  status: "PROCESSED" | "AUTOMATIC_GEOMETRY_UNCONFIRMED" | "AUTOMATIC_GEOMETRY_FAILED_VALIDATION";
  four_edges_confirmed: boolean;
  orientation_preflight: {
    exif: number;
    semantic: { orientation: SemanticOrientation; confidence: "none" | "low" | "high"; method: string };
    selected_geometry_orientation?: WorkingOrientation;
  };
  semantic_post_check: { orientation: SemanticOrientation; confidence: "none" | "low" | "high"; method: string };
  analysis_width: number;
  analysis_height: number;
  rough_candidate_source?: string;
  rough_candidate_score?: number;
  top?: EdgeDiagnostics;
  right?: EdgeDiagnostics;
  bottom?: EdgeDiagnostics;
  left?: EdgeDiagnostics;
  corners?: { TL: Point; TR: Point; BR: Point; BL: Point };
  angles?: { TL: number; TR: number; BR: number; BL: number };
  top_angle_deg?: number;
  right_angle_deg?: number;
  bottom_angle_deg?: number;
  left_angle_deg?: number;
  parallel_error?: { top_bottom: number; left_right: number };
  level_error?: GeometryMetrics["level_errors"];
  source_aspect?: number;
  classification: GeometryClass;
  correction: "NONE" | "CROP" | "ROTATE" | "PERSPECTIVE_WARP";
  rotation_angle_deg?: number;
  post_rotation_geometry?: Record<string, unknown>;
  post_validation?: Record<string, unknown>;
  final_dimensions?: { width: number; height: number };
  failure_reason?: string;
};

export type DriverLicenseProcessResult = {
  status: "SUCCESS" | "MANUAL_REVIEW";
  processedBlob?: Blob;
  report: DriverLicenseProcessReport;
  /** Compatibility alias for earlier UI code. */
  metadata: DriverLicenseProcessReport;
  suggestedCorners?: Point[];
};

type Component = { area: number; boundary: Point[] };
type RoughCandidate = {
  box: Point[];
  score: number;
  source: string;
  areaRatio: number;
  roughAspect: number;
  density: number;
};
type RansacResult = { line: LineParam | null; inlierIndices: number[]; fitError: number; coverage: number };
type ConfirmedGeometry = {
  corners: Point[];
  edges: Required<Pick<EdgeLines, "top" | "right" | "bottom" | "left">> & { all_four_confirmed: true };
  diagnostics: Record<EdgeName, EdgeDiagnostics>;
};
type BestCandidate = {
  orientation: WorkingOrientation;
  orientationWidth: number;
  orientationHeight: number;
  rough: RoughCandidate;
  confirmed: ConfirmedGeometry;
  metrics: GeometryMetrics;
  classification: GeometryClass;
  score: number;
};

function semanticOrientationUnavailable(): { orientation: SemanticOrientation; confidence: "none"; method: string } {
  return { orientation: "unknown", confidence: "none", method: "geometry_only_no_browser_ocr" };
}

function canvasToBlob(canvas: HTMLCanvasElement, quality = 0.92): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Unable to encode processed Driver Licence image"))), "image/jpeg", quality);
  });
}

async function readExifOrientation(file: File): Promise<number> {
  const buffer = await file.slice(0, 256 * 1024).arrayBuffer();
  const view = new DataView(buffer);
  if (view.byteLength < 4 || view.getUint16(0, false) !== 0xffd8) return 1;
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    const marker = view.getUint16(offset, false);
    offset += 2;
    if (marker === 0xffda || marker === 0xffd9) break;
    if (offset + 2 > view.byteLength) break;
    const length = view.getUint16(offset, false);
    if (length < 2 || offset + length > view.byteLength) break;
    if (marker === 0xffe1 && length >= 10) {
      const tiff = offset + 2;
      if (view.getUint32(tiff, false) !== 0x45786966) return 1;
      const byteOrder = tiff + 6;
      const little = view.getUint16(byteOrder, false) === 0x4949;
      const ifdOffset = view.getUint32(byteOrder + 4, little);
      let directory = byteOrder + ifdOffset;
      if (directory + 2 > view.byteLength) return 1;
      const entries = view.getUint16(directory, little);
      directory += 2;
      for (let i = 0; i < entries; i += 1) {
        const entry = directory + i * 12;
        if (entry + 12 > view.byteLength) break;
        if (view.getUint16(entry, little) === 0x0112) {
          const orientation = view.getUint16(entry + 8, little);
          return orientation >= 1 && orientation <= 8 ? orientation : 1;
        }
      }
      return 1;
    }
    offset += length;
  }
  return 1;
}

function drawImageWithExif(ctx: CanvasRenderingContext2D, image: HTMLImageElement, orientation: number): void {
  const w = image.naturalWidth;
  const h = image.naturalHeight;
  switch (orientation) {
    case 2: ctx.translate(w, 0); ctx.scale(-1, 1); break;
    case 3: ctx.translate(w, h); ctx.rotate(Math.PI); break;
    case 4: ctx.translate(0, h); ctx.scale(1, -1); break;
    case 5: ctx.rotate(Math.PI / 2); ctx.scale(1, -1); break;
    case 6: ctx.translate(h, 0); ctx.rotate(Math.PI / 2); break;
    case 7: ctx.translate(h, 0); ctx.rotate(Math.PI / 2); ctx.scale(-1, 1); break;
    case 8: ctx.translate(0, w); ctx.rotate(-Math.PI / 2); break;
    default: break;
  }
  ctx.drawImage(image, 0, 0);
}

async function fileToExifCorrectedCanvas(file: File): Promise<{ canvas: HTMLCanvasElement; exifOrientation: number }> {
  const orientation = await readExifOrientation(file);
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
    const rotate90 = orientation >= 5 && orientation <= 8;
    const canvas = document.createElement("canvas");
    canvas.width = rotate90 ? image.naturalHeight : image.naturalWidth;
    canvas.height = rotate90 ? image.naturalWidth : image.naturalHeight;
    const ctx = canvas.getContext("2d")!;
    drawImageWithExif(ctx, image, orientation);
    return { canvas, exifOrientation: orientation };
  } finally {
    URL.revokeObjectURL(url);
  }
}

function resizeCanvas(source: HTMLCanvasElement, width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width));
  canvas.height = Math.max(1, Math.round(height));
  canvas.getContext("2d")!.drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function rotateRightAngle(source: HTMLCanvasElement, orientation: WorkingOrientation): HTMLCanvasElement {
  if (orientation === "original") return source;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  if (orientation === "rotate180") {
    canvas.width = source.width;
    canvas.height = source.height;
    ctx.translate(canvas.width, canvas.height);
    ctx.rotate(Math.PI);
    ctx.drawImage(source, 0, 0);
    return canvas;
  }
  canvas.width = source.height;
  canvas.height = source.width;
  if (orientation === "cw90") {
    ctx.translate(canvas.width, 0);
    ctx.rotate(Math.PI / 2);
  } else {
    ctx.translate(0, canvas.height);
    ctx.rotate(-Math.PI / 2);
  }
  ctx.drawImage(source, 0, 0);
  return canvas;
}

function gaussianBlur5(gray: Float32Array, width: number, height: number): Float32Array {
  const kernel = [1, 4, 6, 4, 1];
  const temp = new Float32Array(gray.length);
  const out = new Float32Array(gray.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let sum = 0;
      let weight = 0;
      for (let k = -2; k <= 2; k += 1) {
        const xx = Math.max(0, Math.min(width - 1, x + k));
        const kw = kernel[k + 2];
        sum += gray[y * width + xx] * kw;
        weight += kw;
      }
      temp[y * width + x] = sum / weight;
    }
  }
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let sum = 0;
      let weight = 0;
      for (let k = -2; k <= 2; k += 1) {
        const yy = Math.max(0, Math.min(height - 1, y + k));
        const kw = kernel[k + 2];
        sum += temp[yy * width + x] * kw;
        weight += kw;
      }
      out[y * width + x] = sum / weight;
    }
  }
  return out;
}

function grayscaleAndGradient(image: ImageData): { gray: Uint8Array; gradient: Float32Array } {
  const { width, height, data } = image;
  const raw = new Float32Array(width * height);
  const gray = new Uint8Array(width * height);
  for (let p = 0, i = 0; p < raw.length; p += 1, i += 4) {
    raw[p] = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
    gray[p] = Math.round(raw[p]);
  }
  const blurred = gaussianBlur5(raw, width, height);
  const gradient = new Float32Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const idx = y * width + x;
      const gx =
        -blurred[idx - width - 1] - 2 * blurred[idx - 1] - blurred[idx + width - 1] +
        blurred[idx - width + 1] + 2 * blurred[idx + 1] + blurred[idx + width + 1];
      const gy =
        -blurred[idx - width - 1] - 2 * blurred[idx - width] - blurred[idx - width + 1] +
        blurred[idx + width - 1] + 2 * blurred[idx + width] + blurred[idx + width + 1];
      gradient[idx] = Math.hypot(gx, gy);
    }
  }
  return { gray, gradient };
}

function rgbToHsv255(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;
  let hue = 0;
  if (delta > 0) {
    if (max === rn) hue = 60 * (((gn - bn) / delta) % 6);
    else if (max === gn) hue = 60 * ((bn - rn) / delta + 2);
    else hue = 60 * ((rn - gn) / delta + 4);
    if (hue < 0) hue += 360;
  }
  return { h: hue, s: max === 0 ? 0 : (delta / max) * 255, v: max * 255 };
}

function otsuThreshold(values: Uint8Array): number {
  const histogram = new Uint32Array(256);
  for (const value of values) histogram[value] += 1;
  let sum = 0;
  let total = 0;
  for (let i = 0; i < 256; i += 1) {
    sum += i * histogram[i];
    total += histogram[i];
  }
  let backgroundWeight = 0;
  let backgroundSum = 0;
  let bestVariance = -1;
  let threshold = 0;
  for (let i = 0; i < 256; i += 1) {
    backgroundWeight += histogram[i];
    if (!backgroundWeight) continue;
    const foregroundWeight = total - backgroundWeight;
    if (!foregroundWeight) break;
    backgroundSum += i * histogram[i];
    const backgroundMean = backgroundSum / backgroundWeight;
    const foregroundMean = (sum - backgroundSum) / foregroundWeight;
    const variance = backgroundWeight * foregroundWeight * (backgroundMean - foregroundMean) ** 2;
    if (variance > bestVariance) {
      bestVariance = variance;
      threshold = i;
    }
  }
  return threshold;
}

function boxMorphAxis(mask: Uint8Array, width: number, height: number, radius: number, axis: "x" | "y", dilate: boolean): Uint8Array {
  if (radius <= 0) return new Uint8Array(mask);
  const out = new Uint8Array(mask.length);
  if (axis === "x") {
    const prefix = new Int32Array(width + 1);
    for (let y = 0; y < height; y += 1) {
      prefix[0] = 0;
      for (let x = 0; x < width; x += 1) prefix[x + 1] = prefix[x] + mask[y * width + x];
      for (let x = 0; x < width; x += 1) {
        const left = Math.max(0, x - radius);
        const right = Math.min(width - 1, x + radius);
        const count = prefix[right + 1] - prefix[left];
        const full = 2 * radius + 1;
        out[y * width + x] = dilate ? (count > 0 ? 1 : 0) : (left === x - radius && right === x + radius && count === full ? 1 : 0);
      }
    }
  } else {
    const prefix = new Int32Array(height + 1);
    for (let x = 0; x < width; x += 1) {
      prefix[0] = 0;
      for (let y = 0; y < height; y += 1) prefix[y + 1] = prefix[y] + mask[y * width + x];
      for (let y = 0; y < height; y += 1) {
        const top = Math.max(0, y - radius);
        const bottom = Math.min(height - 1, y + radius);
        const count = prefix[bottom + 1] - prefix[top];
        const full = 2 * radius + 1;
        out[y * width + x] = dilate ? (count > 0 ? 1 : 0) : (top === y - radius && bottom === y + radius && count === full ? 1 : 0);
      }
    }
  }
  return out;
}

function dilateBox(mask: Uint8Array, width: number, height: number, radius: number): Uint8Array {
  return boxMorphAxis(boxMorphAxis(mask, width, height, radius, "x", true), width, height, radius, "y", true);
}

function erodeBox(mask: Uint8Array, width: number, height: number, radius: number): Uint8Array {
  return boxMorphAxis(boxMorphAxis(mask, width, height, radius, "x", false), width, height, radius, "y", false);
}

function cleanMask(mask: Uint8Array, width: number, height: number, openRadius: number, closeRadius: number): Uint8Array {
  let out = mask;
  if (openRadius > 0) out = dilateBox(erodeBox(out, width, height, openRadius), width, height, openRadius);
  if (closeRadius > 0) out = erodeBox(dilateBox(out, width, height, closeRadius), width, height, closeRadius);
  return out;
}

function buildCandidateMasks(image: ImageData, gradient: Float32Array): Array<{ name: string; mask: Uint8Array }> {
  const count = image.width * image.height;
  const cool = new Uint8Array(count);
  const saturationValues = new Uint8Array(count);
  const bright = new Uint8Array(count);
  const edge = new Uint8Array(count);
  for (let p = 0, i = 0; p < count; p += 1, i += 4) {
    const hsv = rgbToHsv255(image.data[i], image.data[i + 1], image.data[i + 2]);
    saturationValues[p] = Math.round(hsv.s);
    // OpenCV sandbox used H=35..135 on a 0..179 hue scale => approximately 70..270 degrees in browser HSV.
    if (hsv.h >= 70 && hsv.h <= 270 && hsv.s >= 18 && hsv.v >= 60) cool[p] = 1;
    if (hsv.v >= 100) bright[p] = 1;
    if (gradient[p] >= 70) edge[p] = 1;
  }
  const satThreshold = otsuThreshold(saturationValues);
  const saturation = new Uint8Array(count);
  for (let p = 0; p < count; p += 1) if (saturationValues[p] >= Math.max(18, satThreshold)) saturation[p] = 1;

  return [
    { name: "cool", mask: cleanMask(cool, image.width, image.height, 2, 9) },
    { name: "saturation", mask: cleanMask(saturation, image.width, image.height, 2, 7) },
    { name: "bright", mask: cleanMask(bright, image.width, image.height, 1, 5) },
    { name: "edge", mask: cleanMask(edge, image.width, image.height, 0, 3) },
  ];
}

function connectedComponents(mask: Uint8Array, width: number, height: number): Component[] {
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const minArea = width * height * 0.0035;
  const components: Component[] = [];
  for (let y0 = 0; y0 < height; y0 += 1) {
    for (let x0 = 0; x0 < width; x0 += 1) {
      const start = y0 * width + x0;
      if (!mask[start] || visited[start]) continue;
      let head = 0;
      let tail = 0;
      queue[tail++] = start;
      visited[start] = 1;
      let area = 0;
      const boundary: Point[] = [];
      let boundarySeen = 0;
      let boundaryRng = (start ^ 0x9e3779b9) >>> 0;
      while (head < tail) {
        const index = queue[head++];
        const x = index % width;
        const y = Math.floor(index / width);
        area += 1;
        let isBoundary = false;
        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            if (!dx && !dy) continue;
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
              isBoundary = true;
              continue;
            }
            const ni = ny * width + nx;
            if (!mask[ni]) isBoundary = true;
            if (mask[ni] && !visited[ni]) {
              visited[ni] = 1;
              queue[tail++] = ni;
            }
          }
        }
        if (isBoundary) {
          // Keep a deterministic reservoir across the ENTIRE component boundary.
          // The old first-6000 cap biased the rough rectangle toward whichever
          // boundary region BFS happened to visit first and could discard the
          // opposite DL edges on highly textured cards.
          boundarySeen += 1;
          if (boundary.length < 6000) {
            boundary.push({ x, y });
          } else {
            boundaryRng = (1664525 * boundaryRng + 1013904223) >>> 0;
            const slot = Math.floor((boundaryRng / 0x100000000) * boundarySeen);
            if (slot < 6000) boundary[slot] = { x, y };
          }
        }
      }
      if (area >= minArea && boundary.length >= 8) {
        const sampled: Point[] = [];
        const target = Math.min(1500, boundary.length);
        for (let i = 0; i < target; i += 1) sampled.push(boundary[Math.floor((i * boundary.length) / target)]);
        components.push({ area, boundary: sampled });
      }
    }
  }
  return components.sort((a, b) => b.area - a.area).slice(0, 6);
}

function cross(o: Point, a: Point, b: Point): number {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => (a.x - b.x) || (a.y - b.y));
  if (sorted.length <= 2) return sorted;
  const lower: Point[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  }
  const upper: Point[] = [];
  for (let i = sorted.length - 1; i >= 0; i -= 1) {
    const point = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function minimumAreaRectangle(points: Point[]): { box: Point[]; width: number; height: number; area: number } | null {
  const hull = convexHull(points);
  if (hull.length < 3) return null;
  let best: { box: Point[]; width: number; height: number; area: number } | null = null;
  for (let i = 0; i < hull.length; i += 1) {
    const a = hull[i];
    const b = hull[(i + 1) % hull.length];
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const cos = Math.cos(-angle);
    const sin = Math.sin(-angle);
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const point of hull) {
      const x = point.x * cos - point.y * sin;
      const y = point.x * sin + point.y * cos;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
    const rw = maxX - minX;
    const rh = maxY - minY;
    const area = rw * rh;
    if (!best || area < best.area) {
      const inverseCos = Math.cos(angle);
      const inverseSin = Math.sin(angle);
      const rotated = [
        { x: minX, y: minY }, { x: maxX, y: minY }, { x: maxX, y: maxY }, { x: minX, y: maxY },
      ];
      best = {
        width: rw,
        height: rh,
        area,
        box: orderCorners(rotated.map((p) => ({
          x: p.x * inverseCos - p.y * inverseSin,
          y: p.x * inverseSin + p.y * inverseCos,
        }))),
      };
    }
  }
  return best;
}

function combinations<T>(items: T[], maxTake: number): T[][] {
  const output: T[][] = [];
  function walk(start: number, take: number, current: T[]): void {
    if (current.length === take) {
      output.push([...current]);
      return;
    }
    for (let i = start; i < items.length; i += 1) {
      current.push(items[i]);
      walk(i + 1, take, current);
      current.pop();
    }
  }
  for (let take = 1; take <= Math.min(maxTake, items.length); take += 1) walk(0, take, []);
  return output;
}

function roughCandidates(image: ImageData, gradient: Float32Array): RoughCandidate[] {
  const candidates: RoughCandidate[] = [];
  const masks = buildCandidateMasks(image, gradient);
  masks.forEach(({ name, mask }, maskRank) => {
    const components = connectedComponents(mask, image.width, image.height);
    for (const group of combinations(components, 4)) {
      const points = group.flatMap((component) => component.boundary);
      if (points.length < 20) continue;
      const rectangle = minimumAreaRectangle(points);
      if (!rectangle) continue;
      const longSide = Math.max(rectangle.width, rectangle.height);
      const shortSide = Math.min(rectangle.width, rectangle.height);
      if (shortSide < 20) continue;
      const ratio = longSide / shortSide;
      const areaRatio = rectangle.area / (image.width * image.height);
      if (areaRatio < 0.03 || areaRatio > 0.94) continue;
      if (ratio < 1.05 || ratio > 3.0) continue;
      const density = Math.min(1, group.reduce((sum, component) => sum + component.area, 0) / Math.max(1, rectangle.area));
      const aspectError = Math.abs(ratio - DL_ASPECT) / DL_ASPECT;
      const score = aspectError * 1.5 - density * 0.45 + maskRank * 0.04;
      candidates.push({ box: orderCorners(rectangle.box), score, source: name, areaRatio, roughAspect: ratio, density });
    }
  });
  return candidates.sort((a, b) => a.score - b.score).slice(0, 14);
}

function sampleBoundaryPoints(
  gradient: Float32Array,
  width: number,
  height: number,
  p0: Point,
  p1: Point,
  searchPx: number,
): Point[] {
  const edgeLength = distance(p0, p1);
  if (edgeLength < 1) return [];
  const tx = (p1.x - p0.x) / edgeLength;
  const ty = (p1.y - p0.y) / edgeLength;
  const nx = -ty;
  const ny = tx;
  const points: Point[] = [];
  for (let sample = 0; sample < EDGE_SAMPLE_COUNT; sample += 1) {
    const t = EDGE_SAMPLE_CORNER_IGNORE_START +
      (sample / Math.max(1, EDGE_SAMPLE_COUNT - 1)) * (EDGE_SAMPLE_CORNER_IGNORE_END - EDGE_SAMPLE_CORNER_IGNORE_START);
    const bx = p0.x + t * (p1.x - p0.x);
    const by = p0.y + t * (p1.y - p0.y);
    let bestScore = -Infinity;
    let bestGradient = 0;
    let bestPoint: Point | null = null;
    for (let offset = -searchPx; offset <= searchPx; offset += 1) {
      const x = Math.round(bx + offset * nx);
      const y = Math.round(by + offset * ny);
      if (x < 1 || y < 1 || x >= width - 1 || y >= height - 1) continue;
      const value = gradient[y * width + x];
      const score = value - Math.abs(offset) * 0.6;
      if (score > bestScore) {
        bestScore = score;
        bestGradient = value;
        bestPoint = { x, y };
      }
    }
    if (bestPoint && bestGradient >= GRADIENT_MAG_THRESHOLD) points.push(bestPoint);
  }
  return points;
}

function seededRandom(state: { value: number }): number {
  state.value = (1664525 * state.value + 1013904223) >>> 0;
  return state.value / 0x100000000;
}

function fitPcaLine(points: Point[]): { line: LineParam; fitError: number } | null {
  if (points.length < 2) return null;
  let mx = 0;
  let my = 0;
  for (const point of points) {
    mx += point.x;
    my += point.y;
  }
  mx /= points.length;
  my /= points.length;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (const point of points) {
    const dx = point.x - mx;
    const dy = point.y - my;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  const theta = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const line = { vx: Math.cos(theta), vy: Math.sin(theta), x0: mx, y0: my };
  let sumSq = 0;
  for (const point of points) {
    const dx = point.x - mx;
    const dy = point.y - my;
    const error = Math.abs(line.vx * dy - line.vy * dx);
    sumSq += error * error;
  }
  return { line, fitError: Math.sqrt(sumSq / points.length) };
}

function pointLineDistance(point: Point, line: LineParam): number {
  const dx = point.x - line.x0;
  const dy = point.y - line.y0;
  return Math.abs(line.vx * dy - line.vy * dx);
}

function edgeCoverage(points: Point[], p0: Point, p1: Point): number {
  if (!points.length) return 0;
  const length = distance(p0, p1);
  if (length < 1e-9) return 0;
  const tx = (p1.x - p0.x) / length;
  const ty = (p1.y - p0.y) / length;
  const projections = points.map((p) => (p.x - p0.x) * tx + (p.y - p0.y) * ty);
  return (Math.max(...projections) - Math.min(...projections)) / length;
}

function ransacLine(points: Point[], p0: Point, p1: Point, seedValue: number): RansacResult {
  if (points.length < 20) return { line: null, inlierIndices: [], fitError: Infinity, coverage: 0 };
  const random = { value: seedValue >>> 0 };
  let best: number[] = [];
  for (let iteration = 0; iteration < RANSAC_ITERATIONS; iteration += 1) {
    const i = Math.floor(seededRandom(random) * points.length);
    let j = Math.floor(seededRandom(random) * points.length);
    if (j === i) j = (j + 1) % points.length;
    const candidate = lineFromPoints(points[i], points[j]);
    if (!candidate || distance(points[i], points[j]) < 5) continue;
    const inliers: number[] = [];
    for (let k = 0; k < points.length; k += 1) {
      if (pointLineDistance(points[k], candidate) <= RANSAC_DISTANCE_THRESHOLD) inliers.push(k);
    }
    if (inliers.length > best.length) best = inliers;
  }
  const inlierPoints = best.map((index) => points[index]);
  const fit = fitPcaLine(inlierPoints);
  return {
    line: fit?.line ?? null,
    inlierIndices: best,
    fitError: fit?.fitError ?? Infinity,
    coverage: edgeCoverage(inlierPoints, p0, p1),
  };
}

function confirmFourEdges(
  image: ImageData,
  gradient: Float32Array,
  rough: RoughCandidate,
  seed: number,
): { confirmed: ConfirmedGeometry | null; diagnostics: Partial<Record<EdgeName, EdgeDiagnostics>>; reason?: string } {
  const box = orderCorners(rough.box);
  const lengths = [distance(box[0], box[1]), distance(box[1], box[2]), distance(box[2], box[3]), distance(box[3], box[0])];
  const shortSide = Math.min(...lengths);
  const searchPx = Math.round(Math.max(SEARCH_PX_MIN, Math.min(SEARCH_PX_MAX, shortSide * SEARCH_PX_RATIO)));
  const names: EdgeName[] = ["top", "right", "bottom", "left"];
  const lines = {} as Record<EdgeName, LineParam>;
  const diagnostics: Partial<Record<EdgeName, EdgeDiagnostics>> = {};

  for (let i = 0; i < 4; i += 1) {
    const p0 = box[i];
    const p1 = box[(i + 1) % 4];
    const samples = sampleBoundaryPoints(gradient, image.width, image.height, p0, p1, searchPx);
    const result = ransacLine(samples, p0, p1, seed + i * 977);
    const inliers = result.inlierIndices.length;
    const ratio = samples.length ? inliers / samples.length : 0;
    const required = Math.max(MIN_ABSOLUTE_INLIERS, Math.ceil(samples.length * MIN_INLIER_RATIO));
    const confirmed = Boolean(
      result.line && inliers >= required && ratio >= MIN_INLIER_RATIO && result.coverage >= MIN_EDGE_SPAN_COVERAGE,
    );
    diagnostics[names[i]] = {
      samples: samples.length,
      inliers,
      inlier_ratio: ratio,
      coverage: result.coverage,
      line_angle_deg: result.line ? axialAngleDeg(result.line) : 0,
      fit_error: result.fitError,
      confirmed,
    };
    if (!confirmed || !result.line) return { confirmed: null, diagnostics, reason: `${names[i]}_not_confirmed` };
    lines[names[i]] = result.line;
  }

  const edges = { ...lines, all_four_confirmed: true as const };
  const corners = cornersFromEdgeLines(edges);
  if (!corners) return { confirmed: null, diagnostics, reason: "four_line_intersections_failed" };
  const sanity = validateSourceQuadrilateral(corners, image.width, image.height);
  if (!sanity.valid) return { confirmed: null, diagnostics, reason: sanity.reason ?? "quadrilateral_sanity_failed" };

  return {
    confirmed: {
      corners,
      edges,
      diagnostics: diagnostics as Record<EdgeName, EdgeDiagnostics>,
    },
    diagnostics,
  };
}

function edgeQualityPenalty(diagnostics: Record<EdgeName, EdgeDiagnostics>): number {
  const values = Object.values(diagnostics);
  return values.reduce((sum, edge) => {
    const fitPenalty = Number.isFinite(edge.fit_error) ? Math.min(1, edge.fit_error / 8) : 1;
    return sum + (1 - Math.min(1, edge.inlier_ratio)) * 0.25 + (1 - Math.min(1, edge.coverage)) * 0.25 + fitPenalty * 0.08;
  }, 0) / values.length;
}

function findBestCandidate(baseAnalysis: HTMLCanvasElement): BestCandidate | null {
  let best: BestCandidate | null = null;
  ORIENTATION_ORDER.forEach((orientation, orientationRank) => {
    const oriented = rotateRightAngle(baseAnalysis, orientation);
    const ctx = oriented.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    const image = ctx.getImageData(0, 0, oriented.width, oriented.height);
    const { gradient } = grayscaleAndGradient(image);
    const seeds = roughCandidates(image, gradient);
    seeds.forEach((rough, seedRank) => {
      const result = confirmFourEdges(image, gradient, rough, 0x5f3759df + orientationRank * 1009 + seedRank * 7919);
      if (!result.confirmed) return;
      const metrics = measureQuadrilateral(result.confirmed.corners, result.confirmed.edges, oriented.width, oriented.height);
      const classification = classifyGeometry(result.confirmed.corners, result.confirmed.edges, metrics);
      const score = rough.score + edgeQualityPenalty(result.confirmed.diagnostics) + orientationRank * 0.002 + seedRank * 0.001;
      const candidate: BestCandidate = {
        orientation,
        orientationWidth: oriented.width,
        orientationHeight: oriented.height,
        rough,
        confirmed: result.confirmed,
        metrics,
        classification,
        score,
      };
      if (!best || candidate.score < best.score) best = candidate;
    });
  });
  return best;
}

function cropAndResize(source: HTMLCanvasElement, cornersInput: Point[]): HTMLCanvasElement | null {
  const corners = orderCorners(cornersInput);
  const xs = corners.map((p) => p.x);
  const ys = corners.map((p) => p.y);
  const x0 = Math.max(0, Math.floor(Math.min(...xs)));
  const y0 = Math.max(0, Math.floor(Math.min(...ys)));
  const x1 = Math.min(source.width, Math.ceil(Math.max(...xs)));
  const y1 = Math.min(source.height, Math.ceil(Math.max(...ys)));
  const width = x1 - x0;
  const height = y1 - y0;
  if (width < 20 || height < 20) return null;
  const output = document.createElement("canvas");
  output.width = TARGET_W;
  output.height = TARGET_H;
  output.getContext("2d")!.drawImage(source, x0, y0, width, height, 0, 0, TARGET_W, TARGET_H);
  return output;
}

function rotateExpandedWithPoints(source: HTMLCanvasElement, corners: Point[], degrees: number): { canvas: HTMLCanvasElement; corners: Point[] } {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const width = Math.ceil(source.width * Math.abs(cos) + source.height * Math.abs(sin));
  const height = Math.ceil(source.width * Math.abs(sin) + source.height * Math.abs(cos));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(width / 2, height / 2);
  ctx.rotate(radians);
  ctx.drawImage(source, -source.width / 2, -source.height / 2);
  return {
    canvas,
    corners: corners.map((point) => rotatePointAroundImageCenter(point, source.width, source.height, width, height, degrees)),
  };
}

function solveHomography(source: Point[], destination: Point[]): number[] {
  if (source.length !== 4 || destination.length !== 4) throw new Error("Homography requires four points");
  const matrix: number[][] = [];
  for (let i = 0; i < 4; i += 1) {
    const { x, y } = source[i];
    const { x: xp, y: yp } = destination[i];
    matrix.push([x, y, 1, 0, 0, 0, -xp * x, -xp * y, xp]);
    matrix.push([0, 0, 0, x, y, 1, -yp * x, -yp * y, yp]);
  }
  const n = 8;
  for (let column = 0; column < n; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < n; row += 1) {
      if (Math.abs(matrix[row][column]) > Math.abs(matrix[pivot][column])) pivot = row;
    }
    if (Math.abs(matrix[pivot][column]) < 1e-10) throw new Error("Singular homography");
    [matrix[column], matrix[pivot]] = [matrix[pivot], matrix[column]];
    for (let row = column + 1; row < n; row += 1) {
      const factor = matrix[row][column] / matrix[column][column];
      for (let k = column; k <= n; k += 1) matrix[row][k] -= factor * matrix[column][k];
    }
  }
  const h = new Array<number>(n).fill(0);
  for (let i = n - 1; i >= 0; i -= 1) {
    let rhs = matrix[i][n];
    for (let j = i + 1; j < n; j += 1) rhs -= matrix[i][j] * h[j];
    h[i] = rhs / matrix[i][i];
    if (!Number.isFinite(h[i])) throw new Error("Non-finite homography");
  }
  return [...h, 1];
}

/** Inverse-map every output pixel to source for stable bilinear sampling. */
function perspectiveWarp(source: HTMLCanvasElement, cornersInput: Point[]): HTMLCanvasElement {
  const corners = orderCorners(cornersInput);
  const destination: Point[] = [
    { x: 0, y: 0 },
    { x: TARGET_W - 1, y: 0 },
    { x: TARGET_W - 1, y: TARGET_H - 1 },
    { x: 0, y: TARGET_H - 1 },
  ];
  // We need destination -> source because the raster loop iterates destination pixels.
  const inverse = solveHomography(destination, corners);
  const sourceCtx = source.getContext("2d", { willReadFrequently: true })!;
  const sourceData = sourceCtx.getImageData(0, 0, source.width, source.height);
  const output = document.createElement("canvas");
  output.width = TARGET_W;
  output.height = TARGET_H;
  const outputCtx = output.getContext("2d", { willReadFrequently: true })!;
  const outData = outputCtx.createImageData(TARGET_W, TARGET_H);

  for (let y = 0; y < TARGET_H; y += 1) {
    for (let x = 0; x < TARGET_W; x += 1) {
      const w = inverse[6] * x + inverse[7] * y + inverse[8];
      if (Math.abs(w) < 1e-10) continue;
      const sx = (inverse[0] * x + inverse[1] * y + inverse[2]) / w;
      const sy = (inverse[3] * x + inverse[4] * y + inverse[5]) / w;
      if (!Number.isFinite(sx) || !Number.isFinite(sy) || sx < 0 || sy < 0 || sx > source.width - 1 || sy > source.height - 1) continue;
      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const x1 = Math.min(source.width - 1, x0 + 1);
      const y1 = Math.min(source.height - 1, y0 + 1);
      const fx = sx - x0;
      const fy = sy - y0;
      const out = (y * TARGET_W + x) * 4;
      for (let channel = 0; channel < 3; channel += 1) {
        const i00 = (y0 * source.width + x0) * 4 + channel;
        const i10 = (y0 * source.width + x1) * 4 + channel;
        const i01 = (y1 * source.width + x0) * 4 + channel;
        const i11 = (y1 * source.width + x1) * 4 + channel;
        outData.data[out + channel] = Math.round(
          sourceData.data[i00] * (1 - fx) * (1 - fy) +
          sourceData.data[i10] * fx * (1 - fy) +
          sourceData.data[i01] * (1 - fx) * fy +
          sourceData.data[i11] * fx * fy,
        );
      }
      outData.data[out + 3] = 255;
    }
  }
  outputCtx.putImageData(outData, 0, 0);
  return output;
}

function reportFor(
  best: BestCandidate | null,
  exifOrientation: number,
  analysis: HTMLCanvasElement,
  status: DriverLicenseProcessReport["status"],
  correction: DriverLicenseProcessReport["correction"],
  postValidation?: Record<string, unknown>,
  finalDimensions?: { width: number; height: number },
  failureReason?: string,
  postRotationGeometry?: Record<string, unknown>,
): DriverLicenseProcessReport {
  const semantic = semanticOrientationUnavailable();
  if (!best) {
    return {
      preprocess_version: PREPROCESS_VERSION,
      status,
      four_edges_confirmed: false,
      orientation_preflight: { exif: exifOrientation, semantic },
      semantic_post_check: semantic,
      analysis_width: analysis.width,
      analysis_height: analysis.height,
      classification: "UNCONFIRMED",
      correction: "NONE",
      failure_reason: failureReason ?? "no_four_edge_candidate",
    };
  }
  const [tl, tr, br, bl] = orderCorners(best.confirmed.corners);
  return {
    preprocess_version: PREPROCESS_VERSION,
    status,
    four_edges_confirmed: true,
    orientation_preflight: { exif: exifOrientation, semantic, selected_geometry_orientation: best.orientation },
    semantic_post_check: semantic,
    analysis_width: best.orientationWidth,
    analysis_height: best.orientationHeight,
    rough_candidate_source: best.rough.source,
    rough_candidate_score: best.rough.score,
    top: best.confirmed.diagnostics.top,
    right: best.confirmed.diagnostics.right,
    bottom: best.confirmed.diagnostics.bottom,
    left: best.confirmed.diagnostics.left,
    corners: { TL: tl, TR: tr, BR: br, BL: bl },
    angles: {
      TL: best.metrics.corner_angles_deg[0],
      TR: best.metrics.corner_angles_deg[1],
      BR: best.metrics.corner_angles_deg[2],
      BL: best.metrics.corner_angles_deg[3],
    },
    top_angle_deg: best.metrics.top_angle_deg,
    right_angle_deg: best.metrics.right_angle_deg,
    bottom_angle_deg: best.metrics.bottom_angle_deg,
    left_angle_deg: best.metrics.left_angle_deg,
    parallel_error: {
      top_bottom: best.metrics.parallel_error_top_bottom_deg,
      left_right: best.metrics.parallel_error_left_right_deg,
    },
    level_error: best.metrics.level_errors,
    source_aspect: best.metrics.source_aspect,
    classification: best.classification,
    correction,
    rotation_angle_deg: best.classification === "FLAT_ROTATED" ? best.metrics.rotation_action_deg : undefined,
    post_rotation_geometry: postRotationGeometry,
    post_validation: postValidation,
    final_dimensions: finalDimensions,
    failure_reason: failureReason,
  };
}

export async function processDriverLicenseCanvas(sourceCanvas: HTMLCanvasElement, exifOrientation = 1): Promise<DriverLicenseProcessResult> {
  const scale = Math.min(1, ANALYSIS_MAX_LONG_SIDE / Math.max(sourceCanvas.width, sourceCanvas.height));
  const analysis = scale < 1
    ? resizeCanvas(sourceCanvas, sourceCanvas.width * scale, sourceCanvas.height * scale)
    : sourceCanvas;
  const best = findBestCandidate(analysis);
  if (!best || best.classification === "UNCONFIRMED") {
    const report = reportFor(best, exifOrientation, analysis, "AUTOMATIC_GEOMETRY_UNCONFIRMED", "NONE", undefined, undefined, "four_edges_not_confirmed");
    return { status: "MANUAL_REVIEW", report, metadata: report };
  }

  const fullOriented = rotateRightAngle(sourceCanvas, best.orientation);
  const sx = fullOriented.width / best.orientationWidth;
  const sy = fullOriented.height / best.orientationHeight;
  const fullCorners = best.confirmed.corners.map((point) => ({ x: point.x * sx, y: point.y * sy }));

  try {
    let corrected: HTMLCanvasElement | null = null;
    let correction: DriverLicenseProcessReport["correction"] = "NONE";
    let postRotationGeometry: Record<string, unknown> | undefined;

    if (best.classification === "FLAT_LEVEL") {
      correction = "CROP";
      corrected = cropAndResize(fullOriented, fullCorners);
    } else if (best.classification === "FLAT_ROTATED") {
      correction = "ROTATE";
      const rotated = rotateExpandedWithPoints(fullOriented, fullCorners, best.metrics.rotation_action_deg);
      const rotatedEdges: EdgeLines = {
        top: lineFromPoints(rotated.corners[0], rotated.corners[1]) ?? undefined,
        right: lineFromPoints(rotated.corners[1], rotated.corners[2]) ?? undefined,
        bottom: lineFromPoints(rotated.corners[3], rotated.corners[2]) ?? undefined,
        left: lineFromPoints(rotated.corners[0], rotated.corners[3]) ?? undefined,
        all_four_confirmed: true,
      };
      const rotatedMetrics = measureQuadrilateral(rotated.corners, rotatedEdges, rotated.canvas.width, rotated.canvas.height);
      const level = rotatedMetrics.level_errors;
      const rotationGeometryPass =
        level.top_horizontal_error_deg <= LEVEL_TOLERANCE_DEG &&
        level.bottom_horizontal_error_deg <= LEVEL_TOLERANCE_DEG &&
        level.left_vertical_error_deg <= LEVEL_TOLERANCE_DEG &&
        level.right_vertical_error_deg <= LEVEL_TOLERANCE_DEG &&
        rotatedMetrics.parallel_error_top_bottom_deg <= PARALLEL_TOLERANCE_DEG &&
        rotatedMetrics.parallel_error_left_right_deg <= PARALLEL_TOLERANCE_DEG;
      postRotationGeometry = {
        level_error: level,
        parallel_error_top_bottom_deg: rotatedMetrics.parallel_error_top_bottom_deg,
        parallel_error_left_right_deg: rotatedMetrics.parallel_error_left_right_deg,
        pass: rotationGeometryPass,
      };
      if (!rotationGeometryPass) throw new Error("post_rotation_geometry_failed");
      corrected = cropAndResize(rotated.canvas, rotated.corners);
    } else if (best.classification === "PERSPECTIVE") {
      correction = "PERSPECTIVE_WARP";
      corrected = perspectiveWarp(fullOriented, fullCorners);
    }

    if (!corrected) {
      const report = reportFor(best, exifOrientation, analysis, "AUTOMATIC_GEOMETRY_FAILED_VALIDATION", correction, undefined, undefined, "correction_failed", postRotationGeometry);
      return { status: "MANUAL_REVIEW", report, metadata: report, suggestedCorners: fullCorners };
    }

    const validation = postValidateCanvas(corrected, best.classification);
    if (!validation.pass) {
      const report = reportFor(
        best,
        exifOrientation,
        analysis,
        "AUTOMATIC_GEOMETRY_FAILED_VALIDATION",
        correction,
        validation.report,
        { width: corrected.width, height: corrected.height },
        "post_validation_failed",
        postRotationGeometry,
      );
      return { status: "MANUAL_REVIEW", report, metadata: report, suggestedCorners: fullCorners };
    }

    const report = reportFor(
      best,
      exifOrientation,
      analysis,
      "PROCESSED",
      correction,
      validation.report,
      { width: corrected.width, height: corrected.height },
      undefined,
      postRotationGeometry,
    );
    return {
      status: "SUCCESS",
      processedBlob: await canvasToBlob(corrected),
      report,
      metadata: report,
      suggestedCorners: fullCorners,
    };
  } catch (error) {
    const report = reportFor(
      best,
      exifOrientation,
      analysis,
      "AUTOMATIC_GEOMETRY_FAILED_VALIDATION",
      "NONE",
      undefined,
      undefined,
      error instanceof Error ? error.message : "processing_exception",
    );
    return { status: "MANUAL_REVIEW", report, metadata: report, suggestedCorners: fullCorners };
  }
}

export async function processDriverLicenseFile(file: File): Promise<DriverLicenseProcessResult> {
  const { canvas, exifOrientation } = await fileToExifCorrectedCanvas(file);
  return processDriverLicenseCanvas(canvas, exifOrientation);
}

/** Compatibility name used by the earlier browser integration. */
export const preprocessDriverLicense = processDriverLicenseFile;
