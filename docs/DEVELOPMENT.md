# Development

**English** · [Español](es/DESARROLLO.md)

For anyone who wants to change TokenDash. How it is built inside: [ARCHITECTURE.md](ARCHITECTURE.md).

## Stack

- **Application:** Django 5.2, with Celery (`worker` and `beat`), PostgreSQL 16 and Redis, run with Docker Compose.
- **Styles:** Tailwind CSS v4, compiled from `assets/app.css`. The compiled CSS (`static/css/app.css`) is part of the repository and is built again with the image.
- **Static files:** whitenoise.
- **Languages:** the interface is in English and Spanish. Code, comments and the original texts are in English; the Spanish translation is in `locale/es/` ([Translations](#translations)).

## Local environment

Requirements: Python 3.12 and Node 22. Without `DB_HOST`, Django uses a local SQLite database and needs neither PostgreSQL nor Redis for the tests.

On Linux or macOS:

```bash
python3.12 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m playwright install chromium
```

```bash
npm ci
```

```bash
npm run build:css
```

```bash
export DJANGO_SECRET_KEY=local-checks-only
```

```bash
.venv/bin/python manage.py check
```

```bash
.venv/bin/python manage.py makemigrations --check --dry-run
```

```bash
.venv/bin/python manage.py test
```

On Windows, with PowerShell:

```powershell
py -3.12 -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```powershell
$env:DJANGO_SECRET_KEY='local-checks-only'
```

```powershell
.\.venv\Scripts\python.exe manage.py test
```

**Visual checks.** They open the dashboard and the "Connect accounts" page in a local Chromium, in English and Spanish, with simulated data. They leave screenshots in `artifacts/`, which is not part of the project:

```bash
.venv/bin/python manage.py collectstatic --noinput
```

```bash
.venv/bin/python scripts/check_dashboard.py
```

```bash
.venv/bin/python scripts/check_connection_ui.py
```

**README screenshots.** `docs/img/panel.png` and `docs/img/panel-single-account.png` (English) and their Spanish versions in `docs/img/es/` are made with invented data, on a test database of their own:

```bash
.venv/bin/python scripts/demo_screenshots.py
```

Playwright is only used for these checks and screenshots. The production image does not include it.

Do not run the tests with the `.env` of a real installation or its `DB_HOST`. Django creates its own test database.

## Translations

Texts are written in English, with `gettext` in Python, `{% translate %}` / `{% blocktranslate %}` in templates and `gettext()` in JavaScript (the catalog is served at `/<language>/jsi18n/`). After changing texts, update the Spanish catalog, translate it and compile it. GNU gettext is needed; if you do not have it (on Windows, for example), use a temporary container:

```bash
docker run --rm -e DJANGO_SECRET_KEY=x -v "$PWD:/app" -w /app python:3.12-slim-bookworm sh -c "apt-get update -qq && apt-get install -y -qq gettext >/dev/null && pip install -q -r requirements.txt && python manage.py makemessages -l es -i .venv -i node_modules -i staticfiles -i scripts && python manage.py makemessages -d djangojs -l es -i .venv -i node_modules -i staticfiles"
```

Fill in the empty or `fuzzy` `msgstr` entries in `locale/es/LC_MESSAGES/django.po` and `djangojs.po`, and compile:

```bash
docker run --rm -e DJANGO_SECRET_KEY=x -v "$PWD:/app" -w /app python:3.12-slim-bookworm sh -c "apt-get update -qq && apt-get install -y -qq gettext >/dev/null && pip install -q -r requirements.txt && python manage.py compilemessages -i .venv -i node_modules"
```

The compiled `.mo` files are part of the repository, so the tests and the image do not need gettext.

Texts stored in the database (limit names, failure messages) are stored in English, marked with `gettext_noop`, and translated when shown. Do not store a translated text.

To add another language, add it to `LANGUAGES` in `config/settings.py` and run `makemessages -l CODE`.

## Test an image before using it

Build it under another tag and run the suite inside the image, without network:

```bash
docker build -t tokendash:test .
```

```bash
docker run --rm --network none -e DJANGO_SECRET_KEY=checks-only -e DB_HOST= tokendash:test sh -c "mkdir /tmp/t && cp -r /app/. /tmp/t && cd /tmp/t && python manage.py test --verbosity 0"
```

## Project rules

- **Real data:** show only quotas the provider publishes. Do not invent percentages or turn tokens into percentages.
- **"No data" is not 0 %:** if a reading fails, keep the last valid one with its date.
- **Separate windows:** the 5-hour, weekly and monthly windows are never added up.
- **Credentials:**
  - Do not print tokens, credentials or raw provider answers in logs, tests or errors.
  - The Claude session belongs to the official client: TokenDash does not read it.
- **Claude client:**
  - It enters the image checked by SHA-256 against Anthropic's signed manifest. No external installers are run.
  - To change its version, set `CLAUDE_CODE_VERSION` in the `Dockerfile` and run `scraper/test_claude_usage.py` again.
  - The `get_usage` protocol is experimental.
- **No evasion:** do not add browser automation to sign in, hiding of automation or CAPTCHA solving.
- **Tests:** with fixtures they validate the software, not compatibility with real accounts.

## Dependencies

- **Python:** direct dependencies are bounded to compatible versions in `requirements.txt`.
- **Node:** `package-lock.json` pins Tailwind.
- **npm warning:** Tailwind's build chain includes `braces` through its file watcher. npm warns about [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), with no fixed version published. That package is only used to compile local sources, and Node is not copied into the final image.
