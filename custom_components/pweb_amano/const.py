"""Constants for the PWEB Amano integration."""
from datetime import timedelta

DOMAIN = "pweb_amano"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

SERVICE_REGISTER_DISCOUNT = "register_discount"
SERVICE_LIST_UNREGISTERED_VEHICLES = "list_unregistered_vehicles"

CONF_CAR_PLATES = "car_plates"
