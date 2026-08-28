/**
 * Pure Driver Licence quadrilateral geometry.
 *
 * Contract:
 * 1. Four independently supported straight edge lines are required.
 * 2. Rounded physical corners are ignored; mathematical corners are line intersections.
 * 3. Only after all four corners exist do we classify FLAT_LEVEL / FLAT_ROTATED / PERSPECTIVE.
 * 4. Source aspect and source corner angles are measurements, never pre-classification rejection gates.
 */

export const PREPROCESS_VERSION = "2026-08-28-four-corner-v3";

export const DL_ASPECT = 85.6 / 53.98;
export const TARGET_W = 1000;
export const TARGET_H = Math.round(TARGET_W / DL_ASPECT);

export const ANALYSIS_MAX_LONG_SIDE = 1600;
export const EDGE_SAMPLE_COUNT = 180;
export const EDGE_SAMPLE_CORNER_IGNORE_START = 0.08;
export const EDGE_SAMPLE_CORNER_IGNORE_END = 0.92;
export const MIN_ABSOLUTE_INLIERS = 50;
export const MIN_INLIER_RATIO = 0.28;
export const MIN_EDGE_SPAN_COVERAGE = 0.55;
export const RANSAC_DISTANCE_THRESHOLD = 4.5;
export const RANSAC_ITERATIONS = 400;
export const GRADIENT_MAG_THRESHOLD = 25;
export const SEARCH_PX_MIN = 30;
export const SEARCH_PX_MAX = 110;
export const SEARCH_PX_RATIO = 0.12;

export const RECTANGLE_CORNER_TOLERANCE_DEG = 4;
export const PARALLEL_TOLERANCE_DEG = 3;
export const LEVEL_TOLERANCE_DEG = 2;

export const SOURCE_MIN_AREA_PERCENT = 4;
export const SOURCE_MAX_AREA_PERCENT = 92;
export const SOURCE_CORNER_MARGIN_PX = 6;

export const POST_ASPECT_TOLERANCE_PERCENT = 1;
export const POST_BORDER_STRIP_RATIO = 0.04;
export const POST_MAX_BORDER_NEAR_BLACK_RATIO = 0.35;
export const POST_MIN_INTERIOR_NONBLACK_RATIO = 0.20;
export const POST_MIN_LUMINANCE_STD = 5;

export const ORIENTATION_ORDER = ["original", "cw90", "ccw90", "rotate180"] as const;
export type WorkingOrientation = (typeof ORIENTATION_ORDER)[number];
export type SemanticOrientation = 0 | 90 | 180 | 270 | "unknown";
export type GeometryClass = "UNCONFIRMED" | "FLAT_LEVEL" | "FLAT_ROTATED" | "PERSPECTIVE";
export type Point = { x: number; y: number };
export type LineParam = { vx: number; vy: number; x0: number; y0: number };
export type EdgeName = "top" | "right" | "bottom" | "left";

export type EdgeDiagnostics = {
  samples: number;
  inliers: number;
  inlier_ratio: number;
  coverage: number;
  line_angle_deg: number;
  fit_error: number;
  confirmed: boolean;
};

export type EdgeLines = {
  top?: LineParam;
  right?: LineParam;
  bottom?: LineParam;
  left?: LineParam;
  all_four_confirmed: boolean;
};

export type LevelErrors = {
  top_horizontal_error_deg: number;
  bottom_horizontal_error_deg: number;
  left_vertical_error_deg: number;
  right_vertical_error_deg: number;
};

export type GeometryMetrics = {
  top_angle_deg: number;
  right_angle_deg: number;
  bottom_angle_deg: number;
  left_angle_deg: number;
  corner_angles_deg: [number, number, number, number];
  parallel_error_top_bottom_deg: number;
  parallel_error_left_right_deg: number;
  rotation_action_deg: number;
  level_errors: LevelErrors;
  top_bottom_length_delta_percent: number;
  left_right_length_delta_percent: number;
  diagonal_delta_percent: number;
  source_aspect: number;
  quadrilateral_area_percent: number;
  border_touch_count: number;
};

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function polygonSignedArea(points: Point[]): number {
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a.x * b.y - b.x * a.y;
  }
  return area / 2;
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/**
 * Order a landscape card as TL, TR, BR, BL.
 * We sort around the centroid, anchor at the visually upper-left corner,
 * then choose the traversal whose first edge is the long edge.
 */
