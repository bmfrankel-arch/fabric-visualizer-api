"""
Sync dorell_fabrics.json with the image directories.

Scans the pattern library image folders and:
  1. Adds new patterns that don't exist in the JSON yet
  2. Adds new colorway images to existing patterns
  3. Reports what changed

Usage:
  python sync_dorell_fabrics.py                  # Dry run (preview changes)
  python sync_dorell_fabrics.py --apply          # Write changes to JSON
  python sync_dorell_fabrics.py --image-dir PATH # Custom image directory
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend" / "app"
JSON_PATH = BACKEND_DIR / "dorell_fabrics.json"

DEFAULT_IMAGE_DIR = Path(
    os.environ.get(
        "DORELL_IMAGE_DIR",
        os.path.expanduser(
            "~/OneDrive - Dorell Fabrics Co/Design/2. New Folders Made - Brian"
            "/00. dorell-full-catalog/images"
        ),
    )
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def scan_image_dirs(image_dir: Path) -> dict[str, list[str]]:
    """Return {slug: [image_filenames]} from the image directory."""
    result = {}
    for entry in sorted(os.listdir(image_dir)):
        full_path = image_dir / entry
        if not full_path.is_dir():
            continue
        images = sorted(
            f
            for f in os.listdir(full_path)
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        )
        if images:
            result[entry] = images
    return result


def guess_pattern_name(slug: str) -> str:
    """Convert slug to a display name. e.g. 'sun-alley' -> 'Sun Alley'."""
    return slug.replace("-", " ").title()


def make_new_entry(slug: str, images: list[str]) -> dict:
    """Create a new fabric entry with sensible defaults."""
    return {
        "name": guess_pattern_name(slug),
        "slug": slug,
        "description": "",
        "content": "TBA",
        "durability": "TBA",
        "direction": "TBA",
        "cleanCode": "TBA",
        "images": images,
    }


def sync(image_dir: Path, json_path: Path, apply: bool):
    print(f"Image directory: {image_dir}")
    print(f"JSON file:       {json_path}")
    print()

    if not image_dir.exists():
        print(f"ERROR: Image directory not found: {image_dir}", file=sys.stderr)
        sys.exit(1)

    if not json_path.exists():
        print(f"ERROR: JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    # Load current state
    data = load_json(json_path)
    slug_index = {p["slug"]: p for p in data}
    disk = scan_image_dirs(image_dir)

    new_patterns = []
    updated_patterns = []

    for slug, disk_images in disk.items():
        if slug not in slug_index:
            # Brand new pattern
            entry = make_new_entry(slug, disk_images)
            new_patterns.append(entry)
        else:
            # Existing pattern - check for new images
            existing = set(slug_index[slug].get("images", []))
            new_imgs = [img for img in disk_images if img not in existing]
            if new_imgs:
                updated_patterns.append((slug, new_imgs))

    # Report
    print(f"Current JSON patterns: {len(data)}")
    print(f"Image directories:     {len(disk)}")
    print()

    if new_patterns:
        print(f"NEW PATTERNS TO ADD: {len(new_patterns)}")
        for p in new_patterns:
            print(f"  + {p['slug']}/ ({len(p['images'])} images)")
    else:
        print("No new patterns to add.")

    print()

    if updated_patterns:
        total_new_imgs = sum(len(imgs) for _, imgs in updated_patterns)
        print(f"EXISTING PATTERNS WITH NEW IMAGES: {len(updated_patterns)} ({total_new_imgs} images)")
        for slug, new_imgs in updated_patterns:
            print(f"  ~ {slug}: +{len(new_imgs)} -> {new_imgs[:3]}{'...' if len(new_imgs) > 3 else ''}")
    else:
        print("No new images for existing patterns.")

    if not new_patterns and not updated_patterns:
        print("\nEverything is already in sync!")
        return

    if not apply:
        print("\n--- DRY RUN --- Run with --apply to write changes.")
        return

    # Apply changes
    for p in new_patterns:
        data.append(p)

    for slug, new_imgs in updated_patterns:
        slug_index[slug]["images"].extend(new_imgs)
        # Keep images sorted
        slug_index[slug]["images"].sort()

    # Sort all patterns by slug for consistency
    data.sort(key=lambda p: p["slug"])

    save_json(json_path, data)
    print(f"\nWrote {len(data)} patterns to {json_path}")
    print(f"  Added {len(new_patterns)} new patterns")
    print(f"  Updated {len(updated_patterns)} existing patterns with new images")


def main():
    parser = argparse.ArgumentParser(description="Sync dorell_fabrics.json with image directories")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry run)")
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR, help="Path to image directories")
    parser.add_argument("--json", type=Path, default=JSON_PATH, help="Path to dorell_fabrics.json")
    args = parser.parse_args()

    sync(args.image_dir, args.json, args.apply)


if __name__ == "__main__":
    main()
