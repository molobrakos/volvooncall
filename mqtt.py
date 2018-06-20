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
from threading import RLock, Event
import paho.mqtt.client as paho
from paho.mqtt.client import MQTT_ERR_SUCCESS
from volvooncall import owntracks_encrypt
from platform import node as hostname
from os import getpid
from dashboard import (Dashboard,
                       Lock, Position,
                       Heater, Sensor,
                       BinarySensor, Switch)

_LOGGER = logging.getLogger(__name__)

STATE_ON = 'on'
STATE_OFF = 'off'
STATE_ONLINE = 'online'
STATE_OFFLINE = 'offline'
STATE_LOCK = 'lock'
STATE_UNLOCK = 'unlock'

DISCOVERY_PREFIX = 'homeassistant'
TOPIC_PREFIX = 'volvo'

CONF_OWNTRACKS_KEY = 'owntracks_key'


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
    lock = RLock()

    def __init__(self, client, instrument, config):
        self.client = client
        self.instrument = instrument
        self.config = config

    def __str__(self):
        return str(self.instrument)

    @property
    def vehicle(self):
        return self.instrument.vehicle

    @property
    def state(self):
        state = self.instrument.state
        if self.is_lock:
            return (STATE_UNLOCK, STATE_LOCK)[state]
        elif self.is_switch:
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
    def attr(self):
        return self.instrument.attr

    @property
    def node_id(self):
        return f'{TOPIC_PREFIX}_{self.vehicle.unique_id}'

    @property
    def discovery_topic(self):
        return (f'{DISCOVERY_PREFIX}/{self.instrument.component}/'
                f'{self.node_id}/{self.attr}/config')

    @property
    def topic(self):
        return (f'{TOPIC_PREFIX}/{self.vehicle.unique_id}/'
                f'{self.attr}')

    @property
    def state_topic(self):
        if self.is_position:
            return f'owntracks/volvo/{self.vehicle.unique_id}'
        else:
            return f'{self.topic}/state'

    @property
    def availability_topic(self):
        return f'{self.topic}/avail'

    @property
    def command_topic(self):
        return f'{self.topic}/cmd'

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

    @threadsafe
    def publish(self, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        res, mid = self.client.publish(topic, payload, retain=retain)
        if res == MQTT_ERR_SUCCESS:
            Entity.pending[mid] = (topic, payload)
        else:
            _LOGGER.warning('Failure to publish on %s', topic)

    @threadsafe
    def subscribe_to(self, topic):
        _LOGGER.debug('Subscribing to %s', topic)
        res, mid = self.client.subscribe(topic)
        if res == MQTT_ERR_SUCCESS:
            Entity.pending[mid] = (self, topic)
        else:
            _LOGGER.warning('Failure to subscribe to %s', self.topic)

    @threadsafe
    def on_mqtt_message(self, userdata, message):
        command = message.payload
        if self.is_lock:
            self.instrument.set(command == STATE_LOCK)
        elif self.is_switch:
            self.instrument.set(command == STATE_ON)
        else:
            _LOGGER.warning(f'No command to execute for {self}: {command}')

    @property
    def is_sensor(self):
        return isinstance(self.instrument, Sensor)

    @property
    def is_binary_sensor(self):
        return isinstance(self.instrument, BinarySensor)

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
                     self.discovery_payload,
                     retain=True)

    def publish_availability(self, available):
        if self.is_position:
            return
        self.publish(self.availability_topic,
                     STATE_ONLINE if available and self.state is not None else
                     STATE_OFFLINE)

    def publish_state(self):
        if self.state is not None:
            _LOGGER.debug(f'State for {self.attr}: {self.state}')
            self.publish(self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


def run(voc, config):

    # FIXME: Allow MQTT credentials in voc.conf

    client_id = 'voc_{hostname}_{pid}'.format(
        hostname=hostname(),
        pid=getpid())

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

    _LOGGER.debug('Waiting for MQTT connection')
    mqtt.event_connected.wait()
    _LOGGER.debug('Connected')

    interval = int(config['interval'])
    _LOGGER.info(f'Polling every {interval} seconds')

    entities = {}

    while True:
        available = voc.update()
        for vehicle in voc.vehicles:
            if vehicle not in entities:
                _LOGGER.debug('creating vehicle %s', vehicle)
                entities[vehicle] = [Entity(mqtt,
                                            instrument,
                                            config)
                                     for instrument in Dashboard(
                                             vehicle, config).instruments]

                for entity in entities[vehicle]:
                    entity.publish_discovery()

            for entity in entities[vehicle]:
                entity.publish_availability(available)
                if available:
                    entity.publish_state()

        sleep(interval)
