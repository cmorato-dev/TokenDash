# Link Claude with the server, step by step

**English** · [Español](es/VINCULAR_CLAUDE.md)

It is done **only once**: afterwards the server reads the Claude quota regularly (every 20 minutes by default) with nobody keeping a browser or a PC on. It is only repeated if the session expires or someone signs out of claude.ai on all devices.

You need a Claude subscription (Pro or Max). TokenDash uses the official Claude Code client, which already comes inside TokenDash: there is nothing to install.

**What you need**

- A terminal on the computer where TokenDash runs, or SSH access to it. On Windows, PowerShell opened in the TokenDash folder works; then skip step 1.
- The folder with TokenDash's `docker-compose.yml`. This guide uses `~/tokendash`, the one from the [installation guide](INSTALL.md); change it if yours is different.
- The claude.ai account whose usage you want to see, and a browser on any device (a phone works).

In steps 3 to 5 you copy an address from the terminal, open it in the browser, sign in and paste into the terminal the code the page gives you. If the account belongs to someone else, they do step 4 and send you the code.

---

## Step 1 · Open the server

```bash
ssh user@tokendash-server
```

```bash
cd ~/tokendash
```

> If running `docker` answers *permission denied*, put `sudo` before every `docker` command in this guide.

## Step 2 · See whether it is already linked

```bash
docker compose exec worker claude auth status
```

Look for the `"authMethod"` line:

| What appears | What it means | What to do |
| --- | --- | --- |
| `"authMethod": "claude.ai"` | It is already linked | Skip to **step 6** |
| `"authMethod": "none"` or `"loggedIn": false` | There is no session | Go on with step 3 |
| `"authMethod": "oauth_token"` | A `setup-token` token is left over, and it does not work | See "Problems" at the end |

## Step 3 · Sign in

```bash
docker compose exec worker claude auth login
```

The terminal shows something like this and **waits**. Do not close it:

```text
Opening browser to sign in…
If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&client_id=...
Paste code here if prompted >
```

Copy **the full address** that starts with `https://claude.com/cai/oauth/authorize`. It is very long: if the terminal wraps it over several lines, copy all of it (or paste it into a text editor and join it into one line). Open it in the browser.

## Step 4 · Authorise in the browser

1. Open the address in any browser.
2. Sign in with the claude.ai account (the one you use for Claude Code or the app).
3. Press **Authorize**.
4. The page shows a **code**. Copy it with the page's copy button.

## Step 5 · Paste the code

Paste the code into the waiting terminal and press **Enter**. `Login successful` should appear.

> **Paste only the code.** If you also paste the page's address, the client rejects it.
> The code expires after a few minutes. If it takes too long or fails, start again from step 3.

## Step 6 · Check and turn on

```bash
docker compose exec worker python manage.py claude_status
```

This command checks the session, turns on reading the quota on the server and refreshes it right away. A correct output looks like this (the numbers and dates change):

```text
Claude session on the server: claude.ai session connected
  5-hour session: 4 % used · Resets on Oct 21 at 14:19
  Week · all models: 65 % used · Resets on Oct 25 at 21:59
Claude quota updated on the dashboard (21/10 14:05).
```

If it ends with `Sign in with: …`, go back to step 3.

> Earlier guides called this command `claude_estado`. It still works.

## Step 7 · Look at the dashboard

Open TokenDash in the browser. The Claude card should be **Updated**, with the time of the last reading. In **Administration → Connect accounts → 2 · Claude** it says "claude.ai session connected".

That's it. Nothing else needs doing: the server renews the session and the reading on its own.

---

## Problems

| Symptom | Cause | Solution |
| --- | --- | --- |
| `no configuration file provided` | You are not in the TokenDash folder | `cd ~/tokendash` (or the right folder) |
| `service "worker" is not running` | The containers are stopped | `docker compose up -d` and repeat |
| `"authMethod": "oauth_token"` | There is a `CLAUDE_CODE_OAUTH_TOKEN` in `.env` | Delete that line from `.env`, run `docker compose up -d worker` and repeat from step 3 |
| The code is not accepted | It was pasted with the address, or it expired | Repeat from step 3 and paste only the code |
| `The quota could not be read` with the session connected | The account's plan publishes no quotas or the client changed | Check the plan on claude.ai; the dashboard keeps the last valid reading |

**Do not use `claude setup-token`.** That token can only send messages to the model; Anthropic does not let it read the quota.

## Security

- The session is stored in the private `claude_config` volume of the `worker` container. It does not go through `.env` or the database.
- TokenDash **does not read, store or show** that credential: it only publishes the percentage and the reset date.
- Do not send screenshots of the full `claude auth status` output: it includes the account's e-mail. The `authMethod` line is enough.
- To unlink the server: `docker compose exec worker claude auth logout`.
