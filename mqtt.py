#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import logging
from time import time
from json import dumps as dump_json
from base64 import b64encode
from collections import OrderedDict
from volvooncall import Connection
from os.path import join, expanduser
from os import environ as env
from requests import certs
from threading import current_thread
from time import sleep
from types import SimpleNamespace as ns
from math import floor
from sys import stderr
import paho.mqtt.client as paho


_LOGGER = logging.getLogger(__name__)


def read_mqtt_config():
    """Read credentials from ~/.config/mosquitto_pub."""
    with open(join(env.get('XDG_CONFIG_HOME',
                           join(expanduser('~'), '.config')),
                   'mosquitto_pub')) as f:
        d = dict(line.replace('-', '').split() for line in f.read().splitlines())
        return dict(host=d['h'],
                    port=d['p'],
                    username=d['username'],
                    password=d['pw'])


def on_connect(client, userdata, flags, rc):
    current_thread().setName('MQTTThread')
    _LOGGER.info('Connected')

def on_publish(client, userdata, mid):
    _LOGGER.info('Published')

def on_disconnect(client, userdata, rc):
    _LOGGER.warning('Disconnected')

def on_message(client, userdata, message):
    _LOGGER.info('Got %s', message)
    # FIXME: Command topic does not make sense for all devices
    entity = Entity.subscriptions.get(message.topic)
    if entity:
        entity.command(message.payload)
    else:
        _LOGGER.warning(f'Unknown recipient for {message.topic}')

