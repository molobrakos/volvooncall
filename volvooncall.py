#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve information from VOC

Usage:
  volvooncall.py (-h | --help)
  volvooncall.py --version
  volvooncall.py [options]
  volvooncall.py --vin=<vin>
  volvooncall.py [(--user <username> --pass <password>)]

Options:
  -u <username>, --user=<username>  VOC username
  -p <password>, --pass=<password>  VOC password
  --vin=<vin>                       VIN or registration number
                                    [default: first veichle]
  -h --help                         Show this message
  -v                                Increase verbosity
  --version                         Show version
"""

import logging
from datetime import timedelta, datetime
import docopt
import requests
from requests.compat import urljoin

__version__ = '0.1.3'

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {'X-Device-Id': 'Device',
           'X-OS-Type': 'Android',
           'X-Originator-Type': 'App'}

TIMEOUT = timedelta(seconds=5)


def datetime_parser(obj):
    """Parse datetime (only Python3) because of timezone."""
    for key, val in obj.items():
        try:
            obj[key] = datetime.strptime(val, '%Y-%m-%dT%H:%M:%S%z')
        except (TypeError, ValueError):
            pass
    return obj


class Connection():

    """Connection to the VOC server."""

    def __init__(self, username, password):
        """Initialize."""
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = {}
        _LOGGER.debug("User: <%s>", username)

    def query(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        url = urljoin(rel, ref)
        _LOGGER.debug('Request for %s', url)
        res = self._session.get(url, timeout=TIMEOUT.seconds)
        res.raise_for_status()
        res = res.json(object_hook=datetime_parser)
        _LOGGER.debug('Received %s', res)
        return res

    def update(self, reset=False):
        """Update status."""
        try:
            _LOGGER.info('Updating')
            if not self._state or reset:
                _LOGGER.info('Querying vehicles')
                user = self.query('customeraccounts')
                _LOGGER.debug("Account for <%s> received",
                              user['username'])
                self._state = {}
                for vehicle in user['accountVehicleRelations']:
                    rel = self.query(vehicle)
                    vehicle = rel['vehicle'] + '/'
                    state = self.query('attributes', vehicle)
                    self._state.update({vehicle: state})
            for vin, vehicle in self._state.items():
                self._state[vin].update(
                    self.query('status', vin))
                self._state[vin].update(
                    self.query('position', vin))
                _LOGGER.debug('State: %s', self._state)
            return True
        except (IOError, OSError) as error:
            _LOGGER.error('Could not query server: %s', error)

    @property
    def vehicles(self):
        """Return state."""
        return (Vehicle(vehicle) for vehicle in self._state.values())


class Vehicle:
    """Convenience wrapper around the state returned from the server."""
    # pylint: disable=no-member
    def __init__(self, data):
        self.__dict__ = data

    @property
    def is_heater_on(self):
        """Return status of heater."""
        return self.heater['status'] != 'off'

    def turn_heater_on(self):
        """Turn on heater."""
        pass

    def __str__(self):
        return "%s (%s/%d) %s %dkm (fuel %d%% %dkm)" % (
            self.registrationNumber,
            self.vehicleType,
            self.modelYear,
            self.VIN,
            self.odometer / 1000,
            self.fuelAmountLevel,
            self.distanceToEmpty)


def main(argv):
    """Command line interface."""

    args = docopt.docopt(__doc__, argv=argv[1:],
                         version=__version__)

    logging.basicConfig(level=logging.ERROR)
    if args['-v']:
        logging.basicConfig(level=logging.INFO)
    if args['-v'] == 2:
        logging.basicConfig(level=logging.DEBUG)

    if args['--user'] and args['--pass']:
        connection = Connection(args['--user'],
                                args['--pass'])
    else:
        try:
            from os import path
            with open(path.join(path.dirname(argv[0]),
                                '.credentials.conf')) as config:
                credentials = dict(x.split(": ")
                                   for x in config.read().strip().splitlines())
                connection = Connection(**credentials)
        except (IOError, OSError):
            print("Could not read configuration "
                  "and no credentials on command line\n")
            raise docopt.DocoptExit()

    if connection.update():
        for vehicle in connection.vehicles:
            print(vehicle)
            try:
                print("    position: %.14f,%.14f" %
                      (vehicle.position['latitude'],
                       vehicle.position['longitude']))
            except AttributeError:
                pass


if __name__ == '__main__':
    import sys
    main(sys.argv)
