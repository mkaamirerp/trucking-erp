import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

type Point = { x: number; y: number };

type Props = {
  imageFile: File;
  label?: string;
  outputWidth?: number;
  outputHeight?: number;
  onConfirm: (corrected: Blob) => void;
  onCancel?: () => void;
  confirmLabel?: string;
};

const OUTPUT_W = 1400;
const OUTPUT_H = 880;
const HANDLE_R = 18;
const HANDLE_HIT = 32;
const MIN_GAP = 24;
const CORNER_COLORS = ["#f5a623", "#34d399", "#60a5fa", "#f472b6"];
const CORNER_LABELS = ["TL", "TR", "BR", "BL"];
const LOUPE_SIZE = 148;
const LOUPE_SAMPLE = 56;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeRotation(value: number): number {
  const normalized = ((value % 360) + 360) % 360;
  if (normalized === 270) return -90;
  if (normalized === 180) return 180;
  if (normalized === 90) return 90;
  return 0;
}

function normalizeRotationDelta(value: number): number {
  const normalized = ((value % 360) + 360) % 360;
  if (normalized === 270) return -90;
  if (normalized === 180) return 180;
  if (normalized === 90) return 90;
  return 0;
}

function rotateSourcePoint(x: number, y: number, width: number, height: number, delta: number): Point {
  if (delta === 90) {
    return { x: height - y, y: x };
  }
  if (delta === -90) {
    return { x: y, y: width - x };
  }
  if (Math.abs(delta) === 180) {
    return { x: width - x, y: height - y };
  }
  return { x, y };
}

function orderCorners(points: Point[]): Point[] {
  if (points.length !== 4) return points;
  const byYThenX = [...points].sort((a, b) => (a.y - b.y) || (a.x - b.x));
  const top = byYThenX.slice(0, 2).sort((a, b) => a.x - b.x);
  const bottom = byYThenX.slice(2).sort((a, b) => a.x - b.x);
  const [tl, tr] = top;
  const [bl, br] = bottom;
  return [tl, tr, br, bl];
}

function defaultCorners(width: number, height: number): Point[] {
  const pad = 0.1;
  return [
    { x: width * pad, y: height * pad },
    { x: width * (1 - pad), y: height * pad },
    { x: width * (1 - pad), y: height * (1 - pad) },
    { x: width * pad, y: height * (1 - pad) },
  ];
}

function isConvexQuad(points: Point[]): boolean {
  if (points.length !== 4) return false;
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % 4];
    const c = points[(i + 2) % 4];
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cross) < 1e-6) return false;
    const currentSign = Math.sign(cross);
    if (sign === 0) sign = currentSign;
    if (sign !== currentSign) return false;
  }
  return true;
}

function respectsCornerOrder(points: Point[]): boolean {
  const [tl, tr, br, bl] = points;
  return (
    tl.x < tr.x - MIN_GAP &&
    bl.x < br.x - MIN_GAP &&
    tl.y < bl.y - MIN_GAP &&
    tr.y < br.y - MIN_GAP
  );
}

function getPerspectiveTransform(src: Point[], dst: Point[]): number[] {
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
  const m = a.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col += 1) {
    let maxRow = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(m[row][col]) > Math.abs(m[maxRow][col])) maxRow = row;
    }
    [m[col], m[maxRow]] = [m[maxRow], m[col]];
    for (let row = col + 1; row < n; row += 1) {
      const factor = m[row][col] / m[col][col];
      for (let k = col; k <= n; k += 1) m[row][k] -= factor * m[col][k];
    }
  }
  const h = new Array(n).fill(0);
  for (let i = n - 1; i >= 0; i -= 1) {
    h[i] = m[i][n] / m[i][i];
    for (let k = i - 1; k >= 0; k -= 1) m[k][n] -= m[k][i] * h[i];
  }
  return [...h, 1];
}

