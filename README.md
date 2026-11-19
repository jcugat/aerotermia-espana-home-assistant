<p align="center">
  <img src="custom_components/aerotermia_espana/brand/icon.png" alt="Aerotermia España" width="140">
</p>

<h1 align="center">Aerotermia España para Home Assistant</h1>

<p align="center">
  Envía cada hora los datos de tu aerotermia a <a href="https://aerotermiaespana.sytes.net">aerotermiaespana.sytes.net</a>, sin tocar YAML.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=jcugat&repository=aerotermia-espana-home-assistant&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Abrir en Home Assistant"></a>
</p>

<p align="center">
  <a href="https://github.com/jcugat/aerotermia-espana-home-assistant/releases"><img src="https://img.shields.io/github/v/release/jcugat/aerotermia-espana-home-assistant?label=versi%C3%B3n" alt="Versión"></a>
</p>

---

La integración hace todo lo que antes había que montar a mano: el envío horario a la web, los contadores de desescarches y de arranques del compresor y la elección de sensores. Si tu máquina lleva el firmware [Midea-heat-pump-ESPHome](https://github.com/jcugat/Midea-heat-pump-ESPHome), encuentra sola todos los sensores.

## Qué necesitas

- Una cuenta en [aerotermiaespana.sytes.net](https://aerotermiaespana.sytes.net) con tu máquina dada de alta.
- Home Assistant 2025.1 o posterior.
- Tu aerotermia conectada a Home Assistant. Lo ideal es un ESP32 con el firmware [Midea-heat-pump-ESPHome](https://github.com/jcugat/Midea-heat-pump-ESPHome), pero también puedes elegir los sensores a mano.

## 1. Da de alta la máquina en la web

1. Entra en tu panel de [aerotermiaespana.sytes.net](https://aerotermiaespana.sytes.net).
2. En el paso 1, da de alta la máquina y elige el tipo de contador **Total Acumulado**.
3. Apunta estos tres datos, los necesitarás después:
   - la **API Key**
   - el **ID de la máquina**, el número que sale después de `#` (por ejemplo, 24)
   - el **minuto asignado** del paso 3

## 2. Instala la integración

Mira qué versión de Home Assistant tienes en **Configuración → Acerca de** y sigue los pasos que te tocan.

### Home Assistant 2026.11 o posterior (Marketplace)

Desde la 2026.11, HACS viene dentro de Home Assistant con el nombre **Marketplace**. No hay que instalar nada antes.

1. Pulsa este botón y confirma tu instancia:

   [![Abrir en Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jcugat&repository=aerotermia-espana-home-assistant&category=integration)

   Si prefieres hacerlo a mano: **Configuración → Marketplace → Añadir desde enlace**, pega `https://github.com/jcugat/aerotermia-espana-home-assistant` en **Enlace de GitHub** y pulsa **Añadir**.
2. La primera vez que abres el Marketplace sale el aviso **Antes de instalar desde el Marketplace**. Marca **Entiendo los riesgos y estoy de acuerdo.** y pulsa **Continuar**.
3. Si aún no has conectado GitHub, Home Assistant te lo pedirá (solo lee información pública). Pulsa **Conectar GitHub**, abre el enlace, escribe el código que te muestra y vuelve a Home Assistant. Después pulsa otra vez el botón del paso 1.
4. Si has usado el botón, en la ventana **Añadir repositorio personalizado** pulsa **Añadir**.
5. Abre **Aerotermia España**, pulsa **Instalar**, revisa la versión y pulsa **Instalar** otra vez.
6. Normalmente no hace falta reiniciar. Si sale el botón **Reiniciar Home Assistant**, púlsalo.

### Home Assistant 2026.10 o anterior (HACS)

Necesitas tener [HACS](https://www.hacs.xyz/) instalado.

1. Pulsa este botón y confirma tu instancia:

   [![Abrir en Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jcugat&repository=aerotermia-espana-home-assistant&category=integration)

   Si prefieres hacerlo a mano: abre **HACS**, pulsa los tres puntos de arriba a la derecha y elige **Repositorios personalizados**. Pega `https://github.com/jcugat/aerotermia-espana-home-assistant` en **Repositorio**, elige el tipo **Integración** y pulsa **Añadir**.
2. Si has usado el botón, en la ventana **Añadir repositorio personalizado** pulsa **Añadir**.
3. En la página de **Aerotermia España**, pulsa **Descargar** abajo a la derecha y confirma la descarga.
4. Reinicia Home Assistant.

## 3. Configúrala

1. Ve a **Configuración → Dispositivos y servicios → Añadir integración** y busca **Aerotermia España**.
2. Escribe la **API Key**, el **ID de la máquina** y el **minuto asignado** que apuntaste en la web.
3. Elige el dispositivo ESPHome de tu aerotermia. La integración busca sus sensores y rellena el siguiente paso.
   Si no usas el firmware [Midea-heat-pump-ESPHome](https://github.com/jcugat/Midea-heat-pump-ESPHome), déjalo vacío y elige los sensores a mano.
4. Revisa los sensores:
   - Arriba salen el consumo eléctrico y los sensores que la máquina no tiene (temperatura interior y humedad exterior). Si tienes un contador externo como Shelly o Wibeee, elígelo para el consumo, porque es más preciso.
   - En **Avanzado** están el resto de sensores detectados. Normalmente no hay que tocarlos.
5. Pulsa **Enviar**. A partir de ahí, la integración envía los datos cada hora en tu minuto asignado.

Para revisar o cambiar los sensores más adelante, abre la integración y pulsa **Configurar**. También puedes cambiar ahí la API Key o el minuto.

Si tienes varias máquinas, añade la integración una vez por cada una. Cada máquina tiene sus propios contadores.

## Comprobar que funciona

Cada máquina tiene un dispositivo **Aerotermia #ID**. En su sensor **Estado del envío** verás el resultado del último envío:

| Estado | Qué significa |
|---|---|
| OK | La web ha recibido los datos. |
| Omitido (sensor sin valor) | El consumo o la producción no tenían valor en ese momento. Revisa que la máquina esté conectada. |
| Rechazado: API Key no válida | La API Key o el ID de la máquina no coinciden con los de la web. Corrígelos en **Configurar**. |
| Rechazado: más de 1 por hora | La web solo acepta un envío por hora. Pasa si algo más está enviando datos de la misma máquina. |
| Error | La web no ha respondido bien. Mira los atributos del sensor para ver la respuesta. |

Para probar sin esperar a la hora siguiente, activa el modo depuración en la web y pulsa el botón **Enviar ahora**. Fuera del modo depuración, ese envío cuenta como el de esa hora.

## Si ya enviabas los datos con YAML

Si antes enviabas los datos con un `rest_command` y una automatización, desactívalos (o bórralos) al configurar la integración. Si no, se harán dos envíos por hora y la web rechazará uno de ellos.

Haz lo mismo con las automatizaciones que contaban desescarches o arranques del compresor. La integración tiene sus propios contadores, y si no las quitas los mismos eventos se contarán dos veces.

Los contadores de la integración empiezan en 0, no continúan desde los que tuvieras antes.

## Datos que se envían

Esta versión envía a la web estos datos. Solo el consumo eléctrico y la producción térmica son obligatorios. Si un dato opcional no tiene sensor, no se envía.

| Dato | Obligatorio | Sensor del firmware [Midea-heat-pump-ESPHome](https://github.com/jcugat/Midea-heat-pump-ESPHome) |
|---|---|---|
| Consumo eléctrico (kWh) | Sí | Electricity Consumption |
| Producción térmica (kWh) | Sí | Power Output |
| Calefacción: consumo (kWh) | No | Total heating power consumed for master unit |
| Calefacción: producción (kWh) | No | Total heating power produced for master unit |
| ACS: consumo (kWh) | No | Total DHW power consumed for master unit |
| ACS: producción (kWh) | No | Total DHW energy produced for master unit |
| Refrigeración: consumo (kWh) | No | Total cooling power consumed for master unit |
| Refrigeración: producción (kWh) | No | Total cooling energy produced for master unit |
| Horas de compresor | No | Compressor Operation Time |
| Temperatura exterior | No | Outdoor Ambient Temperature |
| Temperatura interior | No | La máquina no lo tiene. Elige un termómetro de la casa. |
| Humedad exterior | No | La máquina no lo tiene. Elige una estación meteorológica o una sonda exterior. |
| Desescarches | No | Los cuenta la integración a partir de Status BIT 1 Defrosting |
| Arranques del compresor | No | Los cuenta la integración a partir de Compressor Running |

Todos los kWh son contadores totales que nunca vuelven a 0. Si la web añade datos nuevos, saldrán en esta tabla junto con la versión de la integración que los envía.

## Entidades que crea

Para cada máquina, con su ID en lugar de `<id>`:

| Entidad | Para qué sirve |
|---|---|
| `sensor.aerotermia_<id>_defrost_cycles_total` | Desescarches totales. Nunca vuelve a 0. |
| `sensor.aerotermia_<id>_compressor_starts_total` | Arranques totales del compresor. Nunca vuelve a 0. |
| `sensor.aerotermia_<id>_push_status` | Estado del último envío, con la petición y la respuesta como atributos. |
| `button.aerotermia_<id>_push_now` | Envía los datos al momento. |

## Historial de versiones

Los cambios de cada versión están en [Releases](https://github.com/jcugat/aerotermia-espana-home-assistant/releases). Home Assistant te avisará cuando haya una versión nueva.
