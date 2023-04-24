# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

import esp32
import json
import machine
from machine import Pin, ADC
from sx1262 import SX1262
from jram import JRAM as nvr

import time

MAX_STUCK_BOOT_COUNT = 5
DOOR_OPEN = 1
DOOR_CLOSED = 0

wake_pin = Pin(6, Pin.IN, pull=Pin.PULL_UP)
battery_pin = ADC(Pin(1))
led_pin = Pin(35, Pin.OUT)
esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ANY_HIGH)
start_time = 0
current_millis = time.ticks_ms()
door_state = 0

retained = nvr().get()
if not retained:
    retained = {'source': 'mailbox', 'battery_level': 0, 'boot_count': 0, 'stuck_boot_count': 0, 'last_door_state': DOOR_CLOSED,
                'time_awake_millis': 0}
    nvr().put(retained)


def save_and_sleep(sleep_until_close):
    retained['time_awake_millis'] = retained['time_awake_millis'] + time.ticks_ms() - current_millis
    last_door_state = retained['last_door_state']
    retained['last_door_state'] = wake_pin.value()
    nvr().put(retained)
    print("Door state: {}, Last door state: {}\nGoing to sleep...".format(retained['last_door_state'], last_door_state))
    if sleep_until_close:
        esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ALL_LOW)
        print("Deep sleep waiting for close")
    machine.deepsleep()


door_state = wake_pin.value()
retained['boot_count'] = retained['boot_count'] + 1

print("Retained state {}, door_state {}".format(retained['last_door_state'], door_state))

changed_state = retained['last_door_state'] != door_state

if changed_state:
    if door_state == DOOR_OPEN:
        print("Door just opened")
        led_pin.on()
        sx = SX1262(spi_bus=1, clk=9, mosi=10, miso=11, cs=8, irq=14, rst=12, gpio=13)

        # LoRa
        sx.begin(freq=923, bw=500.0, sf=12, cr=8, syncWord=0x12,
                 power=-5, currentLimit=60.0, preambleLength=8,
                 implicit=False, implicitLen=0xFF,
                 crcOn=True, txIq=False, rxIq=False,
                 tcxoVoltage=1.7, useRegulatorLDO=False, blocking=True)

        retained['source'] = 'mailbox'
        retained['RSSI'] = sx.getRSSI()
        retained['battery_level'] = round(battery_pin.read_u16() / 65535 * 6.6, 1)
        sx.send(json.dumps(retained).encode('utf-8'))
        led_pin.off()
    else:
        print("Door just closed")

if door_state == DOOR_OPEN:
    retained['stuck_boot_count'] = retained['stuck_boot_count'] + 1
    if retained['stuck_boot_count'] > MAX_STUCK_BOOT_COUNT:
        print("Door stuck open too long...sleeping until closed")
        retained['stuck_boot_count'] = 0
        save_and_sleep(True)
    else:
        print("Door stuck open...sleeping")
        time.sleep(5)
        save_and_sleep(False)

save_and_sleep(False)