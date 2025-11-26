# Proxy loader: ensure that `import utils` will delegate to the package directory `./utils/`.
# This allows existing imports and the package `utils` (folder) to be used while keeping
# this top-level file present for historical reasons.
import importlib.util
import sys
from pathlib import Path

_pkg_init = Path(__file__).parent / "utils" / "__init__.py"
if _pkg_init.exists():
    spec = importlib.util.spec_from_file_location("utils", str(_pkg_init))
    pkg = importlib.util.module_from_spec(spec)
    # Insert into sys.modules under the canonical name before executing to support recursive imports
    sys.modules["utils"] = pkg
    # Execute the package __init__.py to populate the module
    try:
        spec.loader.exec_module(pkg)  # type: ignore
    except Exception:
        # If package init fails, remove the injected module to avoid hiding import errors
        sys.modules.pop("utils", None)
        raise
    # Expose commonly used submodule(s) if available
    try:
        auth = pkg.auth
    except Exception:
        try:
            import importlib

            auth = importlib.import_module("utils.auth")
        except Exception:
            auth = None
else:
    # No package found; provide minimal placeholders
    auth = None
