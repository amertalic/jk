from pathlib import Path
import json
from typing import Callable, Dict, Any
from fastapi import Request

# Simple i18n loader and translator
_TRANSLATIONS: Dict[str, Dict[str, str]] = {}
_SUPPORTED_LOCALES = {"en", "bs"}
_DEFAULT_LOCALE = "en"

# Default translations file path (resolve relative to this module so CWD doesn't matter)
_DEFAULT_TRANSLATIONS_PATH = Path(__file__).parent.joinpath("translations.json")


def load_translations(path: str | Path = "translations.json") -> None:
    """Load translations JSON into memory. Expected format:
    {
      "key.path": { "en": "...", "bs": "..." },
      ...
    }
    The `path` may be absolute or relative; relative paths are resolved relative to this module.
    """
    global _TRANSLATIONS
    p = Path(path)
    # If relative path, resolve relative to this module's directory
    if not p.is_absolute():
        p = Path(__file__).parent.joinpath(path)
    if not p.exists():
        # leave empty if file missing; callers should ensure file exists
        _TRANSLATIONS = {}
        return
    with p.open("r", encoding="utf-8") as fh:
        _TRANSLATIONS = json.load(fh)


def _parse_accept_language(header: str) -> list[str]:
    if not header:
        return []
    parts = [p.strip() for p in header.split(",") if p.strip()]
    langs = []
    for part in parts:
        lang = part.split(";")[0].strip()
        if not lang:
            continue
        # normalize like 'en-US' -> 'en'
        if "-" in lang:
            lang = lang.split("-")[0]
        langs.append(lang)
    return langs


def pick_locale_from_request(request: Request) -> str:
    # 1) Preference cookie (set by language switcher)
    cookie_lang = request.cookies.get("site_lang")
    if cookie_lang and cookie_lang in _SUPPORTED_LOCALES:
        return cookie_lang

    # 2) Accept-Language header
    header = request.headers.get("accept-language", "")
    prefs = _parse_accept_language(header)
    for p in prefs:
        if p in _SUPPORTED_LOCALES:
            return p
    # fallback to default
    return _DEFAULT_LOCALE


def get_translator(locale: str) -> Callable[[str, Any], str]:
    # Ensure translations are loaded (lazy load) so failures at import-time don't leave _TRANSLATIONS empty
    try:
        if not _TRANSLATIONS:
            load_translations(_DEFAULT_TRANSLATIONS_PATH)
    except Exception:
        # non-fatal: fall back to empty translations
        pass

    def translate(key: str, **kwargs) -> str:
        entry = _TRANSLATIONS.get(key, {})
        text = entry.get(locale) or entry.get(_DEFAULT_LOCALE) or key
        try:
            return text.format(**kwargs) if kwargs else text
        except Exception:
            return text

    return translate


# FastAPI dependency to provide translator per-request
def i18n_dependency(request: Request) -> Callable[[str, Any], str]:
    # Reload translations on each request so developers can add keys without needing a server restart.
    try:
        load_translations(_DEFAULT_TRANSLATIONS_PATH)
    except Exception:
        # non-fatal; proceed with whatever is already loaded
        pass
    locale = pick_locale_from_request(request)
    return get_translator(locale)


# Try to load translations at import time as a fallback (helpful for tests and simple imports)
try:
    if not _TRANSLATIONS:
        load_translations(_DEFAULT_TRANSLATIONS_PATH)
except Exception:
    # non-fatal; main.py will try to load at startup
    pass
