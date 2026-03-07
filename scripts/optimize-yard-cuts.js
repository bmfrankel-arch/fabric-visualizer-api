#!/usr/bin/env node
// ============================================================
//  Dorell Fabrics — Yard-Cut Image Optimizer
//  Converts PNG yard-cut images to optimized WebP for faster
//  page loads and smaller Netlify deploys.
//
//  Usage:
//    node optimize-yard-cuts.js              # Convert all PNGs to WebP
//    node optimize-yard-cuts.js --quality 85 # Custom quality (default: 82)
//    node optimize-yard-cuts.js --keep-png   # Don't delete originals
//    node optimize-yard-cuts.js --dry-run    # Show what would be done
//
//  Requires: npm install sharp (one-time setup)
// ============================================================

const fs   = require('fs');
const path = require('path');

let sharp;
try {
  sharp = require('sharp');
} catch {
  console.error('ERROR: sharp is not installed.');
  console.error('Run: npm install sharp');
  process.exit(1);
}

const DIR = path.join(__dirname, '..', 'output', 'yard-cuts');
const MANIFEST = path.join(__dirname, '..', 'output', 'manifest.json');

// Parse CLI flags
const args = process.argv.slice(2);
const DRY_RUN  = args.includes('--dry-run');
const KEEP_PNG = args.includes('--keep-png');
const qualityIdx = args.indexOf('--quality');
const QUALITY = qualityIdx >= 0 ? parseInt(args[qualityIdx + 1], 10) : 82;

const CONCURRENT = 5;

// Recursively find all PNGs in the directory tree
function findPngs(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findPngs(fullPath));
    } else if (entry.name.endsWith('.png')) {
      results.push(fullPath);
    }
  }
  return results;
}

async function main() {
  console.log('===============================================================');
  console.log('  Dorell Fabrics — Yard-Cut Image Optimizer');
  console.log('===============================================================');
  console.log(`  Quality: ${QUALITY}  |  Keep PNGs: ${KEEP_PNG}  |  Dry Run: ${DRY_RUN}`);
  console.log();

  if (!fs.existsSync(DIR)) {
    console.log(`Output directory not found: ${DIR}`);
    console.log('Run generate-dorell-yard-cuts.js first.');
    return;
  }

  // Find all PNGs recursively (yard-cuts/{slug}/{colorway}.png)
  const pngs = findPngs(DIR);
  console.log(`Found ${pngs.length} PNG files to convert`);

  if (pngs.length === 0) {
    console.log('Nothing to do.');
    return;
  }

  // Calculate current total size
  let totalPngBytes = 0;
  pngs.forEach(f => { totalPngBytes += fs.statSync(f).size; });
  console.log(`Current PNG total: ${(totalPngBytes / 1024 / 1024).toFixed(1)} MB`);
  console.log();

  if (DRY_RUN) {
    console.log(`[DRY RUN] Would convert ${pngs.length} PNGs to WebP`);
    console.log(`Estimated WebP size: ~${(totalPngBytes * 0.4 / 1024 / 1024).toFixed(1)} MB (~60% savings)`);
    return;
  }

  let converted = 0;
  let errors = 0;
  let totalWebpBytes = 0;

  // Process in batches
  for (let i = 0; i < pngs.length; i += CONCURRENT) {
    const batch = pngs.slice(i, i + CONCURRENT);
    const promises = batch.map(async (pngPath) => {
      const webpPath = pngPath.replace(/\.png$/, '.webp');

      try {
        await sharp(pngPath)
          .webp({ quality: QUALITY, effort: 4 })
          .toFile(webpPath);

        const webpStat = fs.statSync(webpPath);
        const pngStat  = fs.statSync(pngPath);
        const savings  = ((1 - webpStat.size / pngStat.size) * 100).toFixed(0);
        totalWebpBytes += webpStat.size;

        if (!KEEP_PNG) {
          fs.unlinkSync(pngPath);
        }

        converted++;
        if (converted % 100 === 0 || converted === pngs.length) {
          const relPath = path.relative(DIR, webpPath);
          console.log(`  [${converted}/${pngs.length}] ${relPath} — ${savings}% smaller`);
        }
      } catch (err) {
        errors++;
        const relPath = path.relative(DIR, pngPath);
        console.error(`  FAILED ${relPath}: ${err.message}`);
      }
    });
    await Promise.all(promises);
  }

  console.log();
  console.log('===============================================================');
  console.log(`  COMPLETE — ${converted} converted, ${errors} errors`);
  console.log(`  PNG total:  ${(totalPngBytes / 1024 / 1024).toFixed(1)} MB`);
  console.log(`  WebP total: ${(totalWebpBytes / 1024 / 1024).toFixed(1)} MB`);
  console.log(`  Savings:    ${((1 - totalWebpBytes / totalPngBytes) * 100).toFixed(0)}%`);
  console.log('===============================================================');

  // Update manifest to reference .webp files instead of .png
  if (fs.existsSync(MANIFEST)) {
    const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
    let updated = 0;
    for (const key of Object.keys(manifest)) {
      if (manifest[key].file && manifest[key].file.endsWith('.png')) {
        manifest[key].file = manifest[key].file.replace(/\.png$/, '.webp');
        updated++;
      }
    }
    fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
    console.log(`  Manifest updated: ${updated} entries now point to .webp`);
  }
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
