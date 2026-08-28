export type DlPoint = { x: number; y: number };
export type DlEdgeName = "top" | "right" | "bottom" | "left";
export type DlGeometryClass = "FLAT_LEVEL" | "FLAT_ROTATED" | "PERSPECTIVE" | "UNCONFIRMED";
export type DlCorrection = "NONE_CROP" | "ROTATE" | "PERSPECTIVE_WARP" | "NONE";
export type DlSemanticRotation = 0 | 90 | 180 | 270 | "unknown";

export type SemanticOrientationResult = {
  rotation: DlSemanticRotation;
  confidence: number;
  engine?: string;
};

export type SemanticOrientationResolver = (
  canvas: HTMLCanvasElement,
) => Promise<SemanticOrientationResult>;

export type DlEdgeEvidence = {
  name: DlEdgeName;
  samples: number;
  inliers: number;
  inlierRatio: number;
  coverage: number;
  fitError: number;
  lineAngleDeg: number;
};

export type DlGeometryMeasurements = {
  cornerAnglesDeg: { TL: number; TR: number; BR: number; BL: number };
  cornerAngleErrorsDeg: { TL: number; TR: number; BR: number; BL: number };
  topAngleDeg: number;
  rightAngleDeg: number;
  bottomAngleDeg: number;
  leftAngleDeg: number;
  topBottomParallelErrorDeg: number;
  leftRightParallelErrorDeg: number;
  longEdgeHorizontalErrorDeg: number;
  shortEdgeVerticalErrorDeg: number;
  longEdgesAreTopBottom: boolean;
  sourceAspect: number;
  sourceAreaRatio: number;
};

export type DlPostValidation = {
  valid: boolean;
  reasons: string[];
  width: number;
  height: number;
  outputAspect: number;
  blackBorderFraction: number;
};

export type DlPreprocessMetadata = {
  version: string;
  analysisWidth: number;
  analysisHeight: number;
  orientationPreflight: SemanticOrientationResult;
  orientationPostflight: SemanticOrientationResult;
  roughCandidateScore?: number;
  edges?: Record<DlEdgeName, DlEdgeEvidence>;
  corners?: { TL: DlPoint; TR: DlPoint; BR: DlPoint; BL: DlPoint };
  measurements?: DlGeometryMeasurements;
  classification: DlGeometryClass;
  correction: DlCorrection;
  rotationAngleDeg?: number;
  postValidation?: DlPostValidation;
  failureReason?: string;
};

export type DlPreprocessResult = {
  ok: boolean;
  processedBlob: Blob | null;
  processedPreviewCanvas: HTMLCanvasElement | null;
  metadata: DlPreprocessMetadata;
  suggestedCorners?: DlPoint[];
};

export type DlPreprocessOptions = {
  analysisMaxDimension?: number;
  targetWidth?: number;
  targetHeight?: number;
  semanticOrientationResolver?: SemanticOrientationResolver;
};

const VERSION = "browser-four-edge-v1";
const ID1_ASPECT = 85.6 / 53.98;
export const DL_TARGET_WIDTH = 1000;
export const DL_TARGET_HEIGHT = Math.round(DL_TARGET_WIDTH / ID1_ASPECT);

const ANALYSIS_MAX_DIMENSION = 1600;
const EDGE_SAMPLE_COUNT = 180;
const EDGE_SAMPLE_MARGIN_RATIO = 0.08;
const EDGE_SEARCH_RATIO_OF_SHORT_SIDE = 0.12;
const EDGE_SEARCH_MIN_PX = 22;
const EDGE_SEARCH_MAX_PX = 110;
const EDGE_GRADIENT_MIN = 25;
const EDGE_RANSAC_DISTANCE_PX = 4.5;
const EDGE_RANSAC_ITERATIONS = 400;
const EDGE_MIN_INLIERS = 50;
const EDGE_MIN_INLIER_RATIO = 0.28;
const EDGE_MIN_COVERAGE = 0.52;

export const RECTANGLE_CORNER_TOLERANCE_DEG = 4;
export const PARALLEL_TOLERANCE_DEG = 3;
export const LEVEL_TOLERANCE_DEG = 2;

const SOURCE_MIN_AREA_RATIO = 0.045;
const SOURCE_MAX_AREA_RATIO = 0.78;
const SOURCE_MIN_SANITY_ASPECT = 0.9;
const SOURCE_MAX_SANITY_ASPECT = 2.6;
const SEMANTIC_ORIENTATION_MIN_CONFIDENCE = 0.85;

const EDGE_NAMES: DlEdgeName[] = ["top", "right", "bottom", "left"];

type FittedLine = { vx: number; vy: number; x: number; y: number };
type BoundarySample = DlPoint & { t: number };
type RansacFit = { line: FittedLine; inlierIndices: number[]; rms: number; coverage: number };
type RoughCandidate = { box: DlPoint[]; score: number; source: string; componentArea: number };
type ConfirmedCandidate = { corners: DlPoint[]; edges: Record<DlEdgeName, DlEdgeEvidence>; score: number };

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function distance(a: DlPoint, b: DlPoint): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function dot(a: DlPoint, b: DlPoint): number {
  return a.x * b.x + a.y * b.y;
}

function subtract(a: DlPoint, b: DlPoint): DlPoint {
  return { x: a.x - b.x, y: a.y - b.y };
}

function add(a: DlPoint, b: DlPoint): DlPoint {
  return { x: a.x + b.x, y: a.y + b.y };
}

function scale(a: DlPoint, k: number): DlPoint {
  return { x: a.x * k, y: a.y * k };
}

function lineAngleDeg(a: DlPoint, b: DlPoint): number {
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
}

function axialAngleDeg(angle: number): number {
  let value = ((angle + 90) % 180 + 180) % 180 - 90;
  if (Object.is(value, -0)) value = 0;
  return value;
}

function axialDifferenceDeg(a: number, b: number): number {
  return Math.abs(axialAngleDeg(a - b));
}

function horizontalErrorDeg(angle: number): number {
  return Math.abs(axialAngleDeg(angle));
}

function verticalErrorDeg(angle: number): number {
  return Math.abs(90 - Math.abs(axialAngleDeg(angle)));
}

