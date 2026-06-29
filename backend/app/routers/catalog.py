"""
Catalog API — serves Dorell fabrics and furniture retailer data.

Fabric images are proxied from the Dorell Netlify site.
Furniture data comes from pre-scraped JSON catalogs.
New retailers can be added by dropping a JSON file in the app directory
and registering it in RETAILERS below.
"""

import json
import time
import uuid
import shutil
import threading
import urllib.request
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from ..config import settings

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _enforce_brand_scope(request: Request, retailer: str):
    """If the caller authenticated via a brand API key, only let them query
    their own brand's retailer. Internal (basic-auth) callers see everything."""
    brand = getattr(request.state, "brand", None)
    if brand and brand != retailer:
        raise HTTPException(
            status_code=403,
            detail=f"API key is scoped to '{brand}', cannot query '{retailer}'",
        )

DATA_DIR = Path(__file__).parent.parent

# ── Dorell Fabrics ──────────────────────────────────────────────

DORELL_IMAGE_BASE = "https://dorell-fabrics-cdn.netlify.app/images"
# Shared photo host: the canonical fabric library for all Dorell apps. We read
# it at runtime so newly-added fabrics appear without re-syncing/redeploying.
PHOTO_HOST_LIBRARY = "https://dorell-fabrics-cdn.netlify.app/library.json"
FABRICS_TTL = 900  # seconds — re-fetch from the photo host at most every 15 min

_fabrics_cache = None
_fabrics_cache_at = 0.0
_fabrics_lock = threading.Lock()


def _shape_from_library(raw: list[dict]) -> list[dict]:
    """Reshape photo-host library.json records into this catalog's fabric shape.

    Photo host record: {name, slug, description, content, durability, direction,
                        cleanCode, ..., colors: [{name, filename, ...}]}
    """
    shaped = []
    for rec in raw:
        slug = rec.get("slug")
        if not slug:
            continue
        images = [c["filename"] for c in rec.get("colors", []) if c.get("filename")]
        shaped.append({
            "name": rec.get("name", slug),
            "slug": slug,
            "description": rec.get("description", ""),
            "content": rec.get("content", ""),
            "durability": rec.get("durability", ""),
            "direction": rec.get("direction", ""),
            "cleanCode": rec.get("cleanCode", ""),
            "images": images,
        })
    return shaped


def _enrich(raw: list[dict]) -> list[dict]:
    """Add full image URLs and derived fields to each fabric record."""
    for p in raw:
        p["image_urls"] = [
            f"{DORELL_IMAGE_BASE}/{p['slug']}/{img}" for img in p.get("images", [])
        ]
        p["thumbnail"] = p["image_urls"][0] if p["image_urls"] else ""
        desc = p.get("description", "").lower()
        p["jacquard"] = "jacquard" in desc
    return raw


def _fetch_library() -> list[dict]:
    with urllib.request.urlopen(PHOTO_HOST_LIBRARY, timeout=10) as r:
        if r.status != 200:
            raise RuntimeError(f"photo host returned HTTP {r.status}")
        return json.loads(r.read())


def _load_fabrics(force: bool = False):
    """Return the enriched fabric list, refreshing from the photo host on a TTL.

    Falls back to the last good cache, then to the bundled JSON, so the catalog
    never goes empty even if the photo host is briefly unreachable.
    """
    global _fabrics_cache, _fabrics_cache_at
    now = time.time()
    if not force and _fabrics_cache is not None and (now - _fabrics_cache_at) < FABRICS_TTL:
        return _fabrics_cache

    with _fabrics_lock:
        # Re-check after acquiring the lock — another request may have refreshed.
        now = time.time()
        if not force and _fabrics_cache is not None and (now - _fabrics_cache_at) < FABRICS_TTL:
            return _fabrics_cache
        try:
            raw = _shape_from_library(_fetch_library())
            if not raw:
                raise RuntimeError("photo host returned no fabrics")
            source = "photo-host"
        except Exception as e:
            if _fabrics_cache is not None:
                # Keep serving the last good data; back off so we don't hammer.
                print(f"[catalog] photo-host refresh failed, keeping cache: {e}")
                _fabrics_cache_at = now
                return _fabrics_cache
            print(f"[catalog] photo-host fetch failed, using bundled JSON: {e}")
            with open(DATA_DIR / "dorell_fabrics.json") as f:
                raw = json.load(f)
            source = "bundled"
        _fabrics_cache = _enrich(raw)
        _fabrics_cache_at = now
        print(f"[catalog] loaded {len(_fabrics_cache)} fabrics from {source}")
        return _fabrics_cache


