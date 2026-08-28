export type DlPoint = { x: number; y: number };

export type DlGeometryClassification =
  | "FLAT_LEVEL"
  | "FLAT_ROTATED"
  | "PERSPECTIVE"
  | "UNCONFIRMED";

export type DlCorrection = "CROP" | "ROTATE" | "PERSPECTIVE_WARP" | "NONE";

export type DlEdgeName = "top" | "right" | "bottom" | "left";

export type DlLine = {
  vx: number;
  vy: number;
  x: number;
  y: number;
};

export type DlEdgeDiagnostics = {
  sampleCount: number;
  inlierCount: number;
  inlierRatio: number;
  coverage: number;
  lineAngleDeg: number | null;
  rmsFitError: number | null;
  confirmed: boolean;
};

export type DlGeometryMeasurements = {
  cornerAnglesDeg: { TL: number; TR: number; BR: number; BL: number };
  edgeAnglesDeg: { top: number; right: number; bottom: number; left: number };
  parallelErrorDeg: { topBottom: number; leftRight: number };
  levelErrorDeg: { top: number; bottom: number; left: number; right: number };
  sourceAspect: number;
  sourceAreaPercent: number;
  convex: boolean;
};

export type DlPreprocessMetadata = {
  version: "browser-four-edge-v1";
  status: "PROCESSED" | "AUTOMATIC_GEOMETRY_UNCONFIRMED" | "AUTOMATIC_GEOMETRY_FAILED_VALIDATION";
  semanticOrientation: "unknown";
  analysisWidth: number;
  analysisHeight: number;
  classification: DlGeometryClassification;
  correction: DlCorrection;
  rotationAngleDeg: number | null;
  cornersConfirmed: boolean;
  corners: { TL: DlPoint; TR: DlPoint; BR: DlPoint; BL: DlPoint } | null;
  edges: Record<DlEdgeName, DlEdgeDiagnostics>;
  measurements: DlGeometryMeasurements | null;
  postValidation: {
    passed: boolean;
    reason: string | null;
    finalWidth: number | null;
    finalHeight: number | null;
  };
};

export type DlPreprocessResult = {
  processedBlob: Blob | null;
  metadata: DlPreprocessMetadata;
  suggestedCorners: DlPoint[] | null;
};

export const DL_GEOMETRY_CONSTANTS = {
  TARGET_WIDTH: 1000,
  TARGET_HEIGHT: 631,
  ID1_ASPECT: 85.6 / 53.98,
  ANALYSIS_MAX_SIDE: 1600,
  CORNER_IGNORE_RATIO: 0.16,
  RECTANGLE_CORNER_TOLERANCE_DEG: 4,
  PARALLEL_TOLERANCE_DEG: 3,
  LEVEL_TOLERANCE_DEG: 2,
  EDGE_SAMPLE_COUNT: 180,
  MIN_EDGE_INLIERS: 36,
  MIN_EDGE_INLIER_RATIO: 0.28,
  MIN_EDGE_COVERAGE: 0.55,
  RANSAC_ITERATIONS: 450,
  BASE_RANSAC_DISTANCE_PX: 4.5,
  BASE_BOUNDARY_GRADIENT: 25,
  MIN_CARD_AREA_RATIO: 0.06,
  MAX_CARD_AREA_RATIO: 0.78,
  MAX_BLACK_EDGE_RATIO: 0.08,
} as const;

const EMPTY_EDGE: DlEdgeDiagnostics = {
  sampleCount: 0,
  inlierCount: 0,
  inlierRatio: 0,
  coverage: 0,
  lineAngleDeg: null,
  rmsFitError: null,
  confirmed: false,
};

type RoughCandidate = {
  box: DlPoint[];
  score: number;
  areaRatio: number;
  roughAspect: number;
};

type EdgeFit = {
  line: DlLine | null;
  diagnostics: DlEdgeDiagnostics;
};

type ConfirmedGeometry = {
  corners: DlPoint[];
  lines: Record<DlEdgeName, DlLine>;
  diagnostics: Record<DlEdgeName, DlEdgeDiagnostics>;
};

type ClassificationResult = {
  classification: DlGeometryClassification;
  correction: DlCorrection;
  rotationAngleDeg: number | null;
  measurements: DlGeometryMeasurements;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function radToDeg(value: number): number {
  return (value * 180) / Math.PI;
}

function degToRad(value: number): number {
  return (value * Math.PI) / 180;
}

function distance(a: DlPoint, b: DlPoint): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function cross(a: DlPoint, b: DlPoint, c: DlPoint): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function polygonArea(points: DlPoint[]): number {
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a.x * b.y - b.x * a.y;
  }
  return area / 2;
}

function isConvexQuad(points: DlPoint[]): boolean {
  if (points.length !== 4) return false;
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % 4];
    const c = points[(i + 2) % 4];
    const value = cross(a, b, c);
    if (Math.abs(value) < 1e-6) return false;
    const current = Math.sign(value);
    if (sign === 0) sign = current;
    if (current !== sign) return false;
  }
  return true;
}

