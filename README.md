# FastAPI + SQLAlchemy + Jinja2 Starter

This repository is a starter for FastAPI apps using PostgreSQL (via SQLAlchemy), Jinja2 templates, HTMX-ready patterns, and Tailwind CSS.

Quick notes
- Templates live in `templates/`.
- Static assets are served from `static/` (Tailwind, logo, etc.).
- The app mounts the static directory using an absolute path so it works regardless of working directory.

Tailwind CSS (development) — setup and build

This project expects Tailwind CSS to be built into `static/tailwind.css`.
A minimal fallback stylesheet `static/fallback.css` is also included and is loaded before Tailwind so pages remain usable if Tailwind isn't built or blocked by an extension.

Below are recommended steps to install and build Tailwind using npm.

1) Install Node.js (if not already). Recommended: install Node 18+.

2) Install node modules and build Tailwind:

```bash
# inside the repository root
npm install
npm run build:css   # builds ./static/tailwind.css from ./assets/tailwind-input.css
```

3) During development you can watch for changes:

```bash
npm run watch:css
```

Troubleshooting notes
- If pages are unstyled in a specific browser (e.g. Vivaldi) but fine in another (Chrome), try:
  - Hard reload (Ctrl+Shift+R) to bypass cache.
  - Disable extensions in that browser (some extensions block remote or local CSS files).
  - Confirm that `/static/tailwind.css` is accessible from the browser (open the CSS URL directly).
- If `npm run build:css` fails, ensure `node` and `npm` are installed and available in PATH.

Tailwind config
- `tailwind.config.js` is preconfigured with the project's templates and python files so Tailwind won't purge used utilities.

Running the app

```bash
uvicorn main:app --reload
```

If you want, tell me and I will:
- Add a simple `Makefile` target to build the CSS.
- Attempt to run `npm run build:css` here and report the exact error output (if you allow me to run commands in your environment) so we can fix your local build problem.
