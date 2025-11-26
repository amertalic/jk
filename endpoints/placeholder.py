from fastapi import APIRouter, Request, Depends
from starlette.responses import HTMLResponse
from templating import templates
from i18n import i18n_dependency
from typing import Callable, Any

router = APIRouter()


@router.get("/placeholder", response_class=HTMLResponse)
async def placeholder(
    request: Request, _: Callable[[str, Any], str] = Depends(i18n_dependency)
):
    return templates.TemplateResponse("placeholder.html", {"request": request})
