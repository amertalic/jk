"""Shared templating utilities for the application.
Provides a single Jinja2Templates instance and a `template_get_alerts` helper.
Other modules should import from here to avoid circular imports and duplication.
"""

from fastapi.templating import Jinja2Templates
import i18n
from jinja2 import pass_context
from pathlib import Path

# Try to load translations here so templates have translations available even when importing templating
try:
    i18n.load_translations("translations.json")
except Exception:
    # non-fatal; main.lifespan will also attempt to load translations
    pass

# Single templates instance (shared)
# Use an absolute path to the templates directory so TemplateResponse can find files
TEMPLATES_DIR = str(Path(__file__).parent.joinpath("templates"))
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# Expose Sex constants to templates


# Jinja helper '_' to translate keys using request's Accept-Language when available
@pass_context
def _jinja_translate(context, key: str, **kwargs):
    # Expect the template context to include 'request' (FastAPI TemplateResponse does)
    request = context.get("request")
    if request is None:
        # no request available; use default locale
        translator = i18n.get_translator(i18n._DEFAULT_LOCALE)
    else:
        locale = i18n.pick_locale_from_request(request)
        translator = i18n.get_translator(locale)
    return translator(key, **kwargs)


templates.env.globals["_"] = _jinja_translate