@router.post("/refresh")
def refresh_fabrics():
    """Force an immediate re-fetch of the fabric library from the photo host."""
    fabrics = _load_fabrics(force=True)
    return {"refreshed": True, "count": len(fabrics)}


@router.get("/fabrics")
def list_fabrics(
    q: str = "",
    durability: str = "",
    content: str = "",
    direction: str = "",
    jacquard: str = "",   # "yes" → jacquard only, "no" → non-jacquard only, "" → all
    limit: int = Query(60, le=200),
    offset: int = 0,
):
    fabrics = _load_fabrics()
    results = fabrics

    if q:
        ql = q.lower()
        results = [
            p for p in results
            if ql in p["name"].lower()
            or any(ql in img.lower() for img in p.get("images", []))
        ]

    if durability and durability != "All":
        results = [p for p in results if durability in p.get("durability", "")]

    if content:
        cl = content.lower()
        results = [p for p in results if cl in p.get("content", "").lower()]

    if direction:
        dl = direction.lower()
        results = [p for p in results if dl in p.get("direction", "").lower()]

    if jacquard == "yes":
        results = [p for p in results if p.get("jacquard")]
    elif jacquard == "no":
        results = [p for p in results if not p.get("jacquard")]

    total = len(results)
    page = results[offset : offset + limit]
    return {"total": total, "items": page}


@router.get("/fabrics/{slug}")
def get_fabric(slug: str):
    fabrics = _load_fabrics()
    for p in fabrics:
        if p["slug"] == slug:
            return p
    raise HTTPException(status_code=404, detail="Fabric not found")


@router.get("/fabrics-filters")
def fabrics_filters():
    """Return available filter values."""
    fabrics = _load_fabrics()
    durabilities = sorted(set(
        p.get("durability", "") for p in fabrics if p.get("durability") and p["durability"] != "TBA"
    ))
    contents = sorted(set(p.get("content", "") for p in fabrics if p.get("content") and p["content"] != "TBA"))
    directions = sorted(set(
        p.get("direction", "").strip() for p in fabrics
        if p.get("direction") and p["direction"] != "TBA"
    ))
    jacquard_count = sum(1 for p in fabrics if p.get("jacquard"))
    return {
        "durabilities": durabilities,
        "contents": contents,
        "directions": directions,
        "jacquard_count": jacquard_count,
    }


# ── Furniture Retailers ─────────────────────────────────────────

