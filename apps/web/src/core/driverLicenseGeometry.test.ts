import { describe, expect, it } from "vitest";

import {
  axialCircularMeanDeg,
  classifyGeometry,
  cornersFromEdgeLines,
  lineFromPoints,
  measureQuadrilateral,
  validateSourceQuadrilateral,
  type EdgeLines,
  type Point,
} from "./driverLicenseGeometry";

const BASE: Point[] = [
  { x: 100, y: 100 },
  { x: 1686, y: 100 },
  { x: 1686, y: 1100 },
  { x: 100, y: 1100 },
];

function edgesFor(points: Point[]): EdgeLines {
  const [tl, tr, br, bl] = points;
  return {
    top: lineFromPoints(tl, tr)!,
    right: lineFromPoints(tr, br)!,
    bottom: lineFromPoints(bl, br)!,
    left: lineFromPoints(tl, bl)!,
    all_four_confirmed: true,
  };
}

function rotate(points: Point[], degrees: number): Point[] {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const cx = 893;
  const cy = 600;
  return points.map((point) => {
    const x = point.x - cx;
    const y = point.y - cy;
    return { x: x * cos - y * sin + cx, y: x * sin + y * cos + cy };
  });
}

describe("Driver Licence four-corner decision tree", () => {
  it("classifies a flat, level rectangle as FLAT_LEVEL", () => {
    const edges = edgesFor(BASE);
    const metrics = measureQuadrilateral(BASE, edges, 2000, 1400);
    expect(metrics.corner_angles_deg.every((angle) => Math.abs(angle - 90) < 1e-6)).toBe(true);
    expect(classifyGeometry(BASE, edges, metrics)).toBe("FLAT_LEVEL");
  });

  it("classifies a true rectangle rotated 12 degrees as FLAT_ROTATED", () => {
    const points = rotate(BASE, 12);
    const edges = edgesFor(points);
    const metrics = measureQuadrilateral(points, edges, 2200, 1800);
    expect(metrics.corner_angles_deg.every((angle) => Math.abs(angle - 90) < 1e-6)).toBe(true);
    expect(metrics.parallel_error_top_bottom_deg).toBeCloseTo(0, 6);
    expect(metrics.parallel_error_left_right_deg).toBeCloseTo(0, 6);
    expect(classifyGeometry(points, edges, metrics)).toBe("FLAT_ROTATED");
    expect(metrics.rotation_action_deg).toBeCloseTo(-12, 5);
  });

  it("uses an axial mean so 89 and -89 degrees average as a vertical line, not zero", () => {
    expect(Math.abs(axialCircularMeanDeg([89, -89]))).toBeCloseTo(90, 5);
  });

  it("classifies a non-rectangular four-corner quadrilateral as PERSPECTIVE", () => {
    const points: Point[] = [
      { x: 150, y: 120 },
      { x: 1650, y: 230 },
      { x: 1420, y: 1080 },
      { x: 280, y: 1010 },
    ];
    const edges = edgesFor(points);
    const metrics = measureQuadrilateral(points, edges, 2000, 1400);
    expect(classifyGeometry(points, edges, metrics)).toBe("PERSPECTIVE");
  });

  it("does not create four corners when an independently fitted edge is missing", () => {
    const edges = edgesFor(BASE);
    delete edges.left;
    edges.all_four_confirmed = false;
    expect(cornersFromEdgeLines(edges)).toBeNull();
  });

  it("derives mathematical corners from straight-edge intersections, not rounded arc pixels", () => {
    const edges: EdgeLines = {
      top: { vx: 1, vy: 0, x0: 100, y0: 100 },
      right: { vx: 0, vy: 1, x0: 1686, y0: 160 },
      bottom: { vx: 1, vy: 0, x0: 150, y0: 1100 },
      left: { vx: 0, vy: 1, x0: 100, y0: 160 },
      all_four_confirmed: true,
    };
    const corners = cornersFromEdgeLines(edges)!;
    expect(corners[0].x).toBeCloseTo(100, 6);
    expect(corners[0].y).toBeCloseTo(100, 6);
    expect(corners[2].x).toBeCloseTo(1686, 6);
    expect(corners[2].y).toBeCloseTo(1100, 6);
  });

  it("does not reject a sane perspective quadrilateral because its source aspect is distorted", () => {
    const points: Point[] = [
      { x: 250, y: 100 },
      { x: 1750, y: 300 },
      { x: 1250, y: 1200 },
      { x: 400, y: 1050 },
    ];
    expect(validateSourceQuadrilateral(points, 2000, 1400).valid).toBe(true);
  });
});
