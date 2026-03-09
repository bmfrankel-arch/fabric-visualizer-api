"""
Fabric visualization service.

Applies fabric textures to furniture frames using image processing.
Supports two modes:
  1. Local CV pipeline: rembg segmentation + GrabCut refinement + texture mapping (default)
  2. AI-powered: uses Replicate API for higher quality results (requires API key)
"""

import uuid
import hashlib
import numpy as np
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageFilter
import cv2
import httpx
from rembg import remove as rembg_remove
from ..config import settings


RESULTS_DIR = settings.upload_dir / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_CACHE_DIR = settings.upload_dir / "cache"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

YARD_CUTS_DIR = settings.upload_dir / "yard-cuts"
YARD_CUTS_DIR.mkdir(parents=True, exist_ok=True)

# CDN base URL for pre-generated yard-cuts (deployed to Netlify alongside swatches)
YARD_CUTS_CDN = "https://dorellfabrics-patternlibrary.netlify.app/yard-cuts"


import re as _re
import shutil as _shutil


def _build_cdn_yard_cut_url(fabric_url: str) -> "str | None":
    """Convert a swatch CDN URL to its corresponding yard-cut CDN URL.

    Input:  .../images/ace/ace-bone.jpg
    Output: .../yard-cuts/ace/ace-bone.webp
    """
    m = _re.search(r'/images/([^/]+)/([^/]+)\.\w+$', fabric_url)
    if not m:
        return None
    slug, colorway = m.group(1), m.group(2)
    return f"{YARD_CUTS_CDN}/{slug}/{colorway}.webp"


async def download_image(url: str) -> Path:
    """Download an image URL to a local cache file. Returns cached path.

    Also handles local /uploads/ paths (from custom frame uploads) by
    resolving them directly against the upload directory.
    """
    # Local file uploaded to this server — resolve directly, no HTTP needed
    if url.startswith("/uploads/"):
        local_path = settings.upload_dir / url[len("/uploads/"):]
        if local_path.exists():
            return local_path
        raise FileNotFoundError(f"Local upload not found: {url}")

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    ext = Path(url.split("?")[0]).suffix or ".jpg"
    cached = IMAGE_CACHE_DIR / f"{url_hash}{ext}"
    if cached.exists():
        return cached
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(cached, "wb") as f:
            f.write(resp.content)
    return cached


def _load_image(path: Path, max_size: int = 1024) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    return img


