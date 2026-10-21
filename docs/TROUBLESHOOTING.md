# Troubleshooting

**English** · [Español](es/PROBLEMAS.md)

Commands are run in the TokenDash folder. If something is not listed here, look at the messages with `docker compose logs --tail=100 web worker` and find the error line.

## Installation and access

| Symptom | Likely cause | Solution |
|---|---|---|
| `permission denied` when using `docker` | Your user is not in the Docker group | `sudo usermod -aG docker $USER`, sign out and sign in again. Or put `sudo` in front |
| `no configuration file provided` | You are not in the TokenDash folder | `cd ~/tokendash`, or the folder where you downloaded it |
| `env file .env not found` or `Set POSTGRES_PASSWORD in .env` | `.env` is missing | Run `python3 scripts/init_env.py IP` ([installation, step 3](INSTALL.md#3-create-the-configuration)) |
| The page does not load from another device, but does on the computer itself | TokenDash only listens on the computer itself | [Open TokenDash from other devices](MAINTENANCE.md#open-tokendash-from-other-devices). Check the firewall too (`sudo ufw allow 8000/tcp` on Ubuntu) |
| "Bad Request (400)" | The address you use is not in `DJANGO_ALLOWED_HOSTS` | Add it to `.env` and run `docker compose up -d` |
| "Forbidden (403) · CSRF" when signing in | The address is not in `DJANGO_CSRF_TRUSTED_ORIGINS` | Add `http://IP:8000`, or your `https://…` address, and run `docker compose up -d` |
| `web` never becomes `healthy` | The database is still starting, or there is an error | Wait a minute. If nothing changes, look at `docker compose logs migrate web` |
| I forgot the password | — | Run `docker compose exec web python manage.py changepassword YOUR_USER`. If you do not remember the user either: `docker compose exec web python manage.py createsuperuser` |
| The page is in the wrong language | Your browser asks for another language | Press **EN** or **ES** at the top right; TokenDash remembers it. You can also open `http://IP:8000/en/` directly |
| Console messages are in English and I want Spanish | English is the console's default language | Put `LANGUAGE_CODE=es` in `.env` and run `docker compose up -d` |
| `admin` / `tokendash` does not work | There are users already: the initial user is only created on an empty installation | Use your user. If you do not remember it, see "I forgot the password" |

## ChatGPT

| Symptom | Solution |
|---|---|
| After authorising, "This site can't be reached" appears | That is normal. Copy the full address of that tab and paste it into TokenDash |
| "ChatGPT did not accept the code" or "The sign-in has expired" | Start again from "Sign in with ChatGPT" and paste the address within 5 minutes. Copy the whole address, it starts with `http://localhost:1455/auth/callback?code=` |
| "Session expired, sign in again" or "The connection with ChatGPT has expired" | OpenAI closed the session, for example after signing out on all devices or changing the password. Connect the account again |
| It stopped working after moving TokenDash or regenerating `.env` | `DJANGO_SECRET_KEY` changed. Connect the account again |
| The limit of regular chats does not appear | ChatGPT does not publish that percentage. There are only percentages for Codex |

## Claude

| Symptom | Solution |
|---|---|
| "Not signed in" in Connect accounts | Link Claude with [the guide](LINK_CLAUDE.md) |
| It stopped reading after weeks of working | The session expired or was closed. Repeat [the linking](LINK_CLAUDE.md) from step 3 |
| `"authMethod": "oauth_token"` | There is a `CLAUDE_CODE_OAUTH_TOKEN` line in `.env`. Delete it, run `docker compose up -d` and link again |
| I used `claude setup-token` and it does not read the quota | That token cannot read the quota. Use `claude auth login`, as the guide says |

More cases in [Link Claude → Problems](LINK_CLAUDE.md#problems).

## Data

| Symptom | Explanation |
|---|---|
| "No data" | There is no good reading yet. **It does not mean 0 %** |
| The percentage does not change and the date is old | The last reading failed. TokenDash keeps the last good one with its date. The card says why it failed |
| "It has already renewed" | The limit restarted after the last reading. It is updated at the next reading, as often as set in Administration → Settings, or when you press "Refresh now" |
| The chart is empty | It appears after the first correct reading |
| The ChatGPT or the Claude card is missing | Administration → Settings → Accounts you use has only the other one chosen |
| "The TokenDash server did not answer properly" or "No connection with the TokenDash server" | TokenDash was restarting or is stopped. The dashboard retries on its own; if it does not go away, check `docker compose ps` |
| The times do not match mine | Change `TIME_ZONE` in `.env` ([settings](MAINTENANCE.md#other-settings)) |

## Home Assistant

| Symptom | Solution |
|---|---|
| The card is blank | If you open Home Assistant with `https://`, the browser blocks `http://` pages. Read the [network section of the guide](HOME_ASSISTANT.md#2-let-home-assistant-reach-the-server) |
| "The key is missing" | `#key=…` is missing at the end of the module address |
| "The Home Assistant key is not valid or has been deleted" | The key was deleted or copied wrongly. Create another one in Administration → Home Assistant keys |
| The card says the server "refused the connection" | Home Assistant cannot reach the computer. First try opening `http://IP:8000` in the browser |
| An account's module or sensor says "Not Found" or "Unknown provider" | That account is turned off in Administration → Settings → Accounts you use |
