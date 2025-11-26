# Copy of utils/auth.py placed under app_utils to avoid import conflicts with top-level utils.py
from typing import Iterable
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from settings import settings

# Default public paths (prefix matching)
DEFAULT_PUBLIC_PATHS = [
    "/login",
    "/api/token",
    "/static/",
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/set-language",
]


def get_public_paths() -> Iterable[str]:
    p = getattr(settings, "PUBLIC_PATHS", None)
    if p is None:
        settings.PUBLIC_PATHS = list(DEFAULT_PUBLIC_PATHS)
        return settings.PUBLIC_PATHS
    return p


def is_public_path(path: str) -> bool:
    for p in get_public_paths():
        if p.endswith("/"):
            if path.startswith(p):
                return True
        else:
            if path == p or path.startswith(p + "/"):
                return True
    return False


def unauth_response(request: Request):
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return RedirectResponse(url="/login")


def require_authenticated_or_redirect(request: Request):
    if getattr(request.state, "user", None):
        return None
    return unauth_response(request)


# Public route decorator and registration helper


def public_route(func):
    setattr(func, "__public__", True)
    return func


def register_public_path(path: str):
    p = getattr(settings, "PUBLIC_PATHS", None)
    if p is None:
        settings.PUBLIC_PATHS = list(DEFAULT_PUBLIC_PATHS)
        p = settings.PUBLIC_PATHS
    if path not in p:
        p.append(path)


# Admin dependency
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest
from database import SessionLocal
from models import User


def require_admin(request: StarletteRequest):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    username = user.get("username")
    admin_list = getattr(settings, "ADMIN_USERS", None)
    if admin_list:
        admins = [a.strip() for a in admin_list.split(",") if a.strip()]
        if username in admins:
            return True

    db = SessionLocal()
    try:
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
        if hasattr(u, "is_admin"):
            if getattr(u, "is_admin"):
                return True
            else:
                raise HTTPException(status_code=403, detail="Admin required")
        raise HTTPException(status_code=403, detail="Admin required")
    finally:
        db.close()
