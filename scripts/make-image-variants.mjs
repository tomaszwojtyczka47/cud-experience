#!/usr/bin/env node
/*
 * Builds the responsive WebP files used in <picture srcset="..."> (no build
 * step is needed for the site itself; run this only when a photo is added or
 * replaced).
 *
 *   npm install sharp            (anywhere outside the repo, or globally)
 *   node scripts/make-image-variants.mjs [quality]
 *
 * For every assets/images/NAME.jpg (the high-quality source) it writes
 *   NAME-480.webp, NAME-720.webp, NAME-1080.webp, NAME-1600.webp, NAME-2000.webp
 * (only widths clearly below the original) and NAME.webp at full size.
 * Hero photos (names containing "hero") use 640 / 828 / 1280 / 1920 instead.
 * Then list the files in the page's srcset with matching w descriptors and set
 * a sizes attribute that says how wide the photo really is on screen.
 */
import sharp from 'sharp';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../assets/images');
const quality = Number(process.argv[2] || 70);
const ladder = (width, hero) =>
  (hero ? [640, 828, 1280, 1920] : [480, 720, 1080, 1600, 2000]).filter((w) => w < width * (hero ? 0.92 : 0.85));
const isVariant = /-(480|640|720|800|828|1080|1200|1280|1600|1920|2000)\.jpg$/;

for (const jpg of fs.readdirSync(dir).filter((f) => f.endsWith('.jpg') && !isVariant.test(f))) {
  const name = jpg.replace(/\.jpg$/, '');
  const { width } = await sharp(path.join(dir, jpg)).metadata();
  const targets = [...ladder(width, /hero/.test(name)).map((w) => [`${name}-${w}.webp`, w]), [`${name}.webp`, width]];
  for (const [file, w] of targets) {
    await sharp(path.join(dir, jpg))
      .resize({ width: w, withoutEnlargement: true })
      .webp({ quality, effort: 6, smartSubsample: true })
      .toFile(path.join(dir, file));
    console.log(file);
  }
}
