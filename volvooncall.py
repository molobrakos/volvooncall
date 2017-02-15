#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Communicate with VOC server."""

from __future__ import print_function
import logging
from datetime import timedelta, datetime
from sys import argv
from requests import Session, RequestException
from requests.compat import urljoin

__version__ = '0.1.10'

_LOGGER = logging.getLogger(__name__)

DEFAULT_SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {'X-Device-Id': 'Device',
           'X-OS-Type': 'Android',
           'X-Originator-Type': 'App',
           'X-OS-Version': '22',
           'Content-Type': 'application/json'}

TIMEOUT = timedelta(seconds=10)


def _obj_parser(obj):
    """Parse datetime (only Python3 because of timezone)."""
    for key, val in obj.items():
        try:
            obj[key] = datetime.strptime(val, '%Y-%m-%dT%H:%M:%S%z')
        except (TypeError, ValueError):
            pass
    return obj


class Connection(object):

    """Connection to the VOC server."""

    def __init__(self, username, password, service_url=DEFAULT_SERVICE_URL):
        """Initialize."""
        self._session = Session()
        self._service_url = service_url
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = {}
        _LOGGER.debug('User: <%s>', username)

    def _query(self, ref, rel=None, post=False):
        """Perform a query to the online service."""
        try:
            url = urljoin(rel or self._service_url, ref)
            _LOGGER.debug('Request for %s', url)
            if post:
                res = self._session.post(url, data='{}',
                                         timeout=TIMEOUT.seconds)
            else:
                res = self._session.get(url, timeout=TIMEOUT.seconds)
            res.raise_for_status()
            res = res.json(object_hook=_obj_parser)
            _LOGGER.debug('Received %s', res)
            return res
        except RequestException as error:
            _LOGGER.error("Failure when communcating with the server: %s",
                          error)
            raise

    def get(self, ref, rel=None):
        """Perform a query to the online service."""
        return self._query(ref, rel)

    def post(self, ref, rel=None):
        """Perform a query to the online service."""
        return self._query(ref, rel, True)

    def call(self, method, rel=None):
        """Make remote method call."""
        try:
            res = self.post(method, rel)

            if (('service' and 'status' not in res or
                 res['status'] != 'Started')):
                _LOGGER.error('Failed to execute: %s', res['status'])
                return

            service_url = res['service']
            res = self.get(service_url)
            if (('service' and 'status' not in res or
                 res['status'] not in ['MessageDelivered',
                                       'Successful',
                                       'Started'])):
                _LOGGER.error('Message not delivered: %s', res['status'])
                return

            _LOGGER.debug('Message delivered')
            return True
        except RequestException as error:
            _LOGGER.error('Failure to execute: %s', error)

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
            _LOGGER.error('Could not query server: %s', error)

    @property
    def vehicles(self):
        """Return vehicle state."""
        return (Vehicle(self, url, vehicle)
                for url, vehicle in self._state.items())

    def vehicle(self, vin):
        """Return vehicle for given vin."""
        return next((vehicle for vehicle in self.vehicles
                     if vehicle.vin.lower() == vin.lower() or
                     vehicle.registrationNumber.lower() == vin.lower()), None)


class Vehicle(object):
    """Convenience wrapper around the state returned from the server."""
    # pylint: disable=no-member
    def __init__(self, conn, url, data):
        self.__dict__ = data  # cave: assume no name clashes
        self._connection = conn
        self._url = url

    def call(self, method):
        """Make remote method call."""
        return self._connection.call(method, self._url)

    @property
    def is_locked(self):
        """Lock status."""
        return self.carLocked

    @property
    def is_heater_on(self):
        """Return status of heater."""
        return ((self.remoteHeaterSupported or
                 self.preclimatizationSupported) and
                hasattr(self, 'heater') and
                self.heater['status'] != 'off')

    def lock(self):
        """Lock."""
        if not self.lockSupported:
            _LOGGER.error('Lock not supported')
            return
        self.call('lock')

    def unlock(self):
        """Unlock."""
        if not self.unlockSupported:
            _LOGGER.error('Unlock not supported')
            return
        self.call('unlock')

    def start_heater(self):
        """Turn on/off heater."""
        if self.remoteHeaterSupported:
            self.call('heater/start')
        elif self.preclimatizationSupported:
            self.call('preclimatization/start')
        else:
            _LOGGER.error("No heater or preclimatization support.")

    def stop_heater(self):
        """Turn on/off heater."""
        if self.remoteHeaterSupported:
            self.call('heater/stop')
        elif self.preclimatizationSupported:
            self.call('preclimatization/stop')
        else:
            _LOGGER.error("No heater or preclimatization support.")

    def __str__(self):
        return '%s (%s/%d) %s' % (
            self.registrationNumber,
            self.vehicleType,
            self.modelYear,
            self.vin)


def read_credentials():
    """Read credentials from file."""
    try:
        from os import path
        with open(path.join(path.dirname(argv[0]),
                            '.credentials.conf')) as config:
            return dict(x.split(': ')
                        for x in config.read().strip().splitlines()
                        if not x.startswith('#'))
    except (IOError, OSError):
        pass


def main():
    """Main method."""
    if "-v" in argv:
        logging.basicConfig(level=logging.INFO)
    elif "-vv" in argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.ERROR)

    connection = Connection(**read_credentials())

    if connection.update():
        for vehicle in connection.vehicles:
            print(vehicle)


if __name__ == '__main__':
    main()
