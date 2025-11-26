from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
import i18n

# Mark public routes
from app_utils import auth as utils_auth

router = APIRouter()


@utils_auth.public_route
@router.post("/set-language")
async def set_language(request: Request, lang: str = Form(...)):
    """Set site language cookie and redirect back to referer or '/'.
    Expects a form post with `lang` value equal to one of the supported locales.
    """
    if lang not in i18n._SUPPORTED_LOCALES:
        # ignore unsupported values, redirect back
        referer = request.headers.get("referer", "/")
        return RedirectResponse(referer or "/", status_code=302)
    referer = request.headers.get("referer", "/") or "/"
    resp = RedirectResponse(referer, status_code=302)
    # set cookie for 1 year
    resp.set_cookie("site_lang", lang, max_age=31536000, path="/", httponly=False)
    return resp