export function orderCorners(points: Point[]): Point[] {
  if (points.length !== 4) throw new Error("Driver Licence geometry requires exactly four corners");
  const center = points.reduce((acc, p) => ({ x: acc.x + p.x / 4, y: acc.y + p.y / 4 }), { x: 0, y: 0 });
  let ordered = [...points].sort(
    (a, b) => Math.atan2(a.y - center.y, a.x - center.x) - Math.atan2(b.y - center.y, b.x - center.x),
  );

  // Image coordinates have +Y downward. Ascending atan2 around an ordinary card gives TL,TR,BR,BL.
  if (polygonSignedArea(ordered) < 0) ordered = ordered.reverse();

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

  // The first segment must be the long edge (top), not the short side.
  if (distance(ordered[0], ordered[1]) < distance(ordered[0], ordered[3])) {
    ordered = [ordered[0], ordered[3], ordered[2], ordered[1]];
  }
  return ordered;
}

/** Normalize an undirected line angle to [-90, 90). */
export function axialAngleDeg(line: LineParam): number {
  let angle = (Math.atan2(line.vy, line.vx) * 180) / Math.PI;
  while (angle >= 90) angle -= 180;
  while (angle < -90) angle += 180;
  return Object.is(angle, -0) ? 0 : angle;
}

export function angularDiffDeg(a: number, b: number): number {
  let diff = Math.abs(a - b) % 180;
  if (diff > 90) diff = 180 - diff;
  return diff;
}

/** Correct axial/circular mean: line directions are equivalent modulo 180°, so average doubled angles. */
export function axialCircularMeanDeg(angles: number[]): number {
  if (!angles.length) return 0;
  let x = 0;
  let y = 0;
  for (const angle of angles) {
    const doubled = (2 * angle * Math.PI) / 180;
    x += Math.cos(doubled);
    y += Math.sin(doubled);
  }
  if (Math.abs(x) < 1e-12 && Math.abs(y) < 1e-12) return angles[0];
  let mean = (Math.atan2(y, x) * 90) / Math.PI;
  while (mean >= 90) mean -= 180;
  while (mean < -90) mean += 180;
  return Object.is(mean, -0) ? 0 : mean;
}

export function deviationFromHorizontalDeg(angle: number): number {
  let a = ((angle % 180) + 180) % 180;
  if (a > 90) a = 180 - a;
  return Math.abs(a);
}

export function deviationFromVerticalDeg(angle: number): number {
  return Math.abs(90 - deviationFromHorizontalDeg(angle));
}

export function angleAt(prev: Point, point: Point, next: Point): number {
  const a = { x: prev.x - point.x, y: prev.y - point.y };
  const b = { x: next.x - point.x, y: next.y - point.y };
  const denom = Math.hypot(a.x, a.y) * Math.hypot(b.x, b.y);
  if (denom < 1e-9) return 0;
  const cosine = clamp((a.x * b.x + a.y * b.y) / denom, -1, 1);
  return (Math.acos(cosine) * 180) / Math.PI;
}

export function lineFromPoints(a: Point, b: Point): LineParam | null {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = Math.hypot(dx, dy);
  if (length < 1e-8) return null;
  return { vx: dx / length, vy: dy / length, x0: a.x, y0: a.y };
}

export function intersectLines(a: LineParam, b: LineParam): Point | null {
  const det = a.vx * -b.vy - -b.vx * a.vy;
  if (Math.abs(det) < 1e-8) return null;
  const dx = b.x0 - a.x0;
  const dy = b.y0 - a.y0;
  const t = (dx * -b.vy - -b.vx * dy) / det;
  const x = a.x0 + t * a.vx;
  const y = a.y0 + t * a.vy;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

export function cornersFromEdgeLines(edges: EdgeLines): Point[] | null {
  if (!edges.all_four_confirmed || !edges.top || !edges.right || !edges.bottom || !edges.left) return null;
  const tl = intersectLines(edges.left, edges.top);
  const tr = intersectLines(edges.top, edges.right);
  const br = intersectLines(edges.right, edges.bottom);
  const bl = intersectLines(edges.bottom, edges.left);
  if (!tl || !tr || !br || !bl) return null;
  return orderCorners([tl, tr, br, bl]);
}

export function isConvexQuad(cornersInput: Point[]): boolean {
  const corners = orderCorners(cornersInput);
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const a = corners[i];
    const b = corners[(i + 1) % 4];
    const c = corners[(i + 2) % 4];
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cross) < 1e-8) return false;
    const current = Math.sign(cross);
    if (sign === 0) sign = current;
    if (current !== sign) return false;
  }
  return true;
}

export function computeLevelErrors(metrics: Pick<GeometryMetrics, "top_angle_deg" | "bottom_angle_deg" | "left_angle_deg" | "right_angle_deg">): LevelErrors {
  return {
    top_horizontal_error_deg: deviationFromHorizontalDeg(metrics.top_angle_deg),
    bottom_horizontal_error_deg: deviationFromHorizontalDeg(metrics.bottom_angle_deg),
    left_vertical_error_deg: deviationFromVerticalDeg(metrics.left_angle_deg),
    right_vertical_error_deg: deviationFromVerticalDeg(metrics.right_angle_deg),
  };
}

