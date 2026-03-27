import os
from pydantic_settings import BaseSettings
from pathlib import Path

# Load .env file from the backend directory before Settings is initialized.
# This works regardless of the working directory uvicorn starts from.
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip()
            if _key and _key not in os.environ:  # real env vars take priority
                os.environ[_key] = _val


class Settings(BaseSettings):
    app_name: str = "Fabric Visualizer"
    upload_dir: Path = Path(__file__).parent.parent / "static" / "uploads"
    fabrics_dir: Path = Path(__file__).parent.parent / "static" / "uploads" / "fabrics"
    furniture_dir: Path = Path(__file__).parent.parent / "static" / "uploads" / "furniture"
    database_path: Path = Path(__file__).parent.parent / "data.db"
    max_upload_size: int = 20 * 1024 * 1024  # 20MB

    # HTTP Basic Auth (set FV_BASIC_AUTH_USERNAME / FV_BASIC_AUTH_PASSWORD env vars)
    basic_auth_username: str = "myusername"
    basic_auth_password: str = "mypassword"

    # AI API settings (optional - enables AI-powered fabric application)
    replicate_api_token: str = ""
    stability_api_key: str = ""
    openai_api_key: str = ""  # FV_OPENAI_API_KEY env var

    model_config = {"env_prefix": "FV_", "extra": "ignore"}


settings = Settings()

# Ensure directories exist
settings.fabrics_dir.mkdir(parents=True, exist_ok=True)
settings.furniture_dir.mkdir(parents=True, exist_ok=True)
