// Copies the app's own icons (frontend/src/components/ui/icons.tsx) into
// assets/icons as standalone SVG files, so the documents use the same drawings
// as the UI. Run again if the app's icons change.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "../../frontend/src/components/ui/icons.tsx"), "utf8");
const out = join(here, "assets/icons");
mkdirSync(out, { recursive: true });

const attr = (jsx) =>
  jsx
    .replace(/\b(stroke|fill)([A-Z]\w*)=/g, (_, a, b) => `${a}-${b.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase()).slice(1).toLowerCase()}=`)
    .replace(/strokeWidth=/g, "stroke-width=")
    .replace(/=\{([^}]+)\}/g, '="$1"');

let count = 0;
for (const match of source.matchAll(/export function (\w+)Icon\([^)]*\)\s*\{\s*return \(\s*<Icon \{\.\.\.props\}>([\s\S]*?)<\/Icon>/g)) {
  const [, name, body] = match;
  const file = name.replace(/[A-Z]/g, (c, i) => (i ? "-" : "") + c.toLowerCase());
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${attr(body).replace(/\s+/g, " ").trim()}</svg>\n`;
  writeFileSync(join(out, `${file}.svg`), svg);
  count++;
}
console.log(`${count} icons written to ${out}`);
