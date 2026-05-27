"""
Sync backend/app/dorell_fabrics.json from the dorell-fabrics-cdn photo host.

This is the canonical successor to sync_dorell_fabrics.py (which scanned local
image directories). All Dorell apps now consume from the same shared photo host
(https://dorell-fabrics-cdn.netlify.app); this script pulls its library.json
and reshapes it into the JSON shape this backend expects.

Usage:
  python sync_dorell_fabrics_from_photo_host.py            # dry run (preview)
  python sync_dorell_fabrics_from_photo_host.py --apply    # write JSON

After --apply, commit and push backend/app/dorell_fabrics.json to GitHub;
Vercel will auto-deploy the updated visualizer.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

PHOTO_HOST_URL = "https://dorell-fabrics-cdn.netlify.app/library.json"
SCRIPT_DIR = Path(__file__).parent
JSON_PATH = SCRIPT_DIR.parent / "backend" / "app" / "dorell_fabrics.json"


def fetch_library(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"Photo host returned {r.status}")
        return json.loads(r.read())


def shape_record(rec: dict) -> dict | None:
    """Convert a photo-host record to the shape backend/app/dorell_fabrics.json expects.

    Photo host shape: {name, slug, description, content, durability, direction,
                       backing, cleanCode, coo, subclass, icons, stainResistance,
                       heroImage, colors: [{name, filename, ...}]}
    Backend shape:    {name, slug, description, content, durability, direction,
                       cleanCode, images: [<filename>...]}
    """
    images = [
        c["filename"]
        for c in (rec.get("colors") or [])
        if c and c.get("filename") and "waterfall" not in c["filename"].lower()
    ]
    if not images:
        return None
    return {
        "name": rec.get("name") or rec.get("slug"),
        "slug": rec["slug"],
        "description": rec.get("description") or "",
        "content": rec.get("content") or "TBA",
        "durability": rec.get("durability") or "TBA",
        "direction": rec.get("direction") or "TBA",
        "cleanCode": rec.get("cleanCode") or "TBA",
        "images": images,
    }


def sync(apply: bool):
    print(f"Source: {PHOTO_HOST_URL}")
    print(f"Target: {JSON_PATH}")
    print()
    print("Fetching photo host library.json...")
    raw = fetch_library(PHOTO_HOST_URL)
    print(f"  -> {len(raw)} records received")
    new_data = [r for r in (shape_record(rec) for rec in raw) if r]
    new_data.sort(key=lambda p: p["slug"])
    print(f"  -> {len(new_data)} usable records (skipped {len(raw) - len(new_data)} with no images)")

    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            current = json.load(f)
        cur_slugs = {p["slug"] for p in current}
        new_slugs = {p["slug"] for p in new_data}
        added = sorted(new_slugs - cur_slugs)
        removed = sorted(cur_slugs - new_slugs)
        # Count images delta (only for slugs in both)
        cur_by_slug = {p["slug"]: p for p in current}
        image_delta = 0
        for p in new_data:
            if p["slug"] in cur_by_slug:
                old_imgs = set(cur_by_slug[p["slug"]].get("images", []))
                new_imgs = set(p["images"])
                image_delta += len(new_imgs - old_imgs) - len(old_imgs - new_imgs)
        print()
        print(f"Current JSON: {len(current)} records")
        print(f"After sync:   {len(new_data)} records ({len(added)} added, {len(removed)} removed)")
        print(f"Net image count delta: {image_delta:+d}")
        if added:
            print(f"  + new slugs (first 15): {added[:15]}")
        if removed:
            print(f"  - removed slugs (first 15): {removed[:15]}")
    else:
        print(f"Note: target does not exist yet — will create.")

    if not apply:
        print("\n--- DRY RUN --- Run with --apply to write changes.")
        return

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nWrote {len(new_data)} patterns to {JSON_PATH}")
    print("Next: commit + push to GitHub. Vercel will auto-deploy.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry run)")
    args = parser.parse_args()
    try:
        sync(args.apply)
    except urllib.error.URLError as e:
        print(f"ERROR: Could not reach photo host: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
