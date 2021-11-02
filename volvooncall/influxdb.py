def format_metric(vehicle, metric, metric_alias=None, field_name='value'):
    value = vehicle.get_attr(metric)
    if isinstance(value, bool):
        if value:
            value = 1
        else:
            value = 0

    timestamp_attr = '{}Timestamp'.format("odometer")
    if vehicle.has_attr(timestamp_attr):
        timestamp_value = vehicle.get_attr(timestamp_attr).strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        timestamp_value = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        "measurement": metric if metric_alias is None else metric_alias,
        "tags": {
            "vin": vehicle.vin,
            "registration": vehicle.registration_number,
            "model": vehicle.vehicle_type,
            "modelyear": vehicle.model_year
        },
        "time": timestamp_value,
        "fields": {
            field_name: value
        }
    }

