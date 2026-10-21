# TokenDash en Home Assistant

En todas las direcciones, `SERVIDOR` es la IP del equipo de TokenDash (por ejemplo `192.168.1.50`) y `CLAVE` la clave que crearás en el paso 1.

TokenDash ofrece tres módulos independientes. Puedes añadir en Home Assistant uno, dos o los tres, cada uno en su propia tarjeta:

| Módulo | Dirección |
|---|---|
| ChatGPT | `http://SERVIDOR:8000/ha/chatgpt/#clave=CLAVE` |
| Claude | `http://SERVIDOR:8000/ha/claude/#clave=CLAVE` |
| Evolución de los límites | `http://SERVIDOR:8000/ha/grafica/#clave=CLAVE` |

Cada módulo se actualiza solo. Las tarjetas cada 30 segundos y la gráfica cada 10 minutos. La gráfica abre en 7 días. Para otro periodo, añade `?dias=` antes del `#`, por ejemplo `/ha/grafica/?dias=30#clave=CLAVE`. Valen 7, 30, 90, 182, 365 y 1825.

Si prefieres entidades propias de Home Assistant, para automatizaciones, historial o tarjetas nativas, cada proveedor tiene además su sensor. Están en la sección 4.

## 1. Crear la clave

1. En TokenDash, entra en **Administración → Claves de Home Assistant → Añadir**.
2. Ponle un nombre, por ejemplo «Home Assistant de casa», y guarda.
3. La página siguiente muestra la clave y las direcciones de los tres módulos, ya completas. **Cópialas en ese momento: la clave no se vuelve a mostrar.** TokenDash solo guarda su huella SHA-256.

La clave solo sirve para **leer** los límites. No puede pulsar «Actualizar ahora», conectar cuentas ni entrar en la administración.

- **Si se pierde o se filtra:** borra la clave en el administrador y crea otra.
- **Para saber si se usa:** la columna «último uso» indica si Home Assistant la está usando.

La clave va detrás de `#` en las direcciones de los módulos. El navegador no envía esa parte al servidor, así que la clave no aparece en sus registros. La página la pasa a la API en una cabecera.

## 2. Que Home Assistant llegue al servidor

Si al instalar pasaste la IP a `init_env.py`, TokenDash ya se ve desde la red: prueba a abrir `http://SERVIDOR:8000` desde otro equipo. Si no, sigue [Ver TokenDash desde otros equipos](MANTENIMIENTO.md#ver-tokendash-desde-otros-equipos).

- **Si abres Home Assistant por HTTPS** (por ejemplo, con Nabu Casa o un proxy): el navegador bloquea una tarjeta que cargue una página `http://` («contenido mixto»). En ese caso TokenDash tiene que servirse también por HTTPS, con un proxy: ver [Mantenimiento → HTTPS](MANTENIMIENTO.md#https).
- **Si lo abres por `http://` en la red local:** basta con la dirección `http://`.
- **Sensores:** no tienen esta limitación, porque los consulta el servidor de Home Assistant y no el navegador.

## 3. Tarjetas «Página web»

En un panel de Home Assistant:

1. Pulsa **Editar → Añadir tarjeta → Página web**.
2. Pega la dirección de un módulo.
3. Repite con cada módulo que quieras.

En YAML:

```yaml
type: iframe
url: http://SERVIDOR:8000/ha/claude/#clave=CLAVE
aspect_ratio: 95%
```

`aspect_ratio` fija el alto de la tarjeta en proporción a su ancho. Valores orientativos:

| Módulo | `aspect_ratio` |
|---|---|
| Tarjetas de ChatGPT y Claude | entre `90%` y `100%` |
| Gráfica en una columna ancha | `55%` |
| Gráfica en una columna estrecha | `110%` |

El módulo ocupa todo el ancho de la tarjeta y tiene fondo transparente.

## 4. Sensores (opcional)

Cada proveedor tiene su propia dirección. Se puede integrar uno sin el otro:

- `http://SERVIDOR:8000/api/ha/chatgpt/`
- `http://SERVIDOR:8000/api/ha/claude/`

Ambas se piden con la cabecera `Authorization: Bearer CLAVE` y devuelven:

| Campo | Contenido |
|---|---|
| `session_used_percent`, `session_resets_at` | Ventana de 5 horas: % consumido e instante de reinicio |
| `weekly_used_percent`, `weekly_resets_at` | Ventana semanal |
| `session_window_reset`, `weekly_window_reset` | `true` si la ventana se reinició después de la lectura: el valor es el último conocido, no el actual |
| `state`, `state_label` | Estado de la lectura (`ok`, `expired`, `unavailable`…) |
| `last_success_at`, `last_attempt_at` | Último dato válido y último intento |

Una ventana sin dato vale `null`, nunca 0. «Sin datos» no significa 0 % consumido.

Primero guarda la clave en `secrets.yaml`, con la palabra `Bearer` delante:

```yaml
tokendash_auth: "Bearer CLAVE"
```

Después, en `configuration.yaml`, añade un bloque por proveedor. Este es el de Claude; para ChatGPT, copia el bloque y cambia `claude` por `chatgpt`:

```yaml
rest:
  - resource: http://SERVIDOR:8000/api/ha/claude/
    headers:
      Authorization: !secret tokendash_auth
    scan_interval: 300
    sensor:
      - name: "Claude · sesión 5 h"
        unique_id: tokendash_claude_session
        unit_of_measurement: "%"
        state_class: measurement
        value_template: "{{ value_json.session_used_percent }}"
        availability: "{{ value_json.session_used_percent is not none }}"
        json_attributes: [session_resets_at, session_window_reset, state, last_success_at]
      - name: "Claude · semana"
        unique_id: tokendash_claude_weekly
        unit_of_measurement: "%"
        state_class: measurement
        value_template: "{{ value_json.weekly_used_percent }}"
        availability: "{{ value_json.weekly_used_percent is not none }}"
        json_attributes: [weekly_resets_at, weekly_window_reset, state, last_success_at]
```

TokenDash consulta los proveedores cada 20 minutos. Un `scan_interval` de 300 segundos basta.
