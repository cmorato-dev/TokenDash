# Instalar TokenDash paso a paso

Esta guía empieza desde cero. Si ya tienes Docker, salta al [paso 2](#2-descargar-tokendash).

**Antes de empezar, elige el equipo.** TokenDash solo lee los límites mientras está encendido, así que conviene un equipo que no se apague: un miniPC, una Raspberry Pi 4 o 5, un NAS con Docker o un servidor de casa. Un ordenador de sobremesa también vale, pero solo verás datos de las horas en que esté encendido.

En los ejemplos, `192.168.1.50` es la IP del equipo donde instalas TokenDash. Cámbiala por la tuya:

- **En Linux:** escribe `hostname -I`. Es el primer número que aparece.
- **En Windows:** escribe `ipconfig` y mira «Dirección IPv4».

Conviene que esa IP no cambie. Reserva la IP del equipo en tu router: suele estar en «DHCP», «Reserva de IP» o «IP estática».

---

## Linux (Ubuntu, Debian, Raspberry Pi OS…)

Todos los comandos se escriben en una terminal del equipo, o por SSH desde otro (`ssh usuario@192.168.1.50`). Copia y pega cada bloque por separado.

### 1. Instalar Docker

Si `docker compose version` ya responde con un número de versión, salta al paso 2.

Docker ofrece un instalador oficial para Ubuntu, Debian y Raspberry Pi OS. Antes de lanzarlo puedes revisar qué hace en [get.docker.com](https://get.docker.com).

```bash
curl -fsSL https://get.docker.com -o instalar-docker.sh
```

```bash
sudo sh instalar-docker.sh
```

Para usar Docker sin escribir `sudo` cada vez:

```bash
sudo usermod -aG docker $USER
```

**Cierra la sesión y vuelve a entrar.** Si es por SSH, sal con `exit` y conéctate de nuevo. Después, comprueba que funciona:

```bash
docker compose version
```

En otras distribuciones, sigue la [guía oficial de Docker](https://docs.docker.com/engine/install/).

### 2. Descargar TokenDash

Si no tienes Git, instálalo con `sudo apt install -y git`.

```bash
git clone https://github.com/autohome365-create/TokenDash.git ~/tokendash
```

```bash
cd ~/tokendash
```

Así TokenDash queda en la carpeta `tokendash` de tu usuario. Todos los comandos de las guías se ejecutan dentro de esa carpeta.

### 3. Crear la configuración

Este comando crea el archivo `.env` con las claves de tu instalación, generadas al azar:

```bash
python3 scripts/init_env.py 192.168.1.50
```

Con la IP, TokenDash se podrá abrir desde cualquier equipo de tu red. Si solo lo vas a abrir desde el mismo equipo, ejecútalo sin la IP.

> **Guarda una copia del `.env` en un sitio seguro** (un USB, tu gestor de contraseñas). Si lo pierdes, la conexión con ChatGPT deja de funcionar y hay que repetirla. No lo compartas: contiene las claves de tu instalación.

### 4. Arrancar

```bash
docker compose up -d --build
```

La primera vez tarda entre 3 y 10 minutos, según el equipo: descarga y prepara todo lo necesario. Las siguientes veces arranca en segundos.

Para comprobar que funciona:

```bash
docker compose ps
```

Debes ver `web`, `worker`, `beat`, `db` y `redis` en estado `running`, y `web` como `healthy` pasado un minuto. `migrate` aparece como terminado (`exited (0)`), y es lo normal: solo se ejecuta al arrancar.

TokenDash vuelve a arrancar solo si el equipo se reinicia.

### 5. Entrar

Abre **http://192.168.1.50:8000** en el navegador de cualquier equipo o móvil de tu red, y sigue con [Primer acceso](USO.md#primer-acceso).

---

## Windows 10 / 11

### 1. Instalar Docker Desktop

1. Descarga **Docker Desktop** de [docker.com](https://www.docker.com/products/docker-desktop/) e instálalo con las opciones por defecto.
2. Reinicia si te lo pide y abre Docker Desktop. Acepta las condiciones y espera a que abajo a la izquierda aparezca «Engine running».
3. En **Settings → General**, marca **Start Docker Desktop when you sign in**. Si no, TokenDash no arranca hasta que abras Docker Desktop.

### 2. Descargar TokenDash

**Sin Git (lo más fácil):**

1. En [la página del proyecto](https://github.com/autohome365-create/TokenDash), pulsa **Code → Download ZIP**.
2. Descomprímelo donde quieras, por ejemplo en `Documentos\tokendash`.

**Con Git**, que facilita actualizar más adelante:

```powershell
git clone https://github.com/autohome365-create/TokenDash.git $HOME\tokendash
```

### 3. Abrir PowerShell en la carpeta

En el Explorador, entra en la carpeta de TokenDash, la que contiene `docker-compose.yml`. Haz clic con el botón derecho en un espacio vacío y pulsa **Abrir en Terminal**.

### 4. Crear la configuración

Si tienes Python instalado:

```powershell
py scripts\init_env.py 192.168.1.50
```

Si no tienes Python, el mismo programa se puede ejecutar dentro de Docker:

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim-bookworm python scripts/init_env.py 192.168.1.50
```

Si solo lo vas a abrir desde este PC, quita la IP del final. Guarda una copia del `.env`, como se explica en el [paso 3 de Linux](#3-crear-la-configuración).

Para que otros equipos lleguen al puerto 8000, la primera vez Windows puede preguntarte si permites el acceso de Docker a la red. Permítelo **solo en redes privadas**.

### 5. Arrancar y entrar

```powershell
docker compose up -d --build
```

Cuando termine, abre **http://localhost:8000** en este PC, o **http://192.168.1.50:8000** desde otro equipo. Sigue con [Primer acceso](USO.md#primer-acceso).

---

## ¿Y ahora?

1. [Primer acceso y usuarios](USO.md#primer-acceso)
2. [Conectar ChatGPT](USO.md#conectar-chatgpt)
3. [Vincular Claude](VINCULAR_CLAUDE.md)
4. Si quieres, [añadirlo a Home Assistant](HOME_ASSISTANT.md)

Si algo falla, mira [Problemas frecuentes](PROBLEMAS.md).
