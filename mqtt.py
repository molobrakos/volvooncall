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
from threading import Event
import string
from threading import RLock
import paho.mqtt.client as paho
from paho.mqtt.client import MQTT_ERR_SUCCESS
from volvooncall import owntracks_encrypt
from platform import node as hostname
from dashboard import (Dashboard,
                       Lock, Position,
                       Heater, Sensor,
                       BinarySensor, Switch)
from util import camel2slug, whitelisted

_LOGGER = logging.getLogger(__name__)

STATE_ON = 'on'
STATE_OFF = 'off'

STATE_ONLINE = 'online'
STATE_OFFLINE = 'offline'

STATE_LOCK = 'lock'
STATE_UNLOCK = 'unlock'

STATE_OPEN = 'open'
STATE_CLOSE = 'close'

STATE_SAFE = 'safe'
STATE_UNSAFE = 'unsafe'

DISCOVERY_PREFIX = 'homeassistant'
TOPIC_PREFIX = 'volvo'

CONF_OWNTRACKS_KEY = 'owntracks_key'


TOPIC_WHITELIST = '_-' + string.ascii_letters + string.digits
TOPIC_SUBSTITUTE = '_'


LOCK = RLock()


def threadsafe(function):
    """ Synchronization decorator.
    The paho MQTT library runs the on_subscribe etc callbacks
    in its own thread and since we keep track of subscriptions etc
    in Device.subscriptions, we need to synchronize threads."""
    def wrapper(*args, **kw):
        with LOCK:
            return function(*args, **kw)
    return wrapper


def make_valid_hass_single_topic_level(s):
    """Transform a multi level topic to a single level.

    >>> make_valid_hass_single_topic_level('foo/bar/baz')
    'foo_bar_baz'

    >>> make_valid_hass_single_topic_level('hello å ä ö')
    'hello______'
    """
    return whitelisted(s, TOPIC_WHITELIST, TOPIC_SUBSTITUTE)


def make_topic(*levels):
    """Create a valid topic.

    >>> make_topic('foo', 'bar')
    'foo/bar'

    >>> make_topic(('foo', 'bar'))
    'foo/bar'
    """
    if len(levels) == 1 and isinstance(levels[0], tuple):
        return make_topic(*levels[0])
    return '/'.join(levels)


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
    if rc != MQTT_ERR_SUCCESS:
        _LOGGER.error('Failure to connect: %d', rc)
        return
    _LOGGER.info('Connected')

    if flags.get('session present', False):
        _LOGGER.debug('Session present')
    else:
        _LOGGER.debug('Session not present, resubscribe to topics')
        for entity in Entity.entities:
            entity.publish_discovery()

    # Go on
    client.event_connected.set()


@threadsafe
def on_publish(client, userdata, mid):
    _LOGGER.debug('Successfully published on %s: %s',
                  *Entity.pending.pop(mid))


def on_disconnect(client, userdata, rc):
    if rc == MQTT_ERR_SUCCESS:
        # we called disconnect ourselves
        _LOGGER.info('Disconnect successful')
    else:
        _LOGGER.warning('Disconnected, automatically reconnecting')
        client.event_connected.clear()


@threadsafe
def on_subscribe(client, userdata, mid, qos):
    entity, topic = Entity.pending.pop(mid)
    _LOGGER.debug('Successfully subscribed to %s',
                  topic)
    client.message_callback_add(topic, entity.on_mqtt_message)


@threadsafe
def on_message(client, userdata, message):
    _LOGGER.warning('Got unhandled message on '
                    f'{message.topic}: {message.payload}')


