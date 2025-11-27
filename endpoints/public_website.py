from fastapi import APIRouter, Request
from templating import templates

router = APIRouter()


@router.get("/")
async def landing_page(request: Request):
    return templates.TemplateResponse(
        "public_website_landing.html", {"request": request}
    )
