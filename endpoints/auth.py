from fastapi import APIRouter, Request, Form, HTTPException, Depends
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from typing import Callable, Any
from templating import templates
from database import (
    create_shared_user,
    SessionLocal as _SessionLocal,
    ensure_shared_schema_and_tables,
)
from models import User, SHARED_SCHEMA
from settings import settings
from sqlalchemy import text
import jwt
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

# Mark public routes
from utils import auth as utils_auth

# i18n dependency
from i18n import i18n_dependency

router = APIRouter()


class TokenRequest(BaseModel):
    username: str
    password: str


def _decode_token(token: str):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request):
    token = None
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    payload = _decode_token(token)
    # Minimal user info returned from shared users table
    db = _SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        user = (
            db.query(User)
            .filter(
                User.username == payload.get("sub"),
                User.tenant_schema == payload.get("tenant_schema"),
            )
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {
            "username": user.username,
            "tenant_schema": user.tenant_schema,
            "is_active": user.is_active,
            "email": user.email,
        }
    finally:
        db.close()


@utils_auth.public_route
@router.get("/login", response_class=HTMLResponse)
async def login_get(
    request: Request, _: Callable[[str, Any], str] = Depends(i18n_dependency)
):
    # pass translator into template
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None, "_": _}
    )


@utils_auth.public_route
@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
):
    # Ensure shared schema exists and tables are created
    ensure_shared_schema_and_tables()
    db = _SessionLocal()
    try:
        # Operate in shared schema for auth
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        user = db.query(User).filter(User.username == username).first()
        if not user:
            # Return to login form with error
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": _("login.invalid_credentials"),
                    "_": _,
                },
            )
        # Verify password using database utility
        from database import _verify_password

        if not _verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": _("login.invalid_credentials"),
                    "_": _,
                },
            )

        # Build JWT payload with tenant info (use timezone-aware timestamps)
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=settings.JWT_EXPIRES_SECONDS)
        payload = {
            "sub": user.username,
            "tenant_schema": user.tenant_schema,
            "is_active": user.is_active,
            "email": user.email,
            "exp": exp,
            "iat": now,
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        # For browser-based flow, set token in cookie and redirect to members page
        response = RedirectResponse(url="/members", status_code=302)
        response.set_cookie("access_token", token, httponly=True)
        return response
    finally:
        db.close()


@utils_auth.public_route
@router.post("/api/token")
async def api_token(req: TokenRequest):
    """Programmatic login: accept JSON username/password and return JWT and token_type."""
    ensure_shared_schema_and_tables()
    db = _SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        user = db.query(User).filter(User.username == req.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        from database import _verify_password

        if not _verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=settings.JWT_EXPIRES_SECONDS)
        payload = {
            "sub": user.username,
            "tenant_schema": user.tenant_schema,
            "is_active": user.is_active,
            "email": user.email,
            "exp": exp,
            "iat": now,
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}
    finally:
        db.close()


@router.get("/api/me")
async def api_me(current_user=Depends(get_current_user)):
    # Ensure current_user includes email when available
    user = current_user
    if isinstance(user, dict) and "email" not in user:
        # Try to look up email in shared users table if missing
        from database import SessionLocal
        from sqlalchemy import text
        from models import SHARED_SCHEMA

        db = SessionLocal()
        try:
            db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
            u = (
                db.query(User)
                .filter(
                    User.username == user.get("username"),
                    User.tenant_schema == user.get("tenant_schema"),
                )
                .first()
            )
            if u and getattr(u, "email", None):
                user["email"] = u.email
        finally:
            db.close()
    return user


@utils_auth.public_route
@router.get("/logout")
@router.post("/logout")
async def logout():
    # Use RedirectResponse and set an empty cookie with max_age=0 to clear it
    response = RedirectResponse(url="/login", status_code=302)
    # Set cookie to empty and expire immediately
    response.set_cookie(
        "access_token", "", httponly=True, path="/", max_age=0, expires=0
    )
    # Also call delete_cookie for extra compatibility
    response.delete_cookie("access_token", path="/")
    return response


@utils_auth.public_route
@router.post("/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    tenant_schema: str = Form("tenant1"),
):
    # helper to create a user in shared schema
    try:
        user = create_shared_user(username, password, tenant_schema, is_active=True)
        return JSONResponse(
            {
                "status": "ok",
                "username": user.username,
                "tenant_schema": user.tenant_schema,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