class Entity:

    pending = {}
    entities = []

    def __init__(self, client, instrument, config):
        self.client = client
        self.instrument = instrument
        self.config = config

    @property
    def vehicle(self):
        return self.instrument.vehicle

    @property
    def attr(self):
        return self.instrument.attr

    @property
    def name(self):
        return self.instrument.full_name

    @property
    def state(self):
        state = self.instrument.state
        if self.is_lock:
            return (STATE_UNLOCK, STATE_LOCK)[state]
        elif self.is_switch:
            return (STATE_OFF, STATE_ON)[state]
        elif self.is_opening:
            return (STATE_CLOSE, STATE_OPEN)[state]
        elif self.is_safety:
            return (STATE_SAFE, STATE_UNSAFE)[state]
        elif self.is_binary_sensor:
            return (STATE_OFF, STATE_ON)[state]
        elif self.is_position:
            lat, lon = state
            key = self.config.get(CONF_OWNTRACKS_KEY)
            res = dict(_type='location',
                       tid='volvo',
                       t='p',
                       lat=lat,
                       lon=lon,
                       acc=1,
                       tst=int(time()))
            return (dict(_type='encrypted',
                         data=owntracks_encrypt(
                             dump_json(res), key))
                    if key else res)
        else:
            return state

    @property
    def discovery_node_id(self):
        return make_valid_hass_single_topic_level(make_topic(
            TOPIC_PREFIX,
            self.vehicle.unique_id))

    @property
    def object_id(self):
        return make_valid_hass_single_topic_level(camel2slug(self.attr))

    @property
    def discovery_topic(self):
        return make_topic(DISCOVERY_PREFIX,
                          self.instrument.component,
                          self.discovery_node_id,
                          self.object_id,
                          'config')

    @property
    def topic(self):
        return make_topic(TOPIC_PREFIX,
                          self.vehicle.unique_id,
                          self.object_id)

    def make_topic(self, *levels):
        return make_topic(self.topic, *levels)

    @property
    def state_topic(self):
        if self.is_position:
            return make_topic('owntracks', 'volvo', self.vehicle.unique_id)
        else:
            return self.make_topic('state')

    @property
    def availability_topic(self):
        return self.make_topic('avail')

    @property
    def command_topic(self):
        return self.make_topic('cmd')

    @property
    def discovery_payload(self):
        instrument = self.instrument
        payload = dict(name=instrument.full_name,
                       state_topic=self.state_topic,
                       availability_topic=self.availability_topic,
                       payload_available=STATE_ONLINE,
                       payload_not_available=STATE_OFFLINE,
                       command_topic=self.command_topic)
        if self.is_sensor:
            return dict(payload,
                        icon=instrument.icon,
                        unit_of_measurement=instrument.unit)
        elif self.is_opening:
            return dict(payload,
                        payload_on=STATE_OPEN,
                        payload_off=STATE_CLOSE,
                        device_class=instrument.device_class)
        elif self.is_safety:
            return dict(payload,
                        payload_on=STATE_UNSAFE,
                        payload_off=STATE_SAFE,
                        device_class=instrument.device_class)
        elif self.is_binary_sensor:
            return dict(payload,
                        payload_on=STATE_ON,
                        payload_off=STATE_OFF,
                        device_class=instrument.device_class)
        elif self.is_lock:
            return dict(payload,
                        payload_lock=STATE_LOCK,
                        payload_unlock=STATE_UNLOCK,
                        optimistic=True)
        elif self.is_switch:
            return dict(payload,
                        payload_on=STATE_ON,
                        payload_off=STATE_OFF,
                        icon=instrument.icon,
                        optimistic=True)
        else:
            _LOGGER.error('Huh?')

    def publish(self, topic, payload, retain=False):
        payload = (dump_json(payload)
                   if isinstance(payload, dict)
                   else str(payload))
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        res, mid = self.client.publish(topic, payload, retain=retain)
        if res == MQTT_ERR_SUCCESS:
            with LOCK:
                Entity.pending[mid] = (topic, payload)
        else:
            _LOGGER.warning('Failure to publish on %s', topic)

    def subscribe_to(self, topic):
        _LOGGER.debug('Subscribing to %s', topic)
        res, mid = self.client.subscribe(topic)
        if res == MQTT_ERR_SUCCESS:
            with LOCK:
                Entity.pending[mid] = (self, topic)
        else:
            _LOGGER.warning('Failure to subscribe to %s', self.topic)

    def on_mqtt_message(self, userdata, message):
        command = message.payload
        if self.is_lock:
            if command == STATE_LOCK:
                self.instrument.lock()
            else:
                self.instrument.unlock()
        elif self.is_switch:
            if command == STATE_ON:
                self.instrument.turn_on()
            else:
                self.instrument.turn_off()
        else:
            _LOGGER.warning(f'No command to execute for {self}: {command}')

    @property
    def is_sensor(self):
        return isinstance(self.instrument, Sensor)

    @property
    def is_binary_sensor(self):
        return isinstance(self.instrument, BinarySensor)

    @property
    def is_opening(self):
        return (self.is_binary_sensor and
                self.instrument.device_class in ['door', 'window'])

    @property
    def is_safety(self):
        return (self.is_binary_sensor and
                self.instrument.device_class == 'safety')

    @property
    def is_switch(self):
        return isinstance(self.instrument, Switch)

    @property
    def is_position(self):
        return isinstance(self.instrument, Position)

    @property
    def is_lock(self):
        return isinstance(self.instrument, Lock)

    @property
    def is_heater(self):
        return isinstance(self.instrument, Heater)

    def publish_discovery(self):
        if self.is_position:
            return
        self.subscribe_to(self.command_topic)
        self.publish(self.discovery_topic,
                     self.discovery_payload)

    def publish_availability(self, available):
        if self.is_position:
            return
        self.publish(self.availability_topic,
                     STATE_ONLINE if available and
                     self.state is not None else
                     STATE_OFFLINE)

    def publish_state(self):
        if self.state is not None:
            _LOGGER.debug(f'State for {self.attr}: {self.state}')
            self.publish(self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


def run(voc, config):

    # FIXME: Allow MQTT credentials in voc.conf

    client_id = 'voc_{hostname}_{time}'.format(
        hostname=hostname(),
        time=time())

    mqtt_config = read_mqtt_config()

    mqtt = paho.Client(client_id=client_id,
                       clean_session=False)
    mqtt.username_pw_set(username=mqtt_config['username'],
                         password=mqtt_config['password'])
    mqtt.tls_set(certs.where())

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message
    mqtt.on_subscribe = on_subscribe

    mqtt.event_connected = Event()

    mqtt.connect(host=mqtt_config['host'],
                 port=int(mqtt_config['port']))
    mqtt.loop_start()

    interval = int(config['interval'])
    _LOGGER.info(f'Polling every {interval} seconds')

    entities = {}

    while True:

        if not mqtt.event_connected.is_set():
            _LOGGER.debug('Waiting for MQTT connection')
            mqtt.event_connected.wait()
            _LOGGER.debug('Connected')

        available = True
        for vehicle in voc.vehicles:
            if vehicle not in entities:
                _LOGGER.debug('creating vehicle %s', vehicle)

                dashboard = Dashboard(vehicle)
                dashboard.configurate(**config)

                entities[vehicle] = [Entity(mqtt,
                                            instrument,
                                            config)
                                     for instrument in dashboard.instruments]

            for entity in entities[vehicle]:
                _LOGGER.debug('%s: %s',
                              entity.instrument.full_name, entity.state)
                entity.publish_discovery()
                entity.publish_availability(available)
                if available:
                    entity.publish_state()

        sleep(interval)
        available = voc.update()
