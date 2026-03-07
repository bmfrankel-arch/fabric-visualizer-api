#!/usr/bin/env node
// ============================================================
//  Dorell Fabrics — Yard-Cut Image Batch Generator
//  Reads all fabric patterns from dorell_fabrics.json, downloads
//  swatch images from Netlify CDN, then uses OpenAI gpt-image-1
//  to generate properly-scaled yard-cut images for each colorway.
//
//  Usage:
//    node generate-dorell-yard-cuts.js                  # full run
//    node generate-dorell-yard-cuts.js --test 5         # test with 5 colorways
//    node generate-dorell-yard-cuts.js --retry          # re-run only failed items
//    node generate-dorell-yard-cuts.js --dry-run        # list what would be generated
//    node generate-dorell-yard-cuts.js --pattern echo   # only one pattern
//
//  Environment variables (required):
//    OPENAI_API_KEY  — OpenAI API key
//
//  Adapted from the proven FabricResource generate-yard-cuts.js
//  (1,499 fabrics generated successfully on 2026-03-03).
// ============================================================

const fs   = require('fs');
const path = require('path');

// ─── Load .env file (no npm dependency) ─────────────────────────────────────
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf8');
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let val = trimmed.slice(eqIdx + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (!process.env[key]) process.env[key] = val;
  }
}

// ─── Configuration ──────────────────────────────────────────────────────────
const DORELL_JSON = path.join(__dirname, '..', 'backend', 'app', 'dorell_fabrics.json');
const CDN_BASE    = 'https://dorellfabrics-patternlibrary.netlify.app/images';

const CONCURRENCY = 3;        // Max simultaneous OpenAI requests
const BATCH_DELAY = 2000;     // ms between batches
const MAX_RETRIES = 3;        // Retries per image on failure
const IMAGE_SIZE  = '1536x1024';
const DEFAULT_WIDTH = 54;     // inches — standard upholstery bolt width

const OUT_DIR      = path.join(__dirname, '..', 'output', 'yard-cuts');
const MANIFEST     = path.join(__dirname, '..', 'output', 'manifest.json');
const ERROR_LOG    = path.join(__dirname, '..', 'output', 'yard-cuts-errors.json');
const PROGRESS_LOG = path.join(__dirname, '..', 'output', 'progress.log');

// ─── Parse CLI args ─────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const TEST_LIMIT   = args.includes('--test') ? parseInt(args[args.indexOf('--test') + 1] || '5', 10) : 0;
const RETRY_ONLY   = args.includes('--retry');
const DRY_RUN      = args.includes('--dry-run');
const PATTERN_ONLY = args.includes('--pattern') ? args[args.indexOf('--pattern') + 1] : '';

// ─── Ensure output directories exist early (before log() is called) ─────────
const outputDir = path.dirname(MANIFEST);
if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });
if (!fs.existsSync(OUT_DIR))   fs.mkdirSync(OUT_DIR, { recursive: true });

// ─── Helpers ────────────────────────────────────────────────────────────────
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  fs.appendFileSync(PROGRESS_LOG, line + '\n');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function loadManifest() {
  try { return JSON.parse(fs.readFileSync(MANIFEST, 'utf8')); }
  catch { return {}; }
}

function saveManifest(manifest) {
  fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
}

function loadErrors() {
  try { return JSON.parse(fs.readFileSync(ERROR_LOG, 'utf8')); }
  catch { return {}; }
}

function saveErrors(errors) {
  fs.writeFileSync(ERROR_LOG, JSON.stringify(errors, null, 2));
}

// ─── Load Dorell Fabrics (replaces WooCommerce API) ─────────────────────────
function loadDorellFabrics() {
  if (!fs.existsSync(DORELL_JSON)) {
    throw new Error(`Dorell fabric data not found: ${DORELL_JSON}`);
  }

  const raw = JSON.parse(fs.readFileSync(DORELL_JSON, 'utf8'));
  const items = [];

  for (const pattern of raw) {
    // If --pattern flag is set, only include matching pattern
    if (PATTERN_ONLY && pattern.slug !== PATTERN_ONLY) continue;

    for (const imgFile of (pattern.images || [])) {
      // Colorway key = filename without extension (e.g., "ace-bone")
      const colorway = imgFile.replace(/\.\w+$/, '');

      items.push({
        slug: pattern.slug,
        colorway,
        patternName: pattern.name,
        imageFile: imgFile,
        imageUrl: `${CDN_BASE}/${pattern.slug}/${imgFile}`,
        width: DEFAULT_WIDTH,
        direction: pattern.direction || '',
      });
    }
  }

  return items;
}