RETAILERS = {
    "ashley": {
        "name": "Ashley Furniture",
        "file": "ashley_catalog.json",
        "logo": "",
    },
    "arhaus": {
        "name": "Arhaus",
        "file": "arhaus_catalog.json",
        "logo": "",
    },
    "bernhardt": {
        "name": "Bernhardt",
        "file": "bernhardt_catalog.json",
        "logo": "",
    },
    "crateandbarrel": {
        "name": "Crate & Barrel",
        "file": "crateandbarrel_catalog.json",
        "logo": "",
    },
    "westelm": {
        "name": "West Elm",
        "file": "westelm_catalog.json",
        "logo": "",
    },
    "potterybarn": {
        "name": "Pottery Barn",
        "file": "potterybarn_catalog.json",
        "logo": "",
    },
    "jonathanlouis": {
        "name": "Jonathan Louis",
        "file": "jonathanlouis_catalog.json",
        "logo": "",
    },
    "livingspaces": {
        "name": "Living Spaces",
        "file": "livingspaces_catalog.json",
        "logo": "",
    },
    "roomstogo": {
        "name": "Rooms To Go",
        "file": "roomstogo_catalog.json",
        "logo": "",
    },
    "crlaine": {
        "name": "CR Laine",
        "file": "crlaine_catalog.json",
        "logo": "",
    },
    "maxhome": {
        "name": "Max Home",
        "file": "maxhome_catalog.json",
        "logo": "",
    },
    "rowe": {
        "name": "Rowe / Robin Bruce",
        "file": "rowe_catalog.json",
        "logo": "",
    },
    "havertys": {
        "name": "Havertys",
        "file": "havertys_catalog.json",
        "logo": "",
    },
    "rh": {
        "name": "RH",
        "file": "rh_catalog.json",
        "logo": "",
    },
    "hickorychair": {
        "name": "Hickory Chair",
        "file": "hickorychair_catalog.json",
        "logo": "",
    },
}

_furniture_cache: dict[str, list] = {}


def _load_furniture(retailer_key: str):
    if retailer_key not in _furniture_cache:
        info = RETAILERS.get(retailer_key)
        if not info:
            return None
        filepath = DATA_DIR / info["file"]
        if not filepath.exists():
            return []
        with open(filepath) as f:
            _furniture_cache[retailer_key] = json.load(f)
    return _furniture_cache[retailer_key]


@router.get("/retailers")
def list_retailers(request: Request):
    """Return list of available furniture retailers.

    For brand-scoped (X-API-Key) callers, only their own brand is returned.
    """
    brand = getattr(request.state, "brand", None)
    items = RETAILERS.items()
    if brand:
        items = [(brand, RETAILERS[brand])] if brand in RETAILERS else []
    return [{"key": k, "name": v["name"], "logo": v["logo"]} for k, v in items]


@router.get("/furniture/{retailer}")
def list_furniture(
    request: Request,
    retailer: str,
    q: str = "",
    category: str = "",
    collection: str = "",
    limit: int = Query(60, le=200),
    offset: int = 0,
):
    _enforce_brand_scope(request, retailer)
    items = _load_furniture(retailer)
    if items is None:
        raise HTTPException(status_code=404, detail=f"Retailer '{retailer}' not found")

    results = items

    if q:
        ql = q.lower()
        results = [p for p in results if ql in p.get("name", "").lower()]

    if category:
        cl = category.lower()
        results = [
            p for p in results
            if cl in p.get("type", "").lower() or cl in p.get("category", "").lower()
        ]

    if collection:
        col = collection.lower()
        results = [p for p in results if col in p.get("collection", "").lower()]

    total = len(results)
    page = results[offset : offset + limit]
    return {"total": total, "items": page}


@router.get("/furniture/{retailer}/filters")
def furniture_filters(request: Request, retailer: str):
    _enforce_brand_scope(request, retailer)
    items = _load_furniture(retailer)
    if items is None:
        raise HTTPException(status_code=404, detail=f"Retailer '{retailer}' not found")

    types = sorted(set(p.get("type", "") for p in items if p.get("type")))
    collections = sorted(set(p.get("collection", "") for p in items if p.get("collection")))
    return {"types": types, "collections": collections}


# ── Custom Frame Upload ─────────────────────────────────────────

@router.post("/upload-furniture")
async def upload_custom_furniture(file: UploadFile = File(...)):
    """
    Upload a custom furniture photo for use in the visualizer.
    Returns a local URL that can be passed directly as furniture_url.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    ext = Path(file.filename or "upload.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"

    filename = f"custom_{uuid.uuid4().hex}{ext}"
    dest = settings.furniture_dir / filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "image_url": f"/uploads/furniture/{filename}",
        "name": Path(file.filename or "Custom Frame").stem,
        "filename": filename,
    }
