"""Settings page endpoint and actions."""

from fastapi import APIRouter, Depends, Form
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from templating import templates
from database import (
    SessionLocal,
    ensure_shared_schema_and_tables,
    _verify_password,
    _hash_password,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from models import User, SHARED_SCHEMA
from typing import Callable, Any
from i18n import i18n_dependency

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request, _: Callable[[str, Any], str] = Depends(i18n_dependency)
):
    """Render settings page. Messages may be supplied in template context."""
    return templates.TemplateResponse("settings.html", {"request": request})


@router.post("/settings/update-email", response_class=HTMLResponse)
async def update_email(
    request: Request,
    email: str = Form(...),
    current_password: str = Form(...),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
):
    """Update user's email in the shared users table after verifying current password."""
    # Require authenticated user (middleware sets request.state.user)
    user_state = getattr(request.state, "user", None)
    if not user_state:
        return RedirectResponse(url="/login", status_code=302)

    username = user_state.get("username")
    tenant = (
        getattr(request.state, "tenant", None)
        or user_state.get("tenant_schema")
        or user_state.get("tenant")
    )

    ensure_shared_schema_and_tables()
    db = SessionLocal()
    try:
        # operate against shared schema
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        db_user = (
            db.query(User)
            .filter(User.username == username, User.tenant_schema == tenant)
            .first()
        )
        if not db_user:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": _("settings.user_not_found")},
            )
        # verify password
        if not _verify_password(current_password, db_user.password_hash):
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": _("settings.password_incorrect")},
            )
        # ensure email uniqueness (allow unchanged email)
        if email and email != db_user.email:
            existing_email = db.query(User).filter(User.email == email).first()
            if existing_email:
                return templates.TemplateResponse(
                    "settings.html",
                    {"request": request, "error": _("settings.email_in_use")},
                )
        # update email
        db_user.email = email
        db.add(db_user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": _("settings.email_in_use")},
            )
        # update in-memory request state so template shows new email immediately
        try:
            if hasattr(request, "state") and getattr(request.state, "user", None):
                request.state.user["email"] = email
        except Exception:
            # ignore any errors updating in-memory state; the DB commit already succeeded
            pass
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "message": _("settings.email_updated")},
        )
    finally:
        db.close()


@router.post("/settings/change-password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
):
    """Change user's password after verifying current password and matching confirmation."""
    user_state = getattr(request.state, "user", None)
    if not user_state:
        return RedirectResponse(url="/login", status_code=302)

    username = user_state.get("username")
    tenant = (
        getattr(request.state, "tenant", None)
        or user_state.get("tenant_schema")
        or user_state.get("tenant")
    )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": _("settings.password_mismatch")},
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": _("settings.password_too_short")},
        )

    ensure_shared_schema_and_tables()
    db = SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        db_user = (
            db.query(User)
            .filter(User.username == username, User.tenant_schema == tenant)
            .first()
        )
        if not db_user:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": _("settings.user_not_found")},
            )
        if not _verify_password(current_password, db_user.password_hash):
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": _("settings.password_incorrect")},
            )
        # set new password hash
        db_user.password_hash = _hash_password(new_password)
        db.add(db_user)
        db.commit()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "message": _("settings.password_updated")},
        )
    finally:
        db.close()
