from typing import Iterable
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from settings import settings
from fastapi import HTTPException
from database import SessionLocal
from models import User

# Default public paths (prefix matching)
DEFAULT_PUBLIC_PATHS = [
    "/",  # make landing page available at the root without requiring auth
    "/login",
    "/signup",
    "/api/token",
    "/static/",
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/set-language",
]


def get_public_paths() -> Iterable[str]:
    # allow override via settings; ensure it's a list for runtime additions
    p = getattr(settings, "PUBLIC_PATHS", None)
    if p is None:
        settings.PUBLIC_PATHS = list(DEFAULT_PUBLIC_PATHS)
        return settings.PUBLIC_PATHS
    return p


def is_public_path(path: str) -> bool:
    # Consider a path public if it matches any prefix in PUBLIC_PATHS
    for p in get_public_paths():
        # Special-case the root "/": treat it as an exact-match only so we don't
        # accidentally make every route public (because every path starts with "/").
        if p == "/":
            if path == "/":
                return True
            continue

        if p.endswith("/"):
            if path.startswith(p):
                return True
        else:
            if path == p or path.startswith(p + "/"):
                return True
    return False


def unauth_response(request: Request):
    """Return appropriate unauthenticated response: redirect to /login for HTML requests,
    or JSON 401 for API requests.
    """
    accept = request.headers.get("accept", "")
    # If the request explicitly asks for JSON treat as API
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    # For non-JSON or browser, redirect to login
    return RedirectResponse(url="/login")


def require_authenticated_or_redirect(request: Request):
    """Helper used in endpoints: returns None if authenticated, otherwise a Response to return to client."""
    if getattr(request.state, "user", None):
        return None
    return unauth_response(request)


# --- Public route decorator and registration helper ---


def public_route(func):
    """Decorator to mark a route function as public; middleware will register its path at startup.

    Usage:
        @public_route
        @router.get('/login')
        def login(...):
            ...
    """
    setattr(func, "__public__", True)
    return func


def register_public_path(path: str):
    """Add a path (or prefix) to the runtime PUBLIC_PATHS list used by middleware."""
    p = getattr(settings, "PUBLIC_PATHS", None)
    if p is None:
        settings.PUBLIC_PATHS = list(DEFAULT_PUBLIC_PATHS)
        p = settings.PUBLIC_PATHS
    if path not in p:
        p.append(path)


# --- Admin requirement dependency ---


def require_admin(request: Request):
    """Dependency to require admin user. Uses settings.ADMIN_USERS (comma-separated) as primary check.
    Falls back to checking a hypothetical `is_admin` column on the shared.users table if present.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    username = user.get("username")
    # Check ADMIN_USERS env var (comma separated)
    admin_list = getattr(settings, "ADMIN_USERS", None)
    if admin_list:
        # normalize
        admins = [a.strip() for a in admin_list.split(",") if a.strip()]
        if username in admins:
            return True

    # Fallback: check shared.users.is_admin if the column exists (safe query)
    db = SessionLocal()
    try:
        # ensure we query shared schema
        from sqlalchemy import text

        db.execute(text(f'SET search_path TO "{User.__table__.schema}", public'))
        u = (
            db.query(User)
            .filter(
                User.username == username,
                User.tenant_schema == user.get("tenant_schema"),
            )
            .first()
        )
        if u is None:
            raise HTTPException(status_code=403, detail="Not authorized")
        # If the model has is_admin attribute, use it (it's an attribute on SQLAlchemy model)
        if hasattr(u, "is_admin"):
            if getattr(u, "is_admin"):
                return True
            else:
                raise HTTPException(status_code=403, detail="Admin required")
        # If no is_admin column, require username be in ADMIN_USERS only -- already checked above
        raise HTTPException(status_code=403, detail="Admin required")
    finally:
        db.close()