class Entity:

    subscriptions = {}

    def __init__(self, component, attr, name):
        self.attr = attr
        self.component = component
        self.name = name
        self.vehicle = None
        self.config = None

    def setup(self, vehicle, config):
        self.vehicle = vehicle
        self.config = config
        return self.supported
        
    def __str__(self):
        return f'{self.entity_name}'
        
    @property
    def vehicle_name(self):
        return self.vehicle.registration_number or self.vehicle.vin

    @property
    def entity_name(self):
        return f'{self.vehicle_name} {self.name}'
    
    @property
    def supported(self):
        return getattr(self.vehicle, self.attr + '_supported', True)

    @property
    def topic(self):
        discovery_prefix = 'homeassistant'
        node = f'volvo_{self.vehicle.unique_id}'
        return f'{discovery_prefix}/{self.component}/{node}/{self.attr}'

    @property
    def discovery_payload(self):
        return dict(name=self.entity_name,
                    state_topic=self.state_topic,
                    availability_topic=self.availability_topic,
                    command_topic=self.command_topic)

    def publish(self, mqtt, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        mqtt.publish(topic, payload, retain=True)

    @property
    def state(self):
        return getattr(self.vehicle, self.attr)

    @property
    def state_topic(self):
        return f'{self.topic}/state'

    @property
    def discovery_topic(self):
        return f'{self.topic}/config'

    @property
    def availability_topic(self):
        return f'{self.topic}/avail'

    @property
    def command_topic(self):
        return f'{self.topic}/cmd'

    def subscribe(self, mqtt):
        mqtt.subscribe(self.command_topic)
        Entity.subscriptions[self.command_topic] = self

    def command(self, command):
        _LOGGER.warning(f'No command to execute for {self}: {command}')

    def publish_discovery(self, mqtt):
        self.subscribe(mqtt)
        self.publish(mqtt, self.discovery_topic, self.discovery_payload)

    def publish_availability(self, mqtt, available):
        self.publish(mqtt, self.availability_topic,
                     'online' if available and self.state else 'offline')

    def publish_state(self, mqtt):
        if self.state:
            _LOGGER.debug(f'State for {self.attr}: {self.state}')
            self.publish(mqtt, self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')

        
class Sensor(Entity):
    def __init__(self, attr, name, icon, unit):
        super().__init__('sensor', attr, name)
        self.icon = icon
        self.unit = unit

    def setup(self, vehicle, config):
        self.unit = (
            self.unit if 'scandinavian_miles' not in config
            else 'L/mil' if self.attr == 'average_fuel_consumption'
            else self.unit.replace('km', 'mil'))
        return super().setup(vehicle, config)
        
    @property
    def discovery_payload(self):
        return dict(super().discovery_payload, icon=self.icon, unit_of_measurement=self.unit)

    @property
    def state(self):
        val = super().state
        return (val / 10
                if val and 'mil' in self.unit
                else val)
        
class FuelConsumption(Sensor):

    def __init__(self):
        super().__init__('average_fuel_consumption', 'Fuel consumption', 'mdi:gas-station', 'L/100 km')

    def setup(self, vehicle, config):
        self.unit = self.unit.replace('100 km', 'mil') if 'scandinavian_miles' in config else self.unit
        return super().setup(vehicle, config)

    @property
    def state(self):
        val = super().state
        return (round(val / 10, 2 if 'mil' in self.unit else 1) # L/1000km -> L/100km
                if val
                else None)
                
class Odometer(Sensor):

    def __init__(self):
        super().__init__('odometer', 'Odometer', 'mdi:speedometer', 'km')
                     
    @property
    def state(self):
        val = super().state
        return (int(round(val / 1000))  # m->km
                if val
                else None) 
    
class BinarySensor(Entity):
    def __init__(self, attr, name, device_class):
        super().__init__('binary_sensor', attr, name)
        self.device_class = device_class

    @property
    def discovery_payload(self):
        return dict(super().discovery_payload, device_class=self.device_class)

    @property
    def state(self):
        val = super().state
        if self.attr == 'bulb_failures':
            return 'ON' if val else 'OFF'
        else:
            return 'ON' if val != 'Normal' else 'OFF'

class AnyOpen(BinarySensor):
    def __init__(self, attr, name, device_class):
        super().__init__(attr, name, device_class)
    @property
    def state(self):
        state = super().state
        return 'ON' if any([state[key] for key in state if 'Open' in key]) else 'OFF'

class Doors(AnyOpen):
    def __init__(self):
        super().__init__('doors', 'Doors', 'door')

class Windows(AnyOpen):
    def __init__(self):
        super().__init__('windows', 'Windows', 'window')
        
class Lock(Entity):
    def __init__(self):
        super().__init__('lock', 'lock', 'Door lock')

    @property
    def state(self):
        return 'LOCK' if self.vehicle.is_locked else 'UNLOCK'
        
    @property
    def discovery_payload(self):
        return dict(super().discovery_payload,
                    command_topic=f'{self.topic}/set')

    def command(self, command):
        if command == 'lock':
            self.vehichle.lock()
        elif command == 'unlock':
            self.vehichle.unlock()
        else:
            _LOGGER.warning(f'Unknown command: {command}')


class Switch(Entity):
    def __init__(self, attr, name, icon=None):
        super().__init__('switch', attr, name)
        self.icon = icon

    @property
    def discovery_payload(self):
        return dict(super().discovery_payload,
                    command_topic=f'{self.topic}/set',
                    icon=self.icon)
    
class Heater(Switch):
    def __init__(self):
        super().__init__('heater', 'Heater', 'mdi:radiator')

    @property
    def state(self):
        return 'ON' if self.vehicle.is_heater_on else 'OFF'

    def command(self, command):
        if command == 'on':
            self.vehichle.start_heater()
        elif command == 'off':
            self.vehichle.stop_heater()
        else:
            _LOGGER.warning(f'Unknown command: {command}')


class Position(Entity):
    def __init__(self):
        super().__init__(None, None, None)

    @property
    def supported(self):
        return True

    def publish_discovery(self, mqtt):
        pass
    
    def publish_availability(self, mqtt, available):
        pass

    @property
    def state_topic(self):
        return f'owntracks/volvo/{self.vehicle.unique_id}'

    @property
    def state(self):
        key = self.config.get('owntracks_key')
        res = dict(_type='location',
                   tid='volvo',
                   t='p',
                   lat=self.vehicle.position['latitude'],
                   lon=self.vehicle.position['longitude'],
                   acc=1,
                   tst=int(time()))
        return dict(_type='encrypted',
                    data=owntracks_encrypt(dump_json(res), key)) if key else res


entities = [
    Position(),
    Lock(),
    Heater(),
    Odometer(),
    Sensor('fuel_amount', 'Fuel amount', 'mdi:gas-station', 'L'),
    Sensor('fuel_amount_level', 'Fuel level', 'mdi:water-percent', '%'),
    FuelConsumption(),
    Sensor('distance_to_empty', 'Range', 'mdi:ruler', 'km'),
    BinarySensor('washer_fluid_level', 'Washer fluid', 'safety'),
    BinarySensor('brake_fluid', 'Brake Fluid', 'safety'),
    BinarySensor('service_warning_status', 'Service', 'safety'),
    BinarySensor('bulb_failures', 'Bulbs', 'safety'),
    Doors(),
    Windows()
]

def push_state(vehicle, mqtt, config, available):
    for entity in entities:
        if not entity.setup(vehicle, config):
            continue
        entity.publish_discovery(mqtt)
        entity.publish_availability(mqtt, available)
        if available:
            entity.publish_state(mqtt)

            
def run(voc, config):

    # FIXME: Allow MQTT credentials in voc.conf

    mqtt_config = read_mqtt_config()
    mqtt = paho.Client()
    mqtt.username_pw_set(username=mqtt_config['username'],
                         password=mqtt_config['password'])
    mqtt.tls_set(certs.where())

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message
    
    mqtt.connect(host=mqtt_config['host'],
                 port=int(mqtt_config['port']))
    mqtt.loop_start()

    interval = int(config['interval'])
    _LOGGER.info(f'Polling every {interval} seconds')

    while True:
        available = voc.update()
        for vehicle in voc.vehicles:
            push_state(vehicle, mqtt, config, available)
        sleep(interval)


if __name__ == '__main__':
   main()
