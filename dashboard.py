#  Utilities for integration with Home Assistant (directly or via MQTT)

import logging

_LOGGER = logging.getLogger(__name__)

CONF_SCANDINAVIAN_MILES = 'scandinavian_miles'


def find_path(src, path):
    """
    >>> find_path(dict(a=1), 'a')
    1

    >>> find_path(dict(a=1), '')
    {'a': 1}

    >>> find_path(dict(a=None), 'a')


    >>> find_path(dict(a=1), 'b')
    Traceback (most recent call last):
    ...
    KeyError: 'b'

    >>> find_path(dict(a=dict(b=1)), 'a.b')
    1

    >>> find_path(dict(a=dict(b=1)), 'a')
    {'b': 1}

    >>> find_path(dict(a=dict(b=1)), 'a.c')
    Traceback (most recent call last):
    ...
    KeyError: 'c'

    """
    if not path:
        return src
    if isinstance(path, str):
        path = path.split('.')
    return find_path(src[path[0]], path[1:])


def is_valid_path(src, path):
    """
    >>> is_valid_path(dict(a=1), 'a')
    True

    >>> is_valid_path(dict(a=1), '')
    True

    >>> is_valid_path(dict(a=1), None)
    True

    >>> is_valid_path(dict(a=1), 'b')
    False
    """
    try:
        find_path(src, path)
        return True
    except KeyError:
        return False


class Instrument:

    def __init__(self, component, attr, name, icon=None):
        self.attr = attr
        self.component = component
        self.name = name
        self.vehicle = None
        self.icon = icon

    def __repr__(self):
        return self.full_name

    def configurate(self, config):
        pass

    def setup(self, vehicle, config):
        self.vehicle = vehicle
        self.configurate(config)
        return self.is_supported

    @property
    def vehicle_name(self):
        return self.vehicle.registration_number or self.vehicle.vin

    @property
    def full_name(self):
        return f'{self.vehicle_name} {self.name}'

    @property
    def is_supported(self):
        supported = 'is_' + self.attr + '_supported'
        if hasattr(self.vehicle, supported):
            return getattr(self.vehicle, supported)
        if hasattr(self.vehicle, self.attr):
            return True
        return is_valid_path(self.vehicle.attrs, self.attr)

    @property
    def str_state(self):
        return self.state

    @property
    def state(self):
        if hasattr(self.vehicle, self.attr):
            return getattr(self.vehicle, self.attr)
        return find_path(self.vehicle.attrs, self.attr)


class Sensor(Instrument):
    def __init__(self, attr, name, icon, unit):
        super().__init__('sensor', attr, name, icon)
        self.unit = unit

    def configurate(self, config):
        if (CONF_SCANDINAVIAN_MILES in config and 'km' in self.unit):
            self.unit = 'mil'

    @property
    def str_state(self):
        return f'{self.state} {self.unit}'

    @property
    def state(self):
        val = super().state
        if val and 'mil' in self.unit:
            return val / 10
        else:
            return val


class FuelConsumption(Sensor):

    def __init__(self):
        super().__init__(attr='average_fuel_consumption',
                         name='Fuel consumption',
                         icon='mdi:gas-station',
                         unit='L/100 km')

    def configurate(self, config):
        if CONF_SCANDINAVIAN_MILES in config:
            self.unit = 'L/mil'

    @property
    def state(self):
        val = super().state
        if val:
            if 'mil' in self.unit:
                return round(val / 10, 2)
            else:
                return round(val, 1)


class Odometer(Sensor):

    def __init__(self,
                 attr='odometer',
                 name='Odometer'):
        super().__init__(attr=attr,
                         name=name,
                         icon='mdi:speedometer',
                         unit='km')

    @property
    def state(self):
        val = super().state
        if val:
            return int(round(val / 1000))  # m->km


class BinarySensor(Instrument):
    def __init__(self, attr, name, device_class):
        super().__init__('binary_sensor', attr, name)
        self.device_class = device_class

    @property
    def str_state(self):
        if self.device_class in ['door', 'window']:
            return 'Open' if self.state else 'Closed'
        if self.device_class == 'safety':
            return 'Warning!' if self.state else 'OK'
        if self.device_class == 'plug':
            return 'Charging' if self.state else 'Plug removed'
        return 'On' if self.state else 'Off'

    @property
    def state(self):
        val = super().state
        if isinstance(val, (bool, list)):
            #  for list (e.g. bulb_failures):
            #  empty list (False) means no problem
            return bool(val)
        elif isinstance(val, str):
            return val != 'Normal'
        else:
            _LOGGER.error('Can not encode state %s:%s', val, type(val))


class BatteryChargeStatus(BinarySensor):
    def __init__(self):
        super().__init__('hvBattery.hvBatteryChargeStatus',
                         'Battery charging',
                         'plug')

    @property
    def state(self):
        return super(BinarySensor, self).state != 'plugRemoved'


