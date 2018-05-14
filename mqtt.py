#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import logging
from time import time
from json import dumps as dump_json
from os.path import join, expanduser
from os import environ as env
from requests import certs
from threading import current_thread
from time import sleep
from threading import RLock
import paho.mqtt.client as paho
from paho.mqtt.client import MQTT_ERR_SUCCESS
from volvooncall import owntracks_encrypt
from platform import node as hostname
from os import getpid

_LOGGER = logging.getLogger(__name__)

CLEAN_SESSION = False

STATE_ON = 'on'
STATE_OFF = 'off'
STATE_ONLINE = 'online'
STATE_OFFLINE = 'offline'
STATE_LOCK = 'lock'
STATE_UNLOCK = 'unlock'

DISCOVERY_PREFIX = 'homeassistant'
TOPIC_PREFIX = 'volvo'


def threadsafe(function):
    """ Synchronization decorator.
    The paho MQTT library runs the on_subscribe etc callbacks
    in its own thread and since we keep track of subscriptions etc
    in Device.subscriptions, we need to synchronize threads."""
    def wrapper(*args, **kw):
        with Entity.lock:
            return function(*args, **kw)
    return wrapper


def read_mqtt_config():
    """Read credentials from ~/.config/mosquitto_pub."""
    with open(join(env.get('XDG_CONFIG_HOME',
                           join(expanduser('~'), '.config')),
                   'mosquitto_pub')) as f:
        d = dict(line.replace('-', '').split()
                 for line in f.read().splitlines())
        return dict(host=d['h'],
                    port=d['p'],
                    username=d['username'],
                    password=d['pw'])


@threadsafe
def on_connect(client, userdata, flags, rc):
    current_thread().setName('MQTTThread')
    _LOGGER.info('Connected')
    for topic, entity in Entity.subscriptions.items():
        entity.subscribe_to(topic, resubscribe=True)


@threadsafe
def on_publish(client, userdata, mid):
    _LOGGER.debug('Successfully published on %s: %s',
                  *Entity.pending.pop(mid))


@threadsafe
def on_disconnect(client, userdata, rc):
    if rc == MQTT_ERR_SUCCESS:
        # we called disconnect ourselves
        _LOGGER.info('Disconnect successful')
    else:
        _LOGGER.warning('Disconnected, automatically reconnecting')


@threadsafe
def on_subscribe(client, userdata, mid, qos):
    topic, entity = Entity.pending.pop(mid)
    _LOGGER.debug('Successfully subscribed to %s',
                  topic)
    Entity.subscriptions[topic] = entity


@threadsafe
def on_message(client, userdata, message):
    _LOGGER.info('Got %s', message)
    entity = Entity.subscriptions.get(message.topic)
    if entity:
        entity.command(message.payload)
    else:
        _LOGGER.warning(f'Unknown recipient for {message.topic}')