function meanAxialAngleDeg(a: number, b: number): number {
  const ar = (2 * a * Math.PI) / 180;
  const br = (2 * b * Math.PI) / 180;
  const x = Math.cos(ar) + Math.cos(br);
  const y = Math.sin(ar) + Math.sin(br);
  return axialAngleDeg((Math.atan2(y, x) * 90) / Math.PI);
}

function angleAt(prev: DlPoint, p: DlPoint, next: DlPoint): number {
  const v1 = subtract(prev, p);
  const v2 = subtract(next, p);
  const denom = Math.hypot(v1.x, v1.y) * Math.hypot(v2.x, v2.y);
  if (denom < 1e-8) return 0;
  const cosine = clamp(dot(v1, v2) / denom, -1, 1);
  return (Math.acos(cosine) * 180) / Math.PI;
}

function polygonArea(points: DlPoint[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

export function isConvexQuadrilateral(points: DlPoint[]): boolean {
  if (points.length !== 4) return false;
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % 4];
    const c = points[(i + 2) % 4];
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cross) < 1e-6) return false;
    const current = Math.sign(cross);
    if (sign === 0) sign = current;
    if (sign !== current) return false;
  }
  return true;
}

export function orderDlCorners(points: DlPoint[]): DlPoint[] {
  if (points.length !== 4) return [...points];
  const sums = points.map((p) => p.x + p.y);
  const diffs = points.map((p) => p.y - p.x);
  const tl = points[sums.indexOf(Math.min(...sums))];
  const br = points[sums.indexOf(Math.max(...sums))];
  const tr = points[diffs.indexOf(Math.min(...diffs))];
  const bl = points[diffs.indexOf(Math.max(...diffs))];
  const result = [tl, tr, br, bl];
  if (new Set(result).size !== 4) {
    const byAngle = [...points];
    const cx = byAngle.reduce((s, p) => s + p.x, 0) / 4;
    const cy = byAngle.reduce((s, p) => s + p.y, 0) / 4;
    byAngle.sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
    const start = byAngle.reduce((best, p, idx, arr) => (p.x + p.y < arr[best].x + arr[best].y ? idx : best), 0);
    return [0, 1, 2, 3].map((offset) => byAngle[(start + offset) % 4]);
  }
  return result;
}

function orientCornersLandscape(points: DlPoint[]): DlPoint[] {
  const [tl, tr, br, bl] = orderDlCorners(points);
  const topBottom = (distance(tl, tr) + distance(bl, br)) / 2;
  const leftRight = (distance(tl, bl) + distance(tr, br)) / 2;
  if (topBottom >= leftRight) return [tl, tr, br, bl];
  return [tr, br, bl, tl];
}

export function measureConfirmedGeometry(points: DlPoint[], imageWidth = 1, imageHeight = 1): DlGeometryMeasurements {
  const [tl, tr, br, bl] = orderDlCorners(points);
  const cornerAnglesDeg = {
    TL: angleAt(bl, tl, tr),
    TR: angleAt(tl, tr, br),
    BR: angleAt(tr, br, bl),
    BL: angleAt(br, bl, tl),
  };
  const cornerAngleErrorsDeg = {
    TL: Math.abs(cornerAnglesDeg.TL - 90),
    TR: Math.abs(cornerAnglesDeg.TR - 90),
    BR: Math.abs(cornerAnglesDeg.BR - 90),
    BL: Math.abs(cornerAnglesDeg.BL - 90),
  };

  const topAngleDeg = lineAngleDeg(tl, tr);
  const rightAngleDeg = lineAngleDeg(tr, br);
  const bottomAngleDeg = lineAngleDeg(bl, br);
  const leftAngleDeg = lineAngleDeg(tl, bl);
  const topBottomParallelErrorDeg = axialDifferenceDeg(topAngleDeg, bottomAngleDeg);
  const leftRightParallelErrorDeg = axialDifferenceDeg(leftAngleDeg, rightAngleDeg);

  const topBottomLength = (distance(tl, tr) + distance(bl, br)) / 2;
  const leftRightLength = (distance(tl, bl) + distance(tr, br)) / 2;
  const longEdgesAreTopBottom = topBottomLength >= leftRightLength;
  const longEdgeHorizontalErrorDeg = longEdgesAreTopBottom
    ? Math.max(horizontalErrorDeg(topAngleDeg), horizontalErrorDeg(bottomAngleDeg))
    : Math.max(horizontalErrorDeg(leftAngleDeg), horizontalErrorDeg(rightAngleDeg));
  const shortEdgeVerticalErrorDeg = longEdgesAreTopBottom
    ? Math.max(verticalErrorDeg(leftAngleDeg), verticalErrorDeg(rightAngleDeg))
    : Math.max(verticalErrorDeg(topAngleDeg), verticalErrorDeg(bottomAngleDeg));

  const longLength = Math.max(topBottomLength, leftRightLength);
  const shortLength = Math.min(topBottomLength, leftRightLength) || 1;
  const sourceAspect = longLength / shortLength;
  const imageArea = Math.max(1, imageWidth * imageHeight);

  return {
    cornerAnglesDeg,
    cornerAngleErrorsDeg,
    topAngleDeg,
    rightAngleDeg,
    bottomAngleDeg,
    leftAngleDeg,
    topBottomParallelErrorDeg,
    leftRightParallelErrorDeg,
    longEdgeHorizontalErrorDeg,
    shortEdgeVerticalErrorDeg,
    longEdgesAreTopBottom,
    sourceAspect,
    sourceAreaRatio: polygonArea([tl, tr, br, bl]) / imageArea,
  };
}

export function classifyConfirmedGeometry(measurement: DlGeometryMeasurements): DlGeometryClass {
  const allCorners90 = Object.values(measurement.cornerAngleErrorsDeg)
    .every((error) => error <= RECTANGLE_CORNER_TOLERANCE_DEG);
  const oppositeEdgesParallel =
    measurement.topBottomParallelErrorDeg <= PARALLEL_TOLERANCE_DEG &&
    measurement.leftRightParallelErrorDeg <= PARALLEL_TOLERANCE_DEG;
  if (!allCorners90 || !oppositeEdgesParallel) return "PERSPECTIVE";
  const alreadyStraight =
    measurement.longEdgeHorizontalErrorDeg <= LEVEL_TOLERANCE_DEG &&
    measurement.shortEdgeVerticalErrorDeg <= LEVEL_TOLERANCE_DEG;
  return alreadyStraight ? "FLAT_LEVEL" : "FLAT_ROTATED";
}

