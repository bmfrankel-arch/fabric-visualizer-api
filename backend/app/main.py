from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db
from .routers import fabrics, furniture, scraper, visualize, catalog

app = FastAPI(title=settings.app_name)

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
    return {
        "status": "ok",
        "ai_enabled": bool(settings.replicate_api_token),
        "openai_enabled": bool(settings.openai_api_key),
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
