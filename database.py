from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, SHARED_SCHEMA, User
import os
from dotenv import load_dotenv
from settings import settings
import re
from starlette.requests import Request
from fastapi import HTTPException
import hashlib
import base64
import hmac

# Load environment variables from .env (if present)
load_dotenv()


# Helper to redact sensitive info from a DB URL for safe logging
def redact_db_url(url: str) -> str:
    if not url:
        return url
    # postgres URL form: dialect+driver://user:pass@host:port/dbname
    try:
        if "@" in url and ":" in url.split("//", 1)[1]:
            # crude but effective redaction: replace between : and @ with ****
            pre, rest = url.split("//", 1)
            creds, hostpart = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{pre}//{user}:****@{hostpart}"
    except Exception:
        pass
    return url


engine = create_engine(settings.ALCHEMY_DB_URL)

# Derive a simple DB dialect/type for logging
DB_DIALECT = (
    settings.ALCHEMY_DB_URL.split(":", 1)[0] if settings.ALCHEMY_DB_URL else "unknown"
)
REDACTED_DATABASE_URL = redact_db_url(settings.ALCHEMY_DB_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def validate_schema_name(name: str):
    """Very small validation to avoid SQL injection in schema names.
    Only allow alphanumeric and underscore."""
    if not re.match(r"^[A-Za-z0-9_]+$", name):
        raise ValueError(
            "Invalid schema name. Only letters, numbers and underscore are allowed."
        )


def ensure_schema_exists(schema_name: str):
    """Create schema if it doesn't exist."""
    validate_schema_name(schema_name)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))


def create_tenant_schema_and_tables(tenant_schema: str):
    """Create a tenant schema and create application tables inside it.

    Strategy: temporarily set the .schema attribute on Table objects that don't
    already have a schema (i.e. tenant-specific tables), call create_all for
    those tables, then restore the original schema attributes.
    """
    validate_schema_name(tenant_schema)

    # Ensure the schema exists on the DB
    ensure_schema_exists(tenant_schema)

    # Prepare to set tenant schema on tables that don't already have one
    tables = list(Base.metadata.tables.values())
    original_schemas = {t: t.schema for t in tables}

    try:
        # Assign tenant schema to non-shared tables
        for t in tables:
            # If the table already has a schema (e.g., shared.users), leave it alone
            if t.schema is None:
                t.schema = tenant_schema

        # Create only the tables that we just assigned to the tenant schema
        tenant_tables = [t for t in tables if t.schema == tenant_schema]
        if tenant_tables:
            Base.metadata.create_all(bind=engine, tables=tenant_tables)
    finally:
        # Restore original schema attributes so we don't mutate global state
        for t, orig in original_schemas.items():
            t.schema = orig


def ensure_shared_schema_and_tables():
    """Create the shared schema and any tables defined with that schema (e.g. User).
    Call this once at startup.
    """
    ensure_schema_exists(SHARED_SCHEMA)
    # Create only tables that belong to the shared schema
    shared_tables = [
        t for t in Base.metadata.tables.values() if t.schema == SHARED_SCHEMA
    ]
    if shared_tables:
        Base.metadata.create_all(bind=engine, tables=shared_tables)


def _hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256.

    Returns a string with the format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
    """
    iterations = 100_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify a plaintext password against the stored PBKDF2 string."""
    try:
        algo, iterations_s, salt_b64, hash_b64 = stored.split("$", 3)
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def create_shared_user(
    username: str,
    password: str,
    tenant_schema: str,
    is_active: bool = True,
    email: str = None,
):
    """Create a user record in the shared schema. Raises ValueError if user exists."""
    validate_schema_name(tenant_schema)
    ensure_shared_schema_and_tables()
    db = SessionLocal()
    try:
        # Ensure we operate against the shared schema for this session
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        # Check uniqueness for username within tenant
        existing = (
            db.query(User)
            .filter(User.username == username, User.tenant_schema == tenant_schema)
            .first()
        )
        if existing:
            raise ValueError("User already exists for that tenant")

        # If email provided, ensure it's not already used by another user
        if email:
            email_exists = db.query(User).filter(User.email == email).first()
            if email_exists:
                raise ValueError("Email already in use")

        user = User(
            username=username,
            email=email,
            password_hash=_hash_password(password),
            tenant_schema=tenant_schema,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def create_tenant_with_admin(
    tenant_schema: str, admin_username: str, admin_password: str
):
    """Create the tenant schema and tables, then create an admin user in the shared schema."""
    validate_schema_name(tenant_schema)
    create_tenant_schema_and_tables(tenant_schema)
    return create_shared_user(
        admin_username, admin_password, tenant_schema, is_active=True
    )


def get_db(request: Request = None):
    """FastAPI dependency that yields a DB session.

    If the incoming request provides a tenant (header `X-Tenant` or query param
    `tenant`) that schema will be ensured and the session's search_path will be
    set so unqualified table names resolve to the tenant schema while the
    shared schema remains available for authentication/centralized data.

    If no tenant is supplied, falls back to DEFAULT_TENANT_SCHEMA env var if set
    or yields a session with the default search_path (no change).
    """
    db = SessionLocal()
    try:
        tenant = None
        # First, prefer tenant set by middleware on request.state (from decoded JWT)
        if (
            request is not None
            and hasattr(request, "state")
            and getattr(request.state, "tenant", None)
        ):
            tenant = request.state.tenant
        # Fallback to explicit header or query param if middleware didn't set it
        if not tenant and request is not None:
            tenant = request.headers.get("X-Tenant") or request.query_params.get(
                "tenant"
            )
        if not tenant:
            tenant = os.environ.get("DEFAULT_TENANT_SCHEMA")
        if tenant:
            try:
                validate_schema_name(tenant)
            except ValueError:
                db.close()
                raise HTTPException(status_code=400, detail="Invalid tenant identifier")
            # Ensure the tenant schema exists before setting search_path
            ensure_schema_exists(tenant)
            db.execute(
                text(f'SET search_path TO "{tenant}", "{SHARED_SCHEMA}", public')
            )
        yield db
    finally:
        db.close()


def get_tenant_db(tenant_schema: str):
    """Yield a DB session scoped to a tenant by setting Postgres search_path.

    Usage as a FastAPI dependency (factory) would look like:
      def get_tenant_db_dep(tenant: str = Depends(get_tenant_identifier)):
          yield from get_tenant_db(tenant)
    """
    validate_schema_name(tenant_schema)
    db = SessionLocal()
    try:
        # Ensure tenant schema exists in case it hasn't been created yet
        ensure_schema_exists(tenant_schema)
        # Set search_path so unqualified table names resolve to tenant schema,
        # while allowing access to shared schema (for auth) and public.
        db.execute(
            text(f'SET search_path TO "{tenant_schema}", "{SHARED_SCHEMA}", public')
        )
        yield db
    finally:
        db.close()


def init_db():
    """Create database objects that are required for the app to run.

    Behavior:
      - Create shared schema and its tables (users/auth)
      - Optionally create a default tenant/schema if configured via env var
    """
    # Create shared schema and tables
    ensure_shared_schema_and_tables()

    # Optionally create a default tenant schema if provided via env
    default_tenant = os.environ.get("DEFAULT_TENANT_SCHEMA")
    if default_tenant:
        create_tenant_schema_and_tables(default_tenant)