function fitLinePca(points: DlPoint[]): FittedLine | null {
  if (points.length < 2) return null;
  let cx = 0;
  let cy = 0;
  for (const p of points) { cx += p.x; cy += p.y; }
  cx /= points.length;
  cy /= points.length;
  let xx = 0;
  let yy = 0;
  let xy = 0;
  for (const p of points) {
    const dx = p.x - cx;
    const dy = p.y - cy;
    xx += dx * dx;
    yy += dy * dy;
    xy += dx * dy;
  }
  xx /= points.length;
  yy /= points.length;
  xy /= points.length;
  const theta = 0.5 * Math.atan2(2 * xy, xx - yy);
  return { vx: Math.cos(theta), vy: Math.sin(theta), x: cx, y: cy };
}

function pointLineDistance(point: DlPoint, line: FittedLine): number {
  return Math.abs(line.vx * (point.y - line.y) - line.vy * (point.x - line.x));
}

function intersectLines(a: FittedLine, b: FittedLine): DlPoint | null {
  const det = a.vx * -b.vy - -b.vx * a.vy;
  if (Math.abs(det) < 1e-8) return null;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const t = (dx * -b.vy - -b.vx * dy) / det;
  const point = { x: a.x + t * a.vx, y: a.y + t * a.vy };
  return Number.isFinite(point.x) && Number.isFinite(point.y) ? point : null;
}

function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function ransacEdgeLine(samples: BoundarySample[], roughLength: number, seed: number): RansacFit | null {
  if (samples.length < EDGE_MIN_INLIERS) return null;
  const random = seededRandom(seed);
  let best: number[] = [];
  for (let iteration = 0; iteration < EDGE_RANSAC_ITERATIONS; iteration += 1) {
    const i = Math.floor(random() * samples.length);
    let j = Math.floor(random() * samples.length);
    if (i === j) j = (j + 1) % samples.length;
    const a = samples[i];
    const b = samples[j];
    const direction = subtract(b, a);
    const length = Math.hypot(direction.x, direction.y);
    if (length < 4) continue;
    const line: FittedLine = { vx: direction.x / length, vy: direction.y / length, x: a.x, y: a.y };
    const inliers: number[] = [];
    for (let k = 0; k < samples.length; k += 1) {
      if (pointLineDistance(samples[k], line) <= EDGE_RANSAC_DISTANCE_PX) inliers.push(k);
    }
    if (inliers.length > best.length) best = inliers;
  }
  const inlierRatio = best.length / samples.length;
  if (best.length < EDGE_MIN_INLIERS || inlierRatio < EDGE_MIN_INLIER_RATIO) return null;
  const inlierPoints = best.map((index) => samples[index]);
  const line = fitLinePca(inlierPoints);
  if (!line) return null;
  let sq = 0;
  let minProjection = Number.POSITIVE_INFINITY;
  let maxProjection = Number.NEGATIVE_INFINITY;
  for (const p of inlierPoints) {
    const d = pointLineDistance(p, line);
    sq += d * d;
    const projection = (p.x - line.x) * line.vx + (p.y - line.y) * line.vy;
    minProjection = Math.min(minProjection, projection);
    maxProjection = Math.max(maxProjection, projection);
  }
  const coverage = (maxProjection - minProjection) / Math.max(1, roughLength);
  if (coverage < EDGE_MIN_COVERAGE) return null;
  return { line, inlierIndices: best, rms: Math.sqrt(sq / inlierPoints.length), coverage };
}

function grayscaleAndGradient(canvas: HTMLCanvasElement): { gradient: Float32Array } {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas unavailable");
  const { width, height } = canvas;
  const data = ctx.getImageData(0, 0, width, height).data;
  const gray = new Float32Array(width * height);
  for (let i = 0, p = 0; p < gray.length; p += 1, i += 4) gray[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  const gradient = new Float32Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = y * width + x;
      const gx = -gray[i - width - 1] + gray[i - width + 1] - 2 * gray[i - 1] + 2 * gray[i + 1] - gray[i + width - 1] + gray[i + width + 1];
      const gy = -gray[i - width - 1] - 2 * gray[i - width] - gray[i - width + 1] + gray[i + width - 1] + 2 * gray[i + width] + gray[i + width + 1];
      gradient[i] = Math.hypot(gx, gy);
    }
  }
  return { gradient };
}

function rgbToHsvOpenCv(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn), delta = max - min;
  let hue = 0;
  if (delta > 1e-6) {
    if (max === rn) hue = 60 * (((gn - bn) / delta) % 6);
    else if (max === gn) hue = 60 * ((bn - rn) / delta + 2);
    else hue = 60 * ((rn - gn) / delta + 4);
  }
  if (hue < 0) hue += 360;
  return { h: hue / 2, s: max <= 1e-6 ? 0 : (delta / max) * 255, v: max * 255 };
}

function horizontalWindowCounts(mask: Uint8Array, width: number, height: number, radius: number, wantMax: boolean): Uint8Array {
  const out = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    let sum = 0;
    for (let x = -radius; x <= radius; x += 1) if (x >= 0 && x < width) sum += mask[y * width + x];
    for (let x = 0; x < width; x += 1) {
      const validSpan = Math.min(width - 1, x + radius) - Math.max(0, x - radius) + 1;
      out[y * width + x] = wantMax ? (sum > 0 ? 1 : 0) : (sum === validSpan ? 1 : 0);
      const removeX = x - radius, addX = x + radius + 1;
      if (removeX >= 0) sum -= mask[y * width + removeX];
      if (addX < width) sum += mask[y * width + addX];
    }
  }
  return out;
}

