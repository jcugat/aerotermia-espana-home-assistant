"""Constants for the Aerotermia España integration."""

DOMAIN = "aerotermia_espana"
PUSH_URL = "https://aerotermiaespana.sytes.net/api/v1/push.php"
DASHBOARD_URL = "https://aerotermiaespana.sytes.net/dashboard?inst_id={}"

CONF_INSTALLATION_ID = "installation_id"
CONF_MINUTE = "minute"
CONF_DEVICE_ID = "device_id"

# Payload fields, named as the web's push API expects them
CONSUMED = "consumed_kwh"
PRODUCED = "produced_kwh"
CONSUMED_HEATING = "consumed_heating_kwh"
PRODUCED_HEATING = "produced_heating_kwh"
CONSUMED_ACS = "consumed_acs_kwh"
PRODUCED_ACS = "produced_acs_kwh"
CONSUMED_COOLING = "consumed_cooling_kwh"
PRODUCED_COOLING = "produced_cooling_kwh"
COMPRESSOR_HOURS = "compressor_hours"
OUTDOOR_TEMP = "outdoor_temp"
INDOOR_TEMP = "indoor_temp"
OUTDOOR_HUMIDITY = "outdoor_humidity"
DEFROST_CYCLES = "defrost_cycles"
COMPRESSOR_STARTS = "compressor_starts"

# Binary sensors the integration counts to produce the two counter fields
DEFROST_SOURCE = "defrost_source"
COMPRESSOR_SOURCE = "compressor_source"
COUNTER_SOURCES = {DEFROST_CYCLES: DEFROST_SOURCE, COMPRESSOR_STARTS: COMPRESSOR_SOURCE}

SENSOR_FIELDS = (
    CONSUMED,
    PRODUCED,
    CONSUMED_HEATING,
    PRODUCED_HEATING,
    CONSUMED_ACS,
    PRODUCED_ACS,
    CONSUMED_COOLING,
    PRODUCED_COOLING,
    COMPRESSOR_HOURS,
    OUTDOOR_TEMP,
    INDOOR_TEMP,
    OUTDOOR_HUMIDITY,
)

# Field -> (domain, entity name in the Midea-heat-pump-ESPHome firmware).
# Matched on the entity's original name, so the user's entity_id prefix does not matter.
ESPHOME_NAMES = {
    CONSUMED: ("sensor", "Electricity Consumption"),
    PRODUCED: ("sensor", "Power Output"),
    CONSUMED_HEATING: ("sensor", "Total heating power consumed for master unit"),
    PRODUCED_HEATING: ("sensor", "Total heating power produced for master unit"),
    CONSUMED_ACS: ("sensor", "Total DHW power consumed for master unit"),
    PRODUCED_ACS: ("sensor", "Total DHW energy produced for master unit"),
    CONSUMED_COOLING: ("sensor", "Total cooling power consumed for master unit"),
    PRODUCED_COOLING: ("sensor", "Total cooling energy produced for master unit"),
    COMPRESSOR_HOURS: ("sensor", "Compressor Operation Time"),
    OUTDOOR_TEMP: ("sensor", "Outdoor Ambient Temperature"),
    DEFROST_SOURCE: ("binary_sensor", "Status BIT 1 Defrosting"),
    COMPRESSOR_SOURCE: ("binary_sensor", "Compressor Running"),
}

SIGNAL_STATUS = f"{DOMAIN}_status_{{}}"