function orderQuad(points: DlPoint[]): DlPoint[] {
  if (points.length !== 4) return points;
  const center = points.reduce(
    (acc, p) => ({ x: acc.x + p.x / 4, y: acc.y + p.y / 4 }),
    { x: 0, y: 0 },
  );
  let ordered = [...points].sort(
    (a, b) => Math.atan2(a.y - center.y, a.x - center.x) - Math.atan2(b.y - center.y, b.x - center.x),
  );
  if (polygonArea(ordered) < 0) ordered = ordered.reverse();

  let start = 0;
  let best = Number.POSITIVE_INFINITY;
  ordered.forEach((p, index) => {
    const score = p.x + p.y;
    if (score < best) {
      best = score;
      start = index;
    }
  });
  ordered = [...ordered.slice(start), ...ordered.slice(0, start)];

  const first = distance(ordered[0], ordered[1]);
  const second = distance(ordered[1], ordered[2]);
  if (first < second) {
    ordered = [ordered[1], ordered[2], ordered[3], ordered[0]];
  }
  return ordered;
}

function axialAngleDeg(line: DlLine): number {
  let angle = radToDeg(Math.atan2(line.vy, line.vx));
  while (angle >= 90) angle -= 180;
  while (angle < -90) angle += 180;
  return angle;
}

function axialDifferenceDeg(a: number, b: number): number {
  let diff = Math.abs(a - b) % 180;
  if (diff > 90) diff = 180 - diff;
  return diff;
}

function horizontalErrorDeg(angle: number): number {
  return Math.abs(angle);
}

function verticalErrorDeg(angle: number): number {
  return Math.abs(90 - Math.abs(angle));
}

function meanAxialAngleDeg(a: number, b: number): number {
  const ar = degToRad(a * 2);
  const br = degToRad(b * 2);
  const x = Math.cos(ar) + Math.cos(br);
  const y = Math.sin(ar) + Math.sin(br);
  let mean = radToDeg(Math.atan2(y, x)) / 2;
  while (mean >= 90) mean -= 180;
  while (mean < -90) mean += 180;
  return mean;
}

function cornerAngleDeg(prev: DlPoint, point: DlPoint, next: DlPoint): number {
  const a = { x: prev.x - point.x, y: prev.y - point.y };
  const b = { x: next.x - point.x, y: next.y - point.y };
  const denom = Math.hypot(a.x, a.y) * Math.hypot(b.x, b.y);
  if (denom < 1e-9) return 0;
  const cosine = clamp((a.x * b.x + a.y * b.y) / denom, -1, 1);
  return radToDeg(Math.acos(cosine));
}

function lineFromTwoPoints(a: DlPoint, b: DlPoint): DlLine | null {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = Math.hypot(dx, dy);
  if (length < 1e-6) return null;
  return { vx: dx / length, vy: dy / length, x: a.x, y: a.y };
}