function verticalWindowCounts(mask: Uint8Array, width: number, height: number, radius: number, wantMax: boolean): Uint8Array {
  const out = new Uint8Array(mask.length);
  for (let x = 0; x < width; x += 1) {
    let sum = 0;
    for (let y = -radius; y <= radius; y += 1) if (y >= 0 && y < height) sum += mask[y * width + x];
    for (let y = 0; y < height; y += 1) {
      const validSpan = Math.min(height - 1, y + radius) - Math.max(0, y - radius) + 1;
      out[y * width + x] = wantMax ? (sum > 0 ? 1 : 0) : (sum === validSpan ? 1 : 0);
      const removeY = y - radius, addY = y + radius + 1;
      if (removeY >= 0) sum -= mask[removeY * width + x];
      if (addY < height) sum += mask[addY * width + x];
    }
  }
  return out;
}

function dilateBinary(mask: Uint8Array, width: number, height: number, radius: number): Uint8Array {
  if (radius <= 0) return new Uint8Array(mask);
  return verticalWindowCounts(horizontalWindowCounts(mask, width, height, radius, true), width, height, radius, true);
}

function erodeBinary(mask: Uint8Array, width: number, height: number, radius: number): Uint8Array {
  if (radius <= 0) return new Uint8Array(mask);
  return verticalWindowCounts(horizontalWindowCounts(mask, width, height, radius, false), width, height, radius, false);
}

function morphologyCloseOpen(mask: Uint8Array, width: number, height: number, openRadius: number, closeRadius: number): Uint8Array {
  const closed = erodeBinary(dilateBinary(mask, width, height, closeRadius), width, height, closeRadius);
  return dilateBinary(erodeBinary(closed, width, height, openRadius), width, height, openRadius);
}

function buildMasks(canvas: HTMLCanvasElement, gradient: Float32Array): Array<{ name: string; mask: Uint8Array; priority: number }> {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas unavailable");
  const { width, height } = canvas;
  const rgba = ctx.getImageData(0, 0, width, height).data;
  const cool = new Uint8Array(width * height), saturated = new Uint8Array(width * height), bright = new Uint8Array(width * height), edge = new Uint8Array(width * height);
  for (let p = 0, i = 0; p < cool.length; p += 1, i += 4) {
    const hsv = rgbToHsvOpenCv(rgba[i], rgba[i + 1], rgba[i + 2]);
    if (hsv.h >= 35 && hsv.h <= 135 && hsv.s >= 22 && hsv.v >= 35) cool[p] = 1;
    if (hsv.s >= 52 && hsv.v >= 35) saturated[p] = 1;
    if (hsv.v >= 110) bright[p] = 1;
    if (gradient[p] >= 95) edge[p] = 1;
  }
  return [
    { name: "cool_security_pattern", mask: morphologyCloseOpen(cool, width, height, 2, 8), priority: 0 },
    { name: "saturation", mask: morphologyCloseOpen(saturated, width, height, 2, 6), priority: 0.35 },
    { name: "edge", mask: morphologyCloseOpen(dilateBinary(edge, width, height, 2), width, height, 1, 5), priority: 0.55 },
    { name: "bright", mask: morphologyCloseOpen(bright, width, height, 2, 6), priority: 0.8 },
  ];
}

type ComponentMoments = { area: number; sumX: number; sumY: number; sumXX: number; sumYY: number; sumXY: number };

function connectedComponentMoments(mask: Uint8Array, width: number, height: number): ComponentMoments[] {
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const minArea = Math.max(80, Math.floor(width * height * 0.004));
  const components: ComponentMoments[] = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let head = 0, tail = 0;
    queue[tail++] = start;
    visited[start] = 1;
    let area = 0, sumX = 0, sumY = 0, sumXX = 0, sumYY = 0, sumXY = 0;
    while (head < tail) {
      const index = queue[head++];
      const y = Math.floor(index / width), x = index - y * width;
      area += 1; sumX += x; sumY += y; sumXX += x * x; sumYY += y * y; sumXY += x * y;
      for (let ny = Math.max(0, y - 1); ny <= Math.min(height - 1, y + 1); ny += 1) {
        for (let nx = Math.max(0, x - 1); nx <= Math.min(width - 1, x + 1); nx += 1) {
          const ni = ny * width + nx;
          if (!visited[ni] && mask[ni]) { visited[ni] = 1; queue[tail++] = ni; }
        }
      }
    }
    if (area >= minArea) components.push({ area, sumX, sumY, sumXX, sumYY, sumXY });
  }
  components.sort((a, b) => b.area - a.area);
  return components.slice(0, 8);
}

function roughBoxFromMoments(component: ComponentMoments): { box: DlPoint[]; ratio: number; boxArea: number } | null {
  const n = component.area;
  if (n <= 0) return null;
  const cx = component.sumX / n, cy = component.sumY / n;
  const xx = component.sumXX / n - cx * cx, yy = component.sumYY / n - cy * cy, xy = component.sumXY / n - cx * cy;
  const theta = 0.5 * Math.atan2(2 * xy, xx - yy);
  const trace = xx + yy;
  const disc = Math.sqrt(Math.max(0, ((xx - yy) / 2) ** 2 + xy * xy));
  const lambda1 = Math.max(1, trace / 2 + disc), lambda2 = Math.max(1, trace / 2 - disc);
  const major = { x: Math.cos(theta), y: Math.sin(theta) }, minor = { x: -major.y, y: major.x };
  const halfMajor = Math.sqrt(3 * lambda1) * 1.12, halfMinor = Math.sqrt(3 * lambda2) * 1.12;
  if (halfMajor < 15 || halfMinor < 10) return null;
  const center = { x: cx, y: cy };
  const p0 = add(add(center, scale(major, -halfMajor)), scale(minor, -halfMinor));
  const p1 = add(add(center, scale(major, halfMajor)), scale(minor, -halfMinor));
  const p2 = add(add(center, scale(major, halfMajor)), scale(minor, halfMinor));
  const p3 = add(add(center, scale(major, -halfMajor)), scale(minor, halfMinor));
  const long = Math.max(halfMajor * 2, halfMinor * 2), short = Math.min(halfMajor * 2, halfMinor * 2);
  return { box: orderDlCorners([p0, p1, p2, p3]), ratio: long / short, boxArea: 4 * halfMajor * halfMinor };
}

