"""Configuración de la aplicación (se alimenta de variables de entorno)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

try:  # .env opcional (desarrollo); debe cargarse antes de leer las variables
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def normalizar_url(url: str) -> str:
    """Fuerza el driver psycopg2 (el instalado) para cualquier URL de PostgreSQL.

    Render/Heroku entregan ``postgres://`` y SQLAlchemy 2.1 usaría por defecto el
    driver ``psycopg`` (v3) con ``postgresql://``; así se evita ambos problemas.
    """
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg2://" + url[len(prefijo):]
    return url


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{INSTANCE_DIR / 'arequipa_house.db'}"
    return normalizar_url(url)


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Cookies de sesión
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1" if APP_ENV == "production" else "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Archivos subidos (fotos de viviendas)
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(INSTANCE_DIR / "uploads"))
    MODELS_FOLDER = os.environ.get("MODELS_FOLDER", str(INSTANCE_DIR / "models"))
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB por petición
    MAX_PHOTOS_PER_LISTING = 8
    MAX_PHOTO_BYTES = 6 * 1024 * 1024

    # Machine Learning
    ML_MIN_ROWS = int(os.environ.get("ML_MIN_ROWS", "60"))
    ML_SYNTHETIC_ROWS = int(os.environ.get("ML_SYNTHETIC_ROWS", "4000"))
    ML_N_JOBS = int(os.environ.get("ML_N_JOBS", "1"))
    ML_RANDOM_STATE = 42

    # Seguridad de acceso
    MAX_FAILED_LOGINS = 5
    LOCK_MINUTES = 10

    # Arranque
    AUTO_BOOTSTRAP = os.environ.get("AUTO_BOOTSTRAP", "1") == "1"
    SEED_DEMO = os.environ.get("SEED_DEMO", "0") == "1"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@arequipahouse.pe")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    WTF_CSRF_TIME_LIMIT = None
    PER_PAGE = 12


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False
    # Por defecto SQLite en memoria; TEST_DATABASE_URL permite correr la suite sobre PostgreSQL.
    SQLALCHEMY_DATABASE_URI = normalizar_url(os.environ.get("TEST_DATABASE_URL") or "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AUTO_BOOTSTRAP = False
    SEED_DEMO = False
    ML_SYNTHETIC_ROWS = 700
    ML_MIN_ROWS = 60
    SESSION_COOKIE_SECURE = False