function intersectLines(a: DlLine, b: DlLine): DlPoint | null {
  const det = a.vx * -b.vy - -b.vx * a.vy;
  if (Math.abs(det) < 1e-8) return null;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const t = (dx * -b.vy - -b.vx * dy) / det;
  const x = a.x + t * a.vx;
  const y = a.y + t * a.vy;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function fitPcaLine(points: DlPoint[]): DlLine | null {
  if (points.length < 2) return null;
  let mx = 0;
  let my = 0;
  points.forEach((p) => {
    mx += p.x;
    my += p.y;
  });
  mx /= points.length;
  my /= points.length;

  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  points.forEach((p) => {
    const dx = p.x - mx;
    const dy = p.y - my;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  });

  const theta = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  return { vx: Math.cos(theta), vy: Math.sin(theta), x: mx, y: my };
}

function pointLineDistance(point: DlPoint, line: DlLine): number {
  const dx = point.x - line.x;
  const dy = point.y - line.y;
  return Math.abs(line.vx * dy - line.vy * dx);
}

function projectAlongLine(point: DlPoint, line: DlLine): number {
  return (point.x - line.x) * line.vx + (point.y - line.y) * line.vy;
}

function seededRandom(seedState: { value: number }): number {
  seedState.value = (1664525 * seedState.value + 1013904223) >>> 0;
  return seedState.value / 0x100000000;
}

function ransacLine(points: DlPoint[], expectedLength: number, analysisMaxSide: number): EdgeFit {
  const sampleCount = points.length;
  if (sampleCount < 2) return { line: null, diagnostics: { ...EMPTY_EDGE, sampleCount } };

  const distanceThreshold = Math.max(2.5, (analysisMaxSide / 1600) * DL_GEOMETRY_CONSTANTS.BASE_RANSAC_DISTANCE_PX);
  const seed = { value: 0x5f3759df };
  let bestIndices: number[] = [];

  for (let iteration = 0; iteration < DL_GEOMETRY_CONSTANTS.RANSAC_ITERATIONS; iteration += 1) {
    const i = Math.floor(seededRandom(seed) * points.length);
    let j = Math.floor(seededRandom(seed) * points.length);
    if (j === i) j = (j + 1) % points.length;
    const candidate = lineFromTwoPoints(points[i], points[j]);
    if (!candidate) continue;
    const inliers: number[] = [];
    points.forEach((point, index) => {
      if (pointLineDistance(point, candidate) <= distanceThreshold) inliers.push(index);
    });
    if (inliers.length > bestIndices.length) bestIndices = inliers;
  }

  const inlierPoints = bestIndices.map((index) => points[index]);
  const line = fitPcaLine(inlierPoints);
  if (!line) {
    return {
      line: null,
      diagnostics: {
        ...EMPTY_EDGE,
        sampleCount,
        inlierCount: bestIndices.length,
        inlierRatio: bestIndices.length / Math.max(1, sampleCount),
      },
    };
  }

  const projections = inlierPoints.map((point) => projectAlongLine(point, line));
  const minProjection = Math.min(...projections);
  const maxProjection = Math.max(...projections);
  const coverage = expectedLength > 0 ? (maxProjection - minProjection) / expectedLength : 0;
  const rms = Math.sqrt(
    inlierPoints.reduce((sum, point) => {
      const error = pointLineDistance(point, line);
      return sum + error * error;
    }, 0) / Math.max(1, inlierPoints.length),
  );
  const inlierRatio = inlierPoints.length / Math.max(1, sampleCount);
  const requiredInliers = Math.max(
    DL_GEOMETRY_CONSTANTS.MIN_EDGE_INLIERS,
    Math.ceil(sampleCount * DL_GEOMETRY_CONSTANTS.MIN_EDGE_INLIER_RATIO),
  );
  const confirmed =
    inlierPoints.length >= requiredInliers &&
    inlierRatio >= DL_GEOMETRY_CONSTANTS.MIN_EDGE_INLIER_RATIO &&
    coverage >= DL_GEOMETRY_CONSTANTS.MIN_EDGE_COVERAGE;

  return {
    line,
    diagnostics: {
      sampleCount,
      inlierCount: inlierPoints.length,
      inlierRatio,
      coverage,
      lineAngleDeg: axialAngleDeg(line),
      rmsFitError: rms,
      confirmed,
    },
  };
}

function grayscaleAndGradient(image: ImageData): { gray: Uint8Array; gradient: Float32Array } {
  const { width, height, data } = image;
  const gray = new Uint8Array(width * height);
  for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
    gray[p] = Math.round(data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114);
  }

  const gradient = new Float32Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const idx = y * width + x;
      const a = gray[(y - 1) * width + (x - 1)];
      const b = gray[(y - 1) * width + x];
      const c = gray[(y - 1) * width + (x + 1)];
      const d = gray[y * width + (x - 1)];
      const f = gray[y * width + (x + 1)];
      const g = gray[(y + 1) * width + (x - 1)];
      const h = gray[(y + 1) * width + x];
      const k = gray[(y + 1) * width + (x + 1)];
      const gx = -a - 2 * d - g + c + 2 * f + k;
      const gy = -a - 2 * b - c + g + 2 * h + k;
      gradient[idx] = Math.hypot(gx, gy);
    }
  }
  return { gray, gradient };
}

function rgbToHsv255(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rf = r / 255;
  const gf = g / 255;
  const bf = b / 255;
  const max = Math.max(rf, gf, bf);
  const min = Math.min(rf, gf, bf);
  const delta = max - min;
  let hue = 0;
  if (delta > 1e-6) {
    if (max === rf) hue = 60 * (((gf - bf) / delta) % 6);
    else if (max === gf) hue = 60 * ((bf - rf) / delta + 2);
    else hue = 60 * ((rf - gf) / delta + 4);
  }
  if (hue < 0) hue += 360;
  return {
    h: hue,
    s: max <= 1e-6 ? 0 : (delta / max) * 255,
    v: max * 255,
  };
}

function otsuThreshold(values: Uint8Array): number {
  const histogram = new Uint32Array(256);
  values.forEach((value) => { histogram[value] += 1; });
  const total = values.length;
  let sum = 0;
  for (let i = 0; i < 256; i += 1) sum += i * histogram[i];
  let sumBackground = 0;
  let weightBackground = 0;
  let maxVariance = -1;
  let threshold = 64;
  for (let i = 0; i < 256; i += 1) {
    weightBackground += histogram[i];
    if (weightBackground === 0) continue;
    const weightForeground = total - weightBackground;
    if (weightForeground === 0) break;
    sumBackground += i * histogram[i];
    const meanBackground = sumBackground / weightBackground;
    const meanForeground = (sum - sumBackground) / weightForeground;
    const variance = weightBackground * weightForeground * (meanBackground - meanForeground) ** 2;
    if (variance > maxVariance) {
      maxVariance = variance;
      threshold = i;
    }
  }
  return threshold;
}

function buildCandidateMasks(image: ImageData, gradient: Float32Array): Uint8Array[] {
  const { width, height, data } = image;
  const pixelCount = width * height;
  const cool = new Uint8Array(pixelCount);
  const saturationValues = new Uint8Array(pixelCount);
  const bright = new Uint8Array(pixelCount);
  const edge = new Uint8Array(pixelCount);

  for (let p = 0, i = 0; p < pixelCount; p += 1, i += 4) {
    const hsv = rgbToHsv255(data[i], data[i + 1], data[i + 2]);
    saturationValues[p] = Math.round(hsv.s);
    if (hsv.h >= 70 && hsv.h <= 250 && hsv.s >= 22 && hsv.v >= 35) cool[p] = 1;
    if (hsv.v >= 95) bright[p] = 1;
    if (gradient[p] >= 70) edge[p] = 1;
  }

  const satThreshold = otsuThreshold(saturationValues);
  const saturation = new Uint8Array(pixelCount);
  for (let p = 0; p < pixelCount; p += 1) {
    if (saturationValues[p] >= satThreshold) saturation[p] = 1;
  }

  return [cool, saturation, bright, edge];
}