function roughCandidates(canvas: HTMLCanvasElement, gradient: Float32Array): RoughCandidate[] {
  const { width, height } = canvas;
  const imageArea = width * height;
  const candidates: RoughCandidate[] = [];
  for (const built of buildMasks(canvas, gradient)) {
    for (const component of connectedComponentMoments(built.mask, width, height)) {
      const rough = roughBoxFromMoments(component);
      if (!rough) continue;
      const areaRatio = rough.boxArea / imageArea;
      if (areaRatio < 0.035 || areaRatio > 0.72) continue;
      if (rough.ratio < 1.05 || rough.ratio > 2.55) continue;
      const density = component.area / Math.max(1, rough.boxArea);
      const ratioError = Math.abs(rough.ratio - ID1_ASPECT) / ID1_ASPECT;
      const score = built.priority + ratioError * 2.8 - Math.min(0.7, density) * 0.65;
      candidates.push({ box: rough.box, score, source: built.name, componentArea: component.area });
    }
  }
  candidates.sort((a, b) => a.score - b.score);
  return candidates.slice(0, 10);
}

function sampleBoundaryPoints(gradient: Float32Array, width: number, height: number, p0: DlPoint, p1: DlPoint, searchPx: number): BoundarySample[] {
  const edge = subtract(p1, p0);
  const edgeLength = Math.hypot(edge.x, edge.y);
  if (edgeLength < 10) return [];
  const tangent = { x: edge.x / edgeLength, y: edge.y / edgeLength };
  const normal = { x: -tangent.y, y: tangent.x };
  const points: BoundarySample[] = [];
  for (let sampleIndex = 0; sampleIndex < EDGE_SAMPLE_COUNT; sampleIndex += 1) {
    const fraction = sampleIndex / Math.max(1, EDGE_SAMPLE_COUNT - 1);
    const t = EDGE_SAMPLE_MARGIN_RATIO + fraction * (1 - 2 * EDGE_SAMPLE_MARGIN_RATIO);
    const base = { x: p0.x + edge.x * t, y: p0.y + edge.y * t };
    let bestScore = Number.NEGATIVE_INFINITY, bestMagnitude = 0;
    let bestPoint: DlPoint | null = null;
    for (let offset = -searchPx; offset <= searchPx; offset += 1) {
      const x = Math.round(base.x + normal.x * offset), y = Math.round(base.y + normal.y * offset);
      if (x < 1 || x >= width - 1 || y < 1 || y >= height - 1) continue;
      const magnitude = gradient[y * width + x];
      const score = magnitude - 0.6 * Math.abs(offset);
      if (score > bestScore) { bestScore = score; bestMagnitude = magnitude; bestPoint = { x, y }; }
    }
    if (bestPoint && bestMagnitude >= EDGE_GRADIENT_MIN) points.push({ ...bestPoint, t });
  }
  return points;
}

function confirmCandidate(candidate: RoughCandidate, gradient: Float32Array, width: number, height: number, seedBase: number): ConfirmedCandidate | null {
  const rough = orderDlCorners(candidate.box);
  const sideLengths = [distance(rough[0], rough[1]), distance(rough[1], rough[2]), distance(rough[2], rough[3]), distance(rough[3], rough[0])];
  const shortSide = Math.min((sideLengths[0] + sideLengths[2]) / 2, (sideLengths[1] + sideLengths[3]) / 2);
  const searchPx = Math.round(clamp(shortSide * EDGE_SEARCH_RATIO_OF_SHORT_SIDE, EDGE_SEARCH_MIN_PX, EDGE_SEARCH_MAX_PX));
  const lines: FittedLine[] = [];
  const evidence = {} as Record<DlEdgeName, DlEdgeEvidence>;
  for (let edgeIndex = 0; edgeIndex < 4; edgeIndex += 1) {
    const p0 = rough[edgeIndex], p1 = rough[(edgeIndex + 1) % 4];
    const samples = sampleBoundaryPoints(gradient, width, height, p0, p1, searchPx);
    const fit = ransacEdgeLine(samples, distance(p0, p1), seedBase + edgeIndex * 977);
    if (!fit) return null;
    const name = EDGE_NAMES[edgeIndex];
    lines.push(fit.line);
    evidence[name] = {
      name,
      samples: samples.length,
      inliers: fit.inlierIndices.length,
      inlierRatio: fit.inlierIndices.length / Math.max(1, samples.length),
      coverage: fit.coverage,
      fitError: fit.rms,
      lineAngleDeg: axialAngleDeg((Math.atan2(fit.line.vy, fit.line.vx) * 180) / Math.PI),
    };
  }
  const rawCorners = [intersectLines(lines[3], lines[0]), intersectLines(lines[0], lines[1]), intersectLines(lines[1], lines[2]), intersectLines(lines[2], lines[3])];
  if (rawCorners.some((corner) => corner == null)) return null;
  const corners = orderDlCorners(rawCorners as DlPoint[]);
  if (!isConvexQuadrilateral(corners)) return null;
  const areaRatio = polygonArea(corners) / Math.max(1, width * height);
  if (areaRatio < SOURCE_MIN_AREA_RATIO || areaRatio > SOURCE_MAX_AREA_RATIO) return null;
  const marginX = width * 0.08, marginY = height * 0.08;
  if (corners.some((p) => p.x < -marginX || p.x > width + marginX || p.y < -marginY || p.y > height + marginY)) return null;
  const measured = measureConfirmedGeometry(corners, width, height);
  if (measured.sourceAspect < SOURCE_MIN_SANITY_ASPECT || measured.sourceAspect > SOURCE_MAX_SANITY_ASPECT) return null;
  const evidenceScore = EDGE_NAMES.reduce((sum, name) => sum + evidence[name].inlierRatio + evidence[name].coverage - evidence[name].fitError * 0.02, 0);
  return { corners, edges: evidence, score: candidate.score - evidenceScore * 0.25 };
}

