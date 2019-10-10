import os


class PrometheusFile:

    def __init__(self, file):
        self.filename = file
        self.tempfile = file + ".temp"

    def __enter__(self):
        self.file = open(self.tempfile, mode='w+')
        print("enter")
        return self.file.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.__exit__(exc_type, exc_val, exc_tb)
        os.rename(self.tempfile, self.filename)
        print("exit", exc_type, exc_val, exc_tb)


def format_metric(vehicles, metric, metric_alias=None, additional_labels=None):
    if additional_labels is None:
        additional_labels = {}
    for vehicle in vehicles:
        attrs = {
            "vin": vehicle.vin,
            "registration": vehicle.registration_number,
            "model": vehicle.vehicle_type,
            "modelyear": vehicle.model_year
        }
        attrs.update(additional_labels)

        attrs_list = ['{key}="{value}"'.format(key=key, value=value) for key, value in attrs.items()]

        timestamp_attr = '{}Timestamp'.format(metric)
        timestamp_value = ''
        if vehicle.has_attr(timestamp_attr):
            timestamp_value = int(vehicle.get_attr(timestamp_attr).timestamp() * 1000)

        value = vehicle.get_attr(metric)
        if isinstance(value, bool):
            if value:
                value = 1
            else:
                value = 0

        yield "{metric}{{{attrs}}} {value} {timestamp}".format(metric=metric if metric_alias is None else metric_alias,
                                                               attrs=','.join(attrs_list),
                                                               value=value,
                                                               timestamp=timestamp_value)


def write_metrics(file, vehicles):
    file.write("# HELP odometer Vehicle main odometer in meter.\n")
    file.write("# TYPE odometer counter\n")
    file.write("\n".join(format_metric(vehicles, 'odometer')))
    file.write("\n")

    file.write("# HELP trip_meter trip meters (in meter) differentiated by type\n")
    file.write("# TYPE trip_meter counter\n")
    file.write("\n".join(format_metric(vehicles, 'tripMeter1', 'trip_meter', {'type': 'TM'})))
    file.write("\n")
    file.write("\n".join(format_metric(vehicles, 'tripMeter2', 'trip_meter', {'type': 'TA'})))

    file.write("# HELP fuel_amount tank size and current volume in liters\n")
    file.write("# TYPE fuel_amount gauge\n")
    file.write("\n".join(format_metric(vehicles, 'fuelTankVolume', 'fuel_amount', {'type': 'capacity'})))
    file.write("\n")
    file.write("\n".join(format_metric(vehicles, 'fuelAmount', 'fuel_amount', {'type': 'level'})))
    file.write("\n")

    file.write("# HELP fuel_level tank level in percent\n")
    file.write("# TYPE fuel_level gauge\n")
    file.write("\n".join(format_metric(vehicles, 'fuelAmountLevel', 'fuel_level')))
    file.write("\n")

    file.write("# HELP car_status car status metrics\n")
    file.write("# TYPE car_status gauge\n")
    file.write("\n".join(format_metric(vehicles, 'engineRunning', 'car_status', {'type': 'engineRunning'})))
    file.write("\n")
    file.write("\n".join(format_metric(vehicles, 'carLocked', 'car_status', {'type': 'carLocked'})))
    file.write("\n")

    file.write("# HELP distance distance values\n")
    file.write("# TYPE distance gauge\n")
    file.write("\n".join(format_metric(vehicles, 'distanceToEmpty', 'distance', {'type': 'toEmpty'})))
    file.write("\n")

    file.write("# HELP consumption consumption values\n")
    file.write("# TYPE consumption gauge\n")
    file.write("\n".join(format_metric(vehicles, 'averageFuelConsumption', 'consumption', {'type': 'fuel'})))
    file.write("\n")

    file.write("# HELP speed speed values\n")
    file.write("# TYPE speed gauge\n")
    file.write("\n".join(format_metric(vehicles, 'averageSpeed', 'speed', {'type': 'average'})))
    file.write("\n")