import base64
import json
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from .config import settings
from .database import init_db
from .routers import fabrics, furniture, scraper, visualize, catalog

app = FastAPI(title=settings.app_name)


# ── Auth middleware ──────────────────────────────────────────────────────────
# Exempt /api/health so Railway's healthcheck still works without credentials.
# Two accepted forms:
#   1. HTTP Basic Auth — for the internal multi-brand frontend
#   2. X-API-Key header — for per-brand white-label frontends
# If neither is present/valid, return 401.

AUTH_EXEMPT_PATHS = {"/api/health"}

try:
    BRAND_API_KEYS: dict[str, str] = json.loads(settings.brand_api_keys or "{}")
except Exception:
    BRAND_API_KEYS = {}
# Reverse lookup: api_key -> brand_name. Used to tag requests with their brand.
_KEY_TO_BRAND = {v: k for k, v in BRAND_API_KEYS.items() if v}


def _check_basic_auth(auth_header: str) -> bool:
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
        user_ok = secrets.compare_digest(username, settings.basic_auth_username)
        pass_ok = secrets.compare_digest(password, settings.basic_auth_password)
        return user_ok and pass_ok
    except Exception:
        return False


def _check_api_key(api_key: str) -> str | None:
    """Return the brand name if the key is valid, else None."""
    if not api_key:
        return None
    for key, brand in _KEY_TO_BRAND.items():
        if secrets.compare_digest(api_key, key):
            return brand
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        # 1) Try X-API-Key
        brand = _check_api_key(request.headers.get("X-API-Key", ""))
        if brand:
            request.state.brand = brand
            return await call_next(request)

        # 2) Fall back to Basic Auth
        if _check_basic_auth(request.headers.get("Authorization", "")):
            request.state.brand = None
            return await call_next(request)

        return Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Fabric Visualizer"'},
        )


app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")

# Register routers
app.include_router(fabrics.router)
app.include_router(furniture.router)
app.include_router(scraper.router)
app.include_router(visualize.router)
app.include_router(catalog.router)

@app.on_event("startup")
def startup():
    init_db()
    # Preload rembg U2-Net model so the first visualization request
    # doesn't pay the 2-3 second cold-start penalty.
    try:
        from rembg import remove as _rembg_remove
        from PIL import Image as _Image
        import numpy as _np
        _dummy = _Image.fromarray(_np.zeros((10, 10, 3), dtype=_np.uint8))
        _rembg_remove(_dummy)
        print("[startup] rembg U2-Net model preloaded")
    except Exception as e:
        print(f"[startup] rembg preload skipped: {e}")


@app.get("/api/health")
def health():
    import os as _os
    raw = settings.brand_api_keys or ""
    parse_error = None
    try:
        json.loads(raw)
    except Exception as e:
        parse_error = str(e)
    # List FV_-prefixed env vars by name only (values redacted) so we can
    # see what Railway is actually injecting into the container.
    fv_env_names = sorted(k for k in _os.environ if k.startswith("FV_"))
    # Also check the raw env var directly, bypassing pydantic
    raw_env = _os.environ.get("FV_BRAND_API_KEYS", "<missing>")
    return {
        "status": "ok",
        "ai_enabled": bool(settings.replicate_api_token),
        "openai_enabled": bool(settings.openai_api_key),
        "brand_keys_loaded": len(BRAND_API_KEYS),
        "brand_names": list(BRAND_API_KEYS.keys()),
        "brand_keys_raw_len": len(raw),
        "brand_keys_raw_first8": raw[:8],
        "brand_keys_parse_error": parse_error,
        "fv_env_var_names": fv_env_names,
        "raw_env_first8": raw_env[:8] if raw_env != "<missing>" else "<missing>",
        "raw_env_len": len(raw_env) if raw_env != "<missing>" else 0,
    }


# Serve built frontend — MUST be last so it doesn't shadow /api routes
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA for any non-API route."""
        if full_path.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file_path = FRONTEND_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
