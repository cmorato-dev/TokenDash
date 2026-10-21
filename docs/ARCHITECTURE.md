# TokenDash architecture

**English** · [Español](es/ARQUITECTURA.md)

## Layout

```text
Docker server (Linux or Windows)
  Admin → Codex sign-in → encrypted ProviderCredential
  Admin / claude_status → "client" mode → the worker reads Claude with the official client
  beat (every minute) → refresh_if_due → Redis → worker → reads ChatGPT/Codex and Claude → ProviderStatus + UsageLog
  web → quota dashboard and history, in /en/ and /es/
  Home Assistant → /<language>/ha/<module>/ ("Webpage" card) and /api/ha/<provider>/ (sensors), with a read-only key
```

**The server depends on no PC and no open browser.** Earlier versions had a browser extension, an agent for the PCs and a browser on the server; they were removed. The migrations `scraper/0004_retire_browser_and_agent.py` and `dashboard/0008_retire_browser_and_scraper_modes.py` drop their tables and set any provider that used those modes to "not connected" (`none`).

## Components

| Source | Responsibility |
| --- | --- |
| `scraper/claude_usage.py` | Asks the official client for `get_usage`, with no messages to the model and no reading of credentials. **The only implementation of the protocol**, standard-library Python only |
| `scraper/claude_client.py` | Reader of the Claude quotas on the server; loads `claude_usage.py` |
| `scraper/claude_client_views.py` | State of the Claude session and switching to "client" mode from the dashboard |
| `scraper/codex_oauth.py`, `codex_views.py` | ChatGPT/Codex PKCE sign-in and server-side reading; encrypted tokens |
| `scraper/connection_views.py`, `urls.py` | "Connect accounts" page (`/<language>/admin/connect/`), superuser only |
| `scraper/quotas.py` | Quota readings (`QuotaReading`) and shared errors; `display_quota` translates their names and the reset sentence when shown |
| `scraper/tasks.py` | `refresh_all`, `refresh_provider`, atomic lock and persistence |
| `scraper/management/commands/claude_status.py` | Checks the Claude session, turns the mode on and saves a reading (`claude_estado` is its old name) |
| `static/css/admin-theme.css` | The dashboard's palette applied to every admin page, loaded from `templates/admin/base_site.html` |
| `dashboard/` | Quota cards and history; modules and sensors for Home Assistant |
| `dashboard/accounts.py` | First sign-in: forces a change of the initial password (`admin` / `tokendash`) before anything else |
| `dashboard/management/commands/create_initial_admin.py` | Creates that initial user, only if there are no users; the `migrate` service runs it |
| `dashboard/templatetags/languages.py`, `templates/_languages.html` | `hreflang` links and the **EN · ES** switch |
| `scripts/init_env.py` | Creates `.env` with random secrets; with an IP address, makes it reachable from the network |
| `locale/es/LC_MESSAGES/` | Spanish translation of Python, templates (`django.po`) and JavaScript (`djangojs.po`) |

## Models

- `ProviderStatus` and `UsageLog`: current quotas and history per window. Incompatible windows are never added up. `collection_mode` is `none` (not connected), `api` (ChatGPT with a credential) or `client` (Claude with the official client). `client_auth_method` and `client_auth_checked_at` hold the **kind** of credential of the official client (never the credential), published by the `worker` so the dashboard can show it.
- `RefreshSettings`: a single row with the refresh frequency (15 min to 6 h), the time of the last automatic reading and the accounts in use (`accounts`: both, only ChatGPT or only Claude). Edited in Administration → Settings. `RefreshSettings.shown_providers()` filters the dashboard, the API, the Home Assistant modules, "Connect accounts" and `refresh_all`.
- `IntegrationKey`: read-only Home Assistant keys. Only their SHA-256 is stored; the key is shown once, when created in the administration.
- `ProviderCredential`: ChatGPT/Codex tokens encrypted with Fernet and a key derived from `DJANGO_SECRET_KEY`. That secret must be kept when migrating.

## Languages

Code, templates and messages are written in English and translated with gettext (`locale/es/`). Every page lives at `/en/…` and `/es/…` (`i18n_patterns`); an address without a prefix redirects to the browser's language or to the one chosen with the **EN · ES** buttons (`set_language`, which stores it in a cookie). Pages link their other version with `hreflang`.

