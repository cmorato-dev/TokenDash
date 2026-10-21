# Problemas frecuentes

Los comandos se ejecutan en la carpeta de TokenDash. Si algo no aparece aquí, mira los mensajes con `docker compose logs --tail=100 web worker` y busca la línea de error.

## Instalación y acceso

| Síntoma | Causa probable | Solución |
|---|---|---|
| `permission denied` al usar `docker` | Tu usuario no está en el grupo de Docker | `sudo usermod -aG docker $USER`, cierra sesión y vuelve a entrar. O antepón `sudo` |
| `no configuration file provided` | No estás en la carpeta de TokenDash | `cd ~/tokendash`, o la carpeta donde lo descargaste |
| `env file .env not found` o `Define POSTGRES_PASSWORD en .env` | Falta el `.env` | Ejecuta `python3 scripts/init_env.py IP` ([instalación, paso 3](INSTALACION.md#3-crear-la-configuración)) |
| La página no carga desde otro equipo, pero sí en el propio | TokenDash solo escucha en el propio equipo | [Ver TokenDash desde otros equipos](MANTENIMIENTO.md#ver-tokendash-desde-otros-equipos). Revisa también el cortafuegos (`sudo ufw allow 8000/tcp` en Ubuntu) |
| «Bad Request (400)» | La dirección que usas no está en `DJANGO_ALLOWED_HOSTS` | Añádela al `.env` y ejecuta `docker compose up -d` |
| «Prohibido (403) · CSRF» al entrar | La dirección no está en `DJANGO_CSRF_TRUSTED_ORIGINS` | Añade `http://IP:8000`, o tu dirección `https://…`, y ejecuta `docker compose up -d` |
| `web` no llega a `healthy` | La base de datos aún arranca, o hay un error | Espera un minuto. Si sigue igual, mira `docker compose logs migrate web` |
| He olvidado la contraseña | — | Ejecuta `docker compose exec web python manage.py changepassword TU_USUARIO`. Si tampoco recuerdas el usuario: `docker compose exec web python manage.py createsuperuser` |
| `admin` / `tokendash` no funciona | Ya hay usuarios: el usuario inicial solo se crea en una instalación vacía | Usa tu usuario. Si no lo recuerdas, mira la fila anterior |

## ChatGPT

| Síntoma | Solución |
|---|---|
| Tras autorizar sale «No se puede acceder a este sitio» | Es lo normal. Copia la dirección completa de esa pestaña y pégala en TokenDash |
| «ChatGPT no ha aceptado el código» o «El inicio de sesión ha caducado» | Repite desde «Iniciar sesión con ChatGPT» y pega la dirección en menos de 5 minutos. Copia la dirección entera, empieza por `http://localhost:1455/auth/callback?code=` |
| «Sesión expirada, reautenticar» o «La conexión con ChatGPT ha caducado» | OpenAI cerró la sesión, por ejemplo al cerrar sesión en todos los dispositivos o cambiar la contraseña. Vuelve a conectar la cuenta |
| Dejó de funcionar tras mover TokenDash o regenerar el `.env` | Cambió `DJANGO_SECRET_KEY`. Vuelve a conectar la cuenta |
| No aparece el límite de los chats normales | ChatGPT no publica ese porcentaje. Solo hay porcentajes para Codex |

## Claude

| Síntoma | Solución |
|---|---|
| «Sin sesión iniciada» en Conectar cuentas | Vincula Claude con [la guía](VINCULAR_CLAUDE.md) |
| Dejó de leer después de semanas funcionando | La sesión caducó o se cerró. Repite [la vinculación](VINCULAR_CLAUDE.md) desde el paso 3 |
| `"authMethod": "oauth_token"` | Hay una línea `CLAUDE_CODE_OAUTH_TOKEN` en el `.env`. Bórrala, ejecuta `docker compose up -d` y vuelve a vincular |
| He usado `claude setup-token` y no lee la cuota | Ese token no sirve para la cuota. Usa `claude auth login`, como dice la guía |

Más casos en [Vincular Claude → Problemas](VINCULAR_CLAUDE.md#problemas).

## Datos

| Síntoma | Explicación |
|---|---|
| «Sin datos» | Todavía no hay ninguna lectura buena. **No significa 0 %** |
| El porcentaje no cambia y la fecha es antigua | La última lectura falló. TokenDash conserva la última buena con su fecha. La tarjeta dice por qué falló |
| «Ya se ha renovado» | El límite se reinició después de la última lectura. Se actualiza en la siguiente lectura, según la frecuencia de Administración → Ajustes, o al pulsar «Actualizar ahora» |
| La gráfica está vacía | Aparece tras la primera lectura correcta |
| Falta la tarjeta de ChatGPT o la de Claude | En Administración → Ajustes → Cuentas que usas está elegida solo la otra |
| «El servidor de TokenDash no ha respondido bien» o «No hay conexión con el servidor» | TokenDash se estaba reiniciando o está parado. El panel reintenta solo; si no se va, mira `docker compose ps` |
| Las horas no coinciden con las mías | Cambia `TIME_ZONE` en el `.env` ([ajustes](MANTENIMIENTO.md#cambiar-otros-ajustes)) |

## Home Assistant

| Síntoma | Solución |
|---|---|
| La tarjeta sale en blanco | Si abres Home Assistant con `https://`, el navegador bloquea las páginas `http://`. Lee la [sección de red de la guía](HOME_ASSISTANT.md#2-que-home-assistant-llegue-al-servidor) |
| «Falta la clave» | Falta `#clave=…` al final de la dirección del módulo |
| «La clave de Home Assistant no es válida o se ha borrado» | La clave se borró o está mal copiada. Crea otra en Administración → Claves de Home Assistant |
| La tarjeta dice que el servidor «rechazó la conexión» | Home Assistant no llega al equipo. Prueba antes a abrir `http://IP:8000` en el navegador |
| El módulo o el sensor de una cuenta dice «Not Found» o «Proveedor desconocido» | Esa cuenta está desactivada en Administración → Ajustes → Cuentas que usas |