class Lock(Instrument):
    def __init__(self):
        super().__init__(component='lock',
                         attr='lock',
                         name='Door lock')

    @property
    def str_state(self):
        return 'Locked' if self.state else 'Unlocked'

    @property
    def state(self):
        return self.vehicle.is_locked

    def command(self, command):
        if self.state:
            self.vehichle.lock()
        else:
            self.vehichle.unlock()


class Switch(Instrument):
    def __init__(self, attr, name, icon):
        super().__init__(component='switch',
                         attr=attr,
                         name=name,
                         icon=icon)

    @property
    def str_state(self):
        return 'On' if self.state else 'Off'

    def set(self, state):
        pass


class Heater(Switch):
    def __init__(self):
        super().__init__(attr='heater',
                         name='Heater',
                         icon='mdi:radiator')

    @property
    def state(self):
        return self.vehicle.is_heater_on

    def set(self, state):
        if state:
            self.vehichle.start_heater()
        else:
            self.vehichle.stop_heater()


class Engine(Switch):

    # FIXME: Should be a BinarySensor if engine start not supported?

    def __init__(self):
        super().__init__(attr='engineRunning',
                         name='Engine',
                         icon='mdi:engine')

    def set(self, state):
        if state:
            self.vehichle.start_engine()
        else:
            self.vehichle.stop_engine()


class Position(Instrument):
    def __init__(self):
        super().__init__(component=None,
                         attr='position',
                         name='Position')

    @property
    def state(self):
        return (super().state['latitude'],
                super().state['longitude'])


#  FIXME: Maybe make this list configurable as external yaml
class Dashboard():
    def __init__(self, vehicle, config):
        self.instruments = [
            instrument for instrument in [
                Position(),
                Lock(),
                Heater(),
                Odometer(),
                Odometer(attr='tripMeter1',
                         name='Trip meter 1'),
                Odometer(attr='tripMeter2',
                         name='Trip meter 2'),
                Sensor(attr='fuelAmount',
                       name='Fuel amount',
                       icon='mdi:gas-station',
                       unit='L'),
                Sensor(attr='fuelAmountLevel',
                       name='Fuel level',
                       icon='mdi:water-percent',
                       unit='%'),
                FuelConsumption(),
                Sensor(attr='distanceToEmpty',
                       name='Range',
                       icon='mdi:ruler',
                       unit='km'),
                Sensor(attr='hvBattery.distanceToHVBatteryEmpty',
                       name='Battery range',
                       icon='mdi:ruler',
                       unit='km'),
                Sensor(attr='hvBattery.hvBatteryLevel',
                       name='Battery level',
                       icon='mdi:battery',
                       unit='%'),
                Sensor(attr='hvBattery.timeToHVBatteryFullyCharged',
                       name='Battery Range',
                       icon='mdi:clock',
                       unit='minutes'),
                BatteryChargeStatus(),
                Engine(),
                BinarySensor(attr='doors.hoodOpen',
                             name='Hood',
                             device_class='door'),
                BinarySensor(attr='doors.frontLeftDoorOpen',
                             name='Front left door',
                             device_class='door'),
                BinarySensor(attr='doors.frontRightDoorOpen',
                             name='Front right door',
                             device_class='door'),
                BinarySensor(attr='doors.rearLeftDoorOpen',
                             name='Rear left door',
                             device_class='door'),
                BinarySensor(attr='doors.rearRightDoorOpen',
                             name='Rear right door',
                             device_class='door'),
                BinarySensor(attr='windows.frontLeftWindowOpen',
                             name='Front left window',
                             device_class='window'),
                BinarySensor(attr='windows.frontRightWindowOpen',
                             name='Front right window',
                             device_class='window'),
                BinarySensor(attr='windows.rearLeftWindowOpen',
                             name='Rear left window',
                             device_class='window'),
                BinarySensor(attr='windows.rearRightWindowOpen',
                             name='Rear right window',
                             device_class='window'),
                BinarySensor(attr='tyrePressure.frontRightTyrePressure',
                             name='Front right tyre',
                             device_class='safety'),
                BinarySensor(attr='tyrePressure.frontLeftTyrePressure',
                             name='Front left tyre',
                             device_class='safety'),
                BinarySensor(attr='tyrePressure.rearRightTyrePressure',
                             name='Rear right tyre',
                             device_class='safety'),
                BinarySensor(attr='tyrePressure.rearLeftTyrePressure',
                             name='Rear left tyre',
                             device_class='safety'),
                BinarySensor(attr='washerFluidLevel',
                             name='Washer fluid',
                             device_class='safety'),
                BinarySensor(attr='brakeFluid',
                             name='Brake Fluid',
                             device_class='safety'),
                BinarySensor(attr='serviceWarningStatus',
                             name='Service',
                             device_class='safety'),
                BinarySensor(attr='bulbFailures',
                             name='Bulbs',
                             device_class='safety'),
                BinarySensor(attr='any_door_open',
                             name='Doors',
                             device_class='door'),
                BinarySensor(attr='any_window_open',
                             name='Windows',
                             device_class='door')
            ] if instrument.setup(vehicle, config)
        ]


def create_dashboards(self, connection, config):
    return (Dashboard(vehicle, config) for vehicle in connection.vehicles)
