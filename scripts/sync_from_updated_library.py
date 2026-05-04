"""Sync the dorell-full-catalog from the Updated Photography Library.

Normalizes photo names from the OneDrive library into the slug-color.jpg
convention used by the catalog and (optionally) updates dorell_fabrics.json.

Policy decisions baked in:
  - Strip "(Main)" and "-C0" / " C0" suffixes from folder names
  - Use the FULL folder name as the prefix to strip from filenames
  - For date-stamped re-shoots like "betty-carbon-(2024-06-11).jpg", keep the
    newest one as "betty-carbon.jpg"
  - Skip "(Incomplete)" folders and admin folders starting with digit+dot

Usage:
  python sync_from_updated_library.py                    # Dry run
  python sync_from_updated_library.py --copy-photos      # Copy photos into catalog
  python sync_from_updated_library.py --copy-photos --apply-json
                                                          # Plus update JSON
"""

import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

LIBRARY = Path(
    r"C:\Users\BrianFrankel\OneDrive - Dorell Fabrics Co\Design"
    r"\1. Updated Photography Library"
)
CATALOG = Path(
    r"C:\Users\BrianFrankel\OneDrive - Dorell Fabrics Co\Design"
    r"\2. New Folders Made - Brian\00. dorell-full-catalog\images"
)
JSON_PATH = Path(__file__).parent.parent / "backend" / "app" / "dorell_fabrics.json"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

DATE_SUFFIX_RE = re.compile(r"\s*\((\d{4}-\d{2}-\d{2})(?:[-_](\d+))?\)$")


def folder_to_slug(name: str) -> str:
    """Normalize a folder name into a slug.

    Strips '(Main)', '-C0', ' C0' suffixes per policy.
    Examples:
      'Anders-C0'       -> 'anders'
      'Audrina (Main)'  -> 'audrina'
      'Audrina-C0'      -> 'audrina'
      'Doro Suede'      -> 'doro-suede'
      'Fisher UV'       -> 'fisher-uv'
      'Adelina-UV'      -> 'adelina-uv'   (UV preserved)
    """
    s = name.strip()
    # Strip suffix variants of (Main) and C0
    s = re.sub(r"\s*\(Main\)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[-\s]C0\s*$", "", s, flags=re.IGNORECASE)
    s = s.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def file_to_color_part(folder_name: str, filename: str) -> str | None:
    """Strip folder-name prefix from filename to extract the color portion.

    Tries several candidate prefixes (original folder name, plus variants
    with (Main) and/or -C0 stripped) since files often use the base pattern
    name even when the folder has a suffix.

    Returns None if no usable color can be extracted.
    """
    stem = Path(filename).stem.strip()
    stem_norm = re.sub(r"\s+", " ", stem).lower()

    no_main = re.sub(r"\s*\(Main\)\s*$", "", folder_name, flags=re.IGNORECASE).strip()
    no_c0 = re.sub(r"[-\s]C0\s*$", "", folder_name, flags=re.IGNORECASE).strip()
    no_both = re.sub(r"[-\s]C0\s*$", "",
                     re.sub(r"\s*\(Main\)\s*$", "", folder_name, flags=re.IGNORECASE),
                     flags=re.IGNORECASE).strip()

    candidates = sorted(
        {folder_name.strip(), no_main, no_c0, no_both} - {""},
        key=len, reverse=True,
    )

    color = None
    for cand in candidates:
        cand_norm = re.sub(r"\s+", " ", cand).lower()
        if stem_norm.startswith(cand_norm):
            color = stem[len(cand):].strip()
            break
    if color is None:
        color = stem

    # Strip any leading suffix tokens like "-C0", "C0", "(Main)" that
    # may remain when a folder mixes naming conventions.
    color = re.sub(r"^[-\s_]*(?:C0|\(Main\))[-\s_]*", "", color, flags=re.IGNORECASE)
    color = color.strip(" -_")
    if not color:
        return None
    return color