class Entity:

    subscriptions = {}
    pending = {}
    lock = RLock()

    def __init__(self, component, attr, name):
        self.attr = attr
        self.component = component
        self.name = name
        self.vehicle = None
        self.mqtt = None

    def configurate(self, config):
        pass

    def setup(self, mqtt, vehicle):
        self.mqtt = mqtt
        self.vehicle = vehicle
        return self.is_supported

    def __str__(self):
        return f'{self.entity_name}'

    @property
    def vehicle_name(self):
        return self.vehicle.registration_number or self.vehicle.vin

    @property
    def entity_name(self):
        return f'{self.vehicle_name} {self.name}'

    @property
    def is_supported(self):
        #  Default to supported if foo_supported is not present
        return getattr(self.vehicle, self.attr + '_supported', True)

    @property
    def node_id(self):
        return f'{TOPIC_PREFIX}_{self.vehicle.unique_id}'

    @property
    def discovery_topic(self):
        return (f'{DISCOVERY_PREFIX}/{self.component}/'
                f'{self.node_id}/{self.attr}/config')

    @property
    def topic(self):
        return (f'{TOPIC_PREFIX}/{self.vehicle.unique_id}/'
                f'{self.attr}')

    @property
    def state_topic(self):
        return f'{self.topic}/state'

    @property
    def availability_topic(self):
        return f'{self.topic}/avail'

    @property
    def command_topic(self):
        return f'{self.topic}/cmd'

    @property
    def discovery_payload(self):
        return dict(name=self.entity_name,
                    state_topic=self.state_topic,
                    availability_topic=self.availability_topic,
                    payload_available=STATE_ONLINE,
                    payload_not_available=STATE_OFFLINE,
                    command_topic=self.command_topic)

    @threadsafe
    def publish(self, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        res, mid = self.mqtt.publish(topic, payload, retain=retain)
        if res == MQTT_ERR_SUCCESS:
            Entity.pending[mid] = (topic, payload)
        else:
            _LOGGER.warning('Failure to publish on %s', topic)

    @property
    def state(self):
        return getattr(self.vehicle, self.attr)

    @threadsafe
    def subscribe_to(self, topic, resubscribe=False):
        _LOGGER.debug('Subscribing to %s', topic)
        if not resubscribe and topic in Entity.subscriptions:
            _LOGGER.warning('Already subscribed to %s', topic)
            return
        res, mid = self.mqtt.subscribe(topic)
        if res == MQTT_ERR_SUCCESS:
            Entity.pending[mid] = (self, topic)
        else:
            _LOGGER.warning('Failure to subscribe to %s', self.topic)

    def command(self, command):
        _LOGGER.warning(f'No command to execute for {self}: {command}')

    def publish_discovery(self):
        self.subscribe_to(self.command_topic)
        self.publish(self.discovery_topic,
                     self.discovery_payload,
                     retain=True)

    def publish_availability(self, available):
        self.publish(self.availability_topic,
                     STATE_ONLINE if available and self.state else
                     STATE_OFFLINE)

    def publish_state(self):
        if self.state:
            _LOGGER.debug(f'State for {self.attr}: {self.state}')
            self.publish(self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


class Sensor(Entity):
    def __init__(self, attr, name, icon, unit):
        super().__init__('sensor', attr, name)
        self.icon = icon
        self.unit = unit

    def configurate(self, config):
        self.unit = (
            self.unit if 'scandinavian_miles' not in config
            else 'L/mil' if self.attr == 'average_fuel_consumption'
            else self.unit.replace('km', 'mil'))

    @property
    def discovery_payload(self):
        return dict(super().discovery_payload,
                    icon=self.icon,
                    unit_of_measurement=self.unit)

    @property
    def state(self):
        val = super().state
        return (val / 10
                if val and 'mil' in self.unit
                else val)


class FuelConsumption(Sensor):

    def __init__(self):
        super().__init__(attr='average_fuel_consumption',
                         name='Fuel consumption',
                         icon='mdi:gas-station',
                         unit='L/100 km')

    def configurate(self, config):
        self.unit = (self.unit.replace('100 km', 'mil')
                     if 'scandinavian_miles' in config
                     else self.unit)

    @property
    def state(self):
        val = super().state
        return (round(val / 10, 2
                      if 'mil' in self.unit
                      else 1)  # L/1000km -> L/100km
                if val
                else None)


class Odometer(Sensor):

    def __init__(self):
        super().__init__(attr='odometer',
                         name='Odometer',
                         icon='mdi:speedometer',
                         unit='km')

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
        return dict(super().discovery_payload,
                    payload_on=STATE_ON,
                    payload_off=STATE_OFF,
                    device_class=self.device_class)

    @property
    def state(self):
        val = super().state
        if self.attr == 'bulb_failures':
            return STATE_ON if val else STATE_OFF
        else:
            return STATE_ON if val != 'Normal' else STATE_OFF


class AnyOpen(BinarySensor):
    def __init__(self, attr, name, device_class):
        super().__init__(attr, name, device_class)

    @property
    def state(self):
        state = super().state
        return (STATE_ON if any([state[key]
                                 for key in state
                                 if 'Open' in key])
                else STATE_OFF)


class Doors(AnyOpen):
    def __init__(self):
        super().__init__(attr='doors',
                         name='Doors',
                         device_class='door')


class Windows(AnyOpen):
    def __init__(self):
        super().__init__(attr='windows',
                         name='Windows',
                         device_class='window')


class Lock(Entity):
    def __init__(self):
        super().__init__(component='lock',
                         attr='lock',
                         name='Door lock')

    @property
    def discovery_payload(self):
        return dict(super().discovery_payload,
                    payload_lock=STATE_LOCK,
                    payload_unlock=STATE_UNLOCK,
                    optimistic=True)

    @property
    def state(self):
        return (STATE_UNLOCK, STATE_LOCK)[self.vehicle.is_locked]

    def command(self, command):
        if command == STATE_LOCK:
            self.vehichle.lock()
        elif command == STATE_UNLOCK:
            self.vehichle.unlock()
        else:
            _LOGGER.warning(f'Unknown command: {command}')


class Switch(Entity):
    def __init__(self, attr, name, icon=None):
        super().__init__(component='switch',
                         attr=attr,
                         name=name)
        self.icon = icon

    @property
    def discovery_payload(self):
        return dict(super().discovery_payload,
                    payload_on=STATE_ON,
                    payload_off=STATE_OFF,
                    icon=self.icon,
                    optimistic=True)

    @property
    def state(self):
        return (STATE_OFF, STATE_ON)[super().state]


class Heater(Switch):
    def __init__(self):
        super().__init__(attr='heater',
                         name='Heater',
                         icon='mdi:radiator')

    @property
    def state(self):
        return (STATE_OFF, STATE_ON)[self.vehicle.is_heater_on]

    def command(self, command):
        if command == STATE_ON:
            self.vehichle.start_heater()
        elif command == STATE_OFF:
            self.vehichle.stop_heater()
        else:
            _LOGGER.warning(f'Unknown command: {command}')


class Position(Entity):
    def __init__(self):
        super().__init__(None, None, None)
        self.key = None

    def configurate(self, config):
        self.key = config.get('owntracks_key')

    @property
    def is_supported(self):
        #  No corresponding attr_supported
        return True

    def publish_discovery(self):
        pass

    def publish_availability(self, available):
        pass

    @property
    def state_topic(self):
        return f'owntracks/volvo/{self.vehicle.unique_id}'

    @property
    def state(self):
        res = dict(_type='location',
                   tid='volvo',
                   t='p',
                   lat=self.vehicle.position['latitude'],
                   lon=self.vehicle.position['longitude'],
                   acc=1,
                   tst=int(time()))
        return (dict(_type='encrypted',
                     data=owntracks_encrypt(dump_json(res), self.key))
                if self.key else res)


def create_entities(mqtt, vehicle):
    return [entity for entity in [
        Position(),
        Lock(),
        Heater(),
        Odometer(),
        Sensor(attr='fuel_amount',
               name='Fuel amount',
               icon='mdi:gas-station',
               unit='L'),
        Sensor(attr='fuel_amount_level',
               name='Fuel level',
               icon='mdi:water-percent',
               unit='%'),
        FuelConsumption(),
        Sensor(attr='distance_to_empty',
               name='Range',
               icon='mdi:ruler',
               unit='km'),
        BinarySensor(attr='washer_fluid_level',
                     name='Washer fluid',
                     device_class='safety'),
        BinarySensor(attr='brake_fluid',
                     name='Brake Fluid',
                     device_class='safety'),
        BinarySensor(attr='service_warning_status',
                     name='Service',
                     device_class='safety'),
        BinarySensor(attr='bulb_failures',
                     name='Bulbs',
                     device_class='safety'),
        Doors(),
        Windows()
    ] if entity.setup(mqtt, vehicle)]


def run(voc, config):

    # FIXME: Allow MQTT credentials in voc.conf

    clean_session = CLEAN_SESSION

    client_id = 'tellsticknet_{hostname}_{pid}'.format(
        hostname=hostname(),
        pid=getpid()) if not clean_session else None

    mqtt_config = read_mqtt_config()
    mqtt = paho.Client(client_id = client_id, clean_session = clean_session)
    mqtt.username_pw_set(username=mqtt_config['username'],
                         password=mqtt_config['password'])
    mqtt.tls_set(certs.where())

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message
    mqtt.on_subscribe = on_subscribe

    mqtt.connect(host=mqtt_config['host'],
                 port=int(mqtt_config['port']))
    mqtt.loop_start()

    interval = int(config['interval'])
    _LOGGER.info(f'Polling every {interval} seconds')

    entities = {}

    while True:
        available = voc.update()
        for vehicle in voc.vehicles:
            if vehicle not in entities:
                _LOGGER.debug('creating vehicle %s', vehicle)
                entities[vehicle] = create_entities(mqtt, vehicle)

                for entity in entities[vehicle]:
                    entity.configurate(config)

                for entity in entities[vehicle]:
                    entity.publish_discovery()

            for entity in entities[vehicle]:
                entity.publish_availability(available)
                if available:
                    entity.publish_state()

        sleep(interval)
