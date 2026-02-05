"""Provide simple NTRIP Client, Server and Caster functionality."""

import asyncio
import gc
gc.enable()
from sys import print_exception
from devices import Logger
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

# Seconds to wait before reconnecting to caster after failure
RECONNECT_TIMEOUT = 10

log = Logger.getLogger().log

try:
    from ubinascii import b2a_base64 as b64encode
except ModuleNotFoundError:
    from base64 import b64encode

# Exception to raise for Caster authentication errors
class AuthError(Exception):
    pass


example_data = bytes([
    0xD3, 0x00, 0x40, 0x41, 0x2E, 0x06, 0x44, 0x19, 0x1E, 0xF5, 0x00,
    0xA4, 0x00, 0x00, 0x10, 0xB6, 0x11, 0x08, 0xC2, 0xE8, 0x1D, 0x58,
    0x1A, 0x72, 0xC8, 0x46, 0xCD, 0x1A, 0x08, 0xEA, 0x81, 0x2C, 0x3E,
    0xDC, 0x1B, 0xBB, 0xD9, 0x5D, 0x90, 0x61, 0xE8, 0x05, 0x2F, 0xFB,
    0x89, 0x9A, 0x4D, 0xCC, 0xEB, 0xFE, 0x4C, 0x25, 0x28, 0xFB, 0x6C,
    0xDA, 0x7F, 0x61, 0x8E, 0x60, 0x9C, 0xBF, 0xFB, 0x6A, 0x2D, 0x30,
    0x02, 0x19, 0x8F, 0x73
])

def calc_crc24q(message: bytes) -> int:
    """
    Perform CRC24Q cyclic redundancy check.

    If the message includes the appended CRC bytes, the
    function will return 0 if the message is valid.
    If the message excludes the appended CRC bytes, the
    function will return the applicable CRC.

    :param bytes message: message
    :return: CRC or 0
    :rtype: int

    """

    poly = 0x1864CFB
    crc = 0
    for octet in message:
        crc ^= octet << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= poly
    return crc & 0xFFFFFF



class Base():

    def __init__(self, host="", port=2101, mount="ESP32", credentials="c:c"):
        self.name = None
        self.host = host
        self.port = port
        self.mount = mount
        self.credb64 =  b64encode(credentials.encode('ascii')).decode().strip()
        self.useragent = "NTRIP ESP32_GPS Client/1.0"
        self.request_headers = None
        self.reader = None
        self.writer = None

    def build_headers(self, method, mount=None):
        mount = mount or self.mount
        return (
            f"{method} /{mount} HTTP/1.1\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            f"User-Agent: {self.useragent}\r\n"
            f"Authorization: Basic {self.credb64}\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        ).encode()

    async def caster_connect(self):
        while True:
            try:
                log(f"[{self.name}] Connecting to {self.host}:{self.port}...")
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    10
                )
                self.writer.write(self.request_headers)
                await self.writer.drain()
                headers = await self.reader.read(1024)
                headers = headers.split(b"\r\n")
                for line in headers:
                    if line.endswith(b"200 OK"):
                        break
                else:
                    # Not valid login
                    raise ValueError(headers)
                break
            except (OSError, ValueError, asyncio.TimeoutError) as err:
                log(f"[{self.name}] Connection error: {err}")
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except (AttributeError, OSError):
                    pass
                # Wait before trying to reconnect
                await asyncio.sleep(RECONNECT_TIMEOUT)