def _create_upholstery_mask(furniture_img: Image.Image) -> np.ndarray:
    """
    Detect upholstered regions using rembg for foreground extraction
    followed by GrabCut refinement within the furniture shape.

    Pipeline:
    1. rembg (U2-Net) extracts the furniture from background (walls, floors, etc.)
    2. Within the furniture shape, use color analysis to exclude non-fabric areas
       (wood legs, metal frames, etc.)
    3. GrabCut refines the mask boundaries for clean edges
    """
    img_rgb = furniture_img.convert("RGB")
    img_array = np.array(img_rgb)
    h, w = img_array.shape[:2]

    # Step 1: Use rembg to extract furniture foreground
    # This removes walls, floors, room backgrounds completely
    rembg_result = rembg_remove(img_rgb)
    alpha = np.array(rembg_result)[:, :, 3]  # Extract alpha channel
    foreground_mask = (alpha > 128).astype(np.uint8) * 255

    # Step 2: Within the foreground, identify upholstery vs non-fabric parts
    # Use color analysis to exclude very dark areas (legs, shadows) and
    # areas with strong wood/metal tones
    hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

    # Exclude very dark regions (typically legs, frames, deep shadows)
    dark_mask = hsv[:, :, 2] < 40
    # Exclude very saturated warm colors (wood tones: H=10-30, S>100)
    wood_mask = (hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 25) & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 60)
    # Exclude near-black and very dark brown (metal/dark wood frames)
    very_dark_mask = (hsv[:, :, 2] < 60) & (hsv[:, :, 1] < 80)

    exclude_mask = (dark_mask | wood_mask | very_dark_mask).astype(np.uint8) * 255
    # Only exclude within the foreground
    exclude_mask = cv2.bitwise_and(exclude_mask, foreground_mask)

    # Initial upholstery mask = foreground minus excluded areas
    upholstery_initial = cv2.bitwise_and(foreground_mask, cv2.bitwise_not(exclude_mask))

    # Step 3: GrabCut refinement for cleaner edges
    # Build GrabCut initialization from our masks
    grabcut_mask = np.full((h, w), cv2.GC_BGD, dtype=np.uint8)  # Start as background
    grabcut_mask[foreground_mask > 128] = cv2.GC_PR_FGD  # Foreground region is probable FG
    grabcut_mask[upholstery_initial > 200] = cv2.GC_FGD  # Strong upholstery is definite FG
    grabcut_mask[foreground_mask == 0] = cv2.GC_BGD  # Outside furniture is definite BG

    # Run GrabCut (limited iterations for speed)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_array, grabcut_mask, None, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_MASK)
        refined_mask = np.where(
            (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    except cv2.error:
        # GrabCut can fail on edge cases; fall back to initial mask
        refined_mask = upholstery_initial

    # Constrain refined mask to the rembg foreground (never extend beyond furniture)
    refined_mask = cv2.bitwise_and(refined_mask, foreground_mask)

    # Step 4: Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    refined_mask = cv2.morphologyEx(refined_mask, cv2.MORPH_CLOSE, kernel)
    refined_mask = cv2.morphologyEx(refined_mask, cv2.MORPH_OPEN, kernel)

    # Fill small holes inside the mask (e.g., button tufting, seam lines)
    contours, _ = cv2.findContours(refined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(refined_mask, contours, -1, 255, cv2.FILLED)

    # Soft edges via Gaussian blur
    refined_mask = cv2.GaussianBlur(refined_mask, (7, 7), 0)

    return refined_mask


def _tile_fabric(fabric_img: Image.Image, target_size: tuple[int, int], scale: float = None) -> Image.Image:
    """Tile fabric texture to fill the target size.

    If scale is None (default), automatically compute a scale so the pattern
    repeats ~12 times across the furniture width.  Dorell fabric photos are
    macro close-ups that show only a few centimetres of cloth; on a real sofa
    the same pattern tiles many times, so we need to shrink each tile
    significantly relative to the furniture image dimensions.
    """
    tw, th = target_size

    if scale is None:
        # Target ~5 repeats across furniture width → visible pattern scale for
        # geometric fabrics (chevrons, plaids, jacquards). 12 was too fine and
        # made patterns indistinguishable from solid textures.
        target_tile_w = tw / 5.0
        scale = target_tile_w / max(1, fabric_img.width)

    fw = max(1, int(fabric_img.width * scale))
    fh = max(1, int(fabric_img.height * scale))
    fabric_scaled = fabric_img.resize((fw, fh), Image.LANCZOS)

    tiled = Image.new("RGBA", (tw, th))
    for y in range(0, th, fh):
        for x in range(0, tw, fw):
            tiled.paste(fabric_scaled, (x, y))

    return tiled


def _apply_lighting(
    fabric_tiled: np.ndarray, furniture_gray: np.ndarray, mask: np.ndarray
) -> np.ndarray:
    """
    Apply the furniture's lighting/shading to the fabric texture.
    This makes the fabric follow the 3D contours of the furniture.
    Uses a gentler approach to preserve the fabric's actual color.
    """
    # Normalize grayscale to use as lighting map
    light_map = furniture_gray.astype(np.float32) / 255.0

    # Compute mean brightness in the masked (upholstery) area only
    masked_pixels = light_map[mask > 128]
    if len(masked_pixels) == 0:
        return fabric_tiled
    mean_val = np.mean(masked_pixels)

    # Gentler contrast enhancement — center around 0.65 (slightly bright)
    # to avoid over-darkening. Use less aggressive multiplier.
    light_map = np.clip((light_map - mean_val) * 0.8 + 0.65, 0.3, 1.0)

    # Apply lighting to each channel of the fabric
    result = fabric_tiled.astype(np.float32)
    for c in range(min(3, result.shape[2])):
        result[:, :, c] = result[:, :, c] * light_map

    return np.clip(result, 0, 255).astype(np.uint8)


def apply_fabric_to_furniture(
    fabric_path: Path, furniture_path: Path
) -> str:
    """
    Apply fabric texture to furniture using local CV pipeline.

    Steps:
    1. Detect upholstered regions via color segmentation
    2. Tile the fabric texture
    3. Apply furniture's lighting/shadows to the fabric
    4. Composite the result
    """
    furniture_img = _load_image(furniture_path)
    fabric_img = _load_image(fabric_path, max_size=512)

    w, h = furniture_img.size

    # Step 1: Create upholstery mask
    mask = _create_upholstery_mask(furniture_img)

    # Step 2: Tile fabric to fill furniture dimensions
    fabric_tiled = _tile_fabric(fabric_img, (w, h))

    # Step 3: Apply furniture's lighting to fabric
    furniture_gray = np.array(furniture_img.convert("L"))
    fabric_array = np.array(fabric_tiled)
    fabric_lit = _apply_lighting(fabric_array, furniture_gray, mask)

    # Step 4: Composite
    furniture_array = np.array(furniture_img.convert("RGBA"))
    result = furniture_array.copy()

    # Blend using mask
    mask_normalized = mask.astype(np.float32) / 255.0
    mask_3d = np.stack([mask_normalized] * 4, axis=2)

    fabric_lit_rgba = np.dstack([fabric_lit[:, :, :3], np.full((h, w), 255, dtype=np.uint8)])

    result = (fabric_lit_rgba * mask_3d + furniture_array * (1 - mask_3d)).astype(np.uint8)

    # Save result
    result_img = Image.fromarray(result)
    result_filename = f"viz_{uuid.uuid4().hex}.png"
    result_img.save(RESULTS_DIR / result_filename, "PNG")

    return result_filename


async def apply_fabric_openai(
    fabric_path: Path,
    furniture_path: Path,
    pillow_fabric_path: "Path | None" = None,
    pillow_fabric_name: str = "",
    main_fabric_name: str = "",
    fabric_url_hint: str = "",
) -> str:
    """
    AI fabric visualization — direct swatch approach (ChatGPT-style).

    Simplified pipeline that sends the original fabric swatch directly to
    gpt-image-1 alongside the furniture photo, using simple conversational
    prompts.  This mirrors the approach that produces excellent results in
    ChatGPT's native interface.

    Pass 1 — REUPHOLSTER (always):
        gpt-image-1 receives the furniture photo + original fabric swatch
        and reupholsters all fabric surfaces.

    Pass 2 — ACCENT PILLOWS (only when pillow_fabric_path is given):
        gpt-image-1 adds/replaces accent pillows with a separate fabric.

    Falls back to plain CV pipeline if OpenAI key is absent or call fails.
    Requires FV_OPENAI_API_KEY environment variable.
    """
    if not settings.openai_api_key:
        return apply_fabric_to_furniture(fabric_path, furniture_path)

    try:
        import base64
        import os
        import tempfile
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)

        has_pillows = pillow_fabric_path is not None and pillow_fabric_path.exists()
        print(f"[OpenAI] apply_fabric_openai v9-direct starting (pillows={'yes' if has_pillows else 'no'})")

        # ── Helper: resize and write to temp file ──────────────────────
        def _resize_and_save(img: Image.Image, max_px: int) -> tempfile.NamedTemporaryFile:
            img = img.convert("RGB")
            if max(img.size) > max_px:
                ratio = max_px / max(img.size)
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS,
                )
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp, format="PNG")
            tmp.flush(); tmp.close()
            return tmp

        body_label = f'"{main_fabric_name}"' if main_fabric_name else "this fabric"

        # ── Pass 1: Reupholster furniture using original swatch ────────
        #
        # Key insight from ChatGPT testing: sending the original fabric
        # swatch directly (no intermediate "yard-cut" generation) with a
        # simple, conversational prompt produces far better fabric fidelity
        # than the previous over-engineered multi-pass pipeline.

        body_prompt = (
            f"I want to reupholster this sofa using {body_label}.\n\n"
            "Image 1 is the furniture photograph.\n"
            "Image 2 is a photo of the fabric I want to use.\n\n"
            "Recreate this exact sofa with all of its upholstered surfaces "
            "(seat cushions, back cushions, arms, and sides) reupholstered "
            "in the fabric from Image 2. Remove any existing throw pillows.\n\n"
            "Match the fabric's exact color, pattern, and texture from Image 2. "
            "Keep the furniture shape, legs, frame, and background exactly as-is. "
            "The result should look like a real product photograph."
        )

        furn_tmp   = _resize_and_save(Image.open(furniture_path), 1536)
        fabric_tmp = _resize_and_save(Image.open(fabric_path), 1536)

        try:
            with open(furn_tmp.name, "rb") as ff, open(fabric_tmp.name, "rb") as sf:
                r = await client.images.edit(
                    model="gpt-image-1",
                    image=[ff, sf],
                    prompt=body_prompt,
                    quality="high",
                    size="1536x1024",
                )
            pass1_data = base64.b64decode(r.data[0].b64_json)
        finally:
            os.unlink(furn_tmp.name)
            os.unlink(fabric_tmp.name)

        print("[OpenAI] Pass 1 (body reupholster) done")

        # If no pillow fabric, save Pass-1 result and return
        if not has_pillows:
            result_filename = f"viz_oai_{uuid.uuid4().hex}.png"
            with open(RESULTS_DIR / result_filename, "wb") as f:
                f.write(pass1_data)
            print(f"[OpenAI] done (no pillows): {result_filename}")
            return result_filename

        # ── Pass 2: Accent pillows ─────────────────────────────────────
        pass1_pil  = Image.open(BytesIO(pass1_data))
        pillow_pil = Image.open(pillow_fabric_path)

        pass1_tmp  = _resize_and_save(pass1_pil,  1536)
        pillow_tmp = _resize_and_save(pillow_pil, 1536)

        pillow_label = f'"{pillow_fabric_name}"' if pillow_fabric_name else "the fabric in Image 2"

        pillow_prompt = (
            f"I want to add accent throw pillows to this sofa using {pillow_label}.\n\n"
            "Image 1 is the sofa photograph.\n"
            "Image 2 is the fabric I want for the pillows.\n\n"
            "Add 2-3 accent throw pillows to the sofa using the fabric from "
            "Image 2. If there are already pillows, replace their fabric. "
            "Match the exact color, pattern, and texture from Image 2.\n\n"
            "Do not change the sofa upholstery, shape, legs, frame, or background. "
            "Only add or re-cover the accent pillows. "
            "The result should look like a real product photograph."
        )

        try:
            with open(pass1_tmp.name, "rb") as p1_f, open(pillow_tmp.name, "rb") as sw_f:
                response2 = await client.images.edit(
                    model="gpt-image-1",
                    image=[p1_f, sw_f],
                    prompt=pillow_prompt,
                    quality="high",
                    size="1536x1024",
                )
        finally:
            os.unlink(pass1_tmp.name)
            os.unlink(pillow_tmp.name)

        img_data = base64.b64decode(response2.data[0].b64_json)
        result_filename = f"viz_oai_{uuid.uuid4().hex}.png"
        with open(RESULTS_DIR / result_filename, "wb") as f:
            f.write(img_data)

        print(f"[OpenAI] Pass 2 (accent pillows) done: {result_filename}")
        return result_filename

    except Exception as e:
        print(f"[OpenAI] visualization failed, falling back to CV pipeline: {e}")
        return apply_fabric_to_furniture(fabric_path, furniture_path)


