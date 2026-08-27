"""Constants for the STRATIS AC integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "stratis_ac"
PLATFORMS = [Platform.CLIMATE]

CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_ACCESS_TOKEN_EXPIRES_AT = "access_token_expires_at"
CONF_USER_ID = "user_id"

OAUTH_TOKEN_URL = "https://auth.stratisiot.com/oauth/token"
API_BASE_URL = "https://api.prod.stratisiot.net"
OAUTH_CLIENT_ID = "stratis-mobile-app"
OAUTH_REDIRECT_URI = "com.stratisiot.mobile.auth://app"
OAUTH_SCOPE = "openid profile email"

APP_ID = "com.stratisiot.mobile"
APP_VERSION = "2.25.0"
USER_AGENT = "STRATIS/378 HomeAssistant"

TOKEN_REFRESH_MARGIN = 120
REQUEST_TIMEOUT = 20
UPDATE_INTERVAL = timedelta(seconds=30)

STRATIS_MODE_AUTO = "AUTO"
STRATIS_MODE_COOL = "COOL"
STRATIS_MODE_HEAT = "HEAT"
STRATIS_MODE_OFF = "OFF"

STRATIS_FAN_AUTO = "FAN_AUTO"
STRATIS_FAN_ON = "FAN_ON"