type Component = { area: number; points: DlPoint[] };

function connectedComponents(mask: Uint8Array, width: number, height: number): Component[] {
  const visited = new Uint8Array(mask.length);
  const minArea = width * height * 0.0025;
  const components: Component[] = [];
  const queueX = new Int32Array(mask.length);
  const queueY = new Int32Array(mask.length);

  for (let y0 = 0; y0 < height; y0 += 1) {
    for (let x0 = 0; x0 < width; x0 += 1) {
      const start = y0 * width + x0;
      if (!mask[start] || visited[start]) continue;
      let head = 0;
      let tail = 0;
      queueX[tail] = x0;
      queueY[tail] = y0;
      tail += 1;
      visited[start] = 1;
      let area = 0;
      const points: DlPoint[] = [];

      while (head < tail) {
        const x = queueX[head];
        const y = queueY[head];
        head += 1;
        area += 1;
        if (points.length < 6000 && (area % 3 === 0 || area < 200)) points.push({ x, y });

        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            if (dx === 0 && dy === 0) continue;
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
            const ni = ny * width + nx;
            if (!mask[ni] || visited[ni]) continue;
            visited[ni] = 1;
            queueX[tail] = nx;
            queueY[tail] = ny;
            tail += 1;
          }
        }
      }

      if (area >= minArea && points.length >= 8) components.push({ area, points });
    }
  }

  return components.sort((a, b) => b.area - a.area).slice(0, 6);
}

