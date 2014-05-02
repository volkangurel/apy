import datetime

import pytz


def snake_case_to_camel_case(name):
    return ''.join(x.capitalize() for x in name.split('_'))


def ms_to_datetime(value):
    return pytz.utc.localize(datetime.datetime.utcfromtimestamp(value / 1000))


def datetime_to_ms(value):
    return round(float(value.astimezone(pytz.utc).strftime('%s.%f')) * 1000)