async def refine_with_openai(result_filename: str, user_prompt: str) -> str:
    """
    Refine an existing visualization using OpenAI gpt-image-1.

    Loads the current result image and sends it to the model with the user's
    custom instruction (e.g. "make the fabric darker", "clean up the edges").
    Returns the filename of the new refined result.
    """
    import base64
    import os
    import tempfile
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    result_path = RESULTS_DIR / result_filename
    if not result_path.exists():
        raise FileNotFoundError(result_filename)

    # Load and cap at 1024px
    img = Image.open(result_path).convert("RGB")
    if max(img.size) > 1024:
        ratio = 1024 / max(img.size)
        img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp, format="PNG")
    tmp.flush()
    tmp.close()

    prompt = (
        "This is a furniture visualization photograph. "
        "Please apply the following modification:\n\n"
        f"{user_prompt.strip()}\n\n"
        "Preserve the furniture shape, fabric pattern, and overall composition "
        "unless the instruction specifically asks to change them. "
        "Output a single photorealistic furniture catalog photograph."
    )

    try:
        with open(tmp.name, "rb") as f:
            response = await client.images.edit(
                model="gpt-image-1",
                image=[f],
                prompt=prompt,
            )
    finally:
        os.unlink(tmp.name)

    img_data = base64.b64decode(response.data[0].b64_json)
    new_filename = f"viz_oai_{uuid.uuid4().hex}.png"
    with open(RESULTS_DIR / new_filename, "wb") as f:
        f.write(img_data)

    return new_filename


