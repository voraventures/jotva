const TYPES = /^image\/(jpeg|png|webp|gif)$/;
export const AVATAR_MAX_INPUT = 15 * 1024 * 1024;

// Centre-crop to a square, scale to `size` px and re-encode as JPEG. Re-encoding keeps the
// stored photo small and drops EXIF metadata such as GPS location.
export async function imageFileToAvatar(file, size = 256) {
  if (!TYPES.test(file.type) || file.size > AVATAR_MAX_INPUT) throw new Error("invalid-image");
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff"; // transparent PNGs would otherwise turn black as JPEG
  ctx.fillRect(0, 0, size, size);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, size, size);
  bitmap.close?.();
  return canvas.toDataURL("image/jpeg", 0.88);
}

export const initialsOf = (name) =>
  (name || "").trim().split(/\s+/).filter(Boolean).map((s) => s[0]).join("").slice(0, 2).toUpperCase();

// How a person's photo is looked up: their name or email, spaces collapsed, case-insensitive.
// Must match person_key() in backend/app/routes/misc.py.
export const personKey = (name) => (name || "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
