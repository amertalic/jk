import logging
import sys
import contextvars
from typing import Optional
from settings import settings

# Context variables to hold per-request values (works with async/await)
request_username: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_username", default=None
)
request_tenant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_tenant", default=None
)


class RequestContextFilter(logging.Filter):
    """Attach request-scoped context (username, tenant) to LogRecord.

    This lets formatters reference %(username)s and %(tenant)s in the log format.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        uname = request_username.get() or "-"
        tenant = request_tenant.get() or "-"
        # Attach attributes used in the format string
        record.username = uname
        record.tenant = tenant
        return True


def configure_logging():
    root = logging.getLogger()
    # Avoid adding the handler multiple times if configure_logging is called more than once
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    # Shorter, more compact format: short time, level, compact user/tenant and message
    fmt = "%(asctime)s %(levelname)s [%(username)s:%(tenant)s] %(message)s"
    # Short time only (HH:MM:SS) keeps lines concise
    datefmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    # Replace any existing handlers so edits to format take effect on import
    root.handlers = [handler]


def set_request_context(username: Optional[str], tenant: Optional[str]):
    """Set the contextvars for the current request.

    Pass None to clear a value.
    """
    if username is None:
        try:
            request_username.set(None)
        except Exception:
            pass
    else:
        request_username.set(username)

    if tenant is None:
        try:
            request_tenant.set(None)
        except Exception:
            pass
    else:
        request_tenant.set(tenant)


def clear_request_context():
    """Clear request context variables (set to None)."""
    set_request_context(None, None)


# Configure logging on import so modules that log during startup are formatted
configure_logging()
