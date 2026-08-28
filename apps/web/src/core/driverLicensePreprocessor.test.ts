import { describe, expect, it } from "vitest";

import { classifyDriverLicenseGeometry } from "./driverLicensePreprocessor";

const BASE = [
  { x: 0, y: 0 },
  { x: 1586, y: 0 },
  { x: 1586, y: 1000 },
  { x: 0, y: 1000 },
];

function rotate(points: Array<{ x: number; y: number }>, degrees: number) {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const cx = 793;
  const cy = 500;
  return points.map((point) => {
    const x = point.x - cx;
    const y = point.y - cy;
    return {
      x: x * cos - y * sin + cx,
      y: x * sin + y * cos + cy,
    };
  });
}

describe("driver licence geometry classification", () => {
  it("classifies a rectangular level DL as FLAT_LEVEL", () => {
    const result = classifyDriverLicenseGeometry(BASE, undefined, 2000, 2000);
    expect(result.classification).toBe("FLAT_LEVEL");
    expect(result.correction).toBe("CROP");
    expect(result.measurements.cornerAnglesDeg.TL).toBeCloseTo(90, 6);
    expect(result.measurements.cornerAnglesDeg.TR).toBeCloseTo(90, 6);
    expect(result.measurements.cornerAnglesDeg.BR).toBeCloseTo(90, 6);
    expect(result.measurements.cornerAnglesDeg.BL).toBeCloseTo(90, 6);
    expect(result.measurements.levelErrorDeg.top).toBeCloseTo(0, 6);
    expect(result.measurements.levelErrorDeg.left).toBeCloseTo(0, 6);
  });

  it("classifies a true rectangle rotated 12 degrees as FLAT_ROTATED", () => {
    const result = classifyDriverLicenseGeometry(rotate(BASE, 12), undefined, 2000, 2000);
    expect(result.classification).toBe("FLAT_ROTATED");
    expect(result.correction).toBe("ROTATE");
    expect(result.rotationAngleDeg).toBeCloseTo(12, 4);
    expect(result.measurements.cornerAnglesDeg.TL).toBeCloseTo(90, 6);
    expect(result.measurements.parallelErrorDeg.topBottom).toBeCloseTo(0, 6);
    expect(result.measurements.parallelErrorDeg.leftRight).toBeCloseTo(0, 6);
  });

  it("classifies a non-rectangular quadrilateral as PERSPECTIVE", () => {
    const result = classifyDriverLicenseGeometry(
      [
        { x: 100, y: 100 },
        { x: 1500, y: 220 },
        { x: 1350, y: 1100 },
        { x: 250, y: 1000 },
      ],
      undefined,
      2000,
      1400,
    );
    expect(result.classification).toBe("PERSPECTIVE");
    expect(result.correction).toBe("PERSPECTIVE_WARP");
    expect(Math.abs(result.measurements.cornerAnglesDeg.TL - 90)).toBeGreaterThan(4);
  });
});
