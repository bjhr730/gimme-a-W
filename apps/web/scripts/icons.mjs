// Rasterize the bird mark into PWA icons. Run once: pnpm --filter web icons
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "..");
const svg = await readFile(path.resolve(root, "../../assets/logo/mark.svg"));
const out = path.join(root, "public");
await mkdir(out, { recursive: true });

// The mark is wide (1300x820). Icons are square: pad on a pitch-green ground,
// bird centered, with safe-zone margin so maskable icons don't clip the beak.
const ground = { r: 29, g: 122, b: 70, alpha: 1 };
for (const size of [192, 512]) {
  const inner = Math.round(size * 0.78);
  const bird = await sharp(svg).resize({ width: inner, fit: "inside" }).png().toBuffer();
  const meta = await sharp(bird).metadata();
  const png = await sharp({
    create: { width: size, height: size, channels: 4, background: ground },
  })
    .composite([
      {
        input: bird,
        left: Math.round((size - (meta.width ?? inner)) / 2),
        top: Math.round((size - (meta.height ?? inner)) / 2),
      },
    ])
    .png()
    .toBuffer();
  await writeFile(path.join(out, `icon-${size}.png`), png);
  console.log(`icon-${size}.png`);
}
await writeFile(path.join(out, "mark.svg"), svg);
console.log("mark.svg");
