# Volvo On Call

Retrieve statistics about your Volvo from the Volvo On Call (VOC) online service
No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

Also contains an MQTT gateway for publishing information and bidirectional communication with e.g. Home Assistant.

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
  --version             Show version
```

```
> /voc status
ABC123 (XC60/2014) ABCD1234567890 92891km (fuel 25% 210km)
    position: 12.34567890,12.34567890
    locked: yes
    heater: off
```