function scaleCanvas(src: HTMLCanvasElement, maxDimension: number): HTMLCanvasElement {
  const largest = Math.max(src.width, src.height);
  if (largest <= maxDimension) return src;
  const ratio = maxDimension / largest;
  const dst = document.createElement("canvas");
  dst.width = Math.max(1, Math.round(src.width * ratio));
  dst.height = Math.max(1, Math.round(src.height * ratio));
  const ctx = dst.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, 0, 0, dst.width, dst.height);
  return dst;
}

function rotateCanvas(src: HTMLCanvasElement, degrees: number): { canvas: HTMLCanvasElement; transformPoint: (p: DlPoint) => DlPoint } {
  const radians = (degrees * Math.PI) / 180, cos = Math.cos(radians), sin = Math.sin(radians);
  const newWidth = Math.ceil(src.width * Math.abs(cos) + src.height * Math.abs(sin));
  const newHeight = Math.ceil(src.width * Math.abs(sin) + src.height * Math.abs(cos));
  const cx = src.width / 2, cy = src.height / 2, ncx = newWidth / 2, ncy = newHeight / 2;
  const dst = document.createElement("canvas");
  dst.width = newWidth; dst.height = newHeight;
  const ctx = dst.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  ctx.translate(ncx, ncy); ctx.rotate(radians); ctx.drawImage(src, -cx, -cy);
  return {
    canvas: dst,
    transformPoint: (p: DlPoint) => {
      const dx = p.x - cx, dy = p.y - cy;
      return { x: ncx + dx * cos - dy * sin, y: ncy + dx * sin + dy * cos };
    },
  };
}

function cropConfirmedRectangle(src: HTMLCanvasElement, points: DlPoint[], outWidth: number, outHeight: number): HTMLCanvasElement | null {
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  const x0 = Math.max(0, Math.floor(Math.min(...xs))), y0 = Math.max(0, Math.floor(Math.min(...ys)));
  const x1 = Math.min(src.width, Math.ceil(Math.max(...xs))), y1 = Math.min(src.height, Math.ceil(Math.max(...ys)));
  if (x1 - x0 < 20 || y1 - y0 < 20) return null;
  if (Math.min(...xs) < -1 || Math.min(...ys) < -1 || Math.max(...xs) > src.width + 1 || Math.max(...ys) > src.height + 1) return null;
  const dst = document.createElement("canvas");
  dst.width = outWidth; dst.height = outHeight;
  const ctx = dst.getContext("2d");
  if (!ctx) return null;
  ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, x0, y0, x1 - x0, y1 - y0, 0, 0, outWidth, outHeight);
  return dst;
}

function solveLinearSystem(matrix: number[][], vector: number[]): number[] | null {
  const n = vector.length;
  const a = matrix.map((row, i) => [...row, vector[i]]);
  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    if (Math.abs(a[pivot][col]) < 1e-10) return null;
    [a[col], a[pivot]] = [a[pivot], a[col]];
    const pivotValue = a[col][col];
    for (let k = col; k <= n; k += 1) a[col][k] /= pivotValue;
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = a[row][col];
      for (let k = col; k <= n; k += 1) a[row][k] -= factor * a[col][k];
    }
  }
  return a.map((row) => row[n]);
}

function homographyFromDestinationToSource(dst: DlPoint[], src: DlPoint[]): number[] | null {
  const matrix: number[][] = [], vector: number[] = [];
  for (let i = 0; i < 4; i += 1) {
    const x = dst[i].x, y = dst[i].y, u = src[i].x, v = src[i].y;
    matrix.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); vector.push(u);
    matrix.push([0, 0, 0, x, y, 1, -v * x, -v * y]); vector.push(v);
  }
  const h = solveLinearSystem(matrix, vector);
  return h ? [...h, 1] : null;
}

function perspectiveWarp(src: HTMLCanvasElement, corners: DlPoint[], outWidth: number, outHeight: number): HTMLCanvasElement | null {
  const oriented = orientCornersLandscape(corners);
  const dstCorners = [{ x: 0, y: 0 }, { x: outWidth - 1, y: 0 }, { x: outWidth - 1, y: outHeight - 1 }, { x: 0, y: outHeight - 1 }];
  const h = homographyFromDestinationToSource(dstCorners, oriented);
  if (!h || h.some((value) => !Number.isFinite(value))) return null;
  const srcCtx = src.getContext("2d", { willReadFrequently: true });
  if (!srcCtx) return null;
  const srcData = srcCtx.getImageData(0, 0, src.width, src.height);
  const dst = document.createElement("canvas");
  dst.width = outWidth; dst.height = outHeight;
  const dstCtx = dst.getContext("2d");
  if (!dstCtx) return null;
  const dstData = dstCtx.createImageData(outWidth, outHeight);
  for (let y = 0; y < outHeight; y += 1) {
    for (let x = 0; x < outWidth; x += 1) {
      const w = h[6] * x + h[7] * y + h[8];
      if (Math.abs(w) < 1e-10) continue;
      const sx = (h[0] * x + h[1] * y + h[2]) / w, sy = (h[3] * x + h[4] * y + h[5]) / w;
      const x0 = Math.floor(sx), y0 = Math.floor(sy), x1 = x0 + 1, y1 = y0 + 1;
      if (x0 < 0 || y0 < 0 || x1 >= src.width || y1 >= src.height) continue;
      const fx = sx - x0, fy = sy - y0, outIndex = (y * outWidth + x) * 4;
      for (let c = 0; c < 3; c += 1) {
        const i00 = (y0 * src.width + x0) * 4 + c, i10 = (y0 * src.width + x1) * 4 + c, i01 = (y1 * src.width + x0) * 4 + c, i11 = (y1 * src.width + x1) * 4 + c;
        dstData.data[outIndex + c] = Math.round(srcData.data[i00] * (1 - fx) * (1 - fy) + srcData.data[i10] * fx * (1 - fy) + srcData.data[i01] * (1 - fx) * fy + srcData.data[i11] * fx * fy);
      }
      dstData.data[outIndex + 3] = 255;
    }
  }
  dstCtx.putImageData(dstData, 0, 0);
  return dst;
}