The API (`/api/…`) has a single address: it answers in the `Accept-Language` language, which the dashboard sends with the page's own. Texts stored in the database (limit names, `last_error`) are stored in English and translated when shown; the "Resets on…" sentence is written from `resets_at`. `LANGUAGE_CODE` (in `.env`, `en` by default) is the fallback language and the console's.

## Claude and ChatGPT

Claude: `scraper/claude_usage.py` starts the official client in `stream-json` mode, with no session persistence, tools, MCP or user/project hooks. It sends only the `initialize` and `get_usage` control requests (`skip_behaviors=true`), never a `user` message. From the result it only accepts `five_hour`/`seven_day`, a percentage between 0 and 100 and a reset date. The client handles its own authentication with **its claude.ai session**, stored in the private `claude_config` volume (`claude auth login` inside the container); TokenDash neither reads nor stores that credential. `CLAUDE_CODE_OAUTH_TOKEN` is not used: Anthropic limits that token to model requests and it cannot read the quota, and the variable would take precedence over the signed-in session. The interface is experimental and must fail while keeping the last reading.

**The session lives in the `worker`, not in `web`.** The `claude_config` volume is only mounted in that service, so the dashboard cannot ask the client. The `worker` publishes the **kind** of credential (`claude.ai`, `none`, `oauth_token`…) in `ProviderStatus.client_auth_method` and the dashboard reads that record. The `scraper.tasks.check_claude_session` task forces the check when the operator presses "Check the session now"; every quota reading updates it too.

ChatGPT/Codex: the superuser signs in once on OpenAI. PKCE/state are validated and the credential is stored encrypted; beat/worker read the limits regularly. The endpoints used by the Codex client are not a guaranteed public API; any failure keeps the last reading.

## Main routes

| Route | Use |
| --- | --- |
| `/en/`, `/es/` | Quota dashboard; sign-in. `/` redirects to one of them. Every page carries that prefix |
| `/i18n/setlang/` | Changes the language (**EN · ES** buttons); POST with CSRF |
| `/<language>/jsi18n/` | Translated texts of the JavaScript |
| `/<language>/accounts/password_change/` | Password change. A session signed in with the initial password cannot reach any other page (the APIs answer 403) |
| `/api/status/`, `/api/history/` | Quota state and history; sign-in or Home Assistant key. The history offers 7, 30, 90, 182, 365 and 1825 days, grouped by day, week, month or year |
| `/<language>/ha/chatgpt/`, `…/ha/claude/`, `…/ha/chart/` | A single module for a Home Assistant card. It can be framed (no `X-Frame-Options`) and carries no data: its JavaScript reads the key from the `#key=…` fragment and sends it as `Authorization: Bearer`. The old unprefixed addresses (`/ha/grafica/`, `#clave=`, `?dias=`) keep working |
| `/api/ha/<provider>/` | A provider's values for REST sensors; Home Assistant key or sign-in |
| `/api/refresh/<provider>/` | Queues a refresh; POST, CSRF and `is_staff` |
| `/<language>/admin/connect/` | Connect accounts; superuser. The old addresses `/admin/conectar/` and `/admin/scraper/scrapersession/connect/` redirect here |
| `/<language>/admin/connect/codex/`, `…/connect/claude/` | ChatGPT and Claude actions; POST with CSRF |

## Services and deployment

Compose runs `web`, `worker`, `beat`, PostgreSQL 16, Redis and `migrate`, which applies the migrations and creates the initial user on an empty installation. Beat uses Celery's standard scheduler: every minute it starts `scraper.tasks.refresh_if_due`, which compares the last automatic reading with the frequency chosen in **Administration → Settings** (`RefreshSettings`, a single row) and, when it is due, queues `refresh_all`. That way the frequency changes without restarting beat. `SCRAPE_INTERVAL_MINUTES` only sets its first value. Persistent data lives in PostgreSQL; the encrypted credentials also need the Django secret. The Claude session is in the `claude_config` volume.

The image includes the official Claude Code client (`/opt/claude/bin/claude`), downloaded from Anthropic's release repository and **checked by SHA-256 against its signed manifest**; no external installer is run. It includes neither Playwright nor Chromium.

Installation: [INSTALL.md](INSTALL.md). Backups, updates and HTTPS: [MAINTENANCE.md](MAINTENANCE.md). Tests and development: [DEVELOPMENT.md](DEVELOPMENT.md).