// ─── OpenAI Image Generation ────────────────────────────────────────────────
async function generateYardCut(item) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY environment variable required');

  // Fetch the swatch image from Netlify CDN
  const imgRes = await fetch(item.imageUrl);
  if (!imgRes.ok) throw new Error(`Failed to fetch image: ${imgRes.status} ${item.imageUrl}`);

  const contentType = imgRes.headers.get('content-type') || 'image/jpeg';
  const mimeType = contentType.split(';')[0].trim();
  const ext = mimeType === 'image/png' ? 'png' : 'jpg';
  const filename = `fabric.${ext}`;
  const imageBuffer = Buffer.from(await imgRes.arrayBuffer());

  // Build the yard-cut prompt (same proven prompt from window-treatment project)
  // Since dorell_fabrics.json has no repeat data, we use the standard 54" width
  // and let the AI determine the repeat from the swatch itself.
  const prompt = `Recreate how this fabric pattern looks in a full yard cut of fabric. Assume the fabric is ${item.width} inches wide and show the complete repeating pattern tiled accurately across the full fabric width and one yard (36 inches) of length. Maintain the exact colors, textures, and pattern details from the original image. Do not include any rulers, measurement markings, dimension labels, borders, or annotations — show only the fabric itself.`;

  // Build multipart/form-data (no npm dependencies)
  const boundary = '----YardCutBoundary' + Date.now().toString(36);

  function fieldPart(name, value) {
    return Buffer.from(
      '--' + boundary + '\r\n' +
      'Content-Disposition: form-data; name="' + name + '"\r\n\r\n' +
      value + '\r\n'
    );
  }

  function filePart(name, fname, type, data) {
    return Buffer.concat([
      Buffer.from(
        '--' + boundary + '\r\n' +
        'Content-Disposition: form-data; name="' + name + '"; filename="' + fname + '"\r\n' +
        'Content-Type: ' + type + '\r\n\r\n'
      ),
      data,
      Buffer.from('\r\n'),
    ]);
  }

  const formParts = [
    fieldPart('model', 'gpt-image-1'),
    fieldPart('prompt', prompt),
    fieldPart('n', '1'),
    fieldPart('size', IMAGE_SIZE),
    filePart('image[]', filename, mimeType, imageBuffer),
  ];
  formParts.push(Buffer.from('--' + boundary + '--\r\n'));
  const formBody = Buffer.concat(formParts);

  // Call OpenAI
  const startTime = Date.now();
  const res = await fetch('https://api.openai.com/v1/images/edits', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type': 'multipart/form-data; boundary=' + boundary,
    },
    body: formBody,
  });

  if (!res.ok) {
    const errBody = await res.text().catch(() => '');
    throw new Error(`OpenAI ${res.status}: ${errBody.slice(0, 300)}`);
  }

  const result = await res.json();
  const b64 = result?.data?.[0]?.b64_json;
  if (!b64) throw new Error('No image data in OpenAI response');

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  return { b64, elapsed };
}

// ─── Generate with retry logic ──────────────────────────────────────────────
async function generateWithRetry(item, attempt = 1) {
  try {
    return await generateYardCut(item);
  } catch (err) {
    if (attempt >= MAX_RETRIES) throw err;

    const delay = Math.pow(2, attempt) * 1000; // Exponential backoff: 2s, 4s, 8s
    log(`  Attempt ${attempt} failed for ${item.colorway}: ${err.message}. Retrying in ${delay/1000}s...`);
    await sleep(delay);
    return generateWithRetry(item, attempt + 1);
  }
}

// ─── Process a batch of colorways concurrently ──────────────────────────────
async function processBatch(batch, startIdx, totalCount, manifest, errors) {
  const promises = batch.map(async (item, i) => {
    const idx = startIdx + i + 1;

    // Output: yard-cuts/{slug}/{colorway}.png
    const slugDir = path.join(OUT_DIR, item.slug);
    if (!fs.existsSync(slugDir)) fs.mkdirSync(slugDir, { recursive: true });
    const outFile = path.join(slugDir, `${item.colorway}.png`);

    try {
      const { b64, elapsed } = await generateWithRetry(item);

      // Save the image
      const imgBuffer = Buffer.from(b64, 'base64');
      fs.writeFileSync(outFile, imgBuffer);

      // Update manifest (keyed by colorway, not pattern slug)
      manifest[item.colorway] = {
        file: `${item.slug}/${item.colorway}.png`,
        patternSlug: item.slug,
        patternName: item.patternName,
        colorway: item.colorway,
        sourceImage: item.imageFile,
        width: item.width,
        generatedAt: new Date().toISOString(),
      };

      // Remove from errors if it was there
      if (errors[item.colorway]) delete errors[item.colorway];

      const sizeKB = (imgBuffer.length / 1024).toFixed(0);
      log(`  [${idx}/${totalCount}] Generated ${item.slug}/${item.colorway}.png (${elapsed}s, ${sizeKB}KB)`);
    } catch (err) {
      errors[item.colorway] = {
        error: err.message,
        patternSlug: item.slug,
        imageUrl: item.imageUrl,
        width: item.width,
        failedAt: new Date().toISOString(),
      };
      log(`  [${idx}/${totalCount}] FAILED ${item.colorway}: ${err.message}`);
    }
  });

  await Promise.all(promises);
}

