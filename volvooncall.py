#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve information from VOC
"""

import json
import requests
import logging
from datetime import timedelta
try:
    from urlparse import urljoin
except:
    from urllib.parse import urljoin

_LOGGER = logging.getLogger(__name__)

SERVICE_URL = 'https://vocapi.wirelesscar.net/customerapi/rest/v3.0/'
HEADERS = {"X-Device-Id": "Device",
           "X-OS-Type": "Android",
           "X-Originator-Type": "App"}

TIMEOUT = timedelta(seconds=5)

class Connection():

    def __init__(self, username, password):
        """Initialize."""
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session.auth = (username,
                              password)
        self._state = None

    def _query(self, ref, rel=SERVICE_URL):
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
                user = self._query("customeraccounts")
                self._state = {}
                for vehicle in user["accountVehicleRelations"]:
                    rel = self._query(vehicle)
                    vehicle = rel["vehicle"] + '/'
                    state = self._query("attributes", vehicle)
                    self._state.update({vehicle: state})
            _LOGGER.debug("Updating ")
            for vehicle in self._state:
                status = self._query("status", vehicle)
                position = self._query("position", vehicle)
                vehicle = self._state[vehicle]
                vehicle.update(status)
                vehicle.update(position)
            _LOGGER.debug("State: %s", self._state)
            return True, self._state
        except requests.exceptions.RequestException as error:
            _LOGGER.error("Could not query server: %s", error)
            return False, self._state

if __name__ == "__main__":
    from os import path
    import sys
    from yaml import safe_load as load_yaml
    logging.basicConfig(level=logging.INFO)
    with open(path.join(path.dirname(sys.argv[0]),
                        ".credentials.yaml")) as f:
        credentials = load_yaml(f)
        print(Connection(credentials["username"],
                         credentials["password"]).update())
