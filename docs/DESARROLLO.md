# Desarrollo

Para quien quiera modificar TokenDash. Cómo está hecho por dentro: [ARQUITECTURA.md](ARQUITECTURA.md).

## Pila

- **Aplicación:** Django 5.2, con Celery (`worker` y `beat`), PostgreSQL 16 y Redis, orquestados con Docker Compose.
- **Estilos:** Tailwind CSS v4, compilado desde `assets/app.css`. El CSS compilado (`static/css/app.css`) se incluye en el repositorio y se vuelve a generar al construir la imagen.
- **Ficheros estáticos:** whitenoise.
- **Idioma:** la interfaz está en español. El código y sus comentarios, en inglés.

## Entorno local

Requisitos: Python 3.12 y Node 22. Sin `DB_HOST`, Django usa SQLite local y no necesita PostgreSQL ni Redis para las pruebas.

En Linux o macOS:

```bash
python3.12 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m playwright install chromium
```

```bash
npm ci
```

```bash
npm run build:css
```

```bash
export DJANGO_SECRET_KEY=solo-comprobaciones-locales
```

```bash
.venv/bin/python manage.py check
```

```bash
.venv/bin/python manage.py makemigrations --check --dry-run
```

```bash
.venv/bin/python manage.py test
```

En Windows, con PowerShell:

```powershell
py -3.12 -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```powershell
$env:DJANGO_SECRET_KEY='solo-comprobaciones-locales'
```

```powershell
.\.venv\Scripts\python.exe manage.py test
```

**Comprobaciones visuales.** Abren el dashboard y la página «Conectar cuentas» en un Chromium local, con datos simulados. Dejan capturas en `artifacts/`, que no forma parte del proyecto:

```bash
.venv/bin/python manage.py collectstatic --noinput
```

```bash
.venv/bin/python scripts/check_dashboard.py
```

```bash
.venv/bin/python scripts/check_connection_ui.py
```

**Capturas del README.** `docs/img/panel.png` y `docs/img/panel-una-cuenta.png` se generan con datos inventados, en una base de pruebas propia:

```bash
.venv/bin/python scripts/capturas_demo.py
```

Playwright solo se usa en estas comprobaciones y en las capturas. La imagen de producción no lo incluye.

No ejecutes las pruebas con el `.env` de una instalación real ni con su `DB_HOST`. Django crea su propia base de pruebas.

## Probar una imagen antes de usarla

Construye con otra etiqueta y pasa la suite dentro de la imagen, sin red:

```bash
docker build -t tokendash:prueba .
```

```bash
docker run --rm --network none -e DJANGO_SECRET_KEY=solo-comprobaciones -e DB_HOST= tokendash:prueba sh -c "mkdir /tmp/t && cp -r /app/. /tmp/t && cd /tmp/t && python manage.py test --verbosity 0"
```

## Reglas del proyecto

- **Datos reales:** mostrar solo cuotas que publique el proveedor. No inventar porcentajes ni convertir tokens en porcentajes.
- **«Sin datos» no es 0 %:** si falla una lectura, conservar la última válida con su fecha.
- **Ventanas separadas:** las ventanas de 5 horas, semana y mes no se suman.
- **Credenciales:**
  - No imprimir tokens, credenciales ni respuestas crudas de los proveedores en logs, pruebas o errores.
  - La sesión de Claude es del cliente oficial: TokenDash no la lee.
- **Cliente de Claude:**
  - Entra en la imagen verificado por SHA-256 contra el manifiesto firmado de Anthropic. No se ejecutan instaladores externos.
  - Para cambiar su versión, ajusta `CLAUDE_CODE_VERSION` en el `Dockerfile` y vuelve a pasar `scraper/test_claude_usage.py`.
  - El protocolo `get_usage` es experimental.
- **Sin evasión:** no añadir automatización de navegadores para iniciar sesión, ocultación de automatización ni resolución de CAPTCHA.
- **Pruebas:** con fixtures validan el software, no la compatibilidad con cuentas reales.

## Dependencias

- **Python:** las dependencias directas están acotadas por versión compatible en `requirements.txt`.
- **Node:** `package-lock.json` fija Tailwind.
- **Aviso de npm:** la cadena de compilación de Tailwind incluye `braces` a través de su observador de archivos. npm avisa de [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), sin versión corregida publicada. Ese paquete solo se usa al compilar fuentes locales, y Node no se copia a la imagen final.
