# Aerotermia España

Integración de Home Assistant que envía cada hora los datos de tu aerotermia a [Aerotermia España](https://aerotermiaespana.sytes.net). Sustituye el `rest_command`, la automatización horaria y los contadores de desescarches y arranques del compresor que, si no, tendrías que añadir a mano.

## Instalación

1. Da de alta la máquina en la web (paso 1 del panel, con el tipo de contador en "Total Acumulado").
2. Instala esta integración (como repositorio personalizado en HACS, o copiando `custom_components/aerotermia_espana` a tu carpeta de configuración) y reinicia Home Assistant.
3. Añade la integración e introduce la API Key, el ID de la máquina y el minuto asignado que aparecen en la web.
4. Elige el dispositivo ESPHome de tu aerotermia. En las máquinas con el firmware [Midea-heat-pump-ESPHome](https://github.com/jcugat/Midea-heat-pump-ESPHome) todos los sensores se rellenan solos.

Para revisar o cambiar los sensores más adelante, abre la integración y pulsa **Configurar**.

## Entidades

Cada máquina tiene un dispositivo `Aerotermia #<id>` con:

- `sensor.aerotermia_<id>_defrost_cycles_total` y `sensor.aerotermia_<id>_compressor_starts_total`, contadores de por vida que se envían a la web
- `sensor.aerotermia_<id>_push_status`, el resultado del último envío, con la petición y la respuesta como atributos
- `button.aerotermia_<id>_push_now`, para probar con el modo depuración de la web