export function measureQuadrilateral(cornersInput: Point[], edgesInput: EdgeLines, imageW: number, imageH: number): GeometryMetrics {
  const corners = orderCorners(cornersInput);
  const [tl, tr, br, bl] = corners;
  const fallback = {
    top: lineFromPoints(tl, tr)!,
    right: lineFromPoints(tr, br)!,
    bottom: lineFromPoints(bl, br)!,
    left: lineFromPoints(tl, bl)!,
  };
  const top = edgesInput.top ?? fallback.top;
  const right = edgesInput.right ?? fallback.right;
  const bottom = edgesInput.bottom ?? fallback.bottom;
  const left = edgesInput.left ?? fallback.left;

  const topAngle = axialAngleDeg(top);
  const rightAngle = axialAngleDeg(right);
  const bottomAngle = axialAngleDeg(bottom);
  const leftAngle = axialAngleDeg(left);
  const cornerAngles: [number, number, number, number] = [
    angleAt(bl, tl, tr),
    angleAt(tl, tr, br),
    angleAt(tr, br, bl),
    angleAt(br, bl, tl),
  ];

  const topLen = distance(tl, tr);
  const bottomLen = distance(bl, br);
  const leftLen = distance(tl, bl);
  const rightLen = distance(tr, br);
  const diagonal1 = distance(tl, br);
  const diagonal2 = distance(tr, bl);
  const long = (topLen + bottomLen) / 2;
  const short = (leftLen + rightLen) / 2;
  const areaPercent = (Math.abs(polygonSignedArea(corners)) / Math.max(1, imageW * imageH)) * 100;
  const margin = Math.max(SOURCE_CORNER_MARGIN_PX, Math.floor(Math.max(imageW, imageH) * 0.006));
  const xs = corners.map((p) => p.x);
  const ys = corners.map((p) => p.y);
  const borderTouchCount = [
    Math.min(...xs) <= margin,
    Math.min(...ys) <= margin,
    Math.max(...xs) >= imageW - 1 - margin,
    Math.max(...ys) >= imageH - 1 - margin,
  ].filter(Boolean).length;

  const levelBase = {
    top_angle_deg: topAngle,
    right_angle_deg: rightAngle,
    bottom_angle_deg: bottomAngle,
    left_angle_deg: leftAngle,
  };

  return {
    ...levelBase,
    corner_angles_deg: cornerAngles,
    parallel_error_top_bottom_deg: angularDiffDeg(topAngle, bottomAngle),
    parallel_error_left_right_deg: angularDiffDeg(leftAngle, rightAngle),
    rotation_action_deg: -axialCircularMeanDeg([topAngle, bottomAngle]),
    level_errors: computeLevelErrors(levelBase),
    top_bottom_length_delta_percent: (Math.abs(topLen - bottomLen) / Math.max(topLen, bottomLen, 1e-9)) * 100,
    left_right_length_delta_percent: (Math.abs(leftLen - rightLen) / Math.max(leftLen, rightLen, 1e-9)) * 100,
    diagonal_delta_percent: (Math.abs(diagonal1 - diagonal2) / Math.max(diagonal1, diagonal2, 1e-9)) * 100,
    source_aspect: long / Math.max(short, 1e-9),
    quadrilateral_area_percent: areaPercent,
    border_touch_count: borderTouchCount,
  };
}

/**
 * Owner's decision tree, explicitly represented in code:
 * - no 4 corners => UNCONFIRMED
 * - all 4 angles ~90 AND opposite edges parallel => card is flat
 * - flat + level => FLAT_LEVEL
 * - flat + tilted => FLAT_ROTATED
 * - otherwise => PERSPECTIVE
 */
export function classifyGeometry(corners: Point[] | null, edges: EdgeLines, metrics: GeometryMetrics): GeometryClass {
  if (!corners || !edges.all_four_confirmed) return "UNCONFIRMED";

  const allFourAngles90 = metrics.corner_angles_deg.every(
    (angle) => Math.abs(angle - 90) <= RECTANGLE_CORNER_TOLERANCE_DEG,
  );
  const oppositeEdgesParallel =
    metrics.parallel_error_top_bottom_deg <= PARALLEL_TOLERANCE_DEG &&
    metrics.parallel_error_left_right_deg <= PARALLEL_TOLERANCE_DEG;

  if (!allFourAngles90 || !oppositeEdgesParallel) return "PERSPECTIVE";

  const level = metrics.level_errors;
  const alreadyStraight =
    level.top_horizontal_error_deg <= LEVEL_TOLERANCE_DEG &&
    level.bottom_horizontal_error_deg <= LEVEL_TOLERANCE_DEG &&
    level.left_vertical_error_deg <= LEVEL_TOLERANCE_DEG &&
    level.right_vertical_error_deg <= LEVEL_TOLERANCE_DEG;

  return alreadyStraight ? "FLAT_LEVEL" : "FLAT_ROTATED";
}