function applyWarp(srcCanvas: HTMLCanvasElement, corners: Point[], outW: number, outH: number): HTMLCanvasElement {
  const dst = document.createElement("canvas");
  dst.width = outW;
  dst.height = outH;
  const ctx = dst.getContext("2d")!;
  const srcCtx = srcCanvas.getContext("2d")!;
  const srcData = srcCtx.getImageData(0, 0, srcCanvas.width, srcCanvas.height);
  const dstData = ctx.createImageData(outW, outH);
  const sw = srcCanvas.width;
  const sh = srcCanvas.height;

  const dstPts: Point[] = [
    { x: 0, y: 0 },
    { x: outW - 1, y: 0 },
    { x: outW - 1, y: outH - 1 },
    { x: 0, y: outH - 1 },
  ];

  const h = getPerspectiveTransform(dstPts, corners);
  for (let dy = 0; dy < outH; dy += 1) {
    for (let dx = 0; dx < outW; dx += 1) {
      const w = h[6] * dx + h[7] * dy + h[8];
      const sx = (h[0] * dx + h[1] * dy + h[2]) / w;
      const sy = (h[3] * dx + h[4] * dy + h[5]) / w;

      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const x1 = x0 + 1;
      const y1 = y0 + 1;
      const fx = sx - x0;
      const fy = sy - y0;
      if (x0 < 0 || y0 < 0 || x1 >= sw || y1 >= sh) continue;

      const idx = (dy * outW + dx) * 4;
      for (let c = 0; c < 3; c += 1) {
        const i00 = (y0 * sw + x0) * 4 + c;
        const i10 = (y0 * sw + x1) * 4 + c;
        const i01 = (y1 * sw + x0) * 4 + c;
        const i11 = (y1 * sw + x1) * 4 + c;
        dstData.data[idx + c] = Math.round(
          srcData.data[i00] * (1 - fx) * (1 - fy) +
          srcData.data[i10] * fx * (1 - fy) +
          srcData.data[i01] * (1 - fx) * fy +
          srcData.data[i11] * fx * fy
        );
      }
      dstData.data[idx + 3] = 255;
    }
  }
  ctx.putImageData(dstData, 0, 0);
  return dst;
}

