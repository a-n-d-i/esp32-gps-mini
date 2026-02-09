""" Config variables - accessed as config.X in main.py"""

# General configuration
CRASH_RESET = True                  # Hard reset the esp32 device on crash.

# GPS device configuration
ENABLE_GPS = True                   # Enable GPS device for reading via UART serial.
GPS_UART = 1                        # UART device for GPS connection
GPS_TX_PIN = 21                      # ESP32 pin - connected to GPS RX pin
GPS_RX_PIN = 19                      # ESP32 pin - connected to GPS TX pin
GPS_BAUD_RATE = 115200              # For LC29HEA, set 460800 - set to 115200 for most other models
GPS_SETUP_COMMANDS = []             # List of NMEA commands (without $ and checksum) to be sent to GPS device on startup.
GPS_SETUP_RESPONSE_PREFIX = "$P"    # When reading responses to commands, only log lines which start with this prefix ($P = proprietary NMEA)
ENABLE_GPS_RESET = False            # If enabled, GPS will be reset via GPIO pin
GPS_RESET_PIN = 8                   # The GPIO pin to toggle to reset the GPS device
GPS_RESET_HIGH = True               # If True, pull the pin high to reset. If false, pull it low
GPS_SETUP_COMMANDS_RESET = False    # Reset GPS after writing setup commands. (GPS_RESET must be enabled).

# NMEA/Data configuration
PQTMEPE_TO_GGST = False             # Convert PQTMEPE messages to GGST (for accuracy info from Quectel devices)

# USB serial configuration
ENABLE_SERIAL_CLIENT = True        # Output GPS data via serial
SERIAL_UART = 2                     # UART device for serial output
SERIAL_TX_PIN = 23                   # Transmit pin
SERIAL_RX_PIN = 22                   # Receive pin
SERIAL_BAUD_RATE = 115200           # Serial baud rate
LOG_TO_SERIAL = False               # If True, log messages are sent over serial, rather than to sys.stdout (REPL)

# Bluetooth configuration
DEVICE_NAME = "ESP32_GPS"           # Bluetooth device name
ENABLE_BLUETOOTH = True            # Output via bluetooth device

# Wifi credentials - needed for NTRIP services
# Either set here, or ensure wifi is enabled in boot.py
WIFI_SSID = ""          # SSID for Wifi Access Point
WIFI_PSK = ""          # PSK for Wifi Access Point
#WIFI_TXPOWER = 5                  # Some boards (e.g. C3) have more stable connections with reduced txpower


# UDP
UDP_PORT = 9999
UDP_IP = "192.168.123.255"

# Client/Server config
NTRIP_CASTER = "www.sapos-xxxx.de"           # NTRIP caster address
NTRIP_PORT = 2101                   # NTRIP caster port
NTRIP_MOUNT = ""               # NTRIP mount. Note there is no support for NEAR/GGA automatic mountpoints.
NTRIP_CLIENT_CREDENTIALS = "c:c"    # NTRIP client credentials (in form user:pass). Centipede: "c:c". rtk2go: "your@email.com:none" (for all modes)
