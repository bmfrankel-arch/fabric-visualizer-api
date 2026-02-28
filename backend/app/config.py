from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "Fabric Visualizer"
    upload_dir: Path = Path(__file__).parent.parent / "static" / "uploads"
    fabrics_dir: Path = Path(__file__).parent.parent / "static" / "uploads" / "fabrics"
    furniture_dir: Path = Path(__file__).parent.parent / "static" / "uploads" / "furniture"
    database_path: Path = Path(__file__).parent.parent / "data.db"
    max_upload_size: int = 20 * 1024 * 1024  # 20MB

    # AI API settings (optional - enables AI-powered fabric application)
    replicate_api_token: str = ""
    stability_api_key: str = ""

    model_config = {"env_prefix": "FV_"}


settings = Settings()

# Ensure directories exist
settings.fabrics_dir.mkdir(parents=True, exist_ok=True)
settings.furniture_dir.mkdir(parents=True, exist_ok=True)
