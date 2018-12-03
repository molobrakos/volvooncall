#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import logging
from time import time
from json import dumps as dump_json
from os.path import join, expanduser
from os import environ as env
import string
from volvooncall import owntracks_encrypt
from platform import node as hostname
from dashboard import Lock, Position, Sensor, BinarySensor, Switch
from util import camel2slug, whitelisted
from hbmqtt.client import MQTTClient, ConnectException, ClientException
import asyncio

_LOGGER = logging.getLogger(__name__)

STATE_ON = "on"
STATE_OFF = "off"

STATE_ONLINE = "online"
STATE_OFFLINE = "offline"

STATE_LOCK = "lock"
STATE_UNLOCK = "unlock"

STATE_OPEN = "open"
STATE_CLOSE = "close"

STATE_SAFE = "safe"
STATE_UNSAFE = "unsafe"

DISCOVERY_PREFIX = "homeassistant"
TOPIC_PREFIX = "volvo"

CONF_OWNTRACKS_KEY = "owntracks_key"


TOPIC_WHITELIST = "_-" + string.ascii_letters + string.digits
TOPIC_SUBSTITUTE = "_"


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
    return "/".join(levels)


def read_mqtt_config():
    """Read credentials from ~/.config/mosquitto_pub."""
    with open(
        join(
            env.get("XDG_CONFIG_HOME", join(expanduser("~"), ".config")),
            "mosquitto_pub",
        )
    ) as f:
        d = dict(
            line.replace("-", "").split() for line in f.read().splitlines()
        )
        return dict(
            host=d["h"], port=d["p"], username=d["username"], password=d["pw"]
        )


class Entity:

    subscriptions = {}

    def __init__(self, client, instrument, config):
        self.client = client
        self.instrument = instrument
        self.config = config

    @classmethod
    def route_message(cls, topic, payload):
        entity = Entity.subscriptions.get(topic)
        if entity:
            entity.receive_command(payload)
        else:
            _LOGGER.warning("No subscriber to message on topic %s", topic)

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
        if state is None:
            return None
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
            res = dict(
                _type="location",
                tid="volvo",
                t="p",
                lat=lat,
                lon=lon,
                acc=1,
                tst=int(time()),
            )
            return (
                dict(
                    _type="encrypted",
                    data=owntracks_encrypt(dump_json(res), key),
                )
                if key
                else res
            )
        else:
            return state

    @property
    def discovery_node_id(self):
        return make_valid_hass_single_topic_level(
            make_topic(TOPIC_PREFIX, self.vehicle.unique_id)
        )

    @property
    def object_id(self):
        return make_valid_hass_single_topic_level(camel2slug(self.attr))

    @property
    def discovery_topic(self):
        return make_topic(
            DISCOVERY_PREFIX,
            self.instrument.component,
            self.discovery_node_id,
            self.object_id,
            "config",
        )

    @property
    def topic(self):
        return make_topic(TOPIC_PREFIX, self.vehicle.unique_id, self.object_id)

    def make_topic(self, *levels):
        return make_topic(self.topic, *levels)

    @property
    def state_topic(self):
        if self.is_position:
            return make_topic("owntracks", "volvo", self.vehicle.unique_id)
        else:
            return self.make_topic("state")

    @property
    def availability_topic(self):
        return self.make_topic("avail")

    @property
    def command_topic(self):
        return self.make_topic("cmd")

    @property
    def discovery_payload(self):
        instrument = self.instrument
        payload = dict(
            name=instrument.full_name,
            state_topic=self.state_topic,
            availability_topic=self.availability_topic,
            payload_available=STATE_ONLINE,
            payload_not_available=STATE_OFFLINE,
        )

        if self.is_mutable:
            payload.update(command_topic=self.command_topic)

        if self.is_sensor:
            return dict(
                payload,
                icon=instrument.icon,
                unit_of_measurement=instrument.unit,
            )
        elif self.is_opening:
            return dict(
                payload,
                payload_on=STATE_OPEN,
                payload_off=STATE_CLOSE,
                device_class=instrument.device_class,
            )
        elif self.is_safety:
            return dict(
                payload,
                payload_on=STATE_UNSAFE,
                payload_off=STATE_SAFE,
                device_class=instrument.device_class,
            )
        elif self.is_binary_sensor:
            return dict(
                payload,
                payload_on=STATE_ON,
                payload_off=STATE_OFF,
                device_class=instrument.device_class,
            )
        elif self.is_lock:
            return dict(
                payload,
                payload_lock=STATE_LOCK,
                payload_unlock=STATE_UNLOCK,
                optimistic=True,
            )
        elif self.is_switch:
            return dict(
                payload,
                payload_on=STATE_ON,
                payload_off=STATE_OFF,
                icon=instrument.icon,
                optimistic=True,
            )
        else:
            _LOGGER.error("Huh?")

    async def publish(self, topic, payload, retain=False):
        payload = (
            dump_json(payload) if isinstance(payload, dict) else str(payload)
        )
        _LOGGER.debug("Publishing on %s: %s", topic, payload)
        await self.client.publish(
            topic, payload.encode("utf-8"), retain=retain
        )
        _LOGGER.debug("Published on %s: %s", topic, payload)

    async def subscribe_to(self, topic):
        _LOGGER.debug("Subscribing to %s", topic)
        from hbmqtt.mqtt.constants import QOS_1

        await self.client.subscribe([(topic, QOS_1)])
        _LOGGER.debug("Subscribed to %s", topic)
        Entity.subscriptions[topic] = self

    def receive_command(self, command):

        run = asyncio.create_task

        if self.is_lock:
            if command == STATE_LOCK:
                run(self.instrument.lock())
            elif command == STATE_UNLOCK:
                run(self.instrument.unlock())
            else:
                _LOGGER.info("Skipping unknown payload %s", command)
        elif self.is_switch:
            if command == STATE_ON:
                run(self.instrument.turn_on())
            elif command == STATE_OFF:
                run(self.instrument.turn_off())
            else:
                _LOGGER.info("Skipping unknown payload %s", command)
        else:
            _LOGGER.warning("No command to execute for %s: %s", self, command)

    @property
    def is_mutable(self):
        return self.is_lock or self.is_switch

    @property
    def is_sensor(self):
        return isinstance(self.instrument, Sensor)

    @property
    def is_binary_sensor(self):
        return isinstance(self.instrument, BinarySensor)

    @property
    def is_opening(self):
        return self.is_binary_sensor and self.instrument.device_class in [
            "door",
            "window",
        ]

    @property
    def is_safety(self):
        return (
            self.is_binary_sensor and self.instrument.device_class == "safety"
        )

    @property
    def is_switch(self):
        return isinstance(self.instrument, Switch)

    @property
    def is_position(self):
        return isinstance(self.instrument, Position)

    @property
    def is_lock(self):
        return isinstance(self.instrument, Lock)

    async def publish_discovery(self):
        if self.is_position:
            return
        if self.is_mutable:
            await self.subscribe_to(self.command_topic)
        await self.publish(self.discovery_topic, self.discovery_payload)

    async def publish_availability(self, available):
        if self.is_position:
            return
        await self.publish(
            self.availability_topic,
            STATE_ONLINE
            if available and self.state is not None
            else STATE_OFFLINE,
        )

    async def publish_state(self):
        if self.state is not None:
            _LOGGER.debug("State for %s: %s", self.attr, self.state)
            await self.publish(self.state_topic, self.state)
        else:
            _LOGGER.warning("No state available for %s", self)


