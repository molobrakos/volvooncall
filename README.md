# Volvo On Call

[![CI](https://github.com/molobrakos/volvooncall/actions/workflows/ci.yml/badge.svg)](https://github.com/molobrakos/volvooncall/actions/workflows/ci.yml)

Retrieve statistics about your Volvo from the Volvo On Call (VOC) online service
No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

Also contains an MQTT gateway for publishing information and bidirectional communication with e.g. Home Assistant.

## system requirements

 - At least python 3.10 or higher

> For contributors: The `pytype` project does not yet support Python 3.11, so you must use 3.10 to run tests locally.

## dependencies

To use just the API in `volvooncall.py` or the Home Assistant bindings in `dashboard.py`, simply install the package as
usual with pip:

```sh
pip install volvooncall
```

To use console features (i.e. the `voc` command documented below):

```sh
pip install volvooncall[console]
```

To use MQTT features:

```sh
pip install volvooncall[mqtt]
```
 
## how to use

```
> voc --help
Retrieve information from VOC

Usage:
  voc (-h | --help)
  voc --version
  voc [-v|-vv] [options] list
  voc [-v|-vv] [options] status
  voc [-v|-vv] [options] trips
  voc [-v|-vv] [options] owntracks
  voc [-v|-vv] [options] print [<attribute>]
  voc [-v|-vv] [options] (lock | unlock)
  voc [-v|-vv] [options] heater (start | stop)
  voc [-v|-vv] [options] engine (start | stop)
  voc [-v|-vv] [options] call <method>
  voc [-v|-vv] [options] mqtt

Options:
  -u <username>         VOC username
  -p <password>         VOC password
  -r <region>           VOC region (na, cn, etc.)
  -s <url>              VOC service URL
  -i <vin>              Vehicle VIN or registration number
  -g                    Geolocate position
  --owntracks_key=<key> Owntracks encryption password
  -I <interval>         Polling interval (seconds) [default: 300]
  -h --help             Show this message
  -v,-vv                Increase verbosity
  --scandinavian_miles  Report using Scandinavian miles instead of km ISO unit
  --usa_units           Report using USA units (miles, mph, mpg, gal, etc.)
  --version             Show version
```

Retrieving basic status:
```
> voc status
ABC123 (XC60/2014) ABCD1234567890 92891km (fuel 25% 210km)
    position: 12.34567890,12.34567890
    locked: yes
    heater: off
```

Printing raw properties:
```
> voc print windows.frontLeftWindowOpen
False
./voc print fuelAmount
45
```

Printing some relevant iofo:
```
> voc dashboard
ABC123 Door lock: Locked
ABC123 Heater: Off
ABC123 Odometer: 12792 mil
ABC123 Fuel amount: 32 L
...
```
Periodically polling the VOC server and republishing all information to a MQTT server
```
> voc mqtt
```

Configuration file in `$HOME/.voc.conf`:
```
username: <username>
password: <password>
```

# credits

https://web.archive.org/web/20180817103553/https://paulpeelen.com/2013/02/08/volvo-on-call-voc-api/ and a lot of random contributors
