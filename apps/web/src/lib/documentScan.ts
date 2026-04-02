/**
 * Document prep for ID upload: manual EXIF rotation + force landscape → export JPEG.
 * No browser scanner; server OpenCV does deskew/perspective/quality.
 * Output is always landscape (width >= height). Backend (dl_enhance) also applies EXIF + force landscape.
 */

const JPEG_QUALITY = 0.92;
const LOG_PREFIX = "[DL scan]";

function log(msg: string, data?: Record<string, unknown>): void {
  if (typeof console !== "undefined" && console.info) {
    if (data != null) console.info(LOG_PREFIX, msg, data);
    else console.info(LOG_PREFIX, msg);
  }
}

/**
 * Return a canvas that is always landscape (width >= height).
 * If input is portrait, rotate 90° clockwise so the image is landscape.
 */
function ensureLandscape(canvas: HTMLCanvasElement): HTMLCanvasElement {
  const w = canvas.width;
  const h = canvas.height;
  if (w >= h) {
    log("ensureLandscape: already landscape", { width: w, height: h });
    return canvas;
  }
  log("ensureLandscape: portrait → rotating 90° to landscape", { before: `${w}x${h}`, after: `${h}x${w}` });
  const out = document.createElement("canvas");
  out.width = h;
  out.height = w;
  const ctx = out.getContext("2d");
  if (!ctx) return canvas;
  ctx.translate(out.width, 0);
  ctx.rotate(90 * (Math.PI / 180));
  ctx.drawImage(canvas, 0, 0);
  return out;
}

/**
 * Read EXIF Orientation tag (0x0112) from JPEG. Returns 1–8; 1 = no rotation.
 */
function getExifOrientation(buffer: ArrayBuffer): number {
  const view = new DataView(buffer);
  const len = view.byteLength;
  if (len < 2 || view.getUint16(0, false) !== 0xffd8) return 1;
  let offset = 2;

  while (offset + 4 <= len) {
    const marker = view.getUint16(offset, false);
    offset += 2;

    if (marker === 0xffda || marker === 0xffd9) break;

    const size = view.getUint16(offset, false);
    if (size < 2) break;

    if (marker === 0xffe1) {
      const start = offset + 2;
      if (start + 6 > len) return 1;
      if (view.getUint32(start, false) !== 0x45786966) return 1;

      const tiffStart = start + 6;
      const little = view.getUint16(tiffStart, false) === 0x4949;
      const ifdOffset = view.getUint32(tiffStart + 4, little);
      const ifdStart = tiffStart + ifdOffset;
      if (ifdStart + 2 > len) return 1;

      const numTags = view.getUint16(ifdStart, little);
      for (let i = 0; i < numTags; i++) {
        const tag = ifdStart + 2 + i * 12;
        if (tag + 12 > len) break;
        if (view.getUint16(tag, little) === 0x0112) {
          return view.getUint16(tag + 8, little);
        }
      }
      return 1;
    }

    offset += size;
  }
  return 1;
}

/**
 * Load image and apply EXIF orientation manually (canvas rotate).
 * Uses imageOrientation: "none" then rotates canvas by EXIF Orientation (1–8).
 */
async function loadWithManualExifRotation(file: File): Promise<HTMLCanvasElement> {
  const buffer = await file.arrayBuffer();
  const orientation = getExifOrientation(buffer);
  log("EXIF orientation tag", { orientation });

  const bitmap = await createImageBitmap(file, { imageOrientation: "none" });
  const w = bitmap.width;
  const h = bitmap.height;

  const swap = orientation >= 5 && orientation <= 8;
  const cw = swap ? h : w;
  const ch = swap ? w : h;

  const canvas = document.createElement("canvas");
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bitmap.close();
    throw new Error("No 2d context");
  }

  switch (orientation) {
    case 2:
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 3:
      ctx.translate(canvas.width, canvas.height);
      ctx.rotate(Math.PI);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 4:
      ctx.translate(0, canvas.height);
      ctx.scale(1, -1);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 5:
      ctx.translate(canvas.width, 0);
      ctx.rotate(Math.PI / 2);
      ctx.scale(1, -1);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 6:
      ctx.translate(canvas.width, 0);
      ctx.rotate(Math.PI / 2);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 7:
      ctx.translate(0, canvas.height);
      ctx.rotate(-Math.PI / 2);
      ctx.scale(-1, 1);
      ctx.drawImage(bitmap, 0, 0);
      break;
    case 8:
      ctx.translate(0, canvas.height);
      ctx.rotate(-Math.PI / 2);
      ctx.drawImage(bitmap, 0, 0);
      break;
    default:
      ctx.drawImage(bitmap, 0, 0);
      break;
  }

  bitmap.close();
  return canvas;
}

/**
 * Orientation → force landscape → JPEG. No deskew/crop (server OpenCV does that).
 */
async function applyExifAndExportJpeg(file: File): Promise<Blob | null> {
  try {
    log("Loading with manual EXIF rotation");
    const canvas = await loadWithManualExifRotation(file);
    log("after manual EXIF", { width: canvas.width, height: canvas.height, portrait: canvas.height > canvas.width });
    const landscape = ensureLandscape(canvas);
    return new Promise((resolve) => {
      landscape.toBlob((blob) => resolve(blob ?? null), "image/jpeg", JPEG_QUALITY);
    });
  } catch (e) {
    log("EXIF path failed", { error: String(e) });
    return null;
  }
}

/**
 * Prepare image for upload: manual EXIF + force landscape → JPEG blob.
 */
export async function extractDocumentFromFile(file: File): Promise<Blob | null> {
  if (!file.type.startsWith("image/")) return null;
  return applyExifAndExportJpeg(file);
}

/**
 * Same pipeline as extract (for preview consistency).
 */
export async function getOrientationCorrectedPreviewBlob(file: File): Promise<Blob | null> {
  if (!file.type.startsWith("image/")) return null;
  return extractDocumentFromFile(file);
}