async def run(voc, config):

    logging.getLogger("hbmqtt.client.plugins.packet_logger_plugin").setLevel(
        logging.WARNING
    )

    # FIXME: Allow MQTT credentials in voc.conf

    client_id = "voc_{hostname}_{time}".format(
        hostname=hostname(), time=time()
    )

    mqtt_config = read_mqtt_config()
    mqtt = MQTTClient(client_id=client_id)
    url = mqtt_config.get("url")

    if not url:
        try:
            username = mqtt_config["username"]
            password = mqtt_config["password"]
            host = mqtt_config["host"]
            port = mqtt_config["port"]
            url = "mqtts://{username}:{password}@{host}:{port}".format(
                username=username, password=password, host=host, port=port
            )
        except Exception as e:
            exit(e)

    entities = {}

    async def mqtt_task():
        try:
            await mqtt.connect(url, cleansession=False)
            _LOGGER.info("Connected to MQTT server")
        except ConnectException as e:
            exit("Could not connect to MQTT server: %s" % e)
        while True:
            _LOGGER.debug("Waiting for messages")
            try:
                message = await mqtt.deliver_message()
                packet = message.publish_packet
                topic = packet.variable_header.topic_name
                payload = packet.payload.data.decode("ascii")
                _LOGGER.debug("got message on %s: %s", topic, payload)
                Entity.route_message(topic, payload)
            except ClientException as e:
                _LOGGER.error("MQTT Client exception: %s", e)

    asyncio.create_task(mqtt_task())

    interval = int(config["interval"])
    _LOGGER.info("Polling VOC every %d seconds", interval)
    while True:
        available = await voc.update(journal=True)
        wait_list = []
        for vehicle in voc.vehicles:
            if vehicle not in entities:
                _LOGGER.debug("creating vehicle %s", vehicle)

                dashboard = vehicle.dashboard(**config)

                entities[vehicle] = [
                    Entity(mqtt, instrument, config)
                    for instrument in dashboard.instruments
                ]
            for entity in entities[vehicle]:
                _LOGGER.debug(
                    "%s: %s", entity.instrument.full_name, entity.state
                )
                wait_list.append(entity.publish_discovery())
                wait_list.append(entity.publish_availability(available))
                if available:
                    wait_list.append(entity.publish_state())

        await asyncio.gather(*wait_list)
        _LOGGER.debug("Waiting for new VOC update in %d seconds", interval)
        await asyncio.sleep(interval)
