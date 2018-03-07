#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Communicate with VOC server."""

import logging
from datetime import timedelta, date, datetime
from functools import partial
from sys import argv, version_info
import re
from os import environ as env
from os.path import join, dirname, expanduser
from itertools import product
from json import dumps as to_json
from collections import OrderedDict

from requests import Session, RequestException
from requests.compat import urljoin

_ = version_info >= (3, 0) or exit('Python 3 required')

__version__ = '0.4.4'

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi{region}.wirelesscar.net/customerapi/rest/v3.0/'
DEFAULT_SERVICE_URL = SERVICE_URL.format(region='')

HEADERS = {'X-Device-Id': 'Device',
           'X-OS-Type': 'Android',
           'X-Originator-Type': 'App',
           'X-OS-Version': '22',
           'Content-Type': 'application/json'}

TIMEOUT = timedelta(seconds=30)


def _obj_parser(obj):
    """Parse datetime (only Python3 because of timezone)."""
    for key, val in obj.items():
        try:
            obj[key] = datetime.strptime(val, '%Y-%m-%dT%H:%M:%S%z')
        except (TypeError, ValueError):
            pass
    return obj


def json_serialize(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


class Connection(object):

    """Connection to the VOC server."""

    def __init__(self, username, password,
                 service_url=None, region=None, **_):
        """Initialize."""
        _LOGGER.info('%s version: %s', __name__, __version__)

        self._session = Session()
        self._service_url = SERVICE_URL.format(region='-'+region) \
            if region else service_url or DEFAULT_SERVICE_URL
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = {}
        _LOGGER.debug('Using service <%s>', self._service_url)
        _LOGGER.debug('User: <%s>', username)

    def _request(self, method, ref, rel=None):
        """Perform a query to the online service."""
        try:
            url = urljoin(rel or self._service_url, ref)
            _LOGGER.debug('Request for %s', url)
            res = method(url, timeout=TIMEOUT.seconds)
            res.raise_for_status()
            res = res.json(object_hook=_obj_parser)
            _LOGGER.debug('Received %s', res)
            return res
        except RequestException as error:
            _LOGGER.warning('Failure when communcating with the server: %s',
                            error)
            raise

    def get(self, ref, rel=None):
        """Perform a query to the online service."""
        return self._request(self._session.get, ref, rel)

    def post(self, ref, rel=None, **data):
        """Perform a query to the online service."""
        return self._request(partial(self._session.post, json=data), ref, rel)

    def update(self, reset=False):
        """Update status."""
        try:
            _LOGGER.info('Updating')
            if not self._state or reset:
                _LOGGER.info('Querying vehicles')
                user = self.get('customeraccounts')
                _LOGGER.debug('Account for <%s> received',
                              user['username'])
                self._state = {}
                for vehicle in user['accountVehicleRelations']:
                    rel = self.get(vehicle)
                    vehicle = rel['vehicle'] + '/'
                    state = self.get('attributes', vehicle)
                    self._state.update({vehicle: state})
            for vin, vehicle in self._state.items():
                self._state[vin].update(
                    self.get('status', vin))
                self._state[vin].update(
                    self.get('position', vin))
                _LOGGER.debug('State: %s', self._state)
            return True
        except (IOError, OSError) as error:
            _LOGGER.warning('Could not query server: %s', error)

    @property
    def vehicles(self):
        """Return vehicle state."""
        return (Vehicle(self, url, vehicle)
                for url, vehicle in self._state.items())

    def vehicle(self, vin):
        """Return vehicle for given vin."""
        return next((vehicle for vehicle in self.vehicles
                     if vehicle.vin.lower() == vin.lower() or
                     vehicle.registration_number.lower() == vin.lower()), None)


def camel2slug(data):
    """Convert camelCase to camel_case."""
    if not isinstance(data, dict):
        return data
    return {re.sub("([A-Z])", "_\\1", k).lower().lstrip("_"):
            camel2slug(v)
            for k, v in data.items()}


class Vehicle(object):
    """Convenience wrapper around the state returned from the server."""
    # pylint: disable=no-member
    def __init__(self, conn, url, data):
        self.data = data
        for key, val in camel2slug(data).items():
            if not hasattr(self, key):  # do not overwrite
                setattr(self, key, val)
        self._connection = conn
        self._url = url

    def get(self, query):
        """Perform a query to the online service."""
        return self._connection.get(query, self._url)

    def post(self, query, **data):
        """Perform a query to the online service."""
        return self._connection.post(query, self._url, **data)

    def call(self, method):
        """Make remote method call."""
        try:
            res = self.post(method)

            if 'service' and 'status' not in res:
                _LOGGER.warning('Failed to execute: %s', res['status'])
                return

            if res['status'] not in ['Queued', 'Started']:
                _LOGGER.warning('Failed to execute: %s', res['status'])
                return

            # if Queued -> wait?

            service_url = res['service']
            res = self.get(service_url)

            if 'service' and 'status' not in res:
                _LOGGER.warning('Message not delivered: %s', res['status'])

            # if still Queued -> wait?

            if res['status'] not in ['MessageDelivered',
                                     'Successful',
                                     'Started']:
                _LOGGER.warning('Message not delivered: %s', res['status'])
                return

            _LOGGER.debug('Message delivered')
            return True
        except RequestException as error:
            _LOGGER.warning('Failure to execute: %s', error)

    @property
    def position_supported(self):
        """Return true if vehichle has position."""
        return 'position' in self.data

    @property
    def heater_supported(self):
        """Return true if vehichle has heater."""
        return ((self.remote_heater_supported or
                 self.preclimatization_supported) and
                hasattr(self, 'heater'))

    @property
    def is_locked(self):
        """Lock status."""
        return self.car_locked

    @property
    def is_heater_on(self):
        """Return status of heater."""
        return (self.heater_supported and
                'status' in self.heater and
                self.heater['status'] != 'off')

    @property
    def trips(self):
        """Return trips."""
        return self.get('trips')

    def lock(self):
        """Lock."""
        if not self.lock_supported:
            _LOGGER.error('Lock not supported')
            return
        self.call('lock')

    def unlock(self):
        """Unlock."""
        if not self.unlock_supported:
            _LOGGER.error('Unlock not supported')
            return
        self.call('unlock')

    def start_heater(self):
        """Turn on/off heater."""
        if self.remote_heater_supported:
            self.call('heater/start')
        elif self.preclimatization_supported:
            self.call('preclimatization/start')
        else:
            _LOGGER.error('No heater or preclimatization support.')

    def stop_heater(self):
        """Turn on/off heater."""
        if self.remote_heater_supported:
            self.call('heater/stop')
        elif self.preclimatization_supported:
            self.call('preclimatization/stop')
        else:
            _LOGGER.error('No heater or preclimatization support.')

    def __str__(self):
        return '%s (%s/%d) %s' % (
            self.registration_number,
            self.vehicle_type,
            self.model_year,
            self.vin)

    @property
    def json(self):
        """Return JSON representation."""
        return to_json(
            OrderedDict(sorted(self.data.items())),
            indent=4, default=json_serialize)


def read_credentials():
    """Read credentials from file."""
    for directory, filename in product(
            [dirname(argv[0]),
             expanduser('~'),
             env.get('XDG_CONFIG_HOME',
                     join(expanduser('~'), '.config'))],
            ['voc.conf',
             '.voc.conf']):
        try:
            config = join(directory, filename)
            _LOGGER.debug('checking for config file %s', config)
            with open(config) as config:
                return dict(x.split(': ')
                            for x in config.read().strip().splitlines()
                            if not x.startswith('#'))
        except (IOError, OSError):
            continue
    return {}


def main():
    """Main method."""
    if '-v' in argv:
        logging.basicConfig(level=logging.INFO)
    elif '-vv' in argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.ERROR)

    connection = Connection(**read_credentials())

    if connection.update():
        for vehicle in connection.vehicles:
            print(vehicle)


if __name__ == '__main__':
    main()