function convexHull(points: DlPoint[]): DlPoint[] {
  const sorted = [...points].sort((a, b) => (a.x - b.x) || (a.y - b.y));
  if (sorted.length <= 2) return sorted;
  const lower: DlPoint[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  }
  const upper: DlPoint[] = [];
  for (let i = sorted.length - 1; i >= 0; i -= 1) {
    const point = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function minimumAreaRectangle(points: DlPoint[]): { box: DlPoint[]; width: number; height: number; area: number } | null {
  const hull = convexHull(points);
  if (hull.length < 3) return null;
  let best: { box: DlPoint[]; width: number; height: number; area: number } | null = null;

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
    hull.forEach((point) => {
      const x = point.x * cos - point.y * sin;
      const y = point.x * sin + point.y * cos;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    });
    const width = maxX - minX;
    const height = maxY - minY;
    const area = width * height;
    if (!best || area < best.area) {
      const cornersRotated = [
        { x: minX, y: minY },
        { x: maxX, y: minY },
        { x: maxX, y: maxY },
        { x: minX, y: maxY },
      ];
      const rcos = Math.cos(angle);
      const rsin = Math.sin(angle);
      const box = cornersRotated.map((point) => ({
        x: point.x * rcos - point.y * rsin,
        y: point.x * rsin + point.y * rcos,
      }));
      best = { box: orderQuad(box), width, height, area };
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
  const masks = buildCandidateMasks(image, gradient);
  const all: RoughCandidate[] = [];
  masks.forEach((mask, maskIndex) => {
    const components = connectedComponents(mask, image.width, image.height);
    for (const group of combinations(components, 4)) {
      const points = group.flatMap((component) => component.points);
      if (points.length < 20) continue;
      const rectangle = minimumAreaRectangle(points);
      if (!rectangle) continue;
      const longSide = Math.max(rectangle.width, rectangle.height);
      const shortSide = Math.min(rectangle.width, rectangle.height);
      if (shortSide < 20) continue;
      const aspect = longSide / shortSide;
      const areaRatio = rectangle.area / (image.width * image.height);
      if (areaRatio < DL_GEOMETRY_CONSTANTS.MIN_CARD_AREA_RATIO || areaRatio > DL_GEOMETRY_CONSTANTS.MAX_CARD_AREA_RATIO) continue;
      if (aspect < 1.15 || aspect > 2.3) continue;
      const aspectError = Math.abs(aspect - DL_GEOMETRY_CONSTANTS.ID1_ASPECT) / DL_GEOMETRY_CONSTANTS.ID1_ASPECT;
      const maskPenalty = maskIndex * 0.03;
      all.push({ box: orderQuad(rectangle.box), score: aspectError + maskPenalty, areaRatio, roughAspect: aspect });
    }
  });
  return all.sort((a, b) => a.score - b.score).slice(0, 12);
}

function sampleBoundaryPoints(
  gradient: Float32Array,
  width: number,
  height: number,
  p0: DlPoint,
  p1: DlPoint,
  searchPx: number,
): DlPoint[] {
  const dx = p1.x - p0.x;
  const dy = p1.y - p0.y;
  const length = Math.hypot(dx, dy);
  if (length < 1) return [];
  const tx = dx / length;
  const ty = dy / length;
  const nx = -ty;
  const ny = tx;
  const points: DlPoint[] = [];

  for (let sample = 0; sample < DL_GEOMETRY_CONSTANTS.EDGE_SAMPLE_COUNT; sample += 1) {
    const t = 0.08 + (0.84 * sample) / Math.max(1, DL_GEOMETRY_CONSTANTS.EDGE_SAMPLE_COUNT - 1);
    const bx = p0.x + t * dx;
    const by = p0.y + t * dy;
    let bestScore = -Infinity;
    let bestGradient = 0;
    let bestPoint: DlPoint | null = null;

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

    if (bestPoint && bestGradient >= DL_GEOMETRY_CONSTANTS.BASE_BOUNDARY_GRADIENT) points.push(bestPoint);
  }
  return points;
}

function confirmFourEdges(candidate: RoughCandidate, gradient: Float32Array, width: number, height: number): ConfirmedGeometry | null {
  const box = orderQuad(candidate.box);
  const expected = [
    distance(box[0], box[1]),
    distance(box[1], box[2]),
    distance(box[2], box[3]),
    distance(box[3], box[0]),
  ];
  const shortSide = Math.min(expected[0], expected[1], expected[2], expected[3]);
  const searchPx = Math.round(clamp(shortSide * 0.12, 24, 120));
  const names: DlEdgeName[] = ["top", "right", "bottom", "left"];
  const lines = {} as Record<DlEdgeName, DlLine>;
  const diagnostics = {} as Record<DlEdgeName, DlEdgeDiagnostics>;

  for (let i = 0; i < 4; i += 1) {
    const points = sampleBoundaryPoints(gradient, width, height, box[i], box[(i + 1) % 4], searchPx);
    const fit = ransacLine(points, expected[i] * 0.84, Math.max(width, height));
    diagnostics[names[i]] = fit.diagnostics;
    if (!fit.line || !fit.diagnostics.confirmed) return null;
    lines[names[i]] = fit.line;
  }

  const TL = intersectLines(lines.left, lines.top);
  const TR = intersectLines(lines.top, lines.right);
  const BR = intersectLines(lines.right, lines.bottom);
  const BL = intersectLines(lines.bottom, lines.left);
  if (!TL || !TR || !BR || !BL) return null;
  const corners = orderQuad([TL, TR, BR, BL]);
  if (!isConvexQuad(corners)) return null;

  const margin = 5;
  if (corners.some((point) => point.x < -margin || point.y < -margin || point.x > width + margin || point.y > height + margin)) return null;
  const areaRatio = Math.abs(polygonArea(corners)) / (width * height);
  if (areaRatio < DL_GEOMETRY_CONSTANTS.MIN_CARD_AREA_RATIO || areaRatio > DL_GEOMETRY_CONSTANTS.MAX_CARD_AREA_RATIO) return null;

  const orderedLines = {
    top: lineFromTwoPoints(corners[0], corners[1])!,
    right: lineFromTwoPoints(corners[1], corners[2])!,
    bottom: lineFromTwoPoints(corners[3], corners[2])!,
    left: lineFromTwoPoints(corners[0], corners[3])!,
  };
  return { corners, lines: orderedLines, diagnostics };
}

export function classifyDriverLicenseGeometry(
  cornersInput: DlPoint[],
  linesInput?: Partial<Record<DlEdgeName, DlLine>>,
  imageWidth = 1,
  imageHeight = 1,
): ClassificationResult {
  if (cornersInput.length !== 4) {
    throw new Error("Driver Licence geometry requires exactly four corners");
  }
  const corners = orderQuad(cornersInput);
  const [TL, TR, BR, BL] = corners;
  const lines: Record<DlEdgeName, DlLine> = {
    top: linesInput?.top ?? lineFromTwoPoints(TL, TR)!,
    right: linesInput?.right ?? lineFromTwoPoints(TR, BR)!,
    bottom: linesInput?.bottom ?? lineFromTwoPoints(BL, BR)!,
    left: linesInput?.left ?? lineFromTwoPoints(TL, BL)!,
  };

  const angles = {
    TL: cornerAngleDeg(BL, TL, TR),
    TR: cornerAngleDeg(TL, TR, BR),
    BR: cornerAngleDeg(TR, BR, BL),
    BL: cornerAngleDeg(BR, BL, TL),
  };
  const edgeAngles = {
    top: axialAngleDeg(lines.top),
    right: axialAngleDeg(lines.right),
    bottom: axialAngleDeg(lines.bottom),
    left: axialAngleDeg(lines.left),
  };
  const parallel = {
    topBottom: axialDifferenceDeg(edgeAngles.top, edgeAngles.bottom),
    leftRight: axialDifferenceDeg(edgeAngles.left, edgeAngles.right),
  };
  const level = {
    top: horizontalErrorDeg(edgeAngles.top),
    bottom: horizontalErrorDeg(edgeAngles.bottom),
    left: verticalErrorDeg(edgeAngles.left),
    right: verticalErrorDeg(edgeAngles.right),
  };
  const long = (distance(TL, TR) + distance(BL, BR)) / 2;
  const short = (distance(TL, BL) + distance(TR, BR)) / 2;
  const sourceAspect = long / Math.max(1e-6, short);
  const sourceAreaPercent = imageWidth > 0 && imageHeight > 0
    ? (Math.abs(polygonArea(corners)) / (imageWidth * imageHeight)) * 100
    : 0;
  const measurements: DlGeometryMeasurements = {
    cornerAnglesDeg: angles,
    edgeAnglesDeg: edgeAngles,
    parallelErrorDeg: parallel,
    levelErrorDeg: level,
    sourceAspect,
    sourceAreaPercent,
    convex: isConvexQuad(corners),
  };

  const allCorners90 = Object.values(angles).every(
    (angle) => Math.abs(angle - 90) <= DL_GEOMETRY_CONSTANTS.RECTANGLE_CORNER_TOLERANCE_DEG,
  );
  const oppositeParallel =
    parallel.topBottom <= DL_GEOMETRY_CONSTANTS.PARALLEL_TOLERANCE_DEG &&
    parallel.leftRight <= DL_GEOMETRY_CONSTANTS.PARALLEL_TOLERANCE_DEG;
  const levelNow =
    level.top <= DL_GEOMETRY_CONSTANTS.LEVEL_TOLERANCE_DEG &&
    level.bottom <= DL_GEOMETRY_CONSTANTS.LEVEL_TOLERANCE_DEG &&
    level.left <= DL_GEOMETRY_CONSTANTS.LEVEL_TOLERANCE_DEG &&
    level.right <= DL_GEOMETRY_CONSTANTS.LEVEL_TOLERANCE_DEG;

  if (allCorners90 && oppositeParallel) {
    if (levelNow) {
      return { classification: "FLAT_LEVEL", correction: "CROP", rotationAngleDeg: 0, measurements };
    }
    const rotationAngleDeg = meanAxialAngleDeg(edgeAngles.top, edgeAngles.bottom);
    return { classification: "FLAT_ROTATED", correction: "ROTATE", rotationAngleDeg, measurements };
  }

  return { classification: "PERSPECTIVE", correction: "PERSPECTIVE_WARP", rotationAngleDeg: null, measurements };
}

function getPerspectiveTransform(src: DlPoint[], dst: DlPoint[]): number[] {
  const a: number[][] = [];
  const b: number[] = [];
  for (let i = 0; i < 4; i += 1) {
    const { x, y } = src[i];
    const { x: xp, y: yp } = dst[i];
    a.push([x, y, 1, 0, 0, 0, -xp * x, -xp * y]);
    a.push([0, 0, 0, x, y, 1, -yp * x, -yp * y]);
    b.push(xp, yp);
  }
  const n = 8;
  const matrix = a.map((row, index) => [...row, b[index]]);
  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(matrix[row][col]) > Math.abs(matrix[pivot][col])) pivot = row;
    }
    if (Math.abs(matrix[pivot][col]) < 1e-10) throw new Error("Singular perspective transform");
    [matrix[col], matrix[pivot]] = [matrix[pivot], matrix[col]];
    for (let row = col + 1; row < n; row += 1) {
      const factor = matrix[row][col] / matrix[col][col];
      for (let k = col; k <= n; k += 1) matrix[row][k] -= factor * matrix[col][k];
    }
  }
  const h = new Array(n).fill(0);
  for (let i = n - 1; i >= 0; i -= 1) {
    h[i] = matrix[i][n] / matrix[i][i];
    for (let k = i - 1; k >= 0; k -= 1) matrix[k][n] -= matrix[k][i] * h[i];
  }
  return [...h, 1];
}

