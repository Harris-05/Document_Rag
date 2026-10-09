// Copies the pdf.js worker and its font/colour data into public/pdfjs so the viewer can load them
// from the same origin. Runs automatically before dev, build and after install.
import { cp, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "pdfjs-dist");
const target = join(root, "public", "pdfjs");

if (!existsSync(source)) {
  console.warn("pdfjs-dist is not installed yet; skipping asset copy.");
  process.exit(0);
}

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(join(source, "legacy", "build", "pdf.worker.min.mjs"), join(target, "pdf.worker.min.mjs"));
for (const folder of ["cmaps", "standard_fonts", "wasm", "iccs"]) {
  if (existsSync(join(source, folder))) await cp(join(source, folder), join(target, folder), { recursive: true });
}
console.log("pdf.js assets copied to public/pdfjs");
