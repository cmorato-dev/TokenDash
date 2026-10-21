# Mantenimiento

Todos los comandos se ejecutan en la carpeta de TokenDash, la que contiene `docker-compose.yml`, por ejemplo después de `cd ~/tokendash`. En Windows, abre ahí PowerShell («Abrir en Terminal»).

## Ver cómo está

```bash
docker compose ps
```

Muestra si cada parte está en marcha:

| Parte | Qué hace |
|---|---|
| `web` | La página web |
| `worker` | Lee los límites |
| `beat` | Le avisa cada 20 minutos |
| `db` | La base de datos |
| `redis` | La cola de tareas |

Para ver los últimos mensajes de cada parte:

```bash
docker compose logs --tail=50 web worker beat
```

## Parar, arrancar y reiniciar

| Quiero | Comando |
|---|---|
| Parar TokenDash | `docker compose stop` |
| Arrancarlo otra vez | `docker compose start` |
| Reiniciarlo | `docker compose restart` |

Los datos no se pierden al parar ni al reiniciar el equipo.

> **No uses `docker compose down -v`.** La `-v` borra la base de datos, el histórico y la sesión de Claude. `docker compose down`, sin `-v`, es seguro.

## Actualizar a una versión nueva

Antes de actualizar, haz una [copia de seguridad](#copias-de-seguridad).

**Si lo descargaste con Git:**

```bash
git pull
```

```bash
docker compose up -d --build
```

**Si lo descargaste en ZIP:**

1. Descarga el ZIP nuevo.
2. Copia en su carpeta tu archivo `.env`.
3. Ejecuta `docker compose up -d --build` desde la carpeta nueva.

Los datos están en Docker, no en la carpeta, así que no se pierden.

Al arrancar, TokenDash aplica solo los cambios que necesite la base de datos. Usuarios, histórico y conexiones se conservan.

Para liberar el espacio de las versiones viejas:

```bash
docker image prune
```

## Copias de seguridad

Una copia completa tiene dos partes. Guarda las dos en un sitio seguro, fuera del equipo, porque contienen tus usuarios y la conexión de ChatGPT cifrada.

1. **El archivo `.env`.** Basta con copiarlo una vez, porque no cambia. Sin él no se puede descifrar la conexión de ChatGPT.
2. **La base de datos**, con usuarios, histórico, conexión de ChatGPT y claves de Home Assistant.

Para copiar la base, ejecuta estos dos comandos:

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/tokendash.dump'
```

```bash
docker compose cp db:/tmp/tokendash.dump ./tokendash-copia.dump
```

Te deja el archivo `tokendash-copia.dump` en la carpeta.

La sesión de Claude no entra en la copia. Si cambias de equipo, se vuelve a vincular en cinco minutos con [la guía](VINCULAR_CLAUDE.md).

### Copia automática todos los días (Linux)

1. Ejecuta `crontab -e`.
2. Añade esta línea al final, cambiando `/home/usuario/tokendash` por tu carpeta.

```cron
30 3 * * * cd /home/usuario/tokendash && docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/tokendash.dump' && docker compose cp db:/tmp/tokendash.dump ./copias/tokendash-$(date +\%a).dump
```

Antes de usarla, crea la carpeta con `mkdir ~/tokendash/copias`. Hace una copia cada noche a las 3:30 y guarda una por día de la semana, así que siempre tienes las de los últimos 7 días.

## Restaurar una copia o cambiar de equipo

En el equipo nuevo:

1. Instala Docker y descarga TokenDash, como en la [guía de instalación](INSTALACION.md), pero **no** ejecutes `init_env.py`.
2. Copia tu `.env` antiguo a la carpeta. Si el equipo nuevo tiene otra IP, cámbiala dentro del archivo: está en `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS`.
3. Copia también el archivo `tokendash-copia.dump`.
4. Arranca solo la base de datos y restaura la copia:

```bash
docker compose up -d --wait db redis
```

```bash
docker compose cp ./tokendash-copia.dump db:/tmp/tokendash.dump
```

```bash
docker compose exec -T db sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/tokendash.dump'
```

5. Arranca el resto:

```bash
docker compose up -d --build
```

6. Entra con tu usuario de siempre. ChatGPT sigue conectado. Para Claude, repite [la vinculación](VINCULAR_CLAUDE.md).

La restauración solo funciona sobre una instalación **vacía**, recién creada. Si ya habías arrancado TokenDash en el equipo nuevo, bórrala antes con `docker compose down -v`, sabiendo que eso borra lo que tuviera ese equipo.

No dejes los dos equipos funcionando a la vez con la misma copia: apaga el antiguo con `docker compose stop`.

## Ver TokenDash desde otros equipos

Si al instalar no pusiste la IP, o la IP ha cambiado, edita el `.env` con cualquier editor de texto:

```dotenv
WEB_BIND=0.0.0.0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://192.168.1.50:8000
```

Cambia `192.168.1.50` por la IP del equipo y aplica el cambio:

```bash
docker compose up -d
```

En `DJANGO_ALLOWED_HOSTS` puedes añadir varias direcciones separadas por comas, por ejemplo el nombre del equipo (`minipc.local`).

## Cambiar otros ajustes

En el `.env`:

| Variable | Para qué | Por defecto |
|---|---|---|
| `TIME_ZONE` | Zona horaria de las fechas (`America/Mexico_City`, `America/Argentina/Buenos_Aires`…) | `Europe/Madrid` |
| `SCRAPE_INTERVAL_MINUTES` | Cada cuántos minutos se leen los límites (mínimo 15) | `20` |
| `WEB_BIND` | `0.0.0.0` para abrirlo desde la red; sin ella, solo desde el propio equipo | solo el equipo |

Después de cambiar algo, ejecuta `docker compose up -d`.

**No cambies `DJANGO_SECRET_KEY`.** Si la cambias, la conexión de ChatGPT deja de funcionar y hay que repetirla.

## HTTPS

En casa, `http://` es suficiente. HTTPS hace falta en dos casos:

- quieres entrar desde fuera de casa con un proxy;
- abres Home Assistant con `https://` y quieres ver los módulos de TokenDash, porque el navegador no mezcla páginas `https` y `http`.

**La forma más sencilla de verlo desde fuera es una VPN**, como Tailscale o WireGuard. Con ella no hay que tocar nada de TokenDash.

Si ya usas un proxy inverso (Nginx Proxy Manager, Caddy, Traefik…):

1. Crea en él una dirección, por ejemplo `https://tokendash.midominio.es`, que reenvíe a `http://IP-DEL-EQUIPO:8000`.
2. Pon en el `.env`:

   ```dotenv
   DJANGO_ALLOWED_HOSTS=tokendash.midominio.es,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://tokendash.midominio.es
   DJANGO_SECURE_COOKIES=1
   DJANGO_TRUST_PROXY_HEADERS=1
   ```

3. Aplica con `docker compose up -d`.

Activa `DJANGO_TRUST_PROXY_HEADERS=1` solo si **todo** el acceso pasa por el proxy. Si el proxy corre en el mismo equipo, deja `WEB_BIND` sin definir, para que el puerto 8000 no se vea desde la red.

## Desinstalar

```bash
docker compose down -v
```

Ese comando borra TokenDash y todos sus datos. Después puedes borrar la carpeta.
