/**
 * Browser-only DL upload prep: EXIF-aware decode + max long-side resize + JPEG.
 * No crop, corners, or licence geometry — server OpenCV remains sole authority.
 */

export const DL_UPLOAD_MAX_LONG_SIDE = 2400;
export const DL_UPLOAD_JPEG_QUALITY = 0.92;

function jpegBasename(originalName: string): string {
  const trimmed = (originalName || "upload").trim() || "upload";
  const base = trimmed.replace(/\.[^.]+$/, "") || "upload";
  return `${base}.jpg`;
}

function canvasToJpegBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("dl_upload_jpeg_encode_failed"));
          return;
        }
        resolve(blob);
      },
      "image/jpeg",
      DL_UPLOAD_JPEG_QUALITY,
    );
  });
}

/**
 * Normalize an applicant DL image for upload.
 * Non-images (e.g. PDF) are returned unchanged.
 */
export async function normalizeDlUpload(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) {
    return file;
  }

  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image",
  });

  try {
    const sourceWidth = bitmap.width;
    const sourceHeight = bitmap.height;
    const scale = Math.min(
      1,
      DL_UPLOAD_MAX_LONG_SIDE / Math.max(sourceWidth, sourceHeight),
    );
    const width = Math.max(1, Math.round(sourceWidth * scale));
    const height = Math.max(1, Math.round(sourceHeight * scale));

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("dl_upload_canvas_unavailable");
    }
    ctx.drawImage(bitmap, 0, 0, width, height);

    const blob = await canvasToJpegBlob(canvas);
    return new File([blob], jpegBasename(file.name), {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  } finally {
    bitmap.close();
  }
}