def strip_date_suffix(color: str) -> tuple[str, date | None, int]:
    """Return (base_color, date_or_None, sub_index).

    'Carbon (2024-06-11)'   -> ('Carbon', date(2024,6,11), 0)
    'Carbon (2024-06-11-2)' -> ('Carbon', date(2024,6,11), 2)
    'Carbon'                -> ('Carbon', None, 0)
    """
    m = DATE_SUFFIX_RE.search(color)
    if not m:
        return color, None, 0
    base = color[: m.start()].strip()
    y, mo, d = map(int, m.group(1).split("-"))
    sub = int(m.group(2)) if m.group(2) else 0
    return base, date(y, mo, d), sub


def color_to_slug_part(color: str) -> str:
    s = color.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def is_skippable_folder(name: str) -> bool:
    if re.match(r"^\d+\.", name):
        return True
    if "incomplete" in name.lower():
        return True
    return False


def collect_library() -> dict[str, dict]:
    """Return {slug: {'src_folders': [...], 'images': {target_filename: src_path}}}."""
    by_slug: dict[str, dict] = {}

    for entry in sorted(p for p in LIBRARY.iterdir() if p.is_dir()):
        name = entry.name
        if is_skippable_folder(name):
            continue
        slug = folder_to_slug(name)

        # Group files by base color, choose newest if date-stamped duplicates
        # candidates: base_color -> (date, sub, src_path)
        candidates: dict[str, tuple[date | None, int, Path]] = {}
        for f in entry.iterdir():
            if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
                continue
            color = file_to_color_part(name, f.name)
            if not color:
                continue
            base_color, dt, sub = strip_date_suffix(color)
            key = base_color.lower().strip()
            existing = candidates.get(key)
            # Newer (later date, then later sub) wins. Undated beats nothing.
            cur_rank = (dt or date.min, sub)
            if existing is None or cur_rank > (existing[0] or date.min, existing[1]):
                candidates[key] = (dt, sub, f)

        if not candidates:
            continue

        slot = by_slug.setdefault(
            slug, {"src_folders": [], "images": {}}
        )
        slot["src_folders"].append(name)
        for base_color, (_, _, src_path) in candidates.items():
            target_name = f"{slug}-{color_to_slug_part(base_color)}{src_path.suffix.lower()}"
            # If two source folders contributed the same target (e.g. Audrina (Main)
            # + Audrina-C0 both have a "Birch" color), prefer the (Main) version.
            existing_src = slot["images"].get(target_name)
            if existing_src is None or "(main)" in src_path.parent.name.lower():
                slot["images"][target_name] = src_path

    return by_slug


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy-photos", action="store_true",
                        help="Copy normalized photos into the catalog dir")
    parser.add_argument("--apply-json", action="store_true",
                        help="Update dorell_fabrics.json")
    parser.add_argument("--limit-copies", type=int, default=0,
                        help="Limit how many files to copy (debug)")
    args = parser.parse_args()

    if not LIBRARY.exists():
        sys.exit(f"Library not found: {LIBRARY}")
    if not CATALOG.exists():
        sys.exit(f"Catalog not found: {CATALOG}")
    if not JSON_PATH.exists():
        sys.exit(f"JSON not found: {JSON_PATH}")

    print(f"Library: {LIBRARY}")
    print(f"Catalog: {CATALOG}")
    print(f"JSON:    {JSON_PATH}")
    print()

    by_slug = collect_library()
    with open(JSON_PATH, encoding="utf-8") as f:
        json_data = json.load(f)
    json_by_slug = {p["slug"]: p for p in json_data}

    new_patterns = []        # slugs not in JSON
    new_colorways = defaultdict(list)  # slug -> [target_filenames]
    photos_to_copy = []      # (src_path, dst_path)

    for slug, slot in by_slug.items():
        target_dir = CATALOG / slug
        existing_files = set()
        if target_dir.exists():
            existing_files = {f.name for f in target_dir.iterdir() if f.is_file()}

        for target_name, src_path in slot["images"].items():
            if target_name not in existing_files:
                photos_to_copy.append((src_path, target_dir / target_name))

        json_entry = json_by_slug.get(slug)
        new_in_json = []
        if json_entry is None:
            new_patterns.append((slug, sorted(slot["images"].keys()), slot["src_folders"]))
        else:
            existing_in_json = set(json_entry.get("images", []))
            for target_name in sorted(slot["images"].keys()):
                if target_name not in existing_in_json:
                    new_in_json.append(target_name)
            if new_in_json:
                new_colorways[slug] = new_in_json

    total_new_colorway_imgs = sum(len(v) for v in new_colorways.values())
    print(f"Library slugs (after normalization): {len(by_slug)}")
    print(f"JSON patterns:                       {len(json_by_slug)}")
    print(f"Net-new patterns:                    {len(new_patterns)}")
    print(f"Existing patterns gaining images:    {len(new_colorways)}  ({total_new_colorway_imgs} new images)")
    print(f"Photos to copy into catalog:         {len(photos_to_copy)}")
    print()

    if new_patterns:
        print("=== NET-NEW PATTERNS (sample) ===")
        for slug, imgs, srcs in new_patterns[:25]:
            src_label = ", ".join(srcs)
            print(f"  + {slug:30s} {len(imgs):3d} images   [from: {src_label}]")
        if len(new_patterns) > 25:
            print(f"  ... and {len(new_patterns) - 25} more")
        print()

    if new_colorways:
        print("=== EXISTING PATTERNS GAINING COLORWAYS (sample) ===")
        for slug, imgs in list(new_colorways.items())[:20]:
            sample = imgs[:3]
            more = "..." if len(imgs) > 3 else ""
            print(f"  ~ {slug:30s} +{len(imgs):2d}: {sample}{more}")
        if len(new_colorways) > 20:
            print(f"  ... and {len(new_colorways) - 20} more")
        print()

    if not args.copy_photos and not args.apply_json:
        print("--- DRY RUN --- pass --copy-photos and/or --apply-json to make changes")
        return

    if args.copy_photos:
        copies = photos_to_copy
        if args.limit_copies:
            copies = copies[: args.limit_copies]
        print(f"Copying {len(copies)} photos...")
        copied = 0
        skipped = 0
        failed: list[tuple[Path, Path, str]] = []
        for src, dst in copies:
            # Skip files already at destination (idempotent re-runs)
            if dst.exists() and dst.stat().st_size > 0:
                skipped += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Retry on transient OneDrive cloud errors (WinError 389 etc.)
            attempts, last_err = 0, None
            while attempts < 4:
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                    break
                except OSError as e:
                    last_err = e
                    attempts += 1
                    time.sleep(2 * attempts)  # backoff: 2s, 4s, 6s
            else:
                failed.append((src, dst, str(last_err)))
                continue
            if (copied + skipped) % 100 == 0:
                print(f"  ... copied {copied} / skipped {skipped} / failed {len(failed)} (of {len(copies)})")
        print(f"Done. copied={copied} skipped={skipped} failed={len(failed)}")
        if failed:
            print("\nFailures:")
            for src, dst, err in failed[:20]:
                print(f"  {src.name} -> {dst.name}: {err}")
            if len(failed) > 20:
                print(f"  ... and {len(failed) - 20} more")

    if args.apply_json:
        # Re-scan the catalog for each affected slug to pick up the just-copied files
        for slug, imgs, srcs in new_patterns:
            target_dir = CATALOG / slug
            actual_imgs = sorted(
                f.name for f in target_dir.iterdir()
                if f.is_file() and f.suffix.lower() in IMG_EXTS
            ) if target_dir.exists() else []
            display_name = re.sub(r"\s*\(Main\)\s*", "", srcs[0]).strip()
            display_name = re.sub(r"[-\s]C0\s*$", "", display_name).strip()
            json_data.append({
                "name": display_name,
                "slug": slug,
                "description": "",
                "content": "TBA",
                "durability": "TBA",
                "direction": "TBA",
                "cleanCode": "TBA",
                "images": actual_imgs,
            })

        for slug, imgs in new_colorways.items():
            entry = next(p for p in json_data if p["slug"] == slug)
            target_dir = CATALOG / slug
            actual_imgs = sorted(
                f.name for f in target_dir.iterdir()
                if f.is_file() and f.suffix.lower() in IMG_EXTS
            )
            entry["images"] = actual_imgs

        json_data.sort(key=lambda p: p["slug"])
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Wrote {len(json_data)} patterns to {JSON_PATH}")


if __name__ == "__main__":
    main()
