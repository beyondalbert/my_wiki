"""Application configuration."""
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(env_value: str | None, default: bool = False) -> bool:
    if env_value is None:
        return default
    return env_value.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-please-change")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@127.0.0.1:3306/my_wiki?charset=utf8mb4",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7

    # Upload
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(32 * 1024 * 1024)))

    # AI
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

    AI_WIKI_DIR = os.getenv("AI_WIKI_DIR", str(BASE_DIR / "instance" / "ai_wiki"))

    # Optional RAG
    ENABLE_RAG = _bool(os.getenv("ENABLE_RAG"), False)
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    CHROMA_PATH = os.getenv("CHROMA_PATH", str(BASE_DIR / "instance" / "chroma"))

    # Captcha
    CAPTCHA_TTL_SECONDS = 300

    # Pagination
    DEFAULT_PAGE_SIZE = 20


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    name = (name or os.getenv("FLASK_CONFIG") or "development").lower()
    return CONFIG_MAP.get(name, DevelopmentConfig)
