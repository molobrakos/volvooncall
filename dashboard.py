#  Utilities for integration with Home Assistant (directly or via MQTT)

CONF_SCANDINAVIAN_MILES = 'scandinavian_miles'

class Instrument:

    def __init__(self, component, attr, name):
        self.attr = attr
        self.component = component
        self.name = name
        self.vehicle = None

    def __str__(self):
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
        supported = self.attr + '_supported'
        if hasattr(self.vehicle, supported):
            return getattr(self.vehicle, supported)
        else:
            return hasattr(self.vehicle, self.attr)

    @property
    def state(self):
        return getattr(self.vehicle, self.attr)


class Sensor(Instrument):
    def __init__(self, attr, name, icon, unit):
        super().__init__('sensor', attr, name)
        self.icon = icon
        self.unit = unit

    def configurate(self, config):
        if (CONF_SCANDINAVIAN_MILES in config and
            'km' in self.unit):
            self.unit = 'mil'

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

    def __init__(self):
        super().__init__(attr='odometer',
                         name='Odometer',
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


class Lock(Instrument):
    def __init__(self):
        super().__init__(component='lock',
                         attr='lock',
                         name='Door lock')

    @property
    def state(self):
        return self.vehicle.is_locked

    def command(self, command):
        if state:
            self.vehichle.lock()
        else:
            self.vehichle.unlock()


class Switch(Instrument):
    def __init__(self, attr, name, icon=None):
        super().__init__(component='switch',
                         attr=attr,
                         name=name)
        self.icon = icon

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


class Position(Instrument):
    def __init__(self):
        super().__init__(component=None,
                         attr='position',
                         name='Position')

    @property
    def state(self):
        return (super().state['latitude'],
                super().state['longitude'])


class Dashboard():
    def __init__(self, vehicle, config):
        self.instruments = [
            instrument for instrument in [
                Position(),
                Lock(),
                Heater(),
                Odometer(),
                Sensor(attr='fuel_amount',
                       name='Fuel amount',
                       icon='mdi:gas-station',
                       unit='L'),
                Sensor(attr='fuel_amount_level',
                       name='Fuel level',
                       icon='mdi:water-percent',
                       unit='%'),
                FuelConsumption(),
                Sensor(attr='distance_to_empty',
                       name='Range',
                       icon='mdi:ruler',
                       unit='km'),
                BinarySensor(attr='washer_fluid_level',
                             name='Washer fluid',
                             device_class='safety'),
                BinarySensor(attr='brake_fluid',
                             name='Brake Fluid',
                             device_class='safety'),
                BinarySensor(attr='service_warning_status',
                             name='Service',
                             device_class='safety'),
                BinarySensor(attr='bulb_failures',
                             name='Bulbs',
                             device_class='safety'),
                BinarySensor(attr='any_door_open',
                             name='Doors',
                             device_class='door'),
                BinarySensor(attr='any_window_open',
                             name='Windows',
                             device_class='window')
            ] if instrument.setup(vehicle, config)
        ]

def create_dashboards(self, connection, config):
    return (Dashboard(vehicle, config) for vehicle in connection.vehicles)