function perspectiveWarp(srcCanvas: HTMLCanvasElement, corners: DlPoint[]): HTMLCanvasElement {
  const outW = DL_GEOMETRY_CONSTANTS.TARGET_WIDTH;
  const outH = DL_GEOMETRY_CONSTANTS.TARGET_HEIGHT;
  const dst = document.createElement("canvas");
  dst.width = outW;
  dst.height = outH;
  const ctx = dst.getContext("2d", { willReadFrequently: true })!;
  const srcCtx = srcCanvas.getContext("2d", { willReadFrequently: true })!;
  const srcData = srcCtx.getImageData(0, 0, srcCanvas.width, srcCanvas.height);
  const dstData = ctx.createImageData(outW, outH);
  const destination: DlPoint[] = [
    { x: 0, y: 0 },
    { x: outW - 1, y: 0 },
    { x: outW - 1, y: outH - 1 },
    { x: 0, y: outH - 1 },
  ];
  const h = getPerspectiveTransform(destination, corners);

  for (let y = 0; y < outH; y += 1) {
    for (let x = 0; x < outW; x += 1) {
      const w = h[6] * x + h[7] * y + h[8];
      if (Math.abs(w) < 1e-10) continue;
      const sx = (h[0] * x + h[1] * y + h[2]) / w;
      const sy = (h[3] * x + h[4] * y + h[5]) / w;
      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const x1 = x0 + 1;
      const y1 = y0 + 1;
      if (x0 < 0 || y0 < 0 || x1 >= srcCanvas.width || y1 >= srcCanvas.height) continue;
      const fx = sx - x0;
      const fy = sy - y0;
      const out = (y * outW + x) * 4;
      for (let channel = 0; channel < 3; channel += 1) {
        const i00 = (y0 * srcCanvas.width + x0) * 4 + channel;
        const i10 = (y0 * srcCanvas.width + x1) * 4 + channel;
        const i01 = (y1 * srcCanvas.width + x0) * 4 + channel;
        const i11 = (y1 * srcCanvas.width + x1) * 4 + channel;
        dstData.data[out + channel] = Math.round(
          srcData.data[i00] * (1 - fx) * (1 - fy) +
          srcData.data[i10] * fx * (1 - fy) +
          srcData.data[i01] * (1 - fx) * fy +
          srcData.data[i11] * fx * fy,
        );
      }
      dstData.data[out + 3] = 255;
    }
  }
  ctx.putImageData(dstData, 0, 0);
  return dst;
}

