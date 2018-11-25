import pytest
from volvooncall import Connection
from asynctest import patch


def mocked_request(method, url, rel=None, **kwargs):

    if 'customeraccounts' in url:
        return {
            'username': 'foobar',
            'accountVehicleRelations': ['rel/1']
        }

    if 'rel' in url:
        return {
            'vehicle': 'vehicle/1'
        }

    if 'attributes' in url:
        return {
            'registrationNumber': 'FOO123',
        }

    if 'status' in url:
        return {
            'engineRunning': False,
            'engineStartSupported': True,
            'ERS': {'status': 'off'},
        }

    if 'position' in url:
        return {}

    if 'engine/start' in url:
        return {
            'service': 'engine/start',
            'status': 'Started'
        }

    return {
        "error": "Unauthorized"
    }


@patch('volvooncall.Connection._request', side_effect=mocked_request)
async def get_vehicle(mock):
    async with Connection(username='', password='') as connection:
        await connection.update()
        assert mock.called
        return next(connection.vehicles, None)


@pytest.mark.asyncio
async def test_basic():
    vehicle = await get_vehicle()
    assert(vehicle)
    assert(vehicle.registration_number == 'FOO123')


@pytest.mark.asyncio
async def test_engine():
    vehicle = await get_vehicle()
    assert(not vehicle.is_engine_running)


@pytest.mark.asyncio
async def test_ers(event_loop):
    vehicle = await get_vehicle()
    dashboard = vehicle.dashboard()
    engine_instruments = [
        instrument
        for instrument in dashboard.instruments
        if instrument.attr == 'is_engine_running']

    # a binary sensor and a switch should be present
    assert(len(engine_instruments) == 2)

    # should be off
    assert(all(not engine.state
               for engine in engine_instruments))


async def get_started_vehicle():

    def mocked_request_ers(method, url, rel=None, **kwargs):
        if 'status' in url:
            return {
                'engineRunning': False,
                'engineStartSupported': True,
                'ERS': {'status': 'on'},
            }
        return mocked_request(method, url, rel, **kwargs)

    vehicle = await get_vehicle()
    with patch('volvooncall.Connection._request',
               side_effect=mocked_request_ers) as mock:
        await vehicle.start_engine()
        assert mock.called
        return vehicle


@pytest.mark.asyncio
async def test_ers_start():
    vehicle = await get_started_vehicle()
    assert(vehicle.is_engine_running)


@pytest.mark.asyncio
async def test_ers_start_dashboard():
    vehicle = await get_started_vehicle()
    dashboard = vehicle.dashboard()
    engine_instruments = [
        instrument
        for instrument in dashboard.instruments
        if instrument.attr == 'is_engine_running']

    # a binary sensor and a switch should be present
    assert(len(engine_instruments) == 2)

    # shold be on
    assert(all(engine.state
               for engine in engine_instruments))
