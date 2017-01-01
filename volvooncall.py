#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Communicate with VOC server."""

from __future__ import print_function
import logging
from datetime import timedelta, datetime
import sys
from requests import Session, RequestException
from requests.compat import urljoin

__version__ = '0.1.5'

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {'X-Device-Id': 'Device',
           'X-OS-Type': 'Android',
           'X-Originator-Type': 'App',
           'X-OS-Version': 22,
           'Content-Type': 'application/json'}

TIMEOUT = timedelta(seconds=10)


def _obj_parser(obj):
    """Parse datetime (only Python3) because of timezone."""
    for key, val in obj.items():
        try:
            obj[key] = datetime.strptime(val, '%Y-%m-%dT%H:%M:%S%z')
        except (TypeError, ValueError):
            pass
    return obj


class Connection(object):

    """Connection to the VOC server."""

    def __init__(self, username, password):
        """Initialize."""
        self._session = Session()
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = {}
        _LOGGER.debug('User: <%s>', username)

    def _query(self, ref, rel=SERVICE_URL, post=False):
        """Perform a query to the online service."""
        try:
            url = urljoin(rel, ref)
            _LOGGER.debug('Request for %s', url)
            method = self._session.post if post else self._session.get
            res = method(url, timeout=TIMEOUT.seconds)
            res.raise_for_status()
            res = res.json(object_hook=_obj_parser)
            _LOGGER.debug('Received %s', res)
            return res
        except RequestException as error:
            _LOGGER.error("Failure when communcating with the server: %s",
                          error)
            return res

    def get(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        return self._query(ref, rel)

    def post(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        return self._query(ref, rel, True)

    def call(self, method, rel=SERVICE_URL):
        """Make remote method call."""
        res = self.post(method, rel)
        if ('service' in res and
                'status' in res and
                res['status'] == 'Started'):
            service_url = res['service']
            res = self.get(service_url)
            if (('service' in res and
                 'status' in res and
                 res['status'] == 'MessageDelivered')):
                _LOGGER.info('ok')
                return True

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
        for vehicle in self.vehicles:
            if ((vehicle.vin.lower() == vin.lower() or
                 vehicle.registrationNumber.lower() == vin.lower())):
                return vehicle


class Vehicle(object):
    """Convenience wrapper around the state returned from the server."""
    # pylint: disable=no-member
    def __init__(self, conn, url, data):
        self.__dict__ = data  # assume no name clashes
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
        return self.remoteHeaterSupported and self.heater['status'] != 'off'

    @property
    def is_preclimatization_on(self):
        """Return status of heater."""
        return (self.preclimatizationSupported and
                self.preclimatization['status'] != 'off')

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

    def set_heater_or_preclimatization(self, state):
        """Set status of heater."""
        if self.remoteHeaterSupported:
            self.call('heater/start' if state else 'heater/stop')
        elif self.preclimatizationSupported:
            self.call('preclimatization/start'
                      if state else 'preclimatization/stop')
        else:
            _LOGGER.error('Not supported')

    def set_heater(self, state):
        """Turn on/off heater."""
        if not self.remoteHeaterSupported:
            _LOGGER.error('Remote heater not supported')
            return
        self.call('heater/start' if state else 'heater/stop')

    def set_preclimatization(self, state):
        """Turn on/off heater."""
        if not self.preclimatizationSupported:
            print('Preclimatization not supported')
            return
        self.call('preclimatization/start'
                  if state else 'preclimatization/stop')

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
        with open(path.join(path.dirname(sys.argv[0]),
                            '.credentials.conf')) as config:
            return dict(x.split(': ')
                        for x in config.read().strip().splitlines())
    except (IOError, OSError):
        pass


def main(argv):
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
    main(sys.argv)
