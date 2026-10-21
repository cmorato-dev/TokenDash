# Arquitectura de TokenDash

## Distribución

```text
Servidor Docker (Linux o Windows)
  Admin → login Codex → ProviderCredential cifrada
  Admin / claude_estado → modo «client» → el worker consulta Claude con el cliente oficial
  beat → Redis → worker → lee ChatGPT/Codex y Claude → ProviderStatus + UsageLog
  web → dashboard de cuotas e histórico
  Home Assistant → /ha/<módulo>/ (tarjeta «Página web») y /api/ha/<proveedor>/ (sensores), con una clave de solo lectura
```

**El servidor no depende de ningún PC ni de ningún navegador abierto.** Versiones anteriores tenían una extensión de navegador, un agente para los PC y un navegador en el servidor; se retiraron. Las migraciones `scraper/0004_retire_browser_and_agent.py` y `dashboard/0008_retire_browser_and_scraper_modes.py` borran sus tablas y dejan «sin conectar» (`none`) cualquier proveedor que usara esos modos.

## Componentes

| Fuente | Responsabilidad |
| --- | --- |
| `scraper/claude_usage.py` | Consulta `get_usage` en el cliente oficial, sin mensajes al modelo ni lectura de credenciales. **Implementación única del protocolo**, solo Python estándar |
| `scraper/claude_client.py` | Lector de cuotas de Claude en el servidor; carga `claude_usage.py` |
| `scraper/claude_client_views.py` | Estado de la sesión de Claude y activación del modo «cliente» desde el panel |
| `scraper/codex_oauth.py`, `codex_views.py` | Login PKCE de ChatGPT/Codex y consulta del servidor; tokens cifrados |
| `scraper/connection_views.py`, `urls.py` | Página «Conectar cuentas» (`/admin/conectar/`), solo superusuario |
| `scraper/quotas.py` | Lecturas de cuota (`QuotaReading`) y errores compartidos |
| `scraper/tasks.py` | `refresh_all`, `refresh_provider`, bloqueo atómico y persistencia |
| `scraper/management/commands/claude_estado.py` | Comprueba la sesión de Claude, activa el modo y guarda una lectura |
| `static/css/admin-theme.css` | Paleta del dashboard aplicada a todas las páginas del administrador, cargada desde `templates/admin/base_site.html` |
| `dashboard/` | Tarjetas de cuotas e histórico; módulos y sensores para Home Assistant |
| `dashboard/accounts.py` | Primer acceso: obliga a cambiar la contraseña inicial (`admin` / `tokendash`) antes de usar nada más |
| `dashboard/management/commands/crear_admin_inicial.py` | Crea ese usuario inicial, solo si no hay ningún usuario; lo ejecuta el servicio `migrate` |
| `scripts/init_env.py` | Crea el `.env` con secretos aleatorios; con una IP, lo deja accesible desde la red |

## Modelos

- `ProviderStatus` y `UsageLog`: cuotas actuales e histórico por ventana. No sumar ventanas incompatibles. `collection_mode` vale `none` (sin conectar), `api` (ChatGPT con credencial) o `client` (Claude con el cliente oficial). `client_auth_method` y `client_auth_checked_at` guardan el **tipo** de credencial del cliente oficial (nunca la credencial), publicado por el `worker` para que el panel pueda mostrarlo.
- `IntegrationKey`: claves de Home Assistant, de solo lectura. Solo se guarda su SHA-256; la clave se muestra una vez al crearla en el administrador.
- `ProviderCredential`: tokens de ChatGPT/Codex cifrados con Fernet y una clave derivada de `DJANGO_SECRET_KEY`. Debe conservarse ese secreto al migrar.

## Claude y ChatGPT

Claude: `scraper/claude_usage.py` inicia el cliente oficial en modo `stream-json`, sin persistencia de sesión, herramientas, MCP ni hooks de usuario/proyecto. Envía exclusivamente peticiones de control `initialize` y `get_usage` (`skip_behaviors=true`), nunca un mensaje `user`. Del resultado solo admite `five_hour`/`seven_day`, porcentaje entre 0 y 100 y fecha de reinicio. El propio cliente gestiona su autenticación con **su sesión de claude.ai**, guardada en el volumen privado `claude_config` (`claude auth login` dentro del contenedor); TokenDash no lee ni almacena esa credencial. No se usa `CLAUDE_CODE_OAUTH_TOKEN`: Anthropic limita ese token a las peticiones al modelo y no permite consultar la cuota, y la variable tendría prioridad sobre la sesión iniciada. La interfaz es experimental y debe fallar conservando la última lectura.

**La sesión vive en el `worker`, no en el `web`.** El volumen `claude_config` solo está montado en ese servicio, así que el panel no puede preguntar al cliente. El `worker` publica en `ProviderStatus.client_auth_method` el **tipo** de credencial (`claude.ai`, `none`, `oauth_token`…) y el panel lee ese registro. La tarea `scraper.tasks.check_claude_session` fuerza la comprobación cuando el operador pulsa «Comprobar ahora la sesión»; cada lectura de cuotas la actualiza igualmente.

ChatGPT/Codex: el superusuario inicia sesión una vez en OpenAI. Se valida PKCE/state y se guarda la credencial cifrada; beat/worker consultan periódicamente los límites. Los endpoints usados por el cliente Codex no son una API pública garantizada; cualquier fallo conserva la última lectura.

## Rutas principales

| Ruta | Uso |
| --- | --- |
| `/` | Dashboard de cuotas; login |
| `/accounts/password_change/` | Cambio de contraseña. Una sesión iniciada con la contraseña inicial no puede ir a ninguna otra página (las API responden 403) |
| `/api/status/`, `/api/history/` | Estado e histórico de cuotas; login o clave de Home Assistant. El histórico ofrece 7, 30, 90, 182, 365 y 1825 días, agrupados por día, semana, mes o año |
| `/ha/chatgpt/`, `/ha/claude/`, `/ha/grafica/` | Un módulo suelto para una tarjeta de Home Assistant. Se puede incrustar (sin `X-Frame-Options`) y no lleva datos: su JavaScript lee la clave del fragmento `#clave=…` y la envía como `Authorization: Bearer` |
| `/api/ha/<proveedor>/` | Valores de un proveedor para sensores REST; clave de Home Assistant o login |
| `/api/refresh/<proveedor>/` | Encola una actualización; POST, CSRF y `is_staff` |
| `/admin/conectar/` | Conectar cuentas; superusuario. La dirección antigua `/admin/scraper/scrapersession/connect/` redirige aquí |
| `/admin/conectar/codex/`, `/admin/conectar/claude/` | Acciones de ChatGPT y Claude; POST con CSRF |

## Servicios y despliegue

Compose mantiene `web`, `worker`, `beat`, PostgreSQL 16, Redis y `migrate`, que aplica las migraciones y crea el usuario inicial en una instalación vacía. Beat usa el planificador estándar de Celery con el calendario de `config/settings.py`. Los datos persistentes están en PostgreSQL; las credenciales cifradas requieren también el secreto Django. La sesión de Claude está en el volumen `claude_config`.

La imagen incluye el cliente oficial de Claude Code (`/opt/claude/bin/claude`), descargado del repositorio de lanzamientos de Anthropic y **verificado por SHA-256 contra su manifiesto firmado**; no se ejecuta ningún instalador externo. No incluye Playwright ni Chromium.

Instalación: [INSTALACION.md](INSTALACION.md). Copias, actualización y HTTPS: [MANTENIMIENTO.md](MANTENIMIENTO.md). Pruebas y desarrollo: [DESARROLLO.md](DESARROLLO.md).
