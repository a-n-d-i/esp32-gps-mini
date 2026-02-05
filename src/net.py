import asyncio
import network
import sys
import time
from devices import Logger
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

log = Logger.getLogger().log

class Net():

    def __init__(self, txpower=None):
        self._buffer = b""
        self.espnow = None
        self.espnow_peers = []
        self.wifi_connected = False
        self.espnow_connected = False
        # Get a handle to wifi interfaces
        self.wlan = network.WLAN(network.WLAN.IF_STA)
        self.wlan.active(True)
        # Some boards (e.g. C3) have more stable connections with lower txpower (5)
        if txpower:
            self.wlan.config(txpower=txpower)
        # Chek if wifi has been set up already (e.g. in boot.py)
        if self.wlan.isconnected():
            self.wifi_connected = True

    def enable_wifi(self, ssid, key):
        """Connect to wifi if not already connected."""
        if self.wifi_connected == False or ssid != self.wlan.config('ssid'):
            self.wlan.disconnect()
            self.wlan.connect(ssid, key)
            log("Wifi connecting...(allowing up to 20 seconds to complete)")
            for i in range(20):
                time.sleep(1)
                if self.wlan.isconnected():
                    self.wifi_connected = True
                    break
            if not self.wlan.isconnected():
                log("WLAN Connection failed.")

        if self.wifi_connected:
            log(f"WLAN connected, SSID: {self.wlan.config('ssid')}, IP: {self.wlan.ifconfig()[0]}, mac: {self.wlan.config('mac')}, channel: {self.wlan.config("channel")}")



    @staticmethod
    def reset():
        """Reset network interfaces."""
        self.wlan.active(False)
        time.sleep(0.5)
        self.wlan.active(True)
        self.wlan.disconnect()
        # Setting txpower fixes ESP32 c3 supermini connection issues
        self.wlan.config(txpower=5)
