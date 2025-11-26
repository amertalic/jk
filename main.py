from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from database import init_db, DB_DIALECT, REDACTED_DATABASE_URL
from endpoints import auth as auth_router
from endpoints import i18n as i18n_router
from endpoints import settings as settings_router
from endpoints import home as home_router
from endpoints import placeholder as placeholder_router
from contextlib import asynccontextmanager
from settings import settings
import jwt
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from logger import set_request_context, clear_request_context
import i18n
from pathlib import Path

# helper

from utils import auth as utils_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: run once at startup and once at shutdown."""
    # Startup
    init_db()
    print(f"[Startup] Database dialect: {DB_DIALECT}, URL: {REDACTED_DATABASE_URL}")

    # Load translations file (if present)
    try:
        i18n.load_translations("translations.json")
        print("[Startup] Loaded translations")
    except Exception:
        print("[Startup] Failed to load translations")

    # Register any routes that were marked with @public_route by scanning the app router
    try:
        for r in app.routes:
            # Most routes have an endpoint attribute which may be a function decorated by us
            endpoint = getattr(r, "endpoint", None)
            if endpoint is not None and getattr(endpoint, "__public__", False):
                # attempt to extract a usable path for registration
                p = (
                    getattr(r, "path", None)
                    or getattr(r, "path_format", None)
                    or getattr(r, "name", None)
                    or ""
                )
                utils_auth.register_public_path(p)
    except Exception:
        # don't fail startup on registration issues; just log
        import traceback

        traceback.print_exc()

    yield
    # Shutdown (no-op for now)


# Middleware to decode JWT from Authorization header or cookie and set request.state.user & tenant
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Clear any previous request context
        clear_request_context()
        token = None
        # Try Authorization header
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        # Fallback to cookie
        if not token:
            token = request.cookies.get("access_token")
        if token:
            try:
                payload = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                )
                # Attach user info to request.state for downstream dependencies
                request.state.user = {
                    "username": payload.get("sub"),
                    "is_active": payload.get("is_active"),
                    "email": payload.get("email"),
                }
                request.state.tenant = payload.get("tenant_schema")
                # Propagate to logging context
                set_request_context(
                    request.state.user.get("username"), request.state.tenant
                )
            except jwt.ExpiredSignatureError:
                # expired token -> ignore and continue as anonymous
                request.state.user = None
                request.state.tenant = None
            except Exception:
                request.state.user = None
                request.state.tenant = None
        else:
            request.state.user = None
            request.state.tenant = None
            # Ensure logging context cleared for anonymous
            clear_request_context()

        # Enforce auth for non-public paths
        path = request.url.path
        if not utils_auth.is_public_path(path) and not getattr(
            request.state, "user", None
        ):
            # return appropriate unauth response (Redirect or JSON)
            return utils_auth.unauth_response(request)

        try:
            response = await call_next(request)
            # Log request with status; RequestContextFilter will attach username/tenant
            logging.getLogger("chinchilla.requests").info(
                "%s %s -> %s", request.method, request.url.path, response.status_code
            )
            return response
        finally:
            # Clear context after response (or if an exception occurs) to avoid leaking into other requests/tasks
            clear_request_context()


# Initialize FastAPI app
app = FastAPI(title="Manage system", lifespan=lifespan)
# Mount static directory using an absolute path based on this file's location so
# the app works regardless of current working directory when started.
STATIC_DIR = str(Path(__file__).parent.joinpath("static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Mount auth routes
# Mount static files (for TailwindCSS and other assets)
# i18n: load translations at startup
app.include_router(settings_router.router)
app.include_router(auth_router.router)
app.include_router(i18n_router.router)
app.include_router(home_router.router)
app.include_router(placeholder_router.router)

app.add_middleware(AuthMiddleware)


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
