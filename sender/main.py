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

BATTERY_ADJUSTMENT = 3.3 / 65535 * 4.9

wake_pin = Pin(6, Pin.IN, pull=Pin.PULL_UP)
adc_ctl = Pin(37, Pin.OUT)
battery_pin = ADC(Pin(1))
battery_pin.atten(ADC.ATTN_11DB)
led_pin = Pin(35, Pin.OUT)
esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ANY_HIGH)
start_time = 0
current_millis = time.ticks_ms()
door_state = 0

retained = nvr().get()
if not retained:
    retained = {'source': 'mailbox', 'battery_level': 0, 'boot_count': 0, 'stuck_boot_count': 0,
                'last_door_state': DOOR_CLOSED,
                'time_awake_millis': 0}
    nvr().put(retained)


def read_battery():
    adc_ctl.off()
    reading = battery_pin.read_u16()
    adc_ctl.on()
    return round(reading * BATTERY_ADJUSTMENT, 3)


def save_and_sleep(sleep_until_close):
    retained['time_awake_millis'] = retained['time_awake_millis'] + time.ticks_ms() - current_millis
    last_door_state = retained['last_door_state']
    retained['last_door_state'] = wake_pin.value()
    nvr().put(retained)
    print("Door state: {}, Last door state: {}\nGoing to sleep...".format(retained['last_door_state'], last_door_state))
    if sleep_until_close:
        esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ALL_LOW)
        print("Deep sleep waiting for close")
    else:
        print("Door open, sleeping in the hope it will close")
    machine.deepsleep()


door_state = wake_pin.value()
retained['boot_count'] = retained['boot_count'] + 1

print("Retained state {}, door_state {}".format(retained['last_door_state'], door_state))

changed_state = retained['last_door_state'] != door_state


def pack_message(message_dict):
    """Take json data and convert to a simple compact string format"""
    # S - source, M - message, R - RSSI, N - SNR, B - battery V, C - boot count
    # SmbMopenR-20N5B3.9C20
    packed = 'S{}M{}R{}N{}B{}C{}'.format(message_dict['source'], message_dict['message'], message_dict['RSSI'],
                                         message_dict['SNR'], message_dict['battery_level'], message_dict['boot_count'])
    return packed


def send_message(message):
    led_pin.on()
    sx = SX1262(spi_bus=1, clk=9, mosi=10, miso=11, cs=8, irq=14, rst=12, gpio=13)
    # LoRa
    sx.begin(freq=923, bw=500.0, sf=12, cr=8, syncWord=0x12,
             power=-5, currentLimit=60.0, preambleLength=8,
             implicit=False, implicitLen=0xFF,
             crcOn=True, txIq=False, rxIq=False,
             tcxoVoltage=1.7, useRegulatorLDO=False, blocking=True)
    retained['source'] = 'mb'
    retained['message'] = message
    retained['RSSI'] = sx.getRSSI()
    retained['SNR'] = sx.getSNR()
    retained['battery_level'] = read_battery()

    sx.send(pack_message(retained).encode('utf-8'))
    led_pin.off()


if changed_state:
    if door_state == DOOR_OPEN:
        print("Door just opened")
        send_message("open")
    else:
        print("Door just closed")

if door_state == DOOR_OPEN:
    retained['stuck_boot_count'] = retained['stuck_boot_count'] + 1
    if retained['stuck_boot_count'] > MAX_STUCK_BOOT_COUNT:
        print("Door stuck open too long...sleeping until closed")
        retained['stuck_boot_count'] = 0
        save_and_sleep(True)
    else:
        print("Door stuck open...sleeping, check again in 5 secs")
        time.sleep(5)
        save_and_sleep(False)

save_and_sleep(False)
