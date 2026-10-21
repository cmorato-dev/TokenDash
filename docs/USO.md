# Uso del panel

## Primer acceso

Abre TokenDash en el navegador, en `http://IP-DEL-EQUIPO:8000`, y entra con:

- **Usuario:** `admin`
- **Contraseña:** `tokendash`

Antes de dejarte continuar, TokenDash te pide una contraseña nueva. La inicial es pública, porque está publicada en GitHub, así que hasta que la cambies no puedes usar nada más.

1. En «Contraseña antigua» escribe `tokendash`.
2. Escribe dos veces la contraseña nueva.
3. Pulsa **Guardar la contraseña**.

La contraseña nueva tiene que tener al menos 8 caracteres, no puede ser solo números ni una contraseña muy común, y no puede volver a ser `tokendash`.

El usuario inicial solo se crea en una instalación nueva, cuando todavía no hay ningún usuario. Si ya existe alguno, no se crea.

## Usuarios y contraseñas

Todo se hace desde **Administración → Usuarios** (el enlace «Administración» de arriba a la derecha).

| Quiero… | Cómo |
|---|---|
| Cambiar mi contraseña | Enlace **Contraseña**, arriba a la derecha |
| Cambiar mi nombre de usuario | Administración → Usuarios → pulsa tu usuario → cambia «Nombre de usuario» → **Guardar** |
| Crear otro usuario | Administración → Usuarios → **Añadir usuario** → nombre y contraseña → **Guardar** |
| Cambiar la contraseña de otro usuario | Administración → Usuarios → pulsa el usuario → botón **Restablecer contraseña** |
| Borrar un usuario | Administración → Usuarios → pulsa el usuario → **Eliminar** |

Al crear un usuario, elige qué puede hacer marcando las casillas de su ficha:

| Tipo | Casillas marcadas | Qué puede hacer |
|---|---|---|
| Solo mirar | ninguna | Ver el panel y la gráfica |
| Gestor | «Es staff» | Además, pulsar «Actualizar ahora» y entrar en la administración |
| Administrador | «Es staff» y «Estado de superusuario» | Todo: conectar cuentas, gestionar usuarios y claves de Home Assistant |

Procura que siempre quede al menos un administrador.

## Conectar ChatGPT

Necesitas una cuenta de ChatGPT con Codex, por ejemplo Plus o Pro. TokenDash muestra los límites de Codex, que son los únicos que OpenAI publica en porcentaje.

1. Entra en **Conectar cuentas** (arriba a la derecha) y pulsa **Iniciar sesión con ChatGPT**.
2. Se abre la página oficial de OpenAI en otra pestaña. Entra con tu cuenta y autoriza.
3. Al terminar, esa pestaña muestra **«No se puede acceder a este sitio»**, en una dirección que empieza por `http://localhost:1455/auth/callback?…`. **Es lo esperado:** el código que necesita TokenDash va dentro de esa dirección.
4. Copia la dirección completa de la barra del navegador.
5. Vuelve a la pestaña de TokenDash, pégala en el recuadro que ha aparecido y pulsa **Completar conexión**. Hazlo en pocos minutos, porque el código caduca.

TokenDash guarda la conexión cifrada y la renueva solo. Tu contraseña de OpenAI nunca pasa por TokenDash. Para quitarla, pulsa **Desconectar**.

## Conectar Claude

Claude se vincula una sola vez desde la consola del equipo donde está TokenDash. El panel te da los comandos con un botón para copiar cada uno.

- Sigue los pasos de **Conectar cuentas → 2 · Claude**.
- La misma guía, con más detalle, está en [Vincular Claude](VINCULAR_CLAUDE.md).

## Cada cuánto se actualiza

TokenDash lee los límites cada 20 minutos. Para cambiarlo:

1. Entra en **Administración → Ajustes**.
2. Elige la frecuencia, entre cada 15 minutos y cada 6 horas.
3. Pulsa **Guardar**.

El cambio vale desde el minuto siguiente, sin reiniciar nada. La misma página dice cuándo fue la última lectura automática y cuándo será la próxima.

Elige una frecuencia más baja si te basta con mirar de vez en cuando. No hay opción de menos de 15 minutos, para no consultar las cuentas con demasiada frecuencia.

## Leer el panel

Cada tarjeta muestra un proveedor:

- **El círculo:** el porcentaje **disponible** del límite principal, el de 5 horas. Debajo aparece lo consumido y cuándo se renueva.
- **Las frases de abajo:** el resto de límites, como el semanal, cada uno con una barra de lo consumido. Por ejemplo: «Llevas un 26 % del límite esta semana. Se renueva el 27/10 a las 7:41».
- **El color:**
  - Hasta la mitad del límite, el del proveedor: verde ChatGPT y naranja Claude.
  - Si pasas del **50 %**, amarillo, y la tarjeta avisa «Has pasado de la mitad del límite».
  - Si pasas del **80 %**, rojo: «Te queda poco».

  El círculo sigue el límite principal y cada barra el suyo. Un límite que ya se ha renovado sale atenuado y sin color de aviso.
- **La etiqueta de arriba a la derecha:**
  - **Actualizado:** la última lectura fue bien.
  - **Sesión expirada:** hay que volver a conectar la cuenta.
  - **No se ha podido leer…:** el servidor no pudo consultar el límite.

  En todos los casos verás el último dato bueno con su fecha.
- **«Ya se ha renovado»:** el límite se reinició después de la última lectura. El número es el último conocido, no el actual. En la siguiente lectura se actualiza.
- **Actualizar ahora:** pide una lectura en ese momento. Hay que esperar un minuto entre pulsaciones.

TokenDash lee los límites con la frecuencia de **Ajustes**, cada 20 minutos por defecto. El panel abierto se refresca solo.

### La gráfica

«Evolución de los límites» muestra la media del porcentaje consumido en cada periodo.

- **Colores:** cada proveedor y cada límite tienen su color.
- **Líneas:** las líneas continuas son el límite de 5 horas y las discontinuas el semanal.
- **Periodo:** elige el periodo arriba a la derecha, desde 7 días hasta 5 años.
- **Agrupación:** con periodos largos agrupa por semanas, meses o años.
- **Detalle:** pasa el ratón por un punto para ver su valor.

Los límites se reinician, así que es normal que la línea suba y baje. Un hueco significa que en ese periodo no hubo lecturas.

## Home Assistant

Las tarjetas de ChatGPT y de Claude y la gráfica se pueden poner en Home Assistant, cada una por separado. Lo explica [Home Assistant](HOME_ASSISTANT.md).
