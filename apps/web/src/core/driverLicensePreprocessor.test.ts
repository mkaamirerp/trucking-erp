import { describe, expect, it } from "vitest";

import {
  classifyConfirmedGeometry,
  measureConfirmedGeometry,
  RECTANGLE_CORNER_TOLERANCE_DEG,
  PARALLEL_TOLERANCE_DEG,
  LEVEL_TOLERANCE_DEG,
  type DlPoint,
} from "./driverLicensePreprocessor";

function rotate(points: DlPoint[], degrees: number): DlPoint[] {
  const radians = degrees * Math.PI / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return points.map(({ x, y }) => ({ x: x * cos - y * sin, y: x * sin + y * cos }));
}

describe("driverLicensePreprocessor geometry decision order", () => {
  it("classifies a level rectangle as FLAT_LEVEL", () => {
    const points: DlPoint[] = [
      { x: 0, y: 0 },
      { x: 1586, y: 0 },
      { x: 1586, y: 1000 },
      { x: 0, y: 1000 },
    ];
    const measurement = measureConfirmedGeometry(points, 2000, 1400);
    expect(Object.values(measurement.cornerAngleErrorsDeg).every((v) => v <= RECTANGLE_CORNER_TOLERANCE_DEG)).toBe(true);
    expect(measurement.topBottomParallelErrorDeg).toBeLessThanOrEqual(PARALLEL_TOLERANCE_DEG);
    expect(measurement.leftRightParallelErrorDeg).toBeLessThanOrEqual(PARALLEL_TOLERANCE_DEG);
    expect(measurement.longEdgeHorizontalErrorDeg).toBeLessThanOrEqual(LEVEL_TOLERANCE_DEG);
    expect(classifyConfirmedGeometry(measurement)).toBe("FLAT_LEVEL");
  });

  it("classifies a 12 degree rectangle as FLAT_ROTATED, not perspective", () => {
    const points = rotate([
      { x: 0, y: 0 },
      { x: 1586, y: 0 },
      { x: 1586, y: 1000 },
      { x: 0, y: 1000 },
    ], 12);
    const measurement = measureConfirmedGeometry(points, 2200, 1800);
    expect(Object.values(measurement.cornerAngleErrorsDeg).every((v) => v <= RECTANGLE_CORNER_TOLERANCE_DEG)).toBe(true);
    expect(measurement.topBottomParallelErrorDeg).toBeLessThanOrEqual(PARALLEL_TOLERANCE_DEG);
    expect(measurement.leftRightParallelErrorDeg).toBeLessThanOrEqual(PARALLEL_TOLERANCE_DEG);
    expect(measurement.longEdgeHorizontalErrorDeg).toBeGreaterThan(LEVEL_TOLERANCE_DEG);
    expect(classifyConfirmedGeometry(measurement)).toBe("FLAT_ROTATED");
  });

  it("classifies non-rectangular confirmed geometry as PERSPECTIVE", () => {
    const points: DlPoint[] = [
      { x: 0, y: 0 },
      { x: 1500, y: 120 },
      { x: 1400, y: 900 },
      { x: 120, y: 1050 },
    ];
    const measurement = measureConfirmedGeometry(points, 1800, 1300);
    expect(classifyConfirmedGeometry(measurement)).toBe("PERSPECTIVE");
  });

  it("does not use apparent source ID-1 aspect as a strict perspective rejection gate", () => {
    const points: DlPoint[] = [
      { x: 100, y: 150 },
      { x: 1450, y: 80 },
      { x: 1275, y: 870 },
      { x: 260, y: 1020 },
    ];
    const measurement = measureConfirmedGeometry(points, 1700, 1200);
    expect(measurement.sourceAspect).not.toBeCloseTo(85.6 / 53.98, 2);
    expect(classifyConfirmedGeometry(measurement)).toBe("PERSPECTIVE");
  });
});
