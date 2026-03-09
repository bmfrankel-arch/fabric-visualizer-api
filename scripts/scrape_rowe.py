#!/usr/bin/env python3
"""
Scrape Rowe Furniture / Robin Bruce product catalog from rff-portal-prod.azurewebsites.net.

Data source: Sitemap → individual product page scraping.
The main site rowefurniture.com redirects to crlaine.com, so we use the Azure backend directly.

Usage:
    python scripts/scrape_rowe.py

Output:
    backend/app/rowe_catalog.json
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import html as html_mod
import json
import re
import random
import time
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing beautifulsoup4 + lxml...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "lxml"])
    from bs4 import BeautifulSoup


BASE_URL = "https://rff-portal-prod.azurewebsites.net"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
OUTPUT_PATH = Path(__file__).parent.parent / "backend" / "app" / "rowe_catalog.json"

# Concurrency control
SEMAPHORE_LIMIT = 5
DELAY_BETWEEN_REQUESTS = 0.2

# ── Furniture type classification ──────────────────────────────────

TYPE_KEYWORDS = [
    ("swivel recliner", "Swivel Recliner"),
    ("manual recliner", "Recliner"),
    ("power recliner", "Recliner"),
    ("swivel glider", "Swivel Glider"),
    ("swivel chair", "Swivel Chair"),
    ("swivel", "Swivel Chair"),
    ("glider", "Glider"),
    ("recliner", "Recliner"),
    ("sectional", "Sectional"),
    ("sleeper", "Sleeper"),
    ("sofa", "Sofa"),
    ("loveseat", "Loveseat"),
    ("settee", "Settee"),
    ("chaise", "Chaise"),
    ("ottoman", "Ottoman"),
    ("bench", "Bench"),
    ("chair", "Chair"),
    ("daybed", "Daybed"),
    ("bed", "Bed"),
]

# Exclude non-upholstered items and non-furniture
EXCLUDE_KEYWORDS = [
    "table", "desk", "mirror", "shelf", "bookcase", "nightstand",
    "dresser", "chest", "sideboard", "stool", "credenza", "console",
    "pillow", "throw", "lamp", "rug",
]

# Sectional component patterns to exclude (we only want complete pieces)
COMPONENT_PATTERNS = [
    "left-arm", "right-arm", "armless-chair", "armless-loveseat",
    "corner-", "large-armless", "small-armless", "bumper",
    "left-seated", "right-seated", "armless-sofa",
    "left-chaise", "right-chaise",
    "left-return", "right-return",
]

# Known category/non-product slugs to skip
CATEGORY_SLUGS = {
    "", "search", "contactus", "express-delivery", "express-chair",
    "express-sofa", "express-slip", "express-sectional", "express-ottoman",
    "rowe-custom", "custom-sectionals", "samples", "fabrics", "leathers",
    "married-fabric-styles", "collaborations", "paul-delaisse-x-rowe",
    "all-products", "living-room", "sofas-sectionals", "custom-sofas-couches",
    "sleeper-sofa-beds", "chaise-sofas", "loveseat-sofas",
    "slipcovered-sofa-couches", "serenity-sleeper-sofa-beds",
    "custom-sectional", "modular-sectionals", "slipcovered-sectionals",
    "upholstered-sectionals", "sleeper-sectionals-beds",
    "chairs-ottomans", "custom-chairs", "accent-chairs",
    "swivel-chairs-gliders", "slipcovered-chairs", "reclining-chairs",
    "custom-ottomans", "upholstered-ottomans", "slipcovered-ottomans",
    "leather-ottomans-2", "custom-ottomans-3", "bench-ottomans",
    "castered-ottomans", "recliners-2", "sleepers", "storage-ottomans",
    "glider-swivel-chairs-2", "bedroom", "custom-beds", "daybeds",
    "chaise-chairs", "bedroom-bench", "dining-room", "dining-tables",
    "chests", "dining-chairs-banquettes", "sideboards", "stools",
    "office", "desks", "office-chairs", "storage", "special-programs",
    "thread-form", "bespoke-leather", "comfort-and-craft", "custom-pillows",
    "serenity-sleep-2", "storage-works-2", "my-style-i", "my-style-ii",
    "custom-ottoman", "rowe", "robin-bruce", "storage-works",
    "spot-end-tables", "cocktail-tables", "credenza-console-tables",
    "nightstands", "dining-chairs", "rowe-rewards", "kindred-2", "nova-2",
}


def classify_type(slug: str, name: str) -> str | None:
    """Classify furniture type from slug and product name. Returns None if excluded."""
    text = f"{slug} {name}".lower()

    # Check exclusions first
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return None

    # Check type keywords (order matters: specific before general)
    for kw, type_name in TYPE_KEYWORDS:
        if kw in text:
            return type_name

    return None


def extract_collection(name: str, furniture_type: str) -> str:
    """Extract collection name from product name by removing the type suffix."""
    collection = name

    # Strip leading dimensions like '105" x 103"' or '75"'
    collection = re.sub(r'^\d+["\u201d]?\s*(x\s*\d+["\u201d]?\s*)?', "", collection).strip()

    # Strip leading "Quick Ship" prefix
    collection = re.sub(r"^Quick\s+Ship\s+", "", collection, flags=re.IGNORECASE).strip()

    # Remove the type keyword and everything after it
    for kw, _ in TYPE_KEYWORDS:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        if pattern.search(collection):
            collection = pattern.split(collection)[0].strip()
            break

    # Strip common qualifiers from what remains
    for suffix in ["Leather", "Slip", "Slipcovered", "Quick Ship",
                   "Everyday Denim", "Manual", "Power", "Large", "Small",
                   "2 Piece", "3 Piece", "4 Piece", "2-Piece", "3-Piece",
                   "Gaming", "Bespoke Leather", "Bespoke",
                   "Built to Floor", "To Floor", "Accent",
                   "Upholstered to the Floor",
                   "Queen Serenity", "Serenity", "Slipcovered Serenity Sleeper",
                   "w/ Glider Option"]:
        collection = re.sub(rf"\s*{re.escape(suffix)}\s*$", "", collection, flags=re.IGNORECASE)
        collection = re.sub(rf"^\s*{re.escape(suffix)}\s+", "", collection, flags=re.IGNORECASE)

    # Remove trailing dimensions like '85"' or '45" x 28"'
    collection = re.sub(r'\s+\d+["\u201d]?(\s*x\s*\d+["\u201d]?)?\s*$', "", collection)
    # Remove trailing plain numbers
    collection = re.sub(r"\s+\d+\s*$", "", collection)

    # Only remove shape words (Rectangle, Round, Octagon) when they appear
    # alongside dimension numbers (not as part of collection names like "Times Square")
    collection = re.sub(r"\s+(Rectangle|Round|Octagon)\s*$", "", collection, flags=re.IGNORECASE)
    collection = re.sub(r"^(Rectangle|Round|Octagon)\s+", "", collection, flags=re.IGNORECASE)

    # Remove descriptors after dash like " - Antiqued Moss Velvet"
    collection = re.sub(r"\s*-\s+.*$", "", collection)

    # Remove parenthetical like "(Bench Cushion)"
    collection = re.sub(r"\s*\(.*?\)\s*$", "", collection)

    collection = collection.strip().strip("-").strip()

    # If empty after stripping, use the first word of the original name
    if not collection:
        words = name.split()
        collection = words[0] if words else "Unknown"

    return collection


def is_component_slug(slug: str) -> bool:
    """Check if slug represents a sectional component rather than a complete piece."""
    slug_lower = slug.lower()
    for pattern in COMPONENT_PATTERNS:
        if pattern in slug_lower:
            return True
    return False


def is_fabric_code(slug: str) -> bool:
    """Check if slug looks like a fabric sample code (e.g. 'kl248-50', '60879-31', '123cr-27')."""
    # Pure numeric with optional hyphen
    if re.match(r"^\d+(-\d+)?$", slug):
        return True
    # Alphanumeric codes like kl248-50, sw102-52, dl104-94, 123cr-27
    if re.match(r"^[a-z]{0,3}\d{2,}[a-z]{0,2}-\d{1,3}$", slug, re.IGNORECASE):
        return True
    return False


async def fetch_sitemap(client: httpx.AsyncClient) -> list[str]:
    """Fetch and parse the sitemap to get all product-candidate URLs."""
    print(f"Fetching sitemap: {SITEMAP_URL}")
    r = await client.get(SITEMAP_URL)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
    print(f"  Total URLs in sitemap: {len(urls)}")

    # Filter to candidate product slugs
    candidates = []
    for url in urls:
        slug = url.rstrip("/").split("/")[-1]

        # Skip known categories
        if slug in CATEGORY_SLUGS:
            continue

        # Skip the base domain entry
        if "azurewebsites.net" in slug:
            continue

        # Skip fabric codes
        if is_fabric_code(slug):
            continue

        # Must contain at least one letter (not pure numbers)
        if not re.search(r"[a-zA-Z]", slug):
            continue

        # Must contain a hyphen (product names are hyphenated like bruges-sofa)
        if "-" not in slug:
            continue

        # Skip sectional components
        if is_component_slug(slug):
            continue

        candidates.append(slug)

    print(f"  Candidate product slugs after filtering: {len(candidates)}")
    return candidates


async def fetch_product_page(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    slug: str,
    index: int,
    total: int,
) -> dict | None:
    """Fetch a single product page and extract catalog data. Returns None if not a valid product."""
    async with semaphore:
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
        url = f"{BASE_URL}/{slug}"
        try:
            r = await client.get(url, follow_redirects=True)
            if r.status_code != 200:
                return None
        except Exception as e:
            print(f"  [{index}/{total}] ERROR fetching {slug}: {e}")
            return None

        html = r.text

        # Must have var obj= to be a real product page (not a category)
        if "var obj=" not in html:
            return None

        # ── Extract product name ──
        name = None
        m = re.search(r'<span class="mobileTitleSpan">(.*?)</span>', html)
        if m:
            name = m.group(1).strip()
        if not name:
            m = re.search(r"<h1[^>]*>(.*?)</h1>", html)
            if m:
                name = m.group(1).strip()
        if not name:
            return None

        # Decode HTML entities (e.g. &quot; &#x201D; &amp; &#xA0;)
        name = html_mod.unescape(name)
        # Normalize unicode whitespace to regular space
        name = re.sub(r"\s+", " ", name).strip()

        # ── Classify type ──
        furniture_type = classify_type(slug, name)
        if not furniture_type:
            return None

        # ── Extract SKU from var obj ──
        sku = ""
        m = re.search(r'Sku:"([^"]+)"', html)
        if m:
            sku = m.group(1)

        # ── Extract main image URL ──
        # Prefer the FullSizeImageUrl from DefaultPictureModel (highest resolution)
        image_url = ""
        m = re.search(r'DefaultPictureModel:\{[^}]*FullSizeImageUrl:"(https://rffblob[^"]+)"', html)
        if m:
            image_url = m.group(1)
        else:
            # Fallback: 1170px version
            m = re.search(r'DefaultPictureModel:\{[^}]*ImageUrl:"(https://rffblob[^"]+)"', html)
            if m:
                image_url = m.group(1)
        if not image_url:
            # Last resort: any rffblob image
            m = re.search(r'(https://rffblob\.blob\.core\.windows\.net/[^"\']+\.jpe?g)', html)
            if m:
                image_url = m.group(1)

        if not image_url:
            return None

        # ── Extract manufacturer/brand ──
        brand = "Rowe"
        m = re.search(r'ProductManufacturers:\[\{Name:"([^"]+)"', html)
        if m:
            mfr = m.group(1)
            if "robin" in mfr.lower():
                brand = "Robin Bruce"
            elif "rowe" in mfr.lower():
                brand = "Rowe"
            else:
                brand = mfr

        # ── Determine material ──
        material = "Fabric"
        if "leather" in slug.lower() or "leather" in name.lower():
            material = "Leather"

        # ── Extract collection ──
        collection = extract_collection(name, furniture_type)

        # ── Build catalog entry ──
        item = {
            "name": name,
            "sku": sku,
            "price": 0,
            "compare_at_price": 0,
            "on_sale": False,
            "collection": collection,
            "color": "As Shown",
            "url": url,
            "image_url": image_url,
            "category": "Living",
            "type": furniture_type,
            "brand": brand,
            "material": material,
        }

        if index % 50 == 0 or index == total:
            print(f"  [{index}/{total}] {name} ({furniture_type}) - {brand}")

        return item


async def validate_images(items: list[dict], sample_size: int = 20) -> None:
    """Validate a random sample of image URLs."""
    print(f"\nValidating {sample_size} random image URLs...")
    sample = random.sample(items, min(sample_size, len(items)))

    valid = 0
    broken = 0

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for item in sample:
            try:
                r = await client.head(item["image_url"])
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and "image" in ct:
                    valid += 1
                else:
                    # Try GET as fallback (some CDNs block HEAD)
                    r2 = await client.get(item["image_url"])
                    ct2 = r2.headers.get("content-type", "")
                    if r2.status_code == 200 and "image" in ct2:
                        valid += 1
                    else:
                        broken += 1
                        print(f"  BROKEN: {item['name']} -> {r.status_code} {ct}")
            except Exception as e:
                broken += 1
                print(f"  ERROR: {item['name']} -> {e}")

    print(f"  Image validation: {valid}/{valid + broken} OK ({broken} broken)")


async def main():
    start_time = time.time()

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        # Step 1: Get candidate slugs from sitemap
        slugs = await fetch_sitemap(client)

        # Step 2: Fetch each product page
        semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        total = len(slugs)
        print(f"\nScraping {total} candidate product pages (semaphore={SEMAPHORE_LIMIT})...")
        print(f"  This will take ~{total * DELAY_BETWEEN_REQUESTS / SEMAPHORE_LIMIT:.0f} seconds...\n")

        tasks = [
            fetch_product_page(client, semaphore, slug, i + 1, total)
            for i, slug in enumerate(slugs)
        ]
        results = await asyncio.gather(*tasks)

    # Filter out None results
    items = [r for r in results if r is not None]
    print(f"\nExtracted {len(items)} valid furniture items from {total} candidates")

    # Deduplicate by SKU (keep first occurrence)
    seen_skus = set()
    deduped = []
    for item in items:
        key = item["sku"] if item["sku"] else item["url"]
        if key not in seen_skus:
            seen_skus.add(key)
            deduped.append(item)
    if len(deduped) < len(items):
        print(f"  Deduplicated: {len(items)} -> {len(deduped)} (removed {len(items) - len(deduped)} dupes)")
    items = deduped

    # Sort by type, then name
    items.sort(key=lambda x: (x["type"], x["name"]))

    # Validate images
    await validate_images(items)

    # Save to JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(items)} items to {OUTPUT_PATH}")

    # Print summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"ROWE FURNITURE CATALOG SUMMARY")
    print(f"{'='*60}")
    print(f"Total items: {len(items)}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print()

    # Type breakdown
    type_counts = {}
    for item in items:
        t = item["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print("Type breakdown:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:25s} {c:4d}")

    # Brand breakdown
    brand_counts = {}
    for item in items:
        b = item["brand"]
        brand_counts[b] = brand_counts.get(b, 0) + 1
    print("\nBrand breakdown:")
    for b, c in sorted(brand_counts.items(), key=lambda x: -x[1]):
        print(f"  {b:25s} {c:4d}")

    # Material breakdown
    material_counts = {}
    for item in items:
        m = item["material"]
        material_counts[m] = material_counts.get(m, 0) + 1
    print("\nMaterial breakdown:")
    for m, c in sorted(material_counts.items(), key=lambda x: -x[1]):
        print(f"  {m:25s} {c:4d}")

    # Sample items
    print(f"\nSample items:")
    for item in items[:5]:
        print(f"  {item['name']:40s} | {item['type']:20s} | {item['brand']:15s} | {item['sku']}")

    print(f"\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