/** Pre-classification sanity only. No source aspect or source-angle rejection. */
export function validateSourceQuadrilateral(cornersInput: Point[], imageW: number, imageH: number): { valid: boolean; reason?: string } {
  const corners = orderCorners(cornersInput);
  if (!corners.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))) return { valid: false, reason: "non_finite_corner" };
  if (!isConvexQuad(corners)) return { valid: false, reason: "not_convex" };

  const margin = SOURCE_CORNER_MARGIN_PX;
  if (corners.some((p) => p.x < -margin || p.y < -margin || p.x > imageW + margin || p.y > imageH + margin)) {
    return { valid: false, reason: "corners_outside_source" };
  }

  const areaPercent = (Math.abs(polygonSignedArea(corners)) / Math.max(1, imageW * imageH)) * 100;
  if (areaPercent < SOURCE_MIN_AREA_PERCENT || areaPercent > SOURCE_MAX_AREA_PERCENT) {
    return { valid: false, reason: "area_out_of_range" };
  }
  return { valid: true };
}

export function rotatePointAroundImageCenter(
  point: Point,
  sourceW: number,
  sourceH: number,
  destW: number,
  destH: number,
  degrees: number,
): Point {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const px = point.x - sourceW / 2;
  const py = point.y - sourceH / 2;
  return {
    x: px * cos - py * sin + destW / 2,
    y: px * sin + py * cos + destH / 2,
  };
}

function isNearBlack(r: number, g: number, b: number): boolean {
  return r + g + b < 35;
}

export function postValidateDimensions(width: number, height: number): { pass: boolean; report: Record<string, unknown> } {
  if (width < 32 || height < 32) return { pass: false, report: { error: "too_small", width, height } };
  const landscape = width >= height;
  const aspect = width / height;
  const aspectErrorPercent = (Math.abs(aspect - DL_ASPECT) / DL_ASPECT) * 100;
  const pass = landscape && aspectErrorPercent <= POST_ASPECT_TOLERANCE_PERCENT;
  return { pass, report: { width, height, landscape, aspect, aspect_error_percent: aspectErrorPercent, pass } };
}

export function postValidateCanvas(canvas: HTMLCanvasElement, classification?: GeometryClass): { pass: boolean; report: Record<string, unknown> } {
  const dimensions = postValidateDimensions(canvas.width, canvas.height);
  if (!dimensions.pass) return { pass: false, report: { ...dimensions.report, stage: "dimensions" } };

  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { pass: false, report: { error: "missing_canvas_context" } };
  const { width, height, data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const stripX = Math.max(2, Math.floor(width * POST_BORDER_STRIP_RATIO));
  const stripY = Math.max(2, Math.floor(height * POST_BORDER_STRIP_RATIO));

  let borderTotal = 0;
  let borderBlack = 0;
  let interiorTotal = 0;
  let interiorNonBlack = 0;
  let luminanceCount = 0;
  let luminanceSum = 0;
  let luminanceSumSq = 0;

  for (let y = 0; y < height; y += 2) {
    for (let x = 0; x < width; x += 2) {
      const index = (y * width + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const nearBlack = isNearBlack(r, g, b);
      const border = x < stripX || x >= width - stripX || y < stripY || y >= height - stripY;
      if (border) {
        borderTotal += 1;
        if (nearBlack) borderBlack += 1;
      } else {
        interiorTotal += 1;
        if (!nearBlack) interiorNonBlack += 1;
        const lum = 0.299 * r + 0.587 * g + 0.114 * b;
        luminanceCount += 1;
        luminanceSum += lum;
        luminanceSumSq += lum * lum;
      }
    }
  }

  const borderBlackRatio = borderTotal ? borderBlack / borderTotal : 1;
  const interiorNonBlackRatio = interiorTotal ? interiorNonBlack / interiorTotal : 0;
  const mean = luminanceCount ? luminanceSum / luminanceCount : 0;
  const variance = luminanceCount ? Math.max(0, luminanceSumSq / luminanceCount - mean * mean) : 0;
  const luminanceStd = Math.sqrt(variance);
  const contentPass =
    borderBlackRatio <= POST_MAX_BORDER_NEAR_BLACK_RATIO &&
    interiorNonBlackRatio >= POST_MIN_INTERIOR_NONBLACK_RATIO &&
    luminanceStd >= POST_MIN_LUMINANCE_STD;

  return {
    pass: contentPass,
    report: {
      ...dimensions.report,
      classification,
      border_black_ratio: borderBlackRatio,
      interior_nonblack_ratio: interiorNonBlackRatio,
      luminance_std: luminanceStd,
      pass: contentPass,
    },
  };
}
