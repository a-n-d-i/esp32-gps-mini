import asyncio
from os import rename
from machine import Pin, reset
from sys import print_exception
from time import sleep_ms
from net import Net
import config as cfg
from devices import Logger

# Enable debugging for current thread

try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

log = Logger.getLogger().log


class ESP32GPS():

    def __init__(self):
        self.net = None
        self.blue = None
        self.gps = None
        self.irq_event = asyncio.ThreadSafeFlag()
        self.espnow_event = asyncio.ThreadSafeFlag()
        self.shutdown_event = asyncio.Event()
        self.serial = None
        self.ntrip_caster = None
        self.ntrip_server = None
        self.ntrip_client = None
        self.tasks = []

    def gps_reset(self):
        if (
            hasattr(cfg, "ENABLE_GPS_RESET") and
            (pin := getattr(cfg, "GPS_RESET_PIN", None))
        ):
            log(f"Resetting GPS device via pin: {pin}")
            reset_pin = Pin(pin, Pin.OUT)
            # Default to resetting by going 'high'
            reset_val = 1
            # Otherwise, reset by going 'low'
            if getattr(cfg, "GPS_RESET_MODE", "high") != "high":
                reset_val = 0

            # Sset reset value
            reset_pin.value(reset_val)
            sleep_ms(100)
            # Revert to inverse of reset value
            reset_pin.value(not reset_val)


    def hard_reset(self):
        """Reset device and GPS device."""

        self.gps_reset()
        # Reset esp32 device
        reset()


    def setup_gps(self):
        log("Enabling GPS device.")
        from devices import GPS
        try:
            self.gps = GPS(uart=cfg.GPS_UART, baudrate=cfg.GPS_BAUD_RATE, tx=cfg.GPS_TX_PIN, rx=cfg.GPS_RX_PIN)
        except (AttributeError, ValueError, OSError) as e:
            log(f"Error setting up GPS: {e}")
            return
        if hasattr(self.gps, "uart"):
            if (cmds := getattr(cfg, "GPS_SETUP_COMMANDS", None)):
                # Prefix used to filter response messages
                prefix = getattr(cfg, "GPS_SETUP_RESPONSE_PREFIX", "")
                for cmd in cmds:
                    self.gps.write_nmea(cmd, prefix)
                if hasattr(cfg, "GPS_SETUP_COMMANDS_RESET"):
                    self.gps_reset()

    def setup_serial(self):
        from devices import Serial
        log_serial = getattr(cfg, "LOG_TO_SERIAL", False)
        try:
            self.serial = Serial(uart=cfg.SERIAL_UART, baudrate=cfg.SERIAL_BAUD_RATE, tx=cfg.SERIAL_TX_PIN, rx=cfg.SERIAL_RX_PIN, log_serial=log_serial)
        except AttributeError:
            # No config options passed in
            pass


    def setup_networks(self):
        txpower = getattr(cfg, "WIFI_TXPOWER", None)
        self.net = Net(txpower=txpower)
        # Note: We start wifi first, as this will define the channel to be used.
        # Wifi connections also enable power management, which espnow startup will later disable.
        # See: https://docs.micropython.org/en/latest/library/espnow.html#espnow-and-wifi-operation
        if ((ssid := getattr(cfg, "WIFI_SSID", None)) and (psk := getattr(cfg, "WIFI_PSK"))):
            self.net.enable_wifi(ssid=cfg.WIFI_SSID, key=cfg.WIFI_PSK)
        # Start ESPNow if peers provided
        peers = getattr(cfg, "ESPNOW_PEERS", set())


    def esp32_write_data(self, value):
        """Callback to run if device is written to (BLE, Serial)"""
        self.gps.uart.write(value)

    async def ntrip_client_read(self):
        """Read data from NTRIP client and write to GPS device."""
        while True:
            try:
                data = await self.ntrip_client.iter_data()
                #print(data)
                self.esp32_write_data(data)
            except Exception as e:
                print_exception(e)

    async def gps_reader(self):
        # FIXME: Move to code where this task is instantiated
        log("Starting GPS reader task.")
        if (
            "server" in getattr(cfg, "NTRIP_MODE", []) or
            hasattr(cfg, "ENABLE_SERIAL_CLIENT") or
            (self.blue and self.blue.is_connected())
        ):
            while True:
                try:
                    data = self.gps.uart.read()
                    if data:
                        for line in data.splitlines(keepends=True):
                            await self.gps_data(line)
                except Exception as e:
                    print_exception(e)
                await asyncio.sleep_ms(0)

    async def gps_data(self, line):
        """Read GPS data and send to configured outputs.

        All exceptions are caught and logged to avoid crashing the main thread.

        NMEA sentences are sent to (if enabled): USB serial, Bluetooth, ESPNow and NTRIP server (only non-NMEA data).
        """
        if not line:
            return
        isNMEA = False
        # Handle NMEA sentences
        if line.startswith(b"$") and line.endswith(b"\r\n"):
            isNMEA = True
            if line.startswith(b"$GPGGA") or line.startswith(b"$GNGGA"):
                if self.ntrip_client:
                    self.ntrip_client.set_gga_sentence(line)
            if cfg.ENABLE_GPS and cfg.PQTMEPE_TO_GGST:
                if line.startswith(b"$GNRMC"):
                    # Extract UTC_TIME (as str) for use in GST sentence creation
                    self.gps.utc_time = line.split(b",",2)[1].decode("UTF-8")
                if line.startswith(b"$PQTMEPE"):
                    line = self.gps.pqtmepe_to_gst(line)
        try:
            if cfg.ENABLE_SERIAL_CLIENT:
                # Only send a line if the last transmit completed - avoid buffer overflow
                if self.serial.uart.txdone():
                    self.serial.uart.write(line)
                    self.serial.uart.flush()
        except Exception as e:
            log(f"[GPS DATA] USB serial send exception: {print_exception(e)}")
        try:
            if cfg.ENABLE_BLUETOOTH and self.blue.is_connected():
                self.blue.send(line)
        except Exception as e:
            log(f"[GPS DATA] BT send exception: {print_exception(e)}")

        try:
            if self.net.espnow_connected and cfg.ESPNOW_MODE == "sender":
                await self.net.espnow_sendall(line)
        except Exception as e:
            log(f"[GPS DATA] ESPNow send exception: {print_exception(e)}")

        try:
            # Don't sent NMEA sentences to NTRIP server
            if not isNMEA and self.ntrip_server:
                await self.ntrip_server.send_data(line)
        except Exception as e:
            log(f"[GPS DATA] NTRIP server send exception: {print_exception(e)}")
        # Settle
        await asyncio.sleep(0)



    def cb_GPS(self, opts):
        """Write a command to the GPS device."""
        if hasattr(self.gps, "uart"):
            # Prefix used to filter response messages
            prefix = getattr(cfg, "GPS_SETUP_RESPONSE_PREFIX", "")
            # Return the GPS response output
            return self.gps.write_nmea(opts, prefix)

    def cb_RESETGPS(self, opts):
        """Reset just the GPS device."""
        self.gps_reset()
        return("GPS device reset.")

    def cb_RESET(self, opts):
        """Hard reset the device."""
        self.hard_reset()

    async def run(self):
        """Start various long-running async processes.

        There are 2 conditions which affect which services to start:
        1. GPS data, sourced either from a GPS device, or ESPNOW receiver.
        2. Wifi connection.

        Data source is needed for:
        a. Bluetooth.
        b. Serial output
        c. NTRIP Server.

        Wifi is needed for:
        a. NTRIP services (caster, server, client)
        """

        # Start serial early, as logs may be redirected to it.
        if getattr(cfg, "ENABLE_SERIAL_CLIENT", None):
            self.setup_serial()
            if hasattr(self.serial, "uart"):
                log(f"Serial output enabled (UART{self.serial.id})")
            else:
                # Serial setup didn't create uart for some reason, so turn off serial logging
                cfg.ENABLE_SERIAL_CLIENT = False

        # Set up wifi
        self.setup_networks()

        # Expect to receive gps data (from device, or ESPNOW)
        if cfg.ENABLE_GPS:
            self.setup_gps()
            self.tasks.append(asyncio.create_task(self.gps_reader()))

        if cfg.ENABLE_BLUETOOTH:
            from blue import Blue
            log("Enabling Bluetooth")
            self.blue = Blue(name=cfg.DEVICE_NAME)
            # Set custom BLE write callback
            self.blue.write_callback = self.esp32_write_data

        # NTRIP needs a network connection
        if self.net.wifi_connected:
            if cfg.NTRIP_MODE:
                import ntrip
            if cfg.ENABLE_GPS and "client" in cfg.NTRIP_MODE:
                log("starting ntrip client")
                self.ntrip_client = ntrip.Client(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
                self.tasks.append(asyncio.create_task(self.ntrip_client.run()))
                self.tasks.append(asyncio.create_task(self.ntrip_client_read()))

        # Wait for shutdown_event signal
        await self.shutdown_event.wait()

    async def shutdown(self):
        """Clean up background processes, handlers etc on exit."""
        # Stop bluetooth irq handling
        if hasattr(self.blue, "ble"):
            self.blue.ble.irq(None)


        # Clean up self
        for task in self.tasks:
            try:
                task.cancel()
            except:
                pass

        # Wait for tasks to exit
        await asyncio.gather(*self.tasks, return_exceptions=True)

if __name__ == "__main__":
    e32gps = ESP32GPS()
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(e32gps.run())

        # The background tasks in e32gps should run forever (or raise exceptions).
        # We only reach here if the event loop exits cleanly - i.e no background tasks.
        log("Exited - nothing to do.")
        log("Enable at least one long-running process in your configuration: (GPS, ESPNow Receiver, NTRIP)")

        # Clean up hanging IRQ etc
        loop.run_until_complete(e32gps.shutdown())

    except (KeyboardInterrupt, Exception) as e:
        e32gps.shutdown_event.set()
        loop.run_until_complete(e32gps.shutdown())
        if isinstance(e, KeyboardInterrupt):
            log("Ctrl-C received - shutting down.")
        else:
            log("Unhandled exception - shutting down.")
            print_exception(e)
            if getattr(cfg, "CRASH_RESET", None):
                log("Hard resetting due to crash...")
                # Delay (to prevent restart tight loop, and give time to read the exception)
                sleep_ms(5000)
                reset()
