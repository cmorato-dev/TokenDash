# Maintenance

**English** · [Español](es/MANTENIMIENTO.md)

All commands are run in the TokenDash folder, the one with `docker-compose.yml`, for example after `cd ~/tokendash`. On Windows, open PowerShell there ("Open in Terminal").

## See how it is doing

```bash
docker compose ps
```

It shows whether each part is running:

| Part | What it does |
|---|---|
| `web` | The web page |
| `worker` | Reads the limits |
| `beat` | Tells it when to read, as set in Administration → Settings |
| `db` | The database |
| `redis` | The task queue |

To see the latest messages of each part:

```bash
docker compose logs --tail=50 web worker beat
```

## Stop, start and restart

| I want to | Command |
|---|---|
| Stop TokenDash | `docker compose stop` |
| Start it again | `docker compose start` |
| Restart it | `docker compose restart` |

No data is lost when stopping it or restarting the computer.

> **Do not use `docker compose down -v`.** The `-v` deletes the database, the history and the Claude session. `docker compose down`, without `-v`, is safe.

## Update to a new version

Before updating, make a [backup](#backups).

**If you downloaded it with Git:**

```bash
git pull
```

```bash
docker compose up -d --build
```

**If you downloaded the ZIP:**

1. Download the new ZIP.
2. Copy your `.env` file into its folder.
3. Run `docker compose up -d --build` from the new folder.

The data lives in Docker, not in the folder, so it is not lost.

At start-up, TokenDash applies whatever changes the database needs. Users, history and connections are kept.

To free the space used by old versions:

```bash
docker image prune
```

## Backups

A full backup has two parts. Keep both somewhere safe, away from the computer, because they hold your users and the encrypted ChatGPT connection.

1. **The `.env` file.** Copying it once is enough, because it does not change. Without it the ChatGPT connection cannot be decrypted.
2. **The database**, with users, history, the ChatGPT connection and the Home Assistant keys.

To copy the database, run these two commands:

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/tokendash.dump'
```

```bash
docker compose cp db:/tmp/tokendash.dump ./tokendash-backup.dump
```

It leaves the file `tokendash-backup.dump` in the folder.

The Claude session is not part of the backup. If you move to another computer, it is linked again in five minutes with [the guide](LINK_CLAUDE.md).

### Automatic daily backup (Linux)

1. Run `crontab -e`.
2. Add this line at the end, replacing `/home/user/tokendash` with your folder.

```cron
30 3 * * * cd /home/user/tokendash && docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/tokendash.dump' && docker compose cp db:/tmp/tokendash.dump ./backups/tokendash-$(date +\%a).dump
```

Before using it, create the folder with `mkdir ~/tokendash/backups`. It makes a backup every night at 3:30 and keeps one per day of the week, so you always have the last 7 days.

## Restore a backup or move to another computer

On the new computer:

1. Install Docker and download TokenDash, as in the [installation guide](INSTALL.md), but do **not** run `init_env.py`.
2. Copy your old `.env` into the folder. If the new computer has another IP address, change it inside the file: it is in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
3. Copy the `tokendash-backup.dump` file too.
4. Start only the database and restore the backup:

```bash
docker compose up -d --wait db redis
```

```bash
docker compose cp ./tokendash-backup.dump db:/tmp/tokendash.dump
```

```bash
docker compose exec -T db sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/tokendash.dump'
```

5. Start the rest:

```bash
docker compose up -d --build
```

6. Sign in with your usual user. ChatGPT is still connected. For Claude, repeat [the linking](LINK_CLAUDE.md).

Restoring only works on an **empty**, freshly created installation. If you had already started TokenDash on the new computer, remove it first with `docker compose down -v`, knowing that it deletes whatever that computer had.

Do not leave both computers running at the same time with the same backup: stop the old one with `docker compose stop`.

## Open TokenDash from other devices

If you did not give the IP address when installing, or the address has changed, edit `.env` with any text editor:

```dotenv
WEB_BIND=0.0.0.0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://192.168.1.50:8000
```

Replace `192.168.1.50` with the computer's IP address and apply the change:

```bash
docker compose up -d
```

`DJANGO_ALLOWED_HOSTS` takes several addresses separated by commas, for example the computer's name (`minipc.local`).

## Other settings

The refresh frequency is changed on the dashboard: **Administration → Settings** ([Using the dashboard](USAGE.md#how-often-it-refreshes)). The other settings are in `.env`:

| Variable | What for | Default |
|---|---|---|
| `TIME_ZONE` | Time zone of the dates (`Europe/London`, `America/New_York`…) | `Europe/Madrid` |
| `LANGUAGE_CODE` | Language of console messages, and of the pages when the browser asks for neither English nor Spanish: `en` or `es` | `en` |
| `WEB_BIND` | `0.0.0.0` to open it from the network; without it, only from the computer itself | the computer only |

After changing something, run `docker compose up -d`.

**Do not change `DJANGO_SECRET_KEY`.** If you change it, the ChatGPT connection stops working and has to be made again.

## HTTPS

At home, `http://` is enough. HTTPS is needed in two cases:

- you want to reach it from outside your home through a proxy;
- you open Home Assistant with `https://` and want to see the TokenDash modules, because the browser does not mix `https` and `http` pages.

**The simplest way to reach it from outside is a VPN**, such as Tailscale or WireGuard. With it nothing in TokenDash needs changing.

If you already use a reverse proxy (Nginx Proxy Manager, Caddy, Traefik…):

1. Create an address in it, for example `https://tokendash.mydomain.com`, that forwards to `http://COMPUTER-IP:8000`.
2. Put in `.env`:

   ```dotenv
   DJANGO_ALLOWED_HOSTS=tokendash.mydomain.com,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://tokendash.mydomain.com
   DJANGO_SECURE_COOKIES=1
   DJANGO_TRUST_PROXY_HEADERS=1
   ```

3. Apply with `docker compose up -d`.

Turn on `DJANGO_TRUST_PROXY_HEADERS=1` only if **all** access goes through the proxy. If the proxy runs on the same computer, leave `WEB_BIND` unset, so port 8000 cannot be reached from the network.

## Uninstall

```bash
docker compose down -v
```

That command deletes TokenDash and all its data. Then you can delete the folder.