function blackBorderFraction(canvas: HTMLCanvasElement): number {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return 1;
  const { width, height } = canvas;
  const data = ctx.getImageData(0, 0, width, height).data;
  const thickness = Math.max(2, Math.round(Math.min(width, height) * 0.015));
  let dark = 0, total = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (x >= thickness && x < width - thickness && y >= thickness && y < height - thickness) continue;
      const i = (y * width + x) * 4;
      total += 1;
      if (data[i] < 8 && data[i + 1] < 8 && data[i + 2] < 8) dark += 1;
    }
  }
  return total ? dark / total : 1;
}

function validateProcessedCanvas(canvas: HTMLCanvasElement, targetWidth: number, targetHeight: number): DlPostValidation {
  const reasons: string[] = [];
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) reasons.push("unexpected_dimensions");
  const aspect = canvas.width / Math.max(1, canvas.height);
  if (Math.abs(aspect - ID1_ASPECT) / ID1_ASPECT > 0.015) reasons.push("output_aspect_not_id1");
  const black = blackBorderFraction(canvas);
  if (black > 0.32) reasons.push("excessive_empty_or_black_border");
  return { valid: reasons.length === 0, reasons, width: canvas.width, height: canvas.height, outputAspect: aspect, blackBorderFraction: black };
}

function canvasToJpegBlob(canvas: HTMLCanvasElement, quality = 0.94): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Could not encode processed Driver Licence image")), "image/jpeg", quality));
}

async function readExifOrientation(file: File): Promise<number> {
  const buffer = await file.arrayBuffer();
  const view = new DataView(buffer);
  if (view.byteLength < 4 || view.getUint16(0, false) !== 0xffd8) return 1;
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    const marker = view.getUint16(offset, false); offset += 2;
    if (marker === 0xffda || marker === 0xffd9) break;
    if (offset + 2 > view.byteLength) break;
    const length = view.getUint16(offset, false);
    if (length < 2 || offset + length > view.byteLength) break;
    if (marker === 0xffe1 && length >= 10) {
      const tiffOffset = offset + 2;
      if (view.getUint32(tiffOffset, false) !== 0x45786966) return 1;
      const byteOrderOffset = tiffOffset + 6;
      const littleEndian = view.getUint16(byteOrderOffset, false) === 0x4949;
      const ifdOffset = view.getUint32(byteOrderOffset + 4, littleEndian);
      let dirStart = byteOrderOffset + ifdOffset;
      if (dirStart + 2 > view.byteLength) return 1;
      const entries = view.getUint16(dirStart, littleEndian); dirStart += 2;
      for (let i = 0; i < entries; i += 1) {
        const entryOffset = dirStart + i * 12;
        if (entryOffset + 12 > view.byteLength) break;
        if (view.getUint16(entryOffset, littleEndian) === 0x0112) {
          const orientation = view.getUint16(entryOffset + 8, littleEndian);
          return orientation >= 1 && orientation <= 8 ? orientation : 1;
        }
      }
      return 1;
    }
    offset += length;
  }
  return 1;
}

function drawImageWithExifOrientation(ctx: CanvasRenderingContext2D, image: HTMLImageElement, orientation: number): void {
  const width = image.naturalWidth, height = image.naturalHeight;
  switch (orientation) {
    case 2: ctx.translate(width, 0); ctx.scale(-1, 1); break;
    case 3: ctx.translate(width, height); ctx.rotate(Math.PI); break;
    case 4: ctx.translate(0, height); ctx.scale(1, -1); break;
    case 5: ctx.rotate(Math.PI / 2); ctx.scale(1, -1); break;
    case 6: ctx.translate(height, 0); ctx.rotate(Math.PI / 2); break;
    case 7: ctx.translate(height, 0); ctx.rotate(Math.PI / 2); ctx.scale(-1, 1); break;
    case 8: ctx.translate(0, width); ctx.rotate(-Math.PI / 2); break;
    default: break;
  }
  ctx.drawImage(image, 0, 0);
}

async function loadExifOrientedCanvas(file: File): Promise<HTMLCanvasElement> {
  const orientation = await readExifOrientation(file);
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Could not decode Driver Licence image"));
      img.src = url;
    });
    const rotate90 = orientation >= 5 && orientation <= 8;
    const canvas = document.createElement("canvas");
    canvas.width = rotate90 ? image.naturalHeight : image.naturalWidth;
    canvas.height = rotate90 ? image.naturalWidth : image.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas unavailable");
    drawImageWithExifOrientation(ctx, image, orientation);
    return canvas;
  } finally { URL.revokeObjectURL(url); }
}

function rotateCanvasQuarterTurns(src: HTMLCanvasElement, rotation: 0 | 90 | 180 | 270): HTMLCanvasElement {
  if (rotation === 0) return src;
  const dst = document.createElement("canvas");
  const quarter = rotation === 90 || rotation === 270;
  dst.width = quarter ? src.height : src.width;
  dst.height = quarter ? src.width : src.height;
  const ctx = dst.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  if (rotation === 90) { ctx.translate(dst.width, 0); ctx.rotate(Math.PI / 2); }
  else if (rotation === 180) { ctx.translate(dst.width, dst.height); ctx.rotate(Math.PI); }
  else { ctx.translate(0, dst.height); ctx.rotate(-Math.PI / 2); }
  ctx.drawImage(src, 0, 0);
  return dst;
}

async function resolveSemanticOrientation(resolver: SemanticOrientationResolver | undefined, canvas: HTMLCanvasElement): Promise<SemanticOrientationResult> {
  if (!resolver) return { rotation: "unknown", confidence: 0, engine: "none" };
  try {
    const result = await resolver(canvas);
    return { rotation: result.rotation, confidence: clamp(result.confidence, 0, 1), engine: result.engine };
  } catch {
    return { rotation: "unknown", confidence: 0, engine: "error" };
  }
}

function mapAnalysisCornersToSource(points: DlPoint[], analysis: HTMLCanvasElement, source: HTMLCanvasElement): DlPoint[] {
  const sx = source.width / analysis.width, sy = source.height / analysis.height;
  return points.map((p) => ({ x: p.x * sx, y: p.y * sy }));
}

