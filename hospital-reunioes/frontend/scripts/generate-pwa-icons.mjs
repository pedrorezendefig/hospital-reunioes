import sharp from "sharp";
import { mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const SOURCE = resolve(
  __dirname,
  "../../backend/app/static/images/logo_hospital.png"
);
const OUT = resolve(__dirname, "../public/icons");

const THEME_COLOR = { r: 43, g: 46, b: 126, alpha: 1 };
const WHITE = { r: 255, g: 255, b: 255, alpha: 1 };

async function ensureOutDir() {
  await mkdir(OUT, { recursive: true });
}

async function logoBuffer(size) {
  return await sharp(SOURCE)
    .resize(size, size, {
      fit: "contain",
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .png()
    .toBuffer();
}

async function makeStandardIcon(size, fileName) {
  const padding = Math.round(size * 0.1);
  const inner = size - 2 * padding;
  const logo = await logoBuffer(inner);
  await sharp({
    create: { width: size, height: size, channels: 4, background: WHITE },
  })
    .composite([{ input: logo, gravity: "center" }])
    .png()
    .toFile(resolve(OUT, fileName));
  console.log(`OK ${fileName} (${size}x${size}) standard`);
}

async function makeMaskableIcon(size, fileName) {
  const safeArea = Math.round(size * 0.6);
  const logo = await logoBuffer(safeArea);
  await sharp({
    create: { width: size, height: size, channels: 4, background: THEME_COLOR },
  })
    .composite([{ input: logo, gravity: "center" }])
    .png()
    .toFile(resolve(OUT, fileName));
  console.log(`OK ${fileName} (${size}x${size}) maskable`);
}

async function makeAppleTouchIcon() {
  const inner = 160;
  const logo = await logoBuffer(inner);
  await sharp({
    create: { width: 180, height: 180, channels: 4, background: WHITE },
  })
    .composite([{ input: logo, gravity: "center" }])
    .png()
    .toFile(resolve(OUT, "apple-touch-icon.png"));
  console.log("OK apple-touch-icon.png (180x180)");
}

async function makeFavicons() {
  for (const size of [16, 32, 48]) {
    const inner = Math.round(size * 0.85);
    const logo = await logoBuffer(inner);
    await sharp({
      create: { width: size, height: size, channels: 4, background: WHITE },
    })
      .composite([{ input: logo, gravity: "center" }])
      .png()
      .toFile(resolve(OUT, `favicon-${size}.png`));
    console.log(`OK favicon-${size}.png`);
  }
}

async function main() {
  await ensureOutDir();
  await makeStandardIcon(192, "icon-192.png");
  await makeStandardIcon(512, "icon-512.png");
  await makeMaskableIcon(192, "icon-maskable-192.png");
  await makeMaskableIcon(512, "icon-maskable-512.png");
  await makeAppleTouchIcon();
  await makeFavicons();
  console.log("\nIcones gerados em:", OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
