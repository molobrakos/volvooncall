#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve information from VOC
"""

import logging
from datetime import timedelta
import requests
from requests.compat import urljoin

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {"X-Device-Id": "Device",
           "X-OS-Type": "Android",
           "X-Originator-Type": "App",
		   "Content-Type": "application/json",
		   "X-OS-Version": "19"}

TIMEOUT = timedelta(seconds=5)


class Connection():
    """Connection to the VOC server."""

    def __init__(self, username, password):
        """Initialize."""
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = None

    def getquery(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        url = urljoin(rel, ref)
        _LOGGER.debug("Request for %s", url)
        res = self._session.get(url, timeout=TIMEOUT.seconds)
        res.raise_for_status()
        _LOGGER.debug("Received %s", res.json())
        return res.json()

    def postquery(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        url = urljoin(rel, ref)
        _LOGGER.debug("Post for %s", url)
        res = self._session.post(url, "{}")
        res.raise_for_status()
        _LOGGER.debug("Received %s", res.json())
        return res.json()

    def update(self, reset=False):
        """Update status."""
        try:
            _LOGGER.info("Updating1")
            if not self._state or reset:
                _LOGGER.info("Querying vehicles")
                user = self.getquery("customeraccounts")
                self._state = {}
                for vehicle in user["accountVehicleRelations"]:
                    rel = self.getquery(vehicle)
                    vehicle = rel["vehicle"] + '/'
                    state = self.getquery("attributes", vehicle)
                    self._state.update({vehicle: state})
            _LOGGER.debug("Updating2")
            for vehicle in self._state:
                status = self.getquery("status", vehicle)
                position = self.getquery("position", vehicle)
                heater = self.postquery("preclimatization/start", vehicle)
                vehicle = self._state[vehicle]
                vehicle.update(status)
                vehicle.update(position)
                vehicle.update(heater)
            _LOGGER.debug("State: %s", self._state)
            return True, self._state.values()
        except requests.exceptions.RequestException as error:
            _LOGGER.error("Could not query server: %s", error)
            return False, self._state.values()

if __name__ == "__main__":
    from os import path
    from sys import argv
    from pprint import pprint
#    logging.basicConfig(level=logging.CRITICAL)
#    logging.basicConfig(level=logging.ERROR)
#    logging.basicConfig(level=logging.WARNING)
    logging.basicConfig(level=logging.INFO)
#    logging.basicConfig(level=logging.DEBUG)
#    logging.basicConfig(level=logging.NOTSET)


    def credentials():
        """Return user, pass."""
        if len(argv) == 3:
            return argv[1:]
        try:
            from yaml import safe_load as load_yaml
            with open(path.join(path.dirname(argv[0]),
                                ".credentials.yaml")) as config:
                return load_yaml(config)
        except ImportError:
            _LOGGER.error("Incorrect parameters. \nUsage: volvooncall.py <username> <password>")
            exit(-1)

    res, value = Connection(**credentials()).update()
    if res:
        pprint(list(value))