// ─── Main ───────────────────────────────────────────────────────────────────
async function main() {
  log('');
  log('===============================================================');
  log('  Dorell Fabrics — Yard-Cut Image Batch Generator');
  log('===============================================================');

  // (API key validated later — dry-run doesn't need it)

  // Load existing manifest and errors
  const manifest = loadManifest();
  const errors   = loadErrors();

  log(`Existing manifest entries: ${Object.keys(manifest).length}`);
  log(`Existing error entries: ${Object.keys(errors).length}`);
  if (PATTERN_ONLY) log(`Pattern filter: ${PATTERN_ONLY}`);

  // ── Load all Dorell fabric colorways ──────────────────────────────────────
  let allItems = [];

  if (RETRY_ONLY) {
    // Only re-run previously failed items
    const errorKeys = Object.keys(errors);
    if (errorKeys.length === 0) {
      log('No errors to retry! All done.');
      return;
    }
    log(`Retry mode: re-processing ${errorKeys.length} failed items`);

    // Rebuild item data from error entries + dorell_fabrics.json
    const allFabrics = loadDorellFabrics();
    const errorSet = new Set(errorKeys);
    allItems = allFabrics.filter(f => errorSet.has(f.colorway));
    log(`  Found ${allItems.length} of ${errorKeys.length} items in fabric data`);
  } else {
    allItems = loadDorellFabrics();
  }

  log(`Total colorways loaded: ${allItems.length}`);

  // ── Filter out already-generated items (resume-safe) ────────────────────
  const toGenerate = allItems.filter(item => {
    if (manifest[item.colorway]) {
      const outFile = path.join(OUT_DIR, manifest[item.colorway].file);
      if (fs.existsSync(outFile)) return false;
    }
    return true;
  });

  log(`Already generated: ${allItems.length - toGenerate.length}`);
  log(`Remaining to generate: ${toGenerate.length}`);

  // ── Apply test limit ────────────────────────────────────────────────────
  let queue = toGenerate;
  if (TEST_LIMIT > 0) {
    queue = toGenerate.slice(0, TEST_LIMIT);
    log(`TEST MODE: limiting to ${queue.length} items`);
  }

  // ── Dry run ─────────────────────────────────────────────────────────────
  if (DRY_RUN) {
    log('');
    log('DRY RUN — would generate these images:');
    queue.forEach((item, i) => {
      log(`  ${i + 1}. ${item.slug}/${item.colorway} — ${item.patternName} (W=${item.width}")`);
    });
    log('');
    log(`Total: ${queue.length} images`);
    log(`Estimated cost: $${(queue.length * 0.06).toFixed(2)} (@ ~$0.06/image)`);
    log(`Estimated time: ${Math.ceil(queue.length / CONCURRENCY * 22 / 60)} minutes`);
    return;
  }

  if (queue.length === 0) {
    log('Nothing to generate! All colorways already have yard-cut images.');
    saveManifest(manifest);
    return;
  }

  // Validate API key before actual generation
  if (!process.env.OPENAI_API_KEY) {
    console.error('ERROR: Set OPENAI_API_KEY environment variable');
    console.error('  Create scripts/.env with: OPENAI_API_KEY=sk-...');
    process.exit(1);
  }

  // ── Generate images in batches ──────────────────────────────────────────
  const startTime = Date.now();
  log('');
  log(`Starting generation of ${queue.length} images (${CONCURRENCY} concurrent)...`);
  log('');

  for (let i = 0; i < queue.length; i += CONCURRENCY) {
    const batch = queue.slice(i, i + CONCURRENCY);
    await processBatch(batch, i, queue.length, manifest, errors);

    // Save manifest and errors after each batch (crash-safe)
    saveManifest(manifest);
    saveErrors(errors);

    // Delay between batches (rate limiting)
    if (i + CONCURRENCY < queue.length) {
      await sleep(BATCH_DELAY);
    }
  }

  // ── Summary ─────────────────────────────────────────────────────────────
  const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
  const totalErrors = Object.keys(errors).length;
  const newSuccess = queue.length - totalErrors;

  log('');
  log('===============================================================');
  log(`  COMPLETE`);
  log(`  Generated: ${newSuccess} new images`);
  log(`  Errors: ${totalErrors}`);
  log(`  Time: ${elapsed} minutes`);
  log(`  Manifest total: ${Object.keys(manifest).length} entries`);
  if (totalErrors > 0) {
    log(`  Errors saved to: ${ERROR_LOG}`);
    log(`  Re-run with: node generate-dorell-yard-cuts.js --retry`);
  }
  log('===============================================================');
}

main().catch(err => {
  console.error('FATAL:', err);
  process.exit(1);
});
