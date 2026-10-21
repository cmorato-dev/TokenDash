# Install TokenDash step by step

**English** · [Español](es/INSTALACION.md)

This guide starts from scratch. If you already have Docker, skip to [step 2](#2-download-tokendash).

**Before you start, choose the computer.** TokenDash only reads the limits while it is on, so a computer that never switches off is best: a mini PC, a Raspberry Pi 4 or 5, a NAS with Docker or a home server. A desktop computer works too, but you will only see data from the hours it is on.

In the examples, `192.168.1.50` is the IP address of the computer where you install TokenDash. Replace it with yours:

- **On Linux:** type `hostname -I`. It is the first number shown.
- **On Windows:** type `ipconfig` and look for "IPv4 Address".

It is best if that address does not change. Reserve the computer's IP address on your router: it is usually under "DHCP", "IP reservation" or "static IP".

---

## Linux (Ubuntu, Debian, Raspberry Pi OS…)

All commands are typed in a terminal on the computer, or over SSH from another one (`ssh user@192.168.1.50`). Copy and paste each block separately.

### 1. Install Docker

If `docker compose version` already answers with a version number, skip to step 2.

Docker offers an official installer for Ubuntu, Debian and Raspberry Pi OS. Before running it you can check what it does at [get.docker.com](https://get.docker.com).

```bash
curl -fsSL https://get.docker.com -o install-docker.sh
```

```bash
sudo sh install-docker.sh
```

To use Docker without typing `sudo` every time:

```bash
sudo usermod -aG docker $USER
```

**Sign out and sign in again.** Over SSH, leave with `exit` and connect again. Then check that it works:

```bash
docker compose version
```

On other distributions, follow [Docker's official guide](https://docs.docker.com/engine/install/).

### 2. Download TokenDash

If you do not have Git, install it with `sudo apt install -y git`.

```bash
git clone https://github.com/cmorato-dev/TokenDash.git ~/tokendash
```

```bash
cd ~/tokendash
```

TokenDash is now in the `tokendash` folder of your user. All the commands in the guides are run inside that folder.

### 3. Create the configuration

This command creates the `.env` file with the keys of your installation, generated at random:

```bash
python3 scripts/init_env.py 192.168.1.50
```

With the IP address, TokenDash can be opened from any device on your network. If you will only open it from the same computer, run it without the address.

Pages appear in each browser's language. Console messages (for example those of `claude_status`) are in English; to have them in Spanish, open `.env` and change `LANGUAGE_CODE=en` to `LANGUAGE_CODE=es`.

> **Keep a copy of `.env` somewhere safe** (a USB stick, your password manager). If you lose it, the ChatGPT connection stops working and has to be made again. Do not share it: it holds the keys of your installation.

### 4. Start

```bash
docker compose up -d --build
```

The first time takes 3 to 10 minutes, depending on the computer: it downloads and prepares everything it needs. Later it starts in seconds.

To check that it works:

```bash
docker compose ps
```

You should see `web`, `worker`, `beat`, `db` and `redis` as `running`, and `web` as `healthy` after a minute. `migrate` shows as finished (`exited (0)`), which is normal: it only runs at start-up.

TokenDash starts again on its own if the computer restarts.

### 5. Open it

Open **http://192.168.1.50:8000** in the browser of any computer or phone on your network, and go on with [First sign-in](USAGE.md#first-sign-in).

---

## Windows 10 / 11

### 1. Install Docker Desktop

1. Download **Docker Desktop** from [docker.com](https://www.docker.com/products/docker-desktop/) and install it with the default options.
2. Restart if asked and open Docker Desktop. Accept the terms and wait until "Engine running" appears at the bottom left.
3. In **Settings → General**, tick **Start Docker Desktop when you sign in**. Otherwise TokenDash does not start until you open Docker Desktop.

### 2. Download TokenDash

**Without Git (easiest):**

1. On [the project page](https://github.com/cmorato-dev/TokenDash), press **Code → Download ZIP**.
2. Unzip it wherever you like, for example in `Documents\tokendash`.

**With Git**, which makes later updates easier:

```powershell
git clone https://github.com/cmorato-dev/TokenDash.git $HOME\tokendash
```

### 3. Open PowerShell in the folder

In File Explorer, open the TokenDash folder, the one with `docker-compose.yml`. Right-click an empty space and choose **Open in Terminal**.

### 4. Create the configuration

If you have Python installed:

```powershell
py scripts\init_env.py 192.168.1.50
```

Without Python, the same program can run inside Docker:

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim-bookworm python scripts/init_env.py 192.168.1.50
```

If you will only open it from this PC, remove the address at the end. Keep a copy of `.env`, as explained in [Linux step 3](#3-create-the-configuration).

For other devices to reach port 8000, the first time Windows may ask whether Docker can access the network. Allow it **on private networks only**.

### 5. Start and open it

```powershell
docker compose up -d --build
```

When it finishes, open **http://localhost:8000** on this PC, or **http://192.168.1.50:8000** from another device. Go on with [First sign-in](USAGE.md#first-sign-in).

---

## What next?

1. [First sign-in and users](USAGE.md#first-sign-in)
2. [Connect ChatGPT](USAGE.md#connect-chatgpt)
3. [Link Claude](LINK_CLAUDE.md)
4. If you like, [add it to Home Assistant](HOME_ASSISTANT.md)

If something fails, see [Troubleshooting](TROUBLESHOOTING.md).
