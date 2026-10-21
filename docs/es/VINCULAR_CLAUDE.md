# Vincular Claude con el servidor, paso a paso

[English](../LINK_CLAUDE.md) · **Español**

Se hace **una sola vez**: después el servidor lee la cuota de Claude periódicamente (cada 20 minutos por defecto) sin que nadie tenga el navegador ni el PC encendidos. Solo se repite si la sesión caduca o si se cierra sesión en claude.ai desde todos los dispositivos.

Necesitas una suscripción de Claude (Pro o Max). TokenDash usa el cliente oficial de Claude Code, que ya viene dentro de TokenDash: no tienes que instalar nada.

**Qué hace falta**

- Una terminal en el equipo donde corre TokenDash, o acceso por SSH. En Windows vale PowerShell abierto en la carpeta de TokenDash; entonces sáltate el paso 1.
- La carpeta donde está `docker-compose.yml` de TokenDash. En esta guía se usa `~/tokendash`, la de la [guía de instalación](INSTALACION.md); cámbiala si es otra.
- La cuenta de claude.ai cuyo uso quieres ver, y un navegador en cualquier equipo (vale el móvil).

En los pasos 3 a 5 copias una dirección de la terminal, la abres en el navegador, inicias sesión y pegas en la terminal el código que te da la página. Si la cuenta es de otra persona, ella hace el paso 4 y te devuelve el código.

---

## Paso 1 · Entrar en el servidor

```bash
ssh usuario@servidor-tokendash
```

```bash
cd ~/tokendash
```

> Si al ejecutar `docker` aparece *permission denied*, antepón `sudo` a todos los comandos `docker` de esta guía.

## Paso 2 · Ver si ya está vinculado

```bash
docker compose exec worker claude auth status
```

Busca la línea `"authMethod"`:

| Lo que aparece | Qué significa | Qué hacer |
| --- | --- | --- |
| `"authMethod": "claude.ai"` | Ya está vinculado | Salta al **paso 6** |
| `"authMethod": "none"` o `"loggedIn": false` | No hay sesión | Sigue con el paso 3 |
| `"authMethod": "oauth_token"` | Queda un token de `setup-token`, que no sirve | Ver «Problemas» al final |

## Paso 3 · Iniciar sesión

```bash
docker compose exec worker claude auth login
```

El terminal muestra algo parecido a esto y **se queda esperando**. No lo cierres:

```text
Opening browser to sign in…
If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&client_id=...
Paste code here if prompted >
```

Copia **la dirección completa** que empieza por `https://claude.com/cai/oauth/authorize`. Es muy larga: si el terminal la parte en varias líneas, cópiala entera (o pégala en un bloc de notas y únela en una sola línea). Ábrela en el navegador.

## Paso 4 · Autorizar en el navegador

1. Abre la dirección en cualquier navegador.
2. Inicia sesión con la cuenta de claude.ai (la que usas para Claude Code o la app).
3. Pulsa **Autorizar**.
4. La página muestra un **código**. Cópialo con el botón de copiar de la página.

## Paso 5 · Pegar el código

Pega el código en el terminal que estaba esperando y pulsa **Enter**. Debe aparecer `Login successful`.

> **Pega solo el código.** Si pegas también la dirección de la página, el cliente lo rechaza.
> El código caduca a los pocos minutos. Si tarda mucho o falla, repite desde el paso 3.

## Paso 6 · Comprobar y activar

```bash
docker compose exec worker python manage.py claude_status
```

Este comando comprueba la sesión, deja activada la lectura de la cuota en el servidor y la actualiza en ese momento. La salida correcta se parece a esta (los números y las fechas cambian). Sale en inglés salvo que tengas `LANGUAGE_CODE=es` en el `.env`; entonces sale en español:

```text
Sesión de Claude en el servidor: Sesión de claude.ai conectada
  Sesión de 5 horas: 4 % consumido · Se reinicia el 21/10 a las 14:19
  Semana · todos los modelos: 65 % consumido · Se reinicia el 25/10 a las 21:59
Cuota de Claude actualizada en el dashboard (21/10 14:05).
```

Si termina con `Inicia la sesión con: …` (en inglés, `Sign in with: …`), vuelve al paso 3.

> Las guías antiguas llamaban a este comando `claude_estado`. Sigue funcionando.

## Paso 7 · Mirar el dashboard

Abre TokenDash en el navegador. La tarjeta de Claude debe estar en **Actualizado**, con la hora de la última lectura. En **Administración → Conectar cuentas → 2 · Claude** aparece «Sesión de claude.ai conectada».

Ya está. No hace falta tocar nada más: el servidor renueva la sesión y la lectura solo.

---

## Problemas

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `no configuration file provided` | No estás en la carpeta de TokenDash | `cd ~/tokendash` (o la carpeta correcta) |
| `service "worker" is not running` | Los contenedores están parados | `docker compose up -d` y repetir |
| `"authMethod": "oauth_token"` | Hay `CLAUDE_CODE_OAUTH_TOKEN` en el `.env` | Borrar esa línea del `.env`, ejecutar `docker compose up -d worker` y repetir desde el paso 3 |
| El código no se acepta | Se pegó con la dirección, o caducó | Repetir desde el paso 3 y pegar solo el código |
| `No se ha podido leer la cuota` (`The quota could not be read`) con la sesión conectada | El plan de la cuenta no publica cuotas o el cliente cambió | Comprobar el plan en claude.ai; el dashboard conserva la última lectura válida |

**No uses `claude setup-token`.** Ese token solo permite enviar mensajes al modelo; Anthropic no le deja leer la cuota.

## Seguridad

- La sesión se guarda en el volumen privado `claude_config` del contenedor `worker`. No pasa por el `.env` ni por la base de datos.
- TokenDash **no lee, no guarda y no muestra** esa credencial: solo publica el porcentaje y la fecha de reinicio.
- No envíes capturas de la salida completa de `claude auth status`: incluye el correo de la cuenta. Basta con la línea `authMethod`.
- Para desvincular el servidor: `docker compose exec worker claude auth logout`.
