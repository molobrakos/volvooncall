#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve information from VOC
"""

import logging
from datetime import timedelta
import requests
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {"X-Device-Id": "Device",
           "X-OS-Type": "Android",
           "X-Originator-Type": "App"}

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

    def query(self, ref, rel=SERVICE_URL):
        """Perform a query to the online service."""
        url = urljoin(rel, ref)
        _LOGGER.debug("Request for %s", url)
        res = self._session.get(url, timeout=TIMEOUT.seconds)
        res.raise_for_status()
        _LOGGER.debug("Received %s", res.json())
        return res.json()

    def update(self, reset=False):
        """Update status."""
        try:
            _LOGGER.info("Updating")
            if not self._state or reset:
                _LOGGER.info("Querying vehicles")
                user = self.query("customeraccounts")
                self._state = {}
                for vehicle in user["accountVehicleRelations"]:
                    rel = self.query(vehicle)
                    vehicle = rel["vehicle"] + '/'
                    state = self.query("attributes", vehicle)
                    self._state.update({vehicle: state})
            _LOGGER.debug("Updating ")
            for vehicle in self._state:
                status = self.query("status", vehicle)
                position = self.query("position", vehicle)
                vehicle = self._state[vehicle]
                vehicle.update(status)
                vehicle.update(position)
            _LOGGER.debug("State: %s", self._state)
            return True, self._state.values()
        except requests.exceptions.RequestException as error:
            _LOGGER.error("Could not query server: %s", error)
            return False, self._state.values()

if __name__ == "__main__":
    from os import path
    from sys import argv
    logging.basicConfig(level=logging.INFO)

    def credentials():
        """Return user, pass."""
        if len(argv) == 3:
            return argv[1:]
        try:
            from yaml import safe_load as load_yaml
            with open(path.join(path.dirname(argv[0]),
                                ".credentials.yaml")) as config:
                config = load_yaml(config)
                return config["username"], config["password"]
        except ImportError:
            exit(-1)

    print(Connection(*credentials()).update())