function getEdgeLength(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function resolveExportSize(
  srcCorners: Point[],
  fallbackWidth: number,
  fallbackHeight: number,
): { width: number; height: number } {
  if (srcCorners.length !== 4) {
    return { width: fallbackWidth, height: fallbackHeight };
  }

  const topW = getEdgeLength(srcCorners[0], srcCorners[1]);
  const rightH = getEdgeLength(srcCorners[1], srcCorners[2]);
  const bottomW = getEdgeLength(srcCorners[2], srcCorners[3]);
  const leftH = getEdgeLength(srcCorners[3], srcCorners[0]);

  const nativeWidth = Math.round((topW + bottomW) / 2);
  const nativeHeight = Math.round((leftH + rightH) / 2);

  if (!Number.isFinite(nativeWidth) || !Number.isFinite(nativeHeight) || nativeWidth < 1 || nativeHeight < 1) {
    return { width: fallbackWidth, height: fallbackHeight };
  }

  // Preserve the crop's native pixel detail instead of forcing a smaller fixed export.
  return { width: nativeWidth, height: nativeHeight };
}

function rotateCanvas(src: HTMLCanvasElement, angleDeg: number): HTMLCanvasElement {
  const rad = (angleDeg * Math.PI) / 180;
  const cos = Math.abs(Math.cos(rad));
  const sin = Math.abs(Math.sin(rad));
  const newW = Math.round(src.width * cos + src.height * sin);
  const newH = Math.round(src.width * sin + src.height * cos);
  const dst = document.createElement("canvas");
  dst.width = newW;
  dst.height = newH;
  const ctx = dst.getContext("2d")!;
  ctx.translate(newW / 2, newH / 2);
  ctx.rotate(rad);
  ctx.drawImage(src, -src.width / 2, -src.height / 2);
  return dst;
}

async function readExifOrientation(file: File): Promise<number> {
  const buffer = await file.arrayBuffer();
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
      const tiffOffset = offset + 2;
      if (view.getUint32(tiffOffset, false) !== 0x45786966) return 1;

      const byteOrderOffset = tiffOffset + 6;
      const littleEndian = view.getUint16(byteOrderOffset, false) === 0x4949;
      const ifdOffset = view.getUint32(byteOrderOffset + 4, littleEndian);
      let dirStart = byteOrderOffset + ifdOffset;
      if (dirStart + 2 > view.byteLength) return 1;

      const entries = view.getUint16(dirStart, littleEndian);
      dirStart += 2;
      for (let i = 0; i < entries; i += 1) {
        const entryOffset = dirStart + i * 12;
        if (entryOffset + 12 > view.byteLength) break;
        const tag = view.getUint16(entryOffset, littleEndian);
        if (tag === 0x0112) {
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

function drawImageWithOrientation(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  orientation: number,
): void {
  const { naturalWidth: width, naturalHeight: height } = image;

  switch (orientation) {
    case 2:
      ctx.translate(width, 0);
      ctx.scale(-1, 1);
      break;
    case 3:
      ctx.translate(width, height);
      ctx.rotate(Math.PI);
      break;
    case 4:
      ctx.translate(0, height);
      ctx.scale(1, -1);
      break;
    case 5:
      ctx.rotate(0.5 * Math.PI);
      ctx.scale(1, -1);
      break;
    case 6:
      ctx.translate(height, 0);
      ctx.rotate(0.5 * Math.PI);
      break;
    case 7:
      ctx.translate(height, 0);
      ctx.rotate(0.5 * Math.PI);
      ctx.scale(-1, 1);
      break;
    case 8:
      ctx.translate(0, width);
      ctx.rotate(-0.5 * Math.PI);
      break;
    default:
      break;
  }

  ctx.drawImage(image, 0, 0);
}

async function loadImageCanvas(file: File): Promise<HTMLCanvasElement> {
  const orientation = await readExifOrientation(file);
  const canvas = document.createElement("canvas");
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
    const rotate90 = orientation >= 5 && orientation <= 8;
    canvas.width = rotate90 ? image.naturalHeight : image.naturalWidth;
    canvas.height = rotate90 ? image.naturalWidth : image.naturalHeight;
    const ctx = canvas.getContext("2d")!;
    drawImageWithOrientation(ctx, image, orientation);
    return canvas;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function DLCornerTool({
  imageFile,
  label = "Driver's Licence",
  outputWidth = OUTPUT_W,
  outputHeight = OUTPUT_H,
  onConfirm,
  onCancel,
  confirmLabel = "Looks Good - Apply",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const baseCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const srcCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const displayRef = useRef({ w: 0, h: 0 });
  const rotationRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const pendingPointRef = useRef<Point | null>(null);
  const activePointerIdRef = useRef<number | null>(null);

  const [corners, setCorners] = useState<Point[]>([]);
  const [dragging, setDragging] = useState<number | null>(null);
  const [dragPoint, setDragPoint] = useState<Point | null>(null);
  const [rotation, setRotation] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [ready, setReady] = useState(false);

  const getDisplay = useCallback((srcW: number, srcH: number) => {
    const container = containerRef.current;
    if (!container) return { w: srcW, h: srcH };
    const maxW = container.clientWidth - 32;
    const maxH = Math.min(window.innerHeight * 0.66, 620);
    const scale = Math.min(maxW / srcW, maxH / srcH, 1);
    return { w: Math.round(srcW * scale), h: Math.round(srcH * scale) };
  }, []);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setCorners([]);
    setRotation(0);
    loadImageCanvas(imageFile).then((canvas) => {
      if (cancelled) return;
      baseCanvasRef.current = canvas;
      srcCanvasRef.current = canvas;
      const disp = getDisplay(canvas.width, canvas.height);
      displayRef.current = disp;
      setCorners(defaultCorners(disp.w, disp.h));
      setReady(true);
    }).catch(() => {
      if (!cancelled) setReady(false);
    });
    return () => {
      cancelled = true;
    };
  }, [getDisplay, imageFile]);

  useEffect(() => {
    const base = baseCanvasRef.current;
    if (!base || !ready) return;
    const prevRotation = rotationRef.current;
    const prevSrc = srcCanvasRef.current ?? base;
    const prevDisp = displayRef.current;
    const working = rotation !== 0 ? rotateCanvas(base, rotation) : base;
    srcCanvasRef.current = working;
    const disp = getDisplay(working.width, working.height);
    displayRef.current = disp;
    const rotationDelta = normalizeRotationDelta(rotation - prevRotation);
    rotationRef.current = rotation;
    setCorners((prev) => {
      if (prev.length !== 4 || rotationDelta === 0 || prevDisp.w === 0 || prevDisp.h === 0) {
        return defaultCorners(disp.w, disp.h);
      }
      const next = prev.map((corner) => {
        const srcX = corner.x * (prevSrc.width / prevDisp.w);
        const srcY = corner.y * (prevSrc.height / prevDisp.h);
        const rotated = rotateSourcePoint(srcX, srcY, prevSrc.width, prevSrc.height, rotationDelta);
        return {
          x: rotated.x * (disp.w / working.width),
          y: rotated.y * (disp.h / working.height),
        };
      });
      const ordered = orderCorners(next);
      return respectsCornerOrder(ordered) && isConvexQuad(ordered) ? ordered : defaultCorners(disp.w, disp.h);
    });
  }, [getDisplay, ready, rotation]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const src = srcCanvasRef.current;
    if (!canvas || !src || corners.length !== 4) return;
    const disp = displayRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(disp.w * dpr);
    canvas.height = Math.round(disp.h * dpr);
    canvas.style.width = `${disp.w}px`;
    canvas.style.height = `${disp.h}px`;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    ctx.clearRect(0, 0, disp.w, disp.h);
    ctx.drawImage(src, 0, 0, disp.w, disp.h);

    ctx.save();
    ctx.fillStyle = "rgba(6,10,18,0.34)";
    ctx.fillRect(0, 0, disp.w, disp.h);
    ctx.restore();

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i = 1; i < 4; i += 1) ctx.lineTo(corners[i].x, corners[i].y);
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(src, 0, 0, disp.w, disp.h);
    ctx.restore();

    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i = 1; i < 4; i += 1) ctx.lineTo(corners[i].x, corners[i].y);
    ctx.closePath();
    ctx.strokeStyle = "rgba(245,166,35,0.98)";
    ctx.lineWidth = 2.8;
    ctx.setLineDash([6, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    [[0, 1], [1, 2], [2, 3], [3, 0]].forEach(([a, b]) => {
      ctx.beginPath();
      ctx.moveTo(corners[a].x, corners[a].y);
      ctx.lineTo(corners[b].x, corners[b].y);
      ctx.strokeStyle = "rgba(245,166,35,0.8)";
      ctx.lineWidth = 1.7;
      ctx.stroke();
    });

    corners.forEach((pt, i) => {
      const isActive = dragging === i;
      const gradient = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, HANDLE_R * 1.8);
      gradient.addColorStop(0, `${CORNER_COLORS[i]}55`);
      gradient.addColorStop(1, "transparent");
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, HANDLE_R * 1.8, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(pt.x, pt.y, HANDLE_R, 0, Math.PI * 2);
      ctx.fillStyle = `${CORNER_COLORS[i]}aa`;
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = isActive ? 3 : 2;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(pt.x, pt.y, HANDLE_R * 0.44, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.fill();

      ctx.fillStyle = "#0f1117";
      ctx.font = "bold 10px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(CORNER_LABELS[i], pt.x, pt.y);
    });

    if (dragging !== null && dragPoint) {
      const scaleX = src.width / disp.w;
      const scaleY = src.height / disp.h;
      const sw = LOUPE_SAMPLE * scaleX;
      const sh = LOUPE_SAMPLE * scaleY;
      const sourceX = clamp(dragPoint.x * scaleX - sw / 2, 0, Math.max(0, src.width - sw));
      const sourceY = clamp(dragPoint.y * scaleY - sh / 2, 0, Math.max(0, src.height - sh));
      const lx = Math.max(12, disp.w - LOUPE_SIZE - 12);
      const ly = 12;

      ctx.save();
      ctx.fillStyle = "rgba(7,10,18,0.92)";
      ctx.fillRect(lx - 4, ly - 4, LOUPE_SIZE + 8, LOUPE_SIZE + 8);
      ctx.strokeStyle = CORNER_COLORS[dragging];
      ctx.lineWidth = 2;
      ctx.strokeRect(lx - 4, ly - 4, LOUPE_SIZE + 8, LOUPE_SIZE + 8);
      ctx.drawImage(src, sourceX, sourceY, sw, sh, lx, ly, LOUPE_SIZE, LOUPE_SIZE);
      ctx.strokeStyle = "rgba(245,166,35,0.98)";
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(lx + LOUPE_SIZE / 2, ly);
      ctx.lineTo(lx + LOUPE_SIZE / 2, ly + LOUPE_SIZE);
      ctx.moveTo(lx, ly + LOUPE_SIZE / 2);
      ctx.lineTo(lx + LOUPE_SIZE, ly + LOUPE_SIZE / 2);
      ctx.stroke();
      ctx.fillStyle = "rgba(7,10,18,0.85)";
      ctx.fillRect(lx, ly + LOUPE_SIZE - 24, LOUPE_SIZE, 24);
      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`${CORNER_LABELS[dragging]} corner`, lx + LOUPE_SIZE / 2, ly + LOUPE_SIZE - 12);
      ctx.restore();
    }
  }, [corners, dragPoint, dragging]);

  const getCanvasPos = (clientX: number, clientY: number): Point => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const disp = displayRef.current;
    const scaleX = rect.width ? disp.w / rect.width : 1;
    const scaleY = rect.height ? disp.h / rect.height : 1;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  };

  const findHitCorner = (pos: Point): number => {
    for (let i = 0; i < corners.length; i += 1) {
      const dx = pos.x - corners[i].x;
      const dy = pos.y - corners[i].y;
      if (Math.hypot(dx, dy) < HANDLE_HIT) return i;
    }
    return -1;
  };

  const queueDragUpdate = useCallback((pos: Point) => {
    pendingPointRef.current = pos;
    if (rafRef.current !== null) return;
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      const point = pendingPointRef.current;
      pendingPointRef.current = null;
      if (!point) return;
      setDragPoint(point);
      setCorners((prev) => {
        if (dragging === null) return prev;
        const disp = displayRef.current;
        const next = prev.map((corner, i) => i === dragging ? {
          x: clamp(point.x, 0, disp.w),
          y: clamp(point.y, 0, disp.h),
        } : corner);
        return respectsCornerOrder(next) && isConvexQuad(next) ? next : prev;
      });
    });
  }, [dragging]);

  const handlePointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const pos = getCanvasPos(event.clientX, event.clientY);
    const hit = findHitCorner(pos);
    if (hit >= 0) {
      activePointerIdRef.current = event.pointerId;
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragging(hit);
      setDragPoint(pos);
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (dragging === null || activePointerIdRef.current !== event.pointerId) return;
    event.preventDefault();
    const samples = typeof event.nativeEvent.getCoalescedEvents === "function"
      ? event.nativeEvent.getCoalescedEvents()
      : [event.nativeEvent];
    const latest = samples[samples.length - 1];
    queueDragUpdate(getCanvasPos(latest.clientX, latest.clientY));
  };

  const handlePointerUp = (event?: ReactPointerEvent<HTMLCanvasElement>) => {
    if (event && activePointerIdRef.current === event.pointerId) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {}
    }
    activePointerIdRef.current = null;
    setDragging(null);
    setDragPoint(null);
  };

  const handleConfirm = async () => {
    const src = srcCanvasRef.current;
    if (!src || corners.length !== 4) return;
    setProcessing(true);
    await new Promise((resolve) => setTimeout(resolve, 30));
    try {
      const disp = displayRef.current;
      const scaleX = src.width / disp.w;
      const scaleY = src.height / disp.h;
      const srcCorners = corners.map((corner) => ({
        x: corner.x * scaleX,
        y: corner.y * scaleY,
      }));
      const fallbackLandscape = outputWidth >= outputHeight;
      const resolved = resolveExportSize(
        srcCorners,
        fallbackLandscape ? outputWidth : outputHeight,
        fallbackLandscape ? outputHeight : outputWidth,
      );
      const outW = resolved.width;
      const outH = resolved.height;
      const warped = applyWarp(src, srcCorners, outW, outH);
      warped.toBlob((blob) => {
        if (blob) onConfirm(blob);
        setProcessing(false);
      }, "image/jpeg", 0.96);
    } catch {
      setProcessing(false);
    }
  };

  const resetCorners = () => {
    const disp = displayRef.current;
    setCorners(defaultCorners(disp.w, disp.h));
    setRotation(0);
    setDragPoint(null);
  };

  return (
    <div
      ref={containerRef}
      style={{
        background: "#0d0f18",
        borderRadius: 14,
        border: "1px solid #1e2235",
        padding: "20px 20px 24px",
        fontFamily: "'DM Sans', 'Segoe UI', sans-serif",
        color: "#e2e8f0",
        userSelect: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, gap: 12 }}>
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#f5a623", marginBottom: 2 }}>
            Step - Adjust Card Corners
          </div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "#f1f5f9" }}>{label}</div>
        </div>
        <div style={{ background: "#1a1d2e", border: "1px solid #2a2d45", borderRadius: 8, padding: "6px 12px", fontSize: "0.72rem", color: "#64748b", lineHeight: 1.5, textAlign: "right" }}>
          {CORNER_LABELS.map((cornerLabel, i) => (
            <span key={cornerLabel} style={{ color: CORNER_COLORS[i], marginRight: i < 3 ? 8 : 0, fontWeight: 700 }}>
              {cornerLabel}
            </span>
          ))}
          <br />
          drag handles, use loupe
        </div>
      </div>

      {!ready ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 240, color: "#475569" }}>
          <span style={{ fontSize: "0.88rem" }}>Loading image...</span>
        </div>
      ) : (
        <div style={{ position: "relative", lineHeight: 0, borderRadius: 8, overflow: "hidden", boxShadow: "0 4px 32px #00000066" }}>
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", width: "100%" }}>
          <canvas
            ref={canvasRef}
            style={{ maxWidth: "100%", cursor: dragging !== null ? "grabbing" : "crosshair", display: "block", touchAction: "none", margin: "0 auto" }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onLostPointerCapture={handlePointerUp}
          />
          </div>
        </div>
      )}

      <div style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.07em", whiteSpace: "nowrap" }}>
          Rotate
        </span>
        <button
          type="button"
          onClick={() => setRotation((prev) => normalizeRotation(prev - 90))}
          style={{ background: "none", border: "1px solid #2a2d45", borderRadius: 8, color: "#cbd5e1", padding: "8px 14px", fontSize: "0.82rem", fontWeight: 700, cursor: "pointer" }}
        >
          Left
        </button>
        <button
          type="button"
          onClick={() => setRotation((prev) => normalizeRotation(prev + 90))}
          style={{ background: "none", border: "1px solid #2a2d45", borderRadius: 8, color: "#cbd5e1", padding: "8px 14px", fontSize: "0.82rem", fontWeight: 700, cursor: "pointer" }}
        >
          Right
        </button>
        <span style={{ fontSize: "0.8rem", fontWeight: 700, color: rotation !== 0 ? "#f5a623" : "#475569", minWidth: 48, textAlign: "right", fontVariantNumeric: "tabular-nums", marginLeft: "auto" }}>
          {rotation}°
        </span>
        {rotation !== 0 && (
          <button
            type="button"
            onClick={() => setRotation(0)}
            style={{ background: "none", border: "1px solid #2a2d45", borderRadius: 8, color: "#64748b", cursor: "pointer", fontSize: "0.75rem", padding: "8px 12px" }}
          >
            Reset rotation
          </button>
        )}
      </div>

      <div style={{ marginTop: 8, fontSize: "0.72rem", color: "#64748b", paddingLeft: 2 }}>
        Drag the corner handles. The zoom box appears while dragging so you can place each corner accurately.
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
        <button
          onClick={resetCorners}
          disabled={processing}
          style={{ background: "none", border: "1px solid #2a2d45", borderRadius: 8, color: "#64748b", padding: "10px 18px", fontSize: "0.85rem", fontWeight: 600, cursor: "pointer" }}
        >
          Reset
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={processing}
            style={{ background: "none", border: "1px solid #2a2d45", borderRadius: 8, color: "#64748b", padding: "10px 18px", fontSize: "0.85rem", fontWeight: 600, cursor: "pointer" }}
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleConfirm}
          disabled={processing || !ready}
          style={{
            marginLeft: "auto",
            background: processing ? "#2a2d45" : "linear-gradient(135deg, #f5a623, #e8951f)",
            border: "none",
            borderRadius: 8,
            color: processing ? "#64748b" : "#0d0f18",
            padding: "10px 28px",
            fontSize: "0.9rem",
            fontWeight: 800,
            cursor: processing ? "not-allowed" : "pointer",
            letterSpacing: "0.02em",
            boxShadow: processing ? "none" : "0 2px 16px #f5a62344",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {processing ? "Processing..." : confirmLabel}
        </button>
      </div>
    </div>
  );
}