function chooseRotationAngle(measurement: DlGeometryMeasurements): number {
  const longAngle = measurement.longEdgesAreTopBottom
    ? meanAxialAngleDeg(measurement.topAngleDeg, measurement.bottomAngleDeg)
    : meanAxialAngleDeg(measurement.leftAngleDeg, measurement.rightAngleDeg);
  return -longAngle;
}

function failResult(analysis: HTMLCanvasElement, orientationPreflight: SemanticOrientationResult, reason: string, suggestedCorners?: DlPoint[]): DlPreprocessResult {
  return {
    ok: false,
    processedBlob: null,
    processedPreviewCanvas: null,
    suggestedCorners,
    metadata: {
      version: VERSION,
      analysisWidth: analysis.width,
      analysisHeight: analysis.height,
      orientationPreflight,
      orientationPostflight: { rotation: "unknown", confidence: 0, engine: "none" },
      classification: "UNCONFIRMED",
      correction: "NONE",
      failureReason: reason,
    },
  };
}

export async function preprocessDriverLicense(file: File, options: DlPreprocessOptions = {}): Promise<DlPreprocessResult> {
  const targetWidth = options.targetWidth ?? DL_TARGET_WIDTH;
  const targetHeight = options.targetHeight ?? Math.round(targetWidth / ID1_ASPECT);
  const sourceExifOriented = await loadExifOrientedCanvas(file);
  const preflight = await resolveSemanticOrientation(options.semanticOrientationResolver, sourceExifOriented);
  const preflightRotation = preflight.confidence >= SEMANTIC_ORIENTATION_MIN_CONFIDENCE && preflight.rotation !== "unknown" ? preflight.rotation : 0;
  const workingSource = rotateCanvasQuarterTurns(sourceExifOriented, preflightRotation as 0 | 90 | 180 | 270);
  const analysis = scaleCanvas(workingSource, options.analysisMaxDimension ?? ANALYSIS_MAX_DIMENSION);
  const { gradient } = grayscaleAndGradient(analysis);
  const candidates = roughCandidates(analysis, gradient);
  let best: ConfirmedCandidate | null = null;
  for (let i = 0; i < candidates.length; i += 1) {
    const confirmed = confirmCandidate(candidates[i], gradient, analysis.width, analysis.height, 9001 + i * 7919);
    if (confirmed && (!best || confirmed.score < best.score)) best = confirmed;
  }
  if (!best) return failResult(analysis, preflight, "four_independent_edges_not_confirmed");
  const sourceCorners = mapAnalysisCornersToSource(best.corners, analysis, workingSource);
  if (!isConvexQuadrilateral(orderDlCorners(sourceCorners))) return failResult(analysis, preflight, "confirmed_intersections_not_convex", sourceCorners);
  const measurement = measureConfirmedGeometry(sourceCorners, workingSource.width, workingSource.height);
  const classification = classifyConfirmedGeometry(measurement);
  let processed: HTMLCanvasElement | null = null;
  let correction: DlCorrection = "NONE";
  let rotationAngleDeg: number | undefined;
  if (classification === "FLAT_LEVEL") {
    correction = "NONE_CROP";
    processed = cropConfirmedRectangle(workingSource, orientCornersLandscape(sourceCorners), targetWidth, targetHeight);
  } else if (classification === "FLAT_ROTATED") {
    correction = "ROTATE";
    rotationAngleDeg = chooseRotationAngle(measurement);
    const rotated = rotateCanvas(workingSource, rotationAngleDeg);
    const rotatedCorners = sourceCorners.map(rotated.transformPoint);
    processed = cropConfirmedRectangle(rotated.canvas, orientCornersLandscape(rotatedCorners), targetWidth, targetHeight);
  } else if (classification === "PERSPECTIVE") {
    correction = "PERSPECTIVE_WARP";
    processed = perspectiveWarp(workingSource, sourceCorners, targetWidth, targetHeight);
  }
  if (!processed) {
    const failed = failResult(analysis, preflight, "transform_failed", sourceCorners);
    failed.metadata = {
      version: VERSION,
      analysisWidth: analysis.width,
      analysisHeight: analysis.height,
      orientationPreflight: preflight,
      orientationPostflight: { rotation: "unknown", confidence: 0, engine: "none" },
      edges: best.edges,
      corners: { TL: sourceCorners[0], TR: sourceCorners[1], BR: sourceCorners[2], BL: sourceCorners[3] },
      measurements: measurement,
      classification,
      correction,
      rotationAngleDeg,
      failureReason: "transform_failed",
    };
    return failed;
  }
  const validation = validateProcessedCanvas(processed, targetWidth, targetHeight);
  if (!validation.valid) {
    const failed = failResult(analysis, preflight, "post_transform_validation_failed", sourceCorners);
    failed.metadata = {
      version: VERSION,
      analysisWidth: analysis.width,
      analysisHeight: analysis.height,
      orientationPreflight: preflight,
      orientationPostflight: { rotation: "unknown", confidence: 0, engine: "none" },
      edges: best.edges,
      corners: { TL: sourceCorners[0], TR: sourceCorners[1], BR: sourceCorners[2], BL: sourceCorners[3] },
      measurements: measurement,
      classification,
      correction,
      rotationAngleDeg,
      postValidation: validation,
      failureReason: "post_transform_validation_failed",
    };
    return failed;
  }
  const postflight = await resolveSemanticOrientation(options.semanticOrientationResolver, processed);
  if (postflight.confidence >= SEMANTIC_ORIENTATION_MIN_CONFIDENCE && postflight.rotation === 180) processed = rotateCanvasQuarterTurns(processed, 180);
  const blob = await canvasToJpegBlob(processed);
  return {
    ok: true,
    processedBlob: blob,
    processedPreviewCanvas: processed,
    suggestedCorners: sourceCorners,
    metadata: {
      version: VERSION,
      analysisWidth: analysis.width,
      analysisHeight: analysis.height,
      orientationPreflight: preflight,
      orientationPostflight: postflight,
      roughCandidateScore: best.score,
      edges: best.edges,
      corners: { TL: sourceCorners[0], TR: sourceCorners[1], BR: sourceCorners[2], BL: sourceCorners[3] },
      measurements: measurement,
      classification,
      correction,
      rotationAngleDeg,
      postValidation: validation,
    },
  };
}