async def apply_fabric_ai(fabric_path: Path, furniture_path: Path) -> str:
    """
    AI-powered fabric application using Replicate API.
    Requires FV_REPLICATE_API_TOKEN environment variable.
    Falls back to local CV pipeline if unavailable.
    """
    if not settings.replicate_api_token:
        return apply_fabric_to_furniture(fabric_path, furniture_path)

    try:
        import replicate

        # Use a depth-aware inpainting model
        # First, generate a mask of the upholstered area
        furniture_img = _load_image(furniture_path)
        mask = _create_upholstery_mask(furniture_img)
        mask_img = Image.fromarray(mask)

        mask_filename = f"mask_{uuid.uuid4().hex}.png"
        mask_path = RESULTS_DIR / mask_filename
        mask_img.save(mask_path)

        fabric_img = Image.open(fabric_path)

        # Use Replicate's img2img with ControlNet for texture transfer
        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "image": open(furniture_path, "rb"),
                "mask": open(mask_path, "rb"),
                "prompt": f"furniture with fabric upholstery texture, photorealistic",
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
            },
        )

        # Download and save result
        import httpx

        result_filename = f"viz_ai_{uuid.uuid4().hex}.png"
        async with httpx.AsyncClient() as client:
            resp = await client.get(str(output[0]))
            with open(RESULTS_DIR / result_filename, "wb") as f:
                f.write(resp.content)

        # Cleanup
        mask_path.unlink(missing_ok=True)

        return result_filename

    except Exception as e:
        print(f"AI visualization failed, falling back to CV: {e}")
        return apply_fabric_to_furniture(fabric_path, furniture_path)
