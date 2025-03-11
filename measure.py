#!/usr/bin/env python3
from smartcard.System import readers


def get_memory(reader=0):
    """
    Returns a dict of the memory values
    :return:
    """

    reader_list = readers()
    if len(reader_list) > 0:
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
        if sw1 == 0x90 and sw2 == 0x00:
            # success: Applet selected, card response is ok
            # Parse response
            memory_persistent = int.from_bytes(data[0:4], "big")
            memory_persistent_total = int.from_bytes(data[4:8], "big")
            memory_persistent_percentage = memory_persistent / memory_persistent_total
            memory_transient_reset = int.from_bytes(data[8:10], "big")
            memory_transient_deselect = int.from_bytes(data[10:12], "big")
            memory_transient_free = min(
                1.0,
                (((memory_transient_reset + memory_transient_deselect) / 2.0) / 4096.0),
            )

            connection.disconnect()

            return {
                "persistent": {
                    "free": memory_persistent,
                    "total": memory_persistent_total,
                    "used": memory_persistent_total - memory_persistent,
                    "percent_free": memory_persistent_percentage,
                },
                "transient": {
                    "reset": memory_transient_reset,
                    "deselect": memory_transient_deselect,
                    "percent_free": memory_transient_free,
                },
            }
        else:
            print("error: Card response: " + f"{sw1:02x}" + " " + f"{sw2:02x}")
        connection.disconnect()