function rotateCanvasAndPoints(src: HTMLCanvasElement, points: DlPoint[], angleDeg: number): { canvas: HTMLCanvasElement; points: DlPoint[] } {
  const rad = degToRad(angleDeg);
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const absCos = Math.abs(cos);
  const absSin = Math.abs(sin);
  const width = Math.ceil(src.width * absCos + src.height * absSin);
  const height = Math.ceil(src.width * absSin + src.height * absCos);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(width / 2, height / 2);
  ctx.rotate(rad);
  ctx.drawImage(src, -src.width / 2, -src.height / 2);

  const cx = src.width / 2;
  const cy = src.height / 2;
  const dx = width / 2;
  const dy = height / 2;
  const transformed = points.map((point) => {
    const px = point.x - cx;
    const py = point.y - cy;
    return {
      x: px * cos - py * sin + dx,
      y: px * sin + py * cos + dy,
    };
  });
  return { canvas, points: transformed };
}

function cropConfirmedRectangle(src: HTMLCanvasElement, corners: DlPoint[]): HTMLCanvasElement | null {
  const xs = corners.map((point) => point.x);
  const ys = corners.map((point) => point.y);
  const minX = Math.max(0, Math.floor(Math.min(...xs)));
  const minY = Math.max(0, Math.floor(Math.min(...ys)));
  const maxX = Math.min(src.width, Math.ceil(Math.max(...xs)));
  const maxY = Math.min(src.height, Math.ceil(Math.max(...ys)));
  const width = maxX - minX;
  const height = maxY - minY;
  if (width < 20 || height < 20) return null;
  const dst = document.createElement("canvas");
  dst.width = DL_GEOMETRY_CONSTANTS.TARGET_WIDTH;
  dst.height = DL_GEOMETRY_CONSTANTS.TARGET_HEIGHT;
  const ctx = dst.getContext("2d")!;
  ctx.drawImage(src, minX, minY, width, height, 0, 0, dst.width, dst.height);
  return dst;
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Unable to encode processed Driver Licence image"));
    }, "image/jpeg", 0.92);
  });
}

function validateProcessedCanvas(canvas: HTMLCanvasElement): { passed: boolean; reason: string | null } {
  if (canvas.width !== DL_GEOMETRY_CONSTANTS.TARGET_WIDTH || canvas.height !== DL_GEOMETRY_CONSTANTS.TARGET_HEIGHT) {
    return { passed: false, reason: "unexpected_output_dimensions" };
  }
  const aspect = canvas.width / canvas.height;
  const aspectError = Math.abs(aspect - DL_GEOMETRY_CONSTANTS.ID1_ASPECT) / DL_GEOMETRY_CONSTANTS.ID1_ASPECT;
  if (aspectError > 0.01) return { passed: false, reason: "output_aspect_invalid" };
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { passed: false, reason: "missing_canvas_context" };
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  let black = 0;
  let sampled = 0;
  const step = 8;
  for (let y = 0; y < canvas.height; y += step) {
    for (let x = 0; x < canvas.width; x += step) {
      if (x > step && y > step && x < canvas.width - step && y < canvas.height - step) continue;
      const i = (y * canvas.width + x) * 4;
      sampled += 1;
      if (data[i] < 6 && data[i + 1] < 6 && data[i + 2] < 6) black += 1;
    }
  }
  if (sampled > 0 && black / sampled > DL_GEOMETRY_CONSTANTS.MAX_BLACK_EDGE_RATIO) {
    return { passed: false, reason: "excessive_black_output_border" };
  }
  return { passed: true, reason: null };
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
        if (view.getUint16(entry, little) === 0x0112) return view.getUint16(entry + 8, little);
      }
      return 1;
    }
    offset += length;
  }
  return 1;
}

