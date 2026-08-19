"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


DATAFORSEO_PRODUCTION_BASE_URL = "https://api.dataforseo.com/v3"
DATAFORSEO_DEFAULT_SANDBOX_BASE_URL = "https://sandbox.dataforseo.com/v3"


def dataforseo_base_url() -> str:
    """Resolve DataForSEO API base URL from sandbox flag and env overrides."""
    if _env_bool("DATAFORSEO_SANDBOX"):
        return os.getenv(
            "SANDBOX_BASE_URL", DATAFORSEO_DEFAULT_SANDBOX_BASE_URL
        ).rstrip("/")
    return DATAFORSEO_PRODUCTION_BASE_URL


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/ai_visibility",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

    DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN", "")
    DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD", "")
    DATAFORSEO_LOCATION_CODE = int(os.getenv("DATAFORSEO_LOCATION_CODE", "2840"))
    DATAFORSEO_LANGUAGE_CODE = os.getenv("DATAFORSEO_LANGUAGE_CODE", "en")
    DATAFORSEO_SANDBOX = _env_bool("DATAFORSEO_SANDBOX")
    SANDBOX_BASE_URL = os.getenv(
        "SANDBOX_BASE_URL", DATAFORSEO_DEFAULT_SANDBOX_BASE_URL
    ).rstrip("/")
    DATAFORSEO_BASE_URL = dataforseo_base_url()

    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
