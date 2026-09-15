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
// the dollar sign on one side, "GaW" near the bottom. Rebuild it with the ground
// left full-bleed and only the drawing scaled to 80%, so everything lands inside
// the safe zone and the ring that gets cropped is the same silver as the rest --
// nesting the whole logo instead would restart its gradient and leave a seam.
const source = logo.toString("utf8");
const defs = source.match(/<defs>[\s\S]*?<\/defs>/)[0];
const ground = source.match(/<rect x="0" y="0"[^>]*fill="url\(#silver\)"\/>/)[0];
const rules = source.match(/<g stroke="#FFFFFF"[\s\S]*?<\/g>/)[0];
const drawing = source.slice(source.indexOf(rules) + rules.length, source.lastIndexOf("</svg>"));
const inset = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 380 380">
${defs}${ground}${rules}
<g transform="translate(38 38) scale(0.8)">${drawing}</g>
</svg>`;
const maskable = await sharp(Buffer.from(inset)).resize(512, 512).png().toBuffer();
await writeFile(path.join(out, "icon-512-maskable.png"), maskable);
console.log("icon-512-maskable.png");

// The favicon gets a tab square 16 pixels wide. The whole logo at that size is a
// grey smudge, so it is cropped to the part that carries the identity -- the bird
// on its perch, and the dollar sign -- on the same silver ground, with the "GaW"
// and the ruled lines dropped. Same artwork, close enough to read.
const crop = "76 100 258 258";
const favicon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${crop}" role="img" aria-label="Gimme a W">
${defs}<rect x="76" y="100" width="258" height="258" fill="url(#silver)"/>${drawing.replace(/<text[\s\S]*?<\/text>/g, "")}
</svg>
`;
await writeFile(path.join(root, "src/app/icon.svg"), favicon);
console.log("src/app/icon.svg");

// The header shows the mark on the page's own background, so it stays SVG.
await writeFile(path.join(out, "mark.svg"), mark);
console.log("mark.svg");
