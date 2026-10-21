# TokenDash

**Mira de un vistazo cuánto te queda de tus límites de ChatGPT y de Claude.**

![Panel de TokenDash con las tarjetas de ChatGPT y Claude y la gráfica de la última semana](docs/img/panel.png)

<sub>Captura con datos de ejemplo.</sub>

ChatGPT (Codex) y Claude limitan cuánto puedes usarlos: hay un límite que se renueva cada 5 horas y otro semanal. TokenDash los consulta solo, cada 20 minutos o con la frecuencia que elijas, y te los enseña en una página web con una gráfica de cómo evolucionan. Lo instalas una vez en un equipo de tu casa que esté siempre encendido (un miniPC, una Raspberry Pi, un NAS, un servidor) y lo abres desde el móvil o el ordenador.

- **No necesitas el PC encendido ni el navegador abierto.** El servidor lee los límites por su cuenta.
- **Se entiende de un vistazo.** Cada tarjeta se pone amarilla cuando pasas de la mitad de un límite y roja cuando pasas del 80 %.
- **Tú eliges cada cuánto se actualiza.** En **Administración → Ajustes**: desde cada 15 minutos hasta cada 6 horas.
- **¿Solo pagas una suscripción?** Elige en **Ajustes** «Solo ChatGPT» o «Solo Claude» y el panel muestra solo esa tarjeta, a todo lo ancho ([ver cómo queda](docs/img/panel-una-cuenta.png)).
- **Solo muestra datos reales.** Enseña los porcentajes que publican OpenAI y Anthropic, sin estimaciones. Si no hay lectura pone «Sin datos», nunca 0 %.
- **Tus datos se quedan en tu casa.** Todo corre en tu equipo; no hay ningún servicio externo de TokenDash.
- **Home Assistant.** Puedes poner en tu panel de Home Assistant la tarjeta de ChatGPT, la de Claude o la gráfica, cada una por separado, o usar los porcentajes como sensores.

> TokenDash es un proyecto personal, no oficial, con [licencia MIT](LICENSE). No está afiliado a OpenAI ni a Anthropic. Usa las mismas interfaces que sus clientes oficiales (Codex y Claude Code) y estas pueden cambiar sin aviso; si una lectura falla, el panel conserva la última buena con su fecha.

## Qué necesitas

| | |
|---|---|
| Un equipo siempre encendido | Linux (Ubuntu, Debian, Raspberry Pi OS de 64 bits…) o Windows 10/11. Procesador x86-64 o ARM64 (Raspberry Pi 4 o 5). Con 1 GB de RAM libre y 3 GB de disco sobra. |
| Docker | Es el programa que ejecuta TokenDash. La guía de instalación explica cómo instalarlo. |
| Tus cuentas | Una suscripción de ChatGPT que incluya Codex (Plus, Pro…) y/o una suscripción de Claude (Pro o Max). Basta con una de las dos. |

## Instalación rápida

Si ya tienes Docker y Git, en Linux son cuatro comandos. Cambia `192.168.1.50` por la IP de tu equipo (la ves con `hostname -I`):

```bash
git clone https://github.com/cmorato-dev/TokenDash.git ~/tokendash
```

```bash
cd ~/tokendash
```

```bash
python3 scripts/init_env.py 192.168.1.50
```

```bash
docker compose up -d --build
```

La primera vez tarda unos minutos. Después abre **http://192.168.1.50:8000** desde cualquier equipo de tu red.

**¿Es la primera vez que usas Docker, o estás en Windows?** Sigue la [guía de instalación paso a paso](docs/INSTALACION.md).

## Primer acceso

Entra con:

- **Usuario:** `admin`
- **Contraseña:** `tokendash`

TokenDash te pedirá elegir una contraseña nueva antes de dejarte continuar: la inicial es pública, porque está en esta página. Después, en **Administración → Usuarios**, puedes cambiar el nombre de usuario, crear otros usuarios o volver a cambiar la contraseña. Lo explica [la guía de uso](docs/USO.md).

## Conectar tus cuentas

En el panel, entra en **Conectar cuentas**:

1. **ChatGPT:** se hace desde el propio navegador, en un par de minutos. [Cómo conectar ChatGPT](docs/USO.md#conectar-chatgpt).
2. **Claude:** se hace una sola vez desde la consola del servidor, copiando y pegando cuatro comandos que el propio panel te da. [Cómo vincular Claude](docs/VINCULAR_CLAUDE.md).

En cuanto estén conectadas, las tarjetas pasan a «Actualizado» y la gráfica empieza a llenarse.

Si solo usas una de las dos, elígela antes en **Administración → Ajustes → Cuentas que usas**: la otra desaparece del panel y de «Conectar cuentas», y el servidor no la consulta.

## Cada cuánto se actualiza

Por defecto, TokenDash lee los límites cada 20 minutos. Para cambiarlo, entra en **Administración → Ajustes**, elige otra frecuencia (de 15 minutos a 6 horas) y pulsa **Guardar**. El cambio se aplica en el minuto siguiente, sin reiniciar nada. En esa misma página verás cuándo fue la última lectura automática y cuándo toca la próxima.

Además, el botón **Actualizar ahora** de cada tarjeta lee en el momento.

## Guías

| Guía | Para qué |
|---|---|
| [Instalación paso a paso](docs/INSTALACION.md) | Instalar Docker y TokenDash en Linux, Raspberry Pi o Windows |
| [Uso del panel](docs/USO.md) | Primer acceso, usuarios y contraseñas, conectar ChatGPT, frecuencia de actualización, leer las tarjetas y la gráfica |
| [Vincular Claude](docs/VINCULAR_CLAUDE.md) | Conectar tu cuenta de Claude, comando a comando |
| [Home Assistant](docs/HOME_ASSISTANT.md) | Tarjetas y sensores en tu panel de Home Assistant |
| [Mantenimiento](docs/MANTENIMIENTO.md) | Actualizar a una versión nueva, copias de seguridad, cambiar de equipo, HTTPS |
| [Problemas frecuentes](docs/PROBLEMAS.md) | Qué hacer si algo no funciona |
| [Cómo funciona por dentro](docs/ARQUITECTURA.md) y [desarrollo](docs/DESARROLLO.md) | Para quien quiera entender o modificar el código |

## Seguridad y privacidad

- TokenDash está pensado para tu **red de casa**. No lo abras a Internet redirigiendo puertos en el router; si quieres verlo desde fuera, usa una VPN (Tailscale, WireGuard…) o un proxy con HTTPS ([Mantenimiento → HTTPS](docs/MANTENIMIENTO.md#https)).
- La conexión de ChatGPT se guarda **cifrada** en la base de datos. La sesión de Claude la guarda el cliente oficial de Claude Code en un almacenamiento privado del contenedor, y TokenDash nunca la lee.
- TokenDash **no envía mensajes** a ChatGPT ni a Claude: solo pregunta por los límites, así que no gasta tu cuota.
- El archivo `.env` contiene las claves de tu instalación. No lo compartas ni lo subas a ningún sitio.
