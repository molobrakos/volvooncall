from unittest.mock import patch
from volvooncall import Connection
import requests


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self, **kwargs):
        return self.json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(self.status_code)


def mocked_requests_get(*args, **kwargs):
    url = args[1]

    if 'customeraccounts' in url:
        return MockResponse(
            {
                'username': 'foobar',
                'accountVehicleRelations': ['rel/1']
            }, 200)

    if 'rel' in url:
        return MockResponse(
            {
                'vehicle': 'vehicle/1'
            }, 200)

    if 'attributes' in url:
        return MockResponse(
            {
                'registrationNumber': 'FOO123',

            }, 200)

    if 'status' in url:
        return MockResponse(
            {
                'engineRunning': False,
                'engineStartSupported': True,
                'ERS': {'status': 'off'},
            }, 200)

    if 'position' in url:
        return MockResponse(
            {
            }, 200)

    if 'engine/start' in url:
        return MockResponse(
            {
                'service': 'engine/start',
                'status': 'Started'
            }, 200)

    return MockResponse({
        "error": "Unauthorized"
    }, 401)


@patch('requests.Session.request', side_effect=mocked_requests_get)
def get_vehicle(req_mock):
    connection = Connection(username='', password='')
    connection.update()

    return next(connection.vehicles, None)


def test_basic():
    vehicle = get_vehicle()
    assert(vehicle)
    assert(vehicle.registration_number == 'FOO123')
    print(vehicle.is_engine_running)


def test_engine():
    vehicle = get_vehicle()
    assert(not vehicle.is_engine_running)


def test_ers():
    vehicle = get_vehicle()
    dashboard = vehicle.dashboard
    engines = [instrument
               for instrument in dashboard.instruments
               if instrument.attr == 'is_engine_running']

    # a binary sensor and a switch should be present
    assert(len(engines) == 2)

    # should be off
    assert(all(not engine.state for engine in engines))

def get_started_vehicle():

    def mocked_requests_get_ers(*args, **kwargs):
        url = args[1]
        if 'status' in url:
            return MockResponse(
                {
                    'engineRunning': False,
                    'engineStartSupported': True,
                    'ERS': {'status': 'on'},
                }, 200)
        return mocked_requests_get(*args, **kwargs)

    vehicle = get_vehicle()

    @patch('requests.Session.request', side_effect=mocked_requests_get_ers)
    def start_engine(req_mock):
        vehicle.start_engine()

    start_engine()
    return vehicle


def test_ers_start():
    vehicle = get_started_vehicle()
    assert(vehicle.is_engine_running)

def test_ers_start_dashboard():
    vehicle = get_started_vehicle()
    dashboard = vehicle.dashboard
    engines = [instrument
               for instrument in dashboard.instruments
               if instrument.attr == 'is_engine_running']

    # a binary sensor and a switch should be present
    assert(len(engines) == 2)

    # shold be on
    assert(all(engine.state for engine in engines))
