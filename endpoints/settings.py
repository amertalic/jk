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
    get_db,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from models import User, SHARED_SCHEMA, Location, Level, PaymentPrice, Member, Payment
from typing import Callable
from i18n import i18n_dependency
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    """Render settings page. Messages may be supplied in template context.

    Also provide current lists of locations, levels and payment prices for management.
    """
    levels = db.query(Level).order_by(Level.rank.asc()).all()
    locations = db.query(Location).order_by(Location.name.asc()).all()
    prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "levels": levels, "locations": locations, "prices": prices, "_": tr},
    )


@router.post("/settings/update-email", response_class=HTMLResponse)
async def update_email(
    request: Request,
    email: str = Form(...),
    current_password: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
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
    shared_db = SessionLocal()
    try:
        # operate against shared schema
        shared_db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        db_user = (
            shared_db.query(User)
            .filter(User.username == username, User.tenant_schema == tenant)
            .first()
        )
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        if not db_user:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": tr("settings.user_not_found"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
            )
        # verify password
        if not _verify_password(current_password, db_user.password_hash):
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": tr("settings.password_incorrect"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
            )
        # ensure email uniqueness (allow unchanged email)
        if email and email != db_user.email:
            existing_email = shared_db.query(User).filter(User.email == email).first()
            if existing_email:
                return templates.TemplateResponse(
                    "settings.html",
                    {"request": request, "error": tr("settings.email_in_use"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
                )
        # update email
        db_user.email = email
        shared_db.add(db_user)
        try:
            shared_db.commit()
        except IntegrityError:
            shared_db.rollback()
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": tr("settings.email_in_use"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
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
            {"request": request, "message": tr("settings.email_updated"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    finally:
        shared_db.close()


@router.post("/settings/change-password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
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

    levels = db.query(Level).order_by(Level.rank.asc()).all()
    locations = db.query(Location).order_by(Location.name.asc()).all()
    prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()

    if new_password != confirm_password:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.password_mismatch"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.password_too_short"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )

    ensure_shared_schema_and_tables()
    shared_db = SessionLocal()
    try:
        shared_db.execute(text(f'SET search_path TO "{SHARED_SCHEMA}", public'))
        db_user = (
            shared_db.query(User)
            .filter(User.username == username, User.tenant_schema == tenant)
            .first()
        )
        if not db_user:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": tr("settings.user_not_found"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
            )
        if not _verify_password(current_password, db_user.password_hash):
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "error": tr("settings.password_incorrect"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
            )
        # set new password hash
        db_user.password_hash = _hash_password(new_password)
        shared_db.add(db_user)
        shared_db.commit()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "message": tr("settings.password_updated"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    finally:
        shared_db.close()


# --- Settings CRUD for Location, Level and PaymentPrice ---

@router.post("/settings/locations/create")
async def settings_location_create(
    request: Request,
    name: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    if not name or not name.strip():
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.location_name_required"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    loc = Location(name=name.strip())
    db.add(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.location_exists"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/locations/{location_id}/edit")
async def settings_location_edit(
    request: Request,
    location_id: int,
    name: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        return RedirectResponse(url="/settings", status_code=302)
    if not name or not name.strip():
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.location_name_required"), "_": tr})
    loc.name = name.strip()
    db.add(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.location_exists"), "_": tr})
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/locations/{location_id}/delete")
async def settings_location_delete(
    request: Request,
    location_id: int,
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        return RedirectResponse(url="/settings", status_code=302)
    # Prevent deletion if members reference this location
    referenced = db.query(Member).filter(Member.location_id == location_id).first()
    if referenced:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.location_in_use"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    db.delete(loc)
    db.commit()
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/levels/create")
async def settings_level_create(
    request: Request,
    name: str = Form(...),
    rank: int = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    if not name or not name.strip():
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.level_name_required"), "_": tr})
    try:
        rank_int = int(rank)
    except Exception:
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.level_rank_invalid"), "_": tr})
    lvl = Level(name=name.strip(), rank=rank_int)
    db.add(lvl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.level_exists"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/levels/{level_id}/edit")
async def settings_level_edit(
    request: Request,
    level_id: int,
    name: str = Form(...),
    rank: int = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    lvl = db.query(Level).filter(Level.id == level_id).first()
    if not lvl:
        return RedirectResponse(url="/settings", status_code=302)
    if not name or not name.strip():
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.level_name_required"), "_": tr})
    try:
        rank_int = int(rank)
    except Exception:
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.level_rank_invalid"), "_": tr})
    lvl.name = name.strip()
    lvl.rank = rank_int
    db.add(lvl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.level_exists"), "_": tr})
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/levels/{level_id}/delete")
async def settings_level_delete(
    request: Request,
    level_id: int,
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    lvl = db.query(Level).filter(Level.id == level_id).first()
    if not lvl:
        return RedirectResponse(url="/settings", status_code=302)
    # Prevent deletion if members reference this level
    referenced = db.query(Member).filter(Member.level_id == level_id).first()
    if referenced:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.level_in_use"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    db.delete(lvl)
    db.commit()
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/prices/create")
async def settings_price_create(
    request: Request,
    amount: str = Form(...),
    description: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    if not description or not description.strip():
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.price_description_required"), "_": tr})
    try:
        amt = float(amount)
    except Exception:
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.price_amount_invalid"), "_": tr})
    p = PaymentPrice(amount=amt, description=description.strip())
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.price_exists"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/prices/{price_id}/edit")
async def settings_price_edit(
    request: Request,
    price_id: int,
    amount: str = Form(...),
    description: str = Form(...),
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    p = db.query(PaymentPrice).filter(PaymentPrice.id == price_id).first()
    if not p:
        return RedirectResponse(url="/settings", status_code=302)
    if not description or not description.strip():
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.price_description_required"), "_": tr})
    try:
        amt = float(amount)
    except Exception:
        return templates.TemplateResponse("settings.html", {"request": request, "error": tr("settings.price_amount_invalid"), "_": tr})
    p.amount = amt
    p.description = description.strip()
    db.add(p)
    db.commit()
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/settings/prices/{price_id}/delete")
async def settings_price_delete(
    request: Request,
    price_id: int,
    tr: Callable[..., str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    # Find the price object
    p = db.query(PaymentPrice).filter(PaymentPrice.id == price_id).first()
    if not p:
        return RedirectResponse(url="/settings", status_code=302)
    # Prevent deletion if payments reference this price
    referenced = db.query(Payment).filter(Payment.price_id == price_id).first()
    if referenced:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        prices = db.query(PaymentPrice).order_by(PaymentPrice.amount.asc()).all()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "error": tr("settings.price_in_use"), "levels": levels, "locations": locations, "prices": prices, "_": tr},
        )
    db.delete(p)
    db.commit()
    return RedirectResponse(url="/settings", status_code=302)

