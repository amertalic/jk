from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from starlette.responses import HTMLResponse, RedirectResponse
from templating import templates
from i18n import i18n_dependency
from typing import Callable, Any, Optional
from database import get_db
from sqlalchemy.orm import Session
from models import Member, Level, Location
from constants import SEX_CHOICES, MEMBER_STATUS_CHOICES

router = APIRouter()


@router.get("/members", response_class=HTMLResponse)
async def members_list_page(
    request: Request,
    page: int = 1,
    per_page: int = 12,
    q: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sex: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    """Render members list page (paginated)."""

    # Accept empty location param ('' from the select -> means no filter).
    loc_id: Optional[int] = None
    if location is not None and location != "":
        try:
            loc_id = int(location)
        except Exception:
            loc_id = None

    # Base query (apply optional filters)
    from sqlalchemy import or_

    query = db.query(Member)
    # location filter
    if loc_id:
        query = query.filter(Member.location_id == loc_id)
    # level filter (accept empty string as no-filter)
    level_id = None
    if level is not None and level != "":
        try:
            level_id = int(level)
        except Exception:
            level_id = None
    if level_id:
        query = query.filter(Member.level_id == level_id)
    # status filter
    if status and status != "":
        allowed_status = {v for v, _ in MEMBER_STATUS_CHOICES}
        if status in allowed_status:
            query = query.filter(Member.status == status)
    # sex filter
    if sex and sex != "":
        allowed_sex = {v for v, _ in SEX_CHOICES}
        if sex in allowed_sex:
            query = query.filter(Member.sex == sex)
    # combined name/surname search
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(Member.name.ilike(term), Member.surname.ilike(term)))

    total = query.count()
    # compute last page and clamp page to a valid value to avoid empty results when filters reduce total
    last_page_calc = max(1, (total + per_page - 1) // per_page)
    if page < 1 or page > last_page_calc:
        page = 1
    offset = (page - 1) * per_page
    members = query.order_by(Member.id.asc()).offset(offset).limit(per_page).all()
    members_list = [
        {
            "id": m.id,
            "name": m.name,
            "surname": m.surname,
            "date_of_birth": getattr(m, "date_of_birth", None),
            "sex": getattr(m, "sex", None),
            "status": getattr(m, "status", None),
            "level_id": getattr(m, "level_id", None),
            "location_id": getattr(m, "location_id", None),
        }
        for m in members
    ]
    # prepare maps for template (value -> translation key)
    sex_map = {v: k for v, k in SEX_CHOICES}
    status_map = {v: k for v, k in MEMBER_STATUS_CHOICES}
    # also build level id -> name mapping so templates can call translation keys like "level.<name>"
    levels_all = db.query(Level).all()
    level_map = {l.id: l.name for l in levels_all}
    # fetch locations and build id->name mapping for display and filtering
    locations_all = db.query(Location).order_by(Location.name.asc()).all()
    location_map = {loc.id: loc.name for loc in locations_all}
    last_page = last_page_calc
    # If request is from HTMX, return partial fragment only
    is_hx = request.headers.get("hx-request") == "true"
    ctx = {
        "request": request,
        "members": members_list,
        "page": page,
        "per_page": per_page,
        "total": total,
        "last_page": last_page,
        "_": _,
        "sex_choices": SEX_CHOICES,
        "status_choices": MEMBER_STATUS_CHOICES,
        "sex_map": sex_map,
        "status_map": status_map,
        "level_map": level_map,
        "levels": levels_all,
        "locations": locations_all,
        "location_map": location_map,
        "current_location": loc_id,
        "current_q": q,
        "current_level": level_id,
        "current_status": status,
        "current_sex": sex,
    }
    if is_hx:
        return templates.TemplateResponse("members_list_fragment.html", ctx)
    return templates.TemplateResponse("members.html", ctx)


@router.get("/members/create", response_class=HTMLResponse)
async def members_create_get(
    request: Request,
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    levels = db.query(Level).order_by(Level.rank.asc()).all()
    locations = db.query(Location).order_by(Location.name.asc()).all()
    return templates.TemplateResponse(
        "member_form.html",
        {
            "request": request,
            "action": "/members/create",
            "member": None,
            "levels": levels,
            "locations": locations,
            "_": _,
            "sex_choices": SEX_CHOICES,
            "status_choices": MEMBER_STATUS_CHOICES,
        },
    )


@router.post("/members/create")
async def members_create_post(
    request: Request,
    name: str = Form(...),
    surname: str = Form(...),
    date_of_birth: str = Form(...),
    sex: str = Form(...),
    status: str = Form(...),
    level_id: int = Form(...),
    location_id: int = Form(...),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    # Validate sex and status
    allowed_sex = {v for v, _ in SEX_CHOICES}
    allowed_status = {v for v, _ in MEMBER_STATUS_CHOICES}
    if sex and sex not in allowed_sex:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        return templates.TemplateResponse(
            "member_form.html",
            {
                "request": request,
                "action": "/members/create",
                "member": {
                    "name": name,
                    "surname": surname,
                    "date_of_birth": date_of_birth,
                    "sex": sex,
                    "status": status,
                    "level_id": level_id,
                    "location_id": location_id,
                },
                "levels": levels,
                "locations": locations,
                "error": "Invalid sex value",
                "_": _,
                "sex_choices": SEX_CHOICES,
                "status_choices": MEMBER_STATUS_CHOICES,
            },
        )
    if status and status not in allowed_status:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        return templates.TemplateResponse(
            "member_form.html",
            {
                "request": request,
                "action": "/members/create",
                "member": {
                    "name": name,
                    "surname": surname,
                    "date_of_birth": date_of_birth,
                    "sex": sex,
                    "status": status,
                    "level_id": level_id,
                    "location_id": location_id,
                },
                "levels": levels,
                "locations": locations,
                "error": "Invalid status value",
                "_": _,
                "sex_choices": SEX_CHOICES,
                "status_choices": MEMBER_STATUS_CHOICES,
            },
        )

    # Create member in tenant schema (get_db sets search_path)
    m = Member(
        name=name,
        surname=surname,
        date_of_birth=date_of_birth,
        sex=sex,
        status=status,
        level_id=level_id,
        location_id=location_id,
    )
    db.add(m)
    db.commit()
    return RedirectResponse(url="/members", status_code=302)


@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
async def members_edit_get(
    request: Request,
    member_id: int,
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    m = db.query(Member).filter(Member.id == member_id).first()
    if not m:
        return RedirectResponse(url="/members", status_code=302)
    levels = db.query(Level).order_by(Level.rank.asc()).all()
    locations = db.query(Location).order_by(Location.name.asc()).all()
    return templates.TemplateResponse(
        "member_form.html",
        {
            "request": request,
            "action": f"/members/{member_id}/edit",
            "member": m,
            "levels": levels,
            "locations": locations,
            "_": _,
            "sex_choices": SEX_CHOICES,
            "status_choices": MEMBER_STATUS_CHOICES,
        },
    )


@router.post("/members/{member_id}/edit")
async def members_edit_post(
    request: Request,
    member_id: int,
    name: str = Form(...),
    surname: str = Form(...),
    date_of_birth: str = Form(...),
    sex: str = Form(...),
    status: str = Form(...),
    level_id: int = Form(...),
    location_id: int = Form(...),
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    m = db.query(Member).filter(Member.id == member_id).first()
    if not m:
        return RedirectResponse(url="/members", status_code=302)

    # Validate sex and status
    allowed_sex = {v for v, _ in SEX_CHOICES}
    allowed_status = {v for v, _ in MEMBER_STATUS_CHOICES}
    if sex and sex not in allowed_sex:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        return templates.TemplateResponse(
            "member_form.html",
            {
                "request": request,
                "action": f"/members/{member_id}/edit",
                "member": m,
                "levels": levels,
                "locations": locations,
                "error": "Invalid sex value",
                "_": _,
                "sex_choices": SEX_CHOICES,
                "status_choices": MEMBER_STATUS_CHOICES,
            },
        )
    if status and status not in allowed_status:
        levels = db.query(Level).order_by(Level.rank.asc()).all()
        locations = db.query(Location).order_by(Location.name.asc()).all()
        return templates.TemplateResponse(
            "member_form.html",
            {
                "request": request,
                "action": f"/members/{member_id}/edit",
                "member": m,
                "levels": levels,
                "locations": locations,
                "error": "Invalid status value",
                "_": _,
                "sex_choices": SEX_CHOICES,
                "status_choices": MEMBER_STATUS_CHOICES,
            },
        )

    m.name = name
    m.surname = surname
    m.date_of_birth = date_of_birth
    m.sex = sex
    m.status = status
    m.level_id = level_id
    m.location_id = location_id
    db.add(m)
    db.commit()
    return RedirectResponse(url="/members", status_code=302)


@router.post("/members/{member_id}/delete")
async def members_delete(
    request: Request,
    member_id: int,
    _: Callable[[str, Any], str] = Depends(i18n_dependency),
    db: Session = Depends(get_db),
):
    m = db.query(Member).filter(Member.id == member_id).first()
    if not m:
        return RedirectResponse(url="/members", status_code=302)
    db.delete(m)
    db.commit()
    return RedirectResponse(url="/members", status_code=302)


# JSON API endpoints for members
@router.get("/api/members")
async def api_members_list(
    page: int = 1,
    per_page: int = 25,
    db: Session = Depends(get_db),
    request: Request = None,
):
    total = db.query(Member).count()
    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    members = (
        db.query(Member).order_by(Member.id.asc()).offset(offset).limit(per_page).all()
    )
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "members": [
            {
                "id": m.id,
                "name": m.name,
                "surname": m.surname,
                "sex": m.sex,
                "status": m.status,
                "level_id": m.level_id,
                "location_id": m.location_id,
            }
            for m in members
        ],
    }


@router.post("/api/members")
async def api_members_create(
    payload: dict, db: Session = Depends(get_db), request: Request = None
):
    required = ("name", "surname", "date_of_birth")
    for k in required:
        if not payload.get(k):
            raise HTTPException(status_code=400, detail=f"{k} is required")
    # Validate sex/status
    allowed_sex = {v for v, _ in SEX_CHOICES}
    allowed_status = {v for v, _ in MEMBER_STATUS_CHOICES}
    if payload.get("sex") and payload.get("sex") not in allowed_sex:
        raise HTTPException(status_code=400, detail="Invalid sex value")
    if payload.get("status") and payload.get("status") not in allowed_status:
        raise HTTPException(status_code=400, detail="Invalid status value")
    m = Member(
        name=payload.get("name"),
        surname=payload.get("surname"),
        date_of_birth=payload.get("date_of_birth"),
        sex=payload.get("sex"),
        status=payload.get("status"),
        level_id=payload.get("level_id"),
        location_id=payload.get("location_id"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id}


@router.put("/api/members/{member_id}")
async def api_members_update(
    member_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    request: Request = None,
):
    m = db.query(Member).filter(Member.id == member_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    allowed_sex = {v for v, _ in SEX_CHOICES}
    allowed_status = {v for v, _ in MEMBER_STATUS_CHOICES}
    if (
        "sex" in payload
        and payload.get("sex")
        and payload.get("sex") not in allowed_sex
    ):
        raise HTTPException(status_code=400, detail="Invalid sex value")
    if (
        "status" in payload
        and payload.get("status")
        and payload.get("status") not in allowed_status
    ):
        raise HTTPException(status_code=400, detail="Invalid status value")
    for k in (
        "name",
        "surname",
        "date_of_birth",
        "sex",
        "status",
        "level_id",
        "location_id",
    ):
        if k in payload:
            setattr(m, k, payload.get(k))
    db.add(m)
    db.commit()
    return {"status": "ok"}


@router.delete("/api/members/{member_id}")
async def api_members_delete(
    member_id: int, db: Session = Depends(get_db), request: Request = None
):
    m = db.query(Member).filter(Member.id == member_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(m)
    db.commit()
    return {"status": "ok"}
