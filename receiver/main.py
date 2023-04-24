# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

import json
from machine import Pin, SoftI2C
from sx1262 import SX1262
import uasyncio as asyncio

import time
import ssd1306
from mqtt_as import MQTTClient
import mqtt_local

BASE_TOPIC = 'esp32/lora'
CONFIG_TOPIC = f'{BASE_TOPIC}/config'
RELAY_TOPIC = f'{BASE_TOPIC}/relay'
AVAILABLE_TOPIC = f'{BASE_TOPIC}/availability'

oled_reset_pin = 21
oled_scl = 18
oled_sda = 17

# Heltec LoRa 32 with OLED Display
oled_width = 128
oled_height = 64
# OLED reset pin
i2c_rst = Pin(21, Pin.OUT)
# Initialize the OLED display
i2c_rst.value(0)
time.sleep(0.010)
i2c_rst.value(1)  # must be held high after initialization
# Setup the I2C lines
i2c_scl = Pin(18, Pin.OUT, Pin.PULL_UP)
i2c_sda = Pin(17, Pin.OUT, Pin.PULL_UP)
# Create the bus object
i2c = SoftI2C(scl=i2c_scl, sda=i2c_sda)
devices = i2c.scan()
print(devices)
for device in devices:
    print("List of Devices: ", device)

# Create the display object
oled = ssd1306.SSD1306_I2C(oled_width, oled_height, i2c)

# define BATTERY_PIN 1 // A battery voltage measurement pin, voltage divider connected here to measure battery voltage

sx = SX1262(spi_bus=1, clk=9, mosi=10, miso=11, cs=8, irq=14, rst=12, gpio=13)

# LoRa
sx.begin(freq=923, bw=500.0, sf=12, cr=8, syncWord=0x12,
         power=-5, currentLimit=60.0, preambleLength=8,
         implicit=False, implicitLen=0xFF,
         crcOn=True, txIq=False, rxIq=False,
         tcxoVoltage=1.7, useRegulatorLDO=False, blocking=True)

client = None
messages = []
error_str = ''


def handle_incoming_message(topic, msg, retained):
    print(f'{topic}: {msg}')
    msg_string = str(msg, 'UTF-8')
    if topic == CONFIG_TOPIC:
        pass


async def wifi_han(state):
    print('Wifi is ', 'up' if state else 'down')
    await asyncio.sleep(1)


# If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
async def conn_han(client):
    await client.subscribe(CONFIG_TOPIC, 0)
    await online()


async def online():
    await client.publish(AVAILABLE_TOPIC, 'online', retain=True, qos=0)


def cb(events):
    if events & SX1262.RX_DONE:
        global error_str
        msg, err = sx.recv()
        error = SX1262.STATUS[err]
        print(msg)
        if error == 'ERR_NONE':
            err_str = ''
            messages.insert(0, msg.decode('utf-8'))
        else:
            err_str = error
        print(err_str)


async def main():
    await client.connect()
    await asyncio.sleep(2)  # Give broker time
    await online()
    while True:
        oled.fill(0)
        try:
            message = messages.pop()
            message_dict = json.loads(message)
            sub_topic = 'default'
            if 'source' in message_dict:
                sub_topic = message_dict.pop('source')
            await client.publish('{}/{}'.format(RELAY_TOPIC, sub_topic), json.dumps(message_dict))
            oled.text('From: {}'.format(sub_topic), 0, 0)
            oled.text('Error: {}'.format(error_str), 0, 10)
            oled.text('Batt: {}V'.format(message_dict['battery_level']), 0, 20)
            oled.text('RSSI: {}'.format(message_dict['RSSI']), 0, 30)
            oled.show()
        except IndexError:
            await asyncio.sleep(1)


sx.setBlockingCallback(False, cb)

mqtt_local.config['subs_cb'] = handle_incoming_message
mqtt_local.config['connect_coro'] = conn_han
mqtt_local.config['wifi_coro'] = wifi_han
mqtt_local.config['will'] = [AVAILABLE_TOPIC, 'offline', True, 0]

MQTTClient.DEBUG = False
client = MQTTClient(mqtt_local.config)

try:
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
finally:
    client.close()
    asyncio.stop()