class Client(Base):

    def __init__(self, *args, **kwargs):
        """Defaults to centipede NTRIP service"""
        super().__init__(*args, **kwargs)
        self.name = "Client"
        self.request_headers = self.build_headers(method="GET")
        self.last_gga = None
        self.last_gga_send_time = 0
        self.gga_send_interval = 5  # Send GGA every 5 seconds


        loop = asyncio.get_event_loop()
        self.monitor = loop.create_task(self.send_gga())



    def set_gga_sentence(self, gga_sentence):
        """Store a GGA sentence to be sent to the caster.
        
        Args:
            gga_sentence: NMEA GGA sentence as bytes or string
        """
        #if isinstance(gga_sentence, str):
        #    gga_sentence = gga_sentence.encode('ascii')
        self.last_gga = gga_sentence

    async def send_gga(self):
        while True:
            try:
                log("gga loop")
                log("last gga %s" % self.last_gga)
                if self.writer and self.last_gga:
                    try:
                        log("gga %s" % self.last_gga)
                        self.writer.write(self.last_gga)
                        await self.writer.drain()
                        log("free mem %s" % gc.mem_free())
                        log(f"[{self.name}] Sent GGA to caster: {self.last_gga}")
                    except OSError as err:
                        log(f"[{self.name}] Error sending GGA to caster: {err}")
                        raise
                    except TypeError as err:
                        log(f"[{self.name}] Error with typing: {err}")
                await asyncio.sleep(5)
            except (EOFError, OSError) as e:
                # wait for connection to be re-established
                await asyncio.sleep(5)
    # TODO: catch OSError: [Errno 9] EBADF and retry



    async def iter_data(self):
        """Read data from caster and yield as requested."""
        while True:
            if self.reader:
                try:

                    # nach zeilen splitten und dann entscheiden ob rtcm oder http?
                    # todo: seek for first bytes...
                    # Regular small reads to avoid blocking (RTCM messages are typically < 512 bytes, max 1023)
                    # maybe detect \r\n as delimeter and then log all non rtcm as possible http errors?

                    first_byte = None
                    second_byte = None


                    while True:
                        log("iter loop")




                        if first_byte and first_byte[0] == 0xd3:
                            log("First byte is 0xd3")
                            second_byte = await self.reader.readexactly(1)
                            if second_byte[0] == 0x00:
                                log("Second byte is 0x00")
                                hdr3 = await self.reader.readexactly(1)
                                size = (second_byte[0] << 8) | hdr3[0]
                                payload = await self.reader.readexactly(size)
                                crc = await self.reader.readexactly(3)
                                raw_data = first_byte + second_byte + hdr3 + payload + crc
                                print(raw_data)
                                res = calc_crc24q(raw_data)
                                if res == 0:
                                    return raw_data
                                else:
                                    # invalid packet
                                    continue
                            else:
                                first_byte = second_byte
                                continue
                        else:
                            first_byte = await self.reader.readexactly(1)
                            log("first byte %s" % str(first_byte))





                    #if first_byte[0] == 0xd3:
                        #    second_byte = await self.reader.readexactly(1)

                        #    else:
                    """
                    # check for empty_bytes = b''?
                    hdr = await self.reader.readexactly(2)
                    
                    
                    if hdr[0] == 0xd3:
                        log("RTCM Message")
                    else:
                        log("not RTCM")
                    # RTCM3 (byte1 = 0xd3; byte2 = 0b000000**)
                    hdr3 = await self.reader.readexactly(1)
                    size = (hdr[1] << 8) | hdr3[0]
                    payload = await self.reader.readexactly(size)
                    crc = await self.reader.readexactly(3)
                    raw_data = hdr + hdr3 + payload + crc
                    #print(raw_data)
                    res = calc_crc24q(raw_data)
                    if res == 0:
                        return raw_data

                    #data = await self.reader.read(128)
                    #if data:
                        #print("got data")
                    #    return data
                    else:
                        # Stream closed
                        raise OSError
                    """

                except (EOFError, OSError) as e:
                    if DEBUG:
                        print_exception(e)
                    log(f"[{self.name}] Caster read error. Closing connection...")
                    try:
                        self.reader.close()
                        await self.reader.wait_closed()
                    except OSError as e:
                        if DEBUG:
                            print_exception(e)
                        pass
                    finally:
                        self.reader = None

            else:
                # Reader not ready yet...
                await asyncio.sleep(1)

    async def run(self):
        while True:
            await self.caster_connect()

            log("connrcted")
            while self.reader and self.writer:
                log("loop")
                #if self.last_gga:
                #    log( self.last_gga)
                # Long sleep while connection established (equivalent to reconnect timeout)
                await asyncio.sleep(RECONNECT_TIMEOUT)

