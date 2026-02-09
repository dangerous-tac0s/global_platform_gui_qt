#!/usr/bin/env python3
import time

from smartcard.Exceptions import CardConnectionException, NoCardException
from smartcard.System import readers


def get_memory(reader=0, retry=0):
    """
    Returns a dict of the memory values
    :return:
    """
    all_readers = readers()
    # Filter out SAM readers - we only want PICC (contactless card) readers
    reader_list = [r for r in all_readers if "SAM" not in str(r).upper()]
    if len(reader_list) > 0:
        connection = None
        try:
            connection = reader_list[reader].createConnection()
            connection.connect()
            # Select the applet
            # info: Sending applet selection
            data, sw1, sw2 = connection.transmit(
                [
                    0x00,
                    0xA4,
                    0x04,
                    0x00,
                    0x0C,
                    0xA0,
                    0x00,
                    0x00,
                    0x08,
                    0x46,
                    0x6D,
                    0x65,
                    0x6D,
                    0x6F,
                    0x72,
                    0x79,
                    0x01,
                ]
            )
        except (CardConnectionException, NoCardException) as e:
            if connection:
                try:
                    connection.disconnect()
                except Exception:
                    pass
            if retry > 10:
                print(e)
                return None

            time.sleep(0.1)
            return get_memory(reader, retry=retry + 1)

        connection.disconnect()
        if sw1 == 0x90 and sw2 == 0x00:
            # success: Applet selected, card response is ok
            # Parse response
            memory_persistent = int.from_bytes(data[0:4], "big")
            memory_persistent_total = int.from_bytes(data[4:8], "big")
            memory_persistent_percentage = min(
                ## 99% at most because we'll at least have free memory installed
                0.99,
                memory_persistent / memory_persistent_total,
            )
            memory_transient_reset = int.from_bytes(data[8:10], "big")
            memory_transient_deselect = int.from_bytes(data[10:12], "big")
            memory_transient_free = min(
                1.0,
                (((memory_transient_reset + memory_transient_deselect) / 2.0) / 4096.0),
            )

            return {
                # Storage
                "persistent": {
                    "free": memory_persistent,
                    "total": memory_persistent_total,
                    "used": memory_persistent_total - memory_persistent,
                    "percent_free": memory_persistent_percentage,
                },
                # "RAM"
                "transient": {
                    "reset_free": memory_transient_reset,
                    "deselect_free": memory_transient_deselect,
                    "percent_free": memory_transient_free,
                },
            }
        else:
            sw1 = f"{sw1:02x}"
            sw2 = f"{sw2:02x}"

            if sw1 == "6a" and sw2 == "82":
                # App not installed
                return -1
