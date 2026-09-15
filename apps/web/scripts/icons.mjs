// Build the PWA icons from the logo. Run after changing it: pnpm --filter web icons
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "..");
const assets = path.resolve(root, "../../assets/logo");
const logo = await readFile(path.join(assets, "gaw-logo.svg"));
const mark = await readFile(path.join(assets, "mark.svg"));
const out = path.join(root, "public");
await mkdir(out, { recursive: true });

// The logo is already square and carries its own ground, so the plain icons are
// just a resize. Nothing to pad or centre.
for (const size of [192, 512]) {
  const png = await sharp(logo).resize(size, size).png().toBuffer();
  await writeFile(path.join(out, `icon-${size}.png`), png);
  console.log(`icon-${size}.png`);
}

// A maskable icon is cropped by the launcher to whatever shape the phone likes,
// so anything inside the outer tenth can be cut off. The logo reaches its edges:
// the dollar sign on one side, "GaW" near the bottom. Nesting it at 80% inside a
// full-bleed copy of its own ground keeps every part of it inside the safe zone,
// and the ring that gets cropped still looks like the logo rather than a border.
const inset = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 380 380">
  <rect width="380" height="380" fill="#DDE0E4"/>
  ${Buffer.from(logo)
    .toString("utf8")
    .replace(/^<svg /, '<svg x="38" y="38" width="304" height="304" ')
    .replace(/ width="1024" height="1024"/, "")}
</svg>`;
const maskable = await sharp(Buffer.from(inset)).resize(512, 512).png().toBuffer();
await writeFile(path.join(out, "icon-512-maskable.png"), maskable);
console.log("icon-512-maskable.png");

// The header shows the mark on the page's own background, so it stays SVG.
await writeFile(path.join(out, "mark.svg"), mark);
console.log("mark.svg");