function drawImageWithExif(ctx: CanvasRenderingContext2D, image: CanvasImageSource & { width: number; height: number }, orientation: number): void {
  const width = image.width;
  const height = image.height;
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

async function loadOrientedCanvas(file: File): Promise<HTMLCanvasElement> {
  const orientation = await readExifOrientation(file);
  const bitmap = await createImageBitmap(file);
  try {
    const rotate90 = orientation >= 5 && orientation <= 8;
    const canvas = document.createElement("canvas");
    canvas.width = rotate90 ? bitmap.height : bitmap.width;
    canvas.height = rotate90 ? bitmap.width : bitmap.height;
    const ctx = canvas.getContext("2d")!;
    drawImageWithExif(ctx, bitmap as ImageBitmap & { width: number; height: number }, orientation);
    return canvas;
  } finally {
    bitmap.close();
  }
}

function createAnalysisCanvas(source: HTMLCanvasElement): HTMLCanvasElement {
  const maxSide = Math.max(source.width, source.height);
  const scale = Math.min(1, DL_GEOMETRY_CONSTANTS.ANALYSIS_MAX_SIDE / maxSide);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  canvas.getContext("2d")!.drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function scaleCorners(corners: DlPoint[], fromWidth: number, fromHeight: number, toWidth: number, toHeight: number): DlPoint[] {
  const sx = toWidth / fromWidth;
  const sy = toHeight / fromHeight;
  return corners.map((point) => ({ x: point.x * sx, y: point.y * sy }));
}

function emptyMetadata(width: number, height: number): DlPreprocessMetadata {
  return {
    version: "browser-four-edge-v1",
    status: "AUTOMATIC_GEOMETRY_UNCONFIRMED",
    semanticOrientation: "unknown",
    analysisWidth: width,
    analysisHeight: height,
    classification: "UNCONFIRMED",
    correction: "NONE",
    rotationAngleDeg: null,
    cornersConfirmed: false,
    corners: null,
    edges: { top: { ...EMPTY_EDGE }, right: { ...EMPTY_EDGE }, bottom: { ...EMPTY_EDGE }, left: { ...EMPTY_EDGE } },
    measurements: null,
    postValidation: { passed: false, reason: "four_edges_not_confirmed", finalWidth: null, finalHeight: null },
  };
}

export async function preprocessDriverLicense(file: File): Promise<DlPreprocessResult> {
  const source = await loadOrientedCanvas(file);
  const analysis = createAnalysisCanvas(source);
  const analysisCtx = analysis.getContext("2d", { willReadFrequently: true });
  if (!analysisCtx) {
    return { processedBlob: null, suggestedCorners: null, metadata: emptyMetadata(analysis.width, analysis.height) };
  }
  const image = analysisCtx.getImageData(0, 0, analysis.width, analysis.height);
  const { gradient } = grayscaleAndGradient(image);
  const candidates = roughCandidates(image, gradient);

  let confirmed: ConfirmedGeometry | null = null;
  for (const candidate of candidates) {
    confirmed = confirmFourEdges(candidate, gradient, analysis.width, analysis.height);
    if (confirmed) break;
  }

  if (!confirmed) {
    return { processedBlob: null, suggestedCorners: null, metadata: emptyMetadata(analysis.width, analysis.height) };
  }

  const classification = classifyDriverLicenseGeometry(confirmed.corners, confirmed.lines, analysis.width, analysis.height);
  const sourceCorners = scaleCorners(confirmed.corners, analysis.width, analysis.height, source.width, source.height);
  let processedCanvas: HTMLCanvasElement | null = null;

  if (classification.classification === "FLAT_LEVEL") {
    processedCanvas = cropConfirmedRectangle(source, sourceCorners);
  } else if (classification.classification === "FLAT_ROTATED") {
    const rotation = -(classification.rotationAngleDeg ?? 0);
    const rotated = rotateCanvasAndPoints(source, sourceCorners, rotation);
    processedCanvas = cropConfirmedRectangle(rotated.canvas, rotated.points);
  } else if (classification.classification === "PERSPECTIVE") {
    processedCanvas = perspectiveWarp(source, sourceCorners);
  }

  if (!processedCanvas) {
    const metadata = emptyMetadata(analysis.width, analysis.height);
    metadata.status = "AUTOMATIC_GEOMETRY_FAILED_VALIDATION";
    metadata.cornersConfirmed = true;
    metadata.classification = classification.classification;
    metadata.correction = classification.correction;
    metadata.rotationAngleDeg = classification.rotationAngleDeg;
    metadata.corners = { TL: confirmed.corners[0], TR: confirmed.corners[1], BR: confirmed.corners[2], BL: confirmed.corners[3] };
    metadata.edges = confirmed.diagnostics;
    metadata.measurements = classification.measurements;
    metadata.postValidation.reason = "correction_failed";
    return { processedBlob: null, suggestedCorners: sourceCorners, metadata };
  }

  const validation = validateProcessedCanvas(processedCanvas);
  const metadata: DlPreprocessMetadata = {
    version: "browser-four-edge-v1",
    status: validation.passed ? "PROCESSED" : "AUTOMATIC_GEOMETRY_FAILED_VALIDATION",
    semanticOrientation: "unknown",
    analysisWidth: analysis.width,
    analysisHeight: analysis.height,
    classification: classification.classification,
    correction: classification.correction,
    rotationAngleDeg: classification.rotationAngleDeg,
    cornersConfirmed: true,
    corners: { TL: confirmed.corners[0], TR: confirmed.corners[1], BR: confirmed.corners[2], BL: confirmed.corners[3] },
    edges: confirmed.diagnostics,
    measurements: classification.measurements,
    postValidation: {
      passed: validation.passed,
      reason: validation.reason,
      finalWidth: processedCanvas.width,
      finalHeight: processedCanvas.height,
    },
  };

  if (!validation.passed) return { processedBlob: null, suggestedCorners: sourceCorners, metadata };
  return { processedBlob: await canvasToBlob(processedCanvas), suggestedCorners: sourceCorners, metadata };
}
