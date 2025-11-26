import os
from urllib.parse import quote_plus

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


class Settings:
    class Env:
        # Prefer a single DATABASE_URL env var (supports full DB URLs such as Postgres)
        DATABASE_URL = os.environ.get("DATABASE_URL")

        DB_USER = os.environ.get("DB_USER")
        DB_PASS = os.environ.get("DB_PASS")
        DB_NAME = os.environ.get("DB_NAME")
        DB_HOST = os.environ.get("DB_HOST")
        DB_PORT = os.environ.get("DB_PORT")
        LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

        # Backwards compatible JWT env names
        JWT_SECRET = os.environ.get("JWT_SECRET")
        JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM")
        JWT_EXPIRES_SECONDS = os.environ.get("JWT_EXPIRES_SECONDS")

        # New env names requested by user
        SECRET_KEY = os.environ.get("SECRET_KEY")
        ALGORITHM = os.environ.get("ALGORITHM")
        # Keep JWT_EXPIRES_SECONDS as fallthrough

    env = Env
    log_level = env.LOG_LEVEL.upper()

    # If DATABASE_URL is provided, use it directly (handles full DB URLs like Postgres).
    if env.DATABASE_URL:
        ALCHEMY_DB_URL = env.DATABASE_URL
    else:
        # Strip whitespace from individual parts and build a postgres URL
        user = (env.DB_USER or "").strip()
        password = (env.DB_PASS or "").strip()
        name = (env.DB_NAME or "").strip()
        host = (env.DB_HOST or "").strip()
        port = (env.DB_PORT or "5432").strip()

        # URL-encode credentials
        user_enc = quote_plus(user) if user else ""
        pass_enc = quote_plus(password) if password else ""

        if user_enc and pass_enc:
            creds = f"{user_enc}:{pass_enc}@"
        elif user_enc:
            creds = f"{user_enc}@"
        else:
            creds = ""

        ALCHEMY_DB_URL = f"postgresql://{creds}{host}:{port}/{name}"

    # Resolve secret and algorithm: prefer new names (SECRET_KEY/ALGORITHM), then fallback to JWT_* env names, then defaults
    SECRET_KEY = env.SECRET_KEY or env.JWT_SECRET or "change-this-secret"
    ALGORITHM = env.ALGORITHM or env.JWT_ALGORITHM or "HS256"

    # token lifetime (seconds)
    try:
        JWT_EXPIRES_SECONDS = (
            int(env.JWT_EXPIRES_SECONDS)
            if env.JWT_EXPIRES_SECONDS is not None
            else 60 * 60 * 24
        )
    except Exception:
        JWT_EXPIRES_SECONDS = 60 * 60 * 24

    # Backwards compatible aliases
    JWT_SECRET = SECRET_KEY
    JWT_ALGORITHM = ALGORITHM


settings = Settings()
